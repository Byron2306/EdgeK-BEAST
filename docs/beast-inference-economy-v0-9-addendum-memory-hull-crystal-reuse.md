# Addendum A: Trust-Bound Residue and First-Class Crystal Reuse Integration Plane

Target paper: `BEAST_Inference_Economy_Inversion_Working_Paper_v0_9_compute_commons_final.pdf`

Date: 2026-06-28

## Placement in the Paper

This addendum fits after section 7.13.5 as section 7.14, with short back-references in sections 3.3, 4, 8, 9, and 10. The v0.9 paper already argues that verified inference can become reusable local compute. The new production layers answer the next question: how does BEAST authenticate, govern, observe, export, and safely reuse that compute across agents, caches, gateways, observability systems, and eval gates?

Recommended insertion points:

| Paper location | Addition |
| --- | --- |
| 3.3 Serving efficiency and stored compute | Add LMCache/GPTCache as concrete neighbors: physical KV/prefix reuse and semantic answer reuse. Clarify BEAST as the governance layer above both. |
| 4 BEAST Architecture | Extend Table 1 with Trust-bound residue and Crystal reuse integration plane. |
| 7.7 Inference conversion | Add Residue Seal and Memory Hull as the durable trust substrate for converted inference residue. |
| 7.12 Production runtime blueprint | Add Crystal Reuse Gateway as the runtime dispatcher in front of provider calls and public cache/trace/eval adapters. |
| 7.13 Verified Compute Commons | Add Agent Passport as identity/policy control for who may mint, read, append, export, or consume commons artifacts. |
| 8 Discussion | Frame the inversion as interoperable with public inference infrastructure without surrendering BEAST verifier authority. |
| 9 Claim Boundaries and 10 Threats | Bound external service claims: first-class adapter contracts exist; live service correctness remains separately probed and verifier-gated. |

## 7.14 Trust-Bound Residue and Public Crystal Reuse Integration Plane

The v0.9 commons layer establishes that verified work can be organized into semantic pages, crystals, portable spaces, witnesses, hardware cards, and Forge-node outputs. Two additional production layers make that commons operational: a trust-bound residue substrate and a first-class crystal reuse integration plane.

### 7.14.1 Memory Hull, Residue Seal, and Agent Passport

Memory Hull makes BEAST residue editable and inspectable without making it mutable in secret. Each operational memory record is written as human-readable Markdown plus a signed JSON sidecar. The sidecar binds the task, provider, decision, evidence, policy tags, caller identity, and Markdown hash. A verified hull can therefore act as an operator-facing memory vault while still detecting silent edits, stale sidecars, path escape, and evidence corruption.

Residue Seal provides the cryptographic boundary for this hull. It signs canonical payloads with purpose-specific Ed25519 signatures, records public-key identity, and rejects purpose mismatch or payload tampering. In the BEAST economy framing, this means a crystal is not merely a useful past answer; it is reusable residue with a verifiable authorship and payload boundary.

Agent Passport adds workload identity and policy to the same layer. BEAST agents receive SPIFFE-shaped local identities, and policy decisions are deterministic, deny-precedent, lintable, and optionally residue-sealed. This gives the commons a missing operational primitive: an answer to who was allowed to append memory, approve cloud escalation, consume a crystal, or export integration evidence.

Together, the three layers upgrade the paper's crystallized-compute claim from "verified work can be reused" to "verified work can be reused only when its identity, provenance, policy, and residue signatures still hold."

### 7.14.2 Crystal Reuse Gateway

The Crystal Reuse Gateway is the production insertion point before provider execution. For each request, it evaluates reuse in a strict order:

1. Verified semantic credit inside BEAST boundaries.
2. Exact cached answer for the prompt, model, and parameters.
3. Durable prefill identity for tokenizer, prompt prefix, and system prompt.
4. Optional semantic cache matcher.
5. KV cache block reuse through the BEAST KV transport adapter.
6. Provider fallback when reuse is not justified.

