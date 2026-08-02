# Corrected Swarm Architecture Implementation Plan

Status: Wider Phase 1-8 foundation implemented; live integrations remain explicit and receipt-bound
Owner: BEAST swarm runtime
Source: corrected swarm architecture supplied by the operator
Wider implementation source: operator-supplied Phase 1-8 specification

## Objective

Turn the swarm from a role sequencer into a governed, observable, local-first
repair pipeline. Hermes owns mission state, routing, and economics. Every later
role consumes typed evidence from the previous role, and every model call is
bounded by the interception and reuse plane.

## Canonical Flow

```text
Hermes
  -> Cartographer
  -> Baseline Verifier
  -> Failure Analyst
  -> Compressor
  -> Crystalist
  -> Patch Compiler
  -> Ollama Residual Solver
  -> Forge Executor
  -> Verifier
  -> Critic
  -> Scribe
  -> Archivist
```

The foreground path is authoritative. Distributed Forge nodes are asynchronous
preparation helpers and must not become foreground decision-makers.

## Shared Composition Root

Create one dependency container and inject narrow capability subsets into roles.
Do not instantiate all services inside individual roles or create new globals.

```python
class SwarmKernelServices:
    economist: ProviderEconomist
    dispatcher: AdaptiveDispatcher
    interceptor: InferenceComputeInterceptor
    context_economizer: ContextEconomizer
    compression_pipeline: CompressionPipeline
    ast_compressor: ASTCompressor
    workspace_graph: WorkspaceGraph
    semantic_raid: SemanticRaidStore
    fingerprint_engine: FingerprintEngine
    insight_compiler: InsightCompiler
    crystal_gateway: CrystalReuseGateway
    mission_lattice: MissionCrystalLattice
    skill_tree: SkillTree
    worktree_forge_factory: Callable
    evidence_ledger: EvidenceLedger
    evidence_bus: EvidenceBus
    policy_gate: PolicyGate
```

The container is a composition boundary, not a permission bypass. Services must
retain their existing approval, isolation, staleness, and evidence contracts.

## Role Contracts

### Hermes: mission governor

Use `ContextEconomizer`, `ProviderEconomist`, `InferenceCostPredictor`,
`CacheAwareEngineSelector`, `LocalRouteOptimizer`, and `AdaptiveDispatcher`.

Responsibilities:

- own mission state and route decisions;
- estimate cost, latency, local capacity, and route trust before inference;
- prefer deterministic crystal, local specialist, warm Ollama, then escalation;
- record rejected alternatives and reasons;
- never allow a later role to silently replace its route decision.

### Cartographer: repository intelligence

Use `WorkspaceGraph`, Code Cortex, `SemanticRaidStore`, `IncrementalFingerprint`,
and `ContextPacket`.

Responsibilities:

- select files and symbols from repository evidence, not caller filenames alone;
- produce repository, target, dependency, and selection fingerprints;
- persist the exact selected context packet for reconstruction;
- provide impact paths and supporting evidence to downstream roles.

### Baseline Verifier: establish real failure

Use `WorktreeForge`, worktree tools, `QualityCascade`, and `LocalComputeCascade`.

Responsibilities:

- run syntax, targeted tests, static checks, and broader checks in order;
- prove the pre-edit failure without mutating the main workspace;
- normalize command output into evidence references;
- report `workspace_mutated: false` for baseline execution.

### Failure Analyst: normalize diagnosis

Use `EvidenceRetriever`, `EvidenceStore`, `EvidenceLedger`, `EvidenceBus`,
`FingerprintEngine`, `EquivalenceEngine`, and `InsightCompiler`.

Responsibilities:

- create a stable task family and failure signature;
- retrieve and rank prior verified repairs;
- distinguish equivalent failures from merely similar text;
- emit confidence, target, operation family, and historical evidence refs.

### Compressor: exact tiny-model context

Use `ContextEconomizer`, `ToolLazinessLearner`, `ASTCompressor`,
`CompressionPipeline`, provider handoff preparation, `ContextTransferManifest`,
and `SemanticRaidStore`.

Responsibilities:

- keep only the target body, relevant signatures, failing assertion, and proof;
- remove unrelated tools, files, comments, literals, and duplicate context;
- report tokens before/after, reduction ratio, and discarded schemas;
- produce the exact residual model payload and its integrity manifest.

### Crystalist: reuse and interception

Use `InferenceComputeInterceptor`, `CrystalReuseGateway`, `LocalSemanticCache`,
`MissionCrystalLattice`, `CompatibilityEngine`, `CrystalStalenessPolicy`,
`CrystalRuntimeBoundary`, and KV/prefix-cache systems.

