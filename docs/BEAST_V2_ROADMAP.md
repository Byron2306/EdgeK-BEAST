# EdgeK BEAST V2 Roadmap

## Active Integration Board (2026-07-18)

These are execution tracks, not aspirational feature claims.  A track may only
move to **operational** when it is exercised on the normal IDE/CLI/MCP path,
has a bounded failure mode, and has focused regression coverage.

| Track | Status | Completion indicator | Current boundary |
| --- | --- | --- | --- |
| Universal retrieval and context headers | in progress | One metadata-first retrieval response feeds Context Packet, Pair Programmer, CLI, TUI, MCP, Review, Task, and Debug surfaces; the IDE presents suggestions for explicit operator acceptance. | Pair Programmer now uses a direct, hash-bound provider Context Packet and has an explicit **Suggest context** workflow backed by `/edgek/workspace/context-header`; suggestions remain unselected until the operator clicks Add. CLI/TUI/MCP/Review still need to converge on the same visible picker. |
| Least-authority tool-use loop | in progress | Tool discovery is policy-scoped; every call is authorized, budgeted, receipt-backed, and cannot widen file/network/write authority. | `LeastAuthorityToolLoop` composes Mode Router and tool buckets into per-tool authorization receipts, structurally refuses generic mutation executors, and exposes a separate mutation-entry gate. IDE Conductor dispatch uses it for task/context/route/verification; MCP exposes `beast_least_authority_plan` and now mutation-gates declared mutating calls; CLI diagnose/route/verify and TUI draft/verify attach the same receipt; `BeastApiClient.apply_patch_plan` now requires a bound, approved mutation-gate receipt before its existing preview/verification/rollback pipeline. CLI/TUI rollback and remaining direct mutation routes still need migration. |
| Conductor inspect → test → repair | in progress | A bounded dispatcher persists each step, stops at approval/scope/budget gates, runs deterministic verification, and hands off only valid SourcePlans. | Pair Programmer now runs Pathfinder and Tool Laziness before provider dispatch, then Quality Cascade, a receipt-backed Conductor dispatch, and Canon validation after bounded proposal validation. Dispatch receipts persist under `.beast/intelligence/workflow_dispatches`; `resume()` reloads the latest receipt and replays only bounded non-mutating callbacks. The dispatcher can stop on a gate, execute registered inspect/verify callbacks, and request a repaired **draft** after a failed verification; it cannot execute a source write. CLI/TUI/MCP executor bindings remain. |
| L0-L4 vector memory projections | operational | Local LanceDB is the L2 rebuildable workspace-source view. Aurora pgvector, Qdrant, and Chroma are reserved for validated L3 verified-skill and L4 forensic-summary projections; all results retain layer and store attribution. | Workspace source, prompts, diffs, and logs are structurally refused by cloud projection. L0 policy and L1 runtime memory stay local. L3/L4 cloud projection requires `verified=true`, a receipt ID, a bounded sanitized summary, and `BEAST_VECTOR_MEMORY_CLOUD_OPERATIONAL_ENABLED=1`; retrieval remains advisory and requires operator acceptance before prompt inclusion. |

### Non-negotiable acceptance rules

- No retrieval suggestion silently becomes provider context or edit scope.
- No tool result, provider placeholder, or KV metadata record is treated as a
  verified execution result.
- No Conductor repair can apply source changes; SourcePlan approval remains the
  mutation boundary.
- No vector backend becomes source of truth or disables lexical fallback.

Working plan for turning BEAST from a governed gateway into a governed
meta-optimization plane for agentic software work.

## V2 Thesis

BEAST V2 should prove one claim before it expands:

AI coding systems waste intelligence when tasks are unprepared. BEAST reduces
that waste by standardizing the task, running cheap local checks first,
packing bounded context, routing safely, verifying outcomes, publishing a
Chronicle, and promoting repeated success into reusable workflow memory.

The first production spine is:

```text
request -> task envelope -> local checks -> context packet -> route decision
-> model/tool action if needed -> verification -> Chronicle -> promotion check
```

The long-term memory architecture should separate truth from retrieval:

- Append-only truth stores: task envelopes, route cards, workflow cards,
  quality reports, Chronicle records, traces, and promotion decisions.
- Retrieval views: vector/RAG indexes, workspace graph projections, semantic
  summaries, and route/workflow recommendations rebuilt from the truth stores.

This gives BEAST a central memory core without making the vector index the
source of truth. The vector layer is where the system "reaches first" when a
new prompt arrives; the append-only layer is where it verifies what actually
happened.

