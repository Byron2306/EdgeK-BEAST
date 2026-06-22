# Commons Swarm Update Set

## Purpose

This update set makes the existing BEAST swarm visible and starts converting its
local role activity into reusable, privacy-safe compute evidence. The goal is to
make inference, learning, and reuse observable across Swarm, OpenClaw/NemoClaw/
ZeroClaw, Ollama scout, Meta Tool Commons, and the promotion loop.

## Progress

- [x] Swarm state, governance, runs, and value logs are visible in the TUI.
- [x] OpenClaw treaty preview is visible from the TUI and diagnostics.
- [x] Ollama scout readiness is visible from the TUI and diagnostics.
- [x] Recent swarm runs convert into privacy-safe Commons evidence.
- [x] Repeated Commons Swarm priors stage local `skill_recipe` candidates.
- [x] Approved Swarm recipes promote into executable local skills.
- [x] OpenClaw execution outcomes feed back into Commons automatically.
- [x] Ollama scout confidence calibrates against verifier outcomes.
- [x] KV/cache reuse hits join the same evidence plane.
- [x] Unified reuse evidence plane rollup is available to API and TUI.
- [x] Mega-test full-channel smoke seeds Swarm, CLI/OpenClaw, Ollama, and KV evidence.
- [x] Compute Forge mines defensive model-agnostic crystals for tiny-model amplification.
- [x] Meta-tools, skills, swarm recipes, and crystals fuse into sealed compound inference crystals.

## Update 1: Swarm Becomes a TUI Surface

The swarm already exists in the backend as a deterministic, governed role
kernel. The TUI now needs to treat it as a first-class operational page instead
of an invisible backend detail.

Implemented first:

- fetch `/edgek/swarm/state`
- fetch `/edgek/swarm/governance`
- fetch `/edgek/swarm/runs`
- fetch `/edgek/swarm/value`
- add a dedicated `Swarm` page
- show profiles, role lanes, statuses, recent runs, value logs, and selected run
  detail
- add Mission and Intelligence summary cards for Swarm, OpenClaw, Ollama, and
  Swarm Commons evidence

## Update 2: OpenClaw Treaty Preview

OpenClaw, NemoClaw, ZeroClaw, and Hermes are now presented as a governance treaty:

- Hermes coordinates role briefs and plan shape.
- OpenClaw inspects and plans local-first work.
- ZeroClaw plans only and never executes tools.
- NemoClaw is the approval-gated execution lane.

The TUI snapshot now asks `/edgek/beast-cli/plan` for a local OpenClaw preview.
This gives operators a live view of readiness, action count, plan hash, and
governance posture without executing risky actions.

## Update 3: Ollama Scout Readiness

Ollama is part of the local reasoning economy, so the TUI now fetches
`/edgek/ollama/status` and displays:

- server readiness
- default scout model
- local model count
- whether local inference is available before cloud escalation

This keeps Ollama in the same mental model as Swarm and OpenClaw: local-first
reasoning, calibrated by verification and Commons evidence over time.

## Update 4: Commons Swarm Evidence

The first evidence bridge converts recent local swarm runs into Commons evidence
without leaking objectives, prompts, paths, or source code.

For each role/action in a swarm plan, BEAST emits a capability envelope shaped
like:

- capability: `swarm:{profile}:{role}:{action}`
- kind: `skill`
- task class: swarm task type
- role: swarm role lane
- outcome: verified/useful/safe/rescued/hidden-clean booleans
- economics: token/cost placeholders when the run value model provides them

The endpoint is:

- `POST /edgek/meta-tool-commons/swarm-ingest`

This lets the Commons learn that certain role-lane sequences are useful for
certain task classes while local policy still decides adoption.

## Update 5: Diagnostics Wide Sweep

Diagnostics now includes explicit rows for:

- Swarm kernel
- OpenClaw preview
- Ollama scout

Opening these rows uses the relevant endpoint instead of falling through to a
generic quality cascade. This should make failures legible: endpoint offline,
plan blocked, Ollama unavailable, or Commons evidence not yet prepared.

## Why This Is Radical

The important shift is that a swarm run is no longer just an orchestration trace.
It becomes a reusable compute artifact.

BEAST can now begin learning from:

- which roles were activated
- which profiles were safe enough
- which local scout signals were available
- which actions were suppressed or allowed
- which runs produced value logs
- which role/action patterns become Commons priors

That moves inference from disposable answer generation toward crystallized
operational memory. Local reasoning, avoided provider calls, gated execution,
and successful role plans become evidence that future runs can reuse.

## Next Slice

The current implementation layer is binding this evidence to the promotion loop:

- repeated safe role-lane evidence is grouped by `swarm:{profile}:{role}:{action}`
- groups above the local sample threshold become schema-pinned `skill_recipe`
  candidates
- candidates stay approval-gated under Meta Tool Commons local policy
- the TUI shows staged Swarm recipes beside recent runs and value logs

Remaining next steps:

- annotate generated meta-tools with their source swarm profile
- feed KV/cache transport stats and adapter receipts into Commons evidence
- use the evidence-plane rollup as a mega-test assertion surface

## Update 6: Reuse Evidence Plane Rollup

The individual bridges now feed a single aggregate plane:

- Swarm role evidence
- OpenClaw/CLI execution evidence
- Ollama scout calibration evidence
- KV/cache transport reuse evidence

The endpoint is:

- `GET /edgek/meta-tool-commons/evidence-plane`

It returns aggregate counts, verification/usefulness/safety rates, token/cost
totals, candidate/adoption summaries, and an integrity hash. It does not expose
prompts, source code, file paths, raw objectives, or secret-bearing payloads.

The TUI now surfaces this rollup in Mission, Intelligence, Swarm, and
Diagnostics. The Swarm page includes a per-plane table so the operator can see
which reuse channels are actually populated.

## Update 7: Full-Channel Reuse Plane Smoke

The mega-test can now run an explicit local smoke that seeds all four reuse
evidence channels into a temporary Commons database before certification:

- Swarm role evidence from repeated local role/action traces
- OpenClaw/CLI execution evidence from dry-run plan receipts
- Ollama scout calibration evidence from scout/verifier agreement
- KV/cache transport evidence from cross-engine reuse stats

The flag is:

- `--reuse-plane-smoke`

This writes `reuse_evidence_plane_smoke.json`, certifies the resulting
`reuse_evidence_plane.json`, and records active-channel counts in
`acceptance_status`. The smoke is synthetic and local-only: it proves plumbing,
receipts, hashes, and privacy shape without pretending that live provider
displacement occurred.

## Update 8: Tiny Llama Crystal Amplification Forge

The Compute Forge now has a defensive crystal-mining layer for Jetson/CPU-style
nodes. A Forge node can mine bounded, model-agnostic cyber-defense crystals,
package them for a tiny local Llama-style model, and compare the resulting
system against a big-model reference lane.

The new benchmark is:

- `benchmarks/tiny_llama_crystal_amplification_gauntlet.py`

The current artifact is:

- `benchmarks/results/tiny_llama_crystal_amplification_gauntlet`

It produces:

- `crystals.json`
- `amplification_pack.json`
- `comparison.json`
- `amplification_report.json`
- `integrity_manifest.json`

The crystals are explicitly defensive only:

- secure code review
- input validation hardening
- secret redaction guard
- dependency manifest triage
- auth boundary audit
- incident timeline digest
- ZeroClaw no-execution investigation plan
- OpenClaw local-first patch plan

The core claim is intentionally precise: a tiny model does not become a frontier
base model, but a tiny model plus verified crystals, OpenClaw/ZeroClaw routing,
Meta Tool Commons ranking, and Compute Governor reuse can act like a much
stronger system inside covered defensive domains.

## Update 9: Sealed Crystal Fusion

Crystals can now fuse with meta-tools, skills, and Swarm recipes to create a
larger compound inference crystal. This is the direct implementation of
inference inversion:

- expensive reasoning is converted into verified crystals
- crystals bind to tool/skill recipes
- Swarm/OpenClaw/ZeroClaw provide orchestration structure
- Meta Tool Commons ranks and routes the fused capability
- Compute Governor only reuses it when fingerprints and verification gates match

The fused artifact is:

- `benchmarks/results/tiny_llama_crystal_amplification_gauntlet/fused_inference_crystal.json`

The current fused crystal combines:

- 8 defensive base crystals
- 3 meta-tools
- 2 skills
- 2 Swarm recipes

It produced 61 internal crystal-credit units and an estimated 13,004 displaced
tokens. The seal is crypto-agile and uses the NIST standardized names:

- ML-KEM-768 for key encapsulation metadata
- ML-DSA-65 for the signature

If liboqs is unavailable, BEAST falls back to a clearly marked local development
HMAC seal. The economic boundary is also explicit: this is an internal verified
compute credit, not a public monetary instrument or proof-of-waste token.

## Update 10: Commons Discovery Ingest

BEAST can now learn what to try even on nodes that never call a frontier model.
The new Commons discovery lane ingests only metadata from external catalogs and
retrieval systems:

- MCP tool catalogs
- governed plugin manifests
- retrieval/document summaries with structured capability claims
- skill manifests

