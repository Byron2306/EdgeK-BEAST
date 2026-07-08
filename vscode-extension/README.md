# EdgeK BEAST VS Code Extension

This extension is the Phase 1 BEAST IDE shell. It keeps the dark, compact,
terminal-native look of the BEAST TUI while bringing Mission Control, governed
SourcePlan editing, Evidence Bus lookup, lattice replay scaffolding, worktree
missions, MCP governance, Chronicle, and provider fitness into VS Code.

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
- `BEAST: Show Evidence Bus`
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
- Create an isolated worktree mission.
- Scaffold a gated lattice replay candidate.

## Source Workbench

`BEAST: Open Source Workbench` shows the current SourcePlan scorecard, policy
gate decision, lattice replay status, rollback/worktree recommendation, and
suggested verification commands. Preview and apply buttons still call BEAST MCP
tools and preserve explicit approval.

## SourcePlan Flow

1. Open a source file and optionally select code.
2. Run `BEAST: SourcePlan from Selection`.
3. Review policy, lattice, rollback, and test guidance in Source Workbench.
4. Run `BEAST: Preview Hunks`.
5. Review the diff.
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
