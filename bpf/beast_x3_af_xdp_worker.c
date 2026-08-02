/*
 * BEAST X3 AF_XDP receive worker.
 *
 * This is deliberately a small native ownership boundary: it creates UMEM,
 * fills the FQ, owns the AF_XDP socket rings, loads the reviewed XSKMAP
 * redirect program, and removes only the program it attached on shutdown.
 * It does not fall back to UDP or pretend an AF_PACKET observation is XDP IO.
 */
#include <errno.h>
#include <getopt.h>
#include <net/if.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <linux/if_link.h>
#include <xdp/xsk.h>

#define BATCH_SIZE 64U

struct worker_config {
    const char *interface;
    const char *object_path;
    unsigned int queue_id;
    unsigned int frame_size;
    unsigned int frame_count;
    unsigned int duration_seconds;
    bool zero_copy;
    bool generic_xdp;
    bool echo;
};

struct worker_state {
    struct xsk_umem *umem;
    struct xsk_socket *xsk;
    struct xsk_ring_prod fill;
    struct xsk_ring_cons completion;
    struct xsk_ring_cons rx;
    struct xsk_ring_prod tx;
    struct bpf_object *object;
    void *umem_area;
    int ifindex;
    int xsk_map_fd;
    int stats_map_fd;
    int program_fd;
    unsigned int xdp_flags;
    bool attached;
    unsigned long long packets_rx;
    unsigned long long bytes_rx;
    unsigned long long fill_starvation;
    unsigned long long packets_tx;
    unsigned long long bytes_tx;
    unsigned long long tx_completions;
    unsigned long long tx_ring_full;
};

static volatile sig_atomic_t stop_requested;

static void request_stop(int signal_number) {
    (void)signal_number;
    stop_requested = 1;
}

static unsigned long long monotonic_ns(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (unsigned long long)now.tv_sec * 1000000000ULL + (unsigned long long)now.tv_nsec;
}

static int is_power_of_two(unsigned int value) {
    return value && !(value & (value - 1));
}

static void usage(const char *program) {
    fprintf(stderr,
        "Usage: %s --interface IFACE --object FILE [--queue N] [--duration SEC] "
        "[--frame-size BYTES] [--frame-count N] [--zero-copy] [--generic-xdp] [--echo]\n", program);
}

static int parse_args(int argc, char **argv, struct worker_config *config) {
    static const struct option options[] = {
        {"interface", required_argument, NULL, 'i'},
        {"object", required_argument, NULL, 'o'},
        {"queue", required_argument, NULL, 'q'},
        {"duration", required_argument, NULL, 'd'},
        {"frame-size", required_argument, NULL, 's'},
        {"frame-count", required_argument, NULL, 'n'},
        {"zero-copy", no_argument, NULL, 'z'},
        {"generic-xdp", no_argument, NULL, 'g'},
        {"echo", no_argument, NULL, 'e'},
        {"help", no_argument, NULL, 'h'},
        {NULL, 0, NULL, 0},
    };
    int option;
    *config = (struct worker_config){.frame_size = 2048, .frame_count = 2048};
    while ((option = getopt_long(argc, argv, "i:o:q:d:s:n:zgeh", options, NULL)) != -1) {
        switch (option) {
        case 'i': config->interface = optarg; break;
        case 'o': config->object_path = optarg; break;
        case 'q': config->queue_id = (unsigned int)strtoul(optarg, NULL, 10); break;
        case 'd': config->duration_seconds = (unsigned int)strtoul(optarg, NULL, 10); break;
        case 's': config->frame_size = (unsigned int)strtoul(optarg, NULL, 10); break;
        case 'n': config->frame_count = (unsigned int)strtoul(optarg, NULL, 10); break;
        case 'z': config->zero_copy = true; break;
        case 'g': config->generic_xdp = true; break;
        case 'e': config->echo = true; break;
        default: usage(argv[0]); return -EINVAL;
        }
    }
    if (!config->interface || !config->object_path || config->queue_id >= 64 ||
        !is_power_of_two(config->frame_count) ||
        config->frame_size < 2048 || config->frame_size % 2048 != 0) {
        usage(argv[0]);
        return -EINVAL;
    }
    return 0;
}

