# C4-X physical truth certificate · physical-truth-digest-bound-hardened-001

- Receipt: `sha256:3a593e75c89a54c773b0d6477a3032a965b9048a30e99de895efe0f7d3b0a3c1`
- Public credit allowed: `True`
- Truth claim allowed: `True`
- Critical failures: `0`

## Certificate gates

- `c4x_truth`: `True`
- `sensorium_observation`: `True`
- `bpf_witness`: `True`
- `protocol_integrity`: `True`
- `memfd_custody`: `True`
- `guardian_custody`: `True`
- `reuse`: `True`
- `pq_transport`: `True`
- `commons_replication`: `True`
- `route_resilience`: `True`
- `psi_governance`: `True`
- `xdp_scope`: `True`

## Boundary

Final BEAST physical-truth claim. C4-X semantic proof, Sensorium/BPF observation, Crystal Bus protocol integrity, memfd/Guardian custody, reuse, post-quantum transport, Commons replication, route resilience, PSI governance, and scoped XDP must all pass independently. Every credited receipt is canonical-digest-bound, source-linked, authority/boundary checked, and signed or attested. Missing, stale, contradictory, or partial evidence lowers authority instead of being averaged away.
