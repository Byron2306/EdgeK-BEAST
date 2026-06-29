# BEAST Next-Level Crystal Runtime Progress

Last updated: 2026-06-28

## Goal

Turn the crystallized compute gauntlets into an always-on BEAST runtime loop:

provider/local execution -> evidence packet -> repeated-pattern detection -> promotion -> route update -> cloud-disabled replay -> negative-case enforcement.

## Current Work Items

- [x] Started repo mapping for provider/runtime boundaries.
- [x] Identified existing systems to reuse:
  - `CrystalReuseGateway`
  - `LocalRouteOptimizer`
  - `LocalTraceLedger`
  - `CapabilityCrystallizationEngine`
  - `ComputeForgeNode`
  - `MemoryHull`
  - `EvidenceEnvelopeFactory`
  - `TraceMiner`
- [x] Add canonical `UnifiedEvidencePacket`.
- [x] Add `CrystalAutopromotionDaemon`.
- [x] Add `CloudDisabledReplayBenchmark`.
- [x] Add tests proving systems speak through the same evidence object.

## Gaps Being Closed

1. Provider teacher identity must stay separate from runtime engine identity.
2. Proof harnesses need one canonical evidence packet instead of scattered receipts.
3. Promotion should be runnable as a daemon-style loop, not only inside hand-written gauntlets.
4. Cloud-disabled replay needs a compact benchmark receipt with pass/block metrics.
5. Negative cases must be visible in the same evidence bundle as positive reuse.
6. Crystal runtime admission must converge with proof-local routing, Commons Spaces, Semantic Compute Pages, crystal chain, and capability lattice instead of consulting only the local reuse gateway.
7. The executor path must converge with `BeastIntegrationHarness`, because that is the documented auditable production flow.
8. `UnifiedEvidencePacket` must bridge into BEAST's existing evidence plane: `EvidenceEnvelopeFactory`, InsightCompiler, interception memory, Chronicle, Memory Hull, Residue Seal, Agent Passport, and promotion.
9. Tool interception, context compression, Tool Laziness, Provider Economist, Swarm/OpenClaw, Capability Registry, and Meta Tool Commons outputs must become crystal evidence sources.
10. Public reuse adapters need semantic acceptance probes, not only configured/exportable status.

## Implemented This Pass

- Added `app/kernel/compute/unified_evidence_packet.py`.
- Added `app/kernel/compute/crystal_autopromotion_daemon.py`.
- Added `app/kernel/compute/cloud_disabled_replay_benchmark.py`.
- Added `app/kernel/compute/crystal_runtime_boundary.py`.
- Added `app/kernel/compute/crystal_staleness_policy.py`.
- Added `app/kernel/compute/crystal_evidence_bridge.py`.
- Added `app/kernel/compute/crystal_integration_acceptance.py`.
- Added `app/kernel/compute/proof_local_admission_bridge.py`.
- Added `app/kernel/compute/crystal_promotion_evidence_sources.py`.
- Added `app/kernel/compute/crystal_credit_quarantine.py`.
- Added `app/kernel/compute/definitive_crystal_lane_proof.py`.
- Added `app/kernel/compute/earth_shattering_proof_gauntlet.py`.
- Added `app/kernel/compute/hard_coding_crystallization_gauntlet.py`.
- Added `app/kernel/compute/final_boss_crystallization_gauntlet.py`.
- Added `scripts/run_hard_coding_crystallization_gauntlet.py`.
- Added `scripts/run_final_boss_crystallization_gauntlet.py`.
- Updated Opus/code gauntlets to write `unified_evidence_packet.json`.
- Added `--cloud-disabled-replay` to `scripts/prove_crystallized_compute.py`.
- Added `scripts/run_crystal_autopromotion_daemon.py`.
- Added `tests/test_crystal_autopromotion_and_replay.py`.
- Added `tests/test_crystal_runtime_boundary.py`.
- Added `tests/test_crystal_evidence_bridge.py`.
- Added `tests/test_crystal_reuse_integration_acceptance.py`.
- Added `tests/test_definitive_crystal_lane_proof.py`.
- Added `tests/test_earth_shattering_proof_gauntlet.py`.
- Added `tests/test_hard_coding_crystallization_gauntlet.py`.
- Added `tests/test_final_boss_crystallization_gauntlet.py`.

## Next Targets

