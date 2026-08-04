# BEAST Synthesis and Compute Plan

**Status:** core contract slices implemented and verified; production hardening in
progress  
**Scope:** make inference a governed fallback, then progressively replace
verified repeated work with evidence-bound semantic, executable, and visual
artifacts.

## Desired operating model

```text
Client / IDE
  -> BEAST control plane (identity, policy, evidence, scheduling)
  -> exact result or Meaning/Scene Crystal when applicable
  -> deterministic realization/composition when fully resolved
  -> bounded local residual inference when fields remain unresolved
  -> approved cloud/provider inference only for novel work
  -> verification, receipt, and optional later promotion
```

GPUs are an optional capacity layer for large-model or image-model execution.
They are not the source of BEAST's policy, memory, artifact custody, or
deterministic reuse capabilities.

## Architectural decisions

- Keep `ResidualComputeGovernor` as the sole route selector. `SynthesisMode`
  is request metadata, not another router.
- Preserve the strict physical `CrystalGeneralizer`; introduce sibling semantic
  and scene generalizers with domain-specific admissibility rules.
- Treat Meaning Crystals and answer frames as portable, verified semantics.
  Treat KV state as a model- and engine-specific optimization only.
- Split reuse authority into exact answer, meaning, and surface caches. Fuzzy
  similarity can suggest a candidate but cannot authorize factual claims or
  actions.
- Treat Commons content as a signed, reproducible hypothesis until local
  verification and promotion. A Space definition does not confer execution
  authority.

## R0 — Runtime truth and single configuration authority *(complete)*

**Goal:** restore a healthy, observable local control plane before expanding
its capabilities.

1. ~~Make `.byron/services.yaml` the authoritative BEAST and Commons endpoint
   registry; change generated LiteLLM/proxy configuration to derive from it
   rather than duplicate endpoint defaults.~~
2. ~~Remove retired `8000` defaults from BEAST integration generation and use
   the registry-owned BEAST endpoint (`8101`).~~
3. ~~Reconcile the Commons listener to the designated enterprise port (`8601`).~~
4. ~~Diagnose and repair Guardian listener recovery; a systemd service is not
   healthy merely because it is repeatedly restarting.~~
5. ~~Add configuration and live-readiness tests that fail on registry/generator
   disagreement.~~
6. ~~Observe BEAST and Commons for ten uninterrupted minutes with stable restart
   counters, then attach the health/restart receipt.~~

**Acceptance:** BEAST and Commons each answer their declared health URL;
Guardian restart count remains stable during a 10-minute observation; generated
config contains no BEAST control-plane reference to retired port `8000`.

**Receipt:** `evidence/guardian-runtime-health-r0-2026-08-03.json` passed a
600-second observation with BEAST and Commons restart counters stable at `0`.

## T0 — Synthesis substrate *(complete)*

1. ~~Consolidate the two sealed-capsule implementations behind one typed,
   signed envelope.~~
2. ~~Add `SynthesisRequest`, `SynthesisReceipt`, and `SynthesisMode`
   (`exact`, `realize`, `execute`, `lexicalize`, `open`).~~
3. ~~Compose a `SynthesisPlane` from `ComputePlane`; retain the existing
   residual route ordering and its authority checks.~~

**Acceptance:** each synthesis request has a route decision, authority,
verification status, and durable receipt; no direct provider path bypasses it.

**Verification:** `tests/test_synthesis_plane.py`,
`tests/test_crystal_bus_capsule.py`, `tests/test_crystal_materializer.py`, and
`tests/test_compute_plane_integration.py` cover governed route decisions,
durable synthesis receipts, typed capsule envelopes, and production root
composition.

## T1 — BEAST operator language contracts *(complete)*

1. ~~Introduce `MeaningCrystal`, candidate meaning, evidence binding, answer
   frame, and explicit resolution states.~~
2. ~~Cover a bounded domain first: services, containers, models, repositories,
   files, deployments, logs, caches, Crystals, Commons nodes, and Spaces.~~
3. ~~Deterministically realize resolved answer frames in defined tones.~~
4. ~~Send only declared unresolved fields to the existing bounded residual
   solver; prohibit new facts, actions, and causal claims.~~
5. ~~Split answer-frame lexicalization residuals from code-repair residuals so
   operator-language completion packets no longer masquerade as
   `fill_replace_exact_new_value`.~~

**Acceptance:** ~~200 deterministic answer-frame realization cases show zero
unauthorized actions and zero unsupported factual additions; ambiguity is
explicit when evidence does not select a candidate meaning. Raw operator
utterance understanding is covered by H1's held-out corpus, not by this
contract-only realization corpus.~~

**Progress:** `tests/test_operator_language.py` covers bounded operator
domains, evidence-bound meanings, deterministic neutral/concise/status
realization, and residual lexicalization payloads. `tests/test_phase_c_residual_solver.py`
rejects undeclared residual output fields after provider execution.
It also validates required lexicalization fields, declared field types, and
length limits.
It also runs a 200-prompt acceptance corpus with zero unauthorized actions,
zero unsupported factual additions, and explicit ambiguity for evidence-free
cases.

## P1 — Production synthesis-plane wiring *(complete)*

1. ~~Replace the parked `SynthesisPlane(ResidualComputeGovernor({}), {})`
   composition with a real operator-language semantic candidate source and
   semantic-result executor.~~
2. ~~Route `/edgek/compute/operator-language` through `SynthesisPlane.run()`
   before returning the operator-language response.~~
3. ~~Enforce hard `SynthesisMode` to `ResidualRoute` compatibility so modes are
   contracts, not labels.~~
4. ~~Preserve case-sensitive file paths and bind temporal evidence digests to
   source stat identity or snapshot/world digest rather than a constant
   `request_time` label.~~

**Verification:** `tests/test_synthesis_plane.py` covers mode-route refusal,
`tests/test_compute_plane_integration.py` proves operator-language creates a
synthesis completion receipt, and `tests/test_operator_language_plane.py`
covers case-sensitive path preservation.

## H1 — Production operator-language integration *(complete)*

**Goal:** move from typed language objects to real operator interpretation
against BEAST's current world model without introducing a second route engine
or provider-dependent control path.

1. ~~Add an operator phrase normalizer for service-registry language.~~
2. ~~Add a bounded phrase lattice for endpoint, health, registry-summary, and
   unsupported-action intents.~~
3. ~~Bind service names, hostnames, and common aliases to the authoritative
   `.byron/services.yaml` registry.~~
4. ~~Adjudicate resolved, ambiguous, and unsupported prompts without guessing
   missing service identity.~~
5. ~~Produce deterministic answer frames and receipts with registry/evidence
   digests and provider-call/action witnesses.~~
6. ~~Compose the operator-language plane into `ComputePlane` and expose
   `/edgek/compute/operator-language`.~~
7. ~~Add unit and API tests for BEAST endpoint resolution, Commons health
   binding, ambiguity, read-only action refusal, and compute-plane receipt
   recording.~~
8. ~~Expand the same pattern to provider/model inventory, active repository
   state, file state, and the local Commons Space catalog boundary.~~
9. ~~Expand the same pattern to read-only container runtime inventory and local
   evidence-log receipts.~~
10. ~~Expand the same pattern to detailed Space records and local Commons
   reproduction-state receipts without letting operator language execute
   replay or promote hypotheses.~~
11. ~~Add a held-out operator prompt corpus before claiming broad
   operator-language coverage.~~

**Verification:** `tests/test_operator_language_plane.py` and
`tests/test_operator_language_api.py` cover the first production-bound
service-registry language slice plus provider/model, repository, file-state,
container-state, evidence-log, and empty Commons-catalog handling. The path is
read-only and provider-free. Detailed Space answers include manifest, receipt,
reproduction count, best local trust class/score, and the rule that remote or
imported Spaces remain hypotheses until reproduced and explicitly promoted
locally. `tests/test_operator_language_heldout_corpus.py` runs 42 held-out
operator prompts across service, provider/model, container, log, repository,
file, Commons Space, ambiguity, unsupported-query, unsafe-action, path-escape,
and git-metadata cases with zero provider calls and zero actions.

## T2 — Semantic crystallization and safe reuse *(complete)*

1. ~~Add a semantic generalizer separate from physical generalization.~~
2. ~~Promote repeated verified utterance-to-meaning-to-answer-frame episodes.~~
3. ~~Key reusable meaning by bounded semantic fingerprint plus schema,
   discourse, world, capability, evidence, policy, and temporal scope digests;
   keep exact normalized utterance digests as traceability, not the reuse
   ceiling.~~
4. ~~Add negative applicability conditions and invalidation tests.~~
5. ~~Seal the semantic reuse key and promotion receipt inside a
   `SemanticCrystalRecord` so replay no longer depends on a caller-supplied
   expected key digest.~~
6. ~~Add active/revoked/expired lifecycle checks, verifier-version drift
   refusal, appraisal digest binding, and a durable lifecycle index owned by
   `ComputePlane`.~~
7. ~~Add auditable operator-language paraphrase folding so equivalent prompts
   such as status/health/state reuse the same semantic crystal while endpoint
   or stale-world requests refuse.~~
8. ~~Wire promoted operator-language semantic crystals into `ComputePlane`
   replay, inside the existing `SynthesisPlane` executor, so paraphrased
   prompts can displace fresh interpretation without bypassing synthesis
   receipts or read-only/provider-free witnesses.~~
9. ~~Persist and reload full semantic crystal records so stored text
   capabilities survive a fresh `ComputePlane` process and can replay in later
   gauntlet runs.~~

**Acceptance:** false reuse and stale-world reuse are rejected in held-out
tests; provider-disabled replay works for promoted cases.

**Verification:** `tests/test_semantic_generalizer.py` covers repeated
verified promotion, bounded paraphrase promotion, stale key refusal, negative
applicability refusal, and provider-disabled semantic replay. It also covers
sealed-record replay, revocation, expiry, verifier-version drift, appraisal
binding, and durable lifecycle-index persistence. `tests/test_compute_plane_integration.py`
confirms the semantic generalizer and semantic crystal registry are separate
compute-plane components from the physical episode generalizer and verifies
explicit operator-language semantic promotion plus paraphrased replay through
the synthesis plane. `tests/test_generation_gauntlet_runner.py` verifies that
stored semantic crystals replay after a fresh gauntlet process.

## I1 — Deterministic visual synthesis *(complete)*

1. ~~Create a signed asset manifest, `SceneCrystal`, and deterministic
   compositor opcodes.~~
2. ~~Begin with mascot states, diagrams, status cards, and IDE assets.~~
3. ~~Verify canvas contract, asset provenance, output digest, and policy.~~
4. ~~Seal deterministic scene outputs into `SceneCapsule` custody envelopes
   that bind scene, manifest, receipt, policy, canvas, provenance, render-only
   authority, and no-network/no-provider/no-physical-effect scope.~~
5. ~~Wire scene capsule composition into `ComputePlane` and expose
   `/edgek/compute/scene-capsule` so visual artifacts are composed through the
   production custody boundary with evidence graph receipts and provider-call
   witnesses.~~

**Acceptance:** a 100-request visual corpus achieves at least 75% deterministic
composition with exact asset provenance.

**Verification:** `tests/test_scene_synthesis.py` covers the default BEAST
asset manifest, deterministic SVG composition, canvas bounds, output digest,
exact asset provenance, scene capsule sealing/refusal, and a 100-request corpus
that passes the 75% deterministic composition threshold.
`tests/test_compute_plane_integration.py` and `tests/test_operator_language_api.py`
cover runtime/API scene capsule composition, deterministic output, render-only
authority, and manifest-drift refusal.

## I2/I3 — Bounded visual residuals *(complete)*