This is not blind trust and it is not raw scraping storage. Discovery creates
schema-pinned hypotheses in Meta Tool Commons, then stages approval-gated
recipes that must pass local verification before they become useful crystals.
Raw document bodies, prompts, paths, and source payloads are not stored; the
plane keeps hashes, source type, trust level, schema pins, and aggregate counts.

New surfaces:

- `MetaToolCommons.ingest_discovery_sources(...)`
- `POST /edgek/meta-tool-commons/discovery-ingest`
- MCP `beast_meta_tool_commons` action: `discovery_ingest`
- Evidence plane bucket: `discovery`

This gives the tiny/local model a bootstrapping route: it can discover tool
shapes and orchestration recipes from Commons, MCPs, plugins, and retrieval, but
only crystallizes them into high-value reusable inference after safe local
execution evidence exists.

## Update 11: Capability Registry to Open MCP Commons Bridge

The Capability Registry now feeds Meta Tool Commons directly. Registry inventory
is converted into Commons discovery sources so the static map of providers,
CLI commands, MCP tools, workflows, parsers, linters, databases, plugins, and
skills can become approval-gated Llama orchestration candidates.

The bridge also includes a conservative open-source MCP seed catalog covering:

- filesystem read/write shapes
- git status/diff shapes
- GitHub issue/PR/check metadata shapes
- SQLite/Postgres read-only shapes
- Playwright inspection shapes
- bounded fetch/docs retrieval
- MarkItDown-style document conversion
- memory/vector search
- LSP symbol search
- shell dry-run planning

New surfaces:

- `CapabilityRegistry.discovery_sources(...)`
- `CapabilityRegistry.open_source_mcp_seed_items()`
- `GET /edgek/capabilities/discovery-sources`
- `POST /edgek/capabilities/ingest-commons`

The current live bridge run produced:

- 112 new registry/open-MCP discovery evidence rows
- 112 new candidates staged and adopted
- 193 total Commons candidates adopted
- 691 total Commons evidence rows

The latest fused artifact is:

- `benchmarks/results/tiny_llama_crystal_amplification_gauntlet/llama_open_mcp_capability_registry_fusion.json`

That fusion combines:

- 8 defensive crystals
- 148 meta-tool bindings
- 214 skill components
- 20 Swarm recipes

It produced 1,380 internal crystal-credit units and an estimated 221,142
displaced tokens. The seal verified with the PQC crypto profile. The claim
boundary remains unchanged: tiny Llama is amplified by verified tool/skill
orchestration and crystals; its base model weights are not changed.

## Update 12: Agent Awareness Handshake for Tiny Llama

The missing link was agent awareness. The session handshake now tells a small
model that it is not a standalone model; it is the BEAST intent router, policy
follower, and compact summarizer operating over adopted Commons tools, skills,
Swarm recipes, and fused crystals.

The handshake now includes:

- Commons evidence/candidate/adoption counts
- evidence planes and safety/verification rates
- Capability Registry count, kinds, and top families
- active fused crystal ID, component counts, economics, and seal status
- a concrete Llama operating loop
- a tool request schema for capability-routed action
- hard bounds around approval, discovery-only MCP seeds, and privacy

The live awareness packet is:

- `benchmarks/results/tiny_llama_crystal_amplification_gauntlet/tiny_llama_agent_awareness_handshake.json`

Current live packet tells tiny Llama:

- 193 adopted Commons candidates
- 692 Commons evidence rows
- active crystal `fused_crystal_87369e5e59f914214393`
- 8 crystals, 148 meta-tools, 214 skill components, 20 Swarm recipes
- 1,380 crystal-credit units
- PQC seal verified

This is the prompt-side activation layer: the fused crystal existed before, but
now the local model is explicitly instructed how to use it through BEAST rather
than trying to behave like an unaided frontier model.

## Update 13: Tiny Llama Agentic Orchestrator Gauntlet

The new test asks the direct question: can a tiny non-reasoning local model act
as a useful reasoning/agentic orchestrator if reasoning is externalized into
BEAST?

The benchmark is:

- `benchmarks/tiny_llama_agentic_orchestrator_gauntlet.py`

It compares:

- raw tiny model lane: direct-answer behavior with no agent awareness
- BEAST-aware tiny lane: classify task, rank Commons, select route, apply risk
  gates, verify before success, and mark reusable patterns for promotion

The task set covers:

- provider route debugging
- safe refactor planning
- open MCP document retrieval
- KV/cache reuse routing
- unsafe shell request conversion into dry-run/approval
- defensive secure code review

Current artifact:

- `benchmarks/results/tiny_llama_agentic_orchestrator_gauntlet`

