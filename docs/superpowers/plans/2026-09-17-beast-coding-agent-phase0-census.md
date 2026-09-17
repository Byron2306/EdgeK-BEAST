# BEAST Coding Agent Phase 0 Full-System Census Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable full-system census of every BEAST component relevant to the coding-agent path, keeping static repository facts separate from runtime participation and producing canonical machine-readable and human-readable outputs.

**Architecture:** Phase 0 begins with a deterministic mixed-language repository scanner, then adds composition-root and runtime evidence overlays. Static discovery never promotes a runtime field. Runtime traces enrich the same canonical JSON records, and Markdown/runtime maps are projections of that source of truth.

**Tech Stack:** Python 3, `ast`, regex-based JS/TS import extraction, pytest, existing BEAST runtime/evidence facilities, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-17-beast-coding-agent-phase0-census-design.md`

## Global Constraints

- Do not change Pair Programmer, planner, provider, compute, execution, crystal, Sensorium, memory, Quality Cascade or governance behavior in Phase 0.
- Never infer runtime construction, invocation, evidence production, authority or `WIRED` status from static imports, file presence, tests, docs, registry entries or historical proof artifacts.
- Exact editable source and patch anchors must remain exact; census compression/summaries are analysis artifacts only.
- The latest publication branch remains untouched; all Phase 0 work lives on `agent/beast-coding-agent-phase0-census` until reviewed.
- `unclassified` is acceptable during intermediate census passes but forbidden for coding-agent-relevant components at Phase 0 exit.

---

### Task 1: Deterministic static census generator

**Files:**
- Create: `scripts/beast_full_system_census.py`
- Create: `tests/test_beast_full_system_census.py`

**Interfaces:**
- Produces: `scan_repository(root: pathlib.Path) -> dict`
- Produces: `render_markdown(report: dict) -> str`
- CLI: `python scripts/beast_full_system_census.py --root . --json-out <path> --md-out <path>`

- [x] **Step 1: Write the failing scanner test**

Create a synthetic mixed repository containing Python agent/context files, a JS Pair Programmer file and a GitHub workflow. Assert deterministic path order, Python/JS import extraction, layer classification, and runtime fields initialized to `unverified`.

- [x] **Step 2: Run the test and verify RED**

Run:

```bash
python -m pytest -q tests/test_beast_full_system_census.py
```

Expected before implementation: collection fails because `beast_full_system_census` does not exist.

- [x] **Step 3: Implement the minimal scanner**

Implement mixed-language scanning, ignore generated/dependency/backup trees, first-pass layer classification, Python AST imports, JS/TS static import extraction, deterministic sorting, JSON report construction and Markdown rendering.

- [x] **Step 4: Verify GREEN against the synthetic fixture**

Expected: `2 passed`.

- [ ] **Step 5: Run the same tests inside the BEAST checkout**

Run:

```bash
python -m pytest -q tests/test_beast_full_system_census.py
```

Expected: all scanner tests pass inside the real project environment.

- [ ] **Step 6: Commit scanner and tests**

```bash
git add scripts/beast_full_system_census.py tests/test_beast_full_system_census.py
git commit -m "feat: add deterministic BEAST full-system census scanner"
```

### Task 2: Generate the baseline full-repository census

**Files:**
- Create/generated: `docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json`
- Create/generated: `docs/BEAST_FULL_SYSTEM_CENSUS.md`

**Interfaces:**
- Consumes: `scan_repository()` and `render_markdown()` from Task 1.
- Produces: deterministic static inventory used by every later Phase 0 overlay.

- [ ] **Step 1: Generate canonical outputs**

Run from repository root:

```bash
python scripts/beast_full_system_census.py \
  --root . \
  --json-out docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json \
  --md-out docs/BEAST_FULL_SYSTEM_CENSUS.md
