# BEAST MCP Client Pack

This pack routes Cursor, Claude Code, and VS Code agent tool calls through the BEAST MCP server.

The important behavior is not just "add another MCP server." The BEAST MCP lane gives clients:

- schema-pinned tool contracts
- output-governed SourcePlan tools
- hunk preview before source writes
- explicit approval before apply
- rollback snapshots
- Chronicle records after verified apply
- provider fitness and role recommendations

## Exposed BEAST Tools

Core coding tools:

- `beast_session_handshake`
- `beast_sourceplan_prepare`
- `beast_sourceplan_preview_hunks`
- `beast_sourceplan_apply_selected`
- `beast_sourceplan_rollback_latest`
- `beast_provider_fitness`
- `beast_provider_economist_select`

Governance and memory tools:

- `beast_prepare_task`
- `beast_run_quality_cascade`
- `beast_prepare_handoff`
- `beast_build_context_packet`
- `beast_validate_canon`
- `beast_publish_chronicle`
- `beast_mcp_tool_catalog`
- `beast_tool_laziness_record`
- `beast_tool_laziness_recommend`
- `beast_otel_export`
- `beast_plugin_manifest_validate`
- `beast_plugin_marketplace_install`
- `beast_capability_exchange`
- `beast_meta_tool_commons`
- `beast_compute_shadow`

## Cursor

Copy the Cursor template into the workspace MCP config location:

```bash
mkdir -p .cursor
cp integrations/mcp-clients/cursor/mcp.json .cursor/mcp.json
```

Then restart Cursor or reload MCP servers.

The template uses:

```json
{
  "mcpServers": {
    "edgek-beast": {
      "command": "./bin/beast",
      "args": ["mcp", "--workspace", "."],
      "env": {"BEAST_WORKSPACE": "."}
    }
  }
}
```

## Claude Code

Install the project-scoped MCP server:

```bash
bash integrations/mcp-clients/claude-code/install.sh
```

Equivalent manual command:

```bash
claude mcp add-json edgek-beast "$(cat integrations/mcp-clients/claude-code/edgek-beast.mcp.json)" --scope project
```

## VS Code

The VS Code extension also registers BEAST as an MCP server definition provider. For a workspace-level config, run:

```bash
./bin/beast mcp-install --workspace "$PWD"
```

## Recommended Agent Instruction

Use this instruction in Cursor, Claude Code, or VS Code agent mode:

```text
For source edits, use BEAST MCP tools. Call beast_sourceplan_prepare first,
then beast_sourceplan_preview_hunks. Do not call beast_sourceplan_apply_selected
unless the user explicitly approves the selected hunks. Prefer provider fitness
and role recommendations from beast_provider_fitness before choosing a provider.
```