static int populate_fill_ring(struct worker_state *state, unsigned int frame_count, unsigned int frame_size) {
    unsigned int index;
    if (xsk_ring_prod__reserve(&state->fill, frame_count, &index) != frame_count)
        return -ENOSPC;
    for (unsigned int frame = 0; frame < frame_count; ++frame)
        *xsk_ring_prod__fill_addr(&state->fill, index + frame) = (unsigned long long)frame * frame_size;
    xsk_ring_prod__submit(&state->fill, frame_count);
    return 0;
}

static int recycle_rx_frames(struct worker_state *state, unsigned int rx_index, unsigned int received) {
    unsigned int fill_index;
    if (xsk_ring_prod__reserve(&state->fill, received, &fill_index) != received) {
        state->fill_starvation++;
        return -ENOSPC;
    }
    for (unsigned int offset = 0; offset < received; ++offset) {
        const struct xdp_desc *descriptor = xsk_ring_cons__rx_desc(&state->rx, rx_index + offset);
        state->packets_rx++;
        state->bytes_rx += descriptor->len;
        *xsk_ring_prod__fill_addr(&state->fill, fill_index + offset) = xsk_umem__extract_addr(descriptor->addr);
    }
    xsk_ring_prod__submit(&state->fill, received);
    xsk_ring_cons__release(&state->rx, received);
    return 0;
}

static unsigned short internet_checksum(const unsigned char *data, unsigned int length, unsigned int seed) {
    unsigned int sum = seed;
    for (unsigned int index = 0; index + 1 < length; index += 2)
        sum += ((unsigned int)data[index] << 8) | data[index + 1];
    if (length & 1) sum += (unsigned int)data[length - 1] << 8;
    while (sum >> 16) sum = (sum & 0xffffU) + (sum >> 16);
    return (unsigned short)~sum;
}

static void set_checksum(unsigned char *field, unsigned short checksum) {
    field[0] = (unsigned char)(checksum >> 8);
    field[1] = (unsigned char)(checksum & 0xff);
}

static void swap_endpoints(void *packet, unsigned int length) {
    unsigned char *bytes = packet;
    if (length < 42 || bytes[12] != 0x08 || bytes[13] != 0x00) return;
    unsigned int ihl = (bytes[14] & 0x0f) * 4;
    if (ihl < 20 || 14 + ihl + 8 > length || bytes[23] != 17) return;
    for (unsigned int index = 0; index < 6; ++index) {
        unsigned char value = bytes[index];
        bytes[index] = bytes[6 + index];
        bytes[6 + index] = value;
    }
    for (unsigned int index = 0; index < 4; ++index) {
        unsigned char value = bytes[26 + index];
        bytes[26 + index] = bytes[30 + index];
        bytes[30 + index] = value;
    }
    unsigned int udp = 14 + ihl;
    unsigned char port = bytes[udp];
    bytes[udp] = bytes[udp + 2];
    bytes[udp + 2] = port;
    port = bytes[udp + 1];
    bytes[udp + 1] = bytes[udp + 3];
    bytes[udp + 3] = port;
    unsigned int udp_length = ((unsigned int)bytes[udp + 4] << 8) | bytes[udp + 5];
    if (udp_length < 8 || udp + udp_length > length) return;
    /* AF_XDP sees ingress before a peer's checksum-offload completion. */
    bytes[24] = bytes[25] = 0;
    set_checksum(bytes + 24, internet_checksum(bytes + 14, ihl, 0));
    bytes[udp + 6] = bytes[udp + 7] = 0;
    unsigned int pseudo_header = 17 + udp_length;
    pseudo_header += ((unsigned int)bytes[26] << 8) | bytes[27];
    pseudo_header += ((unsigned int)bytes[28] << 8) | bytes[29];
    pseudo_header += ((unsigned int)bytes[30] << 8) | bytes[31];
    pseudo_header += ((unsigned int)bytes[32] << 8) | bytes[33];
    unsigned short udp_checksum = internet_checksum(bytes + udp, udp_length, pseudo_header);
    set_checksum(bytes + udp + 6, udp_checksum ? udp_checksum : 0xffff);
}

