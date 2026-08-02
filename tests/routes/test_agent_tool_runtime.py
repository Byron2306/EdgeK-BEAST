from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import app.kernel.agents.tool_runtime as tool_runtime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.tool_models import ToolEffect


def _engine(tmp_path: Path) -> tuple[AgentRunEngine, str]:
    (tmp_path / "alpha.py").write_text("def alpha():\n    return 42\n", encoding="utf-8")
    (tmp_path / "math.nim").write_text("import std/strutils\n\ntype BeastNumber* = object\n\nproc beastAdd*(left: int, right: int): int = left + right\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(session_id="session-test", objective="inspect alpha")
    return engine, str(run["run_id"])


def test_default_tool_registry_is_typed_and_read_only(tmp_path: Path):
    engine, _ = _engine(tmp_path)
    tools = engine.list_tools()
    ids = {item["tool_id"] for item in tools}
    assert {"workspace.index", "workspace.list", "workspace.read_range", "workspace.search_text", "git.status"} <= ids
    read_ids = {"workspace.index", "workspace.list", "workspace.read_range", "workspace.search_text", "git.status"}
    assert all(item["effect"] == ToolEffect.READ.value for item in tools if item["tool_id"] in read_ids)
    assert all("input_schema" in item and "risk" in item for item in tools)


def test_read_range_emits_structured_observation(tmp_path: Path):
    engine, run_id = _engine(tmp_path)
    observation = asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {
        "path": "alpha.py",
        "start_line": 1,
        "line_count": 2,
    }))
    assert observation["status"] == "completed"
    assert observation["tool_id"] == "workspace.read_range"
    assert "def alpha" in observation["result"]["content"]
    assert len(observation["evidence_digest"]) == 64
    events = engine.store.events(run_id, after=0, limit=100)
    types = [item["event_type"] for item in events]
    assert "agent.tool.started" in types
    assert "agent.tool.completed" in types


def test_workspace_index_extracts_symbols_and_nim_context(tmp_path: Path):
    engine, run_id = _engine(tmp_path)
    observation = asyncio.run(engine.execute_tool(run_id, "workspace.index", {"limit": 100, "include_symbols": True}))
    result = observation["result"]
    assert observation["status"] == "completed"
    assert result["beast_object_type"] == "beast_workspace_index_snapshot"
    assert result["summary"]["languages"]["python"] >= 1
    assert result["summary"]["languages"]["nim"] >= 1
    symbols = {(item["path"], item["name"], item["kind"]) for item in result["symbols"]}
    assert ("alpha.py", "alpha", "function") in symbols
    assert ("math.nim", "beastAdd", "function") in symbols
    assert result["index_digest"].startswith("sha256:")


def test_remote_workspace_index_preserves_deep_symbol_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine, run_id = _engine(tmp_path)

    async def fake_run_target_shell(context, script, *, timeout=20.0, output_limit=512000):
        assert "python3 -c" in script
        return {
            "ok": True,
            "returncode": 0,
            "stdout": '{"beast_object_type":"beast_workspace_index_snapshot","version":"1.0","ok":true,"source":"agent_target_deep_index","files":[{"path":"math.nim","language":"nim","size":99,"mtime_ms":1}],"symbols":[{"path":"math.nim","name":"beastAdd","kind":"function","line":3}],"imports":[{"path":"math.nim","target":"std/strutils","kind":"import"}],"tests":[],"summary":{"file_count":1,"symbol_count":1,"import_count":1,"languages":{"nim":1},"symbol_kinds":{"function":1}},"index_digest":"sha256:abc","truncated":false}\n',
            "stderr": "",
            "truncated": False,
        }

    monkeypatch.setattr(tool_runtime, "_run_target_shell", fake_run_target_shell)
    observation = asyncio.run(engine.execute_tool(
        run_id,
        "workspace.index",
        {"limit": 100, "include_symbols": True},
        execution_target="container",
        execution_target_payload={"kind": "container", "containerId": "ctr-test", "workspaceFolder": "/workspace"},
    ))
    result = observation["result"]
    assert result["source"] == "agent_target_deep_index"
    assert result["summary"]["languages"]["nim"] == 1
    assert result["symbols"][0]["name"] == "beastAdd"
    assert result["target_execution"] == "remote_container"


def test_tool_path_escape_is_rejected_and_recorded(tmp_path: Path):
    engine, run_id = _engine(tmp_path)
    with pytest.raises(RuntimeError, match="escapes workspace"):
        asyncio.run(engine.execute_tool(run_id, "workspace.read_range", {"path": "../secret.txt"}))
    events = engine.store.events(run_id, after=0, limit=100)
    assert any(item["event_type"] == "agent.tool.failed" for item in events)


def test_unknown_arguments_are_rejected_before_execution(tmp_path: Path):
    engine, run_id = _engine(tmp_path)
    with pytest.raises(ValueError, match="unknown tool arguments"):
        asyncio.run(engine.execute_tool(run_id, "workspace.list", {"banana": True}))


def test_search_is_bounded_and_excludes_beast_state(tmp_path: Path):
    engine, run_id = _engine(tmp_path)
    state = tmp_path / ".beast" / "private.txt"
    state.parent.mkdir(exist_ok=True)
    state.write_text("needle", encoding="utf-8")
    (tmp_path / "visible.txt").write_text("needle here", encoding="utf-8")
    observation = asyncio.run(engine.execute_tool(run_id, "workspace.search_text", {"query": "needle"}))
    paths = {item["path"] for item in observation["result"]["matches"]}
    assert "visible.txt" in paths
    assert ".beast/private.txt" not in paths
