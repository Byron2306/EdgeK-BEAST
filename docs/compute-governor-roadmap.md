# Inference Compute Governor Rollout

The Compute Governor reduces probabilistic work only when BEAST can preserve or
improve verified behavior. Its unit of control is the remaining semantic
uncertainty inside a task, not merely a model call.

Implementation maturity was reconciled against runtime call sites in the
[phase audit](compute-governor-phase-audit.md). “Engine implemented” does not
mean “runtime wired” or “savings realized.”

## Non-Negotiable Policies

### Ambiguity tiebreaker

When confidence does not clearly support one outcome, the gate chooses
`escalate`. It never chooses `suppress` by ambiguity.

A false escalation costs time or money and remains visible in a receipt. A false
suppression can silently remove required work. Suppression therefore requires
positive evidence; uncertainty is evidence for escalation.

### Gate outcomes

| Decision | Meaning |
| --- | --- |
| `reuse` | Use a verified capability whose impact fingerprint is still valid |
| `deterministic` | Resolve the work with a deterministic transform and verifier |
| `local_inference` | Use the local scout or executor within its latency budget |
| `cloud_inference` | Send unresolved semantic work to the selected provider |
| `escalate` | Increase context, capability, or verification because confidence is ambiguous |
| `suppress` | Skip work proven unnecessary; never an ambiguity fallback |
| `require_approval` | Stop before a high-risk, destructive, privileged, or costly action |

Phase 1 records a candidate decision and confidence, but always executes the
existing cloud path. Phase 2 can displace only an explicitly complete task with
a promoted proof and a calibrated, verified deterministic result.

## Repository Impact Fingerprint

Every promoted deterministic capability should carry an Impact Fingerprint:

- SHA-256 file hashes for target, dependency, and test files;
- normalized AST hashes that ignore formatting and source positions;
- hashes for selected functions/classes or top-level symbols;
- pinned tool-schema hashes;
- the governing policy version; and
- the capability confidence at promotion time.

BEAST compares that fingerprint before reuse:

| Repository change | Result |
| --- | --- |
| No relevant change | Capability remains active at the same confidence |
| Comment/format-only change with identical AST | Capability remains active; confidence decays by 2% |
| Target, dependency, test, or symbol AST changes | Capability returns to `shadow_revalidation`; confidence is capped below 0.50 |
| Tool schema or policy version changes | Capability returns to `shadow_revalidation` |
| A tracked path disappears, appears unexpectedly, or escapes the repository | Fail closed and require shadow revalidation |

The fingerprint engine is implemented in `app/kernel/capability_impact.py`.
Automatic attachment and checking at every promotion/reuse boundary remains a
Phase 6 enforcement item.

## Phase 1: Shadow Accounting

Status: **finished for rollout gate: operational, live-evidenced, locally calibrated, and free-provider revalidated; live calibration remains continuous monitoring**.

Goal: measure demand without changing runtime behavior.

- ~~Create privacy-safe Compute Plans before governed provider calls.~~
- ~~Record candidate decision, confidence, ambiguity, and escalation tiebreaker.~~
- ~~Link Compute Receipts to runtime attempts.~~
- ~~Record observed tokens, latency, and first-party cost when supplied.~~
- ~~Add `avoided_tokens_estimate` and `predicted_savings_usd` to receipts.~~
- ~~Expose plans, receipts, metrics, and savings summaries through API, MCP, and TUI.~~
- ~~Keep prompts and source code out of the Compute Ledger.~~
- ~~Run a deterministic behavior-preservation smoke benchmark.~~
- ~~Run a 120-pair closure preflight with unchanged calls, 100% behavior preservation, 100% receipt coverage, and zero suppressions.~~
- ~~Gate weekly savings publication on declared call volume and first-party cost coverage.~~
- ~~Collect a representative xAI observation window across 24 task classes.~~
- ~~Add paired-ablation/provider-attribution calibration fields, coverage, and estimation error to receipts.~~
- ~~Calibrate receipt arithmetic across 120 paired local usage deltas.~~
- Continue live paired calibration as provider budget and attributable usage data become available.

Exit criteria:

- ~~No behavior differences in the deterministic accounting-on/off preflight.~~
- ~~Complete receipts for at least 95% of deterministic preflight attempts.~~
- ~~Cost coverage reported explicitly, never inferred from an undocumented price.~~
- ~~Estimated savings labelled counterfactual.~~
- ~~Confirm behavior preservation and at least 95% receipt coverage on the live observation window.~~

Current deterministic preflight evidence:

- provider calls accounting off/on: `120/120`;
- verified behavior preservation: `100%`;
- receipt coverage: `100%`;
- enforced suppressions and false suppressions: `0`;
- estimated avoidable tokens: `4,380`, explicitly counterfactual;
- USD estimate: unavailable because no first-party cost evidence was present.

See `benchmarks/results/compute_governor_phase1_closure.md`. This does not close
live-provider calibration by itself.

Current token-calibration evidence:

- paired usage deltas: `120` across all six deterministic task classes;
- calibration coverage: `100%`;
- avoidable-token mean absolute error: `0.0` on the controlled arithmetic set;
- provider execution preserved and enforced suppressions: `true` / `0`.

See `benchmarks/results/compute_governor_phase1_calibration.md`. This validates
receipt arithmetic and evidence handling; production calibration remains an
ongoing operational metric rather than a release blocker.

Current xAI live evidence:

- verified tasks and task classes: `24/24`;
- actual provider calls and receipts: `25/25`;
- receipt and first-party cost coverage: `100%`;
- observed tokens: `232,081`;
- candidate avoidable tokens: `33,017`, explicitly counterfactual;
- predicted savings: `$0.052213896`, explicitly counterfactual;
- retained-response cost lower bound: `$0.3589802`;
- enforced suppressions and false suppressions: `0`.

See `benchmarks/results/compute_governor_phase1_xai_live.md`.

Current free-provider live revalidation:

- providers: `groq`, `gemini`, `openrouter_gptoss`;
- successful provider calls and compute receipts: `9/9`;
- receipt coverage: `100%`;
- observed tokens: `1,385`;
- first-party observed cost coverage: `33.3333%`;
- candidate avoidable tokens: `415`, explicitly counterfactual;
- enforced suppressions and false suppressions: `0`;
- Phase 1 free-live gate: `PASS`.

See `benchmarks/results/compute_governor_free_live.md`. A failed Hugging Face
Router attempt returned `402 Payment Required` and is not part of the clean
free-provider pass.

## Phase 2: Deterministic Displacement

Goal: remove the safest deterministic work from model prompts and outputs.

~~Initial allowlist:~~

~~1. JSON and Action IR schema validation.~~
~~2. Provider alias and route normalization.~~
~~3. Exact in-memory patch compilation with syntax and rollback checks.~~
~~4. Test discovery and deterministic test selection.~~
~~5. File and handoff hash guards.~~
~~6. Secret detection and redaction.~~

Each displacement must run in paired shadow mode first. Enforcement requires equal
or better visible tests, hidden tests, scope checks, rollback behavior, and
security checks. Any verifier disagreement escalates to cloud inference.

**Current status:** Phase 2 transform execution and the narrow complete-task runtime branch are finished for rollout gate: locally evidenced and free-provider live-shadow revalidated.
- ~~Recognize eligibility only from a verified `DeterministicDisplacementProof`, never keyword candidates.~~
- ~~Implement callable adapters for all six allowlisted transforms.~~
- ~~Require explicit structured `deterministic_work`; prompt text cannot become executable input.~~
- ~~Record privacy-safe transform hashes, verifier checks, timing, calibration, and agreement in Compute receipts.~~
- ~~Execute adapters in paired shadow mode while preserving provider execution.~~
- ~~Fail closed on missing work, ambiguous anchors, invalid syntax, stale hashes, unknown routes, verifier disagreement, or calibration mismatch.~~
- ~~Wire a deterministic executor branch for exactly one verified, calibrated, explicitly complete task.~~
- ~~Bind enforcement output hashes to the promoted proof; request-supplied calibration cannot authorize bypass.~~
- ~~Preserve provider execution for partial transforms and every unproven or ambiguous result.~~
- ~~Verify 120 paired shadow attempts across all six classes with 100% transform verification, 100% calibrated agreement, and zero suppressions.~~