```

- [ ] **Step 2: Validate deterministic regeneration**

Run the generator twice and verify no diff:

```bash
cp docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json /tmp/beast-census-first.json
cp docs/BEAST_FULL_SYSTEM_CENSUS.md /tmp/beast-census-first.md
python scripts/beast_full_system_census.py --root . --json-out docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json --md-out docs/BEAST_FULL_SYSTEM_CENSUS.md
diff -u /tmp/beast-census-first.json docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json
diff -u /tmp/beast-census-first.md docs/BEAST_FULL_SYSTEM_CENSUS.md
```

Expected: both diffs are empty.

- [ ] **Step 3: Inspect census coverage**

Confirm the generated inventory includes at minimum `desktop-ide`, `app/routes`, `app/kernel/agents`, `app/kernel/data_processing`, `app/kernel/compute`, `app/kernel/storage`, `app/kernel/governance`, `app/kernel/execution`, `app/kernel/commons`, `scripts`, `.github/workflows`, and `tests` where present.

- [ ] **Step 4: Commit baseline outputs**

```bash
git add docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json docs/BEAST_FULL_SYSTEM_CENSUS.md
git commit -m "audit: generate BEAST full-system census baseline"
```

### Task 3: Add composition-root and disposition overlay

**Files:**
- Modify: `scripts/beast_full_system_census.py`
- Modify: `tests/test_beast_full_system_census.py`
- Create: `config/beast_coding_agent_census_overrides.json`

**Interfaces:**
- Consumes: static census records.
- Produces per-component `composition_roots`, `disposition`, `agent_relevance`, `claimed_responsibilities`, and `overlap_candidates` fields without altering runtime truth.

- [ ] **Step 1: Write a failing override test**

Add a fixture override assigning one component `online_authoritative`, one `supervised_offline`, and one overlapping responsibility. Assert invalid dispositions are rejected and missing paths are surfaced as stale overrides.

- [ ] **Step 2: Run RED**

```bash
python -m pytest -q tests/test_beast_full_system_census.py -k override
```

Expected: fails because override loading/validation does not exist.

- [ ] **Step 3: Implement override loading and validation**

Allow only these dispositions: `online_authoritative`, `online_supporting`, `supervised_offline`, `dormant_gated`, `stranded`, `duplicate_candidate`, `compatibility_shim`, `retired`, `unclassified`.

- [ ] **Step 4: Seed verified existing compute dispositions**

Translate the existing `app/kernel/compute/module_dispositions.py` categories into the census without weakening their meaning. Preserve `ONLINE_ENFORCEMENT`, `SUPERVISED_EVIDENCE`, `OFFLINE_LIBRARY`, and `RETIRED` as source facts in notes while mapping them into Phase 0 dispositions.

- [ ] **Step 5: Run GREEN and regenerate census**

```bash
python -m pytest -q tests/test_beast_full_system_census.py
python scripts/beast_full_system_census.py --root . --json-out docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json --md-out docs/BEAST_FULL_SYSTEM_CENSUS.md
```

- [ ] **Step 6: Commit overlay**

```bash
git add scripts/beast_full_system_census.py tests/test_beast_full_system_census.py config/beast_coding_agent_census_overrides.json docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json docs/BEAST_FULL_SYSTEM_CENSUS.md
git commit -m "audit: classify BEAST census dispositions"
```

### Task 4: Build current coding-agent runtime trace harness

**Files:**
- Create: `scripts/trace_beast_coding_agent_runtime.py`
- Create: `tests/test_trace_beast_coding_agent_runtime.py`
- Modify: `docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json` only through the trace/merge tool.

**Interfaces:**
- Produces trace records containing request ID, mode, component path or canonical ID, event (`constructed`, `invoked`, `evidence_written`, `authority_exercised`), receipt/evidence reference, and timestamp.
- Merge operation may promote runtime fields from `unverified` only when a matching trace event exists.

- [ ] **Step 1: Write failing trace-merge tests**

Assert that a static import alone leaves runtime fields `unverified`; a valid `constructed` trace promotes only construction; an `invoked` trace promotes invocation; malformed or unknown component references are rejected.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/test_trace_beast_coding_agent_runtime.py
```

- [ ] **Step 3: Implement trace schema and merge logic**

