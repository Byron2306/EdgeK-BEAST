# BEAST Coding Agent Phase 0 Full-System Census Design

Date: 2026-09-17
Base branch: `agent/dai-diode-final-publication-closure`
Phase branch: `agent/beast-coding-agent-phase0-census`

## Purpose

Phase 0 establishes repository-wide truth before any coding-agent repair or integration work. The coding agent is treated as a vertical slice through BEAST rather than an isolated Pair Programmer feature. The census must identify which organs exist, what each organ claims to own, whether it is statically reachable, whether it is actually constructed and invoked at runtime, what authority it holds, what evidence it emits, and whether its responsibility overlaps another organ.

Phase 0 does not change coding-agent behavior. Known defects such as the local planner turn budget, frontend Action IR versus backend PlannerDecision protocol collision, tiny Ollama planner context/output budgets, three-file clipping, blind prompt truncation, and broken endurance CI remain recorded for later repair phases.

## Non-negotiable truth rule

A component is not `WIRED` merely because it exists, is imported, appears in a registry, has tests, is mentioned in documentation, generated a historical proof artifact, or is statically reachable.

`WIRED` requires evidence that a real production request reaches the component through the intended composition root, the component materially participates in that request, and the participation is observable through runtime evidence or an equivalent auditable trace.

Static facts and runtime facts therefore remain separate fields throughout the census.

## Census domains

The census covers the complete coding-agent-relevant organism, including:

1. interface and ingress: desktop IDE, Pair Programmer renderer, API routes, CLI and MCP surfaces;
2. agency and planning: AgentRun, planner runtime, model providers, task state machines, repair loops and SourcePlan;
3. perception and semantic understanding: Code Cortex, code indexers, Context Packet, Insight Compiler, incremental fingerprints and Sensorium inputs;
4. context and compression: AST compression, semantic pruning, chunk selection, context budgets and exact-source anchors;
5. memory and evidence: durable inference state, Evidence Chronicle, evidence bus/ledger/store/retrieval, outcome evidence, Sensorium episodes and forensic memory families;
6. compute and inference: ComputePlane, ComputeGovernor, interceptors, provider routing, local models, Forge, KV/prefix reuse and economics;
7. crystallisation and reusable authority: physical crystals, generative crystals, semantic reuse, lattices, promotion, held-out replay and Crystal Bus transport;
8. governance and authority: approvals, capabilities, policies, action contracts, gates and promotion authority;
9. execution: worktrees, source mutation, deterministic transforms, tool execution, isolation, rollback and remote execution;
10. verification and quality: Quality Cascade, tests, validators, failure analysis, SourcePlan, repair evidence and negative capabilities;
11. distributed intelligence: Commons, Forge scheduling, remote nodes, lattice/trust exchange and remote IDE machinery;
12. operations and supervision: composition roots, systemd/supervisors, health, telemetry, runtime reachability and evidence projection;
13. CI and proof: GitHub Actions, gauntlets, benchmarks, acceptance suites and supervised offline experiments.

The census may discover additional domains. Discovery expands the inventory rather than forcing a component into an incorrect category.

## Canonical component record

Every component record must support these fields:

- `path`
- `language`
- `layer`
- `imports`
- `runtime.constructed`
- `runtime.invoked`
- `runtime.evidence_producing`
- `authority`
- `disposition`
- `agent_relevance`
- `notes`

Later Phase 0 passes enrich records with composition root, inputs, outputs, persistence class, evidence contract, overlapping responsibilities, tests, failure modes, and final integration disposition.

Runtime fields begin as `unverified`. Static analysis may never promote them to `true`.

## Dispositions

The final census uses explicit dispositions rather than vague labels:

- `online_authoritative`: production participant and canonical owner of a responsibility;
- `online_supporting`: production participant supporting another authoritative owner;
- `supervised_offline`: non-request-path experiment or proof job whose signed evidence may affect promotion;
- `dormant_gated`: production-composed capability intentionally inactive until prerequisites are satisfied;
- `stranded`: meaningful capability with no valid production composition path;
- `duplicate_candidate`: materially overlapping responsibility requiring consolidation review;
- `compatibility_shim`: retained only for compatibility and not an authority source;
- `retired`: explicitly superseded and not part of the intended organism;
- `unclassified`: temporary Phase 0 state only.

`unclassified` is forbidden at the Phase 0 exit gate for any coding-agent-relevant component.

## Layer ownership rule

Phase 0 does not decide future architecture merely from names. It identifies the current owner and competing claimants. Phase 1 will assign one authoritative owner for each coding-agent responsibility.

Examples of responsibilities that require explicit ownership include repository discovery, semantic indexing, context selection, compression, working memory, episodic memory, evidence persistence, inference routing, interception, mutation authority, verification, repair, crystallisation and operator presentation.

## Automated static census

`scripts/beast_full_system_census.py` provides the first deterministic inventory pass. It:

- scans mixed Python, JavaScript, TypeScript, workflow/config and shell surfaces;
- excludes generated, virtual-environment, dependency and backup trees;
- assigns a first-pass functional layer from repository location;
- extracts Python and JS/TS import references;
- emits deterministic ordering and summary counts;
- marks all runtime and authority facts as `unverified`;
- emits JSON and Markdown forms.

Compression or summary output is never allowed to replace exact editable source anchors. The scanner itself does not modify source.

## Runtime census

Static inventory is necessary but insufficient. A later Phase 0 runtime pass must trace representative coding-agent journeys and bind observed participants to evidence:

- analysis-only request;
- simple single-file mutation;
- cross-file mutation;
- failed mutation followed by repair;
- verification failure;
- remote-workspace request where supported.

For each journey the trace records the composition root, planner/provider, retrieval/context organs, compute/interception organs, execution tools, verification organs, evidence writes, memory writes and human approval boundaries actually observed.

## Phase 0 outputs

The canonical outputs are:

- `docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json`
- `docs/BEAST_FULL_SYSTEM_CENSUS.md`
- `docs/BEAST_CODING_AGENT_RUNTIME_MAP.md`
- `docs/BEAST_CODING_AGENT_RECOVERY_MASTER_PLAN.md`
- scanner tests under `tests/`

The Markdown census may be generated from the JSON source of truth, but manually verified runtime findings must be represented in the JSON first so the two views cannot diverge.

## Exit gate

Phase 0 passes only when:

1. all coding-agent-relevant components are inventoried;
2. no relevant component has an unknown functional owner;
3. static reachability and runtime participation are represented separately;
4. representative coding-agent request paths are traced end to end;
5. every relevant component has a disposition;
6. overlaps and duplicate responsibility claims are explicitly listed;
7. existing evidence/proof-only machinery is distinguished from live enforcement;
8. the current coding-agent runtime path can be drawn from ingress to final receipt without speculative edges;
9. Phase 1 has a bounded list of ownership conflicts to resolve.

No Phase 3 behavioral repair is permitted to masquerade as Phase 0 census work.