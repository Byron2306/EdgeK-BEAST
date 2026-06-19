# EdgeK BEAST VS Code Extension

This extension turns VS Code into a BEAST operator surface for governed coding work.

It provides:

- BEAST MCP server registration
- `/sourceplan`-style current-file patch planning
- hunk diff preview before apply
- explicit approval before selected hunk apply
- rollback-backed apply through BEAST
- Chronicle panel
- route fitness panel
- provider role selector

## Commands

- `BEAST: Start Local Governor`
- `BEAST: SourcePlan Current File`
- `BEAST: Preview Hunks`
- `BEAST: Apply Selected Hunks`
- `BEAST: Select Provider Role`
- `BEAST: Refresh Chronicle`
- `BEAST: Refresh Route Fitness`
- `BEAST: Open Mission Control`
- `BEAST: Configure Integrated Terminal Gateway`
- `BEAST: Install Workspace MCP Config`

## Activity Bar Views

- **BEAST Status**: gateway, provider, provider role, MCP lane, workspace.
- **Chronicle**: recent BEAST Chronicle records.
- **Route Fitness**: provider score and recommended runtime role.

## SourcePlan Flow

1. Open a source file.
2. Run `BEAST: SourcePlan Current File`.
3. Enter the objective.
4. Run `BEAST: Preview Hunks`.
5. Review the diff.
6. Run `BEAST: Apply Selected Hunks`.

Apply calls BEAST MCP tool `beast_sourceplan_apply_selected` with explicit approval. BEAST verifies, writes rollback state, and crystallizes a Chronicle record.

## MCP Lane

The extension registers `beast mcp --workspace <workspace>` as a stdio MCP server.

Key MCP tools:

- `beast_sourceplan_prepare`
- `beast_sourceplan_preview_hunks`
- `beast_sourceplan_apply_selected`
- `beast_sourceplan_rollback_latest`
- `beast_provider_fitness`
- `beast_prepare_handoff`
- `beast_validate_canon`
- `beast_mcp_tool_catalog`

## Terminal Gateway Variables

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8000/proxy/anthropic"
export OPENAI_BASE_URL="http://127.0.0.1:8000/proxy/openai/v1"
export ENABLE_TOOL_SEARCH=true
```
