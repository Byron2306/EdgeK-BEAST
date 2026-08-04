# C4-X physical truth certificate · physical-truth-protocol-reuse-route-smoke-002

- Receipt: `sha256:1d32fab2f8b587cd200d01af5ed458382a0df362398c2c74588d845cb643618d`
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