See `benchmarks/results/compute_governor_phase2_calibration.md`. Production
promotion remains evidence-driven: this local preflight does not claim displaced
live calls, and broad coding-flow displacement still requires transform-specific
live ablations and active Impact Fingerprints.

Current free-provider live-shadow revalidation:

- providers: `groq`, `gemini`, `openrouter_gptoss`;
- provider calls and compute receipts: `9/9`;
- deterministic shadow verification rate: `100%`;
- calibrated agreement rate: `100%`;
- provider path unchanged: `true`;
- enforced suppressions and false suppressions: `0`;
- Phase 2 free-live shadow gate: `PASS`.

See `benchmarks/results/compute_governor_free_live.md`. This closes Phase 2's
shared runtime shadow/executor gate. It still does not claim broad live-call
displacement; promoted production displacement remains governed by
transform-specific ablations and active Impact Fingerprints.

Current transform-specific live displacement evidence:

- provider: `groq`;
- candidate: `schema_validation`;
- live shadow provider calls: `1`;
- shadow transform verification/agreement: `true` / `true`;
- promoted proof: `proof_phase2_live_schema_validation`;
- active Impact Fingerprint at enforcement: `true`;
- enforced provider execution requested: `false`;
- displaced matching live calls: `1`;
- Phase 2 live displacement gate: `PASS`.

See `benchmarks/results/compute_governor_phase2_live_displacement.md`. This is
the first actual live-call displacement claim, scoped to one promoted
allowlisted transform under one active repository Impact Fingerprint. It does
not generalize to unpromoted transforms, changed repositories, stale
fingerprints, or broad coding-flow displacement.

## Phase 3: Verified Reuse

Goal: avoid recomputing outcomes already captured as local capabilities.

- Match task envelopes to Chronicle lessons and promoted capabilities.
- Require an active Impact Fingerprint before reuse.
- Replay deterministic verification before accepting a reused outcome.
- Fall back to escalation on stale hashes, low confidence, or verifier drift.
- Measure reuse hit rate, avoided calls, and false-reuse rate.

**Current status:** Phase 3 runtime reuse path implemented for explicit promoted capabilities; production evidence is still pending.
- `VerifiedReuseEngine` implemented with task-to-capability matching, Impact Fingerprint verification, all 5 safety checks required, ablation proof requirement, approval gate
- `compute_reuse_decision()` returns `reuse` | `escalate` | `cloud_inference`
- Reuse names remain advisory in `ComputeGovernor`; fabricated capability evidence has been removed
- `VerifiedReuseMetrics` tracks hit rate, avoided calls, false-reuse rate
- Current repository state is mandatory for standalone verification
- Runtime branch added in `Executor.execute()` through `InferenceComputeInterceptor` for `phase3_enforce` / `phase4_enforce`
- Reuse enforcement requires an explicit promoted capability source (`promoted_capabilities` / `verified_capabilities`) or persisted `data/promoted_capabilities.json`, active current repository state, complete safety checks, and deterministic replay with an expected output hash
- Capabilities can declare an `impact_boundary`; the interceptor automatically builds the current repository Impact Fingerprint at the reuse boundary when explicit `current_repo_state` is not supplied
- False-reuse observations are recorded when a reused result is later completed with `behavior_preserved=false`, and `VerifiedReuseMetrics` reports `false_reuse_count` / `false_reuse_rate`
- Reuse receipts are recorded with `provider_execution_requested=false` and `gate_decision=reuse`
- Missing: production-traffic false-reuse observations across promoted capabilities

## Phase 4: Adaptive Inference

Goal: spend probabilistic compute in proportion to unresolved uncertainty.

- Route bounded microtasks to local inference or low-cost provider roles.
- Apply Provider Economist decisions using role, fitness, latency, cost, and auth confidence.
- Enforce per-task cloud-call, token, latency, and USD budgets.
- Require approval before exceeding budgets or performing high-risk actions.
- Keep a more capable cloud route available as the ambiguity fallback.

