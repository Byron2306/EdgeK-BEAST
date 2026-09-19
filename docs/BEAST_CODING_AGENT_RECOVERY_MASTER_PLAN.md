# BEAST Coding Agent Recovery Master Plan

Date: 2026-09-17
Status: **Phase 7 COMPLETE — Phase 8 ready**
Working branch: `agent/beast-coding-agent-phase7-compute-reuse-crystallisation`
Base: `agent/dai-diode-final-publication-closure` @ `97867af340dc847ef9556ec3995b0e1ad20a0392`

## Programme objective

Make the BEAST coding agent a coherent vertical slice through the existing organism rather than a thin LLM wrapper. Existing BEAST organs for perception, semantic indexing, context construction, compression, compute routing, interception, memory, evidence, Sensorium, execution, quality, crystals/lattices, distributed operation and governance must be inventoried before deciding what to wire or consolidate.

The programme does not assume that every existing organ belongs in the live coding path. Each component must earn a disposition based on responsibility, production ownership and evidence.

## Phase sequence

| Phase | Objective | Exit condition |
|---|---|---|
| **0. Full Organism Census** | Establish repository and runtime truth across all coding-agent-relevant BEAST layers. | Complete canonical census, observed runtime map, explicit dispositions and overlap list. |
| **1. Responsibility & Authority Map** | Assign one authoritative owner for each cognitive/operational responsibility and classify support/duplicates. | No unresolved competing authority for repository discovery, context, memory, routing, mutation, verification, evidence or reuse. |
| **2. Current Agent Trace** | Measure real request paths across analysis, edits, repair and remote operation. | Every observed edge is evidence-backed; speculative edges are separate. |
| **3. Agent Core Repair** | Repair known deterministic planner/integration defects. | Simple governed local-model mutation completes reliably with truthful telemetry. |
| **4. Perception & Repository Intelligence** | Integrate repository indexing, Code Cortex and Sensorium-derived world state into task discovery. | Cross-file tasks discover relevant evidence without manual three-file attachment dependence. |
| **5. Context Architecture** | Establish canonical Context Packet and evidence-preserving compression. | Context remains task-relevant under pressure while exact editable anchors remain authoritative. |
| **6. Memory Architecture** | Assign explicit roles to working, episodic, durable, evidence and forensic memory families. | One documented promotion/read path with no competing authoritative memory stores. |
| **7. Compute, Reuse & Crystallisation** | Route tasks through BEAST compute/reuse machinery and use verified crystals/lattices where appropriate. | Requests can choose deterministic reuse, local inference or stronger provider routes based on evidence. |
| **8. Governed Execution** | Consolidate mutation authority, worktrees, isolation, rollback and approvals. | Every mutation has source, authority, diff, verification and rollback lineage. |
| **9. Verification, Repair & Learning** | Integrate Quality Cascade, failure analysis, negative evidence and promotion. | Injected failures are detected, repaired or refused, and recorded without unsupported completion claims. |
| **10. Distributed BEAST** | Extend the same cognitive/governance contracts to Commons, Forge and remote workspaces. | Local and remote coding requests share one semantic and authority model. |
| **11. Operator Surface Unification** | Make backend state legible in the Pair Programmer/IDE. | UI reflects actual planner phase, evidence, route, verification and human gates. |
| **12. Agent Gauntlet & Promotion** | Measure integrated BEAST against baseline across controlled coding tasks. | Evidence-backed promotion decision across simple, cross-file, repair, large-repo and remote tasks. |

## Phase 0 rules

1. No coding-agent behavioral repairs are mixed into census work.
2. File presence, imports, registries, tests, documentation and historical proof artifacts do not prove live wiring.
3. Runtime construction/invocation/authority begins `unverified` and requires runtime evidence to change.
4. Existing offline or supervised scientific machinery remains distinct from production request-path enforcement.
5. Existing exact-source boundaries are preserved; compressed context never becomes mutation authority.

## Phase 0 census domains