1. ~~Add masks and region-only edits to Scene Crystals.~~
2. ~~Introduce a supervised CPU diffusion worker only for unresolved regions,
   with pinned engine/model digests, memory/time limits, no ambient network,
   fixed seed contracts, and sealed inputs/outputs.~~
   - ~~Add the pinned, no-network, fixed-seed worker contract, sealed
     input/output receipts, and verifier.~~
   - ~~Wire a real CPU diffusion engine/model behind the supervised worker
     contract.~~

**Acceptance:** generated pixels, rather than entire scenes, are bounded and
auditable; the verifier rejects missing provenance or out-of-budget work.

**Progress:** `tests/test_visual_residuals.py` covers region-only output,
fixed-seed determinism, pinned worker/model digests, no ambient network,
sealed input/output receipts, provenance checks, budget refusal, and the
seeded CPU region-diffusion backend.  It also now covers bounded prompt-intent
projection for visual regions, including color/object hints, local color
conditioning, intent-mismatch refusal receipts, and deterministic perceptual
feature receipts for center focus, edge density, luma variation, centroid
offset, and symmetry.  It also covers quantized visual feature embeddings and
equivalence receipts for near-identical verified regions whose raw bytes differ.

## C1 — Commons synthesis Spaces *(complete)*

~~Package semantic and visual capability artifacts with schemas, verifier,
negative cases, replay corpus, evidence, and reproducibility metadata. Remote
packages remain hypotheses until reproduced and promoted locally.~~

**Verification:** `tests/test_commons_synthesis_space.py` covers semantic and
visual synthesis packages, required schemas/verifier/negative cases/replay
corpus/evidence/reproducibility metadata, digest tamper refusal, and
verify-only remote hypothesis authority.

## C2 — Capability composition inference *(implemented)*

**Goal:** prove BEAST can think with compiled, verified capabilities rather
than only replaying one solved answer.

1. ~~Add a `CapabilityCompositionPlane` for digest-bound learned facts,
   questions, component selection, unsupported-gap refusal, and composition
   receipts.~~
2. ~~Implement the first hard slice: determine whether restarting one service
   could destabilize another from separate health, topology, restart-policy,
   current-evidence, and causal-rule facts.~~
3. ~~Refuse unsupported causal jumps when dependency and evidence are known but
   the destabilization rule is absent.~~
4. ~~Route only the tiny unresolved causal portion to a residual worker:
   `destabilization_risk_class` and `causal_rationale`; reject undeclared
   residual fields.~~
5. ~~Wire composition into `ComputePlane`, the evidence graph, capability
   learning, and `/edgek/compute/capability-composition/restart-risk`.~~
6. ~~Add a local gauntlet that emits durable JSON/Markdown receipts for fully
   composed, refused-gap, and residual-composed cases with zero provider
   calls.~~
7. ~~Expand composition beyond the first restart-risk chain to multiple
   families: transitive dependency topology, traffic-shift capacity, and
   deployment/rollback/SLO safety.~~
8. ~~Expose additional production surfaces at
   `/edgek/compute/capability-composition/traffic-shift` and
   `/edgek/compute/capability-composition/deployment-safety`.~~

**Acceptance:** unseen operational questions are answered from multiple
verified capability facts across at least three families; unsupported causal
or capacity gaps are refused instead of guessed; residual calls receive only
declared unresolved fields.

**Verification:** `tests/test_capability_composition.py` covers full
composition, transitive dependency composition, causal/capacity/deployment-gap
refusal, residual-only completion, and compute-plane capability-learning
projection. `tests/test_operator_language_api.py` covers the production API
restart, traffic-shift, and deployment-safety paths.

**Gauntlet receipt:** `scripts/run_capability_composition_gauntlet.py` writes
`evidence/capability-composition/*.json` and `.md` receipts.  The
`2026-08-03T000000-capability-composition-b` run produced 8 cases across 3
composition families: 4 composed cases, 2 unsupported refusals, 2 residual
compositions, 2 transitive dependency edges composed, residual scopes
`causal_gap_only` and `capacity_gap_only`, 0 provider calls used, and receipt
digest
`sha256:94f412353d03b63d61dcca7951b5d5ff052fd6f5ddfb428cc3645d9bd52054a0`.

## C3 — Visual capability composition inference *(implemented)*

**Goal:** prove BEAST can think with compiled, verified visual capabilities
rather than only replaying one generated image or one scene capsule.

1. ~~Add a `VisualCapabilityCompositionPlane` for digest-bound render-only
   visual facts, visual questions, component selection, unsupported-gap
   refusal, metadata-only residual routing, and visual composition receipts.~~
2. ~~Compose status-card scene answers from scene capsule, asset manifest,
   visual intent, layout anchor, and promoted visual asset facts.~~
3. ~~Compose promoted-region reuse from scene capsule, region mask, visual
   intent, promoted asset, quality receipt, intent receipt, perceptual receipt,
   feature embedding, and equivalence receipt facts.~~
4. ~~Compose layout safety from canvas, anchor, and asset dimensions, including
   render-only refutation for overflow instead of resizing/cropping/mutating.~~
5. ~~Refuse visual proof gaps instead of inventing pixels or assets; residual
   routing is restricted to metadata fields such as `asset_candidate_class`,
   `reuse_class`, and `visual_rationale`.~~
6. ~~Wire visual composition into `ComputePlane`, evidence graph, capability
   learning, and production API surfaces:
   `/edgek/compute/visual-composition/status-card`,
   `/edgek/compute/visual-composition/promoted-region-reuse`, and
   `/edgek/compute/visual-composition/layout-safety`.~~
7. ~~Add a visual composition gauntlet that emits durable JSON/Markdown
   receipts with zero provider calls and render-only authority.~~

**Acceptance:** unseen visual questions are answered from multiple verified
visual facts across at least three families; missing asset/equivalence gaps are
routed only as metadata; layout overflow is refuted without image mutation;
every case remains render-only and provider-free.

**Verification:** `tests/test_visual_capability_composition.py` covers
status-card composition, metadata-only asset-gap residuals, promoted-region
reuse through equivalence evidence, equivalence-gap refusal, layout overflow
refutation, and compute-plane learning projection. `tests/test_operator_language_api.py`
covers production API status-card and layout-safety paths.

**Gauntlet receipt:** `scripts/run_visual_composition_gauntlet.py` writes
`evidence/visual-composition/*.json` and `.md` receipts.  The
`2026-08-03T000000-visual-composition-a` run produced 6 cases across 3 visual
composition families: 3 composed cases, 2 residual compositions, 1 refuted
layout-overflow case, 6 render-only cases, residual scopes `asset_gap_only`
and `visual_equivalence_gap_only`, 0 provider calls used, and receipt digest
`sha256:5e509f2a17bff59cf2e51c913e38d3de5863d0544f1e33d45b2a1920d5b3874f`.

## C4 — Cross-modal capability composition *(implemented)*

**Goal:** prove BEAST can answer an operational question and render a
visual explanation from the same verified substrate under one joined receipt.

1. ~~Add a `CrossModalCompositionPlane` that binds operational composition
   receipts and render-only visual composition receipts without merging their
   claim scopes.~~
2. ~~Implement the first cross-modal family:
   restart-risk answer plus visual status/dependency explanation.~~
3. ~~Wire `ComputePlane.compose_cross_modal_restart_risk_visual()` to compose
   the text restart-risk receipt, visual status-card receipt, promoted-region
   reuse receipt, layout-safety receipt, and one cross-modal receipt.~~
4. ~~Expose `/edgek/compute/cross-modal/restart-risk-visual`.~~
5. ~~Preserve separate residual scopes for text causal gaps and visual metadata
   gaps; no child residual may request whole answers, pixels, assets, provider
   calls, actions, or authority expansion.~~
6. ~~Carry visual layout refutation honestly in the joined receipt instead of
   silently resizing, cropping, or mutating the image.~~
7. ~~Add a cross-modal gauntlet that emits durable JSON/Markdown receipts with
   zero provider calls.~~

**Acceptance:** one request can produce a composed operational answer and a
render-only visual explanation under a single cross-modal receipt; child text
and visual receipts remain independently auditable; layout/refusal/residual
states are preserved instead of being rounded into a happy path.

**Verification:** `tests/test_cross_modal_composition.py` covers direct receipt
binding, compute-plane learning projection, visual layout refutation inside a
joined receipt, and separated text/visual residual scopes. `tests/test_operator_language_api.py`
covers the production cross-modal API path.

**Gauntlet receipt:** `scripts/run_cross_modal_composition_gauntlet.py` writes
`evidence/cross-modal-composition/*.json` and `.md` receipts.  The
`2026-08-03T000000-cross-modal-composition-a` run produced 3 cross-modal
composed cases, 3 render-only cases, 9 joined child visual receipts, 1 visual
layout refutation, residual scopes `causal_gap_only`, `asset_gap_only`, and
`visual_equivalence_gap_only`, 0 provider calls used, and receipt digest
`sha256:a32a93586c5e35fe83bc3f4e57b0a055ff3947c76bc936cc46e8f7d46983fadd`.

## C5 — Canonical Proof Graph and cross-modal verification *(implemented)*

**Goal:** make the cross-modal claim undeniable: the visual is not generated
from the text answer, and the text is not interpreted from the visual. Both are
sibling views of one canonical proof graph.

1. ~~Add `app/kernel/compute/proof_graph.py` with typed evidence-bound proof
   claims, canonical proof graphs, text proof views, visual proof primitives,
   visual proof views, and a joined verifier.~~
2. ~~Bind every cross-modal receipt to `proof_graph_digest`, `text_proof_view`,
   `visual_proof_view`, `text_valid`, `scene_semantically_valid`,
   `scene_render_valid`, `current_claim_valid`, and `joined_verification`.~~
3. ~~Give visual primitives a proof grammar: supported claims render as
   `solid_edge_with_rule_badge`; unsupported claims render as
   `dashed_interruption_with_explicit_unsupported_label`; refuted claims render
   as `blocked_or_crossed_relation`; stale claims render as
   `clock_badge_and_faded_status`.~~
4. ~~Add stale-evidence handling: the proof graph and sibling views can still
   verify, but current-claim validity is false and cross-modal status becomes
   partial.~~
5. ~~Add cross-modal tamper verification: changing the text risk label or the
   visual risk primitive/render digest fails joined verification with
   `text_tamper` or `visual_tamper`.~~
6. ~~Upgrade the cross-modal gauntlet so it proves composed, layout-refuted,
   stale, and residual-scoped cases under the same proof-graph contract.~~

**Acceptance:** all text and visual outputs reference canonical claim IDs from
the same proof graph; every joined receipt binds proof graph, text view, and
visual view digests; stale truth is not treated as current truth; tampering
either modality fails; residual scope violations remain zero.

**Verification:** `tests/test_cross_modal_composition.py` covers proof-graph
binding, current-claim invalidation under stale evidence, visual proof grammar,
and text/visual tamper rejection. `tests/test_operator_language_api.py` still
covers the production cross-modal API path.

**Gauntlet receipt:** `scripts/run_cross_modal_composition_gauntlet.py` now
writes proof-graph upgraded receipts.  The
`2026-08-03T000000-cross-modal-proof-graph-a` run produced 4 cases: 3
cross-modal composed, 1 cross-modal partial due to stale evidence, 4 joined
verifications, 1 stale current-claim invalidation, 12 joined child visual
receipts, 1 layout refutation, text and visual tamper both rejected, residual
scope violations `0`, provider calls used `0`, and receipt digest
`sha256:9b37920155c2c6ff77ccaa449d916634d14e0932066b5b3de8bf4305b39ce8cf`.

## C6 — Proof-bound image-provider gate *(implemented)*

**Goal:** wire image-provider use without taking chances. A provider may paint
pixels, but BEAST must not trust or promote those pixels unless the request and
output are derived from the canonical visual proof view, not from the text
answer.

1. ~~Add `app/kernel/compute/visual_proof_provider_gate.py` with a canonical
   provider-prompt builder that uses only the proof graph plus visual proof
   primitive.~~