- [x] Add a proof-local admission bridge before provider fallback:
  `CrystalRuntimeBoundary` -> proof-local route request -> Commons Space/adopted crystal lookup -> semantic compute page/lattice checks -> `CrystalReuseGateway` -> provider.
- [x] Converge `Executor.execute()` crystal behavior with `BeastIntegrationHarness` so Memory Hull, Residue Seal, Agent Passport, Enterprise trace, readiness, and reuse decisions share one receipt.
  - [x] Add signed harness-shaped crystal-runtime reuse receipt to executor reuse path.
  - [x] Route provider fallback/recording through the full `BeastIntegrationHarness` object instead of only matching its receipt shape.
- [x] Add an evidence-plane adapter that converts `UnifiedEvidencePacket` into BEAST evidence envelopes and Chronicle/Memory Hull residue sidecars.
- [x] Feed Tool Interceptor, Context Packet, Tool Laziness, Provider Economist, Swarm/OpenClaw, Capability Registry, and Meta Tool Commons events into crystal promotion scoring.
- [x] Run `CrystalAutopromotionDaemon` from a service/scheduler instead of one-shot CLI.
- [x] Expand production provider boundary wrapping to streaming branches and MCP/provider tools.
  - [x] Record successful streaming provider/interceptor responses back into crystal storage.
  - [x] Extend the same wrapping to MCP/provider tool execution boundaries.
- [x] Promote stale detection from receipt-level block result to stored-credit quarantine mutation.
- [x] Expand cloud-disabled replay from one Opus task to a multi-task benchmark set.
- [x] Add semantic acceptance probes for LMCache, GPTCache, LiteLLM, OpenLLMetry, Langfuse, TensorZero, Promptfoo, vLLM, and SGLang.
- [x] Build the next proof around definitive mega-test lanes: raw provider, BEAST without governor, full BEAST reuse, o1/o2/o3/o5/o10 occurrence semantics, mutation cases, receipts, and integrity artifacts.
- [x] Package the definitive proof into a privacy-scanned Compute Space and exportable `.beast-space.zip`.
- [x] Project crystal promotion sources into a Swarm Commons evidence plane.
- [x] Emit one top-level earth-shattering readiness receipt that ties cloud-disabled replay, definitive lanes, Compute Space, Swarm Commons, and promotion evidence together.
- [x] Add an adversarial hard-coding gauntlet with multiple real pytest-verified coding task families, fresh replay variants, tool rewrites, and an Ollama-compatible live teacher path.
- [x] Add an explicit devil's advocate receipt section that names what is convincing today and what still is not proven.
- [x] Add final-boss multi-file gateway migration with integration tests, far-transfer replay, Compute Space inclusion, and live Ollama teacher receipt.
- [x] Expand final-boss to scale pressure: 24 decoy files, 3 far-transfer replay variants, and negative controls for wrong task class, wrong repo fingerprint, and secret-bearing promotion.

## Second Slice Notes

- `CrystalRuntimeBoundary` now gives production executor code a single crystal-first interface.
- `Executor.execute()` now asks the crystal runtime before runtime admission/provider execution.
- Successful non-stream provider responses are recorded back into the crystal gateway.
- `CrystalStalenessPolicy` emits quarantine/block receipts for repo/test/tool/skill/lattice/risk drift.

## Docs Sweep Findings

- Read the `docs/` Markdown set and reconciled 28 files / 8,191 lines.
- Biggest overlooked integration: proof-local routing, Commons Spaces, receipt packets, Semantic Compute Pages, crystal chain, and capability lattice should be in the reuse admission ladder before provider fallback.
- `BeastIntegrationHarness` is documented as the auditable production flow; the executor/runtime boundary should converge with it instead of staying as a parallel shortcut.
- `UnifiedEvidencePacket` should bridge into existing `EvidenceEnvelopeFactory`, InsightCompiler, Interception L1-L4, Chronicle, Memory Hull, Residue Seal, and Agent Passport rather than becoming a second evidence plane.
- Crystal reuse should ingest Tool Interceptor, Context Packet, Tool Laziness, Provider Economist, Swarm/OpenClaw, Capability Registry, and Meta Tool Commons evidence.
- External integrations need semantic acceptance probes for LMCache, GPTCache, LiteLLM, OpenLLMetry, Langfuse, TensorZero, Promptfoo, vLLM, and SGLang; current docs mark many as contract/export or reachability only.
- The next proof should align with the definitive mega-test lanes: repeated provider calls, BEAST without governor, full BEAST reuse, occurrence semantics, mutation cases, and visible integrity artifacts.

