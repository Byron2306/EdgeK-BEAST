// SPDX-License-Identifier: GPL-2.0
// BEAST X6: ARDA-admitted XDP fast path (experimental; NEVER loaded by BEAST — operator-run commands only).
//
// Builds on X3 (beast_x3_redirect: UDP/IPv4 -> XSKMAP redirect, proven 2026-07-20 in the veth lab) and reuses
// ARDA's live ring-0 policy instead of a parallel one. The three arda_* maps below are byte-identical to
// /usr/lib/arda/src/arda_os/backend/services/bpf/arda_physical_lsm.c so the operator can bind them to ARDA's
// pinned maps at load time (bpftool "map name <n> pinned /sys/fs/bpf/arda/<pin>"); this program only READS them.
//
// Decision (fail-open to the kernel stack, never drop):
//   not UDP/IPv4                          -> XDP_PASS
//   ARDA lockdown (DENY_ALL)              -> XDP_PASS (slow path keeps every normal control)
//   ARDA redline triggered                -> XDP_PASS
//   no beast_admitted_flows entry         -> XDP_PASS
//   entry expired                         -> XDP_PASS
//   ARDA active generation for the entry's cgroup != entry generation (re-measure/rotate) -> XDP_PASS
//   ARDA policy generation_hash_prefix != entry prefix (policy changed) -> XDP_PASS
//   no AF_XDP socket on this queue        -> XDP_PASS
//   otherwise                             -> bpf_redirect_map(xsks, queue, XDP_PASS)
// beast_admitted_flows is written only by the BEAST flow writer after a Guardian lease + Compute Governor admit.
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>

#define ARDA_LOCKDOWN_DENY_ALL 1
#define ARDA_POLICY_FLAG_REDLINE_TRIGGERED 2

struct arda_policy_state {
    __u64 generation_hash_prefix;
    __u32 redline_rule_count;
    __u32 projection_flags;
};

// --- ARDA maps (read-only here; identical definitions for map reuse) ---
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, __u64);
    __type(value, __u64);
} arda_active_generation_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct arda_policy_state);
} arda_policy_state_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u32);
} arda_lockdown_map SEC(".maps");

// --- BEAST maps ---
struct beast_flow_key {
    __u32 saddr;   // network byte order, as on the wire
    __u32 daddr;
    __u16 sport;   // network byte order
    __u16 dport;
    __u8 proto;
    __u8 pad[3];
};

struct beast_flow_admission {
    __u64 cgroup_id;                // consumer cgroup bound by the Guardian lease
    __u64 arda_generation;          // ARDA active generation for that cgroup at admit time
    __u64 generation_hash_prefix;   // ARDA policy_state prefix at admit time
    __u64 guardian_lease_generation;
    __u64 governor_receipt_prefix;  // first 8 bytes of the Governor receipt hash
    __u64 expires_ns;               // bpf_ktime_get_ns() deadline
};

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 4096);
    __type(key, struct beast_flow_key);
    __type(value, struct beast_flow_admission);
} beast_admitted_flows SEC(".maps");

struct { __uint(type, BPF_MAP_TYPE_XSKMAP); __uint(max_entries, 64); __type(key, __u32); __type(value, __u32); } xsks SEC(".maps");

enum { ST_SEEN, ST_REDIRECT, ST_LOCKDOWN, ST_REDLINE, ST_MISS, ST_EXPIRED, ST_GEN, ST_PREFIX, ST_NOXSK, ST_MAX };
struct { __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY); __uint(max_entries, ST_MAX); __type(key, __u32); __type(value, __u64); } stats SEC(".maps");

static __always_inline int count(__u32 k, int action) {
    __u64 *v = bpf_map_lookup_elem(&stats, &k);
    if (v) __sync_fetch_and_add(v, 1);
    return action;
}

SEC("xdp") int beast_x6_admitted_fastpath(struct xdp_md *ctx) {
    unsigned char *p = (void *)(long)ctx->data;
    unsigned char *end = (void *)(long)ctx->data_end;
    if (p + 14 > end || p[12] != 0x08 || p[13] != 0x00) return XDP_PASS;
    unsigned char *ip = p + 14;
    if (ip + 20 > end) return XDP_PASS;
    __u32 ihl = (ip[0] & 0x0f) * 4;
    if (ihl < 20 || ip + ihl + 8 > end || ip[9] != 17) return XDP_PASS;
    unsigned char *udp = ip + ihl;
    count(ST_SEEN, 0);

    __u32 zero = 0;
    __u32 *lockdown = bpf_map_lookup_elem(&arda_lockdown_map, &zero);
    if (!lockdown || *lockdown == ARDA_LOCKDOWN_DENY_ALL) return count(ST_LOCKDOWN, XDP_PASS);
    struct arda_policy_state *policy = bpf_map_lookup_elem(&arda_policy_state_map, &zero);
    if (!policy || (policy->projection_flags & ARDA_POLICY_FLAG_REDLINE_TRIGGERED)) return count(ST_REDLINE, XDP_PASS);

    struct beast_flow_key key = {};
    __builtin_memcpy(&key.saddr, ip + 12, 4);
    __builtin_memcpy(&key.daddr, ip + 16, 4);
    __builtin_memcpy(&key.sport, udp, 2);
    __builtin_memcpy(&key.dport, udp + 2, 2);
    key.proto = 17;
    struct beast_flow_admission *flow = bpf_map_lookup_elem(&beast_admitted_flows, &key);
    if (!flow) return count(ST_MISS, XDP_PASS);
    if (bpf_ktime_get_ns() > flow->expires_ns) return count(ST_EXPIRED, XDP_PASS);
    __u64 cg = flow->cgroup_id;
    __u64 *generation = bpf_map_lookup_elem(&arda_active_generation_map, &cg);
    if (!generation || *generation == 0 || *generation != flow->arda_generation) return count(ST_GEN, XDP_PASS);
    if (policy->generation_hash_prefix != flow->generation_hash_prefix) return count(ST_PREFIX, XDP_PASS);

    __u32 q = ctx->rx_queue_index;
    if (!bpf_map_lookup_elem(&xsks, &q)) return count(ST_NOXSK, XDP_PASS);
    count(ST_REDIRECT, 0);
    return bpf_redirect_map(&xsks, q, XDP_PASS);
}

char LICENSE[] SEC("license") = "GPL";