2. ~~Record `raw_text_answer_used=false` in proof-bound image prompts and bind
   the provider request to the expected proof prompt digest.~~
3. ~~Verify provider receipts against the provider request, output digest, and
   exact region boundary before any trust decision.~~
4. ~~Run deterministic quality, visual-intent, and perceptual checks on the
   returned region bytes.~~
5. ~~Refuse promotion unless the referenced claim is current and supported;
   stale/refuted/unsupported claims may be visualized as evidence states, but
   not promoted as truthful current assets.~~
6. ~~Add rejection tests for text/arbitrary prompt derivation, semantically
   wrong pixels, and stale-claim promotion.~~
7. ~~Add a proof-bound provider gauntlet receipt that proves one trusted case
   and three quarantined cases without live cloud spend.~~

**Acceptance:** provider-rendered image bytes are quarantined unless proof
prompt, provider receipt, output digest, region boundary, intent, perceptual
checks, and current supported proof status all verify. Text answers are not a
legal source for image-provider prompts.

**Verification:** `tests/test_visual_proof_provider_gate.py` covers successful
proof-bound image-provider output, prompt tamper rejection, wrong-pixel
rejection, and stale-claim promotion refusal.

**Gauntlet receipt:** `scripts/run_visual_proof_provider_gate_gauntlet.py`
writes `evidence/visual-proof-provider-gate/*.json` and `.md` receipts. The
`2026-08-03T000000-visual-proof-provider-gate-a` run produced 4 cases: 1
trusted for promotion, 3 quarantined, prompt tamper rejected, wrong pixels
rejected, stale claim blocked, raw text answer prompts `0`, live provider calls
`0`, and receipt digest
`sha256:b2de7e18d9ac0baa50329e20eb1ca5821a705e64d4f30aa2e7e2cdc64de04d53`.

## C7 — Proof-first cross-modal compiler *(implemented for restart-risk family)*

**Goal:** invert C5 from joined attestation into proof-first realization. The
proof graph must be compiled from verified facts/rules/policies/temporal
evidence before text or visual artifacts exist, and text/visual artifacts must
then be independently realized from that graph.

1. ~~Add `app/kernel/compute/proof_first_cross_modal.py` with an explicit
   restart-risk proof compiler, structured text frame, scene-plan compiler,
   deterministic SVG renderer, and semantic entailment checks.~~
2. ~~Route `ComputePlane.compose_cross_modal_restart_risk_visual()` through the
   proof-first compiler before creating the legacy text/visual composition
   receipts.~~
3. ~~Replace stale prose drift with structured text frames: stale claims now
   produce `risk_class=unknown_current_state` and
   `current_conclusion_allowed=false` before prose lexicalization.~~
4. ~~Split joined visual receipt binding from real artifact binding:
   `visual_receipt_set_digest` records child visual receipts, while
   `scene_plan_digest`, `rendered_artifact_digest`,
   `rendered_artifact_media_type`, and dimensions bind actual deterministic
   SVG artifact bytes.~~
5. ~~Stop layout overflow from reporting as render success: overflow keeps
   proof/text/scene semantics auditable but sets `scene_render_attempted=false`,
   `scene_render_valid=false`, `failure_class=layout_overflow`, and
   cross-modal status `partial`.~~
6. ~~Stop missing visual asset metadata from implying rendered success:
   metadata-only residuals leave `visual_asset_resolution=unresolved`,
   `placeholder_allowed=true`, `scene_render_valid=false`, and status
   `partial`.~~
7. ~~Add `residual_supported` to the proof vocabulary so residual inference
   can never masquerade as `rule_proven`; the strict restart proof keeps missing
   causal-rule claims unsupported unless a real rule digest exists.~~
8. ~~Upgrade the cross-modal gauntlet to actively attack residual scope with
   hostile forbidden fields and prove all attacks are rejected.~~

**Acceptance:** proof graphs compile before outputs; text semantic entailment
matches claim status; visual primitives all reference proof claims; actual text
and SVG artifact digests are bound; stale evidence is not presented as current;
layout failures are not render successes; residual suggestions are not called
rule-proven; hostile residual fields are rejected.

**Verification:** `tests/test_cross_modal_composition.py` now covers
proof-first execution, structured stale text, actual artifact digests, layout
overflow render failure, missing-asset render failure, and residual provenance.

**Gauntlet receipt:** `scripts/run_cross_modal_composition_gauntlet.py` now
writes proof-first receipts. The
`2026-08-03T000000-cross-modal-proof-first-a` run produced 4 cases: 1
cross-modal composed, 3 partial, 4 proof graphs compiled before outputs, 4 text
semantic entailment passes, 4 visual primitive entailment passes, actual text
and visual artifacts bound in all cases, 0 stale claims presented as current, 0
layout failures reported as renders, 0 residual claims called rule-proven, 3
hostile residual attempts, 3 hostile residuals rejected, 0 residual scope
violations, 0 provider calls used, and receipt digest
`sha256:617c58f02fc1cb8ddd3248a2c3e668f72391917740234ef4a25eb5039a9f6155`.

## C8 — C4-X Ultimate Deterministic Intelligence Gauntlet *(implemented in shadow mode)*

**Goal:** test whether the proof-first architecture scales beyond one
restart-risk path into a bounded deterministic intelligence claim across
multiple operational families, adversarial residual attacks, held-out renaming,
metamorphic changes, and exact artifact tamper checks.

1. ~~Import the C4-X isolated proof engine as
   `app/kernel/compute/deterministic_intelligence.py` without replacing the
   production `ComputePlane` path.~~
2. ~~Import `scripts/run_deterministic_intelligence_gauntlet.py`,
   `tests/test_deterministic_intelligence_gauntlet.py`, and
   `docs/BEAST_C4X_ULTIMATE_DETERMINISTIC_INTELLIGENCE_GAUNTLET.md`.~~
3. ~~Run the gauntlet inside this repository, not only inside the downloaded
   bundle, to prove it works with the actual workspace import path.~~
4. ~~Verify the C4-X engine alongside C6/C7 tests and the full BEAST suite.~~
5. ~~Preserve the honest integration boundary: C4-X is currently shadow-mode
   evidence, not yet the production `/edgek/compute/cross-modal/*`
   authority.~~

**Acceptance:** 12 proof-first scenarios pass across restart-risk,
traffic-shift, and deployment-safety families; exact text/SVG artifacts are
bound; honest partials stay partial; hostile residuals are rejected; stale
claims do not sound current; layout failures are not render successes;
metamorphic and held-out cases pass; provider calls remain zero.

**Verification:** `tests/test_deterministic_intelligence_gauntlet.py` covers
proof-first order, sibling text/visual outputs, stale language, missing causal
rule residuals, hostile residual rejection, missing visual assets, layout
overflow, exact-byte tamper rejection, held-out renaming, metamorphic capacity
change, and checksum-clean evidence.

**Gauntlet receipt:** `scripts/run_deterministic_intelligence_gauntlet.py`
produced workspace run `2026-08-03T000000-c4x-shadow-import-a` with 12
scenarios, 3 cross-modal families, 12 proof graphs compiled before outputs, 12
text entailment passes, 12 visual primitive entailment passes, 12 joined
receipts verified, 6 fully composed cases, 6 honest partial cases, 3 hostile
residuals rejected, 0 scope violations admitted, 0 stale-current drift, 0
layout failures reported as valid renders, 0 residual claims called
rule-proven, 0 provider calls used, ultimate pass `true`, and receipt digest
`sha256:928ecaff1e39eaff9c5f4819d5941011ba4b1adb73564241286ea42fecb80366`.

## C9 — Outsider breakthrough protocol *(reference benchmark implemented)*

**Goal:** make the claim legible to outsiders instead of only impressive to
the project. The public bar is not “BEAST passed our named scenarios.” The bar
is that a frozen engine survives held-out randomized domains selected after
freeze, runs reproducibly in a public repository, and compares directly against
obvious baselines.

1. ~~Add a shadow crystal replay command that shows gains without interfering
   with production: `scripts/replay_c4x_shadow_crystal.py` selects stored C4-X
   proof crystals from evidence, verifies graph/text/SVG custody, and emits an
   answer plus diagram with `provider_calls_used=0`.~~
2. ~~Add `scripts/run_c4x_external_breakthrough_benchmark.py`, which freezes
   the C4-X engine hash before generating cases, accepts an evaluator seed, and
   emits reproducible benchmark receipts.~~
3. ~~Generate post-freeze held-out cases with randomized service names,
   topology-relevant facts, health/capacity/deployment values, temporal states,
   visual asset availability, and layout constraints.~~
4. ~~Compare BEAST against five reference baseline adapters: nearest-exemplar
   RAG, cached named templates, text-only rule engine, topology-only
   knowledge-graph reasoning, and model-generated multimodal stub.~~
5. ~~Score all systems on semantic correctness, honest uncertainty, visual
   presence, proof/artifact custody, proof-first execution, provider calls, and
   total benchmark score.~~
6. ~~Add `tests/test_c4x_external_breakthrough_benchmark.py` to verify
   post-freeze randomization, baseline comparison, receipt writing, and BEAST
   scoring.~~
7. ~~Remove circular benchmark scoring: expected semantic answers now come from
   an independent oracle derived from randomized scenario facts, rules,
   policies, topology metadata, and temporal flags before BEAST runs; joined
   verification/artifact custody can no longer auto-award semantic
   correctness.~~
8. ~~Add randomized topology shapes and held-out operational-domain labels to
   the post-freeze generator, with test coverage requiring diversity across
   generated runs.~~
9. ~~Expose a third-party verifier contract in the receipt schema so external
   systems can submit answer text, visual artifacts/digests, structured
   status/class/current-claim fields, and provider-call counts against the same
   independent oracle.~~
10. ~~Add `scripts/verify_c4x_external_breakthrough_submission.py`, a verifier
   that scores external submissions against saved `oracle_expected` cases
   without running BEAST or deriving expected answers from BEAST conclusions.~~
11. ~~Add existing in-repo BEAST subsystem competitors to the benchmark:
   `LocalSemanticCache`, `CapabilityCompositionPlane`, topology graph
   traversal, and the generation provider boundary adapter.~~
12. ~~Add an optional external RAG command lane:
   `--external-rag-command` sends one public scenario/facts JSON object per
   case on stdin and scores either returned answer fields or returned retrieval
   chunks against the same independent oracle.~~
13. ~~Add an Amazon RDS/Postgres RAG adapter command:
   `scripts/run_c4x_rds_rag_adapter.py` reads the benchmark request on stdin,
   queries RDS using env-provided DSN/table/SQL configuration, returns retrieved
   chunks or structured answer fields, and never serializes credentials into
   receipts.~~
14. ~~Send public, non-oracle facts/rules/policies to external competitors so
   real RAG/rule/KG/model systems are not blind to the held-out case evidence.~~
15. ~~Seed Aurora pgvector with a scoped generic C4-X operational-pattern corpus
   (`c4x:*` rows only), using deterministic local 64-d embeddings and no
   held-out service names or oracle labels.~~
16. ~~Harden the RDS adapter for the live Aurora lane: accept existing
   `.beast/vector.env` `BEAST_PGVECTOR_*` names, preserve port 5432, isolate AWS
   CLI IAM token generation with `PYTHONNOUSERSITE=1`, retrieve by operation
   terms instead of brittle full-question text, and synthesize bounded answers
   only from retrieved guidance plus public facts.~~
17. ~~Persist sanitized baseline-output summaries in the benchmark receipt so
   external RAG answers, retrieval hit counts, chunk metadata, and output
   digests are inspectable case-by-case.~~
18. Publish a public repository/container and invite third parties to replace
   the local reference baseline adapters with independently maintained RAG,
   template, rule-engine, KG, and model systems.

**Acceptance:** outsiders can run the frozen engine on held-out randomized
cases that were not named in the source tree, reproduce receipts/checksums, and
see where BEAST beats or loses to each baseline.

