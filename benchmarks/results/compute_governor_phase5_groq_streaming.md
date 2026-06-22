# Compute Governor Phase 5 Groq Streaming Evidence

- Provider: `nvidia_nim`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Stop reason: `governed_object_complete`
- Upstream cancel requested: `True`
- Provider stream close observed: `True`
- Baseline completion tokens: `44`
- Emitted stream tokens: `9`
- Measured saved tokens: `35`
- Repair prompt executed: `True`
- Repaired valid: `True`
- Result: `PASS`

## Claim Boundary

This run uses Groq's OpenAI-compatible live stream, cancels after the first schema-valid governed object, measures saved tokens against a non-stream Groq completion baseline, and executes one live Groq repair prompt for an intentionally invalid governed object.
