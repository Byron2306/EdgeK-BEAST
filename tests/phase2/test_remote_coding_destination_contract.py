"""Remote coding must never fall back locally or reuse another target's authority."""
import asyncio
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents import worktree_tools
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.tool_runtime import h12_approval_authorizes

SSH_A = {"kind": "ssh", "host": "beast-ide-loopback", "remoteRoot": "/tmp/beast-remote-proof"}
SSH_B = {"kind": "ssh", "host": "other-host", "remoteRoot": "/tmp/beast-remote-proof"}


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Remote Contract Test"], cwd=root, check=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "calc.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


def _approval(engine, run_id, destination=SSH_A):
    engine.store.create_approval(run_id, {
        "request_id": "bound-approval",
        "execution_target": destination["kind"],
        "execution_target_payload": destination,
        "capabilities": [{"id": "worktree_mutation"}],
    })
    engine.store.resolve_approval(run_id, "bound-approval", {"approved": True})
    return "bound-approval"


def test_remote_approval_cannot_follow_different_host():
    approval = {
        "status": "approved",
        "request": {
            "execution_target": "ssh",
            "execution_target_payload": SSH_A,
            "capabilities": [{"id": "worktree_mutation"}],
        },
    }
    assert h12_approval_authorizes(approval, "worktree.bind", {}, "ssh", SSH_A)
    assert not h12_approval_authorizes(approval, "worktree.bind", {}, "ssh", SSH_B)
    assert not h12_approval_authorizes(approval, "worktree.bind", {}, "container", SSH_A)
    legacy = {"status": "approved", "request": {"capabilities": [{"id": "worktree_mutation"}]}}
    assert not h12_approval_authorizes(legacy, "worktree.bind", {}, "ssh", SSH_A)


def test_default_local_run_rejects_remote_tool_before_dispatch(tmp_path):
    async def scenario():
        engine = AgentRunEngine(_repo(tmp_path))
        run_id = engine.create_run(session_id="session", objective="local only")["run_id"]
        approval_id = _approval(engine, run_id)
        with pytest.raises(PermissionError, match="immutable AgentRun destination"):
            await engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id,
                                      execution_target="ssh", execution_target_payload=SSH_A)
    asyncio.run(scenario())


def test_same_kind_different_host_refused_before_dispatch(tmp_path):
    async def scenario():
        engine = AgentRunEngine(_repo(tmp_path))
        run_id = engine.create_run(session_id="session", objective="remote",
                                   request={"execution_target": "ssh", "execution_target_payload": SSH_A})["run_id"]
        approval_id = _approval(engine, run_id)
        with pytest.raises(PermissionError, match="destination identity"):
            await engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id,
                                      execution_target="ssh", execution_target_payload=SSH_B)
    asyncio.run(scenario())


def test_remote_worktree_bind_is_non_destructive_and_target_bound(tmp_path, monkeypatch):
    async def scenario():
        engine = AgentRunEngine(_repo(tmp_path))
        run_id = engine.create_run(session_id="session", objective="remote",
                                   request={"execution_target": "ssh", "execution_target_payload": SSH_A},
                                   run_id="remote-contract-test")["run_id"]
        approval_id = _approval(engine, run_id)
        calls = []

        async def fake_shell(context, script, *, timeout=20.0, output_limit=512000):
            calls.append((context.execution_target, context.execution_target_payload, script))
            return {"ok": True, "returncode": 0, "stdout": (
                "BEAST_WORKTREE\n/tmp/beast-remote-proof/.beast/agent-worktrees/remote-contract-test\n"
                "abc123\nbeast-agent-remote-contract-test\n"), "stderr": "", "truncated": False}

        monkeypatch.setattr(worktree_tools, "_run_target_shell", fake_shell)
        result = await engine.execute_tool(run_id, "worktree.bind", {}, approval_id=approval_id,
                                           execution_target="ssh", execution_target_payload=SSH_A)
        assert result["status"] == "completed"
        assert len(calls) == 1
        assert calls[0][0] == "ssh" and calls[0][1] == SSH_A
        assert "git worktree add -b " in calls[0][2]
        assert "git worktree remove --force" not in calls[0][2]
        assert "git branch -D " not in calls[0][2]
        checkpoint = engine.store.get_run(run_id)["checkpoint"]
        assert checkpoint["worktree_execution_target_payload"] == SSH_A
        with pytest.raises(PermissionError, match="destination identity"):
            await engine.execute_tool(run_id, "worktree.diff", {},
                                      execution_target="ssh", execution_target_payload=SSH_B)
    asyncio.run(scenario())


def test_remote_mutation_rejects_git_metadata_and_absolute_paths():
    from app.kernel.agents.worktree_tools import _remote_mutation_path
    for path in (".git/config", "nested/.beast/secret", "/tmp/file", "../escape.py", ""):
        with pytest.raises((ValueError, PermissionError)):
            _remote_mutation_path(path)
    assert _remote_mutation_path("src/calc.py") == "src/calc.py"