**Reference + in-repo benchmark receipt:** `scripts/run_c4x_external_breakthrough_benchmark.py`
produced `2026-08-03T-c4x-external-oracle-topology-domain-inrepo` using evaluator seed
`outsider-oracle-topology-domain-2026-08-03`. The run generated 12 held-out
cases across 3 families after engine freeze
`sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`, with
23 randomized service names, 4 randomized topology shapes, and 6 held-out
operational domains. BEAST scored 12/12 semantic correctness against the
independent oracle, 12/12 artifact custody, 12/12 honest uncertainty, 0 provider
calls, beat all 9 baselines, and produced breakthrough protocol
pass `true` with receipt digest
`sha256:3bfef0ebbf40485fa88e6e33fdc0be3001603b9a58b395c847e3006b91da969e`.
The strongest competitor is the existing `CapabilityCompositionPlane`: it
also scored 12/12 semantic correctness, but scored 0/12 artifact custody and no
proof-first cross-modal receipts, so BEAST still won total score 190 to 84.

**External RAG adapter smoke receipt:** `scripts/run_c4x_external_breakthrough_benchmark.py`
also produced `2026-08-03T-c4x-external-rag-smoke` with
`--external-rag-command` enabled. The smoke used a fake JSON retriever only to
prove adapter plumbing, generated 12 held-out cases, compared 10 baselines,
enabled `external_rag_enabled=true`, and passed with receipt digest
`sha256:aff38840472c54871f791df4b155dfac59ba52f7a79aa6ee5f7297094cae3001`.
Replace the smoke command with the real external RAG command to produce the
actual RAG competitor receipt. For Amazon RDS/Postgres, use:
`--external-rag-command "python3 scripts/run_c4x_rds_rag_adapter.py"` with
`BEAST_RDS_RAG_DSN`/`AMAZON_RDS_DSN`/`RDS_DSN`/`POSTGRES_DSN` plus either
`BEAST_RDS_RAG_SQL` or table/column env vars.

**Live Aurora pgvector RAG receipt:** `scripts/seed_c4x_pgvector_rag_corpus.py`
upserted five generic `c4x:*` corpus rows into `public.beast_memory_vectors`
using the existing `.beast/vector.env` Aurora IAM configuration, 64-d
pgvector embeddings, and receipt digest
`sha256:2ca28f0b6cd92a85bd01d69c19e40eb674379f0299379c9437fa8538e10c9037`.
Then `scripts/run_c4x_external_breakthrough_benchmark.py` produced
`pgvector-rag-real-run-005` with live
`--external-rag-command ".venv/bin/python scripts/run_c4x_rds_rag_adapter.py"`.
The run generated 12 held-out cases after freeze, 22 randomized service names,
4 randomized topology shapes, and 6 operational domains. BEAST scored 12/12
semantic correctness, 12/12 artifact custody, 12/12 proof-first, 12/12 visual
presence, and total 192. The live Aurora RDS RAG competitor improved to 12/12
semantic correctness and 12/12 honest uncertainty with zero provider calls, but
still scored 0/12 artifact custody, 0/12 proof-first, and 0/12 visual presence,
for total 84. BEAST still beat all 10 baselines. Receipt digest:
`sha256:0c4c1d9dcc6596c618fd80c7281a24c66bd734bdd818bb46e0c265b0a3e15ba2`.

**Honest external-proof boundary:** the benchmark now fixes the circular
semantic-oracle gap, randomizes topology/domain context, and compares against
four existing in-repo BEAST subsystems, five reference adapters, and an optional
external RAG command lane. It is still not a third-party breakthrough claim until
independent RAG, template, rule-engine, KG, and model competitors are run from a
public repository/container.

**Current visible replay:** `scripts/replay_c4x_shadow_crystal.py` produced a
restart-risk answer plus SVG from stored proof crystals with no production
interference and receipt digest
`sha256:69cd36d0cd7c3bcbe7de14ab749069eec42e9b0259f08a7ae5eb73e2620941e0`.
It also replayed a traffic-shift crystal with receipt digest
`sha256:e445c2824b23fc193e30f63c61e2bac3037df258c614fba3b36dba502d16cfea`.

## C10 — Three-front Truth Arena *(initial arena implemented)*

**Goal:** stop averaging unlike systems into one flattering number. The final
arena asks three separate questions: did the contender reach the correct
conclusion, how much compute did it need, and can it prove exactly how the
conclusion/artifacts were produced?

1. ~~Add `benchmarks/c4x_truth_arena.py`, a wrapper around the existing C4-X
   independent-oracle benchmark that emits three scoreboards instead of one
   soup score.~~
2. ~~Implement Scoreboard A, Truth: semantic correctness, uncertainty/refusal
   correctness, proof graph before output, text custody, visual custody,
   cross-modal entailment, and independent-oracle agreement.~~
3. ~~Implement Scoreboard B, Compute: raw measurement fields for TTFT,
   provider calls, tokens, cached tokens, KV bytes, store/restore latency,
   memory, network, and cost, with `compute_points_mixed_into_truth=false`.~~
4. ~~Implement the KV Reuse War boundary: publish the exact runtime-native KV
   cases required for public credit and explicitly refuse public credit for
   synthetic KV payloads.~~
5. ~~Implement Scoreboard C, Security/Custody: semantic-without-proof and
   semantic-without-artifact-custody are hard failures that cannot be averaged
   away by speed.~~
6. ~~Preserve honest visual accounting: missing/partial visual artifacts lose
   visual-custody truth points but do not become a critical custody failure when
   proof-first artifact custody remains valid.~~
7. ~~Add `tests/test_c4x_truth_arena.py` to enforce truth/compute/custody
   separation, RAG semantic success without custody credit, and KV sidecar
   metrics without truth-point leakage.~~
8. ~~Add `benchmarks/c4x_existing_evidence_sidecar.py` to mine existing Forge
   KV and provider-matrix evidence into Truth Arena sidecar metrics without
   rerunning engines/providers.~~
9. ~~Normalize real llama.cpp prompt-cache receipts as engine-local
   runtime-native prefix-cache evidence for exact repeated-prefix reuse, while
   preserving the restart-boundary miss and refusing portable raw-KV restore
   credit.~~
10. ~~Normalize Forge KV ML-KEM transport receipts as transport/hypothesis
    evidence only when the payload is `test_oracle` and no engine-native restore
    proof exists.~~
11. ~~Add provider evidence lanes from the old provider tournament, provider
    model-fitness snapshot, xAI/Omni live-provider report, and Gemini/HF
    teach-replay generation gauntlet.~~
12. ~~Add a dedicated RAG War front to the sidecar and Truth Arena, mining C4-X
    RAG benchmark receipts for local semantic cache, nearest-exemplar,
    cached-template, external smoke, corpus-poor Aurora pgvector, and seeded
    Aurora pgvector lanes.~~
13. ~~Preserve the RAG custody boundary: seeded pgvector can win semantics, but
    still receives 0 proof-first and 0 artifact-custody credit unless it
    supplies those receipts independently.~~
14. Add fresh live-provider arena lanes with frozen provider-economist route
    selection, raw request/response/usage capture, provider cache telemetry,
    and teach-to-crystal replay on the same C4-X challenge manifest.
15. Add full real runtime-native KV sidecars from vLLM/SGLang/LMCache and
    hostile KV identity cases beyond llama.cpp exact-prefix reuse.
16. Add separate-process Guardian custody sidecars and public CI artifact
    attestation before claiming third-party custody.

**Acceptance:** truth, compute, and custody can be inspected independently;
RAG/rule/KG/model systems can win semantic cases without inheriting BEAST proof
claims; KV speedups remain compute evidence only; critical custody failures are
hard gates.

**Verification:** `tests/test_c4x_truth_arena.py`,
`tests/test_c4x_external_breakthrough_benchmark.py`, and
`tests/test_deterministic_intelligence_gauntlet.py` pass together.

**Live Aurora Truth Arena receipt:** `benchmarks/c4x_truth_arena.py` produced
`truth-arena-live-rds-002` with live Aurora RDS RAG enabled. BEAST won the
truth arena with 189/192 points: 12/12 semantic, 12/12 proof-first, 12/12 text
custody, 11/12 visual custody, and 0 provider calls. Live Aurora RDS RAG and
the capability-composition engine both reached 96/192 by matching 12/12
semantic cases, but both failed the custody gate with
`semantic_without_proof_first` and `semantic_without_artifact_custody`. KV
runtime measurements were not supplied, and synthetic KV public credit remained
false. Receipt digest:
`sha256:1c798616109998a3cfa7e0862e2193be5b1038d8aad2682a6295ccaafc006d3a`.

**Forge KV + provider sidecar receipt:** `benchmarks/c4x_existing_evidence_sidecar.py`
normalized existing evidence into
`evidence/c4x-truth-arena-sidecars/existing-evidence-sidecar.json` with
3 KV lanes, 9 provider lanes, 15 RAG War lanes, and receipt digest
`sha256:6227d25984f945e50ee76e672f220ecc2c1b4fbc2c2732d6c9ffa2c40ad2ec65`.
The sidecar imports llama.cpp prompt-cache evidence as observed
engine-local prefix-cache reuse, imports the llama.cpp restart-boundary receipt
as a failed persistent-restore case, keeps Forge KV ML-KEM transport as
`claim_class=hypothesis` because the payload was `test_oracle`, and imports old
provider tournament/fitness/Omni/generation-gauntlet receipts as provider
evidence lanes rather than proof-first truth custody. It also imports C4-X RAG
receipts as RAG War lanes: reference nearest-exemplar RAG, local semantic
cache, cached templates, smoke external RAG, corpus-poor live Aurora pgvector,
and seeded live Aurora pgvector.

**Live Aurora + Forge/provider Truth Arena receipt:** the sidecar-backed run
`truth-arena-live-rds-forge-provider-002` passed with BEAST as truth winner:
189/192 truth points, 12/12 semantic, 12/12 proof-first, 12/12 text custody,
11/12 visual custody, and 0 provider calls. Live Aurora RDS RAG and the
capability-composition engine remained semantically strong but failed custody.
The compute front now shows runtime-native KV measurements supplied, one covered
KV case (`exact_repeated_prefix`), 15 missing KV hostile/transport/identity
cases, llama.cpp cold prompt time 13616.182 ms vs warm 226.166333 ms with 962
cached tokens reused, restart restore miss after process restart, and
synthetic-KV public credit `false`. The provider front shows 9 evidence lanes,
including provider tournament, five provider-fitness routes, NVIDIA NIM Omni
raw/full-BEAST lanes, and Gemini/HF teach-replay with 6 provider calls avoided.
Receipt digest:
`sha256:607bf3113353d6839b95e08c006ddfb01f35f80ca07b0a987060d386225d5306`.

**Full Truth Arena snapshot with RAG War:** `truth-arena-live-rds-forge-provider-rag-001`
adds the RAG War front to the full snapshot. BEAST remained truth winner and
passed custody. The RAG War showed 15 lanes and an explicit Aurora pgvector
learning curve: corpus-poor live pgvector scored 0/12 semantic with 0 retrieved
cases, while seeded live pgvector scored 12/12 semantic with 12 retrieved cases,
for seed gain 1.0. Seeded pgvector still scored 0 proof-first and 0 artifact
custody, preserving the central claim that semantic agreement is not proof
custody. The same snapshot retained 3 KV lanes, 9 provider lanes, runtime-native
KV exact-prefix coverage, 15 missing KV hostile/transport/identity cases, and
synthetic-KV public credit `false`. Receipt digest:
`sha256:a1e80850606cc0154c7e5d093e4f91908f0deee827e8ea89fcc0fdfb25a3bd64`.

## C11 — Frozen core and document/scientific-PDF frontier *(adjudication scaffold implemented)*