The census covers interface/ingress, agency/planning, perception/Sensorium, semantic understanding, context/compression, memory/evidence, compute/inference, interception, crystals/lattices/reuse, governance/authority, execution/worktrees, verification/Quality Cascade, distributed Commons/Forge, operations/supervision, CI/proof and operator presentation.

Additional domains discovered during scanning are added rather than forced into the wrong bucket.

## Already verified inputs to later phases

These findings are recorded as later-phase defects and are **not repaired during Phase 0**:

- Local mutating AgentRun defaults to a planner turn budget that is shorter than the clean mandatory lifecycle it enforces.
- Frontend mutating prompts demand BEAST Action IR while the backend typed planner demands a distinct PlannerDecision protocol.
- Actual Ollama planner context/output defaults are much smaller than the renderer telemetry suggests, including a hard-coded smaller native-context generation path.
- Frontend/planner context can be clipped to three files before backend retrieval has a chance to reason across the repository.
- Compact planner prompt handling uses prefix truncation, risking loss of late observations/authority/repair evidence.
- The current Agentic Loop Endurance workflow can fail during test import because its dependency install is incomplete, so its red status does not necessarily mean the planner tests themselves ran.

## Phase 0 current checkpoint

Implemented on the Phase 0 branch:

- approved Phase 0 design spec;
- detailed implementation plan;
- deterministic mixed-language census scanner;
- test-first scanner contract covering Python, JavaScript and workflow discovery;
- explicit `unverified` runtime/authority defaults;
- ignore rules preventing backup, dependency, build and virtual-environment trees from polluting the census.

The scanner is only the first static pass. Phase 0 remains open until the real repository inventory is generated inside the BEAST checkout, existing module disposition evidence is overlaid, representative coding-agent journeys are traced, and responsibility overlaps are classified.

## Canonical Phase 0 outputs

- `docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json`
- `docs/BEAST_FULL_SYSTEM_CENSUS.md`
- `docs/BEAST_CODING_AGENT_RUNTIME_MAP.md`
- this master plan
- census and runtime-trace tests

## Phase 0 exit gate

Phase 0 closes only when every coding-agent-relevant component has an explicit disposition; static and runtime truth are separate; observed request paths can be reconstructed end to end; duplicate responsibility claims are explicit; proof-only/offline systems cannot be mistaken for enforcement; and Phase 1 receives a finite list of ownership conflicts instead of architectural guesswork.

## Phase 5 completion checkpoint

Phase 5 establishes one canonical planner context contract and closes the authority gap between repository discovery, compressed/model-visible context, and editable source evidence.

Implemented:

- `app/kernel/agents/context_architecture.py` defines the canonical `beast_agent_context_packet`.
- Repository discovery is explicitly advisory and cannot grant mutation authority.
- Only completed `workspace.read_range` observations may enter the exact-source authority lane.
- Deterministic compaction sheds advisory detail before exact-source evidence and preserves hashes/authority labels when source text must be omitted for budget.
- The planner runtime now renders this canonical packet directly instead of maintaining a second repository-discovery prompt projection.
- Compact planner bounding preserves both the contract head and late authority/repair evidence rather than prefix-truncating the newest evidence.
- Recovery tests cover exact-source admission, evidence-preserving compaction and deterministic packet digests.

### Phase 5 exit gate

**COMPLETE in repository implementation.** The architecture now has a single context authority contract: context may be compressed for relevance and local-model pressure, but compression never upgrades authority, and editable anchors remain rooted in exact `workspace.read_range` evidence.

The next programme phase is **Phase 6 — Memory Architecture**. It must preserve this boundary: working, episodic, durable, evidence and forensic memory may inform planning, but memory content cannot silently become exact-source or mutation authority.


## Phase 6 implementation checkpoint

Phase 6 starts by making the coding agent's memory families explicit instead of allowing every persistent store to behave like an interchangeable source of truth.

Canonical roles:

| Memory role | Canonical owner | Coding-agent purpose | Authority |
|---|---|---|---|
| Working | AgentRun state/checkpoint | Current plan, recent observations and repair continuity | advisory continuity only |
| Episodic | Memory Hull / Chronicle | Prior task decisions, outcomes, route cards and residue | advisory prior experience only |
| Durable | Workspace Graph / Skill Tree | Rebuildable project knowledge and explicitly promoted reusable patterns | advisory retrieval only |
| Evidence | Evidence Bus | Pointers/receipts that resolve to authoritative evidence | reference only |
| Forensic | L4 Forensic Archive | Append-only attempts, failures, checks and interception history | audit only |

Implemented in `app/kernel/agents/memory_architecture.py`:

- one machine-readable ownership and authority contract for all five memory families;
- bounded per-role retrieval projection for planner use;
- explicit prohibition on memory silently becoming exact-source, mutation, verification or promotion authority;
- deterministic digests for the contract and projected memory context;
- Phase 6 tests proving ownership, boundedness and non-escalation of authority.

### Phase 6 closure

Repository implementation is complete.

- `AgentMemoryRuntime` now reads the existing Memory Hull, Workspace Graph, Skill Tree, Evidence Bus and L4 Forensic Memory and projects them through one bounded Phase 6 context.
- The planner consumes that projection on every turn alongside the Phase 5 Context Packet.
- Working memory is rebuilt from durable planner observations on resume rather than copied into a competing store.
- Evidence Bus pointers can be resolved to a workspace-contained artifact and checked against their recorded SHA-256 before being treated as resolved evidence references.
- Memory compaction preserves the promotion/authority boundary even when retrieval detail is removed.
- Recovery tests cover organ projection, resume continuity, evidence reference/hash resolution, boundedness and non-escalation of memory authority.

The Phase 6 exit condition is therefore satisfied at repository implementation level: one documented promotion/read path exists and the coding agent has no new peer authoritative memory store. A fresh runtime/CI execution is still required before claiming live gauntlet proof.

Phase 7 must build compute, reuse and crystallisation on top of this boundary: crystals and learned reuse may propose or accelerate work, but they must not bypass exact-source, verification, promotion or mutation authority.


## Phase 7 implementation checkpoint

The coding-agent path now consumes BEAST's existing Mission Crystal Lattice through a dedicated reuse authority plane rather than treating crystals as memory or source truth.

Implemented:

- `AgentReuseRuntime` converts lattice matches into bounded planner proposals with explicit compute-savings claims and authority limits.
- Strong, previously verified lattice matches may become strategy/replay candidates; weaker matches degrade to strategy scaffold or context hint.
- Every proposal states that fresh source reads and fresh verification remain mandatory.
- Planner context now includes the Phase 7 reuse proposal alongside canonical context and memory packets.
- Exact planner-response crystal replay can still produce zero-inference turns, but cached worktree decisions have any prior `approval_id` stripped before returning to the live loop. Prior authorization is therefore not replayable.
- Recovery tests cover strong reuse, blocked/unverified reuse, compaction authority preservation, and stale mutation-approval stripping.

### Phase 7 closure

Repository implementation is complete.

- Fresh successful `worktree.verify` observations now feed a verified outcome back into the Mission Crystal Lattice.
- Failed verification emits crystal feedback but writes no promoted lattice cell.
- Existing Crystal Runtime staleness/proof-local gates and Crystal Credit Quarantine remain the canonical mechanism for stale or incompatible inference credits.
- Exact verified planner-response reuse can produce a zero-inference planner turn, with avoided-token telemetry, while historical mutation approval is stripped.
- Strategy/lattice reuse remains advisory and cannot skip a current exact source read, current verifier receipt, governed mutation tool or promotion gate.
- Recovery tests cover fresh-verification strengthening and failed-verification non-promotion in addition to the reuse authority membrane.

Phase 7 is closed at repository implementation level. Fresh runtime/CI execution is still required before claiming measured live token savings or gauntlet proof.

Phase 8 can now move the coding agent onto governed execution: bind execution intent, worktree authority, interception, input/output governance and execution evidence into one coherent path.
