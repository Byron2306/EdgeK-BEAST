# Compute Governor Phase 7 Runtime Reuse Evidence

- Provider baseline: `nvidia_nim` / `nvidia/nemotron-3-super-120b-a12b`
- Baseline tokens: `138`
- Answer replay type: `cached_answer`
- Prefill replay type: `kv_prefill`
- Provider calls displaced by replay: `2`
- Measured reuse tokens saved: `138`
- KV adapter payload round trip: `True`
- KV network manifest ready: `True`
- Result: `PASS`

## Claim Boundary

This bounded run uses one Groq baseline answer to measure replay savings, then proves the opt-in executor branch can replay a cached answer and prefill identity without another provider call. KV adapter evidence is local CPU transport with engine-native payload bytes.
