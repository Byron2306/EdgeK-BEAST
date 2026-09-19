from __future__ import annotations

import asyncio
from pathlib import Path

import app.kernel.agents.worktree_tools as worktree_tools
from app.kernel.agents.tool_models import ToolExecutionContext
from app.kernel.agents.verification_planner import execution_target_descriptor, plan_verification


class _Store:
    def __init__(self, run):
        self.run = run

    def get_run(self, run_id):
        return self.run if run_id == self.run["run_id"] else None


class _Engine:
    def __init__(self, run):
        self.store = _Store(run)
        self.events = []

    def merge_checkpoint(self, run_id, payload):
        checkpoint = dict(self.store.run.get("checkpoint") or {})
        checkpoint.update(payload or {})
        self.store.run["checkpoint"] = checkpoint

    def emit(self, run_id, event_type, payload):
        self.events.append({"run_id": run_id, "event_type": event_type, "payload": payload})


def _remote_run(*, failures=None):
    return {
        "request": {
            "execution_target": "ssh",
            "execution_target_payload": {
                "kind": "ssh",
                "host": "beast-host",
                "remoteRoot": "/workspace/project",
            },
        },
        "checkpoint": {
            "planner": {
                "observations": [
                    {
                        "tool_id": "worktree.replace_exact",
                        "status": "completed",
                        "result": {"path": "pkg/demo.py"},
                    }
                ],
                "verification_failures": list(failures or []),
            }
        },
    }


def test_phase10_execution_target_descriptor_preserves_remote_identity():
    target = execution_target_descriptor(_remote_run())
    assert target["kind"] == "ssh"
    assert target["host"] == "beast-host"
    assert target["base"] == "/workspace/project"
    assert target["target_execution"] == "remote_ssh"


def test_phase10_remote_verifier_retry_then_degrades_target_natively():
    retry_failure = {
        "repair_cycle": 1,
        "command": ["python3", "-m", "pytest", "-q", "tests/test_demo.py"],
        "target_execution": "remote_ssh",
        "analysis": {
            "failure_class": "environment_issue",
            "retryable_without_code_change": True,
        },
    }
    retry = plan_verification(_remote_run(failures=[retry_failure]))
    assert retry["reason"] == "retry_same_target_verifier_once"
    assert retry["command"][:3] == ["python3", "-m", "pytest"]
    assert retry["strategy"]["mode"] == "target_native_remote"
    assert retry["strategy"]["family"] == "retry_same_command"

    second_failure = dict(retry_failure, repair_cycle=2)
    degraded = plan_verification(_remote_run(failures=[second_failure]))
    assert degraded["reason"] == "degraded_target_fallback_after_retryable_verifier_failure"
    assert degraded["command"][:3] == ["python3", "-m", "py_compile"]
    assert degraded["strategy"]["mode"] == "target_native_remote"
    assert degraded["strategy"]["family"] == "python_compile"


def test_phase10_remote_verification_receipt_keeps_transport_and_target(monkeypatch, tmp_path: Path):
    run = {"run_id": "phase10-remote", "checkpoint": {"worktree_mutation_epoch": 4}}
    engine = _Engine(run)
    context = ToolExecutionContext(
        run_id=run["run_id"],
        workspace_root=str(tmp_path),
        execution_target="ssh",
        execution_target_payload={
            "kind": "ssh",
            "host": "beast-host",
            "remoteRoot": "/workspace/project",
        },
        worktree_root="/workspace/project/.beast/agent-worktrees/phase10-remote",
        engine=engine,
    )

    async def fake_target_shell(_context, _script, *, timeout=20.0, output_limit=512000):
        return {
            "ok": False,
            "returncode": 2,
            "stdout": "pytest collected 1 item\n",
            "stderr": "AssertionError: expected 2 actual 1\n",
            "truncated": False,
        }

    monkeypatch.setattr(worktree_tools, "_run_target_shell", fake_target_shell)
    result = asyncio.run(
        worktree_tools._worktree_run_verification(
            {"command": ["python3", "-m", "pytest", "-q", "tests/test_demo.py"]},
            context,
        )
    )

    verification = run["checkpoint"]["verification"]
    failure = next(event for event in engine.events if event["event_type"] == "agent.verification.failed")
    assert result["ok"] is False
    assert result["target_execution"] == "remote_ssh"
    assert result["transport"] == "ssh"
    assert verification["target_execution"] == "remote_ssh"
    assert verification["execution_target"] == "ssh"
    assert verification["transport"] == "ssh"
    assert failure["payload"]["target_execution"] == "remote_ssh"
    assert failure["payload"]["execution_target"] == "ssh"
    assert failure["payload"]["transport"] == "ssh"


def test_phase10_remote_strategy_never_upgrades_to_source_or_promotion_authority():
    plan = plan_verification(_remote_run())
    strategy = plan["strategy"]
    assert strategy["mode"] == "target_native_remote"
    assert strategy["execution_target"]["target_execution"] == "remote_ssh"
    assert "authority" not in strategy
    assert "promotion" not in strategy
