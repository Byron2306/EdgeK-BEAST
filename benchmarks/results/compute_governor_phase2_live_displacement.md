# Compute Governor Phase 2 Live Displacement

- Provider: `nvidia_nim`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Candidate: `schema_validation`
- Shadow live provider calls: `1`
- Shadow transform verified/agreed: `True` / `True`
- Impact Fingerprint: `sha256:2776a9c5a5eec0fc136f2c8d7c651bcbbfb42ed78788aaf10c7bde4904a1d869`
- Impact reusable at enforcement: `True`
- Enforced provider execution requested: `False`
- Displaced live calls: `1`
- Result: `PASS`

## Claim Boundary

One transform-specific live shadow call was followed by an enforced deterministic displacement using a promoted proof and active Impact Fingerprint. This proves the runtime can avoid the matching live call; it does not generalize to unpromoted transforms or changed repositories.