static void recycle_tx_completions(struct worker_state *state) {
    unsigned int completion_index;
    unsigned int completed = xsk_ring_cons__peek(&state->completion, BATCH_SIZE, &completion_index);
    if (!completed) return;
    unsigned int fill_index;
    if (xsk_ring_prod__reserve(&state->fill, completed, &fill_index) != completed) {
        state->fill_starvation++;
        xsk_ring_cons__release(&state->completion, completed);
        return;
    }
    for (unsigned int offset = 0; offset < completed; ++offset)
        *xsk_ring_prod__fill_addr(&state->fill, fill_index + offset) =
            xsk_umem__extract_addr(*xsk_ring_cons__comp_addr(&state->completion, completion_index + offset));
    xsk_ring_prod__submit(&state->fill, completed);
    xsk_ring_cons__release(&state->completion, completed);
    state->tx_completions += completed;
}

static int echo_rx_frames(struct worker_state *state, unsigned int rx_index, unsigned int received) {
    unsigned int tx_index;
    if (xsk_ring_prod__reserve(&state->tx, received, &tx_index) != received) {
        state->tx_ring_full++;
        return recycle_rx_frames(state, rx_index, received);
    }
    for (unsigned int offset = 0; offset < received; ++offset) {
        const struct xdp_desc *received_desc = xsk_ring_cons__rx_desc(&state->rx, rx_index + offset);
        struct xdp_desc *transmit_desc = xsk_ring_prod__tx_desc(&state->tx, tx_index + offset);
        swap_endpoints(xsk_umem__get_data(state->umem_area, received_desc->addr), received_desc->len);
        *transmit_desc = *received_desc;
        state->packets_rx++;
        state->bytes_rx += received_desc->len;
        state->packets_tx++;
        state->bytes_tx += received_desc->len;
    }
    xsk_ring_prod__submit(&state->tx, received);
    xsk_ring_cons__release(&state->rx, received);
    if (xsk_ring_prod__needs_wakeup(&state->tx))
        (void)sendto(xsk_socket__fd(state->xsk), NULL, 0, MSG_DONTWAIT, NULL, 0);
    return 0;
}

static unsigned long long stat_total(int map_fd, unsigned int key) {
    int cpus = libbpf_num_possible_cpus();
    if (map_fd < 0 || cpus <= 0) return 0;
    unsigned long long *values = calloc((size_t)cpus, sizeof(*values));
    if (!values) return 0;
    unsigned long long total = 0;
    if (bpf_map_lookup_elem(map_fd, &key, values) == 0)
        for (int cpu = 0; cpu < cpus; ++cpu) total += values[cpu];
    free(values);
    return total;
}

static void cleanup(struct worker_state *state) {
    if (state->attached) {
        /* Do not detach a program that another owner installed after us. */
        struct bpf_xdp_attach_opts options = {
            .sz = sizeof(options),
            .old_prog_fd = state->program_fd,
        };
        (void)bpf_xdp_detach(state->ifindex, state->xdp_flags, &options);
    }
    if (state->xsk) xsk_socket__delete(state->xsk);
    if (state->umem) (void)xsk_umem__delete(state->umem);
    if (state->object) bpf_object__close(state->object);
    free(state->umem_area);
}

