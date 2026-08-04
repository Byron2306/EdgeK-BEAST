# C4-X physical truth certificate · physical-truth-digest-bound-one-shot-001-protocol-reuse-route

- Receipt: `sha256:d8998aca7e009c8e2e847266a932cc839eabbec276094a87758b732b7ca8bccb`
- Public credit allowed: `False`
- Truth claim allowed: `False`
- Critical failures: `8`

## Certificate gates

- `c4x_truth`: `True`
- `sensorium_observation`: `False`
- `bpf_witness`: `False`
- `protocol_integrity`: `False`
- `memfd_custody`: `True`
- `guardian_custody`: `True`
- `reuse`: `False`
- `pq_transport`: `True`
- `commons_replication`: `False`
- `route_resilience`: `False`
- `psi_governance`: `False`
- `xdp_scope`: `False`

## Boundary

Final BEAST physical-truth claim. C4-X semantic proof, Sensorium/BPF observation, Crystal Bus protocol integrity, memfd/Guardian custody, reuse, post-quantum transport, Commons replication, route resilience, PSI governance, and scoped XDP must all pass independently. Every credited receipt is canonical-digest-bound, source-linked, authority/boundary checked, and signed or attested. Missing, stale, contradictory, or partial evidence lowers authority instead of being averaged away.
