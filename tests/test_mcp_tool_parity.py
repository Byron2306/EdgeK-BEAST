import json
from pathlib import Path

from app.mcp import stdio_server
from app.mcp.runtime import BeastToolRuntime


def test_snapshot_matches_runtime_and_is_listed(monkeypatch):
    for k in ("BEAST_MCP_TOOLS", "BEAST_MCP_TOOLS_ALLOW", "BEAST_MCP_TOOLS_DENY"):
        monkeypatch.delenv(k, raising=False)
    runtime = BeastToolRuntime()
    snap = json.loads((Path(stdio_server.__file__).with_name("tool_definitions.json")).read_text())
    assert sorted(t["name"] for t in snap) == sorted(t["name"] for t in runtime._raw_tool_definitions()), \
        "regenerate app/mcp/tool_definitions.json from BeastToolRuntime()._raw_tool_definitions()"
    listed = stdio_server._listed_tools()
    assert len(listed) == len(runtime.tool_definitions()) >= 69
    assert {t["name"] for t in stdio_server.TOOL_DEFINITIONS} <= {t["name"] for t in listed}


def test_readonly_profile_is_filtered_by_runtime(monkeypatch):
    monkeypatch.setenv("BEAST_MCP_TOOLS", "readonly")
    names = {t["name"] for t in stdio_server._listed_tools()}
    assert "beast_sourceplan_apply_selected" not in names and "beast_prepare_task" in names
