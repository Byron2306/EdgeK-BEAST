# Compute Governor Phase 4 Groq Routing Evidence

- Provider: `nvidia_nim`
- Model: `nvidia/nemotron-3-super-120b-a12b`
- Local adapter status: `succeeded`
- Local provider call requested: `False`
- Approval pause gate: `require_approval`
- Approval audit events: `approval_requested, approval_resumed`
- Approved Groq call requested: `True`
- Groq response id: `chatcmpl-a9cf0030d5bb60cd`
- Groq tokens: `140`
- Result: `PASS`

## Claim Boundary

This run proves Phase 4 local adapter execution, persisted approval request/resume audit, and one approved Groq provider route in a bounded live harness. It is production-routing evidence for the Groq endpoint, not a broad production traffic sample.
