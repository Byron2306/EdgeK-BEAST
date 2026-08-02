# BEAST Next-Level Upgrade Master Plan

**Document version:** 1.0  
**Date:** 18 July 2026  
**Target release concept:** BEAST IDE 4.0, Governed Autonomy Workbench  
**Primary objective:** Complete the declared VS Code daily-driver parity contract, then surpass ordinary editor-agent systems through proof-governed autonomous execution, local-first inference, evidence, and verified reusable compute.

---

## 1. Executive verdict

BEAST is no longer an early IDE prototype.

The supplied backend, IDE, and documentation show a substantial governed development platform with:

- a VS Code-shaped Electron and Monaco workbench;
- multi-root workspaces and target-aware filesystem operations;
- bounded Git, terminal, task, test, LSP, DAP, notebook, SSH, and container capabilities;
- a mediated extension host and declarative/executable extension foundation;
- multi-provider and local-model inference;
- Code Cortex, Context Packet, Workspace Graph, and context-economy systems;
- SourcePlan, Action IR, exact-content guards, approval, rollback, and evidence;
- Worktree Forge for isolated mutation and promotion;
- Safety Governor, Agent Passport, Capability Plane, One-Use Capabilities, Runtime Governor, and policy gates;
- Agent Scheduler, Provider Economist, Quality Cascade, Pathfinder, Conductor, Canon, Chronicle, Sensorium, Memory Hull, and crystal reuse systems;
- a large regression, benchmark, gauntlet, visual-acceptance, and proof-evidence estate.

The central remaining limitation is not a lack of systems. It is that the systems are not yet composed into one canonical, durable, model-directed coding runtime.

The next-level release should therefore pursue two outcomes in parallel:

1. **Finish a clearly defined BEAST VS Code Parity Contract.**
2. **Create a canonical AgentRunEngine that turns BEAST's existing governance, context, tooling, worktrees, verification, evidence, and crystallisation systems into a persistent autonomous coding loop.**

The target is not a decorative clone of VS Code and not a green-skinned imitation of Cursor, Claude Code, or Codex.

The target is:

> **A daily-driver development environment in which autonomous AI work is bounded by explicit authority, performed in an isolated execution target, verified before promotion, attributable through evidence, and eligible for reuse only after proven success.**

---

## 2. Ground-truth corrections before new development

The documentation reflects rapid progress across several days. Before adding more capability, BEAST needs one canonical current-state ledger.

### 2.1 Known documentation and release-state inconsistencies

The following items should be reconciled immediately:

| Item | Current observations | Required correction |
|---|---|---|
| Detailed parity document date | File is dated `2027-07-18`, while the archive timestamp and present work are from `2026-07-18` | Correct the document date to 2026 |
| Local parity assertion count | Documents mention 86/86 and 87/87; the inspected IDE harness has evolved again | Generate counts directly from the running verifier |
| Execution-target results | Documents mention 12/13 and 14/15 under different environments | Report each environment and skip reason separately |
| Extension-host status | An older assessment calls execution incomplete; newer ADRs and fixtures show mediated execution and a passing lifecycle | Mark the old assessment as historical |
| Product version | `package.json`, Electron runtime identity, and renderer release identity differ | Generate one composite build identity |
| Agent mode labels | Acceptance fixtures and current renderer use different historical labels | Assert semantic capabilities, not stale strings |
| Timeout assertions | A verifier expects an exact timeout literal that differs from the current bounded implementation | Test policy bounds and behaviour rather than source strings |
| Canonical imports | Compatibility facades remain beside canonical modules | Enforce canonical imports and deprecation deadlines |
| Release evidence | Some checks are structural, some local-live, some environment-gated, and some fully external | Tag evidence by verification class |

### 2.2 Establish one generated build identity

Create a root-level generated file:

```json
{
  "product": "BEAST IDE",
  "product_version": "4.0.0-dev",
  "renderer_version": "4.0.0-dev",
  "desktop_runtime_version": "0.2.0",
  "backend_api_version": "4",
  "agent_contract_version": "1",
  "sourceplan_schema_version": "1",
  "sensorium_schema_version": "1",
  "git_commit": "<commit>",
  "git_dirty": false,
  "build_timestamp": "<utc>",
  "release_id": "BEAST-IDE-4.0.0-DEV-<shortsha>"
}
```

Every surface should read this generated identity:

- Electron About dialog;
- renderer release guard;
- backend `/health` and `/version`;
- evidence packets;
- AgentRun receipts;
- parity reports;
- crash reports;
- installer metadata;
- update manifests;
- benchmark bundles.

No component should independently invent a version string.

---

## 3. Define what “100% VS Code parity” means

Literal parity with all VS Code behaviour, all operating systems, and the entire Marketplace is not a defensible finish line. VS Code has a huge extension API, multiple extension hosts, years of adapter-specific behaviour, remote servers, profiles, accessibility paths, and a production population that BEAST cannot reproduce by counting routes.

BEAST should instead publish and complete a measurable contract.

# BEAST Parity Contract 1.0

A capability reaches 100% only when all four layers pass:

1. **Surface:** the user can discover and operate the capability.
2. **Contract:** a bounded main-process or backend interface owns the capability.
3. **Acceptance:** the complete user journey is automatically tested.
4. **Operational proof:** the relevant real runtime or external target is exercised.

### 3.1 Parity tiers

| Tier | Definition | Release requirement |
|---|---|---|
| P1: Daily-driver parity | Common edit, search, Git, task, test, debug, terminal, notebook, remote, extension, and AI journeys | 100% required |
| P2: Protocol parity | Declared LSP, DAP, notebook, testing, task, SCM, and target contracts behave consistently | 100% of published support matrix |
| P3: Operational parity | Local, SSH, and Dev Container matrices run in CI and soak environments | 100% of required environments |
| P4: Extension compatibility | A documented subset of VS Code extension APIs and contribution points works | 100% of published subset |
| P5: BEAST superiority | Governed autonomy, evidence, exact mutation, verified reuse, local-first routing, and proof bundles | Mandatory differentiator |

### 3.2 Explicit non-goals

BEAST 4.0 should not claim:

- compatibility with every VS Code Marketplace extension;
- identical undocumented VS Code internals;
- complete parity with every debugger, language server, notebook renderer, and test framework;
- automatic execution of arbitrary extension code;
- silent remote fallback to local execution;
- unrestricted AI terminal or filesystem authority;
- verified crystal reuse without exact evidence and policy compatibility.

### 3.3 The honest release statement

A defensible release claim is:

> **BEAST IDE 4.0 completes the BEAST Parity Contract for its published daily-driver, protocol, execution-target, and extension-compatibility matrices. It adds proof-governed autonomous coding, evidence-backed promotion, and verified reusable compute beyond the ordinary VS Code workflow.**

---

## 4. North-star operator journey

The complete journey must be one uninterrupted product experience:

```text
Install and launch
    ↓
Open or clone repository
    ↓
Select workspace roots
    ↓
Review workspace trust and execution target
    ↓
Restore profile, layout, terminals and prior sessions
    ↓
Index repository and build Workspace Graph
    ↓
Edit, search, navigate and refactor with LSP
    ↓
Run terminals, tasks, tests, notebooks and debuggers
    ↓
Use Git across working tree, index, branches, history and conflicts
    ↓
Ask BEAST in Ask, Edit or Agent mode
    ↓
Review exact context manifest and authority
    ↓
Agent plans, inspects, invokes tools, edits a worktree and verifies
    ↓
Failures return to the same run for bounded repair
    ↓
Final worktree diff becomes a SourcePlan
    ↓
Operator reviews hunks, evidence, risk and test results
    ↓
Promote or reject
    ↓
Collect evidence and rollback material
    ↓
Evaluate verified outcome for Chronicle, skill or crystal promotion
```

Every arrow must have:

- explicit UI state;
- a canonical owner;
- a cancellation path;
- a recovery path;
- an evidence record;
- a regression test.

---

## 5. Target platform architecture

