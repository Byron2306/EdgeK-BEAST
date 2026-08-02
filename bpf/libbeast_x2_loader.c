// SPDX-License-Identifier: GPL-2.0
/* Narrow, fail-closed libbpf ABI for the BEAST X2 observation runtime. */
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define BEAST_EVENT_SIZE 80
#define BEAST_QUEUE_CAPACITY 1024

struct beast_event { uint8_t bytes[BEAST_EVENT_SIZE]; };
struct queued_event { struct beast_event event; struct queued_event *next; };
struct beast_x2_handle {
    struct bpf_object *object;
    struct bpf_link *links[8];
    size_t link_count;
    unsigned int attached_mask;
    struct ring_buffer *ring;
    int loss_map_fd;
    struct queued_event *head, *tail;
    size_t queue_size;
    unsigned long long userspace_drops;
};

struct attachment_spec { const char *program, *kind, *target; int required; };
static const struct attachment_spec ATTACHMENTS[] = {
    {"on_exec", "tracepoint", "sched/sched_process_exec", 1},
    {"on_exit", "tracepoint", "sched/sched_process_exit", 1},
    {"on_wakeup", "tracepoint", "sched/sched_wakeup", 1},
    {"on_switch", "tracepoint", "sched/sched_switch", 1},
    {"on_tcp_connect", "tracepoint", "syscalls/sys_enter_connect", 0},
    {"on_bind", "tracepoint", "syscalls/sys_enter_bind", 0},
    {"on_write", "kprobe", "vfs_write", 0},
    {"on_pwrite", "kprobe", "vfs_pwrite", 0},
};

void beast_x2_close(void *opaque);

static int manifest_has(const char *json, const char *key, const char *value) {
    char needle[128];
    int written = snprintf(needle, sizeof(needle), "\"%s\"", key);
    if (written < 0 || (size_t)written >= sizeof(needle)) return 0;
    const char *cursor = json;
    while ((cursor = strstr(cursor, needle)) != NULL) {
        cursor += strlen(needle);
        while (*cursor == ' ' || *cursor == '\t' || *cursor == '\n' || *cursor == '\r') ++cursor;
        if (*cursor++ != ':') continue;
        while (*cursor == ' ' || *cursor == '\t' || *cursor == '\n' || *cursor == '\r') ++cursor;
        size_t length = strlen(value);
        if (*cursor == '"' && strncmp(cursor + 1, value, length) == 0 && cursor[length + 1] == '"') return 1;
    }
    return 0;
}

static size_t manifest_key_count(const char *json, const char *key) {
    char needle[128];
    int written = snprintf(needle, sizeof(needle), "\"%s\"", key);
    if (written < 0 || (size_t)written >= sizeof(needle)) return 0;
    size_t count = 0;
    const char *cursor = json;
    while ((cursor = strstr(cursor, needle)) != NULL) { ++count; cursor += strlen(needle); }
    return count;
}

static char *manifest_object_path(const char *json) {
    const char *key = strstr(json, "\"object_path\"");
    if (!key) return NULL;
    const char *colon = strchr(key, ':');
    if (!colon) return NULL;
    const char *start = strchr(colon, '"');
    if (!start) return NULL;
    ++start;
    const char *end = strchr(start, '"');
    if (!end || end == start) return NULL;
    size_t length = (size_t)(end - start);
    char *path = calloc(length + 1, 1);
    if (!path) return NULL;
    memcpy(path, start, length);
    return path;
}

static int validate_manifest(const char *json) {
    if (!json || !manifest_has(json, "ring_map", "events") || !manifest_has(json, "loss_map", "loss_counters")) return -EINVAL;
    if (manifest_key_count(json, "program") != 8 || manifest_key_count(json, "kind") != 8 || manifest_key_count(json, "target") != 8) return -EINVAL;
    for (size_t i = 0; i < sizeof(ATTACHMENTS) / sizeof(ATTACHMENTS[0]); ++i) {
        if (!manifest_has(json, "program", ATTACHMENTS[i].program) ||
            !manifest_has(json, "kind", ATTACHMENTS[i].kind) ||
            !manifest_has(json, "target", ATTACHMENTS[i].target)) return -EINVAL;
    }
    return 0;
}

static int enqueue_event(void *ctx, void *data, size_t size) {
    struct beast_x2_handle *handle = ctx;
    if (size != BEAST_EVENT_SIZE || handle->queue_size >= BEAST_QUEUE_CAPACITY) {
        handle->userspace_drops++;
        return 0;
    }
    struct queued_event *item = calloc(1, sizeof(*item));
    if (!item) { handle->userspace_drops++; return 0; }
    memcpy(item->event.bytes, data, BEAST_EVENT_SIZE);
    if (handle->tail) handle->tail->next = item; else handle->head = item;
    handle->tail = item;
    handle->queue_size++;
    return 0;
}

