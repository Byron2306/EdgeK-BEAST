from __future__ import annotations

import asyncio
import subprocess

from app.kernel.agents.run_engine import AgentRunEngine


def _runtime_events(engine: AgentRunEngine, run_id: str, event_type: str):
    return [
        event
        for event in engine.store.events(run_id, after=0, limit=200)
        if event["event_type"] == event_type
    ]


def test_default_engine_executes_workspace_tool_through_effect_ts(tmp_path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="effect-default",
        objective="inspect sample",
        mode="analysis",
    )["run_id"]

    observation = asyncio.run(engine.execute_tool(
        run_id,
        "workspace.read_range",
        {"path": "sample.py", "start_line": 1, "line_count": 5},
    ))

    assert observation["status"] == "completed"
    assert observation["result"]["content"] == "VALUE = 1"
    completed = _runtime_events(engine, run_id, "agent.tool.completed")
    assert completed[-1]["payload"]["runtime"] == "effect_ts"


def test_effect_callback_preserves_engine_context_for_worktree_binding(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="effect-worktree",
        objective="change VALUE",
        mode="agent",
    )["run_id"]
    approval_id = "effect-worktree-approval"
    engine.store.create_approval(
        run_id,
        {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]},
    )
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})

    observation = asyncio.run(engine.execute_tool(
        run_id,
        "worktree.bind",
        {"objective": "change VALUE"},
        approval_id=approval_id,
    ))

    assert observation["status"] == "completed"
    run = engine.store.get_run(run_id)
    assert run["checkpoint"]["worktree_root"] == observation["result"]["worktree_root"]
    completed = _runtime_events(engine, run_id, "agent.tool.completed")
    assert completed[-1]["payload"]["runtime"] == "effect_ts"