```text
┌───────────────────────────────────────────────────────────────────┐
│                         BEAST IDE Workbench                       │
│ Explorer · Editor · Git · Search · Test · Debug · Terminal · AI │
└───────────────────────────────┬───────────────────────────────────┘
                                │ typed preload IPC
┌───────────────────────────────▼───────────────────────────────────┐
│                     Desktop Service Plane                         │
│ Workspace · Git · LSP · DAP · Tasks · Tests · PTY · Extensions │
│ SSH · Containers · Notebook · Gateway · Security · Profiles     │
└───────────────────────────────┬───────────────────────────────────┘
                                │ HTTP/SSE or WebSocket
┌───────────────────────────────▼───────────────────────────────────┐
│                      Canonical Agent Runtime                       │
│ Task Envelope · AgentRunEngine · Plan · Tool Loop · Budgets      │
│ Scheduler · Conductor · Approvals · Cancellation · Checkpoints   │
└───────────────┬───────────────────────┬───────────────────────────┘
                │                       │
┌───────────────▼─────────────┐ ┌──────▼────────────────────────────┐
│ Context and Memory Plane    │ │ Authority and Execution Plane     │
│ Code Cortex                 │ │ Capability Plane                  │
│ Workspace Graph             │ │ Agent Passport                    │
│ Context Packet              │ │ One-Use Capability                │
│ L0-L4 Memory                │ │ Runtime Governor                  │
│ Chronicle                   │ │ Execution Target                  │
│ Skill and Crystal Retrieval │ │ Worktree Forge                    │
└───────────────┬─────────────┘ └──────┬────────────────────────────┘
                │                       │
                └───────────────┬───────┘
                                │
┌───────────────────────────────▼───────────────────────────────────┐
│              Verification, Mutation and Evidence Plane            │
│ Quality Cascade · Deterministic Verifiers · SourcePlan           │
│ Evidence Bus · Sensorium · Rollback · Promotion · Crystalliser   │
└───────────────────────────────────────────────────────────────────┘
```

### 5.1 Architectural laws

1. **One canonical owner per concern.**
2. **Renderer code never receives raw shell, process, filesystem, SSH, Docker, or extension authority.**
3. **Every operation carries an execution-target identity.**
4. **No mutating agent action writes directly to the operator workspace.**
5. **SourcePlan remains the promotion boundary.**
6. **Sensorium and evidence stores record outcomes, not hidden reasoning traces.**
7. **Retrieval is advisory and never silently widens context or edit scope.**
8. **Remote failure never silently falls back to local execution.**
9. **Tool authority is request-bound, scope-bound, time-bound, and revocable.**
10. **Crystals and promoted skills require verified outcomes and policy compatibility.**
11. **All long-running work is cancellable, resumable, and budgeted.**
12. **Every release claim maps to an executable acceptance test.**

---

## 6. Canonical ownership map for BEAST 4.0

| Concern | Canonical owner | Existing systems to compose |
|---|---|---|
| Desktop interaction | Renderer workbench | Store, router, editor cortex, AI coding, pages |
| Desktop authority | Electron service plane | Main process, preload, compatibility host |
| Workspace identity | Workspace Manager | Multi-root state, safe paths, target identity |
| Code intelligence | Code Cortex | Workspace Graph, semantic retrieval, LSP results |
| Context construction | Context Packet | Context header, explicit attachments, diagnostics |
| Task representation | Task Envelope | Mode Router, Forge scorecard, success criteria |
| Agent lifecycle | **AgentRunEngine** | Scheduler, Conductor, runtime governor |
| Tool discovery | Capability Plane | Registry, tool buckets, MCP, integrations |
| Tool authorization | LeastAuthorityToolLoop | Agent Passport, OneUseCapability, policy gates |
| Execution target | Target Runtime Manager | Local, SSH, Dev Container |
| Isolated mutation | Worktree Forge | Git worktree, target-aware mutation |
| Deterministic validation | Quality Cascade | Syntax, lint, type, test, build, security |
| Workspace promotion | SourcePlan | Action IR, exact hashes, approval, rollback |
| Durable events | Sensorium Journal | Event sequencer, read models, exporter |
| Evidence | Evidence Bus | SourcePlan, scheduler, tools, tests, outcome evidence |
| Long-term task memory | Chronicle | Task summaries, root causes, outcome metadata |
| Reusable recipes | Skill Tree | Canon validation, promotion candidates |
| Verified reusable compute | Crystal Runtime | Crystal lattice, replay, proof conductor |
| Operator summary | Mission Cockpit | Read models from canonical surfaces |
| Provider route | Agent Scheduler | Provider Economist, inference fabric, local scout |

### 6.1 Compatibility facades

Existing compatibility modules should remain temporarily, but new imports must use canonical paths. Add a static import guard and a removal milestone for:

- `app.kernel.task_envelope`;
- `app.kernel.ollama_scout`;
- `app.kernel.commons_spaces`;
- `app.kernel.canon_registry`;
- `app.kernel.forensic_memory`;
- `app.kernel.insight_compiler`;
- `app.kernel.beast_cli_executor`.

The compatibility facade may re-export. It must never gain new logic.

---

# PART II: IMPLEMENTATION PROGRAM

## 7. Phase 0: Truth freeze, release contract, and repository hygiene

### Objective

Create a stable, generated description of what BEAST currently supports before more features move underneath it.

### Deliverables

#### 7.1 Canonical capability ledger

Create:

```text
contracts/
  beast-parity-contract.v1.yaml
  execution-target-matrix.v1.yaml
  extension-compatibility.v1.yaml
  language-adapter-matrix.v1.yaml
  debugger-adapter-matrix.v1.yaml
  test-adapter-matrix.v1.yaml
  agent-tool-policy.v1.yaml
```

Each capability entry includes:

```yaml
id: git.hunk.stage
surface: source-control
owner: desktop.git
targets: [local, ssh, devcontainer]
risk: mutation
acceptance:
  structural: required
  local_live: required
  external_live: required
evidence:
  receipt_type: git_mutation
status: operational
```

#### 7.2 Generated parity report

Replace manually maintained percentages with a generated report containing:

- implemented capabilities;
- test coverage;
- latest run timestamp;
- runtime versions;
- passed, failed, skipped, and not-configured states;
- environment identity;
- evidence references;
- known gaps;
- percentage calculation method.

#### 7.3 Repository cleanup

- Remove tracked `node_modules`, generated caches, `.bak` files, stale duplicates, and machine-local paths.
- Move debug scripts into `scripts/debug/`.
- Move manual probes into `scripts/manual/`.
- Put binaries and large proof bundles in explicit release/evidence directories.
- Add archive retention rules.
- Run secret scanning and remove stale credentials from Git history where necessary.
- Require `git diff --check`, manifest generation, and dependency lock validation.

#### 7.4 Documentation correction

- Fix the detailed parity document date.
- Mark historical assessments as superseded.
- Generate result counts from verifier output.
- Distinguish `structural`, `local-live`, `external-live`, and `soak` evidence.
- Add a “last verified commit” field to every operational document.

### Exit gate

Phase 0 is complete when one command produces a truthful, reproducible status bundle:

```bash
beast verify release-contract --all
```

The command must emit:

- build identity;
- capability ledger;
- environment matrix;
- test results;
- evidence references;
- unresolved gaps.

---

## 8. Phase 1: Decompose the monoliths without changing behaviour

### Objective

Create stable module boundaries around the current working features.

### 8.1 Split Electron `main.js`

Target structure:

```text
desktop-ide/main/
  bootstrap.js
  build-identity.js
  security-policy.js
  ipc-registry.js
  gateway-host.js
  workspace-host.js
  file-host.js
  git-host.js
  task-host.js
  test-host.js
  terminal-host.js
  lsp-host.js
  dap-host.js
  notebook-host.js
  ssh-host.js
  container-host.js
  extension-host.js
  execution-target-host.js
  profile-host.js
  diagnostics-host.js
```

Rules:

- `bootstrap.js` creates the window and composes services.
- Each host owns a typed IPC namespace.
- Shared path, process, output, timeout, and target validation live in reusable services.
- No host imports renderer code.
- No renderer-provided shell strings.
- Every long operation registers cancellation and lifecycle metadata.

### 8.2 Split backend `app/routes/ide.py`

Target structure:

```text
app/routes/ide/
  router.py
  models.py
  sessions.py
  context.py
  providers.py
  action_ir.py
  sourceplans.py
  worktrees.py
  validation.py
  agent_runs.py
  events.py
```

Business logic moves into kernel services. Routes validate, invoke, and serialize.

### 8.3 Split `beast-ai-coding.js`

Target structure:

```text
renderer/js/ai/
  agent-client.js
  agent-store.js
  agent-events.js
  agent-view.js
  context-picker.js
  context-manifest.js
  approval-cards.js
  tool-cards.js
  plan-view.js
  verification-view.js
  sourceplan-handoff.js
  conversation-renderer.js
  mode-controller.js
  budget-view.js
```