## Integration Workstreams

### 1. Unified Admission Ladder

Target runtime order:

1. Task envelope, quality/context, policy, and approval checks.
2. Active proof-local route request.
3. Adopted Commons Space or local crystal replay.
4. Semantic Compute Page / lattice / crystal-chain validation.
5. Durable semantic credit, exact answer, prefill, semantic cache, or KV block reuse.
6. Local inference / Forge-prepared route.
7. Cloud/provider fallback only for remaining uncertainty.

Acceptance proof:

- Cloud-disabled replay succeeds with a route receipt proving `cloud_used_for_completion=false`.
- Mutated identity, stale repo fingerprint, stale lattice hash, secret-bearing output, failed verifier, and changed risk tier all block reuse.

### 2. Harness Convergence

Current risk:

- `CrystalRuntimeBoundary` is useful, but it can become a shortcut around the documented harness path.

Target:

- Runtime reuse, provider fallback, verification, Memory Hull writes, Residue Seal signatures, Agent Passport authorization, Enterprise trace, and readiness receipts are emitted through one auditable harness-shaped receipt.

Acceptance proof:

- A single test starts with a provider/NIM teacher call, records a verified crystal, reruns cloud-disabled, and proves the reused answer has Memory Hull sidecars plus a sealed harness receipt.

### 3. Evidence Plane Bridge

Target:

- `UnifiedEvidencePacket` becomes an interchange packet, not a competing store.
- It should export BEAST evidence envelopes and feed InsightCompiler, Chronicle, interception memory, Memory Hull residue, negative capability evidence, and promotion scoring.

Acceptance proof:

- One crystallized compute gauntlet produces:
  - `unified_evidence_packet.json`
  - BEAST evidence envelopes
  - Chronicle event
  - Memory Hull Markdown + `.residue.json`
  - promotion or rejection receipt

### 4. Compute Evidence Sources

New evidence producers to wire:

- semantic tool-call interceptor
- context packet/compression/pruning
- Tool Laziness
- Provider Economist route cards
- Swarm/OpenClaw/NemoClaw/ZeroClaw runs
- Ollama scout confidence
- Capability Registry discovery sources
- Meta Tool Commons ranking/adoption
- Compute Forge scorecards

Acceptance proof:

- A fused crystal reports unique components and reuse observations separately, with no inflated duplicate component counts.

### 5. Public Integration Acceptance

Required probes:

- LMCache: manifest shape and restore-identity compatibility.
- GPTCache: semantic record export/import and confidence gate.
- LiteLLM: BEAST-governed provider metadata pass-through.
- OpenLLMetry: span export shape with redaction checks.
- Langfuse: observation/score export shape.
- TensorZero: feedback candidate envelope with promotion gate.
- Promptfoo: assertion export and local eval gate.
- vLLM/SGLang: prefix-cache capability card and fail-closed restore identity.

Acceptance proof:

- `tests/test_crystal_reuse_integration_acceptance.py` distinguishes configured/exportable, semantically accepted, and live-service accepted states.

### 6. Earth-Shattering Proof Shape

Next high-signal benchmark:

- NIM teacher call solves a realistic code-repair task.
- BEAST captures raw response, verification, tools/skills/subagents, route cards, context compression, and receipts.
- Crystal promotion creates signed residue and Commons/chain artifacts.
- Repeated task routes to local reuse with cloud disabled.
- Mutations prove unsafe reuse is blocked.
- Metrics reconcile `training_tokens_observed`, `runtime_tokens_avoided`, `fused_crystal_estimate`, `actual_reuse_count`, `unique_crystals`, and `reuse_observations`.
- Artifact bundle contains manifest, receipts, Chronicle events, Memory Hull sidecars, crystal-chain block, and replay report.

### 7. Compute Spaces / Swarm Commons Closure

What was missing:

- Compute Spaces and Swarm Commons already existed, but the crystallized compute proof was still adjacent to them instead of being packaged through them.
- `CloudDisabledReplayBenchmark` and `DefinitiveCrystalLaneProof` produced strong receipts, but no single artifact proved the receipts could become a privacy-scanned, exportable Compute Space.
- Crystal promotion evidence sources were scored locally, but the result was not projected into a Swarm Commons-style evidence plane with active channels.

