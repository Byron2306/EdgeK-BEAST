# C4-X physical truth certificate · physical-truth-digest-bound-audit-001

- Receipt: `sha256:0d75fa8b4560ff96ae3b80f3df45d9853b88bdd2a0267d0d90681f287d86ec35`
- Public credit allowed: `False`
- Truth claim allowed: `False`
- Critical failures: `12`

## Certificate gates

- `c4x_truth`: `False`
- `sensorium_observation`: `False`
- `bpf_witness`: `False`
- `protocol_integrity`: `False`
- `memfd_custody`: `False`
- `guardian_custody`: `False`
- `reuse`: `False`
- `pq_transport`: `False`
- `commons_replication`: `False`
- `route_resilience`: `False`
- `psi_governance`: `False`
- `xdp_scope`: `False`

## Boundary

Final BEAST physical-truth claim. C4-X semantic proof, Sensorium/BPF observation, Crystal Bus protocol integrity, memfd/Guardian custody, reuse, post-quantum transport, Commons replication, route resilience, PSI governance, and scoped XDP must all pass independently. Every credited receipt is canonical-digest-bound, source-linked, authority/boundary checked, and signed or attested. Missing, stale, contradictory, or partial evidence lowers authority instead of being averaged away.
