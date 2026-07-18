# OPCB Desktop UI Wiring Plan

## Progress Notes

- Phase 1 complete: OPCB controls now use an explicit contract (`data-ide-action`, `data-opcb-refresh`, `data-opcb-select`, `data-page-target`, or `data-prototype-reason`).
- Phase 2 complete: OPCB has a gateway-first live store and route contract probing.
- Phase 3 complete: Workspace, Mission, Evidence, and Map load live gateway payloads into the OPCB view model.
- Phase 4 in progress: Review, Trust, and Crystallization now have live adapters and dashboard controls route through the real IDE action manifest.
- Phase 5 in progress: OPCB actions and refreshes write to a visible Action Ledger, Gateway Doctor exposes route-contract probes, and full readiness scoring combines route health, critical action blockers, release-readiness checks, and recent failures.
- Current push: Models, Agents, and Memory now have live-store adapters for provider registry/state, tooling snapshot, agent sessions, memory stack, and evidence summaries; crystallization live data now writes to the correct `crystal` state key.
- Control audit push: OPCB dashboard/right-rail buttons now pass a static contract audit; Mission health, Scope pills, Canary details, integrity checks, gates, attestations, model fallback/explain, and agent command chips are bound to page navigation, live refresh, readiness, or existing IDE actions.
- Workspace selection fix: the main process now tracks `activeWorkspaceRoot`, status/gateway probes/local fallbacks use it, persisted workspace wins on startup, and the renderer guards file refreshes with `workspaceRevision` so stale in-flight snapshots cannot replace newly chosen workspace files.
- Select-control push: `data-opcb-select` controls now update local UI state and action ledger instead of only logging; Workspace Fit/100/List shows active state and list mode, Map filter buttons actually filter graph nodes, and Gateway Doctor route selection opens a selected-route detail card.
- Files/System/Tooling/MCP push: Workspace and Mission no longer hide the file explorer, `setDesktopPage` is exported for OPCB page-target controls, Tooling entry refreshes MCP ops, System has local manifest actions, and every OPCB command strip now includes `/files`, `/tooling`, `/mcp`, `/system`, and `/doctor`.

## Current Diagnosis

The new OPCB dashboard pages are visually close to the intended cockpit, but they are not yet wired as first-class product surfaces. Most real functionality already exists elsewhere in the desktop IDE or gateway; the gap is an adapter layer between the new dashboard markup and those real handlers/routes.

Gateway health is phase zero. When the gateway is offline, stale, or warming, the UI can still browse and edit local files through Electron IPC, but SourcePlan, Evidence Bus, agent sessions, MCP ops, provider routes, workspace graph, crystal/lattice, memory, skills, swarm, and most diagnostics become unavailable or fallback-only.

## Gateway-First Work

1. Add a dedicated gateway contract check before rendering live OPCB data.
   - Source: `window.beastDesktop.status()`
   - Existing gateway startup: `desktop-ide/main.js`
   - Required routes:
     - `/edgek/root-info`
     - `/edgek/ide/snapshot`
     - `/edgek/ide/actions/manifest`
     - `/edgek/workspace/files`
     - `/edgek/evidence-bus/query`
     - `/edgek/ide/agent-sessions`
     - `/edgek/workspace/export`
     - `/edgek/crystal-compute`
     - `/edgek/memory/stack`

2. Surface gateway failure as a blocking state on live controls.
   - Mark affected controls with `data-live-requires="gateway"`.
   - Disable them when `lastGatewayStatus.health.ok` is false.
   - Keep local-only controls enabled: file explorer, local file read, local tooling snapshot, local release readiness.

3. Improve startup diagnosis.
   - Add "Open Gateway Doctor" action from every dashboard rail.
   - Show `lastGatewayCommand`, pid, port, tcp state, root route error, and route capability checks.
   - Add a one-click "Restart Gateway And Recheck Routes" action mapped to `doctor.restart_gateway`.