Responsibilities:

- classify advisory, scaffold, and execution matches separately;
- refuse execution on source, verifier, environment, or policy mismatch;
- distinguish semantic proof from KV acceleration;
- expose whether inference was avoided, warmed, restored, or permitted.

### Patch Compiler: bounded Action IR

Use `ActionIR`, `ActionResolver`, `SkillTree`, `SkillRegistry`,
`CapabilityRegistry`, `MetaToolGenerator`, `ToolBuckets`, `SequenceDetector`,
and `SandboxValidator`.

Responsibilities:

- construct a bounded action from verified target evidence;
- resolve known operation templates before using a model;
- leave only explicitly unresolved fields for residual inference;
- reject unbounded file selection, command generation, or approval claims.

### Ollama Residual Solver: one typed hole

Use `OllamaPlannerProvider` residual mode, `LocalExecutionGateway`,
`AdaptiveInference`, `InferenceEngineFabric`, `MemoryPolicy`, and verified
prefix/KV caches.

The solver receives no tool catalogue, file-selection authority, arbitrary
command capability, approval authority, or promotion authority. It receives one
typed unresolved field and must return structured JSON under deterministic
temperature/seed and bounded retry rules.

All model calls pass through `InferenceComputeInterceptor.begin()` and
`complete()`.

### Forge Executor: isolated mutation

Use `WorktreeForge`, agent tool runtime, least-authority tools, approval cards,
`ForgeIsolation`, `SecureMemory`, and `SecretVault`.

Responsibilities:

- consume fully compiled Action IR only;
- use one worktree, one file, one operation, one run, and one expiry;
- never ask Ollama which file to change after authority is issued;
- collect bounded diff and execution evidence.

### Verifier: prove or reject

Use `QualityCascade`, deterministic verifiers, hidden tests, effect hashing,
`CrystalVerifierSynthesis`, and context-restore verification where applicable.

Responsibilities:

- verify the isolated mutation in increasing cost order;
- compare expected and observed effects;
- produce fresh evidence, not recommendations;
- reject on missing, stale, or contradictory proof.

### Critic: policy and blast radius

Use `PolicyGate`, `SpecCovenant`, architecture decisions, evidence scoring,
`ControlGraph`, `PostApplyVerificationPromotionGate`, equivalence checks, and
secret scanning.

Responsibilities:

- verify authorized files and operation scope;
- detect command or secret smuggling;
- validate crystal applicability and fresh verification;
- check causal chain, provenance, and blast-radius expansion.

### Scribe: compile the episode

Use `RuntimeCrystallizer`, capability crystallization, crystal evidence bridges,
`CrystalCandidateAdapter`, `SkillTree`, `TraceMiner`, and `SequenceDetector`.

Classify outputs as advisory crystal, scaffold crystal, execution candidate,
skill candidate, meta-tool candidate, negative evidence, refusal pattern, or
repair pattern. Scribe may propose promotion; existing gates remain authoritative.

### Archivist: preserve causal evidence

Use `EvidenceLedger`, `EvidenceBus`, `EvidenceChronicle`, ForensicMemory,
MemoryStack/MemoryHull, `SemanticRaidStore`, `UnifiedEvidencePacket`, and
`ProofCarryingArtifact`.

Record each state transition distinctly: planned, started, tool invoked, tool
succeeded, model called, model responded, mutation applied, verification passed,
operator approved, capability promoted, capability reused, or reuse refused.

## KV and Background Forge Use

Compressor splits stable prefix from task residual. Crystalist may restore only
verified prefixes or KV blocks. KV reuse accelerates inference and is never proof
that a patch is correct.

Background Forge helpers may refresh fingerprints, AST summaries, symbol maps,
secret scans, stable Ollama prefixes, test-impact maps, crystal staleness,
verifier contracts, task-family packs, and promoted-skill indexes.

Meta Tool Commons is a capability directory for promoted tools, validated skills,
trusted crystal packs, verifier templates, specialist adapters, route penalties,
and known incompatibilities. Route damping must influence Hermes.

## Implementation Phases

### Phase A: inventory and composition root

- [x] Locate current swarm role constructors and composition paths.
- [x] Define typed `SwarmKernelServices` with optional adapters for unavailable services.
- [x] Bind existing production services without behavior changes.
- [x] Add dependency and capability inventory diagnostics.
- [x] Add unit tests proving role construction does not create hidden globals.

Phase A implementation is in `app/kernel/networking/swarm_services.py`. The
current composition root binds the safe, low-risk economist and compression
services plus the workspace graph. Heavy workspace-specific services remain
explicitly missing until the application composition root supplies them.

