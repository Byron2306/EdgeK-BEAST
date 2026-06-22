# Compute Governor Phase 3 Live False-Reuse Observation

- Provider: `nvidia_nim`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Live call succeeded: `True`
- Matched capability: `phase3-stale-schema-reuse`
- Impact reusable at boundary: `True`
- Live valid: `False`
- Reuse valid: `True`
- Behavior preserved against live baseline: `False`
- Observed false reuse: `True`
- False reuse count: `1`
- Result: `PASS`

## Claim Boundary

This is an intentionally adversarial live observation: Groq supplies one baseline answer, then an isolated stale promoted capability is reused without another provider call. A false reuse is counted only when the parsed live baseline disagrees with the reused result.