4. Expand `/edgek/root-info` or gateway capability probing to include OPCB dependencies.
   - Current capability health only checks IDE snapshot/events/timeline/workspace files.
   - Add checks for Evidence Bus, actions manifest, agent sessions, workspace graph export, crystal compute, memory stack, MCP state.

## Markup Contract

Every visible interactive control in OPCB should be one of these:

```html
<button data-ide-action="evidence.search">Search Evidence</button>
<button data-opcb-refresh="evidence">Refresh Evidence View</button>
<button data-opcb-select="evidence-file" data-id="...">Select File</button>
<button data-page-target="review">Open Review</button>
<button data-prototype-reason="No backend route yet" disabled>Future Control</button>
```

Rules:

- No plain `<button>` inside `.opcb-dashboard` or `#opcbRightRail`.
- No dashboard control should rely on label text for behavior.
- Use `data-ide-action` when the action exists in `/edgek/ide/actions/manifest`.
- Use `data-opcb-refresh` for page-level data loaders.
- Use `data-opcb-select` for local view selection.
- Use `data-prototype-reason` only when a backend route truly does not exist yet.
- Add `data-live-source` to panels that render live data.

## Existing Real Surfaces To Reuse

Desktop action manifest:

- `mission.refresh_snapshot` -> `/edgek/ide/snapshot`
- `mission.route` -> `/edgek/ide/mission-route`
- `sourceplan.*` -> SourcePlan draft, lifecycle, verify, apply, runbook, handoff, learning proposal
- `code.symbol_search` -> `/edgek/ide/symbol-search`
- `code.intel` -> `/edgek/ide/code-intel`
- `agents.*` -> `/edgek/ide/agent-sessions/*`
- `worktrees.*` -> `/edgek/ide/worktree-mission/*`
- `evidence.search` -> `/edgek/evidence-bus/query`
- `evidence.choose_receipts` -> `/edgek/ide/receipts/chooser`
- `terminal.*` -> Safety Governor and streaming terminal routes
- `providers.*` -> provider registry and smoke checks
- `tooling.*` -> tooling, MCP, plugin, benchmark, environment checks
- `system.*` -> ports, processes, packages, extensions, catalog
- `doctor.*` -> gateway restart/report
- `settings.release_readiness` -> `/edgek/ide/release-readiness/check`

Studio integration functions already exist in `desktop-ide/renderer/beast-studio-integrations.js`:

- `refreshCrystalization()` -> `/edgek/crystal-reuse`
- `refreshCrystalChain()` -> `/edgek/crystal-chain`, `/edgek/crystal-lattice`
- `refreshMemoryState()` -> `/edgek/memory/stack`
- `refreshEvidenceState()` -> `/edgek/chronicle`
- `studioBuildEvidencePack()` -> `/edgek/evidence/score`
- `refreshCodeGraph()` -> `/edgek/capabilities`
- `refreshApprovalState()` -> `/edgek/mcp/approvals`
- `refreshSkillsSummary()` -> `/edgek/skills/state`
- `studioMineSkills()` -> `/edgek/skills/mine`
- `studioGenerateSkillCandidates()` -> `/edgek/skills/candidates/generate`
- `refreshSwarmState()` -> `/edgek/swarm/state`
- `studioRunSwarm()` -> `/edgek/swarm/run`
- `refreshComputeEconomy()` -> compute economy routes
- `refreshRuntimeState()` and `studioSweepRuntime()` -> runtime routes
- `studioSelectRoute()` -> route selection/economist surface

## Unimplemented Or Partially Implemented OPCB Controls

### Workspace

Currently real:

- Page navigation via `data-page-target`

Needs wiring:

- `Fit`, `100%`, `List`
- Mission brief card action
- Model route card action
- Toolbelt/manage tools action
- Review/evidence/crystallization detail card actions should use real `data-page-target` or `data-ide-action`