### 8.4 Add boundary tests

- Renderer cannot call undeclared IPC channels.
- IPC handlers cannot bypass safe workspace paths.
- Routes cannot import renderer or Electron code.
- Kernel services do not depend on FastAPI request objects.
- Agent runtime does not call SourcePlan apply directly.
- Worktree edits cannot target the operator workspace.
- Execution-target methods require a target ID.

### Exit gate

All existing local parity and visual tests remain green after decomposition, with no user-visible feature change.

---

## 9. Phase 2: Build the canonical AgentRunEngine

### Objective

Give one durable runtime ownership of a coding task from creation through final promotion readiness.

### 9.1 New kernel package

```text
app/kernel/agents/
  run_engine.py
  run_state.py
  run_models.py
  run_events.py
  run_projection.py
  run_store.py
  run_budget.py
  run_cancel.py
  run_checkpoint.py
  run_recovery.py
  tool_runtime.py
  approval_runtime.py
  model_runtime.py
  worktree_runtime.py
  verification_runtime.py
```

### 9.2 State machine

```text
CREATED
  → SCOPING
  → PLANNING
  → OBSERVING
  → WAITING_FOR_APPROVAL
  → EXECUTING_TOOL
  → UPDATING_PLAN
  → EDITING_WORKTREE
  → VERIFYING
  → DIAGNOSING
  → REPAIRING
  → FINALIZING
  → SOURCEPLAN_READY
  → WAITING_FOR_PROMOTION
  → PROMOTING
  → POST_VERIFY
  → COMPLETED
```

Terminal states:

```text
CANCELLED
FAILED
BUDGET_EXHAUSTED
POLICY_BLOCKED
REJECTED
ROLLED_BACK
```

### 9.3 Durable run API

```text
POST   /edgek/agent-runs
GET    /edgek/agent-runs/{run_id}
GET    /edgek/agent-runs/{run_id}/events?after={sequence}
POST   /edgek/agent-runs/{run_id}/cancel
POST   /edgek/agent-runs/{run_id}/resume
POST   /edgek/agent-runs/{run_id}/approvals/{approval_id}
GET    /edgek/agent-runs/{run_id}/artifacts
POST   /edgek/agent-runs/{run_id}/sourceplan
POST   /edgek/agent-runs/{run_id}/promote
```

Run creation uses POST. Prompts, context references, provider choices, and file paths must not travel in query strings.

### 9.4 Event contract

Each event contains:

```json
{
  "event_id": "evt_...",
  "sequence": 42,
  "run_id": "run_...",
  "step_id": "step_...",
  "type": "agent.tool.completed",
  "timestamp": "2026-07-18T12:00:00Z",
  "actor": "tool:test.pytest",
  "execution_target": "local",
  "policy_generation": "pol_...",
  "payload": {},
  "evidence_ref": "sha256:...",
  "previous_event_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

Core event types:

```text
agent.run.created
agent.run.scoped
agent.plan.created
agent.plan.updated
agent.model.started
agent.model.delta
agent.model.completed
agent.tool.requested
agent.approval.requested
agent.approval.resolved
agent.tool.started
agent.tool.completed
agent.tool.failed
agent.worktree.created
agent.worktree.changed
agent.verification.started
agent.verification.completed
agent.repair.started
agent.checkpoint.created
agent.sourceplan.ready
agent.promotion.requested
agent.promotion.completed
agent.run.cancelled
agent.run.failed
agent.run.completed
```

### 9.5 Sensorium integration

Use Sensorium Journal as the append-only event truth. Build agent-specific read models for fast UI queries.

Do not create a competing free-standing event truth.

Suggested projections:

```text
agent_runs
agent_steps
agent_model_invocations
agent_tool_calls
agent_approvals
agent_artifacts
agent_budgets
agent_worktree_mutations
agent_verification_cycles
```

### 9.6 Cancellation

Cancellation must propagate through:

- provider HTTP/SSE streams;
- local model calls;
- MCP calls;
- subprocess groups;
- tasks and tests;
- SSH commands and terminals;
- Docker exec processes;
- LSP/DAP requests where cancellation is supported;
- queued scheduler work;
- worktree verification.

Acceptance:

- UI receives acknowledgement immediately.
- Backend moves to `CANCELLING`.
- Active child process groups terminate within the policy limit.
- No new tool starts after cancellation.
- Final cancellation evidence identifies what stopped and what could not be interrupted.

### 9.7 Checkpoint and resume

Checkpoint after:

- task scoping;
- plan creation;
- each consequential tool result;
- approval interruption;
- worktree mutation;
- verification result;
- provider failure;
- SourcePlan generation.

A restart must resume without duplicating an already consumed one-use capability or replaying a completed mutation.

### Exit gate

A seeded agent run can be created, disconnected, reconnected, approved, cancelled, resumed after restart, and replayed with a complete ordered event history.

---

## 10. Phase 3: Real least-authority model-directed tool use

### Objective

Turn the current staged proposal pipeline into a bounded inspect, act, observe, repair loop.

### 10.1 Typed tool classes

#### Class A: read-only and automatic

- list workspace roots;
- list directory;
- read bounded file range;
- search text;
- search symbols;
- retrieve diagnostics;
- inspect Git status/diff;
- inspect task definitions;
- inspect test tree;
- inspect dependency manifests;
- inspect logs and prior evidence;
- retrieve accepted context suggestions.

#### Class B: read-only but sensitive

- read secret-adjacent files;
- query external GitHub;
- query a database;
- fetch an approved URL;
- inspect remote system metadata.

Require explicit scope or approval.

#### Class C: isolated mutation

- create or modify files inside a mission worktree;
- apply typed patches;
- create directories;
- run formatters;
- update dependency manifests;
- run migration generators.

Require Worktree Forge and a mutation capability.

#### Class D: consequential execution

- run tests;
- run builds;
- execute task definitions;
- launch containers;
- invoke networked tools;
- alter Git state inside the worktree.

Approval depends on risk policy.

#### Class E: never model-authorized

- apply directly to operator workspace;
- promote SourcePlan;
- push to a remote;
- publish a package;
- rotate credentials;
- change global policy;
- disable evidence;
- disable trust;
- erase audit history.

### 10.2 Tool schema

Every tool publishes:

```json
{
  "tool_id": "workspace.read_range",
  "version": "1",
  "category": "read",
  "risk": "low",
  "idempotent": true,
  "targets": ["local", "ssh", "devcontainer"],
  "input_schema": {},
  "output_schema": {},
  "max_output_bytes": 65536,
  "timeout_seconds": 10,
  "requires_approval": false,
  "requires_worktree": false,
  "redaction_policy": "source",
  "evidence_level": "summary"
}
```

### 10.3 Bound the loop

Each run receives policy limits:

```json
{
  "max_model_turns": 24,
  "max_tool_calls": 60,
  "max_mutating_tool_calls": 20,
  "max_verification_cycles": 5,
  "max_files_changed": 20,
  "max_lines_changed": 2000,
  "max_wall_seconds": 1800,
  "max_input_tokens": 180000,
  "max_output_tokens": 40000,
  "max_cloud_cost": 5.0,
  "max_parallel_subagents": 3
}
```

Values are policy profiles, not hardcoded global constants.

### 10.4 Stagnation detection

Stop or replan when:

- the same tool is called with equivalent input repeatedly;
- no new evidence is added across multiple turns;
- the same verifier failure repeats;
- the plan oscillates between equivalent states;
- tool output is repeatedly truncated without narrowed requests;
- the agent exceeds change or budget thresholds;
- provider output violates schema repeatedly.

### 10.5 Worktree-first mutation

Agent mode always creates or attaches to a mission worktree when:

- multiple files may change;
- a command or test will run;
- dependency files may change;
- risk is medium or higher;
- repair cycles are expected.

The operator workspace remains untouched until promotion.

### 10.6 Verification ladder

Run the cheapest relevant checks first:

1. content safety;
2. conflict markers and NUL checks;
3. syntax parsing;
4. formatter check;
5. linter;
6. type checker;
7. focused test selection;
8. affected package tests;
9. full test suite where policy requires;
10. build or launch smoke;
11. security and dependency scan;
12. target-specific runtime check.

Verification failures become structured observations for the same run.

### 10.7 Final SourcePlan synthesis

After successful worktree verification:

```text
base commit
+ worktree diff
+ file hashes
+ policy receipts
+ tool receipts
+ verification receipts
+ model and context manifest
    ↓