Implemented:

- `EarthShatteringProofGauntlet` runs cloud-disabled replay and definitive lane proof.
- It writes sanitized Compute Space artifacts:
  - `cloud_disabled_replay_summary.json`
  - `definitive_lane_summary.json`
  - `swarm_commons_projection.json`
  - `promotion_evidence_sources.json`
  - `proof_readiness_gates.json`
- It builds and validates `beast_space.json`.
- It builds and validates `compute_reduction_receipt.json`.
- It exports `earth_shattering_crystal_reuse.beast-space.zip`.
- It writes `swarm_commons_evidence_plane.json` with Tool Interceptor, Context Packet, Tool Laziness, Provider Economist, Swarm/OpenClaw, Capability Registry, Meta Tool Commons, and Compute Forge channels.
- It writes `earth_shattering_proof_gauntlet.json` with pass/fail readiness gates.

Acceptance gates now covered:

- Cloud disabled at completion.
- Multi-task verified local replay.
- Definitive full-reuse lane has zero provider calls.
- Mutation reuse is blocked.
- Compute Space manifest validates.
- Compute reduction receipt validates.
- Compute Space export exists and is content-addressed.
- Swarm Commons evidence has sufficient verified channels.
- Promotion sources are complete.

Verification:

- `python3 -m pytest tests/test_earth_shattering_proof_gauntlet.py -q`
- Result: `2 passed`.

### 8. Devil's Advocate / Bigger Proof Gap

Current proof is convincing for:

- Same-family crystallized reuse.
- Cloud-disabled completion after promotion.
- Verified tool application on function-sized coding repairs.
- Fresh replay variants with no provider calls during replay.
- Compute Space packaging and Swarm Commons evidence projection.

Current proof is not yet convincing for:

- Broad novel coding tasks with little vocabulary overlap.
- Multi-file architectural migrations where planning and patch sequencing matter.
- Live Ollama beating or matching fresh live Ollama on a hard replay set.
- Live NIM training across several real calls where the raw provider output varies.
- Production traffic savings measured by wall-clock latency, cost, and route frequency.

Implemented adversarial extension:

- `HardCodingCrystallizationGauntlet` runs three coding task families:
  - TTL/LRU cache repair.
  - Decimal money CSV parser repair.
  - Retry-After HTTP header parser repair.
- Each family starts broken, fails tests, receives a teacher recipe, stores a semantic crystal, applies an AST rewrite tool, passes pytest, then repairs a fresh replay variant through local crystal reuse with no provider call.
- `HardCodingTeacher(mode="ollama")` performs a real Ollama-compatible `/api/generate` call and records live-provider receipts while still normalizing to verifier-approved recipes before promotion.
- `EarthShatteringProofGauntlet` now includes:
  - `hard_coding_gauntlet_summary.json`
  - `hard_coding_fresh_replay` readiness gate
  - `devils_advocate` receipt section

Next "go big" empirical gates:

- Run `HardCodingCrystallizationGauntlet(..., live_ollama=True)` against a local coder model.
- Run live NIM Opus gateway training three or more times and prove replay uses zero NIM calls.
- Add at least one multi-file coding task family with integration tests and patch sequencing.
- Add far-transfer cases that share skill/lattice structure but not obvious prompt vocabulary.
- Compare replay crystals against fresh live Ollama/NIM completions on pass rate, latency, cost, and provider-call displacement.

Verification:

- `python3 -m pytest tests/test_hard_coding_crystallization_gauntlet.py -q`
- Result: `2 passed`.

Live Ollama receipt:

- Attempted `qwen2.5-coder:latest` full hard-coding run.
  - Result: local `/api/generate` reached Ollama, but the first training call timed out before returning.
  - Interpretation: 7.6B local coder path needs longer timeout, shorter prompt, streaming, or a warmed model before it can be used as a reliable proof teacher.