**Current status:** Phase 4 routing controller is wired into the shared executor for approval/escalation/local-route decisions, with bounded Groq live-routing evidence.
- `AdaptiveInferenceController` implemented with:
  - `check_budget()` — validates cloud_calls, input/output tokens, latency, cost_usd (0/None treated as unlimited)
  - `route_adaptively()` — decision ladder: reuse/deterministic preserved → budget violation → high-risk → ambiguity escalate → economist routing → cloud default
  - `BudgetCheckResult` with `violations[]` and `requires_approval()`
  - `AdaptiveRoutingDecision` with `decision`, `route`, `economist_decision`, `ambiguity_fallback`
- `AdaptiveInferenceController.HIGH_RISK_CLASSES = {"destructive", "privileged", "costly", "high"}`
- `should_invoke_cloud_fallback()` and `requires_explicit_approval()` helpers
- Exposed through `ComputeGovernor.route_adaptively()` and called by `Executor.execute()` via the interceptor in `phase4_enforce`
- Budget and high-risk approval pauses now return `APPROVAL_REQUIRED` with a receipt instead of calling the provider
- Ambiguous gates in `phase4_enforce` return `COMPUTE_ESCALATED` with a receipt instead of calling the provider
- Local inference route selection invokes a dedicated `LocalModelAdapter` boundary and records `local_model_result` evidence in the route response
- Approval resume lifecycle supports an explicit `compute_approval.approved=true` bypass for the approval pause
- `ApprovalAuditStore` persists approval request/resume events as JSONL audit records
- Provider Economist (`provider_economist.py`) reused for role/economics/latency/auth scoring
- Groq Phase 4 benchmark evidence: `benchmarks/results/compute_governor_phase4_groq_routing.json` shows local adapter execution, approval pause/resume audit, and an approved live Groq provider route
- Missing: broad production traffic sample across real users/sessions and longer-lived approval audit retention policy

## Phase 5: Streaming Interception

Goal: stop paying for output after the governed action is complete or invalid.

- Incrementally parse JSON and Action IR during provider generation.
- Stop the upstream provider on a complete, schema-valid governed object.
- Stop and repair/escalate when the stream cannot become contract-valid.
- Detect repetition, explanation leakage, and output-budget exhaustion.
- Measure tokens saved against identical non-intercepted controls.

~~A 30-40% reduction is a research target, not a current claim. Success requires~~
~~equivalent patch, hidden-test, safety, and rollback outcomes.~~

**Current status:** Phase 5 stream interception engine, provider-stream adapter, cancellation hook, schema parser, repair lifecycle, token-savings measurement, opt-in executor integration, receipt/metric telemetry, and bounded Groq live evidence are implemented.
- `StreamingInterceptionEngine` implemented with:
  - `process_chunk()` — incremental parsing of streaming generation
  - `_extract_governed_object()` — JSONDecoder-based parser for complete nested JSON Action IR objects (`action`/`tool`/`patch`/`result`)
  - `_validate_against_contract()` — local JSON-schema subset validation (`type`, `required`, `properties`, `items`, `enum`, `const`, `anyOf`, `oneOf`, `allOf`, `additionalProperties=false`)
  - `_detect_repetition()` — 3-word phrase repeated 3+ times triggers stop
  - `_detect_explanation_leakage()` — markers like "here's how", "let me explain", "because" trigger stop
  - Budget exhaustion check against `max_output_tokens`
