# Physical Crystal Fabric — Compute Governor Spine (PREC integration)

Date: 2026-11-16. Sources of truth: `.beast/papers/econ.txt` (IEI v0.9), `.beast/papers/pgec.txt` (PGEC v1.0).

## Goal

One arbiter for the Reason phase of Perceive → Reason → Execute → Crystallize (PREC):
`ComputeGovernorSpine.admit(episode, proposal) -> GovernorDecision` with outcome
`admit | refuse | revalidate | escalate` (plus `defer` for budget/circuit exhaustion — see ruling).
Enforcement is default-off (`BEAST_GOVERNOR_ENFORCE`); in shadow mode every decision is still
computed, receipted and attached, but nothing is suppressed.

Paper anchors:
- IEI §4: the workflow puts the compute governor between provider handoff and provider/local route.
- IEI Table 3: "False suppression … Redline metric: must remain zero" → ambiguity escalates, never suppresses.
- IEI §3.4 cost-aware cascades; §7.12 / Table 15 bands (D9 router is a typed input, never a grant).
- IEI §7.12.1 / Table 14: similarity never grants execution; verifiers decide.
- IEI §7.13.1–7.13.3: credits settle from witnessed receipts and reverse on demotion.
- PGEC eq. 3 authority envelope, §2.4 promotion sovereignty, Appendix B (composition emerging).

## Survey (read-only, before edits)

| Input | Existing component | Finding |
|---|---|---|
| Gate | `governance/compute_governor.py::evaluate` | always `allowed=True` |
| L0 rules | `governance/reason.py` `_apply_meta_rules` (EdgeK IR only, request path) | not applied to tools/commands/crystals |
| Budget | D5 `RunBudgetTracker` (run), `BudgetLedger.daily_totals` (session), `ComputeBudget` (plan) | three disjoint budgets |
| Route | D9 `AdaptiveRouter` `RouteDecision` | proposal-only |
| Pathfinder | no module found | accepted as typed advisory dict |
| Lattice | `crystal_lattice_spine.CrystalLattice` | node/children status |
| MCP vault | `mcp/broker.py` allowed set | only checked on MCP path |
| Pressure | `psi_governor.PsiGovernor.decide` | can suppress lanes on its own |
| Circuits | `runtime.RuntimeGovernor.circuit_state` | provider circuits |
| Safety | `security/safety_governor.SafetyGovernor.classify_command` | classifier *and* executor gate in `routes/policy.py` execute-command |
| Task Envelope | `execution/task_envelope.TaskEnvelopeBuilder` | separate from D5 EpisodeEnvelope |
| Quality Cascade | `data_processing/quality_cascade.QualityCascade` | not required before cloud |
| L3 | `capability/skill_tree.SkillTree.promote_candidate` | sandbox validation only |
| L4/Chronicle | `ChronicleProjectionPublisher`, memory stack | no governor receipts |
| Evictions | `capsule_lifecycle_governor`, `prism_r5_workload_governor.evict_cold`, PSI | evict directly |
| Tool readiness | `registry/tool_integrations.py` | rtk/sqz forced `ready: true` even when binary absent |
| Economizer | `tests/test_context_economizer.py` | 3 failures vs. safer refuse behaviour |

## Decision order in `admit`

1. L0 hard rules on every path (safety `block`, MCP tool outside vault allowed set, unknown kind) → REFUSE.
2. Loop detection: L1 signature repeated ≥ threshold → REFUSE + negative evidence.
3. Ambiguity (explicit flag, structural/specialist band for a crystal) → ESCALATE (never refuse).
4. Lattice: composite with any non-admitted child or node → REFUSE; lattice unavailable → REVALIDATE.
5. Router/Pathfinder: crystal needs a valid D9 `crystal_replay`; specialist needs `local_specialist_adapter`; else REVALIDATE.
6. Safety classification: warn/require_approval without approval → ESCALATE.
7. Cost ladder crystal → local_specialist → deterministic_tool → cloud: cloud with an untried cheaper available rung → REVALIDATE.
8. Quality Cascade before cloud: missing → REVALIDATE; failed → ESCALATE; explicit skip with reason → OK.
9. Circuits: open circuit for the provider → DEFER.
10. Unified budget (D5 run + session ledger + ComputeBudget), shrunk by pressure factor ∈ (0,1]; exceeded → DEFER.
11. Otherwise ADMIT with rung, effective budget and a hash-chained receipt.

