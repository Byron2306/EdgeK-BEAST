// SPDX-License-Identifier: GPL-2.0
// BEAST X1 read-only observation plane. No override, redirect, LSM deny, or packet mutation programs.
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

char LICENSE[] SEC("license") = "GPL";
#define COMM_LEN 16

enum beast_kind { BEAST_EXEC=1, BEAST_EXIT=2, BEAST_TCP_CONNECT=3, BEAST_SOCKET_BIND=4,
                  BEAST_FILE_MUTATION=5, BEAST_SCHED_LATENCY=6, BEAST_NET_BYTES=7 };

/* This layout is the X2 wire contract: 80 bytes, little-endian, no padding. */
struct beast_event {
    __u64 ts_ns;
    __u32 cpu, pid, tgid, uid, gid, kind;
    __u64 cgroup_id, sequence;
    char comm[COMM_LEN];
    __u64 value_a, value_b;
};

struct { __uint(type, BPF_MAP_TYPE_RINGBUF); __uint(max_entries, 1 << 24); } events SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, __u64); } sequence SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, __u64); } loss_counters SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_LRU_HASH); __uint(max_entries, 32768); __type(key, __u32); __type(value, __u64); } wakeups SEC(".maps");
/* Set by the native loader so the observer never observes its own JSONL writes. */
struct { __uint(type, BPF_MAP_TYPE_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, __u32); } observer_tgid SEC(".maps");

#define SCHED_SAMPLE_MASK 0x3ff /* at most one scheduler event in 1024 */
#define WRITE_SAMPLE_MASK 0x7f  /* at most one file-mutation event in 128 */

static __always_inline int is_observer_process(void) {
    __u32 z = 0;
    __u32 *observer = bpf_map_lookup_elem(&observer_tgid, &z);
    return observer && *observer && *observer == (__u32)(bpf_get_current_pid_tgid() >> 32);
}

static __always_inline struct beast_event *begin(__u32 kind) {
    if (is_observer_process()) return 0;
    struct beast_event *e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
    __u32 z=0; if (!e) { __u64 *p=bpf_map_lookup_elem(&loss_counters,&z); if(p) __sync_fetch_and_add(p,1); return 0; }
    __u64 id=bpf_get_current_pid_tgid(), ug=bpf_get_current_uid_gid();
    e->ts_ns=bpf_ktime_get_ns(); e->cgroup_id=bpf_get_current_cgroup_id(); e->kind=kind;
    e->cpu=bpf_get_smp_processor_id(); e->pid=(__u32)id; e->tgid=id>>32; e->uid=(__u32)ug; e->gid=ug>>32;
    __u64 *s=bpf_map_lookup_elem(&sequence,&z); e->sequence=s ? __sync_fetch_and_add(s,1)+1 : 0;
    bpf_get_current_comm(e->comm,sizeof(e->comm)); return e;
}
static __always_inline int submit(__u32 kind, __u64 a, __u64 b) { struct beast_event *e=begin(kind); if(!e)return 0; e->value_a=a;e->value_b=b;bpf_ringbuf_submit(e,0);return 0; }

SEC("tracepoint/sched/sched_process_exec") int on_exec(void *ctx){ return submit(BEAST_EXEC,0,0); }
SEC("tracepoint/sched/sched_process_exit") int on_exit(void *ctx){ return submit(BEAST_EXIT,0,0); }
/* Stable syscall tracepoints are portable across kernels that do not expose
 * attachable tcp_v4_connect/__sys_bind kprobe symbols. */
SEC("tracepoint/syscalls/sys_enter_connect") int on_tcp_connect(void *ctx){ return submit(BEAST_TCP_CONNECT,0,0); }
SEC("tracepoint/syscalls/sys_enter_bind") int on_bind(void *ctx){ return submit(BEAST_SOCKET_BIND,0,0); }
SEC("kprobe/vfs_write") int on_write(void *ctx){ if (bpf_get_prandom_u32() & WRITE_SAMPLE_MASK) return 0; return submit(BEAST_FILE_MUTATION,0,0); }
SEC("kprobe/vfs_pwrite") int on_pwrite(void *ctx){ if (bpf_get_prandom_u32() & WRITE_SAMPLE_MASK) return 0; return submit(BEAST_FILE_MUTATION,0,1); }
SEC("tracepoint/sched/sched_wakeup") int on_wakeup(void *ctx){ if (is_observer_process() || (bpf_get_prandom_u32() & SCHED_SAMPLE_MASK)) return 0; __u32 pid=(__u32)bpf_get_current_pid_tgid(); __u64 now=bpf_ktime_get_ns(); bpf_map_update_elem(&wakeups,&pid,&now,BPF_ANY); return 0; }
SEC("tracepoint/sched/sched_switch") int on_switch(void *ctx){ if (is_observer_process() || (bpf_get_prandom_u32() & SCHED_SAMPLE_MASK)) return 0; __u32 pid=(__u32)bpf_get_current_pid_tgid(); __u64 *start=bpf_map_lookup_elem(&wakeups,&pid); if(start){__u64 d=bpf_ktime_get_ns()-*start;bpf_map_delete_elem(&wakeups,&pid);return submit(BEAST_SCHED_LATENCY,d,pid);} return 0; }
SEC("tracepoint/net/net_dev_queue") int on_net_tx(void *ctx){ return submit(BEAST_NET_BYTES,0,1); }
SEC("tracepoint/net/netif_receive_skb") int on_net_rx(void *ctx){ return submit(BEAST_NET_BYTES,0,0); }