- `ProviderStreamAdapter` normalizes OpenAI-compatible and Anthropic-style streaming deltas
- `UpstreamCancellation` and adapter `cancel_upstream()` request cancellation and close async upstream streams when interception stops
- `repair_or_escalate()` records accept/repair/escalate lifecycle decisions for stopped streams
- `measure_tokens_saved()` records measured saved output tokens against provider completion-token baselines or the governed output budget
- `Executor.execute()` has an opt-in governed streaming lane (`stream=true`, `metadata.stream_interception_enabled=true`) that intercepts provider streams before non-streaming fallback
- Compute receipts record `early_stopped`, `stream_stop_reason`, `stream_tokens_saved`, `stream_repair_action`, and `upstream_cancel_requested`
- Compute metrics aggregate stream early stops, saved tokens, upstream cancellation count, and repair actions
- `StreamInterceptionResult` with `should_continue`, `should_stop`, `stop_reason`, `partial_object`, `schema_valid`
- `StreamingComputeInterceptor` high-level wrapper with sync `intercept_stream()`, async `intercept_provider_stream()`, and `estimate_tokens_saved()`
- Stop reasons: `governed_object_complete`, `governed_object_invalid_escalate`, `output_budget_exhausted`, `repetition_detected`, `explanation_leakage`
- Groq Phase 5 benchmark evidence: `benchmarks/results/compute_governor_phase5_groq_streaming.json` shows OpenAI-compatible SSE cancellation telemetry, live repair prompt execution, and measured token savings against a Groq baseline
- Missing: broader live stream samples across providers, error cases, and long-running production cancellation reliability

## Phase 6: Capability Crystallization

Goal: prove that repeated probabilistic lessons can become deterministic local
capability.

- ~~Implement repository Impact Fingerprint generation and comparison.~~
- Run candidate deterministic transforms in parallel shadow mode during Phases 1 and 2.
- Promote only after repeated hidden-test and rollback success.
- Attach Impact Fingerprints to every promoted capability.
- Check fingerprints at every promotion and reuse boundary.
- Automatically demote stale capabilities to `shadow_revalidation`.
- Track deterministic coverage, promotion precision, demotion rate, and compute displaced.

**Current status:** Phase 6 lifecycle engine, persisted state, runtime boundary checks, and bounded promotion-precision evidence are implemented.
- `CapabilityCrystallizationEngine` implemented with:
  - `register_shadow_run()` — tracks shadow validation (hidden/rollback/behavior preservation)
  - `check_promotion_eligibility()` — requires ≥3 runs, ≥95% success rates, ≥80% confidence, active fingerprint
  - `promote_candidate()` — creates `DeterministicDisplacementProof` with attached Impact Fingerprint
  - `check_fingerprint_at_boundary()` — compares fingerprints, auto-demotes on `shadow_revalidation`
  - `demote_candidate()` / `retire_candidate()` — status transitions with metric tracking
  - `CrystallizationMetrics` — coverage, precision, demotion rate, compute displaced (tokens + USD)
- Promotion thresholds configurable via `PROMOTION_THRESHOLD` dict
- Demotion triggers: stale fingerprint, confidence <50%, repeated behavior failures
- Promotion now fails closed without an Impact Fingerprint and emits Phase-2-compatible proof identities
- Lifecycle state persists/reloads through `capability_crystallization_state.json`
- Runtime boundary checks compare current Impact Fingerprints and automatically demote stale promoted capabilities to `demoted`
- Phase 6 benchmark evidence: `benchmarks/results/compute_governor_phase6_lifecycle.json` shows persisted reload, active boundary pass, stale boundary demotion, and observed promotion precision
- Missing: longer production promotion-precision samples across real promoted capabilities

## Phase 7: durable inference storage

~~There are several levels of “stored inference.”~~

~~1. Store the answer~~

~~This is normal caching.~~

~~same prompt~~
~~same model~~
~~same parameters~~
~~→ return cached response~~

~~Useful, but brittle and boring.~~

~~2. Store the semantic result~~

~~This is more BEAST-like.~~

~~task envelope~~
~~repository state~~
~~tests~~
~~evidence packet~~
~~verified patch~~
~~chronicle lesson~~
~~impact fingerprint~~
~~→ reused as a capability~~

**Current status:** Phase 7 storage, runtime replay, KV adapter payload transport, and bounded Groq measured reuse evidence are implemented.
- `DurableInferenceStorage` implemented with three storage tiers:
  - `store_answer()` — normal caching (prompt_hash + model + parameters → cached response), confidence 0.50 (brittle)
  - `store_semantic_result()` — BEAST-like (task envelope + repo fingerprint + verified tests + evidence + chronicle + Impact Fingerprint), confidence ≥0.60, `artifact_type="verified_capability"`
  - `store_prefill()` — engine-level KV prefill (model + tokenizer + prompt_prefix + system_prompt), `artifact_type="kv_prefill"`