## Tasks

1. Plan + ledger (this file).
2. RED tests `tests/test_compute_governor_spine.py`: admit/refuse matrix, ambiguity never suppresses, pressure cannot deny alone, proposal cannot run without admit, failed lattice part refuses composite, budget exhaustion defers, Quality Cascade gates cloud, loop detection → negative evidence, false-suppression redline. Plus integrations.
3. GREEN `app/kernel/governance/governor_spine.py` + wiring: `ComputeGovernor.evaluate` (spine attached; allowed derived from admit only when enforced), execute-command behind admit, Task Envelope → D5 seal binding, D7 settlement requiring governor receipts (opt-in), Skill Tree promotion through D6 (enforced mode), L4/Chronicle receipt sinks, eviction dry-run via admit (capsule governor; PSI/PRISM wrapper).
4. RTK/sqz readiness fix; context-economizer tests updated to refuse semantics.
5. Verification: new + scoped suites, 84 planner tests, D5/D6/D7/D9/lattice, Ruff, `git diff --check`.

## Claim boundary

A typed, fail-closed admission arbiter with receipts. Default-off enforcement; shadow mode never
suppresses. No claim of realized savings (IEI §4 distinguishes counterfactual from realized).

## Addendum (2026-11-16 02:07–02:16): execution-path wiring, swarm specialist, RTK, memory contract, promotion evidence

6. Local specialist rung (`app/kernel/agents/swarm_specialist.py`, default-off `BEAST_SWARM_SPECIALIST`): a D9
   `local_specialist_adapter` proposal → `ComputeGovernorSpine.admit` (strict ADMIT, also in shadow) → native
   Ollama runner (`/api/generate`, qwen3 `think:false`) → Quality Cascade gate → Output Governor gate → verifiers.
   Any failure discards the output, records negative evidence and the provider path continues. Wired in
   `Executor._try_local_specialist` before `RuntimeGovernor.begin_execution`; bound as
   `SwarmKernelServices.specialist_runner`. `AdaptiveDispatcher` normalises the distiller's real lattice schema.
7. Quality Cascade → `evaluate()/admit()`: `QualityCascade.run` attests its report server-side
   (`.beast/governor/cascade_attestations.jsonl`, override `BEAST_CASCADE_ATTESTATIONS`); the interceptor maps
   request metadata through `cascade_admission_input` (client-claimed reports never count; operator skip only via
   server env `BEAST_QUALITY_CASCADE_SKIP`).
8. PSI: `RuntimeGovernor.begin_execution` never refuses on pressure alone; it returns `pressure_factor`
   (governor policy, 0.25–1.0) and the executor shrinks `max_tokens`.
9. RTK for cascade output (`app/kernel/data_processing/cascade_output_compressor.py`): real `rtk` when on PATH
   (`rtk pipe --filter pytest|ruff`, else `rtk log`), native stand-in otherwise; failing assertions, `file:line`
   locations, traceback frames and edit targets are re-appended byte-exact. sqz stays on Perceive transcript
   compaction. Install (not performed): `curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh`
   or `cargo install --git https://github.com/rtk-ai/rtk`; sqz: see its upstream README (not installed).
10. 4-tier memory contract (`app/kernel/governance/memory_contract.py`): cheapest-first reader
    (exact → schema → graph → local Chroma last; vector/schema/graph hits only nominate) feeding the Task Envelope
    and `Proposal.memory` (L0 refuses a nomination that claims a grant); verified-only writer to pages/crystals,
    graph/contracts, optional local embeddings (privacy filter, local sink only, remote Qdrant/pgvector/Chroma
    Cloud refused), L3 skills, L4 receipts, lattice composites.
11. Promotion receipts (`heldout_replay.ReplayReceipt`): `evidence_root = H(episode envelope digest,
    variant-results digest, reproduction-record digest)`; `structured` true only for typed (mapping) variants
    bound to an episode envelope. Applied centrally in `replay_candidate` (learn and reproduce paths).