Current result:

- raw tiny average score: 0.133333
- BEAST-aware tiny average score: 1.0
- absolute gain: 0.866667
- pass rate: 100%

Boundary: this is an orchestration-contract benchmark, not proof that the base
model learned frontier reasoning. It shows that BEAST can make a tiny model act
as a policy head over externalized reasoning, tools, skills, crystals, and
verification gates.

## Update 14: Tiered Subagent Orchestration and Live Tiny Ollama

The agentic orchestrator gauntlet now has five tiers:

- Tier 1: single route selection
- Tier 2: multi-tool orchestration
- Tier 3: reuse-plane orchestration
- Tier 4: risk recovery and approval
- Tier 5: subagent swarm plus promotion loop

The required BEAST subagents are now scored explicitly:

- `zeroclaw_planner`
- `openclaw_inspector`
- `cartographer`
- `cache_router`
- `supervisor`
- `scribe`
- `promotion_scribe`

The live Ollama lane was run with the installed tiny model `qwen2.5:0.5b`.
The first raw live pass showed the expected weak-model behavior: the model
recognized and copied the required routes/subagents/gates, but drifted from the
requested output schema. BEAST now records a normalization layer that repairs
that weak JSON into the orchestration contract.

Current repaired live artifact:

- `benchmarks/results/tiny_llama_agentic_orchestrator_gauntlet_ollama_qwen25_05b_live_repaired`

Current repaired live result:

- live attempts: 6
- live passed: 6
- live pass rate: 100%
- live average score: 0.98

This is the practical answer to "how does a tiny non-reasoning model become
agentic?" It does not reason alone. It recognizes scaffolded task structure,
BEAST repairs schema drift, Commons ranks capabilities, subagents take roles,
and verification gates decide whether the route is allowed to matter.

## Update 15: Live E2E Tiny Orchestration Gauntlet

The final question was whether the tiny model merely chose labels or actually
ran a chained BEAST workflow. The new E2E gauntlet does the full chain:

- live tiny Ollama proposes an orchestration plan
- BEAST repairs weak-model schema drift
- Capability Registry inventory is queried
- Meta Tool Commons ranking is queried
- Swarm runs a real role/gate cycle
- OpenClaw-style CLI planning runs in dry-run mode
- focused local verification runs
- Commons stages a promotion candidate
- receipts and hashes are written

The benchmark is:

- `benchmarks/tiny_llama_live_e2e_orchestration_gauntlet.py`

Current live artifact:

- `benchmarks/results/tiny_llama_live_e2e_orchestration_gauntlet_qwen25_05b`

Current live result with `qwen2.5:0.5b`:

- live model attempted: true
- advanced tools selected: true
- subagents selected: true
- Swarm orchestrated or correctly approval-gated: true
- CLI plan ready: true
- verification passed: true
- promotion candidate staged: true
- no cloud model used: true
- live score: 1.0
- passed: true

Important nuance: the Swarm result hit an OpenClaw approval gate for medium-risk
work. That is counted as success because governed gating is the correct behavior;
an ungated write/execution path would be a failure.

## Update 16: Opus/Codex-style Case Study with Approval Gates

The newest case study makes the tiny local model face a harder, more realistic
workflow: an isolated synthetic provider gateway repo starts with five failing
tests across provider normalization, secret handling, beast-auto routing, async
stream collection, and recursive redaction.

The benchmark is:

- `benchmarks/tiny_llama_opus_case_study_gauntlet.py`

The flow is deliberately governed:

- live tiny Ollama proposes the orchestration plan
- BEAST repairs weak-model schema drift into the orchestration contract
- Capability Registry and Meta Tool Commons are queried
- Swarm runs before approval and correctly stops at an approval gate
- an explicit approval receipt is recorded for the isolated case repo
- BEAST applies a deterministic multi-file repair only after approval
- pytest verifies the repaired repo
- Swarm completes the approved lane
- Commons stages a promotion candidate with hashes and receipts

Current live artifact:

- `benchmarks/results/tiny_llama_opus_case_study_qwen25_05b`

Current live result with `qwen2.5:0.5b`:

- baseline failed: true
- baseline failing tests: 5
- verification after approved patch: 5 passed
- live score: 0.955
- gated before approval: true
- approval receipt present: true
- patch hash present: true
- promotion candidate staged: true
- no cloud model used: true
- passed: true

Boundary: the tiny model did not independently write a frontier-quality patch.
The radical part is the division of labor. The local model acts as a policy
head over BEAST's externalized reasoning, Commons, Capability Registry, Swarm,
approval gates, deterministic repair logic, verification loop, receipts, and
promotion machinery.