- `SemanticComputeCredit` is the core abstraction: verified reusable artifact with `avoided_tokens_estimate`, `confidence`, `reuse_state`, `impact_fingerprint_hash`, `chronicle_lesson_id`
- `StoredInferenceValue` implements the three-currency model: `live_compute`, `stored_compute`, `crystallized_compute`
- `lookup_reusable_credit()` finds highest-confidence active match by task_class + repo_fingerprint
- `record_credit_reuse()` / `mark_stale()` / `retire_credit()` manage lifecycle
- `compute_stored_inference_value()` aggregates all tiers for reporting
- Persistence now reloads valid credits, reports corrupt records, redacts secret metadata, and writes atomically
- Verified capability lookup requires visible/hidden evidence, an Impact Fingerprint, and exact repository identity
- Complete answer retrieval returns full cached answers by exact prompt/model/parameter identity and records reuse
- Shared runtime lookup/replay selects reusable semantic credits, exact cached answers, or exact prefill identities through `runtime_lookup_replay()` / `replay_credit()`
- Measured reuse savings can be attached to credit reuse and are reported in storage metrics
- Engine-native KV tensor payloads can be registered, imported, exported, persisted to storage, and advertised in network manifests
- `Executor.execute()` has an opt-in durable replay branch (`metadata.durable_inference_replay_enabled=true`) for cached answer and prefill replay before provider admission
- `LocalKVEngineAdapter` provides a live adapter boundary over CPU KV transport with engine-native payload round trip, storage persistence, and network manifest generation
- Phase 7 benchmark evidence: `benchmarks/results/compute_governor_phase7_runtime_reuse.json` uses a Groq baseline to measure replay savings, then replays cached answer/prefill without another provider call
- Missing: production measured reuse savings over broad real traffic and direct vLLM/SGLang server adapters

This survives better than response caching because you are not trusting text. You are trusting verified behavior under a fingerprint.

3. Store the prefill / KV cache

This is the engine-level version.

same model
same tokenizer
same prompt prefix
same system prompt / repo context
→ reuse the expensive prefill computation

vLLM’s prefix caching, for example, caches KV blocks from processed requests and reuses them for later requests with the same prefix.

This can be powerful for BEAST because your handoff packets have repeated structure:

system policy
Action IR schema
output contract
provider role instructions
repo rules
verification contract

Those could become prefix-cache-friendly governance headers.

4. Store KV caches across engines

This is where it gets very close to your “inference storage” idea. LMCache, for example, is an open-source KV cache layer that stores and shares KV caches across vLLM and SGLang engines, with control APIs for pinning, lookup, cleanup, movement, and compression across GPU, CPU, storage, and network layers.

That is basically:

computed attention state becomes a transportable resource

Not exactly currency, but it starts looking like a compute asset.

CPU-based inference generator: yes, but redefine what it generates

A CPU is usually too slow to be a great token factory for big LLMs. But it can be an excellent inference-preparation engine.

Instead of asking a CPU to generate long answers, BEAST could make CPUs generate:

AST maps
symbol graphs
test-impact maps
route cards
provider handoff packets
semantic chunks
deduped context
secret scans
policy checks
capability fingerprints
deterministic patch candidates
local scout summaries

That is not “token generation.” It is probabilistic-work displacement.

The CPU becomes a little mill that grinds messy repo material into inference-ready flour. 🌾⚙️

The idea I think you are circling

I would call it:

Stored Inference Value

or more technically:

Semantic Compute Credit

A unit of stored inference value is not “one token.” It is a verified reusable artifact that reduces future uncertainty.

Example:

{
  "artifact_type": "verified_capability",
  "task_class": "provider_id_parser",
  "repo_fingerprint": "...",
  "policy_version": "...",
  "verified_tests": ["visible", "hidden"],
  "avoided_tokens_estimate": 3600,
  "confidence": 0.92,
  "reuse_state": "active"
}

That object has value because it can prevent a future provider call.

This is different from GPU marketplaces

A GPU marketplace says:

I have compute.
Pay me to use it.

Your idea says:

I have already spent compute.
I preserved the verified useful part.
Future work can reuse it safely.