The gateway emits a sealed decision object containing action, source, confidence, reason, avoided-token estimate, request boundary, reuse payload, and telemetry. Provider responses can then be recorded back into durable storage and, when verified, into Memory Hull as crystallized inference residue.

### 7.14.3 Public Integration Plane

The gateway gives BEAST first-class contracts for public infrastructure while preserving BEAST's own execution authority:

| Integration | Role in BEAST | Claim boundary |
| --- | --- | --- |
| LMCache | External KV/prefix-cache substrate and manifest target for engine-level reuse. | Production restoration remains engine/tokenizer/privacy gated. |
| GPTCache | Semantic answer cache neighbor for approximate answer reuse. | BEAST still requires confidence, policy, and verifier boundaries. |
| LiteLLM | Provider gateway insertion point for routed model calls. | LiteLLM routes providers; BEAST governs reuse, identity, policy, and verification. |
| OpenLLMetry | OpenTelemetry-shaped spans for crystal decisions and lifecycle events. | Export format exists; collector delivery is deployment-specific. |
| Langfuse | Trace, dataset, score, and observation export for reuse decisions. | Observability does not itself authorize reuse. |
| TensorZero | Feedback candidate envelope for optimization loops. | Optimization candidates must not bypass BEAST promotion gates. |
| Promptfoo | Assertion/eval envelope for CI and reuse safety checks. | Eval assertions gate confidence; BEAST verifiers remain final authority. |
| vLLM/SGLang | Prefix-cache-capable execution engines adjacent to the reuse plane. | Engine capability cards require live probe and restore correctness evidence. |

This integration layer directly strengthens sections 3.3 and 7.12. It shows how BEAST can cooperate with text caches, KV caches, provider routers, trace systems, optimization loops, and eval frameworks without reducing its core claim to ordinary caching.

### 7.14.4 Updated Research Questions

Add two research questions to section 5:

RQ7. Can reusable inference artifacts remain useful while being identity-gated, residue-sealed, and policy-authorized across local agents?

RQ8. Can crystallized inference interoperate with public cache, gateway, observability, optimization, and evaluation ecosystems while preserving BEAST verifier authority?

### 7.14.5 Updated Claim Boundary

The production-ready claim is local and contract-level: BEAST can sign residue, verify Memory Hull sidecars, enforce Agent Passport policy, make sealed crystal reuse decisions, expose integration health, and export adapter-native payloads for LMCache, GPTCache, LiteLLM, OpenLLMetry, Langfuse, TensorZero, and Promptfoo.

The bounded claim is equally important: external services being configured does not prove live cache restoration, cross-engine KV correctness, marketplace value, autonomous adapter execution, or quality-preserving displacement. Those claims require separate live probes, mutation tests, privacy checks, verifier gauntlets, and production evidence.

### 7.14.6 Updated Architecture Row

Add these rows to Table 1:

| Layer | Governance question | Representative artifacts |
| --- | --- | --- |
| Trust-bound residue | Controls whether reusable work can be authenticated, edited visibly, and policy-authorized. | Memory Hull Markdown/sidecars, Residue Seal signatures, Agent Passport decisions. |
| Crystal reuse integration plane | Controls whether verified work can interoperate with cache, gateway, trace, optimization, and eval systems. | Crystal reuse decisions, LMCache manifests, GPTCache records, LiteLLM metadata, OpenLLMetry spans, Langfuse observations, TensorZero feedback, Promptfoo assertions. |

### 7.14.7 Addendum Synthesis

The new layers complete the operational arc of the paper. BEAST is no longer only a governed runtime that can produce crystals; it is a trust-bound reuse substrate. Memory Hull preserves the residue. Residue Seal proves the residue has not silently changed. Agent Passport decides which local actors may touch it. Crystal Reuse Gateway decides whether the next request may consume it. The integration registry then exports the decision into the public inference ecosystem without letting external systems become the source of truth.

