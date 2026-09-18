from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.run_engine import AgentRunEngine


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "phase4-modes"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "beast@example.test")
    _git(root, "config", "user.name", "BEAST Phase4 Modes")
    (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    _git(root, "add", "sample.py")
    _git(root, "commit", "-qm", "seed")
    return root


def _run(engine: AgentRunEngine, mode: str, *, extra_request: dict | None = None) -> str:
    request = {
        "durable_approvals": True,
        "permission_mode": mode,
        **(extra_request or {}),
    }
    return engine.create_run(
        session_id=f"phase4-mode-{mode.lower()}",
        objective=f"exercise {mode}",
        mode="agent",
        provider="simulated",
        model="phase4-mode-test",
        request=request,
        budget={"profile": "balanced"},
    )["run_id"]


def test_guided_ordinary_read_remains_automatic(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(engine, "GUIDED")

    observation = asyncio.run(engine.execute_tool(run_id, "workspace.list", {}))
    assert observation["status"] == "completed"
    events = engine.store.events(run_id, limit=100)
    mode = [
        event["payload"] for event in events
        if event["event_type"] == "agent.permission_mode.evaluated"
    ][-1]
    assert mode["permission_mode"] == "GUIDED"
    assert mode["auto_authorized"] is True
    assert mode["requires_approval"] is False


def test_review_requires_durable_approval_even_for_ordinary_read(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(engine, "REVIEW")

    with pytest.raises(PermissionError, match="approved Phase 4 capability"):
        asyncio.run(engine.execute_tool(run_id, "workspace.list", {}))


def test_guided_sensitive_read_cannot_bypass_explicit_approval(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(engine, "GUIDED")

    with pytest.raises(PermissionError, match="approved Phase 4 capability"):
        asyncio.run(engine.execute_tool(
            run_id,
            "workspace.read_range",
            {"path": ".env", "start_line": 1, "line_count": 20},
        ))
    event = next(
        event for event in reversed(engine.store.events(run_id, limit=100))
        if event["event_type"] == "agent.permission_mode.evaluated"
    )
    assert event["payload"]["requires_approval"] is True
    assert event["payload"]["auto_authorized"] is False


def test_locked_mode_refuses_even_read_only_tool(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(engine, "LOCKED")

    with pytest.raises(PermissionError, match="LOCKED mode disables the agent"):
        asyncio.run(engine.execute_tool(run_id, "workspace.list", {}))


def test_bounded_autonomy_stays_inside_file_and_command_allowlists(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    command = "python -m py_compile allowed.py"
    run_id = _run(engine, "BOUNDED_AUTONOMY", extra_request={
        "allowed_files": ["allowed.py"],
        "allowed_commands": [command],
        "context_files": ["allowed.py"],
    })

    bind = asyncio.run(engine.execute_tool(
        run_id,
        "worktree.bind",
        {"objective": "bounded autonomy proof", "risk": "high"},
    ))
    assert bind["status"] == "completed"
    bound = engine.store.get_run(run_id) or {}
    assert bound["checkpoint"]["worktree_root"]

    write = asyncio.run(engine.execute_tool(
        run_id,
        "worktree.write_file",
        {"path": "allowed.py", "content": "VALUE = 2\n"},
    ))
    assert write["status"] == "completed"

    with pytest.raises(PermissionError, match="outside the explicit file allowlist"):
        asyncio.run(engine.execute_tool(
            run_id,
            "worktree.write_file",
            {"path": "forbidden.py", "content": "NOPE = True\n"},
        ))

    verify = asyncio.run(engine.execute_tool(
        run_id,
        "worktree.verify",
        {"command": ["python", "-m", "py_compile", "allowed.py"]},
    ))
    assert verify["status"] == "completed"

    with pytest.raises(PermissionError, match="outside the explicit command allowlist"):
        asyncio.run(engine.execute_tool(
            run_id,
            "worktree.verify",
            {"command": ["python", "-m", "pytest", "-q"]},
        ))
