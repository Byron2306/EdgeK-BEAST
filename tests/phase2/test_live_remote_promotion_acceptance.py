from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.promotion_engine import PromotionEngine
from app.kernel.agents.run_engine import AgentRunEngine


def _run(args: list[str], *, cwd: Path | None = None, timeout: float = 30.0) -> str:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout, check=True)
    return result.stdout.strip()


def _repo(root: Path) -> None:
    _run(["git", "init"], cwd=root)
    _run(["git", "checkout", "-b", "main"], cwd=root)
    _run(["git", "config", "user.email", "beast@example.test"], cwd=root)
    _run(["git", "config", "user.name", "BEAST Test"], cwd=root)
    (root / ".gitignore").write_text(".beast/\n", encoding="utf-8")
    (root / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=root)
    _run(["git", "commit", "-m", "base"], cwd=root)


def _approval(engine: AgentRunEngine, run_id: str, approval_id: str = "mutation") -> str:
    engine.store.create_approval(run_id, {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]})
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "resolved_by": "live-test"})
    return approval_id


def _agent_ci_image(tmp_path: Path) -> str:
    image = os.environ.get("BEAST_LIVE_AGENT_CI_IMAGE", "beast-disposable-agent-ci:live")
    dockerfile = Path(__file__).resolve().parents[1] / "fixtures" / "disposable-sshd"
    _run(["docker", "build", "-t", image, str(dockerfile)], timeout=180.0)
    return image