Plan:

- Add `data-opcb-canvas="fit|zoom-reset|list"` for flow canvas controls.
- Map cards to pages or manifest actions:
  - Mission brief -> `mission.route`
  - Model route -> `providers.refresh`
  - Toolbelt -> `tooling.refresh`
  - Review gates -> `evidence.search`
  - Evidence sink -> `evidence.search`
  - Crystallization -> `sourceplan.propose_learning` or crystal chain refresh

### Mission

Currently real:

- Mission path navigation
- Snapshot route exists
- Mission timeline route exists
- Mission route route exists

Needs wiring:

- `Open Full Brief`
- `View Gaps`
- Success criteria edit/view
- Timeline values should come from `/edgek/ide/mission-timeline`
- Mission metrics should come from `/edgek/ide/snapshot`
- Next best action rail should call its actual manifest action

Plan:

- Build `loadOpcbMissionViewModel()` from:
  - `/edgek/ide/snapshot`
  - `/edgek/ide/mission-route`
  - `/edgek/ide/mission-timeline`
- Mark all mission cards with `data-live-source`.
- Use `data-ide-action="mission.route"` and `data-ide-action="mission.refresh_snapshot"`.

### Models

Currently real:

- Provider setup and smoke checks exist.
- Route selection exists in Studio integration.
- Provider page already has live setup controls.

Needs wiring:

- `Model Settings`
- `Test Route`
- model rows
- runtime cards
- `+ Add Model`
- route tests
- hardware profile and utilization should be live

Plan:

- Build `loadOpcbModelsViewModel()` from:
  - provider registry routes
  - `/edgek/ide/tooling-snapshot`
  - local system snapshot for GPU/CPU/memory
  - Studio route selection function if available
- Map:
  - `Model Settings` -> `providers.refresh`
  - `Test Route` -> provider smoke or `studioSelectRoute`
  - `Run New Test` -> provider smoke or benchmark route
  - runtime cards -> provider/runtime detail selection
  - `+ Add Model` -> provider page with command palette focused

### Agents

Currently real:

- Agent session create/update/pause/resume/cancel/send/run-events routes exist.
- Agent page has real handlers.

Needs wiring:

- Orbit nodes should select real agent sessions.
- Live handoff stream should use agent run events or IDE events.
- Capability matrix should use session/tools from real agent sessions.
- Assign Agent should create an agent session.

Plan:

- Build `loadOpcbAgentsViewModel()` from:
  - `/edgek/ide/agent-sessions`
  - `/edgek/ide/events`
  - `/edgek/mcp/state`
- Map:
  - `Assign Agent` -> `agents.create`
  - orbit node -> select session, open real Agents page drawer or detail
  - capability row -> agent detail
  - review access -> trust page

### Review

Currently real:

- SourcePlan lifecycle/scorecard/verifier routes exist.
- Evidence receipts exist.
- Runbook verify/export exists.

Needs wiring:

- Score dials are static.
- Gate rows are static.
- Diff review is static.
- Risk register, contradiction check, tests, final recommendation are static.
- Approval rail is static except MCP approval data exists elsewhere.

Plan:

- Build `loadOpcbReviewViewModel()` from:
  - current SourcePlan lifecycle
  - `/edgek/sourceplan/verify`
  - `/edgek/ide/receipts/chooser`
  - `/edgek/evidence-bus/query`
  - MCP approvals if applicable
- Map:
  - `View Details` -> evidence search filtered to review gate receipts
  - `View Report` -> runbook verify/export
  - `Open Scorecard` -> sourceplan lifecycle scorecard
  - `View Full Diff` -> SourcePlan preview/diff panel
  - `Open Risk Register` -> SourcePlan action contract
  - `Review Contradictions` -> evidence query for contradiction artifacts
  - `Generate Review Report` -> `sourceplan.export_runbook`
  - approve/request/re-run -> `sourceplan.verify`, `sourceplan.apply`, or MCP approval route depending state