That is a temporal inversion of inference economics. 🟢🧪

Instead of compute as a live commodity only, BEAST treats verified inference residue as an asset.

The BEAST version could have three “currencies”
1. Live Compute
GPU/CPU seconds
provider tokens
latency budget
USD budget

This is normal compute economics.

2. Stored Compute
KV cache
prefix cache
embeddings
repo summaries
test-impact maps
route cards
verified handoff packets

This is reusable preparation.

3. Crystallized Compute
promoted capability
deterministic transform
Impact Fingerprint
hidden-test evidence
rollback-safe proof

This is the highest-value form, because it can safely displace future inference.

Where Jetson / edge boxes fit

A Jetson, RTX box, or even a CPU-only Ollama node could participate in BEAST as a Compute Forge Node:

idle machine
→ watches repo
→ builds fingerprints
→ runs cheap local inference
→ updates vector/AST/test maps
→ performs secret scans
→ runs deterministic verifiers
→ prepares handoff packets
→ earns internal BEAST compute credits

The “credit” does not need to be crypto. It can be internal:

this node displaced 41,000 future tokens
this node produced 12 verified capability candidates
this node reduced handoff size by 62%
this node caught 3 stale fingerprints

That becomes a Compute Ledger.

The big architecture idea
BEAST Compute Governor
  ↓
Semantic Work Queue
  ↓
CPU / Jetson / Local GPU Forge Nodes
  ↓
Stored Inference Artifacts
  ↓
Impact Fingerprint + Verification
  ↓
Provider Economist
  ↓
Cloud inference only if uncertainty remains

This is not just batching. This is inference composting. Yesterday’s model work becomes tomorrow’s deterministic soil. 🟢🌱

The hard technical limits

There are real constraints.

KV caches are usually:

model-specific
tokenizer-specific
prompt-prefix-specific
precision-specific
often engine-specific
large in memory
sensitive to tiny prompt changes

So storing KV cache as a general reusable currency is difficult.

But storing semantic compute artifacts is much more robust:

repo graph
test graph
provider route card
verified diff
Action IR recipe
capability fingerprint
Chronicle lesson

That is why BEAST should not bet everything on KV cache. It should use KV cache when available, but treat verified semantic artifacts as the real durable currency.

The wacky idea, refined

Here is the clean version:

BEAST can transform inference from a disposable event into a governed asset by recording which parts of probabilistic work were reusable, verifiable, and safe to crystallize into local capability.

That is the paper sentence.

## Phase 7 Implementation: Compute Forge Nodes + Semantic Compute Credit

**Current status:** Phase 7 standalone prototypes implemented; the architecture flow below is a target, not the active runtime.

### Semantic Compute Credit Storage (`durable_inference_storage.py`)
- `SemanticComputeCredit` — verified reusable artifact with `avoided_tokens_estimate`, `confidence`, `reuse_state`, `impact_fingerprint_hash`, `chronicle_lesson_id`
- `store_answer()` — stores response metadata, but complete runtime cache retrieval is not wired
- `store_semantic_result()` — BEAST-like (task envelope + repo fingerprint + verified tests + evidence + chronicle + fingerprint), confidence ≥0.60
- `store_prefill()` — stores privacy-safe prefill identity and metadata, not engine tensors
- `lookup_reusable_credit()` — standalone exact-repository lookup for verified capabilities
- `lookup_answer()` — retrieves complete cached answers from sidecar payload files
- `runtime_lookup_replay()` / `replay_credit()` — shared runtime lookup/replay surface for semantic credits, cached answers, and prefill identities
- `StoredInferenceValue` — three-currency model: `live_compute`, `stored_compute`, `crystallized_compute`

### Cross-Engine KV Cache Transport (`kv_cache_transport.py`)
Implements a metadata/control-plane prototype inspired by the LMCache-style layer:

> "LMCache... stores and shares KV caches across vLLM and SGLang engines, with control APIs for pinning, lookup, cleanup, movement, and compression across GPU, CPU, storage, and network layers. That is basically: computed attention state becomes a transportable resource."