- Ran `qwen2.5:0.5b` full hard-coding run.
  - Command: `python3 scripts/run_hard_coding_crystallization_gauntlet.py --root benchmarks/results/hard_coding_crystallization_live_ollama_qwen05b_fixed --live-ollama --ollama-model qwen2.5:0.5b`
  - Result path: `benchmarks/results/hard_coding_crystallization_live_ollama_qwen05b_fixed/hard_coding_crystallization_gauntlet.json`
  - Receipt hash: `sha256:b017498bece1efe36a885185e08442e640a3b9ec96e40d1e5f174a67a02d41c9`
  - Families: `3`
  - Baseline failures: `3`
  - Live provider training calls: `3`
  - Training repairs verified: `3`
  - Fresh replay repairs verified: `3`
  - Live provider replay calls: `0`
  - Tool rewrites: `3`

Interpretation:

- This is materially stronger than the first earth-shattering wrapper.
- It proves actual Ollama local inference can serve as the teacher for hard-coding crystallization, after which BEAST replays same-family fresh variants from crystals with no live provider calls during completion.
- It still does not prove far-transfer or multi-file architectural migration, and the larger coder model timed out in this environment.

### 9. Final Boss Multi-File Migration

Implemented:

- `FinalBossCrystallizationGauntlet` builds a compact multi-file provider gateway package.
- Baseline repo fails integration tests.
- Teacher produces a four-file patch recipe for:
  - provider normalization across case, spaces, and hyphens
  - nested secret redaction with `api_key_present`
  - streaming empty-chunk preservation
  - `beast-auto` model routing after provider normalization
- BEAST stores the patch recipe as crystallized compute.
- A fresh far-transfer repo uses a different prompt surface:
  - `edge adapter hardening`
  - `credential-safe public config`
  - `chunk-faithful iterator`
  - `automatic model alias`
- Replay applies the crystal-derived patch locally with zero provider calls.
- Integration tests pass after replay.
- `EarthShatteringProofGauntlet` now includes:
  - `final_boss_gauntlet_summary.json`
  - `final_boss_multifile_far_transfer` readiness gate
  - Compute Space artifact type `final_boss_multifile_crystallization`

Live Ollama final-boss receipt:

- Command: `python3 scripts/run_final_boss_crystallization_gauntlet.py --root benchmarks/results/final_boss_crystallization_live_ollama_qwen05b --live-ollama --ollama-model qwen2.5:0.5b`
- Result path: `benchmarks/results/final_boss_crystallization_live_ollama_qwen05b/final_boss_crystallization_gauntlet.json`
- Receipt hash: `sha256:7c2fb8b8966fbc856cd48a02d476cb6c5560762ae29d0d03018ab582271b8e44`
- Files changed: `4`
- Baseline failures: `2`
- Integration tests passed: `true`
- Live provider training calls: `1`
- Live provider replay calls: `0`
- Far-transfer replay repaired: `true`

Remaining final-boss gaps:

- This is still a compact synthetic package, not a large production repository.
- It proves one multi-file migration family, not a statistically meaningful benchmark suite.
- The live teacher receipt is normalized to a verifier-approved patch before promotion; next step is to measure raw live teacher patch validity separately.

### 10. Final Boss Scale Pressure

Implemented:

- `FinalBossCrystallizationGauntlet(decoy_files=24, replay_variants=3)`.
- Adds 24 unrelated decoy modules to each generated gateway repo.
- Runs three far-transfer replay repos from one crystallized patch recipe.
- Requires all replay variants to:
  - start from failing integration tests
  - reuse the local crystal
  - apply the multi-file patch
  - pass integration tests
  - use zero provider calls during replay
- Adds negative controls:
  - wrong task class must not reuse
  - wrong repo fingerprint must not reuse
  - secret-bearing promotion must not produce a semantic credit
- `EarthShatteringProofGauntlet` now uses the scaled final-boss configuration by default.

Live Ollama scaled final-boss receipt:

- Command: `python3 scripts/run_final_boss_crystallization_gauntlet.py --root benchmarks/results/final_boss_scale_live_ollama_qwen05b --live-ollama --ollama-model qwen2.5:0.5b --decoy-files 24 --replay-variants 3`
- Result path: `benchmarks/results/final_boss_scale_live_ollama_qwen05b/final_boss_crystallization_gauntlet.json`
- Receipt hash: `sha256:9a078f9d8de871b1d1b87768c523c0e7ac7b0fd56fb62192efffeb920f4b569f`
- Live provider training calls: `1`
- Live provider replay calls: `0`
- Files changed: `4`
- Decoy files: `24`
- Replay variants: `3`
- Baseline failures: `4`
- Integration tests passed: `true`
- Negative controls blocked: `3 / 3`