**Goal:** separate the frozen reasoning claim from the wider BEAST systems
claim, then start testing the next outside-world frontier: messy scientific
documents, scanned/OCR-hostile PDFs, tables, charts, footnotes, native vision,
and audit exports.

1. ~~Add `benchmarks/c4x_freeze_identities.py` to produce two immutable
   identity manifests: `c4x-core-v1.0` for the proof-composition semantic
   engine, and `beast-truth-stack-v1.0` for the surrounding observation,
   custody, reuse, transport, reproduction, and pressure-governance stack.~~
2. ~~Emit a seven-certificate contract instead of one mushy score:
   truth, observation, protocol integrity, custody, reuse, resilience, and
   replication.~~
3. ~~Add `benchmarks/c4x_document_truth_arena.py`, a real local PDF corpus
   audit runner using Poppler/Tesseract-era system tools rather than text
   fixtures.~~
4. ~~Run the document frontier over real local PDFs:
   `docs/external/obsidian-beast/Blurred Text Extraction Limitations.pdf`,
   `evidence/inference_economy_v0_9.pdf`, and
   `assets/release/commons-media/inference-economy-paper.pdf`.~~
5. ~~Extract Poppler text, page counts, image-object counts, first-page PNG
   renders, PDF digests, text digests, and OCR-hostility flags for every
   document.~~
6. ~~Export audit packets in JSONL, CSV, Zotero-style JSON, and a Gemini-vs-human
   protocol JSONL.~~
7. ~~Preserve the truth boundary: no document truth credit is awarded until
   native Gemini vision sidecars, blinded human annotations, merged-header table
   oracles, footnote/statistical-notation oracles, and chart-value annotations
   are supplied.~~
8. ~~Add `app/kernel/compute/document_vision_adjudication.py` so Gemini,
   blinded-human, and frozen-oracle sidecars are compared independently of
   BEAST answers.~~
9. ~~Require source-digest custody, native-vision independence, human blinding,
   field-level Gemini/human/oracle agreement, and separate certificate gates for
   merged headers, footnotes/statistical notation, chart values, and no
   text-answer-derived visual generation.~~
10. ~~Export human annotation packets, oracle templates, adjudication JSONL, and
   disagreement CSVs alongside Zotero/CSV/JSONL corpus packets.~~
11. ~~Add `scripts/run_c4x_gemini_document_vision_sidecar.py`, a native Gemini
   vision sidecar runner for rendered PDF pages. It defaults to dry-run rows
   that cannot earn truth credit; `--live` requires an approval receipt and
   emits model, source digest, request digest, raw response digest, and provider
   call count.~~
12. ~~Add native Gemini vision execution evidence for rendered PDF pages, with raw request
   digest, raw response digest, model id, latency, usage, and no access to human
   annotations.~~
13. Add blinded human inspection packets for the same rendered pages and compare
   Gemini vs human on tables, charts, merged headers, footnotes, statistical
   notation, and uncertainty/refusal behavior.
14. Add chart/table oracle annotations for real scientific PDFs and promote only
    verified extraction capabilities into crystals.

**Acceptance:** the core and stack identities are frozen separately; real local
PDF corpus packets are reproducible; export formats are available for Zotero,
CSV, and JSONL review; document truth claims stay pending until source-bound
Gemini vision, blinded human, and frozen oracle annotations independently agree.

**Verification:** `tests/test_c4x_document_and_freeze.py`,
`tests/test_c4x_truth_arena.py`,
`tests/test_c4x_external_breakthrough_benchmark.py`, and
`tests/test_deterministic_intelligence_gauntlet.py` pass together
(`31/31` focused tests on 2026-08-03). The document tests include both a
positive independent-sidecar proof and a refusal for a Gemini sidecar derived
from a text answer.

**Freeze identity receipt:** `benchmarks/c4x_freeze_identities.py` produced
`c4x-freeze-v1-2026-08-03` with `c4x-core-v1.0` digest
`sha256:60a83595d3e79f130822a3a8f6343bc484a50660b20f20fa81a84016789352f9`,
`beast-truth-stack-v1.0` digest
`sha256:25827a2c90455635b1f50be9bc15e1cf52dc967dbe975279147d66e87393fc81`,
and receipt digest
`sha256:1ea3c9cb337d2a3ed254436a4fec5c702be3ff7c08481d6fc4d2af1c28eff78f`.

**Document frontier receipt:** `benchmarks/c4x_document_truth_arena.py` produced
`document-frontier-real-pdfs-001` over three real PDFs. It rendered 3 first-page
PNGs, extracted text/page/image metadata, exported
`document_corpus.jsonl`, `document_corpus.csv`, `zotero_items.json`, and
`gemini_vs_human_protocol.jsonl`, and deliberately awarded
`truth_credit_awarded=false` until Gemini/human/table/chart oracle sidecars are
provided. Receipt digest:
`sha256:a5bc238b448f3b47790a2733f2debcf71aa11093f227237119e875396601e3ce`.

**Document adjudication receipt:** `benchmarks/c4x_document_truth_arena.py`
produced `document-frontier-adjudication-001` over the same three real PDFs with
the new three-way adjudication spine. It rendered 3 first-page PNGs and exported
`human_annotation_packet.jsonl`, `oracle_packet_template.jsonl`,
`document_vision_adjudication.jsonl`, and
`document_vision_disagreements.csv`. All final document-truth gates correctly
remain `false` until real Gemini/human/oracle sidecars are supplied. Receipt
digest:
`sha256:51acfc9f4ea9ed4669726e46b88d625b133e16bf8ce44ca8067e88f9c51eb5dd`.

**Gemini dry-run refusal receipt:** `scripts/run_c4x_gemini_document_vision_sidecar.py`
produced a non-credit planning sidecar with `eligible_rows=0` and receipt
digest `sha256:a050bceffdc209e815d6d8e57d237526b498a7502f9358a2e33b401a61928760`.
Re-feeding that sidecar through the document arena as
`document-frontier-gemini-dryrun-refusal-001` correctly kept
`truth_credit_awarded=false`. Receipt digest:
`sha256:296a23ca68d3da643b0356ef06f2ef12da2787fc7e6cb3e73bd78a5a27f4f652`.

**Live Gemini-only receipt:** the Gemini sidecar runner auto-discovered
`gemini-3.6-flash` from the Gemini models endpoint and produced 3 eligible
native-vision rows over the rendered first-page PDF images. Re-feeding those
rows through the document arena as `document-frontier-live-gemini-only-001`
correctly moved only `native_gemini_vision_custody=true` and
`no_text_answer_generation=true`; final `truth_credit_awarded` remained `false`
because blinded human and frozen oracle lanes are still absent. Sidecar receipt
digest: `sha256:cd0c741cb10d9b57d53e5201175ea9d987ebeaa7511a82c1d61e6f7efe5a798e`.
Arena receipt digest:
`sha256:d711f1460bb3d9e3190a07c341ae5c1a936a796fba638a897833cc3936b3af87`.

## Measurement protocol *(complete)*

~~Compare raw local model, ordinary RAG plus model, BEAST cache, Meaning
Crystals, and Meaning Crystals plus bounded lexicalization. Measure resolution
accuracy, false reuse, unsupported assumptions, latency, CPU/memory time,
tokens, provider calls, and cache invalidation correctness. Do not claim
general reasoning or model-weight learning from deterministic replay results.~~

**Verification:** `tests/test_synthesis_measurement.py` covers all five
required routes, measurement fields, provider-call accounting, false-reuse
failure, unsupported-assumption failure, and cache-invalidation correctness.

## D0 — Provider-reduction observatory *(in progress)*

**Goal:** make the provider-displacement curve visible from one production
surface instead of leaving it split across Sensorium packets, Grand Closure
receipts, Forge KV proofs, Commons Spaces, synthesis receipts, and ad hoc tests.

1. ~~Add a production `DisplacementObservatory` that summarizes runtime
   `ComputePlane` counters and Control Evidence Graph receipts into one
   provider-use scorecard.~~
2. ~~Expose the scorecard from `ComputePlane` and `/edgek/compute/provider-reduction`.~~
3. ~~Add file-evidence ingestion for historical proof families:~~
   - ~~Sensorium learned physical crystals.~~
   - ~~Forge KV prompt-cache receipts.~~
   - ~~Grand Closure G7/G8/G9 bundles.~~
   - ~~High-velocity fabric residual-routing receipts.~~
   - ~~Commons Space reduction receipts.~~
4. ~~Split observed reductions from estimates:~~
   - ~~actual provider calls used;~~
   - ~~counterfactual provider calls avoided;~~
   - ~~prompt tokens avoided by measured KV/cache behavior;~~
   - ~~estimated fused-crystal tokens;~~
   - ~~route-selection-only claims that cannot count as execution savings.~~
5. ~~Add trend buckets over time so the operator can see whether provider calls
   are falling as semantic, physical, and visual artifacts promote.~~
6. Add refusal/accountability rows for false reuse, stale reuse, demotion, and
   provider fallback.

**Acceptance:** one endpoint reports provider calls used, provider calls
avoided, semantic replays, physical crystal replays, scene capsule
compositions, image-region local fills, image-provider fallbacks, measured KV
token savings, unsupported/estimated claims, and a digest-bound scorecard.

**Progress:** `/edgek/compute/reduction-evidence/discover` now scans bounded
repo-local JSON evidence roots, detects Forge KV, Grand Closure/G9, Commons
Space, and Sensorium receipts, and idempotently ingests normalized projections
without copying raw payloads into the scorecard evidence graph.  The
provider-reduction scorecard now includes digest-bound daily trend buckets for
timestamped semantic replay, visual residual/promotion/reuse, provider
fallback, production displacement, economics, and normalized reduction evidence.

## D1 — Image-generation displacement loop *(implemented)*

**Goal:** make image generation follow the same provider-less-over-time arc as
semantic and physical compute.

1. ~~Wire `SupervisedCPUVisualResidualWorker` into `ComputePlane` and expose
   `/edgek/compute/visual-residual`.~~
2. ~~Accept only region masks bound to a `SceneCapsule`; never regenerate whole
   scenes when only a region is unresolved.~~
3. ~~Record visual residual receipts in the evidence graph with:~~
   - ~~scene digest;~~
   - ~~scene capsule digest;~~
   - ~~mask digest;~~
   - ~~engine/model digest;~~
   - ~~seed;~~
   - ~~output digest;~~
   - ~~no-network witness;~~
   - ~~provider-call witness.~~
4. ~~Add an explicit image-provider fallback boundary for unresolved visual
   regions, with policy and operator approval hooks, but no ambient bypass.~~
5. ~~Verify provider/local/generated pixels at the region boundary before
   admitting them as visual asset candidates.~~
6. ~~Promote repeated verified region outputs into the signed asset manifest.~~
7. ~~Prefer promoted visual assets and deterministic scene composition before
   local residual generation, and prefer local residual generation before image
   provider fallback.~~
8. ~~Add bounded visual prompt-intent receipts so repeated outputs can only
   promote when the generated region is mechanically compatible with declared
   color/object intent, such as a green status light.~~
9. ~~Add deterministic perceptual feature receipts so structurally weak visual
   regions, such as a flat green swatch claiming to be a status light, cannot
   promote even when byte quality and color intent pass.~~
10. ~~Add visual feature embeddings and equivalence receipts so byte-different
    but verified-equivalent region outputs can still promote into reusable
    render-only assets.~~
11. ~~Add a local text/image generation gauntlet runner that writes durable JSON
    and Markdown receipts, then proves stored semantic crystals and promoted
    visual assets reduce fresh work on later runs.~~
12. ~~Add a capability learning ledger and `/edgek/compute/capability-learning`
    report so promoted, reused, refused, revoked, demoted, and gauntlet-run
    events are visible as one durable learning inventory.~~
13. ~~Add Provider Adapter Boundary v1 for text/image generation gauntlets:
    deterministic stub providers remain the default, live providers require
    env readiness plus explicit approval, and adapter receipts are bound into
    gauntlet evidence before any downstream promotion.~~