- `CrossEngineKVCacheTransport` with:
  - `register_block()` — register KV cache from any engine (vLLM, SGLang, Ollama, LM Studio)
  - `lookup()` — find reusable block by (model, tokenizer, prompt_prefix, system_prompt)
  - `pin()` / `unpin()` — prevent/allow eviction
  - `move()` — CPU/storage persistence and network manifests; no real GPU/RPC tensor transfer
  - `import_tensor_payload()` / `export_tensor_payload()` — exact engine-native tensor payload byte transport for registered blocks
  - `compress()` — reduce memory footprint (simulated quantization)
  - `cleanup()` — evict unpinned blocks when over `max_memory_bytes`
- `KVCacheBlock` — pinned, compressible, trackable cache entries with `prompt_prefix_hash`, `system_prompt_hash`, `precision`, `seq_len`, `size_bytes`
- `KVCacheTransportOperation` — audit log of all transport operations
- Respects KV cache constraints (model-specific, tokenizer-specific, prefix-specific, precision-specific, engine-specific)

### Compute Forge Nodes (`compute_forge.py`)
- `ComputeForgeNode` — idle machines as inference-preparation engines:
  - `watch_repo()` → builds Impact Fingerprints
  - `run_local_inference()` → earns semantic credits, tracks `total_tokens_displaced`
  - `update_test_impact_map()` → currently records requested map work
  - `perform_secret_scan()` → currently records scan work; scanner integration remains open
  - `run_deterministic_verifier()` → currently records verifier work; real verifier dispatch remains open
  - `prepare_handoff_packet()` → prepares provider handoffs, tracks `total_handoff_reduction_pct`
  - `catch_stale_fingerprint()` → detects stale fingerprints, tracks `stale_fingerprints_caught`
- `ForgeNodeProfile` — per-node metrics matching roadmap example:
  - `total_tokens_displaced` (e.g., 41,000)
  - `total_candidates_produced` (e.g., 12)
  - `total_handoff_reduction_pct` (e.g., 62%)
  - `stale_fingerprints_caught` (e.g., 3)
- `ComputeLedger` — aggregates forge node credits into system-wide totals

### Target Architecture Flow
```
BEAST Compute Governor
  ↓
Semantic Work Queue
  ↓
CPU / Jetson / Local GPU Forge Nodes
  ↓
Stored Inference Artifacts (Semantic Compute Credits + KV Cache Blocks)
  ↓
Impact Fingerprint + Verification
  ↓
Provider Economist
  ↓
Cloud inference only if uncertainty remains
```

This is inference composting. Yesterday's model work becomes tomorrow's deterministic soil. 🟢🌱

### Sacred Measurements (Implementation Coverage)
- ✅ verified outcome rate, including hidden tests
- ✅ cloud calls and tokens per verified outcome
- ✅ first-party USD per verified outcome
- ✅ avoided tokens estimate and observed cost coverage
- ✅ deterministic/reuse hit rate
- ✅ escalation, suppression, and approval rates
- ✅ false suppression rate (must remain zero)
- ✅ stale-capability detection and shadow-revalidation outcomes
- ✅ latency to first valid governed action
- ✅ behavior-preserving savings measured by paired ablation

### Claim Boundary
BEAST may currently claim that it observes compute demand, identifies candidate
deterministic/reusable work, records counterfactual savings, and fails safely on
ambiguous decisions and material repository drift. It may not yet claim that
those estimates are realized savings or that provider calls are being displaced
in production.

## Sacred Measurements

- verified outcome rate, including hidden tests;
- cloud calls and tokens per verified outcome;
- first-party USD per verified outcome;
- avoided tokens estimate and observed cost coverage;
- deterministic/reuse hit rate;
- escalation, suppression, and approval rates;
- false suppression rate, which must remain zero;
- stale-capability detection and shadow-revalidation outcomes;
- latency to first valid governed action;
- behavior-preserving savings measured by paired ablation.

## Claim Boundary

BEAST may currently claim that it observes compute demand, identifies candidate
deterministic/reusable work, records counterfactual savings, and fails safely on
ambiguous decisions and material repository drift. It may not yet claim that
those estimates are realized savings or that provider calls are being displaced
in production.