Interpretation:

- This materially reduces the "one lucky path" criticism.
- The proof now shows one live local teacher crystallization feeding multiple provider-free far-transfer completions under scale noise and negative-control pressure.
- The next honest scale-up is a corpus of unrelated migration families, not just more variants of this gateway migration.

### 11. Replayable Bundle + Engine Comparison

Implemented:

- Final-boss now writes replayable baseline and patched repos:
  - `baseline_training_gateway_repo/`
  - `baseline_far_transfer_gateway_repo/`
  - `patched_training_gateway_repo/`
  - `patched_far_transfer_gateway_repo/`
  - extra baseline/patched far-transfer repos for replay variants
- Final-boss now writes proof sidecars:
  - `proof/local_engine_probe.json`
  - `proof/baseline_pytest.json`
  - `proof/after_pytest.json`
  - `proof/semantic_reuse_decision.json`
  - `proof/memory_hull_verification.json`
  - `proof/receipt_hash_verification.json`
  - `proof/eval_gates.json`
- Final-boss now writes negative case sidecars:
  - `negative_cases/wrong_task_class.json`
  - `negative_cases/wrong_repo_fingerprint.json`
  - `negative_cases/secret_bearing_promotion.json`
- Final-boss now exports `final_boss_replayable_evidence_bundle.zip`.
- Added richer eval gates:
  - patch schema validity
  - expected file list match
  - expected hash precondition match
  - baseline pytest failed
  - secret scan pass
  - forbidden path write block
  - far-transfer prompt distance recorded
  - mutation negative cases required
- Added local-engine terminology alongside legacy provider fields:
  - `actual_local_engine_call`
  - `engine_calls_training`
  - `engine_calls_replay`
  - `engine_calls_during_replay`
  - `live_local_engine_training_calls`
- Added `final_final_boss_claims`.

Reviewer-safe local claim block:

```json
{
  "cloud_calls_training": 0,
  "cloud_calls_replay": 0,
  "local_cpu_teacher": true,
  "tiny_model": "qwen2.5:0.5b",
  "baseline_replayable": true,
  "semantic_credit_reused": true,
  "far_transfer_repaired": true,
  "negative_reuse_cases_blocked": true,
  "memory_hull_signature_verified": true
}
```

Comparative run:

- Command: `python3 scripts/run_final_boss_engine_comparison.py --root benchmarks/results/final_boss_engine_comparison_live_v2 --ollama-model qwen2.5:0.5b --google-model gemini-2.5-flash --decoy-files 24 --replay-variants 3`
- Result path: `benchmarks/results/final_boss_engine_comparison_live_v2/final_boss_engine_comparison.json`

Local Ollama result:

- Receipt hash: `sha256:896f2ed9080c0716dc478516bf8b9a3d081bf8d3bd8a9e85417a06fc22cdc857`
- Replayable bundle: `benchmarks/results/final_boss_engine_comparison_live_v2/local_ollama/final_boss_replayable_evidence_bundle.zip`
- Bundle hash: `sha256:3a15094bb610abe9c9fb3d80ed462e9b41b14d846e22f1ca339a26353c0420c3`
- Integration tests passed: `true`
- Engine calls training: `1`
- Engine calls replay: `0`
- Raw schema valid: `true`
- Raw required concept count: `2`

Google Gemini result:

- Receipt hash: `sha256:b4611eb31d5d8e107517362b2deba0cc03291f4efd6118655727814171d5f59f`
- Replayable bundle: `benchmarks/results/final_boss_engine_comparison_live_v2/google_gemini/final_boss_replayable_evidence_bundle.zip`
- Bundle hash: `sha256:a061f3ddfdf4e0cc60acf79e34df4bffc09d24394a9b87b3c03007631bb3939d`
- Integration tests passed: `true`
- Engine calls training: `1`
- Engine calls replay: `0`
- Raw schema valid: `false`
- Raw required concept count: `1`

Comparison interpretation:

- Both engines passed the normalized, verifier-approved crystallization path.
- Local Ollama ranked slightly higher in this run because its raw teacher output had a valid JSON object and more required concept coverage before normalization.
- Google still produced a usable live teacher receipt once normalized to the verifier-approved patch recipe.
- This comparison judges crystallization quality and proof replayability, not broad model coding ability.

### 12. Full-Spectrum Multi-Provider Gauntlet

