# EdgeK BEAST VS Code Extension

This extension is the Phase 1 BEAST IDE shell. It keeps the dark, compact,
terminal-native look of the BEAST TUI while bringing Mission Control, governed
SourcePlan editing, Evidence Bus lookup, lattice replay scaffolding, worktree
missions, MCP governance, Chronicle, and provider fitness into VS Code.

The VSIX uses the little BEAST dragon mascot throughout the IDE panels. The
marketplace/extension icon is a restrained grey dragon treatment so it fits VS
Code chrome while still matching the TUI identity.

BEAST remains governance-first: edits still flow through SourcePlan, policy
gates, verification, rollback, Chronicle, and evidence receipts. The extension
is an operator cockpit, not a bypass around BEAST mutation rules.

## Commands

- `BEAST: Start Local Governor`
- `BEAST: SourcePlan Current File`
- `BEAST: SourcePlan from Selection`
- `BEAST: Score Current SourcePlan`
- `BEAST: Preview Hunks`
- `BEAST: Apply Selected Hunks`
- `BEAST: Open Mission Control`
- `BEAST: Refresh IDE Snapshot`
- `BEAST: Open Source Workbench`
- `BEAST: Select All Source Hunks`
- `BEAST: Clear Source Hunk Selection`
- `BEAST: Show Evidence Bus`
- `BEAST: Show Code Cortex`
- `BEAST: Show Policy Gate`
- `BEAST: Show Worktrees`
- `BEAST: Start Live IDE Event Bus`
- `BEAST: Jump to Related Tests or Routes`
- `BEAST: Open Side-by-Side Preview`
- `BEAST: Switch SourcePlan Session`
- `BEAST: Refresh SourcePlan Preview`
- `BEAST: Create Worktree Mission`
- `BEAST: Scaffold Lattice Replay`
- `BEAST: Select Provider Role`
- `BEAST: Refresh Chronicle`
- `BEAST: Refresh Route Fitness`
- `BEAST: Run Maintenance Cascade`
- `BEAST: Open Maintenance Report`
- `BEAST: Prepare Handoff Packet`
- `BEAST: Configure Integrated Terminal Gateway`
- `BEAST: Install Workspace MCP Config`

## Activity Bar Views

- **BEAST Status**: gateway, provider, provider role, MCP lane, workspace.
- **Mission Control**: compact IDE snapshot for cockpit cards, SourcePlan queue,
  Evidence Bus, Code Cortex, lattice, and worktrees.
- **Chronicle**: recent BEAST Chronicle records.
- **Route Fitness**: provider score and recommended runtime role.

## Mission Control

`BEAST: Open Mission Control` opens an in-editor webview backed by
`/edgek/ide/snapshot`. It intentionally reuses the BEAST TUI visual language:
black-green-cyan palette, compact cockpit cards, monospace labels, and explicit
operator actions.

The webview can:

- Prepare a SourcePlan from the active editor selection.
- Open the Source Workbench.
- Show Evidence Bus receipts.
- Show Code Cortex context, file summary, and dependents.
- Show the unified Policy Gate state.
- Show worktree missions.
- Subscribe to the live BEAST IDE event stream.
- Create an isolated worktree mission.
- Scaffold a gated lattice replay candidate.

## Source Workbench

`BEAST: Open Source Workbench` shows the current SourcePlan scorecard, policy
gate decision, lattice replay status, rollback/worktree recommendation, and
suggested verification commands. Preview and apply buttons still call BEAST MCP
tools and preserve explicit approval.

The workbench also keeps an active SourcePlan session in VS Code workspace
state. Source operations are visible as selectable cards, and changed ranges for
the active file are decorated in the editor:

- green ranges are selected for apply;
- muted ranges are skipped;
- red ranges are stale and require plan refresh.
- side-by-side preview opens BEAST virtual old/new documents without writing
  files.
- multi-plan sessions are persisted in VS Code workspace state and can be
  switched from CodeLens or the Source Workbench.

## Inline Intelligence

The extension contributes lightweight inline IDE affordances:

- CodeLens actions for SourcePlan from selection, related tests/routes, current
  hunk selection count, and stale context warnings.
- Hovers over BEAST-decorated ranges with hunk status and SourcePlan summary.
- Diagnostics for stale SourcePlan context.
- Diagnostics for high-risk plans and worktree recommendations.
- `BEAST: Jump to Related Tests or Routes`, powered by Code Cortex dependents.
- Stale preview refresh from CodeLens or command palette.

## Live Event Bus

`BEAST: Start Live IDE Event Bus` connects to `/edgek/ide/events` and listens
for SourcePlan, policy, evidence, context/index, worktree, and lattice events.
The IDE remains usable if the stream stops; BEAST falls back to request/response
commands and snapshot refresh.

## SourcePlan Flow

1. Open a source file and optionally select code.
2. Run `BEAST: SourcePlan from Selection`.
3. Review policy, lattice, rollback, and test guidance in Source Workbench.
4. Select or clear individual source operations in the workbench.
5. Review editor decorations and the generated diff.
6. Run `BEAST: Apply Selected Hunks`.

Apply calls BEAST MCP tool `beast_sourceplan_apply_selected` with explicit
approval. BEAST verifies, writes rollback state, and crystallizes Chronicle and
Evidence Bus records.

## MCP Lane

The extension registers `beast mcp --workspace <workspace>` as a stdio MCP
server.

Key MCP tools:

- `beast_sourceplan_prepare`
- `beast_sourceplan_scorecard`
- `beast_sourceplan_preview_hunks`
- `beast_sourceplan_apply_selected`
- `beast_sourceplan_rollback_latest`
- `beast_mission_lattice_replay_scaffold`
- `beast_worktree_create`
- `beast_evidence_bus_summary`
- `beast_provider_fitness`
- `beast_prepare_handoff`
- `beast_architecture_decisions`
- `beast_mcp_tool_catalog`

## Terminal Gateway Variables

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8000/proxy/anthropic"
export OPENAI_BASE_URL="http://127.0.0.1:8000/proxy/openai/v1"
export ENABLE_TOOL_SEARCH=true
```
