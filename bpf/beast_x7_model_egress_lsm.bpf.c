// SPDX-License-Identifier: GPL-2.0
// BEAST X7: ARDA-measured model-egress admit-token enforcement (closure 2026-11-16).
// NEVER loaded by BEAST. Operator-only: see evidence/closure-2026-11-16/04-bypasses/REPORT.md.
//
// Hook: lsm/socket_connect. It reuses ARDA's live ring-0 policy instead of keeping a parallel one.
// The three arda_* maps are byte-identical to arda_physical_lsm.c (as in X6), so the loader binds them to ARDA's pins:
//   arda_active_generation_map -> /sys/fs/bpf/arda/active_generation_map  (cgroup_id -> generation = the MEASURED SET)
//   arda_policy_state_map      -> /sys/fs/bpf/arda/policy_state_map
//   arda_lockdown_map          -> /sys/fs/bpf/arda/lockdown_map
// This program only READS ARDA maps. ARDA's manifest stage/project flow decides who is measured.
//
// Decision for connect(2) from a task in cgroup C to destination D:
//   C not in ARDA's measured set (generation missing or 0)       -> allow (out of scope; ARDA does not cover C)
//   D not in beast_model_egress_dst (not a model endpoint)       -> allow
//   ARDA lockdown DENY_ALL                                       -> deny
//   no beast_admit_tokens[{tgid, D}]                             -> deny  (bypass: a model call with no Governor admit)
//   token expired | token ARDA generation != C's generation      -> deny  (re-measure / rotation invalidates tokens)
//   token policy prefix != ARDA generation_hash_prefix           -> deny  (policy changed since admit)
//   otherwise                                                    -> allow
// "deny" returns -EPERM only when beast_x7_mode[0] == 1 (enforce). The default 0 is audit: count the event and allow.
// Tokens are written only by scripts/beast_x7_admit_writer.py from Governor admits (governed_egress admit queue).
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_endian.h>

#define ARDA_LOCKDOWN_DENY_ALL 1
#define AF_INET 2
#define AF_INET6 10
#define EPERM 1

struct arda_policy_state {
    __u64 generation_hash_prefix;
    __u32 redline_rule_count;
    __u32 projection_flags;
};

// --- ARDA maps (read-only; identical definitions for map reuse) ---
struct { __uint(type, BPF_MAP_TYPE_HASH); __uint(max_entries, 1024); __type(key, __u64); __type(value, __u64); } arda_active_generation_map SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, struct arda_policy_state); } arda_policy_state_map SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, __u32); } arda_lockdown_map SEC(".maps");

// --- BEAST X7 maps (pinned under /sys/fs/bpf/beast/x7 by the operator) ---
struct beast_dst {            // model endpoint: IPv4 is stored v4-mapped (::ffff:a.b.c.d)
    __u8 addr[16];
    __u16 port;               // network byte order
    __u16 family;
};
struct beast_admit_key { __u32 tgid; __u32 pad; struct beast_dst dst; };
struct beast_admit_token {
    __u64 arda_generation;          // ARDA active generation of the consumer cgroup at admit time
    __u64 generation_hash_prefix;   // ARDA policy prefix at admit time
    __u64 governor_receipt_prefix;  // first 8 bytes of the Governor receipt hash
    __u64 expires_ns;               // bpf_ktime_get_ns() deadline
};
struct { __uint(type, BPF_MAP_TYPE_HASH); __uint(max_entries, 4096); __type(key, struct beast_dst); __type(value, __u8); } beast_model_egress_dst SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_LRU_HASH); __uint(max_entries, 16384); __type(key, struct beast_admit_key); __type(value, struct beast_admit_token); } beast_admit_tokens SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, __u32); } beast_x7_mode SEC(".maps");

enum { ST_SEEN, ST_UNMEASURED, ST_NOT_MODEL, ST_ALLOW, ST_LOCKDOWN, ST_NO_TOKEN, ST_EXPIRED, ST_GEN, ST_PREFIX, ST_DENIED, ST_AUDITED, ST_MAX };
struct { __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY); __uint(max_entries, ST_MAX); __type(key, __u32); __type(value, __u64); } beast_x7_stats SEC(".maps");

static __always_inline void bump(__u32 k) {
    __u64 *v = bpf_map_lookup_elem(&beast_x7_stats, &k);
    if (v) __sync_fetch_and_add(v, 1);
}

static __always_inline int verdict(__u32 reason) {
    __u32 zero = 0;
    __u32 *mode = bpf_map_lookup_elem(&beast_x7_mode, &zero);
    bump(reason);
    if (mode && *mode == 1) { bump(ST_DENIED); return -EPERM; }
    bump(ST_AUDITED);
    return 0;
}

SEC("lsm/socket_connect")
int BPF_PROG(beast_x7_model_egress, struct socket *sock, struct sockaddr *address, int addrlen, int ret)
{
    if (ret != 0) return ret;
    bump(ST_SEEN);
    __u64 cg = bpf_get_current_cgroup_id();
    __u64 *gen = bpf_map_lookup_elem(&arda_active_generation_map, &cg);
    if (!gen || *gen == 0) { bump(ST_UNMEASURED); return 0; }

    struct beast_dst dst = {};
    __u16 family = 0;
    bpf_probe_read_kernel(&family, sizeof(family), &address->sa_family);
    if (family == AF_INET && addrlen >= (int)sizeof(struct sockaddr_in)) {
        struct sockaddr_in *in4 = (struct sockaddr_in *)address;
        dst.addr[10] = 0xff; dst.addr[11] = 0xff;
        bpf_probe_read_kernel(&dst.addr[12], 4, &in4->sin_addr.s_addr);
        bpf_probe_read_kernel(&dst.port, 2, &in4->sin_port);
    } else if (family == AF_INET6 && addrlen >= (int)sizeof(struct sockaddr_in6)) {
        struct sockaddr_in6 *in6 = (struct sockaddr_in6 *)address;
        bpf_probe_read_kernel(&dst.addr[0], 16, &in6->sin6_addr);
        bpf_probe_read_kernel(&dst.port, 2, &in6->sin6_port);
    } else {
        bump(ST_NOT_MODEL); return 0;
    }
    dst.family = AF_INET6;   // canonical v6 / v4-mapped form
    if (!bpf_map_lookup_elem(&beast_model_egress_dst, &dst)) { bump(ST_NOT_MODEL); return 0; }

    __u32 zero = 0;
    __u32 *lockdown = bpf_map_lookup_elem(&arda_lockdown_map, &zero);
    if (lockdown && *lockdown == ARDA_LOCKDOWN_DENY_ALL) return verdict(ST_LOCKDOWN);

    struct beast_admit_key key = { .tgid = (__u32)(bpf_get_current_pid_tgid() >> 32) };
    key.dst = dst;
    struct beast_admit_token *tok = bpf_map_lookup_elem(&beast_admit_tokens, &key);
    if (!tok) return verdict(ST_NO_TOKEN);
    if (bpf_ktime_get_ns() > tok->expires_ns) return verdict(ST_EXPIRED);
    if (tok->arda_generation != *gen) return verdict(ST_GEN);
    struct arda_policy_state *policy = bpf_map_lookup_elem(&arda_policy_state_map, &zero);
    if (!policy || policy->generation_hash_prefix != tok->generation_hash_prefix) return verdict(ST_PREFIX);
    bump(ST_ALLOW);
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
