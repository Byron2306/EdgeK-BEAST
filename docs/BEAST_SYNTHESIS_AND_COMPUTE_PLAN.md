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
the synthesis plane.

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
offset, and symmetry.

## C1 — Commons synthesis Spaces *(complete)*

~~Package semantic and visual capability artifacts with schemas, verifier,
negative cases, replay corpus, evidence, and reproducibility metadata. Remote
packages remain hypotheses until reproduced and promoted locally.~~

**Verification:** `tests/test_commons_synthesis_space.py` covers semantic and
visual synthesis packages, required schemas/verifier/negative cases/replay
corpus/evidence/reproducibility metadata, digest tamper refusal, and
verify-only remote hypothesis authority.

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

**Acceptance:** repeated image-region requests show a transition from provider
fallback or local residual generation to deterministic asset composition, with
provider-image calls trending down and false/stale/intent-mismatched/
structure-weak visual reuse refused.

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
because it matches the requested color.  Low-quality/transparent/flat,
intent-mismatched, or structurally weak regions produce
`visual_asset_candidate_refused` evidence instead of entering the promotion
counter.  The provider-reduction scorecard reports image-region local fills,
visual provider fallback calls, promoted visual assets, promoted asset reuses,
and visual asset refusals without overstating provider-call avoidance until
paired fallback comparisons exist.

## D2 — Evidence economy unification *(implemented)*

**Goal:** make Sensorium, Forge KV, Grand Closure, Commons, and Synthesis
receipts speak the same accounting language without overstating claims.

1. ~~Normalize all reduction receipts into `observed`, `estimated`,
   `route_selection_only`, or `hypothesis` claim classes.~~
2. ~~Feed Forge KV measured prompt-cache savings into the observatory only when
   the engine-specific proof allows a performance claim.~~
3. ~~Feed Grand Closure economics as lifecycle/economics evidence, not provider
   execution savings unless paired execution evidence exists.~~
4. ~~Feed Commons Spaces only after local reproduction/promotion.~~
5. ~~Add G9 bundle-health reporting so missing gates, such as the current
   missing `G3`, stay visible instead of being mentally rounded up.~~

**Progress:** `ComputePlane.ingest_reduction_evidence()` and
`/edgek/compute/reduction-evidence` now admit bounded projections of Forge KV,
Grand Closure/G9, Commons Space, Sensorium, and future reduction receipts.
`/edgek/compute/reduction-evidence/discover` imports recognized repo-local JSON
receipts from historical evidence folders.  Raw prompt/private payload fields
are refused.  Forge KV token savings count only when a native context restore
verifier proves prompt prefill displacement.  Grand Closure/G9 contributes
lifecycle and bundle-health evidence, including missing gates, but does not
count provider execution savings.  Commons Space receipts count only after seal
verification plus local reproduction or promotion.  The provider-reduction
scorecard now reports normalized evidence events and G9 bundle health alongside
observed channels.