governed SourcePlan
```

The agent may prepare the plan. It may not approve or promote it.

### Exit gate

A multi-file seeded defect is solved through repeated inspect, tool, edit, test, diagnose, and repair turns in a worktree, then converted into a reviewable SourcePlan.

---

## 11. Phase 4: Durable approval and autonomy controls

### Objective

Replace transient browser dialogs with policy-aware, persisted capability decisions.

### 11.1 Approval card contents

Every approval request shows:

- requesting run and step;
- agent identity and model;
- tool name and version;
- exact arguments or a safe digest view;
- workspace and execution target;
- files, command, URL, or external service involved;
- data leaving the machine;
- expected side effects;
- risk class;
- reason the tool is needed;
- budget impact;
- expiry;
- evidence policy.

### 11.2 Approval scopes

- Approve once.
- Approve equivalent calls for this run.
- Approve tool and scope for this workspace.
- Approve read-only calls for this execution target.
- Edit the requested scope.
- Reject and request replan.
- Permanently deny through policy.

No “approve everything forever” option should exist for destructive tool classes.

### 11.3 Permission modes

BEAST can expose:

| Mode | Behaviour |
|---|---|
| Review | Every consequential action requires approval |
| Guided | Read-only automatic, isolated mutation and execution approved |
| Bounded Autonomy | Approved policy profile auto-authorizes scoped worktree actions |
| Observe Only | No mutation tools |
| Locked | AI cannot run |

Unlike a simple bypass toggle, Bounded Autonomy still enforces:

- worktree isolation;
- file and command allowlists;
- cost and turn budgets;
- network restrictions;
- SourcePlan promotion approval;
- evidence generation.

### 11.4 Sensitive data controls

- `.env`, credentials, private keys, signing files, policy files, and secret stores require explicit approval.
- External tool results receive a prompt-injection risk classification before entering model context.
- URL request and response trust are separate decisions.
- Tool output is provenance-labelled.
- Secret values are redacted from Chronicle, Sensorium summaries, and model prompts.

### Exit gate

An approval can survive desktop and backend restart, resume the exact paused step, and issue one request-bound capability without widening future authority.

---

## 12. Phase 5: Pair Programmer becomes the Agent Operations Console

### Objective

Preserve the conversation-first design while making autonomous execution understandable and controllable.

### 12.1 Primary layout

The AI workbench should contain:

1. **Conversation**
2. **Current objective and success criteria**
3. **Plan**
4. **Live run timeline**
5. **Context manifest**
6. **Tool and approval cards**
7. **Worktree changes**
8. **Verification**
9. **Budget and provider route**
10. **SourcePlan handoff**

### 12.2 Mode definitions

#### Ask

- read-only;
- no worktree;
- no SourcePlan;
- optional cited workspace context.

#### Edit

- one bounded proposal;
- normally exact in-memory projection;
- one repair turn;
- SourcePlan required.

#### Agent

- durable run;
- model-directed tools;
- worktree mutation;
- repeated verification and repair;
- SourcePlan promotion boundary.

#### Review

- critic and verifier roles;
- no mutation unless explicitly converted into a new Agent run.

### 12.3 Context manifest

Show each context item with:

- source;
- file path and line range;
- content hash;
- retrieval reason;
- selected manually or suggested;
- token estimate;
- privacy level;
- provider visibility;
- accepted or rejected.

Context suggestions remain unselected until accepted.

### 12.4 Run timeline

Example:

```text
09:14:02  Run created
09:14:03  Task classified: test_failure
09:14:04  Worktree created
09:14:05  Context packet built: 14 excerpts, 9 excluded
09:14:07  Local scout selected 5 tools
09:14:12  Read failing test
09:14:15  Search references
09:14:20  Plan updated
09:14:31  Patch applied in worktree
09:14:35  Focused test failed
09:14:36  Repair cycle 1 started
09:14:52  Focused test passed
09:15:04  Package tests passed
09:15:07  SourcePlan ready
```

### 12.5 Recovery UX

Explicit states:

- provider unavailable;
- model schema invalid;
- tool denied;
- approval expired;
- target disconnected;
- test timed out;
- budget nearly exhausted;
- run paused;
- run recoverable;
- worktree dirty;
- SourcePlan stale because base changed.

Every error card offers only valid next actions.

### Exit gate

A user can understand what the agent is doing, why it needs authority, what changed, what passed, what failed, and what remains before promotion without opening raw logs.

---

## 13. Phase 6: Core editor and workbench parity completion

### Objective

Complete the daily editing experience so BEAST can serve as a primary workbench.

### 13.1 Editor groups and tabs

- Multiple editor groups.
- Drag and move tabs between groups.
- Preview and pinned tabs.
- Dirty-buffer indicators.
- Reopen closed editor.
- Restore group layout.
- Compare editors.
- Diff navigation.
- Virtual and read-only documents.
- Large-file mode.
- Binary-file fallback.

### 13.2 Workspace and Explorer

- Reliable local file watching.
- Remote and container watcher abstraction.
- Multi-root add, remove, rename, and reorder.
- Workspace file support.
- File operations with undo.
- Exclude and search settings.
- Symlink policy.
- Very large tree virtualization.
- Conflict detection when external edits occur.
- Workspace storage and restoration.

### 13.3 Settings and profiles

- User, workspace, folder, language, and target settings.
- Searchable Settings UI and JSON editor.
- Profile export/import.
- Profile contents: settings, keybindings, layout, extension set, UI density, model route, and trust defaults.
- Per-project BEAST profile.
- Safe migration between schema versions.

### 13.4 Workspace Trust

Restricted mode must disable or constrain:

- agents;
- terminals;
- tasks;
- debugging;
- notebooks;
- executable extensions;
- workspace-provided settings;
- automatic hooks;
- source mutation.

Trust state must be visible in the status bar and shared across workbench and agent surfaces.

### 13.5 Search and navigation

- Quick open.
- Go to symbol in file/workspace.
- Go to definition/type definition/implementation.
- Peek views.
- Reference list.
- Search editor.
- Search history.
- Replace preview.
- Include/exclude glob support.
- Results grouping and navigation.

### 13.6 Performance proof

Test against repositories with:

- 10,000 files;
- 100,000 files;
- large generated directories;
- many Git changes;
- slow network filesystems;
- deeply nested paths;
- frequent external file mutations.

### Exit gate

The basic edit, navigation, search, save, restore, and trust journeys pass across all supported desktop platforms and target types.

---

## 14. Phase 7: Source control parity completion

### Objective

Turn the substantive Git backend into a polished, reliable daily-driver source-control experience.

### 14.1 Core operations

Complete and harden:

- status;
- file and hunk stage/unstage;
- discard;
- amend;
- branch create/switch/delete;
- tags;
- stash create/apply/pop/drop;
- fetch;
- pull with explicit strategy;
- push and upstream selection;
- rebase;
- cherry-pick;
- revert;
- reset with risk gates;
- remote management;
- submodule status.

### 14.2 Visual history graph

- Commit graph.
- Branch and tag decoration.
- Author, time, refs, and signature status.
- File history.
- Line history.
- Compare commits/branches.
- Open commit changes.
- Copy commit identifiers.

### 14.3 Merge and conflict experience

- Three-way merge editor.
- Base, current, incoming, and result.
- Accept current/incoming/both.
- Manual result editing.
- Conflict navigation.
- Re-run conflict parser after edits.
- Prevent commit while unresolved.
- Evidence for conflict resolution.
- Rebase and cherry-pick continuation/abort.

### 14.4 Multi-repository support

- Detect multiple repositories across roots.
- Select active repository.
- Independent status and branch state.
- Cross-repository overview.
- No mutation against an implicit repository.
- Agent context records repository identity for every edit.

### 14.5 Remote-operation proof

CI fixtures should exercise:

- authenticated local bare remote;
- rejected non-fast-forward push;
- fast-forward pull;
- merge-required pull;
- branch deletion;
- tag push;
- network interruption;
- credential failure;
- protected-operation policy.

### Exit gate

Every published Git operation has a real disposable-repository acceptance test and a recoverable failure path.

---

## 15. Phase 8: LSP and refactoring depth

### Objective

Move from protocol availability to consistently good language behaviour.

### 15.1 Language server supervisor

For each server:

- provision or discover;
- version check;
- initialize;
- capability negotiation;
- progress reporting;
- request cancellation;
- crash detection;
- bounded restart;
- log capture;
- target-aware transport;
- workspace-folder changes;
- graceful shutdown.

### 15.2 Capability-aware UI

Do not show unavailable actions. Surface:

- completion;
- signature help;
- hover;
- definition;
- type definition;
- implementation;
- references;
- rename;
- formatting;
- code actions;
- inlay hints;
- semantic tokens;
- call hierarchy;
- type hierarchy;
- document links;
- workspace symbols.

### 15.3 Refactor preview

Rename and code actions should show:

- affected files;
- affected symbols;
- text edits;
- conflicts;
- unsupported edits;
- target server;
- workspace hash.

Consequential refactors can become SourcePlans.

### 15.4 Versioned adapter matrix

Pin and test supported combinations for:

- TypeScript/JavaScript;
- Python with Pyright and pylsp;
- Bash;
- Go;
- Rust;
- C/C++;
- JSON, HTML, CSS, YAML;
- selected future languages.

### 15.5 Degraded-mode behaviour

- Explain when a server is unavailable.
- Offer install/provision action.
- Fall back to lexical symbols where possible.
- Never imply semantic correctness from a failed server.
- Preserve editing while intelligence restarts.

### Exit gate

Each supported language has a version-pinned protocol acceptance suite and a user-visible capability report.

---

## 16. Phase 9: Debugging, testing, tasks, terminals, and notebooks

### 16.1 DAP completion

Add and test:

- attach-to-process discovery;
- exception breakpoints;
- data breakpoints;
- instruction breakpoints where supported;
- child-process handling;
- restart frame;
- set variable;
- memory/reference views where supported;
- test-debug launch;
- remote path mapping;
- adapter-specific schemas;
- compound lifecycle;
- terminated/crashed adapter recovery.

### 16.2 Testing platform

Create a test-adapter interface supporting:

- discovery;
- hierarchy;
- run;
- debug;
- cancellation;
- output;
- failure location;
- diff;
- coverage;
- history;
- flaky-state annotation;
- target selection.

Initial adapters:

- pytest;
- unittest;
- Jest/Vitest;
- Node test runner;
- Go test;
- Cargo test.

### 16.3 Test selection for agents

Use:

- changed files;
- import/dependency graph;
- failing stack traces;
- historical failure correlation;
- test ownership metadata;
- prior verified routes.

Record why each test was selected or skipped.

### 16.4 Task system

Complete:

- task dependencies;
- sequence and parallel order;
- background readiness;
- problem matchers;
- presentation groups;
- inputs;
- target routing;
- restart;
- reveal policies;
- run-on-folder-open gated by trust;
- task history and evidence.

### 16.5 Terminal robustness

- Real PTY abstraction per platform.
- Unicode, resize, alternate screen, colours, and signals.
- Shell integration markers.
- command detection;
- target identity;
- reconnect;
- output retention policy;
- process tree termination;
- no terminal input from an unapproved agent tool.

### 16.6 Notebook platform

Expand from a Python kernel slice to:

- full `.ipynb` document model;
- cell insert/delete/move;
- execution order;
- rich MIME output;
- images;
- tables;
- HTML sandbox;
- error rendering;
- variable explorer;
- interrupt/restart;
- trust metadata;
- output clearing;
- kernel selection;
- notebook diff;
- extension renderer compatibility subset.

### Exit gate

A user can discover, run, debug, and inspect tests; use durable terminals and tasks; and complete a trusted notebook workflow locally and on supported targets.

---

## 17. Phase 10: Remote SSH, Dev Containers, and target fidelity

### Objective

Make remote work operationally proven rather than merely protocol-ready.

### 17.1 Unified execution target contract

Every operation receives:

```json
{
  "target_id": "ssh:lab-server",
  "target_type": "ssh",
  "workspace_uri": "beast-ssh://lab-server/home/user/repo",
  "target_generation": 7
}
```

A stale target generation invalidates handles.

### 17.2 Remote service lifecycle

Create a minimal target-side BEAST service or relay for:

- filesystem events;
- extension execution;
- LSP and DAP;
- task and test execution;
- terminal PTY;
- process inventory;
- port discovery;
- target health;
- bounded evidence relay.

Desktop remains the policy authority.

### 17.3 SSH completion

- strict host-key verification;
- key-agent and explicit credential integration;
- no password logging;
- reconnect and backoff;
- remote file watching;
- atomic writes;
- remote trash/restore policy;
- port forwarding lifecycle;
- remote extension placement and update state;
- long-session soak;
- interrupted-network recovery.

### 17.4 Dev Container completion

Support the declared subset of:

- `devcontainer.json`;
- Dockerfile;
- Compose;
- mounts;
- environment variables;
- lifecycle commands;
- user selection;
- forwarded ports;
- features;
- rebuild;
- logs;
- extension placement;
- target tools;
- remote Docker host where supported.

### 17.5 No silent fallback

When target execution fails:

- show target failure;
- preserve requested target;
- pause the run;
- offer reconnect, reselect, or explicit local conversion;
- record the decision.

### 17.6 CI environments

Maintain disposable fixtures:

- local Linux;
- local container;
- Compose project;
- strict-host-key SSH server;
- SSH plus container;
- network interruption proxy;
- slow filesystem;
- low-disk target.

### Exit gate

The same repository journey passes through Explorer, LSP, DAP, tests, tasks, terminals, extensions, and Agent mode on local, SSH, and Dev Container targets.

---

## 18. Phase 11: Extension ecosystem and compatibility contract

### Objective

Grow extension utility without surrendering BEAST's trust model.

### 18.1 Compatibility tiers

| Tier | Capability |
|---|---|
| E0 | Declarative themes, snippets, languages, settings, commands |
| E1 | Sandboxed code with notices, configuration, bounded reads and commands |
| E2 | Tree views, status bar, diagnostics, code actions, testing contributions |
| E3 | Sandboxed webviews and custom editors with strict CSP |
| E4 | Notebook, SCM, debugger, language-model tools, and agent contributions |
| Companion | Requires full VS Code and runs through BEAST's VS Code extension/MCP integration |

### 18.2 Extension package lifecycle

- install;
- validate manifest;
- verify signature or publisher trust;
- inspect requested capabilities;
- grant per workspace and target;
- enable/disable;
- activate on declared events;
- update;
- rollback;
- remove;
- quarantine;
- collect health and crash data.

### 18.3 Contribution points

Prioritize:

- commands;
- configuration;
- keybindings;
- menus;
- languages;
- grammars;
- snippets;
- themes;
- views and view containers;
- diagnostics;
- problem matchers;
- task definitions;
- testing;
- debuggers;
- notebook renderers;
- source control;
- language-model tools;
- custom agents, instructions, skills, and hooks.

### 18.4 OS-level isolation

Node VM isolation is not a final security boundary.

Add:

- separate extension-host process;
- restricted filesystem namespace;
- network policy;
- resource limits;
- process limits;
- syscall or sandbox profile where available;
- per-extension capability broker;
- crash isolation;
- watchdog;
- quarantine after repeated violations.

### 18.5 Compatibility test corpus

Build a set of representative open-source extensions, each mapped to the supported API subset. Never report “Marketplace parity” from manifest counts alone.

### 18.6 BEAST extension registry

A future registry should provide:

- signed manifests;
- compatibility tier;
- permissions;
- target support;
- test status;
- publisher identity;
- update channel;
- SBOM;
- known vulnerabilities;
- deterministic install bundle.

### Exit gate

Every advertised extension API and contribution point has a fixture extension, lifecycle test, permission test, and sandbox escape test.

---

## 19. Phase 12: Security, workspace trust, and supply-chain hardening

### 19.1 Electron hardening

- Enable Chromium sandbox.
- Keep `contextIsolation: true`.
- Keep `nodeIntegration: false`.
- Deny unexpected navigation.
- Deny new windows by default.
- Strictly allowlist external links.
- Deny permissions unless explicitly required.
- Validate IPC sender and frame identity.
- Limit payload size and rate.
- Apply a strict Content Security Policy.
- Do not render untrusted model HTML.
- Disable dangerous Electron features.

### 19.2 Workspace trust policy

Trust governs:

- agents;
- extension activation;
- hooks;
- terminals;
- tasks;
- notebooks;
- debugging;
- workspace settings;
- automatic tool calls;
- remote connections.

### 19.3 Agent sandbox

For Bounded Autonomy:

- worktree-only write root;
- explicit read roots;
- network deny by default;
- approved domains;
- process tree limits;
- CPU/memory/time quotas;
- no access to desktop secrets;
- target-specific sandbox;
- evidence of sandbox policy.

### 19.4 Prompt-injection resistance

- Mark external content as untrusted data.
- Do not place tool output into system instructions.
- Separate tool pre-approval from output admission.
- Scan URL, MCP, GitHub, issue, log, and database content.
- Prevent retrieved text from modifying policy.
- Require confirmation before context widens to sensitive paths.
- Record provenance for every model-visible byte range.

### 19.5 Supply chain

- Lock dependencies.
- Generate SBOM.
- Scan Python, npm, container, and extension dependencies.
- Verify downloaded binaries.
- Sign release artifacts.
- Reproducible build metadata.
- Publish checksums.
- Rollback update support.
- Secret scanning.
- License inventory.

### 19.6 Adversarial test program

Test:

- path traversal;
- symlink escape;
- command injection;
- argument confusion;
- oversized output;
- malformed LSP/DAP frames;
- extension escape;
- IPC spoofing;
- event replay;
- capability reuse;
- stale approval;
- target confusion;
- prompt injection;
- evidence tampering;
- worktree-to-workspace escape.

### Exit gate

A red-team suite proves that renderer, extension, agent, tool, and remote-target boundaries fail closed.

---

## 20. Phase 13: Integrate V2 memory, retrieval, compute, and crystal systems

### Objective

Make the V2 systems part of the normal IDE agent path rather than parallel demonstrations.

### 20.1 Universal task envelope

Every Agent run starts from a Task Envelope containing:

- objective;
- task class;
- success criteria;
- execution target;
- risk;
- privacy;
- allowed actions;
- context budget;
- provider budget;
- approval profile;
- verification requirements;
- repository and base commit.

### 20.2 Universal context header

One metadata-first context service feeds:

- Pair Programmer;
- Agent mode;
- Review;
- Debug;
- Task failure;
- CLI;
- TUI;
- MCP.

Suggestions remain advisory and require acceptance.

### 20.3 L0-L4 memory

| Layer | Agent use |
|---|---|
| L0 policy | authority, budgets, sensitive paths, allowed tools |
| L1 session | run state, cache handles, circuit state, active plan |
| L2 workspace | symbols, dependency graph, semantic chunks, diagnostics |
| L3 skills | verified task recipes, test selection patterns, repair strategies |
| L4 forensic | append-only events, outcomes, evidence, Chronicle |

Vector stores remain rebuildable projections. They are not truth.

### 20.4 Tool-call interception

Integrate the existing interceptor as a tool-output economy layer:

- semantic snippet extraction;
- deterministic lexical fallback;
- token pruning;
- code-density filtering;
- bounded GitHub context;
- bounded Postgres context;
- output compression with traceable references.

The interceptor must never falsely claim that compressed output is the full source.

### 20.5 Local scout role

Use compact local models for:

- classification;
- context ranking;
- tool shortlist;
- failure clustering;
- test selection suggestions;
- privacy and escalation decisions;
- critic passes on small outputs.

Do not ask a tiny local model to perform a repository-wide refactor outside its measured capability.

### 20.6 Provider role routing

Roles:

| Role | Preferred route |
|---|---|
| Scout | local Ollama or lightweight provider |
| Planner | strong reasoning model when task complexity requires |
| Implementer | coding-capable provider chosen by policy |
| Critic | different model or deterministic review |
| Verifier | deterministic checks first, model only for interpretation |
| Summarizer | local or low-cost provider |
| Crystal evaluator | deterministic evidence and policy, optional model assistance |

### 20.7 Chronicle

Every completed or failed run produces a bounded Chronicle record:

- objective;
- root cause;
- plan summary;
- tools used;
- files changed;
- verification;
- failure and repair cycles;
- provider route;
- cost;
- evidence;
- outcome;
- reusable pattern candidate.

No secrets or hidden chain-of-thought.

### 20.8 Skill promotion

A pattern becomes a skill candidate only when:

- repeated;
- verified;
- policy-compatible;
- low enough failure rate;
- context-independent enough to generalize;
- accompanied by exact acceptance criteria;
- human-approved.

### 20.9 Crystal promotion

A crystal requires:

- exact task fingerprint or valid generalized contract;
- engine/runtime compatibility;
- proof-carrying evidence;
- staleness policy;
- rollback or refusal;
- reproducible replay;
- measured equivalence;
- no metadata-only masquerading as executable compute.

### 20.10 KV cache boundary

Preserve the documented rule:

- transport only exact engine-native payload bytes;
- validate engine and identity;
- checksum all transfers;
- no cross-engine tensor claims;
- no metadata-only reuse claim;
- authenticated explicit peer transport only.

### Exit gate

A normal IDE Agent run visibly uses Task Envelope, context header, least-authority tools, Conductor, Quality Cascade, Chronicle, Canon, and promotion checks through one run ID.

---

## 21. Phase 14: Performance, accessibility, localization, and UX quality

### 21.1 Candidate service-level objectives

Measure first, then tune. Initial candidate targets:

| Metric | Candidate target |
|---|---:|
| Warm workbench interactive | p95 below 2.5 s |
| Cold workbench interactive | p95 below 5 s |
| Local file open | p95 below 150 ms |
| Warm workspace search | p95 below 2 s on 100k-file fixture |
| Command palette open | p95 below 100 ms |
| Local LSP completion request | p95 below 500 ms excluding server cold start |
| Agent run creation acknowledgement | p95 below 300 ms |
| Event reconnect and replay | p95 below 1 s for normal session |
| Cancellation acknowledgement | p95 below 250 ms |
| Child process termination after cancel | p95 below 3 s |
| Approval resume | p95 below 500 ms |
| Crash-free desktop sessions | above 99.5% |
| Evidence completeness for mutating operations | 100% |
| Silent target fallback | 0 |
| Unapproved workspace mutation | 0 |

### 21.2 Performance telemetry

Expose:

- startup phases;
- renderer frame stalls;
- memory by process;
- extension CPU/memory;
- LSP/DAP latency;
- search/index latency;
- file watcher backlog;
- agent first-token latency;
- model/tool duration;
- output truncation;
- event-store lag;
- remote round trips;
- cancellation delay.

### 21.3 Accessibility

- Full keyboard operation.
- Logical tab order.
- Focus visibility.
- Focus restoration after dialogs.
- Screen-reader labels and live regions.
- Accessible editor and terminal modes.
- High contrast.
- Reduced motion.
- Font scaling.
- Zoom across 100%, 125%, 150%, and higher.
- Colour-independent status.
- Automated axe-style checks plus manual screen-reader journeys.
- No critical information conveyed only through animation or glow.

### 21.4 Localization readiness

- Externalize strings.
- Locale-aware dates and numbers.
- Do not concatenate translated fragments.
- Test right-to-left layout.
- Preserve command IDs independently of labels.
- Localize errors and recovery instructions.

### 21.5 Visual continuity

Retain BEAST's distinctive visual identity, but:

- prioritise code and conversation density;
- reduce decorative motion during heavy work;
- preserve animation as ambient state, not obstruction;
- make every dashboard card actionable or remove it;
- keep telemetry behind progressive disclosure;
- preserve the mascot as an informative runtime signal.

### Exit gate

Accessibility, performance, and large-workspace suites become release gates rather than optional audits.

---

## 22. Phase 15: Packaging, onboarding, updates, and operations

### 22.1 Installer and first run

- Signed AppImage, deb, and future supported packages.
- Dependency doctor.
- Guided workspace trust.
- Provider configuration.
- Ollama detection and model recommendations.
- Optional LSP/DAP/tool provisioning.
- Execution-target setup.
- Profile selection.
- Sample governed Agent run.

### 22.2 Release channels

- stable;
- beta;
- nightly;
- enterprise-controlled.

Each channel has independent update policy and rollback.

### 22.3 Auto-update

- signed update manifest;
- delta where practical;
- preflight disk-space check;
- migration preview;
- automatic backup;
- rollback;
- evidence and error reporting;
- no update during active mutating runs.

### 22.4 Configuration migration

Every persisted store has:

- schema version;
- forward migration;
- backup;
- rollback;
- corruption detection;
- repair tool;
- human-readable export.

### 22.5 Operational doctor

`beast doctor` should diagnose:

- build identity;
- backend and gateway;
- event store;
- workspace permissions;
- Git;
- Node and Python;
- Ollama and selected models;
- provider credentials without exposing values;
- LSP/DAP adapters;
- Docker;
- SSH known hosts;
- extension host;
- disk and memory;
- stuck runs;
- stale worktrees;
- evidence integrity;
- crystal store health.

### 22.6 Crash recovery

- restore workbench layout;
- restore unsaved buffers;
- reconnect terminals where supported;
- mark interrupted tasks;
- resume Agent runs from checkpoints;
- reopen worktrees;
- invalidate stale capabilities;
- preserve SourcePlan review state.

### Exit gate

A new user can install, configure, run a governed edit, restart after interruption, update, and roll back without manual filesystem repair.

---

## 23. Phase 16: Proof, benchmarks, and release certification

### Objective

Make every product claim reproducible.

### 23.1 Test pyramid

#### Unit

- policies;
- schemas;
- path guards;
- capability scoping;
- budgets;
- event sequencing;
- projections;
- adapter framing;
- context packing;
- SourcePlan operations.

#### Integration

- provider plus tool loop;
- worktree plus verification;
- approval pause/resume;
- cancellation;
- event replay;
- extension host;
- Git repository lifecycle;
- target transport;
- LSP/DAP sessions.

#### End-to-end

- full operator journeys;
- local;
- SSH;
- Dev Container;
- recovery;
- update;
- rollback.

#### Adversarial

- malicious workspace;
- malicious extension;
- malicious MCP tool;
- malicious external content;
- target confusion;
- evidence tampering.

#### Soak and load

- eight-hour IDE session;
- long terminal;
- repeated LSP restart;
- 1,000 Agent events;
- 100 concurrent read-only runs where supported;
- large repository;
- slow provider;
- intermittent network;
- low disk;
- high CPU pressure.

### 23.2 BEASTBench coding-agent suite

Measure:

- task success;
- exact test pass;
- regression rate;
- files changed;
- unnecessary change;
- tool calls;
- model turns;
- token use;
- cost;
- wall time;
- approval count;
- recovery quality;
- evidence completeness;
- reproducibility;
- local versus cloud route;
- crystal reuse correctness.

Task categories:

- single-file bug;
- multi-file feature;
- dependency update;
- test repair;
- refactor;
- API change;
- UI change;
- remote-target failure;
- container build;
- Git conflict;
- security fix;
- performance fix.

### 23.3 Blind grading

For inference-economy claims:

- held-out tasks;
- fixed public baselines;
- hidden tests;
- blinded output review;
- complete token and compute accounting;
- scaffolding overhead included;
- local hardware reported;
- failed runs retained;
- no selective result deletion;
- reproducible bundles.

### 23.4 Release evidence bundle

Each release produces:

```text
release/
  BUILD_IDENTITY.json
  PARITY_CONTRACT.json
  CAPABILITY_REPORT.json
  TEST_RESULTS.xml
  LIVE_TARGET_MATRIX.json
  ADAPTER_MATRIX.json
  SECURITY_REPORT.json
  ACCESSIBILITY_REPORT.json
  PERFORMANCE_REPORT.json
  SBOM.json
  CHECKSUMS.txt
  RELEASE_NOTES.md
  KNOWN_LIMITS.md
  ROLLBACK_MANIFEST.json