## Layered Memory Model

BEAST's memory model is the L0-L4 stack managed by the EdgeK kernel:

| Layer | Name | Scope | Persistence | Examples |
| --- | --- | --- | --- | --- |
| L0 | Meta Rules | Immutable Governance | Config / Policy DB | Spend caps, shell allowlists, blocked files, destructive gates |
| L1 | Insight Index | Active Session State | In-memory / Redis-ready / runtime ledgers | Cache handles, request hashes, loop signatures, circuit state |
| L2 | Workspace Graph | Project Facts | SQLite / Vector DB | Symbol maps, dependency edges, file trees, semantic chunks |
| L3 | Skill Tree | Reusable Recipes | SQLite / Postgres-ready | Provider diagnostic route, optimized test summarization, repeated fixes |
| L4 | Forensic Archive | Audit and Telemetry | Append-only logs / Chronicle JSON | Request IR traces, tool results, route cards, verification records |

Current endpoint:

```text
GET /edgek/memory/stack
```

This endpoint is the canonical view of how existing BEAST stores map into the
layered model. V2 should evolve memory features by enriching these layers, not
by creating a parallel memory system.

## Current Baseline

Already present:

- Provider adapters for OpenAI, Anthropic, Gemini, Hugging Face, TGI, and LiteLLM.
- Policy-backed governance with request budgets, provider settings, semantic risk checks, and context economy.
- Runtime governor with stasis walls, circuit breakers, attempt history, and stale-attempt sweeps.
- Workspace graph with repository indexing, symbol extraction, semantic context, and trace-derived graph updates.
- MCP broker with tool evaluation, audit, approvals, and constrained execution.
- Skill registry, sequence mining, meta-tool candidates, and promotion scaffolding.
- BEAST cockpit with live state panels.
- V2 seed feature: canonical task envelopes and provider diagnostics.

## V2 North-Star Outcomes

By the end of V2, BEAST should be able to:

- Convert user requests, IDE events, webhook events, and provider failures into canonical task envelopes.
- Run deterministic local diagnostics before spending cloud tokens.
- Build auditable context packets with included/excluded evidence records.
- Select route cards and workflow cards for common software tasks.
- Produce Chronicle records for every task outcome.
- Promote repeated verified workflows into reusable skills or commands.
- Show task state, route state, verification state, and Chronicle output in the cockpit.

## Phase 1: Task Envelope Spine

Status: started.

Scope:

- Canonical `task_envelope` object.
- Task classification for provider debugging, test failure, dashboard widget build, refactor request, and general software task.
- Risk, privacy, context budget, allowed actions, approval gates, and success criteria.
- Dry-run endpoint for task preparation.
- Cockpit visibility for provider diagnostic envelopes.

Endpoints:

```text
POST /edgek/task/envelope
POST /edgek/task/provider-diagnostic
```

Acceptance:

- A provider failure request creates a complete envelope without a model call.
- The envelope is returned in a stable JSON shape.
- Risk and approval gates are explicit.
- Tests cover classification, diagnostics, and endpoint behavior.

## Phase 2: Provider Diagnostic MVP

Status: started.

Scope:

- Local provider policy check.
- Credential environment check.
- Runtime circuit check.
- Recent attempt analysis.
- Local log scan.
- Failure category normalization.
- Recommendation generation.
- Chronicle Markdown output.

Failure categories:

- `auth_or_credentials`
- `quota_or_rate_limit`
- `runtime_circuit_open`
- `network_or_timeout`
- `upstream_server_error`
- `insufficient_local_evidence`

Acceptance:

- A known 429 attempt is categorized as quota/rate limit.
- Missing expected credentials are surfaced without exposing secret values.
- Open circuits produce a no-retry recommendation.
- Chronicle output is written locally and references task id, checks, category, and recommendations.

## Phase 3: Chronicle Engine

Status: started.

Scope:

- Generalize local Markdown Chronicle writing beyond provider diagnostics.
- Add JSON Chronicle records for machine reuse.
- Link Chronicle entries to task envelopes and runtime traces.
- Add Chronicle listing endpoint and cockpit panel.

Proposed endpoints:

```text
GET  /edgek/chronicle
GET  /edgek/chronicle/{task_id}
POST /edgek/chronicle/publish
```

Record shape:

```json
{
  "chronicle_type": "task_summary",
  "task_id": "tsk_...",
  "task_class": "provider_debugging",
  "summary": "...",
  "root_cause": "...",
  "actions_taken": [],
  "verification": {},
  "recommendations": [],
  "memory_candidate": true
}
```

Acceptance:

- Every diagnostic can write Markdown and JSON records.
- Chronicle entries can be listed and searched by task id, class, provider, and category.
- No provider secrets or raw API keys appear in Chronicle output.

## Phase 4: Quality Cascade

Status: started.

Scope:

- Task-class-specific local checks.
- Syntax checks for Python and JavaScript.
- Targeted pytest selection.
- Import/dependency scan.
- Log clustering and stack trace extraction.
- Verification report object.

Initial task classes:

- `provider_debugging`
- `test_failure`
- `dashboard_widget_build`
- `small_patch`

Proposed endpoint:

```text
POST /edgek/task/quality-cascade
```

Acceptance:

- Test-failure envelopes run targeted local checks before cloud escalation.
- Dashboard widget tasks run syntax validation before completion.
- Verification report is attached to Chronicle.

## Phase 5: Context Packet Builder

Status: started.

Scope:

- Evidence-backed handoff packets for local or cloud reasoning.
- Line-anchored file snippets.
- Workspace graph references.
- Semantic context slices.
- Exclusion records for omitted context.
- Token estimates before and after packing.
- Stable packet and evidence hashes for audit/replay.
- Cockpit preview after provider diagnostics.

Current endpoint:

```text
POST /edgek/context/packet
```

Acceptance:

- A packet can be built from a task envelope without uploading the whole repo.
- Included files and omitted files are both recorded.
- Packet hash is stable for identical evidence.

## Phase 6: Pathfinder Route Cards

Status: started.

Scope:

- Route cards for provider debugging, localhost service debugging, GitHub issue triage, test failure repair, and dashboard widget build.
- Cache policy and retry policy per route.
- Route quality scoring using confidence, verification, reuse, risk, cost, and latency.

Proposed endpoints:

```text
POST /edgek/route/card
GET  /edgek/route/cards
```

Acceptance:

- Provider diagnostics use a route card instead of hardcoded check order.
- Route card output explains preferred order, avoided actions, safety gates, and promotion status.

## Phase 7: Forge Scorecards

Status: started.

Scope:

- Refactor and implementation shape scoring.
- Dependency risk profile.
- Adapter compatibility scorecards.
- Minimal-patch-first recommendations.
- Pre-edit gates for compatibility tests, dependency review, and human approval.

Current endpoint:

```text
POST /edgek/forge/scorecard
```

Acceptance:

- A provider-router refactor request produces a risk/benefit scorecard before any code edit.
- High-risk refactors require compatibility tests before patching.

## Phase 8: Conductor Workflows

Status: started.

Scope:

- Workflow cards for common task classes.
- High-level reasoning schema registry.
- Approval gates.
- Recovery paths.
- Promotion checks.
- Swarm advisory integration using existing deterministic role-state runs.
- Explicit executor binding status so planning is not confused with real tool dispatch.

Current endpoints:

```text
POST /edgek/workflow/plan
GET  /edgek/workflow/cards
GET  /edgek/workflow/cards/{workflow_id}
```

Acceptance:

- A task envelope can produce a workflow card.
- Workflow cards describe steps, tools, approvals, verification, and Chronicle output.
- No hidden chain-of-thought is stored; only high-level procedure is retained.
- Existing swarm roles are used as planning/supervision advice only until an executor binding exists.

## Phase 9: Canon Registry

Status: started.

Scope:

- Schema registry for task envelopes, route cards, workflow cards, Chronicle records, and promotion candidates.
- Metric registry.
- Definition registry.
- Policy alignment checks.
- Cross-artifact reference validation for task ids, route ids, packet ids, scorecard ids, and hashes.

Current endpoints:

```text
GET  /edgek/canon/schemas
POST /edgek/canon/validate
GET  /edgek/canon/metrics
```

Acceptance:

- All V2 objects validate against registered schemas.
- Route, workflow, Chronicle, and promotion objects share task ids and evidence ids.
- Validation failures are visible in API and cockpit.

## Phase 10: Skill Promotion Loop

Status: started.

Scope:

- Detect repeated successful task envelopes and route/workflow combinations.
- Promote verified patterns into reusable skills, commands, or templates.
- Require policy review for risky promotions.
- Use Canon validation and Tool Laziness signals before recommending promotion.
- Keep promotion approval-gated; no auto-execution from promotion candidates.