14. ~~Wire concrete live provider adapters behind the same boundary: Gemini
    `generateContent` for chat/text and Hugging Face text-to-image for visual
    generation, with `gemini`/`hf` aliases, alternate secret readiness
    (`GEMINI_API_KEY|GOOGLE_API_KEY`, `HF_TOKEN|HUGGINGFACE_API_KEY`),
    operator approval requirements, mocked boundary tests, and no ambient
    live execution.~~
15. ~~Seal every provider-bound generation request into a digest-only
    Generation Crystal IR capsule before receipt admission, binding execution
    mode, render/model/reuse/proof contracts, Commons capability snapshot,
    Socket Guardian registry binding, output digest, approval digest, and
    prompt digest without storing raw prompts.~~
16. ~~Expose Evidence-Bounded Semantic Resolution in gauntlet receipts so text
    cases report provable/resolvable/open semantic-space class, explicit
    meaning-resolution state, candidate count, evidence binding count, and
    matrix-free replay counts.~~
17. ~~Add actual Socket Guardian generation-capsule fd handoff: a guardian
    daemon operation receives sealed Generation Crystal memfds through
    `SCM_RIGHTS`, verifies seals, capsule digest, authority/audience/capability
    and appraisal bindings, returns a guardian handoff receipt, and projects
    attempted/verified handoff counts into gauntlet evidence.~~

**Acceptance:** repeated image-region requests show a transition from provider
fallback or local residual generation to deterministic asset composition, with
provider-image calls trending down, near-equivalent verified variations
promoting safely, and false/stale/intent-mismatched/structure-weak visual reuse
refused.

**Progress:** local region generation is content-stable, scene-capsule-bound,
no-network verified, and available at `/edgek/compute/visual-residual`.
Provider fallback is now an explicit separate boundary at
`/edgek/compute/visual-residual/provider-fallback`; it requires a configured
fallback callback, `allow_provider_fallback=true`, and an operator approval
receipt.  Repeated matching verified region outputs now promote into
render-only visual assets, are visible through `/edgek/compute/visual-assets`,
and are preferred before rerunning local residual generation or attempting
provider fallback.  Promotion now requires a mechanical visual-region quality
gate: correct byte boundary, opacity coverage, non-blankness, channel
variation, and digest binding.  It also requires a bounded intent gate that
extracts privacy-safer color/object hints from the prompt, binds the intent
digest into sealed visual requests, records intent receipts on candidate
promotion, and refuses otherwise valid pixels that miss the declared visual
intent.  The deeper perceptual gate records deterministic shape/texture
features — center emphasis, edge density, luma variation, centroid offset, and
symmetry — so a provider can no longer promote a flat color patch simply
because it matches the requested color.  The equivalence layer projects
verified regions into quantized visual feature embeddings and records
equivalence receipts, allowing repeated near-identical provider outputs to
promote even when raw bytes differ while still refusing embedding-distance
drift.  Low-quality/transparent/flat,
intent-mismatched, or structurally weak regions produce
`visual_asset_candidate_refused` evidence instead of entering the promotion
counter.  The provider-reduction scorecard reports image-region local fills,
visual provider fallback calls, promoted visual assets, promoted asset reuses,
and visual asset refusals without overstating provider-call avoidance until
paired fallback comparisons exist.

Capability learning is now recorded in an append-only local ledger at
`capability_learning.jsonl` under the compute-plane state root.  Semantic
crystal promotion/replay, visual asset promotion/reuse/refusal, semantic
revocation, visual demotion, and gauntlet completion events are projected into
bounded ledger events.  `/edgek/compute/capability-learning` reports learned
capabilities, lifecycle states, fresh-work units, reuse hits, provider calls
used, and provider calls avoided without exposing raw prompts or pixels.

Provider adapters are now visible at `/edgek/compute/provider-adapters`.
The gauntlet uses this boundary in `stub` mode by default and records provider
adapter receipt digests.  `live` mode now has concrete adapters for Gemini
chat/text and Hugging Face image generation, but does not execute unless the
provider supports the requested modality, required environment secrets are
present, and an approval receipt is supplied.  Governed one-off execution is
available at `/edgek/compute/provider-adapters/execute`; live chat uses
`provider=gemini`, `modality=text`, and live image generation uses
`provider=hf` or `provider=huggingface`, `modality=image`.  HF image bytes can
also be normalized into exact RGBA scene-region bytes for
`/edgek/compute/visual-residual/provider-fallback`.

Generation provider receipts now include a `generation_synthesis_capsule`
metadata object produced by `app/kernel/compute/generation_synthesis_plane.py`.
On Linux this seals the canonical Generation Crystal IR into a memfd-backed
typed capsule and verifies it before returning the receipt.  The capsule binds
to the Commons capability vocabulary and to the authoritative
`.byron/services.yaml` Socket Guardian services digest, but this is still a
receipt-level binding: it proves the provider boundary is ready for
`memfd+SCM_RIGHTS` handoff and Commons scheduling, not that the live Socket
Guardian daemon or a distributed Commons scheduler has already performed the
descriptor transfer.

The gauntlet also reports Evidence-Bounded Semantic Resolution (EBSR).  Text
cases now distinguish exact/provable semantic-crystal replay from bounded
schema/world adjudication and open/unsupported cases, instead of collapsing
everything into a vague "provider used or not" signal.

`SocketGuardianServer` now also has a generation-capsule verification operation
for this boundary.  When `BEAST_GENERATION_SOCKET_GUARDIAN` points at a running
guardian socket, sealed Generation Crystal capsules are sent to the daemon via
`SCM_RIGHTS`; the daemon validates the received fd, memfd seals, capsule digest,
capsule envelope, authority/audience/capability/appraisal bindings, and returns
a digest-bound handoff receipt.  This still does not claim distributed Commons
scheduling; it does retire the weaker claim that generation capsules are merely
"eligible" for fd transport.

**Gauntlet receipt:** `scripts/run_generation_gauntlets.py` writes
`evidence/generation-gauntlet/*.json` and `.md` receipts.  The provider-boundary
gauntlet pair `2026-08-03T000000-provider-boundary-a` →
`2026-08-03T000000-provider-boundary-b` promoted 3 semantic crystals and 2
visual assets on the teach pass, then reused all 3 text crystals and both
visual assets on the replay pass.  Image provider-boundary calls dropped from
4 to 0, fresh work dropped to 0, reuse hits reached 5, provider calls avoided
reached 6, and the teach pass recorded 4 adapter receipt digests under the
deterministic stub boundary.

The named-provider stub pair `2026-08-03T000000-gemini-hf-stub-a` →
`2026-08-03T000000-gemini-hf-stub-b` verified the new Gemini/HF routing
without network spend: the teach pass recorded 3 chat boundary calls and 4
image boundary calls with 7 provider adapter receipts; the replay pass reused
all stored semantic crystals and visual assets, with chat calls dropping to 0,
image calls dropping to 0, and no provider adapter receipts needed.

The live-provider sequence `2026-08-03T000000-live-gemini-hf-c` →
`2026-08-03T000000-live-gemini-hf-d` →
`2026-08-03T000000-live-gemini-hf-e` verified the same curve against real
providers using the local `.beast/provider_secrets.env` secrets without
printing secret values.  The first live combined pass used 3 Gemini chat calls,
promoted/replayed all 3 text crystals, and promoted one HF visual asset while
one HF image request hit a transient TLS handshake timeout.  The second pass
reused all text crystals, completed the remaining HF visual asset, and passed
with 2 HF image calls.  The third pass reused all 3 text crystals and both
visual assets, with Gemini calls dropping to 0, Hugging Face image calls
dropping to 0, and no live adapter receipts needed.  HF image generation used
Hugging Face Routing via `fal-ai` and `krea/Krea-2-Turbo`, then performed
local receipt-marked intent-color/status-light region normalization on the tiny
RGBA scene regions before visual asset admission.

The next-level stub pair `2026-08-03T000000-next-level-stub-a` →
`2026-08-03T000000-next-level-stub-b` verifies the outstanding note elements
without cloud spend.  The teach pass recorded 7 provider-boundary receipts
(3 text teach calls through the Gemini-named stub lane plus 4 image teach calls
through the HF-named stub lane), 7 sealed memfd capsules, 7 verified capsules,
2 Commons capability digests, 1 Socket Guardian binding digest, and 0 raw
prompts stored.  The replay pass reused all stored semantic crystals and visual
assets, required 0 provider receipts/capsules, and reported EBSR as 3/3
provable, resolved, matrix-free text cases.

The next-level live pair `2026-08-03T000000-next-level-live-a` →
`2026-08-03T000000-next-level-live-b` verified the same capsule/EBSR path
against real providers using local secrets without printing secret values.  The
teach pass used 3 Gemini text calls and 4 Hugging Face image calls, recorded
7 `escalate` provider receipts, sealed and verified all 7 Generation Crystal
IR capsules with memfd, and stored no raw prompts.  The replay pass reused all
3 semantic crystals and both promoted visual assets, dropping Gemini calls to
0, HF image calls to 0, provider receipts to 0, and reporting EBSR as 3/3
provable, resolved, matrix-free text cases.

The guardian-handoff pairs `2026-08-03T000000-guardian-handoff-stub-a` →
`2026-08-03T000000-guardian-handoff-stub-b` and
`2026-08-03T000000-guardian-handoff-live-a` →
`2026-08-03T000000-guardian-handoff-live-b` verified actual Socket Guardian
descriptor transport.  The live teach pass used 3 Gemini text calls and
4 Hugging Face image calls, recorded 7 `escalate` provider receipts, sealed
and verified all 7 Generation Crystal capsules, and had the guardian verify
all 7 received fds through `SCM_RIGHTS` with 0 raw prompts stored.  The replay
pass dropped provider calls, provider receipts, capsules, and guardian handoffs
to 0 because the stored semantic crystals and visual assets were sufficient.

The promoted visual assets from the live guardian-handoff gauntlet are now
exported as real files under `artifacts/generation-visual-assets/`: exact PNGs,
scaled preview PNGs, raw RGBA bytes, `manifest.json`, and a README.  These are
the tiny scene-region assets admitted by the gauntlet, not full-scene image
renders; the current exported previews are the green and blue status-light
regions whose promoted asset digests backed the replay pass.

To run the real-provider gauntlet after local secrets are configured:

```bash
GEMINI_API_KEY=... HF_TOKEN=... \
python3 scripts/run_generation_gauntlets.py \
  --provider-mode live \
  --chat-provider gemini \
  --provider hf \
  --approval approval:operator:live-generation-gauntlet
```

## D2 — Evidence economy unification *(implemented)*

**Goal:** make Sensorium, Forge KV, Grand Closure, Commons, and Synthesis
receipts speak the same accounting language without overstating claims.

1. ~~Normalize all reduction receipts into `observed`, `estimated`,
   `route_selection_only`, or `hypothesis` claim classes.~~
2. ~~Feed Forge KV measured prompt-cache savings into the observatory only when
   the engine-specific proof allows a performance claim, while separating
   local prompt-cache savings from portable raw-KV or cross-node claims.~~
3. ~~Feed Grand Closure economics as lifecycle/economics evidence, not provider
   execution savings unless paired execution evidence exists.~~
4. ~~Feed Commons Spaces only after local reproduction/promotion.~~
5. ~~Add G9 bundle-health reporting so missing gates, such as the current
   missing `G3`, stay visible instead of being mentally rounded up.~~
6. ~~Project Sensorium disk-pressure cleanup evidence into capability learning
   as resource-governance learning, not as automatic destructive authority.~~
7. ~~Project Forge KV prompt-cache and restart-boundary proofs into capability
   learning as `forge_kv_node` capabilities, distinguishing observed
   engine-local reuse from cache-staleness boundaries.~~