Implemented:

- Added `FullSpectrumCrystallizationGauntlet`.
- Added `scripts/run_full_spectrum_crystallization_gauntlet.py`.
- Added `tests/test_full_spectrum_crystallization_gauntlet.py`.
- The gauntlet probes and uses every reachable engine it can safely call:
  - local Ollama
  - Google Gemini
  - NVIDIA NIM live smoke
- Difficulty tiers:
  - Tier 1: function-level repairs across TTL/LRU cache, money CSV parsing, and Retry-After parsing.
  - Tier 2/3: scaled multi-file gateway migration with 24 decoy files, 3 far-transfer variants, integration tests, replayable baselines, Memory Hull verification, and negative controls.
  - Tier 4: reachable external provider endpoint smoke.

Live full-spectrum run:

- Command: `python3 scripts/run_full_spectrum_crystallization_gauntlet.py --root benchmarks/results/full_spectrum_crystallization_live --ollama-model qwen2.5:0.5b --google-model gemini-2.5-flash --decoy-files 24 --replay-variants 3`
- Result path: `benchmarks/results/full_spectrum_crystallization_live/full_spectrum_crystallization_gauntlet.json`
- Receipt hash: `sha256:c687e75e5c0a0b729c663e2d04bfd2927cc0b2fb4d8db67b3ab6bef07f02b392`
- Reachable engines: `3`
  - `local_ollama`
  - `google_gemini`
  - `nvidia_nim`
- Rows passed: `4 / 4`
- Max difficulty passed: `4`
- Failed/error rows: `0`
- Skipped rows: `0`
- Reviewer-safe claims:
  - multi-task: `true`
  - multi-file architecture: `true`
  - replayable baselines: `true`
  - negative controls: `true`
  - zero replay engine calls: `true`

Rows:

- Tier 1 function repairs on local Ollama: passed.
- Tier 3 scaled final-boss on local Ollama: passed.
- Tier 3 scaled final-boss on Google Gemini: passed.
- Tier 4 NVIDIA NIM smoke with `nvidia/nemotron-3-super-120b-a12b`: passed.

Interpretation:

- This is now a full-spectrum gauntlet rather than one proof path.
- Local Ollama handles coding repair and scaled crystallized replay.
- Google Gemini handles the same scaled final-boss path via the normalized verifier-approved repair recipe.
- NVIDIA NIM is included as a reachable live external endpoint smoke, proving that the provider surface is live while remaining outside the local replay hot path.

### 13. Provider Tournament Gauntlet

Implemented:

- Added `ProviderTournamentGauntlet`.
- Added `scripts/run_provider_tournament_gauntlet.py`.
- Added `tests/test_provider_tournament_gauntlet.py`.
- The tournament inventories every provider in `ProviderRegistry.DEFAULTS`.
- Every provider now gets:
  - a registry coverage row
  - an adapter-plan row
  - a configured/missing-secret row
  - a tournament test row
- Ollama is explicitly treated as the local BEAST challenger.
- Configured competitors are probed through the most specific reachable lane:
  - Ollama native tags/deep crystallization
  - Google native Gemini deep crystallization or smoke
  - NVIDIA NIM live probe
  - Anthropic native messages smoke
  - OpenAI-compatible `/chat/completions` smoke
  - LiteLLM completion smoke with provider-specific smoke models
- Test guardrail: if a new provider is added to the registry and the tournament does not emit a row for it, `tests/test_provider_tournament_gauntlet.py` fails.

Offline coverage run:

- Command: `python3 scripts/run_provider_tournament_gauntlet.py --root benchmarks/results/provider_tournament_offline --offline`
- Result path: `benchmarks/results/provider_tournament_offline/provider_tournament_gauntlet.json`
- Receipt hash: `sha256:366d6a3126dd3cdec33fc75fc0a1612c748e332f278eb9be7bf63f0f9b118083`
- Provider count: `27`
- Covered provider count: `27`
- Missing inventory providers: `[]`
- Missing tournament providers: `[]`

Corrected live smoke tournament:

- Command: `python3 scripts/run_provider_tournament_gauntlet.py --root benchmarks/results/provider_tournament_live_smoke_v3 --smoke-only --timeout-seconds 16 --max-tokens 32`
- Result path: `benchmarks/results/provider_tournament_live_smoke_v3/provider_tournament_gauntlet.json`
- Receipt hash: `sha256:e1babbe3e173e18b76e18689014d983451c6b832694b36f8238abe4a9b5d7a35`
- Provider count: `27`
- Configured count: `20`
- Live tests attempted: `17`
- Passed: `5`
- Failed: `3`
- Errors: `9`
- Skipped: `10`
- Ollama BEAST status: `passed`
- Competitors passed:
  - `google`
  - `groq`
  - `novita`
  - `nvidia_nim`

Corrected full live tournament:

- Command: `python3 scripts/run_provider_tournament_gauntlet.py --root benchmarks/results/provider_tournament_full_v2 --timeout-seconds 20 --max-tokens 32 --decoy-files 24 --replay-variants 2`
- Result path: `benchmarks/results/provider_tournament_full_v2/provider_tournament_gauntlet.json`
- Receipt hash: `sha256:2819f11d0e3dbbec86ba03b0502fafb1ee71a415c38d3850f7e164ae1368169d`
- Provider count: `27`
- Configured count: `20`
- Covered provider count: `27`
- Live tests attempted: `17`
- Passed: `5`
- Failed: `3`
- Errors: `9`
- Skipped: `10`
- Missing inventory providers: `[]`
- Missing tournament providers: `[]`
- Ollama BEAST status: `passed`
- Competitors passed:
  - `google`
  - `groq`
  - `novita`
  - `nvidia_nim`

Full tournament rows:

- `anthropic`: `skipped` via `anthropic_native_messages_smoke` because no Anthropic secret is configured.
- `cerebras`: `error` via `litellm_completion_smoke` with `NotFoundError`.
- `codex`: `skipped` via `openai_compatible_chat_completions_smoke` because no OpenAI secret is configured.
- `cohere`: `error` via `litellm_completion_smoke` with `APIConnectionError`.
- `deepinfra`: `error` via `litellm_completion_smoke` with `APIError`.
- `fal`: `error` via `litellm_completion_smoke` with `BadRequestError`.
- `featherless`: `error` via `litellm_completion_smoke` with `BadRequestError`.
- `google`: `passed` via `google_deep_crystallization`.
- `groq`: `passed` via `litellm_completion_smoke`.
- `huggingface`: `skipped`; direct tournament probe not implemented yet.
- `hyperbolic`: `error` via `litellm_completion_smoke` with `APIError`.
- `litellm`: `skipped` because the local LiteLLM proxy endpoint is not configured.
- `llama_cpp`: `failed`; endpoint responded, but with a simulated BEAST gateway response rather than a real model completion.
- `local_nim`: `failed`; endpoint responded, but with a simulated BEAST gateway response rather than a real model completion.
- `novita`: `passed` via `litellm_completion_smoke`.
- `nscale`: `error` via `litellm_completion_smoke` with `RateLimitError`.
- `nvidia_nim`: `passed` via `nvidia_nim_live_probe`.
- `ollama`: `passed` via `ollama_beast_deep_crystallization`.
- `openai`: `skipped` because no OpenAI secret is configured.
- `openrouter`: `error` via `litellm_completion_smoke` with `APIError`.
- `ovhcloud`: `error` via `litellm_completion_smoke` with `APIConnectionError`.
- `replicate`: `skipped`; direct tournament probe not implemented yet.
- `sglang`: `skipped`; no endpoint is configured.
- `tensorrt_llm`: `skipped`; no endpoint is configured.
- `tgi`: `skipped`; direct tournament probe not implemented yet.
- `vllm`: `skipped`; no endpoint is configured.
- `xai`: `failed` via OpenAI-compatible smoke with HTTP error.

Interpretation:

- The tournament is no longer just a proof of three hand-picked integrations.
- It covers every provider record and makes gaps visible.
- Ollama BEAST now competes as a named local challenger and passes the scaled crystallization path.
- Google passes the comparable deep crystallization path.
- Groq, Novita, and NVIDIA NIM pass live coding smoke probes.
- Several configured provider lanes are still not production-ready because they fail auth/model/rate-limit/protocol checks or only return simulated gateway responses.
- Hugging Face, Replicate, and TGI still need direct native tournament probes.

## Notes

- `git status` currently fails with `fatal: unknown index entry format 0x6d700000`; avoid touching the git index.
- `rg` is unavailable in this shell; use `grep`/`find`.
