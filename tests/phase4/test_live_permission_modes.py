from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.durable_approval_runtime import DurableAgentApprovalRuntime


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


def test_approved_sensitive_read_is_redacted_before_event_persistence(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = _run(engine, "GUIDED")
    spec = engine.tool_registry.get("workspace.read_range")
    arguments = {"path": ".env", "start_line": 1, "line_count": 20}
    approval_id = "approval-sensitive-once"
    step_id = "step-sensitive-read"

    runtime = DurableAgentApprovalRuntime(root)
    artifacts = runtime.create_for_tool(
        run=engine.store.get_run(run_id) or {},
        step_id=step_id,
        approval_id=approval_id,
        spec=spec,
        arguments=arguments,
        execution_target="local",
        worktree_bound=False,
    )
    assert artifacts["classification"]["requirement"] == "REQUIRE_SENSITIVE_APPROVAL"
    assert artifacts["sensitive_classification"]["sensitive"] is True
    assert artifacts["sensitive_classification"]["model_context_allowed"] is False

    engine.store.create_approval(run_id, {
        "request_id": approval_id,
        "run_id": run_id,
        "step_id": step_id,
        "tool_id": spec.tool_id,
        "tool_version": spec.version,
        "phase4_durable": True,
    })
    engine.merge_checkpoint(run_id, {
        "suspended_step": {
            "step_id": step_id,
            "approval_id": approval_id,
            "tool_id": spec.tool_id,
            "tool_version": spec.version,
            "arguments": arguments,
            "execution_target": "local",
            "execution_target_payload": {},
            "phase4_durable": True,
            "request_digest": artifacts["request"]["request_digest"],
        },
        "suspended_step_id": step_id,
        "suspended_approval_id": approval_id,
    })
    engine.store.transition(run_id, "waiting_for_approval")

    resolved = runtime.resolve(
        approval_id=approval_id,
        resolution={
            "approved": True,
            "decision": "APPROVE",
            "scope": "ONCE",
            "operator_id": "operator:sensitive-test",
        },
        run=engine.store.get_run(run_id) or {},
    )
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "ONCE"})
    runtime.consume_and_resume(
        capability=resolved["capability"],
        request=resolved["request"],
    )

    observation = asyncio.run(engine.execute_tool(
        run_id,
        "workspace.read_range",
        arguments,
        approval_id=approval_id,
    ))
    assert observation["status"] == "completed"
    assert observation["result"]["beast_object_type"] == "beast_sensitive_tool_observation"
    assert observation["result"]["sensitive"] is True
    assert observation["result"]["redaction_receipt"]["raw_secret_persisted"] is False

    import json
    serialized_observation = json.dumps(observation, sort_keys=True)
    assert "TOKEN=secret" not in serialized_observation
    serialized_events = json.dumps(engine.store.events(run_id, limit=500), sort_keys=True)
    assert "TOKEN=secret" not in serialized_events
    assert "agent.sensitive_data.result_redacted" in serialized_events


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