8. ~~Add Forge KV ML-KEM transport receipts that bind a checksum-verified KV
   network manifest to a Commons ML-KEM gauntlet receipt, reject secret/raw
   payload serialization, and record transport learning without counting token
   savings or provider-call avoidance.~~

**Progress:** `ComputePlane.ingest_reduction_evidence()` and
`/edgek/compute/reduction-evidence` now admit bounded projections of Forge KV,
Grand Closure/G9, Commons Space, Sensorium, and future reduction receipts.
`/edgek/compute/reduction-evidence/discover` imports recognized repo-local JSON
receipts from historical evidence folders.  Raw prompt/private payload fields
are refused.  Forge KV token savings count only when a native context restore
verifier proves prompt prefill displacement.  Grand Closure/G9 contributes
lifecycle and bundle-health evidence, including missing gates, but does not
count provider execution savings.  Commons Space receipts count only after seal
verification plus local reproduction or promotion.  Sensorium disk-pressure
proofs are recognized as `sensorium_physical_crystal` learning events:
replay-eligible disk cleanup becomes resource-governance knowledge, but stays
`promotion_blocked_destructive` until explicit production isolation and
operator approval gates allow it.  Forge KV prompt-cache receipts are recognized
as `forge_kv_node` learning events: local llama.cpp prompt-cache proofs count
observed prompt-eval/token work avoided, while restart-boundary receipts teach
that the cache is stale/not durable after process restart unless native restore
or portable KV proof exists.  The provider-reduction scorecard now reports
normalized evidence events and G9 bundle health alongside observed channels.
Forge KV ML-KEM transport receipts are now recognized as `forge_kv_node`
learning events with lifecycle `transport_verified` only when a live
ML-KEM-confirmed Commons receipt is paired with an engine-native,
checksum-bound KV payload acknowledgement.  CI/test-oracle payloads exercise
the route but remain `hypothesis`, with 0 tokens avoided and 0 provider calls
avoided.

**Live integration receipt:** a `codex-integration` discovery run ingested
`docs/evidence/sensorium-disk-cleanup-candidate-2026-07-15.json`,
`evidence/forge_kv/llamacpp_prompt_cache_20260720T115125Z.json`, and
`evidence/forge_kv/llamacpp_restart_boundary_20260720T131312Z.json` into the
default compute-plane state root `/home/byron/.local/state/beast/compute_plane`.
The scorecard now records 3 normalized evidence events, 2886 observed
engine-local prompt tokens avoided, 0 provider calls avoided from these
particular proofs, and capability-learning states `observed_engine_local`,
`restart_boundary_observed`, and `promotion_blocked_destructive`.

**Transport receipt:** `scripts/run_forge_kv_ml_kem_transport_gauntlet.py`
binds a local KV network transfer manifest to
`evidence/commons-ml-kem/latest.json` and writes
`evidence/forge-kv-ml-kem-transport/*.json` and `.md` receipts.  The
`2026-08-03T000000-forge-kv-mlkem-ci-a` run used the live Commons ML-KEM
receipt but a CI test-oracle payload, so it deliberately produced
`claim_class=hypothesis`, `transport_verified=false`, 0 provider calls avoided,
and 0 observed tokens avoided.  Supplying `--engine-native-payload <path>` is
required before the same route can earn `transport_verified`.

## D3 — Commons ML-KEM key-agreement proof *(implemented)*

**Goal:** give the live Commons swarm a post-quantum key-agreement proof path
that is small, signed, gauntlet-tested, and does not leak session material into
evidence.

1. ~~Add `app/kernel/commons/ml_kem.py` with ML-KEM-768 key load/create,
   public-key document, encapsulation/decapsulation helpers, and transcript
   HMAC confirmation.~~
2. ~~Add `GET /v1/ml-kem/key` and `POST /v1/ml-kem/challenge` to the remote
   Commons node without granting execution authority.~~
3. ~~Keep `/health` independent from ML-KEM startup by lazy-loading the
   node KEM key on the first ML-KEM endpoint request.~~
4. ~~Prebuild container `liboqs` into `/opt/oqs` with
   `OQS_MINIMAL_BUILD="KEM_ml_kem_768"` and pin `liboqs-python==0.16.0` for
   the Commons lab image.~~
5. ~~Add `scripts/run_commons_ml_kem_gauntlet.py` to test all three live
   Commons nodes and write digest-bound JSON/Markdown receipts.~~
6. ~~Run the live gauntlet against ports `8111`, `8112`, and `8113`.~~

**Receipt:** `evidence/commons-ml-kem/2026-08-03T000000-commons-ml-kem-live-a.json`
passed with 3/3 nodes confirmed, 6 directed pairwise transcript bindings, 1088
byte ciphertexts, 32 byte shared secrets, `secret_exported=false`, and receipt
digest `sha256:c653b6c12fc77a19a57c8d3d46755e3435cd203eff6c0f5dc765de6a13b51507`.

**Boundary:** this is key-agreement proof and transcript binding, not yet a
full encrypted Commons transport/session layer.  The next upgrade is to derive
session keys from the ML-KEM shared secret and bind them to signed request
authentication or a hybrid classical+PQC channel.

## C12 — Physical truth certificate spine *(implemented as hard gate, 12/12 live certificate closed)*

**Goal:** stop the final BEAST claim from being awarded by internal self-report
or by averaging unlike evidence.  The final physical-truth certificate now has
one hard gate per dragon limb:

1. ~~Add `app/kernel/compute/c4x_physical_truth_certificate.py` with mandatory
   gates for C4-X truth, Sensorium observation, BPF witness, Crystal Bus
   protocol integrity, memfd custody, Socket Guardian custody, reuse,
   ML-KEM/ML-DSA transport, Commons replication, route resilience, PSI
   governance, and XDP scope.~~
2. ~~Add `scripts/run_c4x_physical_truth_certificate.py` to write JSON/Markdown
   certificate receipts and a sidecar template for independent evidence.~~
3. ~~Make internal `provider_calls_used=0` insufficient for zero-provider-call
   truth: the BPF gate requires cgroup-bound outbound connect, DNS, provider
   socket, child-process, ring-loss, raw-payload, and live-provider-comparator
   observations.~~
4. ~~Add tests proving empty/missing receipts refuse all public credit, complete
   independent sidecars unlock credit, and self-reported provider counts do not
   satisfy the BPF witness.~~
5. ~~Harden the local Crystal Bus transport with optional session IDs, HMAC
   binding, message expiry, payload digests, durable high-water marks, and a
   `CrystalBusAuthorizer` that checks UID, ProcessLease, workspace, cgroup,
   capability lease, ARDA appraisal, policy generation, descriptor presence,
   and capability replay before authority-changing frames are accepted.~~

**Receipt:** `physical-truth-pending-001` wrote
`evidence/c4x-physical-truth-certificate/physical-truth-pending-001/physical_truth_certificate.json`
with all 12 gates false and public credit refused, because live sidecar
receipts have not yet been attached. Receipt digest:
`sha256:d5947a913cc53d77d448557fed836aa981486154440d59fd35aacad0d6ca4869`.

**Verification:** `tests/test_c4x_physical_truth_certificate.py` and
`tests/test_crystal_bus_capsule.py` pass together (`13/13`). A broader focused
run also showed two environment-only blockers in this sandbox: AF_UNIX Guardian
bind was denied with `EPERM`, and `PIL` is not installed for one HF mock image
test.

**Boundary:** this is the final certificate spine, not a claim that privileged
BPF/XDP/PSI/Commons three-node attack runs have already passed. Those live
receipts must be generated and attached as sidecars before the final physical
truth claim can turn green.

**Live infrastructure harvest:** after the Commons containers were confirmed up
on ports `8111`, `8112`, and `8113`, `scripts/harvest_c4x_physical_truth_sidecar.py`
mapped available evidence into
`evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json`
without overclaiming.  The harvested certificate
`physical-truth-harvested-live-infra-002` correctly sets
`c4x_truth=true` from the ultimate deterministic gauntlet while leaving the
physical gates red.  The BPF preflight records `bpffs_present=true`,
`tracefs_present=true`, `btf_present=true`, `bpftool_present=true`, and
`load_ready=false` for this process; `bpftool prog show` and
`sudo -n bpftool prog show` could not enumerate loaded programs without
additional privilege.  The Commons ML-KEM live receipt
`2026-08-03T000000-commons-ml-kem-live-a` remains valid key-agreement evidence
with 3/3 nodes confirmed, but it does not unlock `pq_transport` or
`commons_replication` because those gates require encrypted artifact transport,
ML-DSA/authenticity, replay/tamper attacks, clean rebuild, independent seed,
and reproduction.  Harvest receipt:
`sha256:5b55f822b42c9235ffdfb4a08d53e0855b07bbec21a49f30e37bac0a1d4b4de4`.
Certificate receipt:
`sha256:5fb16f0ae5126b328975e23574ff498cfd4448692e3cc561a8eb3a32965eee91`.

**Interactive sudo harvester:** `scripts/run_c4x_sudo_physical_harvest.py`
is now the operator path for privileged evidence collection.  It prompts with
`sudo -v` in the operator terminal, then uses `sudo -n` for `bpftool`
inventory so no password is written to command logs, shell history, or
receipts.  It writes a live BPF/XDP receipt, runs the local memfd/Socket
Guardian custody attack suite, merges the harvested sidecar, and rebuilds the
physical-truth certificate.

Run:

```bash
.venv/bin/python scripts/run_c4x_sudo_physical_harvest.py
```

The managed Codex sandbox blocks AF_UNIX `SOCK_SEQPACKET` Guardian bind, so the
local smoke run `physical-truth-local-script-smoke-003` proves the launcher
fails closed there while still turning `memfd_custody=true` through kernel seal,
post-seal digest, mutation rejection, and wrong-FD rejection checks.  Smoke
certificate receipt:
`sha256:9d701c651aceb677472acc219ef0c45d68b7cd357a3960d1a556e28ae0cae52a`.

Current expected behavior: on Byron's real terminal, the same launcher should
prompt for sudo, harvest live `bpftool` program/map/net state, attach existing
AF_XDP proof receipts, and attempt the real Guardian process custody attacks.
The final certificate still refuses public credit for BPF/XDP/Guardian unless
the exact hard-gate attack evidence is present.

**Guardian producer-death upgrade:** the sudo harvester now includes a
separate producer process that creates a sealed capsule, performs a real
`SCM_RIGHTS` handoff to the Socket Guardian, exits, and then verifies from the
parent that the signed Guardian receipt remains valid after the producer PID is
gone.  This is the missing `producer_death_after_handoff_verified` field for
the `guardian_custody` gate.  The Codex managed sandbox cannot execute this
because AF_UNIX `SOCK_SEQPACKET` bind is denied, but Byron's terminal run
already proved the other Guardian checks execute on the host.

**ARDA/Integritas BPF authority import:** the sudo harvester now also checks
`/home/byron/Integritas-Mechanicus/arda_os/bin/arda status --json` by default
and records ARDA's authoritative substrate state as a separate
`arda_status_harvest.json` receipt.  Fields such as
`bpf_authoritative=true`, `attach_verified=true`, `is_authoritative=true`,
`is_simulation=false`, pinned required maps, and the Valinor kernel now feed
`bpf_authority_present=true` in the harvest summary.  This fixes the earlier
blind spot where ARDA could prove BPF was live while the BEAST physical
certificate still appeared to say "BPF absent."  The hard `bpf_witness` gate
remains stricter: it requires a closed BEAST observation episode proving zero
provider sockets/DNS/connects/child processes plus live-provider comparator
network observation.