### Phase B: read-only intelligence

- [x] Operationalize Hermes route/economics output.
- [x] Add Cartographer graph/evidence selection output for coding missions.
- [x] Add Failure Analyst normalized diagnosis packets.
- [x] Add Compressor exact payload and reduction manifest.
- [x] Add Crystalist advisory/scaffold/execution classification.
- [x] Keep all Phase B roles read-only.

Phase B is implemented in the existing `SwarmKernel` pipeline. The role packets
are intentionally read-only and consume supplied evidence or explicitly bound
services. Crystalist may classify execution candidates but cannot authorize a
mutation; live interception and residual model execution begin in Phase C.

The wider Phase 1 contract is implemented in
`app/kernel/networking/swarm_contracts.py`. Every new role event carries a
validated `SwarmRoleResult` with status, input digest, outputs, evidence refs,
next-role routing, and model/tool/mutation counters. Execution claims without a
tool receipt are rejected before persistence.

The wider Phase 2 contract is implemented in
`app/kernel/networking/swarm_lifecycle.py`. `HermesLifecycle` deterministically
selects the legal next role and explicitly reports whether Ollama is allowed;
the legacy `SwarmState` remains available for API compatibility.

### Phase C: intercepted residual inference

- [x] Add Patch Compiler Action IR output and unresolved-field contract.
- [x] Add a residual boundary that wraps model calls with `InferenceComputeInterceptor`.
- [x] Add Ollama `solve_residual()` with deterministic structured output.
- [x] Add refusal and route telemetry to the residual result contract.
- [x] Add tests proving the residual path cannot authorize mutation.

Phase C is implemented in `app/kernel/agents/patch_compiler.py` and
`app/kernel/agents/residual_solver.py`. The boundary is opt-in from the
foreground swarm until a production interceptor and provider are explicitly
bound in `SwarmKernelServices`; no existing planner route is silently changed.

### Phase D: isolated execution and verification

- [x] Add Forge Executor fail-closed boundary for WorktreeForge-backed execution.
- [x] Issue one-use, one-worktree, one-file authority envelopes.
- [x] Add fresh mutation-epoch verification contract.
- [x] Add Critic scope, provenance, and blast-radius checks.
- [x] Reject incomplete, residual, or stale execution evidence.

Phase D is implemented in `app/kernel/agents/phase_d_execution.py`. The
coordinator is opt-in and requires an injected governed mutation runner; it does
not write to the workspace by itself. Existing `worktree_tools.py` remains the
authoritative mutation and verification implementation.

### Phase E: learning closure

- [x] Compile verified episodes with Scribe.
- [x] Emit skill and crystal candidates without bypassing promotion gates.
- [x] Archive causal evidence as a unified hashed packet.
- [x] Persist refusal and negative evidence classifications.

Phase E is implemented in `app/kernel/agents/phase_e_learning.py` and is now
part of the SwarmKernel Scribe/Archivist event path. Candidate generation is
active, but promotion remains explicitly unauthorized until the later evidence
and approval integration is supplied.

### Phase F: background Forge helpers

- [x] Add background repository fingerprint and secret-scan preparation.
- [x] Prepare handoff packets and test-impact maps asynchronously.
- [x] Add explicit background-only scheduler submission metadata.
- [x] Keep all background helpers mutation- and promotion-inert.

Phase F is implemented in `app/kernel/agents/background_forge.py`. It wraps the
existing `ComputeForgeNode` and `DistributedForgeScheduler` as a preparation
plane. KV/crystal staleness and skill-index jobs can be added as worker types,
but their results must continue to enter the foreground through receipts.

### Phase G: visible IDE proof

- [x] Show role contributions from the latest swarm run in the Agents page.
- [x] Show route, compression, interception, isolation, verification, and archive decisions.
- [x] Keep unavailable or unrun phases visibly distinct from passed phases.
- [x] Preserve live-only behavior and avoid demo data in the proof surface.

Phase G is implemented as the Agents-page `Swarm Proof` panel. It reads the
existing `/edgek/swarm/runs/{run_id}` detail route and renders role receipts and
packet hashes without inventing missing evidence. The tiny-Ollama demonstration
remains an operator-triggered integration exercise rather than an automatic
boot action.

## Wider Phase 1-8 Exit Mapping

The operator-supplied wider implementation maps onto the current modules as
follows:

- [x] Phase 1 typed role result, evidence, and receipt contract.
- [x] Phase 2 deterministic Hermes lifecycle and Ollama boundary decision.
- [x] Phase 3-4 bounded Cartographer and failure-analysis seams with live
  service injection when supplied.
