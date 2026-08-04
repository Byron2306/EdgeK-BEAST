# C4-X physical truth certificate · physical-truth-local-script-smoke-003

- Receipt: `sha256:9d701c651aceb677472acc219ef0c45d68b7cd357a3960d1a556e28ae0cae52a`
- Public credit allowed: `False`
- Truth claim allowed: `False`
- Critical failures: `10`

## Certificate gates

- `c4x_truth`: `True`
- `sensorium_observation`: `False`
- `bpf_witness`: `False`
- `protocol_integrity`: `False`
- `memfd_custody`: `True`
- `guardian_custody`: `False`
- `reuse`: `False`
- `pq_transport`: `False`
- `commons_replication`: `False`
- `route_resilience`: `False`
- `psi_governance`: `False`
- `xdp_scope`: `False`

## Boundary

Final BEAST physical-truth claim. C4-X semantic proof, Sensorium/BPF observation, Crystal Bus protocol integrity, memfd/Guardian custody, reuse, post-quantum transport, Commons replication, route resilience, PSI governance, and scoped XDP must all pass independently. Missing or partial evidence lowers authority instead of being averaged away.