Current endpoints:

```text
POST /edgek/skills/promotion-check
POST /edgek/skills/promote
GET  /edgek/skills/promotion-candidates
GET  /edgek/skills/promotion-candidates/{candidate_id}
```

Acceptance:

- Repeated provider diagnostics can become a promotion candidate.
- Promotion includes pattern, action, verification history, failure rate, and approval status.
- Promoted skills can be selected by later task envelopes.

## Cockpit V2

The cockpit should move from observability-only toward task operations:

- Task Envelope panel.
- Provider Diagnostic runner.
- Chronicle list/detail view.
- Route card visualization.
- Quality Cascade status.
- Promotion candidates.
- Canon validation status.

Near-term cockpit additions:

- Provider Diagnostic card in the Inference tab.
- Chronicle panel under Logs or a new Meta Ops tab.
- Task Envelope JSON preview with copy/download action.

## Immediate Build Queue

1. Expand BEAST CLI into the primary operator surface for MCP install, provider proxy setup, diagnostics, and Openclaw/Nemoclaw execution.
2. Make MCP the governed tool bus for context, planning, Canon, promotion, and executor actions.
3. Expand cockpit Chronicle detail into a full task memory view.
4. Add vector/RAG indexing over Chronicle records, route cards, task envelopes, and high-value tool outcomes.
5. Add test-failure and dashboard-widget Quality Cascade routes.
6. Add role-level swarm execution regression tests once executor bindings cover write-safe workflows.

## Executor Binding: Openclaw / Nemoclaw

Status: started.

Scope:

- Openclaw: BEAST's local-first agentic CLI profile for reasoning, planning, and safe read-only execution.
- Nemoclaw: gated high-risk profile for future write/shell/destructive workflows.
- Ollama-first local inference before cloud reasoning.
- MCP-brokered execution for approved/read-only actions.
- Dry-run default for all execution endpoints.

Current endpoints:

```text
POST /edgek/beast-cli/plan
POST /edgek/beast-cli/execute
```

Acceptance:

- A workflow can produce an Openclaw execution plan with local inference metadata.
- Read-only actions can execute through MCP policy when allowed.
- Gated/Nemoclaw actions refuse execution without explicit approval.
- Executor output is auditable and does not bypass Canon, workflow gates, or MCP policy.

## MCP And CLI Control Plane

Status: started.

Scope:

- `bin/beast` is the local operator CLI with welcome header, doctor/status checks, MCP config install, provider proxy hints, and Openclaw/Nemoclaw commands.
- BEAST MCP exposes V2 tools for task envelopes, quality cascade, context packets, Forge scorecards, Conductor workflows, Canon validation, promotion checks, Openclaw execution, and MCP status/catalog.
- MCP tool catalog includes Metatron-inspired metadata: category, trust state, risk, rate limit, audit level, idempotence, and redaction hints.
- VS Code and other clients should route through BEAST by using the MCP server or provider proxy base URLs; arbitrary extension traffic cannot be transparently intercepted unless the client opts into those routes.

Current commands:

```text
beast serve
beast doctor
beast status
beast mcp
beast mcp-http
beast mcp-config
beast mcp-install
beast providers
beast openclaw-plan
beast openclaw-execute
```

Acceptance:

- `beast mcp` initializes quickly over stdio and lazy-loads the kernel only when needed.
- `tools/list` advertises the full BEAST V2 MCP tool catalog.
- `beast doctor` diagnoses gateway, MCP config, proxy URLs, logo presence, and Ollama readiness.
- CLI commands return JSON for automation and human output with `--human`.

## V2 Guardrails

- No cloud model call until local checks have run unless explicitly requested.
- No secret values in task envelopes, diagnostics, traces, or Chronicle records.
- No production writes without explicit approval.
- No broad refactors without scorecard and tests.
- No hidden reasoning traces; store high-level schemas, evidence, and outcomes.
- Every feature must expose measurable saved tokens, avoided calls, narrowed tool exposure, or improved verification.

## First V2 Demo Scenario

Prompt:

```text
Diagnose why the Hugging Face route is failing.
```

Expected BEAST behavior:

1. Build task envelope.
2. Run local provider diagnostic route.
3. Check policy, credentials, circuit, attempts, and logs.
4. Categorize failure.
5. Recommend fallback or fix.
6. Write Chronicle.
7. Mark promotion candidate if repeated.

This is the smallest demo that proves the larger V2 idea.