### Evidence

Currently real:

- Evidence Bus query exists.
- Receipt chooser exists.
- Runbook/evidence export exists through SourcePlan/runbook.
- Studio evidence pack route exists.

Needs wiring:

- Evidence file list is static demo data.
- `Open`, `View All Entities`, trace link cards, export format buttons, checkboxes are static.
- Search/filter input is markup-only.

Plan:

- Build `loadOpcbEvidenceViewModel()` from:
  - `/edgek/evidence-bus/query`
  - `/edgek/evidence-bus/summary`
  - `/edgek/evidence-bus/related/{key}`
  - `/edgek/ide/receipts/chooser`
  - file preview from `/edgek/workspace/file` when receipt points to workspace artifact
- Map:
  - evidence rows -> receipt/file selection
  - `Open` -> open real file if local path exists, otherwise show receipt JSON
  - `Filter` -> query Evidence Bus
  - trace links -> `/edgek/evidence-bus/related/{key}`
  - `Export Evidence` -> runbook/handoff/evidence pack generation
  - `Generate Audit Pack` -> handoff package or evidence score route

### Crystallization

Currently real:

- Crystal compute routes exist.
- Crystal chain/lattice Studio integrations exist.
- Learning proposal route exists.

Needs wiring:

- Candidate queue is static.
- Crystal readiness is static.
- Quality gates and event ledger are static.
- Verify/Crystallize/Seal/Export are mapped only to generic readiness today.

Plan:

- Build `loadOpcbCrystalViewModel()` from:
  - `/edgek/crystal-compute`
  - `/edgek/crystal-chain`
  - `/edgek/crystal-lattice`
  - `/edgek/mission-lattice/summary`
  - `/edgek/mission-lattice/lookup`
  - `/edgek/ide/learning-queue/propose`
- Map:
  - candidate row -> select real crystal/credit/lattice candidate
  - `Verify` -> release readiness plus lattice verification
  - `Crystallize` -> learning proposal or crystal-compute outcome record, depending selected candidate
  - `Seal` -> crystal chain/lattice append route if present; otherwise disabled with reason
  - `Export` -> runbook/handoff package
  - event ledger -> crystal chain/lattice events

### Trust

Currently real:

- Safety Governor routes exist.
- SourcePlan action contract has approval/rollback/policy.
- MCP approval/audit routes exist.
- Release readiness exists.

Needs wiring:

- Trust score, canaries, provenance, attestation, permissions, audit timeline are mostly static.

Plan:

- Build `loadOpcbTrustViewModel()` from:
  - `/edgek/safety-governor/scan-workspace`
  - `/edgek/ide/release-readiness/check`
  - `/edgek/mcp/approvals`
  - `/edgek/mcp/audit`
  - `/edgek/workspace/integrity`
  - SourcePlan action contract when a plan exists
- Map:
  - `View Boundary Map` -> workspace/context pack or trust map
  - `Verify Now` -> release readiness + workspace integrity
  - `View Policies` -> Safety Governor/policy panel
  - `Run All Checks` -> readiness + integrity + MCP state
  - access controls -> MCP/tooling approvals or settings

### Memory

Currently real:

- Memory stack Studio integration exists.
- Skills routes exist.
- Mission lattice and crystal compute can provide memory-like signals.

Needs wiring:

- Observatory/starfield is static.
- Skill candidates are static.
- Promote Skill is static.
- Recall query is not surfaced on the OPCB page.

Plan:

- Build `loadOpcbMemoryViewModel()` from:
  - `/edgek/memory/stack`
  - `/edgek/mission-lattice/summary`
  - `/edgek/skills/state`
  - `/edgek/meta-tool-commons/candidates`
- Map:
  - constellation node -> filter memory layer/entity
  - `Promote Skill` -> `/edgek/skills/candidates/generate` then candidate selection; promotion route if available
  - rail `Run Recall Query` -> memory query input/modal