Do not instrument broad production behavior yet. First support importing existing durable AgentRun, tool, compute and evidence events where identifiers can be matched without semantic guessing.

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/test_trace_beast_coding_agent_runtime.py
```

- [ ] **Step 5: Commit runtime trace harness**

```bash
git add scripts/trace_beast_coding_agent_runtime.py tests/test_trace_beast_coding_agent_runtime.py
git commit -m "audit: add coding-agent runtime census trace harness"
```

### Task 5: Trace representative agent journeys and produce runtime map

**Files:**
- Create: `docs/BEAST_CODING_AGENT_RUNTIME_MAP.md`
- Modify/generated: `docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json`
- Modify/generated: `docs/BEAST_FULL_SYSTEM_CENSUS.md`

**Interfaces:**
- Consumes trace records from Task 4.
- Produces an evidence-backed current runtime route; speculative/future edges are rendered separately.

- [ ] **Step 1: Trace analysis-only request**

Capture ingress, mode resolution, planner/provider route, retrieval/context organs, compute organs and final response evidence without mutation.

- [ ] **Step 2: Trace single-file mutation**

Capture index, worktree bind, source read, mutation, verification, SourcePlan and completion path.

- [ ] **Step 3: Trace cross-file mutation**

Record whether Code Cortex/index/context organs are actually used and whether frontend three-file clipping changes the planner evidence set.

- [ ] **Step 4: Trace failed mutation and repair**

Capture invalid decision/repair/escalation path and every turn consumed.

- [ ] **Step 5: Render runtime map**

The map must distinguish observed edges, static-only edges, dormant/gated edges and intended future edges.

- [ ] **Step 6: Commit runtime map and enriched census**

```bash
git add docs/BEAST_CODING_AGENT_RUNTIME_MAP.md docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json docs/BEAST_FULL_SYSTEM_CENSUS.md
git commit -m "audit: map observed BEAST coding-agent runtime"
```

### Task 6: Responsibility conflict census and Phase 0 closure report

**Files:**
- Create: `docs/BEAST_CODING_AGENT_RECOVERY_MASTER_PLAN.md`
- Modify: `docs/BEAST_FULL_SYSTEM_CENSUS.md`
- Modify: `docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json`

**Interfaces:**
- Produces the exact ownership conflicts that Phase 1 must resolve.

- [ ] **Step 1: Enumerate responsibility claimants**

At minimum review repository discovery, semantic indexing, context selection, compression, working memory, episodic memory, evidence persistence, inference routing, interception, mutation authority, verification, repair, crystallisation and operator presentation.

- [ ] **Step 2: Classify each overlap**

For each responsibility, identify current authoritative owner if proven, supporting owners, duplicate candidates, stranded implementations and unresolved conflicts.

- [ ] **Step 3: Run Phase 0 exit validation**

Fail closure if any coding-agent-relevant component remains `unclassified`, any runtime edge is asserted without evidence, or the observed runtime map contains a speculative edge presented as current.

- [ ] **Step 4: Record later-phase defect queue without fixing it**

Include the already established planner-turn-budget contradiction, frontend/backend protocol collision, actual Ollama budget mismatch, three-file clipping, blind prompt truncation and endurance-CI dependency failure as Phase 3 inputs.

- [ ] **Step 5: Run focused Phase 0 tests**

```bash
python -m pytest -q tests/test_beast_full_system_census.py tests/test_trace_beast_coding_agent_runtime.py
```

- [ ] **Step 6: Commit Phase 0 closure artifacts**

```bash
git add docs/BEAST_CODING_AGENT_RECOVERY_MASTER_PLAN.md docs/BEAST_FULL_SYSTEM_CENSUS.md docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json
git commit -m "docs: close BEAST coding-agent phase 0 census"
```

## Phase 0 acceptance

Phase 0 is complete only when the machine-readable census, human census and runtime map agree; every coding-agent-relevant component has a disposition; static and runtime truth remain separate; responsibility overlaps are explicit; and Phase 1 receives a finite ownership-conflict list rather than another architectural hypothesis.