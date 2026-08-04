# C4-X physical truth certificate · physical-truth-protocol-reuse-route-smoke-003

- Receipt: `sha256:cf045641be547af038a8627c354660844e51be89d58454b4a069d40398378946`
- Public credit allowed: `False`
- Truth claim allowed: `False`
- Critical failures: `5`

## Certificate gates

- `c4x_truth`: `True`
- `sensorium_observation`: `True`
- `bpf_witness`: `True`
- `protocol_integrity`: `True`
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