**Sensorium + BPF zero-provider closure:** added
`scripts/run_c4x_sensorium_bpf_zero_provider_episode.py`.  It runs a closed
Sensorium episode over the deterministic C4-X receipt, records a durable
Sensorium journal, instruments the process for DNS/connect/provider socket and
child-process attempts, and then runs a positive provider-network comparator so
the witness is not a silent stub.  The mission itself opened zero provider
sockets, zero DNS calls, zero connects, and zero child processes.  Smoke run
`sensorium-bpf-zero-provider-smoke-002` moved both `sensorium_observation` and
`bpf_witness` green in the certificate.  Receipt:
`sha256:ccba2ac07f0c0b031baee7f607a68062f7b4bbd829f9aef841756272f9fbdec7`.

Run:

```bash
.venv/bin/python scripts/run_c4x_sensorium_bpf_zero_provider_episode.py
```

**Protocol + reuse + route hostile gauntlet:** added
`scripts/run_c4x_protocol_reuse_route_gauntlet.py`.  This is a local,
non-sudo gauntlet for the certificate layers that can be proven without live
external infrastructure:

1. Crystal Bus protocol integrity: real AF_UNIX `SOCK_SEQPACKET`,
   `SO_PEERCRED`, HMAC/session binding, SCM_RIGHTS sealed memfd handoff,
   sequence replay rejection, durable high-water replay rejection,
   sender-death-after-handoff, and capability revocation replay rejection.
2. Reuse hostile matrix: exact prefix hit accepted, identity mismatch refused,
   corrupt payload rejected, restart persistence credit only when demonstrated,
   cross-engine import refused without physical success, and no semantic-truth
   points awarded merely for KV speed.
3. Route resilience: hidden deterministic failure schedule, attestation failure
   suppression, timeout penalty, 429 suppression, decay recovery, oscillation
   bound, decision receipts, and comparison against a naive no-damping router.

Smoke run `physical-truth-protocol-reuse-route-smoke-005` moved
`protocol_integrity`, `reuse`, and `route_resilience` green.

**Live Commons ML-KEM container-helper proof:** the host venv did not have
`liboqs-python`, but the live Commons containers did.  I added
`--oqs-helper-container` to `scripts/run_commons_ml_kem_gauntlet.py` so the
shared secret is created, used, and destroyed inside the Commons container
process.  The host receipt receives only public ciphertext digests,
confirmation digests, and pass/fail status.  Run
`physical-truth-commons-mlkem-live-container-helper-001` confirmed all three
Commons nodes with ML-KEM-768.  Receipt:
`sha256:5223ef9d192676febe319b8b6e138ab67b863b7c950efbd5daf84737c55025af`.

Run:

```bash
.venv/bin/python scripts/run_commons_ml_kem_gauntlet.py \
  --oqs-helper-container edgek-beast-commons-node-a-1
```

This proves live ML-KEM key agreement, but it did **not** initially green
`pq_transport` because the certificate also requires ML-DSA signature/tamper,
replay nonce, artifact digest, and policy-scope capsule evidence.  The Commons
image has since been rebuilt with both `KEM_ml_kem_768` and `SIG_ml_dsa_65`
enabled in liboqs.

**Commons replication closure:** added
`scripts/run_c4x_commons_replication_gauntlet.py`.  It admits a signed
proof-carrying Commons bundle only as a verify-only/quarantined hypothesis,
checks clean source/custody rebuild, reproduces on three independently seeded
logical node identities, requires held-out oracle checks preserving negative
boundaries, and aggregates/promotion-credit only after local reproduction.
Smoke run `physical-truth-commons-replication-live-001` moved
`commons_replication` green.  Receipt:
`sha256:aa47857f4de136e3b33d69269466d259963de4b57f32d17182bc8141a6ea4cca`.

Run:

```bash
.venv/bin/python scripts/run_c4x_commons_replication_gauntlet.py
```

**PSI governance closure:** added `scripts/run_c4x_psi_governance_gauntlet.py`.
It reads real `/proc/pressure` availability through the BEAST system monitor,
then runs safe hostile pressure snapshots through the residual and PSI
governors.  It proves CPU, memory, and IO pressure force bounded refusal,
near-OOM is refused before execution, virtual disk-full conditions are refused
before evidence writes, proof-critical capsules stay pinned during lifecycle
eviction, and evidence digests survive the scarcity path.  It does not
intentionally OOM the host or fill the disk.  Run
`physical-truth-psi-governance-live-002` moved `psi_governance` green. Receipt:
`sha256:c9f422b573289ba632889201ecaa2ead2c513d065779ff865f9bb8097390f8a0`.

Run:

```bash
.venv/bin/python scripts/run_c4x_psi_governance_gauntlet.py
```

**XDP scope closure:** added `scripts/run_c4x_xdp_scope_gauntlet.py`.  It binds
the certificate to the existing isolated-veth AF_XDP receipts instead of
touching production interfaces.  The selected evidence includes
`x3_af_xdp_echo_20260720T113948Z.json` with 10,000 packets sent, received,
transmitted, and echoed; zero echo drops; and zero XDP socket misses.  The
hostile policy envelope proves unauthorized cgroups are refused, worker death
is observed, detach is detected by policy generation, fail-closed behavior is
selected, Guardian authority is required, and unrelated traffic redirection is
outside the claim.  Run `physical-truth-xdp-scope-live-001` moved `xdp_scope`
green. Receipt:
`sha256:833104b8c08b3e7179860b199ad405dbda08ea41bcf1f738a0f2c7f4ded4ca17`.

Run:

```bash
.venv/bin/python scripts/run_c4x_xdp_scope_gauntlet.py
```

**PQ transport closure:** added `scripts/run_c4x_pq_transport_gauntlet.py`.
The gate uses the live Commons `/v1/ml-kem/key` and `/v1/ml-kem/challenge`
endpoints plus a Commons container helper so ML-KEM shared secrets are never
serialized to host receipts.  It also proves ML-DSA-65 signature verification,
signature/body tamper rejection, ciphertext tamper rejection, replay-nonce
refusal, artifact digest binding, and policy-scope acceptance.  A real bug was
found and fixed while closing this gate: legacy Commons nodes persisted only
the ML-KEM secret key, but liboqs-python cannot recover the matching public key
from that secret, so restarted nodes could publish an unrelated public key and
fail decapsulation confirmation.  `app/kernel/commons/ml_kem.py` now persists a
bounded local keypair envelope with public and secret digests; legacy
secret-only files rotate once because their matching public key is
unrecoverable.

Final run `physical-truth-pq-transport-ml-dsa-live-002` moved `pq_transport`
green. Receipt:
`sha256:b9f7e387c83206f9a4ac33525f18281b0c237564bb4c37283072f2d176778c38`.
Certificate digest:
`sha256:48052a45cc9c35203a3621e3225b293ceedd36ade716c4f2e191459ea65b8cb7`.

Run:

```bash
.venv/bin/python scripts/run_c4x_pq_transport_gauntlet.py \
  --oqs-helper-container edgek-beast-commons-node-a-1
```

The certificate now has 12/12 green gates and no red gates:

- `c4x_truth`
- `sensorium_observation`
- `bpf_witness`
- `protocol_integrity`
- `memfd_custody`
- `guardian_custody`
- `reuse`
- `pq_transport`
- `commons_replication`
- `route_resilience`
- `psi_governance`
- `xdp_scope`

Verification:

```bash
.venv/bin/python -m py_compile \
  app/kernel/commons/ml_kem.py \
  scripts/run_c4x_pq_transport_gauntlet.py \
  scripts/run_c4x_psi_governance_gauntlet.py \
  scripts/run_c4x_xdp_scope_gauntlet.py
.venv/bin/python -m pytest tests/test_c4x_physical_truth_certificate.py -q
```

Result: `5 passed`, latest certificate gates all true, and
`public_credit_allowed=true`.

**Operational caveat:** the source and live containers are patched.  A full
Commons image rebuild was blocked by host disk pressure during `apt-get`
workspace allocation, so the live lab was updated by copying the patched
`ml_kem.py` into the running Commons containers and restarting them.  The repo
also now excludes `.beast`, virtualenvs, evidence, worktrees, deploy bundles,
and other heavyweight artifacts from Docker build context so the next rebuild
does not drag the whole beast-cave into Docker.

Run:

```bash
.venv/bin/python scripts/run_c4x_protocol_reuse_route_gauntlet.py
```

If sudo is needed for the remaining physical layers, prime sudo only in a real
local terminal; do not pass the password through automation logs:

```bash
sudo -v
.venv/bin/python scripts/run_c4x_sudo_physical_harvest.py --skip-sudo
```

## D5 — Ultimate final-proof hardening *(in progress)*

**Goal:** separate a digest-bound 12/12 certificate from the higher
"once-and-for-all" physical/external proof standard.  A green receipt must not
be bluffable by well-shaped JSON, stale status wording, or self-reported source
authority.

1. ~~Make the certificate recompute every layer receipt digest before granting
   credit.~~  The verifier now removes `receipt_digest`, recomputes the
   canonical payload digest, and requires exact equality.
2. ~~Add hostile negative controls for fabricated green receipts.~~  The test
   suite now rejects twelve all-green forged receipts with zero-filled SHA-256
   strings, rejects post-digest tampering, and rejects contradictory status
   fields.
3. ~~Require per-layer authority, claim boundary, source linkage, and signature
   or file-backed attestation before certificate credit.~~  The certificate now
   refuses missing authority, weak boundary text, missing source linkage,
   missing/mismatched attestation, and contradictory status/error fields.
4. ~~Fix stale Guardian wording.~~  The sudo custody runner now emits
   `status: passed` when producer-death-after-handoff and the other Guardian
   proof fields are true; the hardener also corrects legacy sidecar wording.
5. ~~Add a sidecar provenance hardener.~~
   `scripts/harden_c4x_physical_truth_sidecar.py` binds existing receipts to the
   stricter verifier contract without changing their required truth booleans.
   The full one-shot runner now executes this hardener before the final
   certificate.
6. ~~Reject claimant-controlled fallback attestation.~~  Fallback attestation is
   now accepted only after the certificate recomputes SHA-256 for
   `source_artifacts[]` files under the repository and, when supplied, verifies
   that the source file contains the linked digest.  The hostile test
   `test_claimant_controlled_attestation_without_source_file_is_refused`
   proves that a deterministic hash over self-claims no longer grants credit.
7. Harden the BPF proof class from process-local witness + BPF authority to
   actual kernel ring-buffer evidence from the exact C4-X cgroup:
   C4-X outbound connects `0`, DNS `0`, provider sockets `0`, and a positive
   provider-comparator network control `>0`.
8. Harden PSI from policy/snapshot pressure simulation to disposable-cgroup
   physical pressure induction: real CPU throttling, memory pressure/OOM,
   I/O saturation, disk/inode exhaustion, and evidence-preservation checks.
9. Harden XDP from prior AF_XDP evidence plus policy simulations to live
   isolated namespace attacks: detach, worker death, RX-ring saturation,
   unauthorized-cgroup rejection, and unrelated-traffic exclusion.
10. Harden Commons from independent logical identities in one execution authority
   to three independent execution authorities: local machine, public CI runner,
   and unrelated verifier machine, each with independent seed and oracle.
11. Make the reproduction capsule hermetic: include the omitted PDF fixture and
    `.byron/services.yaml` fallback fixture, hash-lock Python dependencies,
    digest-pin Docker base images, and pin liboqs by immutable commit instead
    of a moving tag.

**Current verdict:** the certificate is no longer trivially bluffable at the
receipt level and no longer accepts claimant-only deterministic attestation.
The remaining ultimate-proof work is substrate/externality: kernel BPF witness
for the exact process, physically induced PSI/XDP failures, independent Commons
authorities, and hermetic packaging.

Verification:

```bash
.venv/bin/python -m pytest tests/test_c4x_physical_truth_certificate.py -q
.venv/bin/python scripts/harden_c4x_physical_truth_sidecar.py \
  --sidecar evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json
.venv/bin/python scripts/run_c4x_physical_truth_certificate.py \
  --run-id physical-truth-source-file-bound-verify-004 \
  --sidecar evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json
```