async def _run_planner_driven_remote_ci_loop(
    *,
    root: Path,
    session_id: str,
    run_id: str,
    execution_target: str,
    target_payload: dict,
    final_branch: str = "main",
) -> dict:
    engine = AgentRunEngine(root)
    created = engine.create_run(
        session_id=session_id,
        objective="Planner-driven remote CI repair VALUE with one verifier failure, repair, SourcePlan, and final apply",
        mode="agent",
        provider="scripted",
        model="remote-ci-loop",
        run_id=run_id,
        request={
            "execution_target": execution_target,
            "execution_target_payload": target_payload,
            "approval_timeout_seconds": 1,
        },
    )
    approval_id = _approval(engine, created["run_id"])
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.index", "execution_target": execution_target, "arguments": {"limit": 1200, "include_symbols": True}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "execution_target": execution_target, "approval_id": approval_id, "arguments": {"objective": "remote CI VALUE repair"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "execution_target": execution_target, "approval_id": approval_id, "arguments": {"path": "value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2\nbroken = "}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "execution_target": execution_target, "approval_id": approval_id, "arguments": {"command": ["python3", "-m", "py_compile", "value.py"]}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "execution_target": execution_target, "approval_id": approval_id, "arguments": {"path": "value.py", "old_text": "VALUE = 2\nbroken = ", "new_text": "VALUE = 2"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "execution_target": execution_target, "approval_id": approval_id, "arguments": {"command": ["python3", "-m", "py_compile", "value.py"]}},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "execution_target": execution_target, "arguments": {}},
        {"decision_type": "complete", "summary": "Remote CI repair passed verification and SourcePlan handoff is ready."},
    ])
    final = await AgentPlannerRuntime(engine, provider, max_turns=8, max_repair_cycles=2).run(created["run_id"])
    planner = final["checkpoint"]["planner"]
    observations = planner["observations"]
    tool_trace = [item["tool_id"] for item in observations]
    assert final["state"] == "completed"
    assert tool_trace == [
        "workspace.index",
        "worktree.bind",
        "worktree.replace_exact",
        "worktree.verify",
        "worktree.replace_exact",
        "worktree.verify",
        "worktree.sourceplan_draft",
    ]
    assert observations[0]["result"]["target_execution"] == f"remote_{execution_target}"
    assert observations[3]["status"] == "failed"
    assert observations[3]["result"]["analysis"]["failure_class"] == "bad_patch"
    assert observations[5]["status"] == "completed"
    assert observations[5]["result"]["target_execution"] == f"remote_{execution_target}"
    assert observations[6]["status"] == "completed"
    assert planner["repair_cycles"] == 1
    assert planner["verification_failures"][-1]["target_paths"] == ["value.py"]
    events = engine.store.events(created["run_id"], limit=500)
    event_types = [event["event_type"] for event in events]
    assert "agent.repair.required" in event_types
    assert "agent.sourceplan.ready" in event_types

    promotion = PromotionEngine(root)
    evaluated = promotion.evaluate(created["run_id"], requested_by="live-planner-ci")
    assert evaluated["eligible"] is True, [policy for policy in evaluated["receipt"]["policies"] if not policy["passed"]]
    promotion_approval = evaluated["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(created["run_id"], promotion_approval, {"approved": True, "resolved_by": "Live CI Operator"})
    promoted = promotion.promote(created["run_id"], approval_id=promotion_approval, commit_message="Promote planner-driven remote CI repair")
    assert promoted["candidate"]["status"] == "remote_commit_candidate"
    assert promoted["candidate"]["target_execution"] == f"remote_{execution_target}"

    final_eval = promotion.evaluate_final_apply(created["run_id"], requested_by="live-planner-ci")
    assert final_eval["eligible"] is True, [policy for policy in final_eval["receipt"]["policies"] if not policy["passed"]]
    final_approval = final_eval["approval"]["approval_id"]
    promotion.engine.store.resolve_approval(created["run_id"], final_approval, {"approved": True, "resolved_by": "Live CI Operator"})
    finalized = promotion.finalize(created["run_id"], approval_id=final_approval, target_branch=final_branch)
    assert finalized["final_apply"]["status"] == "finalized"
    assert finalized["final_apply"]["applied_to_remote_target"] is True
    assert finalized["final_apply"]["target_execution"] == f"remote_{execution_target}"
    return finalized


@pytest.mark.skipif(os.environ.get("BEAST_LIVE_DOCKER_ACCEPTANCE") != "1", reason="set BEAST_LIVE_DOCKER_ACCEPTANCE=1 to run disposable Docker target acceptance")
def test_live_docker_target_full_remote_promotion_and_final_apply(tmp_path: Path):
    image = os.environ.get("BEAST_LIVE_DOCKER_IMAGE", "hackingtool:latest")
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    container = _run([
        "docker", "run", "-d",
        "--entrypoint", "sleep",
        "-v", f"{root}:/repo",
        image,
        "900",
    ])
    try:
        _run(["docker", "exec", container, "git", "config", "--global", "--add", "safe.directory", "*"])

        async def scenario() -> None:
            engine = AgentRunEngine(root)
            run_id = engine.create_run(session_id="live-container", objective="remote VALUE repair", run_id="live-container-promotion")["run_id"]
            approval = _approval(engine, run_id)
            target_payload = {"kind": "container", "containerId": container, "workspaceFolder": "/repo"}
            await engine.execute_tool(
                run_id,
                "worktree.bind",
                {"objective": "remote VALUE repair"},
                approval_id=approval,
                execution_target="container",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.replace_exact",
                {"path": "value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
                approval_id=approval,
                execution_target="container",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.verify",
                {"command": ["python3", "-m", "py_compile", "value.py"]},
                approval_id=approval,
                execution_target="container",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.diff",
                {},
                execution_target="container",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.sourceplan_draft",
                {},
                execution_target="container",
                execution_target_payload=target_payload,
            )

            promotion = PromotionEngine(root)
            evaluated = promotion.evaluate(run_id, requested_by="live-test")
            assert evaluated["eligible"] is True, [policy for policy in evaluated["receipt"]["policies"] if not policy["passed"]]
            promotion_approval = evaluated["approval"]["approval_id"]
            promotion.engine.store.resolve_approval(run_id, promotion_approval, {"approved": True, "resolved_by": "Live Operator"})
            promoted = promotion.promote(run_id, approval_id=promotion_approval, commit_message="Promote live remote VALUE repair")
            assert promoted["candidate"]["status"] == "remote_commit_candidate"

            final_eval = promotion.evaluate_final_apply(run_id, requested_by="live-test")
            assert final_eval["eligible"] is True
            final_approval = final_eval["approval"]["approval_id"]
            promotion.engine.store.resolve_approval(run_id, final_approval, {"approved": True, "resolved_by": "Live Operator"})
            finalized = promotion.finalize(run_id, approval_id=final_approval, target_branch="main")
            assert finalized["final_apply"]["status"] == "finalized"
            assert finalized["final_apply"]["applied_to_remote_target"] is True

        asyncio.run(scenario())
        assert (root / "value.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        assert _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root) == "main"
    finally:
        subprocess.run(["docker", "exec", container, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/repo"], capture_output=True, text=True, timeout=20, check=False)
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=20, check=False)


@pytest.mark.skipif(os.environ.get("BEAST_LIVE_DOCKER_ACCEPTANCE") != "1", reason="set BEAST_LIVE_DOCKER_ACCEPTANCE=1 to run disposable Docker target acceptance")
def test_live_docker_target_planner_driven_multiturn_ci_repair_and_final_apply(tmp_path: Path):
    image = _agent_ci_image(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    container = _run([
        "docker", "run", "-d",
        "--entrypoint", "sleep",
        "-v", f"{root}:/repo",
        image,
        "900",
    ])
    try:
        _run(["docker", "exec", container, "git", "config", "--global", "--add", "safe.directory", "*"])
        finalized = asyncio.run(_run_planner_driven_remote_ci_loop(
            root=root,
            session_id="live-container-planner-ci",
            run_id="live-container-planner-ci",
            execution_target="container",
            target_payload={"kind": "container", "containerId": container, "workspaceFolder": "/repo", "label": "disposable-devcontainer-ci"},
        ))
        assert finalized["final_apply"]["target_branch"] == "main"
        assert (root / "value.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        assert _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root) == "main"
    finally:
        subprocess.run(["docker", "exec", container, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/repo"], capture_output=True, text=True, timeout=20, check=False)
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=20, check=False)


@pytest.mark.skipif(os.environ.get("BEAST_LIVE_SSH_DOCKER_ACCEPTANCE") != "1", reason="set BEAST_LIVE_SSH_DOCKER_ACCEPTANCE=1 to build and run disposable strict-host-key SSH acceptance")
def test_live_disposable_ssh_target_full_remote_promotion_and_final_apply(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    key_path = tmp_path / "id_ed25519"
    known_hosts = tmp_path / "known_hosts"
    image = os.environ.get("BEAST_LIVE_SSH_IMAGE", "beast-disposable-sshd:live")
    dockerfile = Path(__file__).resolve().parents[1] / "fixtures" / "disposable-sshd"
    _run(["docker", "build", "-t", image, str(dockerfile)], timeout=180.0)
    _run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path)], timeout=20.0)
    container = _run([
        "docker", "run", "-d",
        "-p", "127.0.0.1::22",
        "-v", f"{root}:/repo",
        image,
    ])
    try:
        _run(["docker", "cp", str(key_path) + ".pub", f"{container}:/root/.ssh/authorized_keys"])
        _run(["docker", "exec", container, "chown", "root:root", "/root/.ssh/authorized_keys"])
        _run(["docker", "exec", container, "chmod", "600", "/root/.ssh/authorized_keys"])
        port_line = _run(["docker", "port", container, "22/tcp"])
        port = port_line.rsplit(":", 1)[-1].strip()
        scan = subprocess.run(["ssh-keyscan", "-p", port, "127.0.0.1"], capture_output=True, text=True, timeout=20, check=True)
        known_hosts.write_text(scan.stdout, encoding="utf-8")

        async def scenario() -> None:
            engine = AgentRunEngine(root)
            run_id = engine.create_run(session_id="live-ssh", objective="ssh VALUE repair", run_id="live-ssh-promotion")["run_id"]
            approval = _approval(engine, run_id)
            target_payload = {
                "kind": "ssh",
                "host": "root@127.0.0.1",
                "port": port,
                "identityFile": str(key_path),
                "knownHosts": str(known_hosts),
                "remoteRoot": "/repo",
            }
            await engine.execute_tool(
                run_id,
                "worktree.bind",
                {"objective": "ssh VALUE repair"},
                approval_id=approval,
                execution_target="ssh",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.replace_exact",
                {"path": "value.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
                approval_id=approval,
                execution_target="ssh",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.verify",
                {"command": ["python3", "-m", "py_compile", "value.py"]},
                approval_id=approval,
                execution_target="ssh",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.diff",
                {},
                execution_target="ssh",
                execution_target_payload=target_payload,
            )
            await engine.execute_tool(
                run_id,
                "worktree.sourceplan_draft",
                {},
                execution_target="ssh",
                execution_target_payload=target_payload,
            )

            promotion = PromotionEngine(root)
            evaluated = promotion.evaluate(run_id, requested_by="live-ssh")
            assert evaluated["eligible"] is True, [policy for policy in evaluated["receipt"]["policies"] if not policy["passed"]]
            promotion_approval = evaluated["approval"]["approval_id"]
            promotion.engine.store.resolve_approval(run_id, promotion_approval, {"approved": True, "resolved_by": "SSH Operator"})
            promoted = promotion.promote(run_id, approval_id=promotion_approval, commit_message="Promote live SSH VALUE repair")
            assert promoted["candidate"]["status"] == "remote_commit_candidate"

            final_eval = promotion.evaluate_final_apply(run_id, requested_by="live-ssh")
            assert final_eval["eligible"] is True, [policy for policy in final_eval["receipt"]["policies"] if not policy["passed"]]
            final_approval = final_eval["approval"]["approval_id"]
            promotion.engine.store.resolve_approval(run_id, final_approval, {"approved": True, "resolved_by": "SSH Operator"})
            finalized = promotion.finalize(run_id, approval_id=final_approval, target_branch="main")
            assert finalized["final_apply"]["status"] == "finalized"
            assert finalized["final_apply"]["target_execution"] == "remote_ssh"

        asyncio.run(scenario())
        assert (root / "value.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    finally:
        subprocess.run(["docker", "exec", container, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/repo"], capture_output=True, text=True, timeout=20, check=False)
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=20, check=False)


@pytest.mark.skipif(os.environ.get("BEAST_LIVE_SSH_DOCKER_ACCEPTANCE") != "1", reason="set BEAST_LIVE_SSH_DOCKER_ACCEPTANCE=1 to build and run disposable strict-host-key SSH acceptance")
def test_live_disposable_ssh_target_planner_driven_multiturn_ci_repair_and_final_apply(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    key_path = tmp_path / "id_ed25519"
    known_hosts = tmp_path / "known_hosts"
    image = os.environ.get("BEAST_LIVE_SSH_IMAGE", "beast-disposable-sshd:live")
    dockerfile = Path(__file__).resolve().parents[1] / "fixtures" / "disposable-sshd"
    _run(["docker", "build", "-t", image, str(dockerfile)], timeout=180.0)
    _run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path)], timeout=20.0)
    container = _run([
        "docker", "run", "-d",
        "-p", "127.0.0.1::22",
        "-v", f"{root}:/repo",
        image,
    ])
    try:
        _run(["docker", "cp", str(key_path) + ".pub", f"{container}:/root/.ssh/authorized_keys"])
        _run(["docker", "exec", container, "chown", "root:root", "/root/.ssh/authorized_keys"])
        _run(["docker", "exec", container, "chmod", "600", "/root/.ssh/authorized_keys"])
        port_line = _run(["docker", "port", container, "22/tcp"])
        port = port_line.rsplit(":", 1)[-1].strip()
        scan = subprocess.run(["ssh-keyscan", "-p", port, "127.0.0.1"], capture_output=True, text=True, timeout=20, check=True)
        known_hosts.write_text(scan.stdout, encoding="utf-8")
        finalized = asyncio.run(_run_planner_driven_remote_ci_loop(
            root=root,
            session_id="live-ssh-planner-ci",
            run_id="live-ssh-planner-ci",
            execution_target="ssh",
            target_payload={
                "kind": "ssh",
                "host": "root@127.0.0.1",
                "port": port,
                "identityFile": str(key_path),
                "knownHosts": str(known_hosts),
                "remoteRoot": "/repo",
            },
        ))
        assert finalized["final_apply"]["target_branch"] == "main"
        assert (root / "value.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    finally:
        subprocess.run(["docker", "exec", container, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/repo"], capture_output=True, text=True, timeout=20, check=False)
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=20, check=False)