- [x] Phase 5 exact Compressor payload and reduction manifest.
- [x] Phase 6 Crystalist assistance classification and interception boundary.
- [x] Phase 7 Patch Compiler Action IR with explicit unresolved fields.
- [x] Phase 8 residual solver with deterministic structured output and bounded
  model budget.

The wider exit criteria are intentionally split: contract-level behavior is
covered by unit tests, while repository-specific invoice fixtures, live
WorktreeForge mutation, and production Ollama closure require explicit runtime
services and receipts. They are not reported as completed by default.

## Invoice Closure Milestone

The first live-style closure is implemented in
`app/kernel/networking/invoice_closure.py` and covered by
`tests/test_invoice_closure.py`. It builds the four-file invoice fixture,
indexes it with `WorkspaceGraph`, selects `pricing.py` and `invoice.py`, proves
the baseline failure as
`pytest:percentage_discount:subtracts_percent_as_value`, compiles a bounded
Action IR, routes one residual through the interception boundary, applies one
approved isolated mutation, runs fresh pytest verification, performs critic
review, and archives the causal packet. The residual boundary also records the
exact serialized model packet and digest sent to the injected provider.

## Cross-Cutting Acceptance Criteria

- No role may claim work it did not perform.
- No model call may bypass the interception boundary.
- No mutation may occur outside an isolated worktree and approved Action IR.
- Approximate semantic or crystal matches cannot authorize execution.
- Every important transition has a durable evidence reference.
- The UI distinguishes unavailable, pending, advisory, verified, refused, and passed.
- Existing local-first, approval, secret, and provenance boundaries remain intact.

## Golden Path Expansion Overlay

The operator-supplied minimal visible golden-path document adds a stricter
execution order to this architecture plan. It is not a replacement for the
role architecture; it is the acceptance ladder that must be passed before
reintroducing wider infrastructure.

### Covered By Current Implementation

- [x] One bounded invoice mission with one failing baseline and one passing
  verifier.
- [x] Hard-coded foreground sequencing; Ollama receives only residual content.
- [x] Isolated worktree mutation, fresh verification, critic review, and
  causal archive receipt.
- [x] Deterministic Hermes lifecycle contract and bounded residual provider
  mode.
- [x] Visible Agents-page proof surface for route, interception, isolation,
  verification, and archive states.

### Newly Added Gates

- [x] Dedicated visible golden-path timeline with explicit Forge contributions
  before the model call.
- [x] Reusable `tiny_model_conductor.py` exposing only the next legal action.
- [x] `crystal_assistance_compiler.py` with broad assistance and strict
  execution-applicability keys.
- [x] Live `ComputeForge.prepare_agent_assistance()` bridge with deterministic
  per-node receipts.
- [x] Explicit model contribution accounting, including BEAST-supplied versus
  Ollama-supplied Action IR fields.
- [x] Advisory, scaffolded, and deterministic crystal operating modes with
  zero-call reuse proof.
- [x] Verification-driven repair loop capped at three rounds, one file, and
  one symbol.
- [x] Verified diff to SourcePlan to operator approval integration.
- [x] Immediate crystal strengthening and same-process reuse proof.
- [ ] Six-family coding suite and per-family false-reuse metrics.
- [ ] Ordered reintroduction of direct Ollama, LiteLLM, proxying, provider
  routing, distributed Forge, and cross-host crystals.

The next milestone is therefore the visible hard-coded golden-path timeline,
not additional provider infrastructure. The invoice closure remains the
canonical fixture and must pass unchanged after each subsequent integration.

The visible golden path is now implemented through the operator-triggered
`POST /edgek/swarm/golden-path` endpoint and the Agents-page `Run Golden Path`
action. It is backed by `TinyModelConductor` and renders repository inspection,
worktree binding, expected baseline failure, bounded residual request, isolated
mutation plus fresh verification, diff review, and archive completion with
stage evidence. It does not run during boot or seed demo telemetry.

The golden path is an execution-spine proof, not yet a model-uplift proof. The
default closure uses a deterministic injected provider so governance regressions
are reproducible. Live Ollama is opt-in and the UI labels `deterministic_test_provider`,
`live_ollama`, or unavailable model evidence explicitly. Model improvement is
not claimed until live runs are compared against a baseline for valid residual
response, verified completion, repair rounds, latency, and token budget.

## First Implementation Target

The implementation began with the narrow `SwarmKernelServices` composition
root, then added the typed role and Hermes lifecycle contracts before enabling
the opt-in residual and Forge boundaries. This ordering keeps ownership and
test seams explicit while preserving local-first and fail-closed defaults.
