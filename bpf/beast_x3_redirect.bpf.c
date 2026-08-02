#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
struct { __uint(type,BPF_MAP_TYPE_XSKMAP); __uint(max_entries,64); __type(key,__u32); __type(value,__u32); } xsks SEC(".maps");
struct { __uint(type,BPF_MAP_TYPE_PERCPU_ARRAY); __uint(max_entries,4); __type(key,__u32); __type(value,__u64); } stats SEC(".maps");
SEC("xdp") int beast_x3_redirect(struct xdp_md *ctx) {
  void *data=(void *)(long)ctx->data;
  unsigned char *end=(void *)(long)ctx->data_end;
  unsigned char *p=data;
  if (p+14>end || p[12]!=0x08 || p[13]!=0x00) return XDP_PASS;
  unsigned char *ip=p+14;
  if (ip+20>end) return XDP_PASS;
  unsigned int ihl=(ip[0]&0x0f)*4;
  if (ihl<20 || ip+ihl+8>end || ip[9]!=17) return XDP_PASS;
  __u32 q=ctx->rx_queue_index,k=0; __u64 *seen=bpf_map_lookup_elem(&stats,&k); if(seen) __sync_fetch_and_add(seen,1);
  if (bpf_map_lookup_elem(&xsks,&q)) return bpf_redirect_map(&xsks,q,XDP_PASS);
  k=1; __u64 *miss=bpf_map_lookup_elem(&stats,&k); if(miss) __sync_fetch_and_add(miss,1);
  return XDP_PASS;
}
char LICENSE[] SEC("license")="GPL";