static int open_worker(const struct worker_config *config, struct worker_state *state) {
    int result;
    struct xsk_umem_config umem_config = {
        .fill_size = config->frame_count,
        .comp_size = config->frame_count,
        .frame_size = config->frame_size,
        .frame_headroom = 0,
        .flags = 0,
    };
    struct xsk_socket_config socket_config = {
        .rx_size = config->frame_count,
        .tx_size = config->echo ? config->frame_count : 0,
        .libxdp_flags = XSK_LIBXDP_FLAGS__INHIBIT_PROG_LOAD,
        .xdp_flags = config->generic_xdp ? XDP_FLAGS_SKB_MODE : 0,
        .bind_flags = XDP_USE_NEED_WAKEUP | (config->zero_copy ? XDP_ZEROCOPY : XDP_COPY),
    };

    state->ifindex = if_nametoindex(config->interface);
    if (!state->ifindex) return -errno;
    result = posix_memalign(&state->umem_area, getpagesize(),
        (size_t)config->frame_count * config->frame_size);
    if (result) return -result;
    memset(state->umem_area, 0, (size_t)config->frame_count * config->frame_size);
    result = xsk_umem__create(&state->umem, state->umem_area,
        (unsigned long long)config->frame_count * config->frame_size,
        &state->fill, &state->completion, &umem_config);
    if (result) return result;
    result = populate_fill_ring(state, config->frame_count, config->frame_size);
    if (result) return result;

    state->object = bpf_object__open_file(config->object_path, NULL);
    if (!state->object || libbpf_get_error(state->object)) return -ENOENT;
    if (bpf_object__load(state->object)) return -EACCES;
    struct bpf_program *program = bpf_object__find_program_by_name(state->object, "beast_x3_redirect");
    struct bpf_map *xsk_map = bpf_object__find_map_by_name(state->object, "xsks");
    struct bpf_map *stats_map = bpf_object__find_map_by_name(state->object, "stats");
    if (!program || !xsk_map || !stats_map) return -ENOENT;
    state->program_fd = bpf_program__fd(program);
    state->xsk_map_fd = bpf_map__fd(xsk_map);
    state->stats_map_fd = bpf_map__fd(stats_map);

    /* UPDATE_IF_NOEXIST preserves any program already owned by the namespace. */
    state->xdp_flags = socket_config.xdp_flags;
    result = bpf_xdp_attach(state->ifindex, state->program_fd,
        XDP_FLAGS_UPDATE_IF_NOEXIST | state->xdp_flags, NULL);
    if (result) return result;
    state->attached = true;
    result = xsk_socket__create(&state->xsk, config->interface, config->queue_id,
        state->umem, &state->rx, config->echo ? &state->tx : NULL, &socket_config);
    if (result) return result;
    unsigned int key = config->queue_id;
    result = bpf_map_update_elem(state->xsk_map_fd, &key, &(int){xsk_socket__fd(state->xsk)}, BPF_ANY);
    if (result) return -errno;
    return 0;
}

int main(int argc, char **argv) {
    struct worker_config config;
    struct worker_state state = {.xsk_map_fd = -1, .stats_map_fd = -1, .program_fd = -1};
    int result = parse_args(argc, argv, &config);
    if (result) return 64;
    signal(SIGINT, request_stop);
    signal(SIGTERM, request_stop);
    result = open_worker(&config, &state);
    if (result) {
        fprintf(stderr, "AF_XDP worker setup failed: %s (%d)\n", strerror(-result), result);
        cleanup(&state);
        return 1;
    }

    unsigned long long started = monotonic_ns();
    unsigned long long deadline = config.duration_seconds ? started + (unsigned long long)config.duration_seconds * 1000000000ULL : 0;
    struct pollfd poll_fd = {.fd = xsk_socket__fd(state.xsk), .events = POLLIN};
    while (!stop_requested && (!deadline || monotonic_ns() < deadline)) {
        recycle_tx_completions(&state);
        unsigned int index;
        unsigned int received = xsk_ring_cons__peek(&state.rx, BATCH_SIZE, &index);
        if (received) {
            if (config.echo) (void)echo_rx_frames(&state, index, received);
            else (void)recycle_rx_frames(&state, index, received);
            continue;
        }
        (void)poll(&poll_fd, 1, 100);
    }
    unsigned long long elapsed_ns = monotonic_ns() - started;
    printf("{\"mode\":\"af_xdp_%s%s\",\"interface\":\"%s\",\"queue_id\":%u,"
           "\"packets_rx\":%llu,\"bytes_rx\":%llu,\"fill_starvation\":%llu,"
           "\"packets_tx\":%llu,\"bytes_tx\":%llu,\"tx_completions\":%llu,\"tx_ring_full\":%llu,"
           "\"xdp_packets_seen\":%llu,\"xdp_socket_misses\":%llu,\"elapsed_ms\":%.3f}\n",
        config.zero_copy ? "zero_copy" : "copy", config.echo ? "_echo" : "", config.interface, config.queue_id,
        state.packets_rx, state.bytes_rx, state.fill_starvation,
        state.packets_tx, state.bytes_tx, state.tx_completions, state.tx_ring_full,
        stat_total(state.stats_map_fd, 0), stat_total(state.stats_map_fd, 1),
        (double)elapsed_ns / 1000000.0);
    cleanup(&state);
    return 0;
}
