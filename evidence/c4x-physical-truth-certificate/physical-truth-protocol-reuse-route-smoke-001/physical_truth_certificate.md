# C4-X physical truth certificate · physical-truth-protocol-reuse-route-smoke-001

- Receipt: `sha256:aaf5d6a14736abfa2f0302d62e9535092b2afa19fab773961276001d747117bd`
- Public credit allowed: `False`
- Truth claim allowed: `False`
- Critical failures: `6`

## Certificate gates

- `c4x_truth`: `True`
- `sensorium_observation`: `True`
- `bpf_witness`: `True`
- `protocol_integrity`: `False`
- `memfd_custody`: `True`
- `guardian_custody`: `True`
- `reuse`: `True`
- `pq_transport`: `False`
- `commons_replication`: `False`
- `route_resilience`: `False`
- `psi_governance`: `False`
- `xdp_scope`: `False`

## Boundary

Final BEAST physical-truth claim. C4-X semantic proof, Sensorium/BPF observation, Crystal Bus protocol integrity, memfd/Guardian custody, reuse, post-quantum transport, Commons replication, route resilience, PSI governance, and scoped XDP must all pass independently. Missing or partial evidence lowers authority instead of being averaged away.