### Map

Currently real:

- Workspace graph export/search/node/neighborhood routes exist.
- Code Cortex symbols/dependents/context routes exist.
- Code intelligence handler exists.

Needs wiring:

- Graph nodes and edges are static demo coordinates.
- Toolbar search/filter/group/layout/fit are inert.
- Selected node rail is static except selected id changes.

Plan:

- Build `loadOpcbMapViewModel()` from:
  - `/edgek/workspace/export`
  - `/edgek/workspace/search`
  - `/edgek/workspace/nodes/{node_id}`
  - `/edgek/workspace/context`
  - `/edgek/code-cortex/dependents`
  - `/edgek/ide/code-intel`
- Map:
  - graph node -> fetch node detail/neighborhood and open file when possible
  - search -> workspace search
  - filters/group/layout -> client-side graph transform
  - fit -> graph viewport transform
  - selected node rail -> real file summary/dependents

## Implementation Stages

### Stage 0: Gateway Reliability

- Add OPCB gateway contract probe.
- Improve Doctor with OPCB-required route matrix.
- Add one-click restart/reprobe action.
- Disable live controls when gateway contract fails.

Acceptance:

- When gateway is offline, every affected control explains why.
- When gateway is online, OPCB route matrix shows green for required routes.

### Stage 1: Control Contract Cleanup

- Replace all plain OPCB buttons with `data-ide-action`, `data-opcb-refresh`, `data-opcb-select`, `data-page-target`, or disabled prototype reason.
- Remove duplicate/malformed dashboard HTML blocks.
- Add automated test that fails on plain buttons inside `.opcb-dashboard`.

Acceptance:

- Zero silent dashboard controls.
- Clicking any dashboard button either executes, navigates, selects, refreshes, or logs a disabled reason.

### Stage 2: Shared OPCB Data Store

- Add `desktop-ide/renderer/opcb-live-store.js`.
- Store:
  - gateway contract
  - current live page view models
  - loading/error states per page
  - selected ids for evidence, crystal, map, agent, model
- Add `window.opcbRefreshPage(page, options)`.
- Keep seeded `opcbState` only as fallback/demo data.

Acceptance:

- Each page can render loading, live, fallback, and error states.

### Stage 3: Core Pages

- Wire Mission, Workspace, Evidence, Map.
- These unlock actual files, graph, receipts, route, and timeline.

Acceptance:

- Evidence rows are real receipts/files.
- Map nodes come from workspace graph export or Code Cortex fallback.
- Mission path/timeline comes from gateway.

### Stage 4: Governance Pages

- Wire Review, Trust, Crystallization.
- Use SourcePlan lifecycle, Evidence Bus, MCP approvals, readiness, workspace integrity, crystal/lattice routes.

Acceptance:

- Review gates reflect real SourcePlan/evidence state.
- Trust posture reflects readiness/integrity/MCP approvals.
- Crystallization candidates reflect crystal compute/lattice/learning queue.

### Stage 5: Intelligence Pages

- Wire Models, Agents, Memory.
- Reuse provider, agent session, memory stack, skills, swarm, runtime integrations.

Acceptance:

- Model route reflects provider/runtime state.
- Agent constellation reflects real sessions/events.
- Memory page reflects memory stack and skill candidates.

### Stage 6: Regression Tests

- Add renderer tests:
  - no inert OPCB buttons
  - all `data-ide-action` ids exist in local or gateway manifest
  - all `data-live-source` panels have fallback/error state
  - gateway-offline mode disables live-only actions
- Extend smoke launch to visit each OPCB page and click representative controls.

## First Patch Targets

1. Gateway route matrix in Doctor and header.
2. OPCB button contract test.
3. Evidence live view model.
4. Map live view model.
5. Review live view model.

This order gives the UI its spine: gateway, controls, proof, graph, governance.
