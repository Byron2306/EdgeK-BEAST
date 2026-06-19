#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code CLI was not found on PATH." >&2
  echo "Install Claude Code first, then rerun this script." >&2
  exit 1
fi

claude mcp add-json edgek-beast "$(cat "$ROOT/integrations/mcp-clients/claude-code/edgek-beast.mcp.json")" --scope project
echo "Installed project-scoped EdgeK BEAST MCP server for Claude Code."
