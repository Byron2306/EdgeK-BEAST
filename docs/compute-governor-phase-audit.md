# Compute Governor Phase Audit

Date: `2026-06-20`

This audit distinguishes an implemented class from a runtime-wired and
evidence-proven capability. A phase is not complete merely because its engine
has unit tests.

## Maturity Matrix

| Phase | Engine | Runtime wired | Safety tested | Evidence | Audit status |
| --- | --- | --- | --- | --- | --- |
| 1. Shadow accounting | Yes | Yes, shared executor | Yes | 120 closure pairs, 120 token-calibration pairs, and 24-class xAI observation | Operational; continuous live calibration |
| 2. Deterministic displacement | Six adapters, proof gate, and allowlist | Yes for verified complete structured tasks | Proof, fallback, privacy, and executor boundaries tested | 120 paired local shadow attempts; no displaced live calls | Local preflight complete |
| 3. Verified reuse | Matching and fingerprint verifier | No promoted-capability source or reuse executor | Standalone drift checks tested | No avoided live calls | Standalone engine |
| 4. Adaptive inference | Budget/economist controller | No shared-executor routing call | Standalone budget tests | No routed production traffic | Standalone engine |
| 5. Streaming interception | Incremental parser prototype | No provider stream or cancellation hook | Heuristic unit tests | No measured early-stop savings | Prototype |
| 6. Crystallization | Candidate lifecycle and ablation harness | No automatic promotion/reuse boundary | Promotion and stale-fingerprint tests | No persistent production lifecycle | Standalone engine |
| 7. Durable inference storage | File-backed credit store and KV metadata layer | Forge-only partial use; no reuse path | Persistence/privacy tests | No runtime reuse savings | Standalone storage layer |

## Blocking Findings

### Phase 2

- `DeterministicTransformExecutor` dispatches all six allowlisted transforms
  from explicit structured work and persists only hashes and verifier evidence.
- The shared executor bypasses provider admission only for one explicitly
  complete result with a valid proof, successful verification, and calibrated
  output agreement whose hash is bound into the promoted proof.
- Partial work and every missing, stale, ambiguous, unverified, or mismatched
  result preserve the provider path.
- Local paired calibration passed 120/120 attempts. Live-provider displacement
  evidence and transform-specific production promotions remain open.

### Phase 3

- Reuse candidate names previously became fabricated capability records. This
  was removed; names are advisory hypotheses again.
- Current repository state is now mandatory and compared against the stored
  Impact Fingerprint.
- A real Chronicle/promotion/storage capability source and a verified replay
  executor are still required.

### Phase 4

- `AdaptiveInferenceController` is not called by the shared executor.
- A zero cloud-call budget and unavailable cost under a declared cost ceiling
  now fail closed.
- Route selection needs an execution adapter, approval resume path, and receipts.

### Phase 5

- The parser is not attached to an HTTP streaming response and cannot cancel an
  upstream generation.
- Schema validation is currently shallow and optional.
- Token-savings values are estimates rather than intercepted provider evidence.

### Phase 6

- Promotion now requires an Impact Fingerprint.
- Crystallized proofs now name the actual allowlisted transform instead of the
  generic string `deterministic`.
- Engine state is not persisted or automatically consulted at runtime.

### Phase 7

- Valid credits previously could not reload because metadata fields were passed
  into the dataclass constructor. The loader now filters schema metadata.
- Verified capabilities now require visible and hidden tests, an Impact
  Fingerprint, and an exact repository fingerprint before reuse.
- Prefill storage persists prompt hashes rather than raw system prompts.
- Writes are atomic and corrupt records are reported.
- Answer caching has no complete retrieval/runtime integration, and KV files are
  metadata plus bounded placeholder payloads rather than portable engine tensors.

## Recommended Order

1. Run transform-specific Phase 2 live ablations and promote only proofs whose
   Impact Fingerprints remain active.
2. Extend the runtime decision executor to apply deterministic results, reuse,
   approval, escalation, or provider fallback without bypassing receipts.
3. Connect Phase 6 promoted proofs and Phase 7 credits through one fingerprint-
   checked capability repository.
4. Integrate Phase 4 routing with the runtime governor and approval lifecycle.
5. Add real streaming cancellation last, against providers that expose a tested
   streaming transport.

## Claim Boundary

BEAST can claim live compute accounting, locally calibrated deterministic
execution, and tested standalone engines for later phases. It cannot yet claim
realized live deterministic savings, verified runtime
reuse, adaptive production routing, streaming token savings, or durable inference
reuse in the shared coding flow.