static struct bpf_link *attach_spec(struct bpf_program *program, const struct attachment_spec *spec) {
    if (strcmp(spec->kind, "tracepoint") == 0) {
        const char *slash = strchr(spec->target, '/');
        if (!slash) return NULL;
        char category[64]; size_t length = (size_t)(slash - spec->target);
        if (length >= sizeof(category)) return NULL;
        memcpy(category, spec->target, length); category[length] = '\0';
        return bpf_program__attach_tracepoint(program, category, slash + 1);
    }
    if (strcmp(spec->kind, "kprobe") == 0) return bpf_program__attach_kprobe(program, false, spec->target);
    if (strcmp(spec->kind, "kretprobe") == 0) return bpf_program__attach_kprobe(program, true, spec->target);
    return NULL;
}

void *beast_x2_open(const char *manifest_json, size_t manifest_len) {
    (void)manifest_len;
    if (validate_manifest(manifest_json) != 0) return NULL;
    char *path = manifest_object_path(manifest_json);
    if (!path) return NULL;
    struct beast_x2_handle *handle = calloc(1, sizeof(*handle));
    if (!handle) { free(path); return NULL; }
    handle->loss_map_fd = -1;
    libbpf_set_strict_mode(LIBBPF_STRICT_ALL);
    handle->object = bpf_object__open_file(path, NULL);
    free(path);
    if (!handle->object || libbpf_get_error(handle->object) || bpf_object__load(handle->object)) goto fail;
    struct bpf_map *observer_tgid = bpf_object__find_map_by_name(handle->object, "observer_tgid");
    if (!observer_tgid) goto fail;
    uint32_t observer_key = 0, observer_pid = (uint32_t)getpid();
    if (bpf_map_update_elem(bpf_map__fd(observer_tgid), &observer_key, &observer_pid, BPF_ANY) != 0) goto fail;
    for (size_t i = 0; i < sizeof(ATTACHMENTS) / sizeof(ATTACHMENTS[0]); ++i) {
        struct bpf_program *program = bpf_object__find_program_by_name(handle->object, ATTACHMENTS[i].program);
        if (!program) { if (ATTACHMENTS[i].required) goto fail; else continue; }
        struct bpf_link *link = attach_spec(program, &ATTACHMENTS[i]);
        if (!link || libbpf_get_error(link)) { if (ATTACHMENTS[i].required) goto fail; else continue; }
        handle->links[handle->link_count++] = link;
        handle->attached_mask |= 1U << i;
    }
    struct bpf_map *events = bpf_object__find_map_by_name(handle->object, "events");
    struct bpf_map *losses = bpf_object__find_map_by_name(handle->object, "loss_counters");
    if (!events || !losses) goto fail;
    handle->loss_map_fd = bpf_map__fd(losses);
    handle->ring = ring_buffer__new(bpf_map__fd(events), enqueue_event, handle, NULL);
    if (!handle->ring || libbpf_get_error(handle->ring)) goto fail;
    return handle;
fail:
    beast_x2_close(handle);
    return NULL;
}

unsigned int beast_x2_attachment_mask(void *opaque) {
    struct beast_x2_handle *handle = opaque;
    return handle ? handle->attached_mask : 0;
}

int beast_x2_poll(void *opaque, int timeout_ms, void *event_out, size_t event_cap) {
    struct beast_x2_handle *handle = opaque;
    if (!handle || !event_out || event_cap < BEAST_EVENT_SIZE) return -EINVAL;
    if (!handle->head) {
        int result = ring_buffer__poll(handle->ring, timeout_ms);
        if (result < 0) return result;
    }
    if (!handle->head) return 0;
    struct queued_event *item = handle->head;
    memcpy(event_out, item->event.bytes, BEAST_EVENT_SIZE);
    handle->head = item->next;
    if (!handle->head) handle->tail = NULL;
    free(item); handle->queue_size--;
    return BEAST_EVENT_SIZE;
}

unsigned long long beast_x2_loss(void *opaque) {
    struct beast_x2_handle *handle = opaque;
    if (!handle || handle->loss_map_fd < 0) return 0;
    int cpus = libbpf_num_possible_cpus();
    if (cpus <= 0) return handle->userspace_drops;
    unsigned long long *values = calloc((size_t)cpus, sizeof(*values));
    if (!values) return handle->userspace_drops;
    uint32_t key = 0; unsigned long long total = handle->userspace_drops;
    if (bpf_map_lookup_elem(handle->loss_map_fd, &key, values) == 0)
        for (int i = 0; i < cpus; ++i) total += values[i];
    free(values);
    return total;
}

void beast_x2_close(void *opaque) {
    struct beast_x2_handle *handle = opaque;
    if (!handle) return;
    if (handle->ring) ring_buffer__free(handle->ring);
    for (size_t i = 0; i < handle->link_count; ++i) bpf_link__destroy(handle->links[i]);
    if (handle->object) bpf_object__close(handle->object);
    while (handle->head) { struct queued_event *next = handle->head->next; free(handle->head); handle->head = next; }
    free(handle);
}
