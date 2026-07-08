# BEAST Upgrade Plan Relative to Gortex and the Agentic IDE Ecosystem

Date: 2026-07-08

## Purpose

This document compares BEAST with
[zzet/gortex](https://github.com/zzet/gortex) and turns that comparison into a
BEAST-native upgrade plan.

The conclusion is not that BEAST should become Gortex. Gortex is a
high-performance code-intelligence engine. BEAST is a governed local-first
runtime for agentic software work, provider economics, crystallized compute,
evidence, verification, and promotion.

The right upgrade is to make BEAST graph-aware and edit-capable without losing
its strongest property: every meaningful action should remain bounded,
approved, verifiable, reversible, and crystallizable into durable evidence.

## Executive Summary

Gortex's strongest ideas are:

- Persistent code graph as the primary context substrate.
- Symbol/file/call/dependency lookup instead of broad file reads.
- MCP, CLI, HTTP, and daemon surfaces backed by one query engine.
- Live file watching and incremental graph updates.
- Speculative edits and live editor overlays before disk writes.
- Small, preset tool surfaces for agent workflows.
- Verification and impact checks close to edit operations.

BEAST already has strong ingredients that Gortex does not center:

- Task envelope, PREC lifecycle, and handoff governance.
- Provider routing, provider fitness, and provider economist lanes.
- SourcePlan approval, diff, apply, rollback, and Chronicle flow.
- Crystal reuse, Memory Hull, Residue Seal, Agent Passport, and local compute
  evidence.
- Commons Spaces, Swarm, capability registry, tool laziness, and promotion
  scaffolding.
- Tournament and final-boss proof harnesses that measure real provider/local
  behavior.

The gap is that BEAST has these systems as powerful lanes, but not yet as a
single, graph-native developer loop. The upgrade target is:

```text
request
-> task envelope
-> graph-aware orientation
-> bounded context/workbench
-> governed SourcePlan / Action IR
-> speculative shadow buffer
-> structured diff and risk
-> approval
-> apply
-> verification
-> Chronicle + Memory Hull + promotion
-> graph refresh
```

## Current BEAST Baseline

### Strengths

BEAST is already unusually strong in the governance and evidence layers.

- `app/cli/api.py` contains local workspace selection, safe file filtering,
  context reads, SourcePlan generation, diff rendering, verification, apply,
  rollback, and Chronicle writing.
- `app/cli/ui.py` already exposes context picking, SourcePlan creation, hunk
  toggling, approval, apply, rollback, provider selection, live sessions, and
  evidence panels.
- `app/mcp/runtime.py` exposes SourcePlan tools, maintenance, handoff,
  provider fitness, capability exchange, and runtime evidence tools.
- `app/kernel/data_processing/workspace_graph.py` provides the current
  SQLite-backed graph for traces, files, symbols, semantic chunks, and graph
  exports.
- `app/kernel/compute/action_ir.py` and
  `app/kernel/compute/action_resolver.py` already define a compact provider
  action language and resolver for anchor/symbol/provider-record style edits.
- The crystal compute stack now has strong proof harnesses and evidence
  artifacts around local replay, negative controls, Memory Hull, and provider
  displacement.

### Weaknesses

The main weaknesses relative to Gortex are architectural cohesion and developer
ergonomics.

- The workspace graph is useful but shallow. It is mostly regex/SQLite based,
  with placeholder vector search and limited language-aware extraction.
- The TUI can apply edits, but the operator does not yet get a first-class code
  workbench with visible buffers, changed line ranges, symbol context, and
  post-apply file confirmation.
- SourcePlan operations often degrade into full-file replacement operations
  rather than targeted anchor/symbol edits.
- MCP tools are numerous and powerful, but the edit/read/graph surfaces are not
  yet grouped into strict presets like `readonly`, `edit`, `nav`, and `full`.
- BEAST has several runtime/evidence lanes that can still feel parallel:
  SourcePlan, Action IR, task envelopes, crystal reuse, workspace graph,
  provider handoff, MCP broker, and TUI workbench.
- There is no long-lived BEAST code intelligence daemon with watcher-driven
  incremental graph updates.
- Verification is strong after apply, but impact/risk analysis should be
  attached before apply using graph dependents, tests, and changed-symbol
  scope.

## Comparison Matrix

| Dimension | Gortex | BEAST Today | Upgrade Direction |
|---|---|---|---|
| Core identity | Code-intelligence graph engine | Governed agentic runtime and compute evidence plane | Keep BEAST governance-first, add graph-native code workbench |
| Context retrieval | Symbol, call graph, dependencies, semantic search, file summaries | Context picker, snippets, workspace graph, compression pipeline | Replace broad file context with graph-ranked edit context |
| Edit model | `edit_file`, `edit_symbol`, speculative execution, overlays | SourcePlan diff/apply/rollback; full-file fallback | Promote Action IR anchor/symbol edits and shadow buffers |
| Runtime | Long-lived daemon, fs watcher, shared graph | Gateway, TUI, MCP runtime, local stores | Add BEAST workspace daemon for graph/watch/index/cache |
| MCP surface | Large catalog with presets and lazy discovery | Many BEAST tools, sourceplan tools, broker policies | Add tool profiles/presets and stricter edit/read modes |
| Multi-repo | First-class multi-repo graph and contracts | Mostly single active workspace, Commons/Spaces adjacent | Add workspace registry and cross-repo contract receipts |
| Verification | `verify_change`, guards, diagnostics | py_compile, pytest opt-in, quality cascade, governance | Add pre-apply impact/test-target selection |
| Evidence | Token savings, graph provenance, safety checks | Chronicle, Memory Hull, crystal reuse, provider tournaments | Make every edit emit unified evidence and promotion candidates |
| UI | Web UI graph visualization | Textual mission console | Add Source Workbench plus graph/evidence panels |

## Upgrade Principles

1. **Do not clone Gortex wholesale.**
   BEAST should ingest the useful graph/edit ergonomics while preserving its own
   governance, verification, and compute-reuse spine.

2. **Make the graph an advisory substrate, not the source of truth.**
   Append-only receipts, Chronicle records, task envelopes, rollback snapshots,
   Memory Hull sidecars, and verification receipts remain authoritative.

3. **Never make edits invisible.**
   Every proposed edit must have a file, old hash, new hash, changed ranges,
   preview buffer, selected state, verification state, and rollback path.

4. **Use local-first verification before provider escalation.**
   Provider calls should receive compact graph-ranked context and return Action
   IR, not free-form patch prose.

5. **Treat graph context as spend reduction.**
   Track tokens/files avoided by graph-oriented context the same way BEAST
   tracks compute reuse and provider displacement.

6. **Keep policy gates close to mutation.**
   Editing tools must be callable only in an explicit implement/edit phase, with
   approval and rollback mandatory for source writes.

## External Code-Intelligence and Agentic IDE Landscape

The additional ecosystem scan broadens the Gortex comparison into four adjacent
families. The important lesson is that BEAST should not integrate every project
as a dependency. It should absorb their workflow patterns into a small number of
governed BEAST-native interfaces.

### Code-Intelligence Engines

These projects improve graph context, symbols, semantic search, cross-repo
contracts, MCP context, and token reduction.

| Reference Pattern | Useful Signal for BEAST | BEAST Integration Direction |
|---|---|---|
| `zzet/gortex` | Multi-language graph, MCP/API/UI surfaces, multi-repo contracts | Optional adapter plus BEAST-owned normalized graph/context schema |
| `oraios/serena` | Symbol-level semantic retrieval, edit/refactor/debug tools over MCP | Add BEAST Symbol Surgeon methods for symbol-scoped SourcePlan operations |
| `ezzy1630/argyph` | Local-first MCP bundle with grep, symbol graph, semantic search, incremental index | Keep BEAST's baseline code cortex local, lightweight, and dependency-optional |
| `probelabs/probe` | Codebase reasoning loop over search/analysis, not only raw retrieval | Add diagnostic-first context plans before patch generation |
| `zilliztech/claude-context` | Vector-backed semantic code retrieval for MCP agents | Use semantic search as a fallback lane, not as the only context source |
| Elastic semantic indexer/MCP split | Separate indexing daemon from agent-facing MCP server | Keep BEAST workspace service as the indexing authority and MCP as one consumer |
| `repomix` / `gitingest` | Reliable repo-to-text fallback bundles | Add emergency repo bundle exports for offline/unsupported languages |

### Agentic Coding Runtimes

These projects improve modes, planning, editing loops, terminal flows, and
GitHub issue-to-patch workflows.

| Reference Pattern | Useful Signal for BEAST | BEAST Integration Direction |
|---|---|---|
| `cline/cline` | Multi-surface runtime and MCP/custom-tool integration | Keep BEAST APIs usable from TUI, CLI, MCP, and future IDE surfaces |
| `RooCodeInc/Roo-Code` | Explicit modes such as Code, Architect, Ask, Debug, Custom | Formalize BEAST Mode Router roles and tool permissions |
| `aider-ai/aider` | Mature terminal/git editing loop | Study patch ergonomics, but keep BEAST SourcePlan governance authoritative |
| `opencode-ai/opencode` | Terminal agent plus issue/PR automation pattern | Future issue-to-task-to-SourcePlan bridge |
| `OpenHands/openhands` | Self-hosted agent control center and workspace SDK | Long-running BEAST missions and isolated workspaces |
| `swe-agent` / AutoCodeRover | Agent-computer interface and diagnostic-first issue solving | Require fault-localization evidence before broad edits |
| `plandex-ai/plandex` / RA.Aid | Planning/execution split for long multi-file tasks | Add BEAST campaign plans that compile into SourcePlan batches |

### Workspace and Multi-Agent Control Planes

These projects improve operator control: worktrees, terminals, sessions, branch
isolation, PR review, and multi-agent supervision.

| Reference Pattern | Useful Signal for BEAST | BEAST Integration Direction |
|---|---|---|
| AgentWrapper/agent-orchestrator | Supervises multiple CLI coding agents, terminals, branches, PRs | BEAST Worktree Forge with governed session cards |
| AgentsMesh | Schedules many agents on owned machines | Tie BEAST compute forge to local agent capacity and isolation |
| TUICommander / Pane / Lattice | Terminal-first multi-agent panes and observability | Add TUI session cards before embedded terminal multiplexing |
| `superset-sh/superset` | Worktree-first model with review/open-in-editor workflows | Make per-task worktrees the default for risky or parallel edits |
| `gastownhall/gastown` / `kandev` | Git-backed persistent work state, Kanban, PR/review loops | Store mission state against branch/worktree receipts, not only chat history |

### Standards and Workflow Glue

| Standard/Pattern | Useful Signal for BEAST | BEAST Integration Direction |
|---|---|---|
| `AGENTS.md` | Project-local agent instructions are becoming common | Add AGENTS.md ingestion with bloat/conflict/pruning lint |
| GitHub `spec-kit` | Spec-driven development flow before implementation | Add Spec Covenant: constitution -> spec -> plan -> tasks -> SourcePlan |
| Agent configuration smell research | Agent files often leak context, conflict, or over-broaden scope | Treat agent instructions as policy inputs that must be linted and scoped |
| Repository setup security reporting | Agents can be tricked by setup/install/bootstrap instructions | Add Safety Governor scans before running setup, install hooks, shell scripts, or networked commands |

## Highest-Value Integrations to Start With

The next integrations should be ranked by how much they improve BEAST's
governed edit loop without creating hard external dependencies.

1. **Serena-style Symbol Surgeon**
   Add symbol-scoped lookup and edit/refactor methods that compile into
   SourcePlan operations. This directly attacks the full-file replacement
   problem and makes edits smaller, clearer, and easier to verify.

2. **Gortex Adapter as Optional Code Cortex Accelerator**
   Add a feature-detected adapter for richer graph context, dependents,
   contract maps, and symbol search. Gortex should feed BEAST context and
   evidence, never bypass SourcePlan approval or apply.

3. **Argyph/Probe-style Local Search Fallback**
   Add a local code-reasoning fallback that combines grep, symbol extraction,
   import/dependent scans, and semantic search when no Gortex-like service is
   available. This keeps BEAST useful on every machine.

4. **Worktree Forge**
   Add per-task worktree/session records inspired by worktree-first agent
   managers. Risky edits, parallel provider attempts, and long refactors should
   happen in isolated branches before merge/apply evidence is promoted.

5. **Mode Router**
   Formalize modes such as Scout, Architect, Debugger, Implementer, Reviewer,
   Security Gate, Evidence Logger, and Budget Controller. Each mode should have
   its own MCP/TUI tool profile, context budget, and mutation permissions.

6. **Spec Covenant and AGENTS.md Lint**
   Add spec-kit style task structure and scoped AGENTS.md ingestion before
   provider escalation. BEAST should load only relevant instructions, flag
   conflicts, and record the instruction digest in evidence.

7. **Safety Governor for Workspace Bootstrap**
   Before running install/setup/test commands suggested by a repo or agent,
   scan shell scripts, package hooks, network calls, and suspicious bootstrap
   behavior. This should become a mandatory pre-execution receipt for unknown
   workspaces.


## Capability Absorption Map

The adjacent repo landscape should be absorbed as BEAST-native capabilities, not
as a pile of fragile dependencies. The guiding metaphor is simple: code
intelligence projects give BEAST better eyes; agentic IDE projects give BEAST
better hands; workspace orchestration projects give BEAST better posture; safety
and spec projects give BEAST better judgment.

| External Pattern Family | What It Adds to BEAST | BEAST-Native Capability | Governing Rule |
|---|---|---|---|
| Gortex / CodeGraphContext / Argyph / Probe | Repo graph, symbols, dependents, semantic retrieval, call/context maps | **Code Cortex** | Advisory context only; SourcePlan remains the write path |
| Serena-style symbol tooling | Symbol-aware edits and refactors | **Symbol Surgeon** | Compile symbol intent into Action IR and previewable hunks |
| Cline / Roo / OpenHands / aider / swe-agent | Agent modes, planning, terminal workflows, issue-to-patch loops | **Mode Router** | Each mode gets scoped tools, budgets, and mutation permissions |
| Agent Orchestrator / TUICommander / Superset / Pane / Lattice | Worktrees, parallel sessions, terminal cards, branch isolation | **Worktree Forge** | Risky or parallel edits never mutate the primary workspace first |
| AgentsMesh-style scheduling | Owned-machine agent capacity and local swarm scheduling | **Compute Forge Agent Scheduler** | Local CPU/agent capacity competes before cloud escalation |
| AGENTS.md / spec-kit | Project-local rules, specs, task breakdowns | **Spec Covenant** | Rules are linted, scoped, digested, and cited as receipts |
| Bootstrap/security research | Setup/install/script risk detection | **Safety Governor** | No implicit trust in repo setup or agent-suggested shell commands |
| Kanban/PR/workflow tools | Mission state, review flow, PR handoff | **Mission Control Cockpit** | Every mission has state, evidence, route, risk, and rollback visibility |

The upgrade path is therefore not "integrate every repo." The upgrade path is:

```text
Code Cortex -> Mode Router -> Worktree Forge -> Spec Covenant -> Safety Governor
-> Compute Forge Scheduler -> Mission Control Cockpit -> Evidence Closure
```

This turns BEAST into a governed workspace operating system for agentic coding,
with local-first economics and hard mutation boundaries.

## New BEAST Workflow: Governed Code Cortex Loop

The upgraded workflow should become:

```text
operator request
-> Spec Covenant
   - parse objective
   - ingest scoped AGENTS.md/project rules
   - lint conflicting or bloated instructions
-> Mode Router
   - choose Scout/Architect/Debugger/Implementer/Reviewer/Security/Evidence
   - select MCP/TUI tool profile and context budget
-> Code Cortex
   - use BEAST graph baseline
   - optionally query Gortex/Serena-style adapters
   - gather symbols, dependents, routes, tests, contracts, semantic snippets
-> Diagnostic First Pass
   - identify likely files/symbols
   - estimate impact radius
   - produce test target plan
   - produce safety/setup risk receipt
-> Worktree Forge
   - create or select task worktree for risky/parallel work
   - attach branch, commit, workspace registry, and terminal/session records
-> Provider/Local Route Selection
   - use provider edit fitness, tournament fitness, local crystal evidence,
     context discipline, and cost/latency
-> Action IR / Symbol Surgeon
   - provider returns compact intent
   - BEAST resolves intent to anchor/symbol SourcePlan operations
-> Source Workbench
   - show files, hunks, before/after buffers, changed ranges, impact, tests,
     stale/hash state, provider route reason, and rollback plan
-> Approval and Apply
   - apply only selected operations
   - verify from disk
   - run targeted tests
-> Evidence Closure
   - Chronicle, Memory Hull, graph refresh, provider edit fitness,
     promotion candidate, negative evidence if blocked/failed
-> Learning Loop
   - update provider routing, context discipline, capability registry,
     crystal promotion, and future Code Cortex ranking
```

### Workflow Design Rules

- Graph and external adapters can recommend context; only SourcePlan can write.
- Symbol edits should be preferred over full-file edits whenever a stable
  resolver exists.
- Every phase should produce a small receipt: spec digest, context pack,
  impact radius, route decision, edit plan, verification, and evidence closure.
- Worktree isolation should be automatic for multi-file, cross-repo, dependency,
  bootstrap, or high-risk provider edits.
- Provider/local route selection should include edit fitness, context
  discipline, graph impact, and prior verification outcomes.
- Fallback repo bundles are allowed, but should be recorded as high-context,
  low-precision context sources.

## Target Architecture

```text
BEAST Gateway / TUI / MCP
        |
        v
Task Envelope + PREC Lifecycle
        |
        v
Workspace Graph Daemon
  - file tree
  - symbols
  - semantic chunks
  - imports/dependencies
  - changed file watcher
  - graph cache
        |
        v
Source Workbench
  - selected files
  - selected symbols
  - shadow buffers
  - structured diffs
  - hunk toggles
        |
        v
Action IR / SourcePlan Compiler
  - replace_exact
  - replace_anchor
  - modify_symbol
  - create_or_replace
  - run_verifier / ask_for_context
        |
        v
Pre-Apply Gates
  - policy
  - drift/hash
  - risk score
  - test targets
  - approval
        |
        v
Apply + Verify + Rollback
        |
        v
Chronicle + Memory Hull + Unified Evidence Packet
        |
        v
Promotion / Crystal Reuse / Commons Space Candidate
```

## Workstream 1: Graph-Native Workspace Core

Status: **Complete for the backend graph core.** Completed on 2026-07-08.
The always-on watcher daemon remains in Workstream 6, and the visual TUI
workbench remains in Workstream 2.

### Problem

BEAST's current `WorkspaceGraph` is valuable but lightweight. It indexes files,
some symbols, traces, semantic chunks, and graph exports, but it does not yet
provide Gortex-class orientation for code edits.

### Progress Update: 2026-07-08

- ~~Added `app/kernel/data_processing/code_indexers.py` for dependency-free
  file metadata, language detection, symbol extraction, import extraction, and
  test-runner detection.~~
- ~~Upgraded `WorkspaceGraph.index_repository()` to produce richer file,
  directory, symbol, import, and test nodes.~~
- ~~Added graph edges for repository containment, file containment, symbol
  definitions, imports, and test coverage hints.~~
- ~~Added `file_status()`, `changed_since()`, and `graph_context_for_task()`
  APIs.~~
- ~~Exposed graph stats, file-status, changed-since, and task-context endpoints
  through `app/main.py`.~~
- ~~Added workspace graph tests covering richer indexing, drift detection, and
  task-context packing.~~
- ~~Verified with `python3 -m py_compile app/main.py
  app/kernel/data_processing/code_indexers.py
  app/kernel/data_processing/workspace_graph.py`.~~
- ~~Verified with `python3 -m pytest tests/test_workspace_graph.py -q`.~~
- ~~Verified related context/reasoning tests with `python3 -m pytest
  tests/test_context_packet.py tests/test_workspace_reasoning.py
  tests/test_ollama_scout.py -q`.~~
- ~~Added route nodes for FastAPI/Flask-style Python routes and Express-style
  JS/TS routes.~~
- ~~Added local `depends_on` and `used_by` edges from import resolution.~~
- ~~Added `record_context_consumption()` and `stale_context_events()` so
  sessions can receive stale-context warnings after consumed files change.~~
- ~~Added `record_sourceplan_apply()` and `record_sourceplan_rollback()` graph
  receipts, including `changed_by` and `verified_by` edges.~~
- ~~Refreshed the workspace graph after SourcePlan apply and rollback when a
  graph instance is attached to the TUI API.~~
- ~~Exposed context-consumption, stale-context, and index-benchmark endpoints
  through `app/main.py`.~~
- ~~Optimized repository indexing with a single SQLite transaction and per-run
  node/edge de-duplication.~~
- ~~Benchmarked BEAST self-indexing at 5,000 files in 5.7835 seconds, under
  the 15-second Workstream 1 target.~~

### Target Capabilities

- ~~Repository index for the active workspace with richer metadata.~~
- ~~Incremental change-detection APIs for the active workspace.~~
- Persistent watcher-driven background re-indexing is deferred to Workstream 6.
- ~~File, directory, symbol, import, test, artifact, and route nodes.~~
- ~~Edges for `contains`, `defines`, `imports`, `mentions`, `tests`,
  `changed_by`, `verified_by`, `depends_on`, and `used_by`.~~
- ~~Fast file/symbol/route search for the TUI and MCP runtime surfaces.~~
- ~~Context packs that return symbol/file slices under a token budget.~~
- ~~Staleness events when files consumed by a session change.~~

### Implementation Plan

1. ~~Extend `WorkspaceGraph.index_repository()` to record richer file metadata:
   language, line count, hash, mtime, size, detected test runner, and import
   statements.~~
2. ~~Add language-specific extractors in a small internal module:
   `app/kernel/data_processing/code_indexers.py`.~~
3. ~~Start with Python, JS/TS, Markdown, JSON/YAML/TOML. Do not attempt 257
   languages immediately.~~
4. ~~Replace placeholder `vector_search()` and `_lexical_semantic_search()`
   with local vector fallback plus BM25-style/token-overlap lexical scoring.~~
5. ~~Add `graph_context_for_task(objective, selected_files, token_budget)`.~~
6. ~~Add `changed_since(timestamp)` and `file_status(path)` APIs.~~
7. ~~Add graph refresh after SourcePlan apply and rollback.~~

### Acceptance Criteria

- ~~A fresh BEAST checkout can index itself in under 15 seconds on normal local
  hardware. Verified at 5,000 files in 5.7835 seconds.~~
- ~~`app/cli/ui.py`, `app/cli/api.py`, and their tests are discoverable by
  symbol/file search.~~
- ~~Context packs show why each file/symbol was selected.~~
- ~~A modified file changes its graph hash.~~
- ~~A modified file emits a stale-context warning for sessions that consumed
  that file.~~

### Remaining Work

1. ~~Benchmark full self-index performance on a fresh BEAST checkout and tune
   to the 15-second target.~~
2. ~~Add session-consumed file tracking plus stale-context event emission.~~
3. ~~Refresh the graph after SourcePlan apply and rollback.~~
4. ~~Add first-class `changed_by`, `verified_by`, `depends_on`, and `used_by`
   relationship edges.~~
5. ~~Expose the new graph context APIs for TUI/MCP edit/read flows.~~
6. ~~Add a stronger local search scorer for file/symbol retrieval.~~
7. Persistent filesystem watching moves to Workstream 6.
8. Visible source-workbench consumption of the new graph context moves to
   Workstream 2.

### Status Answer

Workstream 1 is **done for the backend graph-native workspace core**. BEAST now
has fast repository indexing, richer code nodes, route/dependency/edit-evidence
edges, task context packing, stale-context warnings, SourcePlan graph refresh,
HTTP surfaces, and a passing self-index benchmark.

## Workstream 2: Source Workbench TUI

Status: **Complete for the first source-workbench TUI slice.** Completed on
2026-07-08. Deeper shadow-buffer recomputation remains in Workstream 3.

### Problem

The TUI currently allows edits, but the operator sees a plan and a large diff
blob rather than an actual source editing workbench.

### Progress Update: 2026-07-08

- ~~Added structured per-operation diff payloads from `render_patch_diff()`,
  including `old_text`, `new_text`, `old_hash`, `new_hash`, and
  `changed_ranges`.~~
- ~~Added `SourceWorkbenchScreen` in `app/cli/ui.py`.~~
- ~~Changed the SourcePlan preview action so `f` opens the source workbench.~~
- ~~Kept `DiffPreviewScreen` available, with a `w` binding to open the
  workbench from the legacy diff view.~~
- ~~Added hunk list, selected-state markers, before/after code panes, line
  numbers, changed-line highlighting, verification/apply/rollback controls,
  and refresh navigation.~~
- ~~Added post-apply disk readback confirmation for applied files.~~
- ~~Added SourcePlan scorecard view-model sections for lattice replay,
  policy gate, verification, rollback, evidence closure, and local reusable
  capabilities.~~
- ~~Added mouse hunk selection and double-click toggle affordance in the Source
  Workbench.~~
- ~~Added focused TUI tests for structured diff data, workbench rendering,
  hunk navigation, and disk-readback confirmation.~~

### Target Capabilities

- ~~File / selected hunk pane.~~
- ~~Hunk list pane.~~
- ~~Code pane with line numbers.~~
- ~~Before/after diff panes.~~
- ~~Current selected state, hash state, verification state, and rollback state.~~
- ~~Post-apply file confirmation from disk.~~

### Implementation Plan

1. ~~Add `SourceWorkbenchScreen` in `app/cli/ui.py`.~~
2. ~~Keep `ContextPickerScreen`, `PatchPlanScreen`, and `DiffPreviewScreen`,
   but make `f` open the workbench once structured diff data exists.~~
3. ~~Add key bindings:
   - `tab`: switch pane
   - `up/down`: move file/hunk/code cursor
   - `space`: toggle selected hunk
   - `v`: verify
   - `y`: approve/save
   - `u`: apply
   - `z`: rollback
   - `r`: refresh from disk~~
4. ~~Render code with line numbers and highlighted changed ranges.~~
5. ~~Add a compact after-apply confirmation that reads current file contents
   from disk.~~

### Acceptance Criteria

- ~~Operator can select a file, build a SourcePlan, inspect the exact code to
  be written, toggle a hunk, apply it, and see the changed file from disk.~~
- ~~Tests cover modal navigation, hunk toggle, structured diff payloads, and
  post-apply visible file state.~~

### Status Answer

Workstream 2 is **done for the first usable source workbench**. The operator now
gets a hunk list, before/after code panes, line numbers, changed range
highlighting, apply/rollback controls, and disk readback after apply.

## Workstream 3: Structured Diff and Shadow Buffers

Status: **Complete for structured preview and shadow-buffer state.** Completed
on 2026-07-08. Symbol/anchor edit compilation continues in Workstream 4.

### Problem

`render_patch_diff()` currently returns a single text diff and basic operation
rows. The UI cannot reliably render code panes or changed ranges from that.

### Progress Update: 2026-07-08

- ~~Added `changed_ranges` computation using `difflib.SequenceMatcher`.~~
- ~~Returned both unified diff text and per-operation structured diff data from
  `render_patch_diff()`.~~
- ~~Added `preview_patch_plan(plan)` as a named API alias while preserving
  `render_patch_diff()` compatibility.~~
- ~~Added selected-operation shadow buffers with `old_text`, `next_text`,
  `old_hash`, `new_hash`, changed ranges, and source/edit state.~~
- ~~Added `preview_hash`, `selected_count`, and `stale_count` to preview
  payloads.~~
- ~~Stamped `preview_hash` metadata onto approved/saved patch plans.~~
- ~~Made stale hash warnings visible in the source workbench before apply.~~
- ~~Blocked stale SourcePlans before disk write through existing verification
  plus preview stale detection.~~
- ~~Pinned explicit `BeastApiClient(workspace=...)` instances so environment
  workspace changes do not override tests or targeted repo operations.~~

### Target Payload

Each operation should include:

```json
{
  "op_id": "op_001",
  "path": "app/cli/ui.py",
  "op": "replace_exact",
  "selected": true,
  "source_edit": true,
  "old_hash": "sha256:...",
  "new_hash": "sha256:...",
  "old_text": "...",
  "new_text": "...",
  "diff_lines": [],
  "changed_ranges": [{"old_start": 10, "old_end": 14, "new_start": 10, "new_end": 18}],
  "can_apply": true,
  "stale_reason": ""
}
```

### Implementation Plan

1. ~~Add a helper that computes changed ranges from
   `difflib.SequenceMatcher`.~~
2. ~~Return both full diff text and per-operation structured diff data.~~
3. ~~Add `preview_patch_plan(plan)` as a named API alias if useful, preserving
   `render_patch_diff()` compatibility.~~
4. ~~Add shadow-buffer state in the TUI:
   - selected operations produce `next_text`
   - toggling hunks recomputes preview without touching disk
   - stale hash warnings are visible before apply~~
5. ~~Record `preview_hash` in the plan before approval.~~

### Acceptance Criteria

- ~~Workbench can display changed line ranges without parsing a giant diff
  blob.~~
- ~~Toggling operations updates `new_hash`, `preview_hash`, shadow buffers, and
  selected counts immediately.~~
- ~~Applying a stale plan fails before disk write and shows the stale path.~~

### Status Answer

Workstream 3 is **done for structured preview and shadow-buffer state**. The
preview compiler now gives the TUI exact old/new text, changed ranges, selected
shadow buffers, preview hashes, and stale-plan blocking signals.

## Workstream 4: Action IR as the Primary Edit Contract

Status: **Complete for the Action IR bridge and evidence closure slice.**
Completed on 2026-07-08.

### Problem

The current fallback SourcePlan often writes full-file replacement content.
That is safe but noisy and less inspectable than symbol/anchor edits.

### Target

Providers and local scouts should produce Action IR. SourcePlan should compile
Action IR into explicit file operations only after policy, hash, and anchor
validation.

### Progress Update: 2026-07-08

- ~~Added first-class `replace_exact` SourcePlan operation support through
  normalization, preview, verification, apply, rollback, and Chronicle flow.~~
- ~~Routed provider Action IR through `ActionIR.from_dict()` and
  `resolve_action_ir()` before falling back to local source-note operations.~~
- ~~Compiled resolved Action IR into exact snippet SourcePlan hunks instead of
  full-file replacement hunks.~~
- ~~Preserved operation provenance fields: `action_ir_id`, `action_ir_type`,
  `anchor_ref`, `symbol`, and `resolver`.~~
- ~~Made invalid/non-unique Action IR visible through `provider_fallback_reason`
  when BEAST falls back to local safe hunks.~~
- ~~Added tests showing a provider can modify a selected function without
  returning the whole file.~~
- ~~Added tests showing non-unique exact snippets are rejected before preview or
  apply and fall back to governed local hunks.~~

### Implementation Plan

1. ~~Provider handoff/output governance describes Action IR and anchored edit
   preferences:~~
   - ~~`replace_exact`~~
   - ~~`replace_anchor`~~
   - ~~`modify_symbol`~~
   - ~~`run_verifier`~~
   - ~~`ask_for_context`~~
2. ~~Use `build_file_references()` from `action_resolver.py` when constructing
   handoffs so providers can refer to `F1`, `F2`, and anchor IDs.~~
3. ~~Route provider output through `ActionIR.from_dict()` and
   `resolve_action_ir()` before falling back to full-file operations.~~
4. ~~`replace_exact` now stays snippet-sized in SourcePlan. `create_or_replace`
   is reserved for metadata artifacts, new files, and fallback paths.~~
5. ~~Add operation provenance:
   - `provider_generated`
   - `local_fallback`
   - `action_ir_id`
   - `anchor_ref`
   - `symbol`
   - `resolver`~~

### Acceptance Criteria

- ~~A provider can modify a selected function without returning the whole
  file.~~
- ~~Non-unique exact anchors/snippets are rejected before preview/apply and
  surface fallback reason.~~
- ~~Exact old/new snippets retain preview, rollback, and verification
  behavior.~~

### Remaining Work

1. ~~Tighten provider-facing prompts in every SourcePlan handoff lane to prefer
   Action IR over source patch JSON.~~
2. Optional future polish: preserve original `replace_anchor` and
   `modify_symbol` labels in the TUI after resolution when that improves
   operator readability.
3. ~~Reduce `create_or_replace` usage further for provider outputs that can be
   represented as snippet edits.~~

### Status Answer

Workstream 4 is **complete for Action IR bridge and evidence closure**. BEAST can now
accept provider Action IR, resolve it through file refs and anchors, preserve
snippet-sized `replace_exact` operations in SourcePlan, reject ambiguous edits,
keep rollback/verification behavior, and persist governance receipts in evidence.

## Workstream 5: MCP Tool Surface Profiles

Status: **Complete for MCP tool profile filtering.** Completed on 2026-07-08.

### Problem

BEAST has many MCP capabilities, but agents should not see every tool schema
for every task. Gortex's preset/lazy surface model is useful here.

### Progress Update: 2026-07-08

- ~~Added `BEAST_MCP_TOOLS=readonly|edit|ops|evidence|full` profile support.~~
- ~~Added `BEAST_MCP_TOOLS_ALLOW` and `BEAST_MCP_TOOLS_DENY` filters.~~
- ~~Added always-visible `beast_tool_profile` tool.~~
- ~~Filtered `tool_definitions()` by active profile, category, allow-list, and
  deny-list.~~
- ~~Blocked hidden/mutating tool calls at `call_tool()` dispatch time with a
  structured profile-block response.~~
- ~~Added tests for default full exposure, readonly hiding/blocking, and
  allow-list filtering.~~

### Target Presets

| Preset | Purpose | Tools |
|---|---|---|
| `readonly` | Explore only | graph/search/context/read/diagnostics |
| `edit` | Governed coding | task envelope, context, sourceplan, verify, apply, rollback |
| `ops` | Runtime/admin | provider diagnostics, deployment, health, economy |
| `evidence` | Chronicle/crystal | evidence, Memory Hull, promotion, tournament receipts |
| `full` | Development/debug | all tools |

### Implementation Plan

1. ~~Add tool metadata categories in `app/mcp/runtime.py`.~~
2. ~~Add environment/config selector:
   - `BEAST_MCP_TOOLS=readonly|edit|ops|evidence|full`
   - `BEAST_MCP_TOOLS_ALLOW=...`
   - `BEAST_MCP_TOOLS_DENY=...`~~
3. ~~Add `beast_tool_profile` tool.~~
4. Deferred: add `beast_tool_search` for deferred tools if client support is
   practical.
5. ~~Make mutating tools blocked unless the active profile allows them.~~

### Acceptance Criteria

- ~~A readonly MCP client cannot apply SourcePlans.~~
- ~~An edit MCP client sees only the workbench-relevant tools.~~
- ~~Tool profile output explains what is live, hidden, or blocked.~~

### Status Answer

Workstream 5 is **done for MCP profile filtering**. BEAST now exposes profile
aware MCP tool definitions, reports active/hidden tools, and blocks mutating
tools when the active profile does not allow them.

## Workstream 6: Long-Lived Workspace Daemon

Status: **Complete for the in-process workspace service slice.** Completed on
2026-07-08. A separate daemon binary remains optional future work.

### Problem

Gortex benefits from a long-lived daemon with shared graph state and watchers.
BEAST currently has a gateway and runtime, but not a dedicated workspace index
daemon.

### Target

Add a BEAST workspace service that can run inside the gateway process first,
then optionally as a separate daemon later.

### Progress Update: 2026-07-08

- ~~Added `WorkspaceGraphService` as a dependency-free service wrapper around
  `WorkspaceGraph`.~~
- ~~Added active root tracking and cached per-root state.~~
- ~~Added service-level `index()`, `poll()`, `status()`, `files()`,
  `file()`, `symbols()`, and `context()` APIs.~~
- ~~Added polling watcher behavior that detects changed files, emits
  stale-context warnings, and optionally re-indexes changed workspaces.~~
- ~~Wired the gateway workspace endpoints through the in-process service.~~
- ~~Added REST endpoints for service status, polling, files, file readback, and
  symbols.~~
- ~~Added focused service tests for indexing, polling, file serving, symbol
  lookup, and stale-context events.~~

### Responsibilities

- ~~Track active workspace roots.~~
- ~~Index files and symbols.~~
- ~~Watch file changes through a polling watcher.~~
- ~~Maintain session-consumed file sets through the graph.~~
- ~~Emit stale-context events.~~
- ~~Cache graph summaries and per-root service state.~~
- ~~Serve graph APIs to TUI, MCP, and gateway.~~

### Implementation Plan

1. ~~Add `WorkspaceGraphService` wrapping `WorkspaceGraph`.~~
2. ~~Add simple polling watcher first; avoid a hard dependency if `watchfiles`
   is unavailable.~~
3. ~~Add REST endpoints:
   - `GET /edgek/workspace/graph/stats`
   - `POST /edgek/workspace/index`
   - `GET /edgek/workspace/files`
   - `GET /edgek/workspace/file`
   - `GET /edgek/workspace/symbols`
   - `POST /edgek/workspace/context`
   - `POST /edgek/workspace/poll`
   - `GET /edgek/workspace/service`~~
4. Partially complete: gateway endpoints now use the service. TUI online
   preference for these endpoints remains a later polish slice.
5. ~~Keep local direct file fallback for offline TUI mode.~~

### Acceptance Criteria

- Gateway and MCP can use the same indexed workspace graph state through the
  service.
- ~~File modifications become visible without restarting BEAST.~~
- ~~Offline mode still works with direct local reads.~~

### Remaining Work

1. Prefer `/edgek/workspace/*` service endpoints from the TUI when the gateway
   is online.
2. Optionally split the in-process service into a separate daemon process once
   BEAST needs cross-process graph sharing.

### Status Answer

Workstream 6 is **done for the in-process workspace service slice**. BEAST now
has active-root service state, polling change detection, stale-context events,
shared graph APIs, and gateway endpoints without adding watcher dependencies.

## Workstream 7: Pre-Apply Risk, Impact, and Test Targeting

Status: **Complete for the first deterministic SourcePlan scorecard slice.**
Completed on 2026-07-08.

### Problem

BEAST verifies after apply and can roll back, but it should expose risk before
approval.

### Target Risk Model

Each SourcePlan should show:

- touched files
- touched symbols
- dependents/importers
- likely tests
- syntax checks
- policy gates
- stale context
- secret/path risk
- estimated blast radius

### Progress Update: 2026-07-08

- ~~Added `sourceplan_scorecard(plan)` to the TUI/API client.~~
- ~~Added `beast_sourceplan_scorecard` MCP tool.~~
- ~~Scorecard now reports touched files, selected count, stale count,
  preview hash, syntax checks, suggested pytest commands, policy gates, risk
  reasons, decision, and risk level.~~
- ~~Workbench now shows a compact pre-apply risk panel with reasons and
  suggested tests.~~
- ~~Stale SourcePlans score as high risk and block-until-resolved before disk
  write.~~
- ~~Added tests for test targeting, stale blocking, and MCP scorecard output.~~
- ~~Scorecard now adds local graph-impact analysis: touched symbol candidates,
  dependent/importing files, HTTP route declarations, sensitive path/content
  flags, and graph-derived pytest commands.~~
- ~~Workbench now shows compact impact counts for dependents, routes, and
  symbols alongside the risk decision.~~

### Implementation Plan

1. ~~Add `beast_sourceplan_scorecard(plan)` in API and MCP.~~
2. ~~Partially complete: the first slice uses deterministic SourcePlan preview,
   file paths, syntax checks, and test-path inference.~~
   ~~Second slice adds bounded local import/dependent, route, touched-symbol,
   sensitive-path, and narrower test-command inference.~~
3. ~~Add a pre-apply verification phase:
   - py compile for staged Python content
   - JSON parse where applicable
   - selected tests inferred from paths
   - optional broader test command~~
4. ~~Attach scorecard to the TUI workbench.~~

### Acceptance Criteria

- ~~SourcePlan preview shows `low|medium|high` risk with concrete reasons.~~
- ~~Changed Python files map to at least one suggested pytest command when
  tests exist.~~
- ~~Approval/workbench screen cannot hide failed pre-apply verification.~~

### Remaining Work

1. ~~Enrich impact scoring with graph dependents/importers and touched symbols.~~
2. Partially complete: infer narrower pytest targets from local test/import
   edges; later polish can use explicit symbol/test edges from the daemon graph.
3. ~~Add secret/path risk classifiers to the scorecard reasons.~~

### Status Answer

Workstream 7 is **done for deterministic pre-apply risk plus local graph-impact
analysis**. BEAST now shows pre-apply risk, concrete reasons, syntax checks,
stale-plan blocking, dependent/importer counts, route and sensitive-path
signals, touched symbol candidates, and sharper test suggestions before the
operator approves or applies a SourcePlan.

## Workstream 8: Evidence Convergence

### Problem

BEAST's evidence stack is powerful, but edit evidence should become a first
class crystal/promotion input automatically.

### Target

Every applied SourcePlan emits:

- ~~Chronicle JSON and Markdown with structured SourcePlan operation summaries.~~
- Rollback snapshot.
- ~~Unified evidence packet.~~
- ~~Memory Hull sidecar.~~
- ~~Provider handoff hash and output gate evidence.~~
- ~~Verification receipt.~~
- ~~Optional promotion candidate if verified and source-edit eligible.~~
- ~~Graph update receipt in the evidence packet.~~

### Implementation Plan

1. ~~Extend `_write_patch_chronicle()` to include structured operation summaries,
   changed ranges, old/new hashes, test commands, and graph refresh status.~~
2. ~~Add `SourcePlanEvidencePacket` or reuse `UnifiedEvidencePacket`.~~
3. Feed successful edits into:
   - Capability Registry
   - Meta Tool Commons
   - Tool Laziness
   - Provider Economist
   - ~~Crystal Autopromotion candidate index~~
4. ~~Add negative evidence for failed/stale/rejected SourcePlans.~~

### Acceptance Criteria

- ~~Successful apply creates one complete receipt bundle.~~
- ~~Failed apply creates negative evidence without promotion.~~
- ~~Repeated verified edit patterns become visible in promotion candidates.~~

### Implemented Slice

- ~~Successful SourcePlan applies now write
  `.beast/evidence/sourceplan/<plan_id>.json`.~~
- ~~Evidence packets include preview hash, scorecard, operation summaries,
  verification, rollback path, Chronicle paths, graph refresh receipt, provider
  handoff hash, output gate metadata, and a deterministic evidence hash.~~
- ~~Evidence operation summaries deliberately omit raw `old_text`/`new_text`
  source content and rollback file contents.~~
- ~~Stale/pre-apply failures now write
  `.beast/evidence/sourceplan/<plan_id>.negative.json` with
  `promotion_candidate: false`.~~
- ~~SourcePlan preview rows now preserve Action IR provenance fields so
  evidence packets can connect edits back to the primary edit contract.~~
- ~~Chronicle JSON/Markdown now records preview hash, operation summaries,
  scorecard, verification, and graph refresh status.~~
- ~~Successful SourcePlan applies now write a verified Memory Hull residue under
  `.beast/vault/tasks/` and link it from the unified evidence packet.~~
- ~~Verified SourcePlan applies update
  `.beast/evidence/sourceplan/promotion_candidates.json`; repeated matching
  patterns become `promotion_ready`.~~

### Remaining Work

1. Feed verified edit packets into Capability Registry, Meta Tool Commons, Tool
   Laziness, and Provider Economist.
2. Connect the SourcePlan promotion candidate index to the existing Crystal
   Autopromotion daemon instead of leaving it as a local evidence artifact.
3. Add richer negative evidence for operator rejection and approval timeout, not
   only stale/verification/apply failures.

### Status Answer

Workstream 8 is **done for receipt-bundle convergence and local promotion
visibility**, but not complete overall. Successful SourcePlans now create
Chronicle, rollback, unified evidence, Memory Hull, and promotion-candidate
artifacts; stale SourcePlans create negative evidence. The remaining work is
feeding those artifacts into the wider registry/commons/economics systems.

## Workstream 9: Multi-Repo and Contract Awareness

### Problem

Gortex treats multi-repo workspaces and cross-repo contracts as first-class.
BEAST has Commons Spaces and evidence packaging, but active editing is mostly
single-workspace.

### Target

BEAST should support a workspace registry:

- ~~repo id~~
- ~~root path~~
- ~~trust level~~
- ~~active branch/commit~~
- ~~graph stats~~
- ~~contract artifacts~~
- ~~allowed edit scope~~
- provider/consumer relationships

### Implementation Plan

1. ~~Add `.beast/workspaces.json` or SQLite-backed workspace registry.~~
2. ~~Add graph node field `repo_id`.~~
3. ~~Support context packs that include read-only cross-repo references while
   only applying edits to the approved repo.~~
4. ~~Detect simple contracts:~~
   - ~~HTTP routes~~
   - ~~OpenAPI files~~
   - ~~env vars~~
   - ~~message topics~~
   - ~~CLI commands~~
5. ~~Add contract mismatch receipts as advisory evidence.~~

### Acceptance Criteria

- ~~A task can read context from repo B while editing only repo A.~~
- ~~Contract findings are advisory unless policy requires blocking.~~
- ~~Cross-repo edits require explicit multi-repo approval.~~

### Implemented Slice

- ~~Added `app/kernel/data_processing/workspace_registry.py` with a JSON-backed
  registry at `.beast/workspaces.json`.~~
- ~~Registry records use the same `repo:{root}` repo id convention already
  emitted by `WorkspaceGraph`.~~
- ~~Registered workspaces carry root path, trust level, edit scope, role,
  branch/commit, graph stats, and detected contract artifacts.~~
- ~~Multi-repo context packs mark reference repo records as `read_only` and
  expose an explicit `allowed_edit_repo_id`.~~
- ~~Contract mismatch receipts are advisory and include env/route differences.~~
- ~~Gateway endpoints now expose registry list/register/context-pack and
  contract-mismatch operations.~~
- ~~SourcePlan scope validation blocks edits to read-only reference repos and
  requires explicit multi-repo approval before multiple writable repos can be
  edited.~~
- ~~TUI now has a clickable `Ctrl+W` workspace registry modal that shows
  registered repos, read/write scope, contract counts, and selectable
  read-only reference files.~~
- ~~Registry context refs use `repo_id::path` so selected cross-repo context can
  still be read by the session pipeline while staying visibly read-only.~~

### Remaining Work

1. Add provider/consumer relationship inference from imports, OpenAPI clients,
   route paths, package metadata, and env/topic overlap.
2. Store contract mismatch receipts as Chronicle/Memory Hull evidence when
   they materially affect an edit.
3. Add richer TUI actions for registering an arbitrary reference repo path from
   inside the modal, not only listing repos already in `.beast/workspaces.json`.

### Status Answer

Workstream 9 is **done for the backend registry, advisory contract, edit-scope
enforcement, and TUI visibility slice**. BEAST can now register multiple repos,
build read-only cross-repo context packs, detect basic contracts, emit advisory
mismatch receipts, block cross-repo SourcePlan writes unless explicit multi-repo
approval is present, and let the operator click/select registered workspace
context from the TUI. The next piece is relationship inference and evidence
publication for contract mismatches.

## Workstream 10: Provider Tournament Feedback Loop

### Problem

BEAST has provider tournaments and fitness summaries, but coding workflow
routing should continuously learn from SourcePlan outcomes.

### Target

Provider roles should be updated from real edit outcomes:

- `primary_patch_provider`
- `repair_provider`
- `review_provider`
- `summarizer`
- `local_teacher`
- `fallback_only`

### Implementation Plan

1. ~~Attach SourcePlan success/failure receipts to provider fitness records.~~
2. Score providers by:
   - ~~valid Action IR rate~~
   - ~~output gate pass rate~~
   - ~~patch verification pass rate~~
   - hidden-clean rate
   - ~~latency~~
   - ~~cost/token metadata~~
   - context discipline
   - ~~rollback frequency~~
3. ~~Add "provider route explanation" to the Source Workbench.~~
4. Let local Ollama/Forge routes compete with cloud providers for bounded
   coding tasks.

### Acceptance Criteria

- ~~Provider selector can explain why it chose a model for patch generation.~~
- ~~Providers that produce invalid Action IR or failed/stale SourcePlan outcomes
  get downgraded for edit tasks.~~
- Local routes can win when they have verified crystal evidence.

### Implemented Slice

- ~~Successful SourcePlan evidence packets update
  `.beast/evidence/sourceplan/provider_edit_fitness.json`.~~
- ~~Negative/stale SourcePlan evidence packets also update provider edit
  fitness, so failures affect future routing.~~
- ~~Provider edit fitness tracks attempts, verified applies, failed attempts,
  valid Action IR rate, output-gate pass rate, verification pass rate,
  rollback frequency, latency samples, token totals, and recent outcomes.~~
- ~~Repeated verified Action IR edits can promote a provider to
  `primary_patch_provider`; failed/stale outcomes can move a provider toward
  `fallback_only`.~~
- ~~`sourceplan_scorecard()` now includes `provider_route_explanation` and
  `provider_edit_fitness`, and the Source Workbench renders that route
  explanation before apply.~~
- ~~The Providers page now surfaces SourcePlan edit-fitness role, score,
  attempts, verified/failed counts, rollback count, and route explanation for
  the selected provider.~~

### Remaining Work

1. Blend SourcePlan edit-fitness with tournament model-fitness artifacts and the
   existing provider economist route selector.
2. Add context-discipline scoring based on graph-ranked context use, context
   size, and broad-file fallback frequency.
3. Let local Ollama/Forge routes compete using verified crystal evidence and
   Memory Hull sidecars.
4. ~~Publish provider edit-fitness summaries into the Providers page, not only
   the Source Workbench scorecard.~~

### Status Answer

Workstream 10 is **done for the SourcePlan feedback-loop slice**. BEAST now
learns from real patch outcomes and can explain provider edit fitness inside the
pre-apply workbench and Providers page. The remaining work is merging those
scores into the global provider economist and local route competition.

## Workstream 11: Code Cortex Interop and External Intelligence

### Problem

Building a full Gortex/Serena/Probe-class code graph inside BEAST may be
unnecessary if stronger local code-intelligence engines are available. At the
same time, BEAST should not become dependent on any one engine or allow an
external tool to bypass governance.

### Options

| Option | Pros | Cons | When Valid |
|---|---|---|---|
| Build BEAST graph only | Full control, no dependency | Slower to reach advanced graph features | Always required as baseline |
| Optional Gortex adapter | Fast access to mature graph features | External binary/config dependency | Developer machines that opt in |
| Optional Serena-style symbol adapter | Strong symbol/refactor operations | Requires adapter-specific schema mapping | When symbol-level edits are stable enough to compile into SourcePlan |
| Optional local search adapter | Cheap fallback for unsupported languages | Lower precision than graph/symbol engines | Always useful as a fallback |
| Hard dependency on Gortex | Strong graph features by default | Violates BEAST local self-contained posture | Not recommended |

### Decision

Use optional interop only. BEAST should keep its own minimal graph and normalized
Code Cortex schema, but can learn from or call Gortex, Serena-style symbol
servers, local search engines, and repo-bundle exporters when installed.

The adapter contract is:

- external engines may provide context, symbols, dependents, routes, contracts,
  semantic matches, and diagnostics;
- external engines may propose edit intent;
- only BEAST SourcePlan may preview, approve, apply, verify, roll back, and
  write evidence;
- every adapter call must produce a receipt with engine id, version/command if
  available, query, result count, latency, and fallback path.

### Implementation Plan

1. ~~Add `CodeCortexAdapter` protocol with feature detection and receipts.~~
2. ~~Add optional `GortexAdapter` behind feature detection and map it to the
   real Gortex CLI verbs.~~
3. ~~Add optional `SymbolSurgeonAdapter` for Serena-style symbol lookup/edit
   intent that compiles into Action IR/SourcePlan operations.~~
4. Partially complete: ~~add local fallback adapter for grep/import/symbol
   search~~; semantic search and repo-bundle export remain later slices.
5. Support normalized adapter methods:
   - ~~`search_symbols`~~
   - ~~`get_file_summary`~~
   - ~~`get_editing_context`~~
   - ~~`get_dependents`~~
   - `get_callers`
   - `get_contract_map`
   - `get_semantic_matches`
   - ~~`propose_symbol_edit`~~
   - `verify_change`
6. Partially complete: ~~convert adapter responses into BEAST context/evidence
   receipts for Symbol Surgeon SourcePlans~~; broader context/evidence records
   remain next.
7. ~~Add Code Cortex source labels to Source Workbench impact/risk panels.~~
8. ~~Never let an adapter directly apply edits through BEAST unless routed
   through SourcePlan approval.~~

### Acceptance Criteria

- BEAST runs fully without Gortex, Serena, Probe, Argyph, or vector stores.
- ~~If Gortex is installed, BEAST can use it for richer context.~~
- If a symbol adapter is installed, BEAST can convert a symbol-level edit
  proposal into a SourcePlan preview with old/new hashes and changed ranges.
- If no external adapter is installed, BEAST falls back to its local graph and
  local search adapter.
- All writes still go through BEAST SourcePlan governance.
- Adapter receipts appear in Chronicle/evidence packets for applied or blocked
  SourcePlans.

### Starter Order

1. ~~`CodeCortexAdapter` protocol and receipt schema.~~
2. Partially complete: ~~Gortex read-only adapter for symbols, edit context,
   file summaries via edit context, and dependents~~; richer contract mapping
   remains next.
3. ~~Local fallback adapter so the workflow is testable without external tools.~~
4. ~~Symbol Surgeon bridge from symbol edit intent to Action IR/SourcePlan.~~
5. ~~TUI surfacing: source labels, adapter confidence, and fallback state.~~
6. Evidence closure: adapter receipts inside SourcePlan packets.

### Implemented Slice

- ~~Added `app/kernel/data_processing/code_cortex.py` with a normalized
  adapter contract, adapter receipts, local fallback adapter, optional Gortex
  command wrapper, and `CodeCortexRouter`.~~
- ~~Local Code Cortex now supports symbol search, file summaries, dependent
  import scans, editing context, and symbol-scoped edit proposals.~~
- ~~Symbol Surgeon proposals compile into governed SourcePlans with old/new
  snippets, hashes, Action IR provenance, preview hash, and SourcePlan apply
  policy.~~
- ~~Gateway endpoints now expose Code Cortex status, symbols, file summary,
  dependents, editing context, and symbol-plan creation.~~
- ~~MCP now exposes Code Cortex status/search/dependents and Symbol Surgeon
  SourcePlan creation, with Symbol Surgeon hidden from the `readonly` profile.~~
- ~~Successful and negative SourcePlan evidence packets can carry Code Cortex
  adapter receipts from symbol-surgeon plans.~~
- ~~Installed Gortex `v0.59.1+00aec842` at `/home/byron/.local/bin/gortex`,
  started its daemon, and tracked `/home/byron/EdgeK-BEAST`. Live status showed
  `7149` files, `4` nodes, and `4` edges at the time of mapping.~~
- ~~Mapped `GortexAdapter` to the actual CLI surface: `gortex status`,
  `gortex query symbol`, `gortex query dependents`, and
  `gortex edit context`.~~
- ~~SourcePlan scorecards now include a `graph_impact.code_cortex` section with
  adapter labels, fallback source, dependent files, receipts, queried files, and
  errors.~~
- ~~Source Workbench now displays Code Cortex adapter/fallback/dependent impact
  in the pre-apply risk panel.~~


## Workstream 12: Mode Router and Agent Role Lanes

Status: **Complete for backend/API/MCP/evidence mode routing.** This workstream formalizes the agent-role layer implied by
Roo/Cline/OpenHands-style systems, but keeps BEAST governance authoritative.

### Problem

A single generic coding agent mode is too blunt. Exploration, architecture,
implementation, review, security checks, evidence writing, and budget decisions
need different permissions, context budgets, and verification obligations.

### Target

Add a BEAST Mode Router that maps task phase and risk to explicit roles:

| Mode | Purpose | Tool Profile | Mutation Permission |
|---|---|---|---|
| `scout` | Find files, symbols, tests, routes, and contracts | `readonly` | No writes |
| `architect` | Produce plan, risks, and SourcePlan outline | `readonly` plus planning tools | No writes |
| `debugger` | Read traces, run safe diagnostics, localize fault | `readonly` plus safe verifier tools | No source writes |
| `implementer` | Generate Action IR and SourcePlan operations | `edit` | SourcePlan only |
| `reviewer` | Inspect diffs, risks, tests, and style | `readonly` plus scorecard | No writes |
| `security_gate` | Inspect commands, scripts, hooks, secrets, dependency risk | `ops`/security subset | Blocks unsafe execution |
| `evidence_logger` | Write Chronicle, Memory Hull, and promotion receipts | `evidence` | Evidence only |
| `budget_controller` | Choose local/cloud/provider route | economy subset | No source writes |

### Implementation Plan

1. ~~Add `app/kernel/agents/mode_router.py` with mode definitions,
   permissions, default budgets, and phase transitions.~~
2. ~~Attach mode selection to SourcePlan scorecards and SourcePlan evidence
   packets.~~
3. ~~Map modes to MCP tool profiles and mission-cockpit cards.~~
4. ~~Add route explanation fields:~~
   - ~~selected mode~~
   - ~~why this mode is active~~
   - ~~allowed tools~~
   - ~~blocked tools~~
   - ~~context budget~~
   - ~~escalation threshold~~
5. ~~Require mode transitions before mutation:
   `scout -> architect -> implementer -> reviewer -> evidence_logger`.~~
6. ~~Allow emergency debugger paths, but record them as receipts.~~
7. ~~Let provider edit fitness influence routing evidence for `implementer` or
   `reviewer`.~~

### Acceptance Criteria

- A task can show its current BEAST mode in TUI, MCP, and evidence packets.
- `scout` and `architect` modes cannot call mutating SourcePlan apply tools.
- `implementer` can propose SourcePlans but cannot bypass preview/approval.
- Mode transitions are recorded in Chronicle/evidence.
- Provider route explanations include both provider choice and mode choice.

### Status Answer

Workstream 12 creates BEAST's role brain. It prevents one broad agent role from
owning every phase by giving each phase bounded permissions, budgets, and an
evidence trail.

## Workstream 13: Worktree Forge and Multi-Agent Mission Control

Status: **Complete for Worktree Forge create/list/status/diff/test/promote/archive gates.** This workstream turns worktree-first agent orchestration
patterns into BEAST's safe workspace mutation layer.

### Problem

Direct edits in the active workspace are too risky for parallel agents,
large refactors, dependency changes, cross-repo tasks, or provider experiments.
BEAST needs isolated task workspaces with visible state, diff, verification,
rollback, and merge readiness.

### Target

Add Worktree Forge:

- one branch/worktree per risky or parallel mission;
- session records for agents, terminals, mode transitions, diffs, tests, and
  evidence;
- safe merge/apply gates back into the approved workspace;
- automatic cleanup/archive of abandoned worktrees;
- optional parallel provider attempts on separate branches.

### Implementation Plan

1. ~~Add `app/kernel/workspaces/worktree_forge.py`.~~
2. ~~Add `.beast/worktrees/tasks.json` or SQLite-backed task/worktree
   registry.~~
3. ~~Add CLI/API/MCP operations:~~
   - ~~`beast_worktree_create`~~
   - ~~`beast_worktree_list`~~
   - ~~`beast_worktree_status`~~
   - ~~`beast_worktree_diff`~~
   - ~~`beast_worktree_test`~~
   - ~~`beast_worktree_promote`~~
   - ~~`beast_worktree_archive`~~
4. Partially complete: ~~recommend worktree isolation for high-risk
   scorecards, multi-file edits, dependency/config changes, and cross-repo
   context~~; automatic create/apply routing remains next.
   - ~~multi-file edits;~~
   - ~~dependency or package changes;~~
   - bootstrap/setup tasks;
   - ~~cross-repo context;~~
   - ~~high-risk SourcePlan scorecards;~~
   - parallel provider tournaments;
   - long campaign plans.
5. ~~Add mission-cockpit session cards showing branch, worktree path, active
   mode, provider, dirty files, tests, risk, and evidence status.~~
6. ~~Add merge-gate checks: explicit approval, passing tests, target branch,
   and clean committed worktree state.~~
7. ~~Add evidence receipts for archived, tested, promoted, and blocked
   worktrees.~~

### Acceptance Criteria

- BEAST can create a task worktree without mutating the main workspace.
- A risky SourcePlan is proposed and verified inside the worktree first.
- TUI shows worktree status, dirty files, active mode, and test state.
- Promotion back to the main workspace requires approval and evidence closure.
- Parallel provider attempts do not collide because each runs in its own branch.

### Status Answer

Workstream 13 gives BEAST its safe workshop. Agents can edit, test, and review
inside isolated worktrees while the main repo remains clean, reversible, and
protected by promotion gates.

## Workstream 14: Spec Covenant and AGENTS.md Governance

Status: **Complete for scoped rule digest, handoff, scorecard, and evidence closure.** This workstream absorbs AGENTS.md and spec-kit lessons into
BEAST's task-envelope and PREC lifecycle.

### Problem

Project-local agent instructions are useful, but they can be bloated,
contradictory, stale, over-broad, or unsafe. BEAST should not paste the whole
instruction swamp into every provider call.

### Target

Add a Spec Covenant compiler that converts project rules and task intent into a
small scoped contract:

```text
constitution -> objective -> constraints -> relevant rules -> plan -> tasks
-> SourcePlan batches -> verification -> evidence
```

### Implementation Plan

1. ~~Add `app/kernel/policy/spec_covenant.py`.~~
2. ~~Ingest supported rule sources:~~
   - ~~`AGENTS.md`~~
   - ~~`BEAST_PROJECT.md`~~
   - ~~`.beast/rules/*.md`~~
   - ~~`.beast/rules/*.yaml`~~
   - task-specific operator notes
3. ~~Add bloat/conflict lint for duplicated rules,
   impossible constraints, unsafe setup instructions, stale file/path
   references, and mode permission contradictions.~~
4. ~~Compile a scoped digest per task and selected file/symbol set.~~
5. ~~Attach digest hash to provider handoff, SourcePlan scorecard, Chronicle,
   and positive/negative SourcePlan evidence packets.~~
6. ~~Show rule inclusion/pruning/conflict state through mission-cockpit summary
   and SourcePlan scorecard payloads.~~
7. ~~Add a `spec_to_sourceplan_batches()` helper for long campaigns.~~

### Acceptance Criteria

- BEAST can ingest AGENTS.md without loading the whole file into every prompt.
- The provider handoff includes only scoped, relevant rules.
- Conflicting or unsafe rules are flagged before provider escalation.
- Evidence packets record the exact rule digest used for an edit.
- Long tasks can be broken into SourcePlan batches that preserve the same
  covenant.

### Status Answer

Workstream 14 gives BEAST a constitution compiler. Repository instructions
become scoped rules with receipts, pruning, and explicit lint warnings.

## Workstream 15: Safety Governor and Bootstrap Quarantine

Status: **Complete for command/file scan, scorecard, handoff, and evidence closure.** This workstream makes BEAST cautious in the useful way:
not panicky, but unwilling to trust accidental `curl | bash` bootstrap paths.

### Problem

Agentic coding tools can be tricked into running setup scripts, package hooks,
networked installers, unknown binaries, or destructive commands. BEAST needs a
mandatory pre-execution receipt for unknown or risky commands.

### Target

Add a Safety Governor that scores and gates:

- shell commands;
- install/setup/bootstrap scripts;
- package manager lifecycle hooks;
- networked command execution;
- unknown binaries;
- secret exposure;
- destructive filesystem operations;
- permission changes;
- environment-variable exfiltration risk.

### Implementation Plan

1. ~~Add `app/kernel/security/safety_governor.py`.~~
2. Partially complete: ~~add command classifier for high-risk patterns:
   `curl ... | bash`, `wget ... | sh`, `sudo`, `su`, `chmod -R`, `chown -R`,
   `rm -rf`, `dd`, raw disk writes, base64 decode plus execute, outbound
   network plus shell execution, package install commands, and unknown repo
   binaries.~~ Lifecycle hook detection is implemented through file scanning.
3. ~~Add package-file scanners for `package.json`, shell
   scripts, Dockerfiles, compose files, Makefiles, setup files, and CI
   workflows.~~
4. ~~Add quarantine modes:~~
   - ~~allow;~~
   - ~~warn;~~
   - ~~require approval;~~
   - ~~sandbox/worktree only;~~
   - ~~block.~~
5. ~~Attach safety receipts to provider handoff, SourcePlan scorecard,
   Chronicle, positive/negative evidence packets, and mission-cockpit cards.~~
6. ~~Add Safety Radar data through mission-cockpit summary with command/file
   risk, hook risk, and override fields.~~
7. ~~Ensure local diagnostics and tests can still run when they are low risk.~~

### Acceptance Criteria

- Dangerous setup commands are blocked or require explicit approval.
- Safety decisions include concrete reasons, not vague warnings.
- High-risk commands are automatically redirected to a worktree/sandbox when
  possible.
- Operator overrides are recorded with timestamp, task id, and reason.
- Safety receipts appear in evidence for both successful and blocked missions.

### Status Answer

Workstream 15 gives BEAST an immune system. It lets agents work, but it does not
let them lick mysterious shell scripts off the internet floor.

## Workstream 16: Compute Forge Agent Scheduler

Status: **Complete for scheduler planning, receipts, scorecards, and cockpit summary.** This workstream connects agent orchestration patterns to
BEAST's local-first compute economy.

### Problem

BEAST has provider fitness and local compute evidence, but local agent capacity
is not yet treated as a schedulable resource. The system should decide when a
local scout, local verifier, local summarizer, cloud implementer, or parallel
reviewer should run based on cost, risk, latency, and past evidence.

### Target

Add a scheduler that treats local and remote agents as capacity lanes:

- local CPU scout;
- local grep/symbol/retrieval worker;
- local verifier/test runner;
- local summarizer/compressor;
- cloud architect/implementer only when justified;
- parallel reviewer when risk is high;
- repair provider when verification fails.

### Implementation Plan

1. ~~Add `app/kernel/compute/agent_scheduler.py`.~~
2. ~~Track available lanes for local CPU scout, Code Cortex
   retrieval, local verifier, local summarizer, crystal replay, provider
   architect/implementer, and parallel reviewer.~~
3. ~~Add route policies:~~
   - ~~scout locally first;~~
   - ~~verify locally first;~~
   - ~~summarize locally first;~~
   - ~~escalate architecture/editing only when graph confidence or local
     fitness is too low;~~
   - ~~use parallel cloud/local attempts only for high-value/high-risk
     missions.~~
4. ~~Attach scheduler outcomes to SourcePlan scorecards and evidence packets.~~
5. ~~Add Compute Forge panel data through mission-cockpit summary:~~
   - ~~active lanes;~~
   - ~~queued/recent jobs;~~
   - ~~local/cloud split;~~
   - ~~cost avoided;~~
   - ~~route explanation.~~
6. ~~Record scheduler receipts with local/cloud split and cost-avoided
   estimates.~~

### Acceptance Criteria

- BEAST can explain why a task stayed local or escalated to a provider.
- Local scout/verifier/summarizer lanes run before cloud calls by default.
- Scheduler records cost/latency and verification outcome per lane.
- Provider Economist consumes scheduler evidence.
- Local crystal replay can win routing for repeated edit patterns.

### Status Answer

Workstream 16 gives BEAST a compute scheduler. Cloud calls become deliberate
escalations; local compute gets the first route whenever it has enough evidence
and capability.

## Workstream 17: Mission Control Cockpit and IDE Workspace UX

Status: **Complete for mission summary API, shared cockpit data model, and the
first dedicated TUI cockpit.** Web/IDE cockpit surfaces remain future consumers
of the same summary API. This workstream turns the TUI/Web UI from a collection
of useful pages into a live workspace cockpit.

### Problem

BEAST has many strong lanes, but they can feel parallel: graph, SourcePlan,
providers, evidence, workspaces, safety, modes, compute economy, and PREC. The
operator needs one cockpit that shows mission state without drowning in logs.

### Target

Add a Mission Control Cockpit with compact, clickable cards:

- Active Missions;
- Agent Modes;
- Worktrees;
- SourcePlan Queue;
- Risk Radar;
- Safety Governor;
- Compute Economy;
- Code Cortex;
- Provider Fitness;
- Evidence Stream;
- PREC Lifecycle;
- Promotion Candidates.

### Implementation Plan

1. ~~Added a dedicated `MissionCockpitScreen` that consumes the completed
   shared summary API.~~
2. ~~Add mission summary API with active modes, active
   worktrees, Safety Governor receipt, Spec Covenant digest, Agent Scheduler
   summary, Code Cortex status, cockpit cards, blockers, SourcePlan queue, and
   evidence stream.~~
3. ~~Expose cockpit navigation targets through API payloads for mission,
   SourcePlan, worktree diff, safety receipt, evidence packet, and
   promote/rollback/archive surfaces.~~
4. ~~Add status chips and meters:~~
   - ~~tests passed/failed;~~
   - ~~risk low/medium/high;~~
   - ~~local/cloud split;~~
   - ~~context tokens avoided;~~
   - ~~worktree dirty/clean;~~
   - ~~evidence open/closed.~~
5. Keep the web cockpit as a later surface that consumes the same mission API.
6. ~~Wired `Ctrl+O` and the command palette to open the mission cockpit from
   the TUI.~~
7. ~~Added cockpit section selection, click-to-select rows, refresh, and
   drilldown into overview, blockers, worktrees, SourcePlans, evidence, and
   governance receipts.~~
8. ~~Added focused TUI tests for cockpit rendering and section navigation.~~

### Acceptance Criteria

- ~~The operator can see all active missions from one screen.~~
- ~~Every card links to or drills into the relevant BEAST surface data:
  workbench, diff, safety, provider, evidence, or worktree.~~
- ~~Mission state updates from the shared summary API after apply, rollback,
  verification, and graph refresh.~~
- ~~The cockpit shows what is blocked and why.~~
- ~~The cockpit can be used without launching an embedded terminal
  multiplexer.~~

### Status Answer

Workstream 17 gives BEAST its mission cockpit. The operator can press `Ctrl+O`
or use the command palette to see modes, worktrees, risk, safety, compute,
Code Cortex, SourcePlan queue, evidence, and blocked states before approving
the next action.

### Full IDE Phase 1: VS Code Shell With TUI Look

Status: **In progress / first slice implemented.**

BEAST's first full IDE step is not a separate editor rewrite. It is a VS Code
operator shell that preserves the BEAST TUI visual language while placing the
governed workflow beside the code:

- `/edgek/ide/snapshot` now provides a presentation-friendly IDE contract over
  Mission Cockpit, Code Cortex, Evidence Bus, Mission Lattice, worktrees, and
  ADR state.
- The VS Code extension registers a `Mission Control` view backed by that
  snapshot instead of manually rebuilding cockpit state.
- `BEAST: Open Mission Control` opens an in-editor webview using the TUI
  palette, compact cards, explicit operator actions, and the same
  governance-first flow.
- `BEAST: SourcePlan from Selection` turns the current editor selection into a
  governed SourcePlan objective, then opens the Source Workbench.
- `BEAST: Open Source Workbench` shows policy gate decision, risk, lattice
  replay status, rollback/worktree recommendation, and suggested verification
  before preview/apply.
- `BEAST: Show Evidence Bus`, `BEAST: Create Worktree Mission`, and
  `BEAST: Scaffold Lattice Replay` expose the newly integrated BEAST layers
  directly from the IDE.

Next IDE slices should add real diff decoration inside editor buffers,
clickable hunk selection, persistent SourcePlan sessions, a file explorer
overlay from Code Cortex, and end-to-end VS Code extension tests. The principle
stays the same: IDE ergonomics improve, but SourcePlan and policy receipts stay
the mutation authority.

## Phased Roadmap

### Phase 0: Stabilize Current SourcePlan Loop

Duration: 1-2 days.

- Add structured diff data while preserving existing diff text.
- Add tests for changed ranges and selected hunk state.
- Add post-apply file confirmation data to apply result.
- Update SourcePlan docs and TUI labels so "edits are allowed" is unambiguous.

### Phase 1: Source Workbench

Duration: 3-5 days.

- Build `SourceWorkbenchScreen`.
- Show files, hunks, code, diff, hash, risk, approval, apply, rollback.
- Wire existing `f`, `u`, `z`, `y`, `v` commands into the workbench.
- Keep legacy modals until the workbench is stable.

### Phase 2: Action IR First

Duration: 4-7 days.

- Update handoff prompts and provider output parsing.
- Compile Action IR through `action_resolver.py`.
- Prefer anchor/symbol edits.
- Add operation provenance and resolver receipts.

### Phase 3: Workspace Graph Upgrade

Duration: 1-2 weeks.

- Add richer indexers and real search.
- Add graph context packs.
- Add stale-context detection.
- Add graph refresh after apply/rollback.
- Expose graph endpoints to TUI and MCP.

### Phase 4: MCP Profiles and Workspace Service

Duration: 1 week.

- Add MCP tool profiles.
- Add tool profile/search.
- Add gateway-backed workspace service.
- Use service as the shared source for TUI/MCP graph reads.

### Phase 5: Evidence and Promotion Closure

Duration: 1-2 weeks.

- Turn every SourcePlan outcome into unified evidence.
- Feed provider economist and capability promotion.
- Add repeated-edit crystal candidates.
- Add provider fitness feedback from valid Action IR and verified applies.

### Phase 6: Code Cortex Interop

Duration: 3-5 days once baseline graph APIs are stable.

- Add `CodeCortexAdapter` protocol.
- Detect local Gortex and other optional code-intelligence engines.
- Map core graph/context/symbol methods.
- Add adapter receipts, source labels, and fallback behavior.
- Keep BEAST edit/apply path authoritative.

### Phase 7: Mode Router

Duration: 3-5 days after MCP profiles are stable.

- Add BEAST modes: Scout, Architect, Debugger, Implementer, Reviewer,
  Security Gate, Evidence Logger, and Budget Controller.
- Map modes to MCP tool profiles and SourcePlan phase gates.
- Add mode route explanations to the TUI, MCP responses, and evidence packets.
- Block mutation from non-implementer modes.

### Phase 8: Worktree Forge

Duration: 1-2 weeks after Code Cortex interop basics.

- Add per-task worktree/session records for risky or parallel edits.
- Add TUI worktree/session cards before embedded terminal multiplexing.
- Run high-risk SourcePlans inside isolated branches before promotion.
- Add branch/worktree promotion, archive, rollback, and negative evidence.

### Phase 9: Spec Covenant and AGENTS.md Governance

Duration: 4-7 days after Mode Router and Worktree Forge are usable.

- Add scoped AGENTS.md/spec ingestion with bloat/conflict lint.
- Compile project rules into task-scoped digests instead of prompt bloat.
- Route long tasks through Spec Covenant -> Code Cortex -> SourcePlan batches.
- Record spec/rule digests in provider handoff and evidence packets.

### Phase 10: Safety Governor and Bootstrap Quarantine

Duration: 4-7 days after Worktree Forge.

- Add shell/package/script risk scanning before setup, install, or bootstrap.
- Add command quarantine modes: allow, warn, approve, sandbox/worktree only,
  block.
- Attach safety receipts to task envelopes, scorecards, and Chronicle.
- Surface Safety Radar in the Source Workbench and Mission Cockpit.

### Phase 11: Compute Forge Agent Scheduler

Duration: 1 week after provider edit-fitness and local evidence are connected.

- Treat local scouts, local verifiers, local summarizers, Ollama routes, cloud
  providers, and crystal replay as schedulable lanes.
- Let local lanes compete before cloud escalation.
- Feed scheduler outcomes into Provider Economist and provider edit-fitness.
- Track local/cloud split, cost avoided, latency, and verification outcomes.

### Phase 12: Mission Control Cockpit

Duration: 1-2 weeks after Worktree Forge and Safety Governor.

- Add a TUI cockpit showing missions, modes, worktrees, SourcePlans, risk,
  safety, compute economy, provider fitness, evidence, and PREC lifecycle.
- Make cockpit cards clickable into workbench, worktree diff, safety receipt,
  evidence packet, and provider route views.
- Add web cockpit later using the same mission summary API.

## Test Plan

### Unit Tests

- Structured diff changed ranges.
- Shadow buffer recomputation.
- Safe path handling.
- Hash drift detection.
- Action IR parse/resolve failures.
- Tool profile allow/deny behavior.
- Workspace graph indexing.

### TUI Tests

- Context picker selects files.
- Workbench opens from SourcePlan.
- Hunk toggle changes selected count and preview hash.
- Verify button surfaces failures.
- Apply button shows post-apply code.
- Rollback refreshes visible code.

### MCP Tests

- `readonly` profile blocks apply.
- `edit` profile exposes SourcePlan flow.
- Tool profile reports hidden/allowed tools.
- SourcePlan preview returns structured hunks.

### Integration Tests

- Build SourcePlan for a temp repo.
- Apply selected anchor edit.
- Run verification.
- Write Chronicle and rollback.
- Refresh workspace graph.
- Roll back and verify file restored.

### Mode Router Tests

- Scout and Architect modes cannot call SourcePlan apply.
- Implementer can propose but not bypass preview/approval.
- Reviewer can inspect scorecards but cannot mutate source.
- Mode transitions are recorded with route reasons.

### Worktree Forge Tests

- Create/list/status/archive worktrees for temporary git repos.
- Risky SourcePlans auto-select isolated worktree mode.
- Parallel provider attempts write to separate branches.
- Promotion back to target workspace requires clean verification.

### Spec Covenant and Safety Tests

- AGENTS.md rules are scoped and pruned by task/file relevance.
- Conflicting rules produce lint warnings before provider handoff.
- Dangerous commands such as networked shell execution are blocked or require
  explicit approval.
- Safety overrides produce evidence receipts.

### Scheduler and Cockpit Tests

- Local scout/verifier lanes run before provider escalation.
- Scheduler records local/cloud route decisions and outcomes.
- Mission cockpit cards reflect current mode, worktree state, risk, safety,
  tests, and evidence closure.

### Proof Harness

- Add a "Gortex-comparison coding loop" benchmark:
  - broad file read baseline
  - BEAST current context picker
  - BEAST graph context pack
  - optional Gortex adapter
  - optional Symbol Surgeon adapter
  - local fallback code search
- Compare:
  - files read
  - tokens included
  - provider calls
  - valid patch rate
  - verification pass rate
  - wall time
  - rollback rate

## Metrics

Track these as first-class receipts:

- `context_files_avoided`
- `context_tokens_avoided`
- `graph_context_tokens`
- `code_cortex_adapter_latency_ms`
- `code_cortex_fallback_rate`
- `symbol_surgeon_edit_rate`
- `agents_md_pruned_tokens`
- `worktree_isolated_edit_count`
- `sourceplan_valid_action_ir_rate`
- `sourceplan_output_gate_pass_rate`
- `sourceplan_apply_success_rate`
- `sourceplan_rollback_rate`
- `pre_apply_stale_block_count`
- `verification_pass_rate`
- `provider_patch_hidden_clean_rate`
- `local_route_patch_success_rate`
- `crystal_reuse_edit_replay_count`
- `mode_transition_count`
- `mode_tool_block_count`
- `worktree_mission_count`
- `worktree_promotion_success_rate`
- `worktree_archive_count`
- `agents_md_rules_pruned`
- `agents_md_conflict_count`
- `spec_covenant_digest_count`
- `bootstrap_command_block_count`
- `safety_override_count`
- `safety_quarantine_count`
- `local_agent_lane_utilization`
- `local_before_cloud_success_rate`
- `scheduler_route_explanation_count`
- `mission_cockpit_open_blocker_count`
- `evidence_time_to_close_ms`

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Graph work grows too large | Delays edit visibility | Build minimal graph first; optional Gortex adapter later |
| Full-file replacement remains default | Noisy diffs and higher risk | Make Action IR first-class and score full-file edits higher risk |
| TUI becomes too complex | Operator confusion | Keep workflow panes simple: files, hunks, code, evidence |
| MCP mutating tools are overexposed | Safety issue | Add profiles and phase gates |
| Provider output remains free-form | Invalid patches | Strict Action IR schema and output gate |
| Optional code-intelligence dependency leaks into core | Deployment fragility | Adapter protocol only, never required |
| Symbol adapter proposes unsafe edits | Source churn or hidden mutation | Convert intent to Action IR/SourcePlan only; no direct writes |
| AGENTS.md/spec ingestion adds context bloat | Higher token spend and conflicting instructions | Lint, prune, and scope rules by task/file |
| Worktree isolation complicates simple edits | Operator friction | Auto-enable only for risky/parallel/cross-repo edits; keep single-workspace fast path |
| Mode routing becomes bureaucratic | Slower simple edits | Use direct fast path for low-risk single-file edits while still recording mode |
| Worktree sprawl | Disk usage and stale branches | Add archive/cleanup policies and dashboard warnings |
| AGENTS.md rules conflict with BEAST policy | Unsafe or confusing provider handoffs | BEAST policy wins; conflicts are linted and scoped |
| Safety Governor false positives | Operator friction | Use allow/warn/approve/block tiers instead of only hard blocks |
| Local agent scheduling overloads CPU | Slow local UX | Add capacity limits, queue visibility, and provider escalation thresholds |
| Cockpit becomes noisy | Operator confusion | Use cards and drill-down views instead of log walls |
| Evidence duplication | Inflated claims | Use one unified evidence packet and negative evidence records |
| Reintegration debt slips past feature work | Architectural drift | Add explicit canonical-owner workstream, deprecation map, receipt index, and cockpit surfacing |

## Architectural Decisions

## Workstream 18: Proof-Carrying Edit Lattice

Status: **In progress. Replay-gated lattice workflow implemented; Source
Workbench polish and feedback economics remain.**

### Problem

BEAST's crystallized compute stack can already reuse durable inference,
semantic credits, KV prefill, proof-local admissions, and crystal evidence. The
new Gortex-adjacent layers add a richer question than prompt reuse:

```text
Have we seen this class of code-change mission before, under a similar graph,
policy, safety, mode, verification, worktree, and provider/local route shape?
```

The upgrade is to make crystallized compute mission-aware. A crystal should not
only mean "cached answer." It should mean "verified edit situation with proof
that this strategy worked under bounded conditions."

### Target

Add a BEAST-native **Mission Crystal Lattice** that records proof-carrying edit
cells from SourcePlan evidence:

- objective terms;
- mode route;
- Spec Covenant hash;
- Safety Governor decision;
- operation shape;
- Code Cortex graph/dependent shape;
- verification shape;
- provider/local route outcome;
- evidence hash;
- promotion eligibility.

The lattice remains advisory. It can recommend replay candidates, strategy
scaffolds, or context hints, but SourcePlan approval, stale checks, verification,
rollback, and Chronicle remain authoritative.

### Implementation Plan

1. ~~Add `app/kernel/compute/mission_crystal_lattice.py` with hash-only mission
   fingerprints, cell storage, lookup, and summary APIs.~~
2. ~~Record verified SourcePlan evidence packets into
   `.beast/compute/mission_lattice/cells.json`.~~
3. ~~Add advisory lattice lookup to SourcePlan scorecards and pass meaningful
   matches into `AgentScheduler` as crystal replay signals.~~
4. ~~Surface mission lattice state in the Mission Cockpit.~~
5. ~~Expose read-only HTTP and MCP surfaces for mission lattice summary and
   lookup.~~
6. ~~Add Source Workbench badges/panels for crystal-backed replay candidates.~~
7. Add stricter blockers for spec-hash drift, safety posture drift, wider graph
   impact, and failed prior verification.
8. ~~Add replay-candidate generation that produces a proposed SourcePlan, never
   a direct write.~~
9. ~~Gate replay candidates through SourcePlan scorecard, policy gate,
   verification plan, and Evidence Bus closure.~~
10. ~~Feed lattice match outcomes back into provider edit fitness and
   local/cloud routing economics.~~

### Acceptance Criteria

- ~~A verified SourcePlan apply records a mission lattice cell without embedding
  raw source.~~
- ~~A later similar SourcePlan can receive a lattice lookup with match strength,
  reuse mode, blockers, and prior evidence hash.~~
- ~~The Agent Scheduler can prefer `crystal_replay` when the lattice finds a
  meaningful match.~~
- ~~Mission Cockpit shows lattice cell counts and proof status.~~
- ~~Lattice replay candidates produce a gated scaffold and still require
  approval, verification, and rollback.~~
- Spec/safety/graph drift can demote or block lattice reuse.

### Status Answer

Workstream 18 turns crystallized compute into a proof-carrying edit memory. The
first slices record verified edit situations as mission lattice cells, query
them during SourcePlan scoring, expose them through HTTP/MCP, and make the
Mission Cockpit aware of the new lattice. The replay-gated slice now adds
`lattice match -> SourcePlan scaffold -> policy gate -> verification plan ->
Evidence Bus closure`, with no auto-apply path.

## Workstream 19: Reintegration and Canonical Ownership

Status: **Planned.** This workstream sits on top of Workstreams 1-18 and exists
to prevent BEAST's older planes, proof engines, compatibility imports, and
parallel route families from drifting away from the new canonical developer
loop.

### Problem

BEAST now has strong new layers: Code Cortex, Mode Router, Worktree Forge, Spec
Covenant, Safety Governor, Agent Scheduler, Mission Cockpit, and Mission Crystal
Lattice. The wider system also contains older and parallel subsystems that were
built for proofs, demos, compatibility, federation, deployment, and local
compute experiments.

The risk is not that these systems are useless. The risk is that they keep
operating as peer authorities:

```text
many compute routers
many evidence stores
many capability registries
many context selectors
many crystal proof engines
many route families
```

The new upgrade must therefore include a reintegration plan: every engine should
either become a canonical owner, an adapter/input to a canonical owner, a
compatibility shim, or a proof/archive harness.

### Audit Findings

The first system audit identified these reintegration targets.

#### Compatibility Imports

These duplicated module names appear to be compatibility shims and should stay,
but new imports should use the canonical paths:

| Compatibility Path | Canonical Path | Action |
|---|---|---|
| `app/kernel/task_envelope.py` | `app/kernel/execution/task_envelope.py` | Mark as compatibility import; ban new direct imports |
| `app/kernel/ollama_scout.py` | `app/kernel/local/ollama_scout.py` | Mark as compatibility import; ban new direct imports |
| `app/kernel/commons_spaces.py` | `app/kernel/networking/commons_spaces.py` | Mark as compatibility import; ban new direct imports |
| `app/kernel/canon_registry.py` | `app/kernel/registry/canon_registry.py` | Mark as compatibility import; ban new direct imports |
| `app/kernel/forensic_memory.py` | `app/kernel/storage/forensic_memory.py` | Confirm shim status and mark |
| `app/kernel/insight_compiler.py` | `app/kernel/data_processing/insight_compiler.py` | Confirm shim status and mark |
| `app/kernel/beast_cli_executor.py` | `app/kernel/deployment/beast_cli_executor.py` | Confirm shim status and mark |

#### Compute Routing Overlap

The following systems all influence local/cloud routing, replay, compute
selection, or proof-local execution:

- `AgentScheduler`;
- `ComputeGovernor`;
- `ComputeLedger`;
- `CrystalRuntimeBoundary`;
- `CrystalReuseGateway`;
- `MissionCrystalLattice`;
- `AdaptiveDispatcher`;
- `LocalRouteOptimizer`;
- `InferenceEngineFabric`;
- `ComputeForge`;
- `DistributedForgeScheduler`.

Canonical owner: **Agent Scheduler**.

Rule: all future routing decisions should produce one `AgentScheduler` receipt.
The other engines should become inputs, adapters, or execution backends.

#### Code Intelligence Overlap

The following systems all participate in repo context selection:

- `CodeCortexRouter`;
- `WorkspaceGraph`;
- `WorkspaceGraphService`;
- `ContextPacket`;
- `OllamaScout`;
- Gortex adapter;
- local code indexers.

Canonical owner: **Code Cortex**.

Rule: the graph, Gortex, local extractors, and future semantic engines provide
signals. Code Cortex is the query front door. Context Packet is an output
format, not a competing selector.

#### Evidence Overlap

The following systems all write or summarize proof:

- SourcePlan unified evidence packet;
- Chronicle;
- Memory Hull;
- Mission Crystal Lattice;
- Agent Scheduler receipts;
- Safety Governor receipts;
- Spec Covenant receipts;
- Worktree Forge receipts;
- Provider edit fitness;
- Crystal evidence bridge;
- Unified crystallized compute evidence packet;
- Compute ledger;
- Commons evidence.

Canonical owner: **Evidence Bus / Receipt Index**.

Rule: every durable proof artifact should register a small pointer receipt in
one index. The artifact remains in its native store, but cockpit/MCP/query tools
should read from the index first.

#### Capability and Commons Overlap

The following systems all describe capability, skills, reuse, or exchange:

- `CapabilityRegistry`;
- `SkillRegistry`;
- `SkillTree`;
- `CapabilityExchange`;
- `MetaToolCommons`;
- `PluginMarketplace`;
- `CommonsSpaces`;
- `FederatedCommons`.

Canonical owner: **Capability Plane**.

Rule: registry, skills, plugins, commons, and exchange should be exposed through
one facade before they affect routing or promotion.

#### Policy and Safety Overlap

The following systems all gate behavior:

- `ModeRouter`;
- `SpecCovenant`;
- `SafetyGovernor`;
- `AgentPassport`;
- `OutputGovernor`;
- deterministic allowlists/executor;
- SourcePlan policy gates.

Canonical owner: **Policy Gate Result**.

Rule: all gates should emit or normalize to a shared decision shape:

```json
{
  "decision": "allow | warn | require_approval | sandbox_only | block",
  "mutation_allowed": false,
  "reasons": [],
  "receipts": {}
}
```

### Target Architecture

Reintegration should leave BEAST with this ownership map:

```text
Code work/context          -> Code Cortex
Mutation                   -> SourcePlan
Isolation/promotion        -> Worktree Forge
Policy/safety              -> Policy Gate Result
Compute route planning     -> Agent Scheduler
Crystal edit memory        -> Mission Crystal Lattice
Evidence discovery         -> Evidence Bus
Operator view              -> Mission Cockpit
External surfaces          -> HTTP/MCP/TUI adapters
Legacy/proof systems       -> adapters, inputs, or archived harnesses
```

### Implementation Plan

1. **Ownership Manifest**
   - ~~Add `docs/beast-canonical-ownership.md`.~~
   - ~~List canonical owners, compatibility shims, adapters, proof harnesses,
     and deprecated import paths.~~
   - ~~Add a route-family ownership table for `app/main.py`.~~

2. **Compatibility Shim Markers**
   - ~~Add explicit `DEPRECATED_COMPAT_IMPORT` comments/docstrings to
     top-level compatibility modules.~~
   - ~~Add a lightweight test or script that flags new imports from shim paths.~~

3. **Evidence Bus / Receipt Index**
   - ~~Add `app/kernel/evidence/evidence_bus.py`.~~
   - ~~Start with pointer receipts for SourcePlan evidence packets.~~
   - ~~Register Agent Scheduler route receipts in the shared index.~~
   - ~~Register Mission Crystal Lattice cells in the shared index.~~
   - ~~Register Spec Covenant receipts in the shared index.~~
   - ~~Register Safety Governor command/workspace receipts in the shared index.~~
   - ~~Register Worktree Forge create/test/promote/archive receipts in the
     shared index.~~
   - ~~Register SourcePlan Chronicle records in the shared index.~~
   - ~~Register SourcePlan Memory Hull sidecar receipts in the shared index.~~
   - ~~Add HTTP/MCP read-only summary surface.~~
   - ~~Make Mission Cockpit read evidence status from the index before falling
     back to filesystem discovery.~~
   - ~~Add lookup/filter surfaces for task id, plan id, artifact type, source,
     status, receipt id, and related evidence.~~

4. **Agent Scheduler Consolidation**
   - ~~Move `AdaptiveDispatcher` lattice-routing signals behind
     `AgentScheduler` as advisory route inputs.~~
   - ~~Treat `CrystalRuntimeBoundary`, `LocalRouteOptimizer`,
     `InferenceEngineFabric`, and Provider Economist as route inputs.~~
   - ~~Record route-input summaries in scheduler receipts.~~
   - Continue replacing direct legacy planner calls with scheduler-mediated
     decisions where they still exist.

5. **Code Cortex Consolidation**
   - ~~Make Gortex and local code indexers feed Code Cortex as read adapters.~~
   - ~~Keep `ContextPacket` as a packaging format enriched by Code Cortex.~~
   - ~~Route TUI/MCP context selection through Code Cortex by default.~~
   - ~~Route `/edgek/workspace/context` through Code Cortex as the context front
     door while preserving graph-context payloads.~~
   - ~~Migrate lower-level workspace search, vector search, semantic context,
     and legacy MCP graph lookup surfaces so they present Code Cortex as the
     context front door while preserving graph adapters underneath.~~
   - Continue migrating artifact-memory helper endpoints into Code Cortex
     adapter calls.

6. **Policy Gate Normalization**
   - ~~Add shared `PolicyGateResult` schema/helper.~~
   - ~~Normalize Mode Router, Spec Covenant, Safety Governor, and SourcePlan
     gates into the shared shape.~~
   - ~~Normalize Output Governor and Agent Passport gates into the shared
     shape.~~
   - ~~Use the shared result in Source Workbench and Mission Cockpit.~~

7. **Capability Plane Facade**
   - ~~Add a facade that reads local registry, skill tree, plugin marketplace,
     capability exchange, and Commons candidates.~~
   - ~~Expose the facade through HTTP, MCP, CLI API, and the TUI snapshot.~~
   - ~~Route Agent Scheduler inputs, SourcePlan scorecards, and Mission Cockpit
     summaries through CapabilityPlane by default.~~
   - Continue replacing remaining one-off promotion callers with CapabilityPlane
     queries.

8. **Route Modularization**
   - Split `app/main.py` route families into modules once canonical ownership is
     stable:
     - ~~`routes/sourceplan.py`;~~
     - ~~`routes/compute.py`;~~
     - `routes/crystal.py`;
     - ~~`routes/workspace.py`;~~
     - ~~`routes/commons.py`;~~
     - ~~`routes/policy.py`;~~
     - ~~`routes/cockpit.py`.~~
   - ~~Extract scheduler visibility, Mission Cockpit, Mission Lattice, lattice
     replay, and Evidence Bus endpoints into `app/routes/cockpit.py`.~~
   - ~~Extract mode router, Spec Covenant, and Safety Governor endpoints into
     `app/routes/policy.py`.~~
   - ~~Extract SourcePlan scorecard/preview/verify/apply/replay surfaces into
     `app/routes/sourceplan.py`.~~
   - ~~Extract compute and Crystal Compute surfaces into
     `app/routes/compute.py`.~~
   - ~~Extract workspace, Code Cortex, registry, and worktree surfaces into
     `app/routes/workspace.py`.~~
   - ~~Extract high-use Meta Tool Commons, Commons Spaces, economy, policy, and
     federated Commons surfaces into `app/routes/commons.py`.~~
   - ~~Deduplicate active route table so mounted route modules own stable paths
     ahead of inline compatibility shadows.~~
   - ~~Retire migrated inline workspace, Code Cortex, worktree, compute, and
     Crystal Compute route bodies from `app/main.py`; those paths now resolve
     directly through route modules.~~
   - Preserve route paths for compatibility.

11. **Final Replay Gauntlet**
   - ~~Add an end-to-end replay proof that seeds verified SourcePlan evidence,
     requests a SourcePlan scorecard over HTTP, builds Code Cortex-fronted
     workspace context over HTTP, scaffolds Mission Lattice replay over HTTP,
     scaffolds the same replay over MCP, and renders the Source Workbench
     replay/policy panel in the TUI path.~~
   - ~~Assert replay remains non-destructive (`no_auto_apply`) while evidence,
     policy, verification, and operator-visible lattice context remain
     connected.~~

9. **Worktree Enforcement**
   - ~~Upgrade worktree recommendations into hard gates for high-risk edits
     unless the operator explicitly overrides.~~
   - ~~Record override receipts in the Evidence Bus.~~

10. **Cockpit Reintegration View**
    - ~~Add a Mission Cockpit section for "Reintegration Health":~~
      - ~~duplicate shim imports;~~
      - ~~orphaned/unexpected receipt count;~~
      - ~~route families without canonical owner;~~
      - engines not feeding canonical owners;
      - proof harnesses not registered as archived/proof-only.

### Acceptance Criteria

- Every major route family has a canonical owner.
- Every duplicated module name is documented as either a compatibility shim or a
  refactor target.
- SourcePlan evidence, Chronicle, Memory Hull, Scheduler, Safety, Spec,
  Worktree, and Mission Lattice receipts are visible through one Evidence Bus.
- Agent Scheduler is the only planner that decides local/cloud/crystal/provider
  route order.
- Code Cortex is the only front door for graph/code context.
- Mission Cockpit can show reintegration health, shim-import drift, evidence
  coverage gaps, and route-ownership gaps.
- High-risk SourcePlan applies either run through Worktree Forge or record an
  explicit override receipt.

### Status Answer

Workstream 19 prevents the new upgrade layers from becoming another parallel
stack. It turns the audit findings into explicit ownership rules and gives BEAST
a reintegration path: canonical owners, compatibility shims, one evidence index,
one compute planner, one code-intelligence front door, one policy result shape,
and cockpit visibility for architectural drift.

### ADR-001: BEAST remains governance-first

Status: Accepted/Implemented.

Decision: BEAST will not become a pure code graph engine. It will add
graph-native context and edit ergonomics while preserving SourcePlan,
approval, verification, rollback, Chronicle, Memory Hull, and promotion as the
authoritative mutation path.

Trade-off: BEAST will not match Gortex's graph depth immediately. In exchange,
BEAST keeps stronger operator control and auditability.

### ADR-002: Workspace graph is advisory, receipts are authoritative

Status: Accepted/Implemented.

Decision: The graph can accelerate context selection and risk scoring, but
append-only receipts and rollback snapshots remain the source of truth.

Trade-off: Some graph state may lag. This is acceptable because apply-time hash
checks and verification block stale writes.

### ADR-003: Optional Code Cortex adapters, no hard dependency

Status: Accepted/Implemented.

Decision: BEAST may call Gortex, Serena-style symbol servers, local search
engines, or repo-bundle exporters for richer graph/symbol/semantic context when
available, but must run without them and must route all writes through BEAST
SourcePlan.

Trade-off: Optional interop adds adapter complexity. It avoids making BEAST
dependent on a separate binary or a single code-intelligence project.

### ADR-004: Action IR becomes the primary provider edit contract

Status: Accepted/Implemented.

Decision: Providers should return compact Action IR rather than full-file patch
prose. BEAST compiles Action IR into explicit operations after validation.

Trade-off: Provider prompts and validators become stricter. The payoff is more
visible, targeted, and reversible edits.


### ADR-005: Agent modes are permission boundaries

Status: Accepted/Implemented.

Decision: BEAST modes are not cosmetic labels. Each mode defines available tools,
mutation permissions, context budgets, escalation thresholds, and evidence
requirements.

Trade-off: Some workflows require explicit mode transitions. The payoff is that
agents cannot accidentally mutate source while operating in exploration,
planning, review, or evidence phases.

### ADR-006: Risky edits default to worktree isolation

Status: Accepted/Implemented.

Decision: BEAST should automatically route high-risk, multi-file, dependency,
bootstrap, cross-repo, and parallel-provider tasks into isolated worktrees before
promotion to the main workspace.

Trade-off: Worktrees add disk and workflow overhead. The payoff is safer
parallelism, cleaner rollback, and auditable promotion.

### ADR-007: Project instructions are compiled, not pasted

Status: Accepted/Implemented.

Decision: AGENTS.md, BEAST rules, and task notes must be linted, scoped, and
compiled into a digest before provider handoff. Providers receive the relevant
rules, not the whole instruction archive.

Trade-off: Rule compilation adds a preflight step. The payoff is lower context
bloat, fewer conflicts, and evidence that identifies which rules shaped the
edit.

### ADR-008: No implicit trust in setup/bootstrap commands

Status: Accepted/Implemented.

Decision: Any setup, install, bootstrap, package hook, or networked shell command
suggested by a repo or agent must pass Safety Governor checks before execution.

Trade-off: Some legitimate commands require approval. The payoff is preventing
agent-assisted workspace compromise before it happens.

### ADR Enforcement Surface

These ADRs are now implemented as runtime-visible contracts:

- `app/kernel/policy/architecture_decisions.py` exposes the accepted ADR
  register and per-surface architecture contract receipts.
- `/edgek/architecture-decisions` and MCP `beast_architecture_decisions` expose
  the accepted/implemented decision register.
- SourcePlan scorecards and Source Workbench views include
  `architecture_contract` receipts covering governance-first mutation,
  receipt authority, optional Code Cortex adapters, Action IR, mode boundaries,
  worktree isolation, compiled Spec Covenant instructions, and Safety Governor
  bootstrap checks.
- Provider handoffs instruct models to return compact Action IR and preserve
  SourcePlan as the local mutation compiler.
- Positive and negative SourcePlan evidence packets include the architecture
  contract through `sourceplan_governance_receipts`.
- Safety Governor command/workspace receipts attach ADR-008 so setup,
  bootstrap, install, package-hook, and networked command checks are explicitly
  tied to the no-implicit-trust decision.

## Definition of Done

The upgrade is successful when an operator can:

1. Start BEAST in a repo.
2. Ask for a code change.
3. Let BEAST graph-rank the relevant files/symbols.
4. See the selected context and risk before provider escalation.
5. Receive an Action IR-backed SourcePlan.
6. Inspect exact changed lines in a code workbench.
7. Toggle hunks in a shadow preview.
8. Approve and apply.
9. See verification and the changed file from disk.
10. Roll back if needed.
11. Find Chronicle, Memory Hull, graph refresh, provider fitness, and promotion
    evidence for the outcome.
12. See which BEAST mode handled each phase and which tools were blocked.
13. Run high-risk or parallel work in an isolated worktree.
14. Promote a verified worktree result back through SourcePlan governance.
15. Ingest AGENTS.md/project rules as scoped digests instead of prompt bloat.
16. Block or quarantine unsafe setup/bootstrap commands before execution.
17. Route local scout/verifier/summarizer lanes before cloud escalation.
18. Use the Mission Control Cockpit to see active missions, risk, compute,
    provider route, evidence closure, and blockers from one screen.
19. Record verified SourcePlan outcomes into a proof-carrying mission lattice
    that can advise future routing without bypassing approval or verification.
20. Query a canonical ownership map that identifies which BEAST layer owns each
    major route family, engine, evidence store, and compatibility shim.
21. Use one Evidence Bus / receipt index to discover SourcePlan, Chronicle,
    Memory Hull, Mission Lattice, Scheduler, Safety, Spec, Worktree, provider,
    crystal, and Commons evidence pointers.
22. See reintegration health in the Mission Cockpit, including orphaned route
    families, duplicate shim imports, and engines not feeding canonical owners.
23. Use a VS Code Mission Control shell that preserves the BEAST TUI look while
    exposing SourcePlan, Evidence Bus, lattice replay, worktrees, Code Cortex,
    and policy state beside the active code editor.

At that point BEAST will have absorbed Gortex's best developer-loop lessons and
the strongest adjacent agentic IDE/workspace orchestration patterns without
giving up BEAST's core advantage: governed, evidence-rich, local-first agentic
software work.