```

### Exit gate

A release cannot claim 100% of the BEAST Parity Contract unless every required journey has current evidence from the release commit.

---

# PART III: DETAILED COMPLETION MATRIX

## 24. BEAST Parity Contract completion matrix

| Domain | Current documented position | 4.0 completion requirement |
|---|---:|---|
| Core editor and layout | About 91% | Multi-group lifecycle, profiles, dirty restore, virtual docs, accessibility and scale proof |
| Explorer and multi-root | About 87% | Watchers, target watchers, lifecycle soak, large-tree proof |
| Git | About 82% | Graph, merge editor, multi-repo, live remote matrix |
| Search and LSP | About 81% | Capability consistency, rich previews, lifecycle/version matrix |
| Debugging | About 80% | Attach discovery, exceptions/data breakpoints, test-debug, adapter matrix |
| Testing and notebooks | About 78% | Framework adapters, history, rich notebook output, trust and target proof |
| Tasks and terminal | About 82% | PTY portability, task dependency/presentation, remote soak |
| Extensions | About 80% | Published API subset, updates, contribution points, OS sandbox, fixtures |
| Remote SSH | About 80% | Remote watcher/extension service, real-host CI, reconnect soak |
| Dev Containers | About 75% | Declared devcontainer subset, mounts/features, extension lifecycle, CI |
| AI Pair Programmer | About 80% | Durable AgentRunEngine, tool loop, worktree repair, approvals, cancellation |
| Reliability | About 80% | continuous live matrix, soak, performance, crash recovery |
| Accessibility | Not yet fully scored | keyboard, screen reader, contrast, zoom, reduced motion release gate |
| Packaging and updates | Partial | signed packages, migration, update/rollback, first-run path |

Percentages should disappear from release marketing once the contract becomes binary and evidence-backed.

---

## 25. AgentRun acceptance scenarios

### Scenario A: Multi-file test repair

1. Open repository.
2. Select local target.
3. Ask Agent to fix a failing test.
4. Task Envelope identifies `test_failure`.
5. Context Packet includes failing stack and affected symbols.
6. Agent creates worktree.
7. Agent reads only bounded files.
8. Focused test fails.
9. Agent diagnoses and patches.
10. Focused and package tests pass.
11. SourcePlan is generated.
12. Operator promotes.
13. Post-apply verification passes.
14. Evidence and Chronicle are complete.

### Scenario B: Approval survives restart

1. Agent requests a networked tool.
2. Backend stores the interruption.
3. Desktop and backend restart.
4. Session reopens at the exact approval.
5. Operator edits scope and approves once.
6. One-use capability is consumed exactly once.
7. Run resumes without duplicate calls.

### Scenario C: Cancellation

1. Agent starts a slow test.
2. Operator cancels.
3. Provider and process tree terminate.
4. No further mutation starts.
5. Worktree remains inspectable.
6. Event stream ends in `CANCELLED`.
7. Evidence reports termination status.

### Scenario D: Remote target fidelity

1. Open an SSH workspace.
2. Agent reads, edits, tests, and verifies remotely.
3. All events identify the SSH target.
4. Disconnect the network.
5. Run pauses, never falls back to local.
6. Reconnect and resume.
7. Promote only after remote verification.

### Scenario E: Prompt injection

1. Agent fetches an issue containing malicious instructions.
2. Tool output is marked untrusted external data.
3. Injection cannot alter system policy or tool authority.
4. Sensitive file access still requires approval.
5. Attempt is recorded.

---

## 26. Model and subagent strategy

### 26.1 Do not begin with an uncontrolled swarm

First establish one reliable main agent loop.

Subagents are permitted only when:

- the subtask is clearly bounded;
- the tool set is restricted;
- context is isolated;
- the parent run owns the budget;
- results return as data;
- subagents cannot promote or widen authority;
- parallelism has an explicit limit.

### 26.2 Initial roles

#### Scout

- local;
- read-only;
- classify task;
- shortlist context and tools;
- propose test targets.

#### Implementer

- strong coding model;
- worktree mutation tools;
- bounded plan and repair.

#### Critic

- separate context;
- inspect diff, risk, and omissions;
- no mutation by default.

#### Verifier

- deterministic checks first;
- model interprets failures and recommends next verification;
- cannot declare success against failing evidence.

### 26.3 Hooks

Add deterministic hooks around the run:

```text
RunCreated
TaskScoped
BeforeModel
AfterModel
BeforeTool
AfterTool
BeforeMutation
AfterMutation
BeforeVerification
AfterVerification
BeforeSourcePlan
AfterSourcePlan
RunCompleted
RunFailed
```

Hooks are policy-controlled and cannot silently bypass SourcePlan.

---

## 27. Migration strategy

### 27.1 Strangler migration

Do not replace the existing Pair Programmer in one risky rewrite.

1. Add new AgentRun API behind a feature flag.
2. Keep Ask and Edit on the existing path initially.
3. Route Agent mode to the new runtime.
4. Mirror events into the old session display where needed.
5. Compare outputs and evidence.
6. Migrate Edit mode after Agent mode stabilises.
7. Retire query-string SSE and transient approval polling.
8. Keep compatibility endpoints for one release.
9. Remove old orchestration only after replay and migration tests pass.

### 27.2 Session-store migration

The existing JSON AgentSessionStore becomes a compatibility facade:

- import existing sessions;
- convert history into projection records;
- retain original IDs;
- preserve user-visible conversations;
- mark old runs as `legacy_non_resumable`;
- stop rewriting a single global JSON registry;
- use transactional storage and locking.

### 27.3 Feature flags

```text
BEAST_AGENT_RUNTIME_V2
BEAST_AGENT_EVENT_REPLAY
BEAST_AGENT_DURABLE_APPROVALS
BEAST_AGENT_WORKTREE_REQUIRED
BEAST_EXTENSION_API_TIER
BEAST_REMOTE_TARGET_SERVICE
BEAST_WORKSPACE_TRUST_V2
```

Each flag must have:

- owner;
- default;
- removal condition;
- telemetry;
- rollback test.

---

## 28. First 30 implementation commits

1. Add generated build identity.
2. Add canonical parity contract schema.
3. Generate capability and test reports.
4. Correct stale parity fixtures and dates.
5. Add canonical import guard.
6. Extract Electron security policy.
7. Extract gateway host from `main.js`.
8. Extract execution-target host.
9. Extract Git, task, test, terminal, LSP, DAP, notebook, and extension hosts.
10. Split `app/routes/ide.py` into route modules.
11. Create AgentRun state and event models.
12. Add Sensorium-backed run store and projection.
13. Add POST AgentRun creation.
14. Add sequenced event replay endpoint.
15. Add backend execution-handle registry.
16. Add real cancellation propagation.
17. Add durable approval interruptions.
18. Add Agent Passport and one-use capability binding.
19. Add typed tool registry.
20. Add bounded model/tool loop.
21. Add stagnation and budget enforcement.
22. Require Worktree Forge for Agent mutations.
23. Feed Quality Cascade failures into repair turns.
24. Generate SourcePlan from verified worktree diff.
25. Split renderer AI client into state, events, approvals, plan, and views.
26. Replace `window.confirm()` for agent authority.
27. Add run timeline and context manifest.
28. Add reconnect and restart-resume acceptance.
29. Add seeded multi-file agent repair benchmark.
30. Make AgentRunEngine the default Agent-mode path.

---

## 29. Risk register

| Risk | Consequence | Mitigation |
|---|---|---|
| Parity scope expands forever | No releasable finish line | Publish the contract and explicit non-goals |
| New runtime duplicates existing systems | More competing authorities | Canonical ownership and adapter-only integration |
| Agent autonomy weakens governance | Unsafe mutation or execution | Worktree, capability, budget, SourcePlan boundary |
| Extension compatibility weakens security | Host compromise | Tiered API, OS isolation, capability broker |
| Provider behaviour is inconsistent | Stalled or malformed runs | Schema validation, retries, routing, checkpointing |
| Local models underperform | Poor patches and long latency | Scout role, bounded local tasks, explicit escalation |
| Event store grows without bound | Disk and replay issues | compaction projections, retention, archive policy |
| Remote target state becomes ambiguous | Local/remote mistakes | immutable target identity and no silent fallback |
| Tests become string-based theatre | False green reports | behavioural fixtures and live runtimes |
| Crystal claims outrun evidence | Credibility loss | strict proof, equivalence, staleness and replay gates |
| UI becomes telemetry-heavy again | Poor daily workflow | conversation/code first, progressive disclosure |
| Large archive and generated evidence bloat | Repository and release friction | retention, external artifact storage, generated manifests |
| One developer carries too much architecture | fragile ownership | modular contracts, ADRs, testable boundaries |

---

## 30. Immediate priority stack

### Do now

1. Freeze the parity contract and build identity.
2. Correct fixture and documentation drift.
3. Split orchestration boundaries.
4. Implement AgentRun state, events, replay, cancellation, and approval.
5. Route Agent mode into Worktree Forge.
6. Close one real inspect, edit, test, repair, SourcePlan loop.

### Do next

1. Live SSH and Compose CI.
2. Remote file watching and remote extension lifecycle.
3. Git graph and merge editor.
4. LSP/DAP version matrices and richer refactor/debug UX.
5. Test adapters and notebook rich output.
6. Workspace Trust and Electron/extension sandbox hardening.

### Do after the runtime is stable

1. Bounded subagents.
2. Agent hooks and plugin packaging.
3. Broader extension compatibility tiers.
4. Skills and crystal promotion from verified Agent runs.
5. Public BEASTBench and inference-economy evaluation.
6. Commercial release channels and enterprise policy management.

---

## 31. Definition of “BEAST has reached the next level”

The upgrade is complete when BEAST can demonstrate all of the following from one release commit:

1. A user opens a local, SSH, or Dev Container workspace.
2. Workspace Trust and target identity are explicit.
3. Editing, Git, search, LSP, DAP, tests, tasks, terminals, notebooks, and the supported extension subset pass their published journeys.
4. Agent mode creates a durable run rather than a transient stream.
5. The model repeatedly selects bounded tools and receives observations.
6. All mutation occurs in a mission worktree.
7. Approval is durable, scoped, and capability-bound.
8. Cancellation actually stops provider and process work.
9. A disconnected client can replay and resume the run.
10. Verification failures return to the same run for bounded repair.
11. The final diff becomes a SourcePlan.
12. Only the operator can promote to the workspace.
13. The resulting operation has hashes, tests, evidence, rollback, target identity, context provenance, provider route, and cost.
14. Chronicle records the outcome.
15. Skill or crystal promotion is considered only after verified success.
16. The complete parity and security matrices are generated and green.
17. Known unsupported extension and protocol surfaces are stated honestly.

At that point, BEAST is not merely “close to VS Code.”

It is a governed development operating environment with a familiar workbench and a fundamentally stronger accountability model for autonomous AI execution.

---

## 32. Final recommendation

The highest-leverage path is not to add more independent dashboards, more parallel orchestrators, or another grandly named subsystem.

The next release should make one architectural promise:

> **Every coding task has one durable run, one execution target, one bounded authority envelope, one evidence chain, one isolated mutation space, and one human-controlled promotion boundary.**

Wire the systems you already built into that promise.

That is the bridge from an extraordinary collection of engines to a coherent world-class platform.

Linux DAMON, resctrl, Pressure Stall Information, host file server name forwarding, python threads, BPF ring buffer, fanotify, sock diag, pidfd open, pidfd getfd, process madvise, memfd           
   create, BPF sk lookup, SO reuseport, and e-graphs  

System Hardening │ DAMON, resctrl, PSI, fanotify        │ app/kernel interfaces for monitoring and managing system pressure and memory tiering policies.                         │
  │ Execution        │ pidfd (open/getfd), memfd, e-graphs  │ app/kernel/execution hardening to use pidfd for safe process tracking and memfd for secure memory sharing; e-graphs in │
  │ Primitives       │                                      │ app/kernel/compute for rewrite optimization.                                                                           │
  │ High-Perf        │ AF_XDP, BPF (sk lookup/ring buffer), │ app/kernel & app/proxy for low-latency packet handling, socket steering, and BPF-based observability. 
Networking       │ SO_REUSEPORT      

IPFS-style content identifiers, OCI registries, In-toto, Xet chunks, AF_XDP, Linux VRF, RATS, BGP route-flap damping, zswap, Kernel Samepage Merging. research how best to integrate or improve     
   these implementations

  Integration Roadmap

  1. Security & Provenance (app/adapters)
   * OCI Registries & IPFS-style CIDs: Implement a generic ArtifactAdapter to pull images/data by CID from OCI-compliant registries (e.g., Harbors/Docker Hub).
   * In-toto & RATS: Integrate an AttestationAdapter to verify In-toto supply chain layouts and RATS-compliant remote attestation before agent workload execution.

  2. Performance Networking (app/kernel & app/proxy)
   * AF_XDP: Introduce a dedicated high-performance socket handler in app/kernel for bypassing the kernel stack for packet processing.
   * Linux VRF: Manage network namespaces and VRFs via app/kernel primitives to isolate agent traffic paths.
   * BGP Route-flap Damping: Integrate into app/proxy to stabilize routing updates for edge workloads.

  3. Memory & Storage (app/kernel & app/data)
   * Xet Chunks & CIDs: Implement a data-layer chunking service in app/data to manage granular, CID-backed updates.
   * zswap & KSM: Manage these at the app/kernel level via sysfs interfaces to optimize memory utilization for dense agent workloads.

BPF/AF_XDP/Zero-copy transport
