# EdgeK BEAST VS Code Extension

This extension wires VS Code into the three-lane BEAST integration model:

1. **MCP lane** – the extension registers `beast mcp` as a stdio MCP server.
2. **Proxy lane** – terminal/API traffic is routed through `http://127.0.0.1:8000/proxy/*`.
3. **IDE lane** – the extension exposes BEAST commands, status, and dashboard access.

## Commands

- `BEAST: Start Local Governor`
- `BEAST: Prepare Handoff Packet`
- `BEAST: Open Mission Control`
- `BEAST: Configure Integrated Terminal Gateway`

## Terminal gateway variables

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8000/proxy/anthropic"
export OPENAI_BASE_URL="http://127.0.0.1:8000/proxy/openai"
export ENABLE_TOOL_SEARCH=true
```
