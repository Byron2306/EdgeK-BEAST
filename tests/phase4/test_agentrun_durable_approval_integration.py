from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.kernel.agents.durable_approval_runtime import DurableAgentApprovalRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.approvals import DurableApprovalCardStore, DurableApprovalStore
from app.routes.ide import build_ide_router


class _Cortex:
    def build_snapshot(self, *_args, **_kwargs): return {"status": "dummy"}
    def related_context(self, *_args, **_kwargs): return []
    def context_for(self, *_args, **_kwargs): return []
    def get_editing_context(self, *_args, **_kwargs): return {"results": []}
    def get_file_summary(self, _root, path):
        return {"ok": True, "summary": {"path": path, "language": "python", "symbols": [], "imports": [], "routes": []}}
    def get_dependents(self, *_args, **_kwargs): return {"results": []}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "phase4-live"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "beast@example.test")
    _git(root, "config", "user.name", "BEAST Phase4")
    (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "seed")
    return root


def _app(root: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(build_ide_router(root, code_cortex_router=_Cortex()))
    return app


def _wait(client: TestClient, root: Path, run_id: str, states: set[str], timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = client.get(
            f"/edgek/agent-runs/{run_id}",
            params={"root_path": str(root)},
        ).json()["run"]
        if str(last.get("state") or "") in states:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run did not reach {states}; last={last}")


async def _wait_async(client: httpx.AsyncClient, root: Path, run_id: str, states: set[str], timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        response = await client.get(
            f"/edgek/agent-runs/{run_id}",
            params={"root_path": str(root)},
        )
        last = response.json()["run"]
        if str(last.get("state") or "") in states:
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"run did not reach {states}; last={last}")


def _session(client: TestClient, root: Path) -> dict:
    response = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(root),
        "task": "Create an isolated worktree and stop.",
        "mode": "agent",
        "provider": "ollama",
        "model": "phase4-scripted",
        "files": ["sample.py"],
    })
    assert response.status_code == 200
    return response.json()["session"]


def _create_run(client: TestClient, root: Path) -> str:
    session = _session(client, root)
    response = client.post("/edgek/agent-runs", json={
        "workspace_root": str(root),
        "session_id": session["session_id"],
        "task": "Create an isolated worktree and stop.",
        "mode": "agent",
        "provider": "ollama",
        "model": "phase4-scripted",
        "launch": False,
        "request": {
            "prompt": "Create an isolated worktree and stop.",
            "context_files": ["sample.py"],
            "durable_approvals": True,
            "permission_mode": "GUIDED",
            "approval_timeout_seconds": 30,
        },
        "budget": {"profile": "balanced"},
    })
    assert response.status_code == 200
    return response.json()["run"]["run_id"]


@pytest.mark.asyncio
async def test_live_planner_uses_one_use_phase4_capability(tmp_path):
    root = _repo(tmp_path)
    app = _app(root)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session_response = await client.post("/edgek/ide/agent-sessions/create", json={
            "workspace_root": str(root),
            "task": "Create an isolated worktree and stop.",
            "mode": "agent",
            "provider": "ollama",
            "model": "phase4-scripted",
            "files": ["sample.py"],
        })
        assert session_response.status_code == 200
        session = session_response.json()["session"]
        created = await client.post("/edgek/agent-runs", json={
            "workspace_root": str(root),
            "session_id": session["session_id"],
            "task": "Create an isolated worktree and stop.",
            "mode": "agent",
            "provider": "ollama",
            "model": "phase4-scripted",
            "launch": False,
            "request": {
                "prompt": "Create an isolated worktree and stop.",
                "context_files": ["sample.py"],
                "durable_approvals": True,
                "permission_mode": "GUIDED",
                "approval_timeout_seconds": 30,
            },
            "budget": {"profile": "balanced"},
        })
        assert created.status_code == 200
        run_id = created.json()["run"]["run_id"]

        launch = await client.post(f"/edgek/agent-runs/{run_id}/planner/execute", json={
            "workspace_root": str(root),
            "max_turns": 6,
            "simulate_decisions": [
                {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {"limit": 100, "include_symbols": True}},
                {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {"objective": "phase4 durable approval", "risk": "high"}},
                {"decision_type": "blocked", "blocker": "phase4 proof complete"},
            ],
        })
        assert launch.status_code == 200

        waiting = await _wait_async(client, root, run_id, {"waiting_for_approval"})
        checkpoint = waiting["checkpoint"]
        suspended = checkpoint["suspended_step"]
        assert suspended["phase4_durable"] is True
        assert suspended["tool_id"] == "worktree.bind"
        assert suspended["arguments"]["objective"] == "phase4 durable approval"

        legacy_response = await client.get(
            f"/edgek/agent-runs/{run_id}/approvals",
            params={"root_path": str(root)},
        )
        legacy = legacy_response.json()["approvals"]
        assert len(legacy) == 1
        approval_id = legacy[0]["approval_id"]
        assert legacy[0]["status"] == "pending"

        card = DurableApprovalCardStore(root).get(approval_id)
        assert card["state"] == "PENDING"
        assert card["envelope"]["approval_request"]["tool_id"] == "worktree.bind"
        assert card["envelope"]["approval_request"]["arguments"] == suspended["arguments"]
        assert DurableApprovalCardStore(root).verify_chain(approval_id)["ok"] is True
        assert DurableApprovalStore(root).verify_chain(approval_id)["ok"] is True

        approved = await client.post(f"/edgek/agent-runs/{run_id}/approvals/{approval_id}", json={
            "root_path": str(root),
            "approved": True,
            "decision": "APPROVE",
            "scope": "ONCE",
            "operator_id": "operator:phase4-test",
        })
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["phase4"]["approved"] is True
        assert body["phase4"]["capability"]["single_use"] is True
        assert body["consumption_receipt"]["replay_allowed"] is False

        final = await _wait_async(client, root, run_id, {"policy_blocked", "completed"})

    events = AgentRunEngine(root).store.events(run_id, limit=500)
    event_types = [event["event_type"] for event in events]
    assert "agent.approval.capability_consumed" in event_types
    assert "agent.approval.exact_call_authorized" in event_types
    assert "agent.approval.exact_call_consumed" in event_types
    assert "agent.tool.completed" in event_types

    checkpoint = final["checkpoint"]
    assert checkpoint["approval_resume"]["status"] == "CONSUMED_COMPLETED"
    assert checkpoint["approval_resume"]["approval_id"] == approval_id
    assert checkpoint["worktree_root"]
    assert Path(checkpoint["worktree_root"]).resolve() != root.resolve()

    with pytest.raises(PermissionError, match="not ready for exact tool execution"):
        await AgentRunEngine(root).execute_tool(
            run_id,
            "worktree.bind",
            {"objective": "phase4 durable approval", "risk": "high"},
            approval_id=approval_id,
        )


@pytest.mark.asyncio
async def test_review_mode_lifts_read_only_tool_into_durable_approval(tmp_path):
    root = _repo(tmp_path)
    app = _app(root)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session_response = await client.post("/edgek/ide/agent-sessions/create", json={
            "workspace_root": str(root),
            "task": "List workspace under review mode.",
            "mode": "analysis",
            "provider": "ollama",
            "model": "phase4-scripted",
        })
        session = session_response.json()["session"]
        created = await client.post("/edgek/agent-runs", json={
            "workspace_root": str(root),
            "session_id": session["session_id"],
            "task": "List workspace under review mode.",
            "mode": "analysis",
            "provider": "ollama",
            "model": "phase4-scripted",
            "launch": False,
            "request": {
                "prompt": "List workspace under review mode.",
                "durable_approvals": True,
                "permission_mode": "REVIEW",
                "approval_timeout_seconds": 30,
            },
            "budget": {"profile": "balanced"},
        })
        run_id = created.json()["run"]["run_id"]

        launched = await client.post(f"/edgek/agent-runs/{run_id}/planner/execute", json={
            "workspace_root": str(root),
            "max_turns": 3,
            "simulate_decisions": [
                {"decision_type": "tool", "tool_id": "workspace.list", "arguments": {}},
            ],
        })
        assert launched.status_code == 200
        waiting = await _wait_async(client, root, run_id, {"waiting_for_approval"})
        suspended = waiting["checkpoint"]["suspended_step"]
        assert suspended["tool_id"] == "workspace.list"
        assert suspended["phase4_durable"] is True

        approvals_response = await client.get(
            f"/edgek/agent-runs/{run_id}/approvals",
            params={"root_path": str(root)},
        )
        approval = approvals_response.json()["approvals"][0]
        card = DurableApprovalCardStore(root).get(approval["approval_id"])
        classification = card["envelope"]["classification"]
        assert classification["tool_class"] == "READ_ONLY"
        assert classification["requirement"] == "REQUIRE_APPROVAL"

        rejected = await client.post(
            f"/edgek/agent-runs/{run_id}/approvals/{approval['approval_id']}",
            json={
                "root_path": str(root),
                "approved": False,
                "decision": "REJECT",
                "reason": "Read-only access is not required for this run.",
                "operator_id": "operator:review-test",
            },
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["phase4"]["approved"] is False
        await _wait_async(client, root, run_id, {"policy_blocked"})


def test_restart_paused_approval_consumes_exact_capability(tmp_path):
    root = _repo(tmp_path)
    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="phase4-restart",
        objective="Resume exact worktree bind after restart",
        mode="agent",
        provider="simulated",
        model="phase4-test",
        request={
            "durable_approvals": True,
            "permission_mode": "GUIDED",
            "approval_timeout_seconds": 600,
        },
        budget={"profile": "balanced"},
    )["run_id"]
    spec = engine.tool_registry.get("worktree.bind")
    approval_id = "approval-phase4-restart"
    step_id = "step-phase4-restart"
    arguments = {"objective": "restart exact step", "risk": "high"}

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
    engine.store.create_approval(run_id, {
        "request_id": approval_id,
        "run_id": run_id,
        "step_id": step_id,
        "tool_id": "worktree.bind",
        "tool_version": spec.version,
        "phase4_durable": True,
    })
    engine.merge_checkpoint(run_id, {
        "suspended_step": {
            "step_id": step_id,
            "approval_id": approval_id,
            "tool_id": "worktree.bind",
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
    engine.store.transition(run_id, "paused", error="runtime_restarted; resume required")

    resolved = runtime.resolve(
        approval_id=approval_id,
        resolution={
            "approved": True,
            "decision": "APPROVE",
            "scope": "ONCE",
            "operator_id": "operator:restart-test",
        },
        run=engine.store.get_run(run_id) or {},
    )
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "ONCE"})
    receipt = runtime.consume_and_resume(
        capability=resolved["capability"],
        request=resolved["request"],
    )
    assert receipt["run_resumed"] is True
    assert receipt["resume_state"] == "executing_tool"
    assert receipt["step_id"] == step_id
    assert receipt["tool_id"] == "worktree.bind"

    resumed = engine.store.get_run(run_id) or {}
    assert resumed["state"] == "executing_tool"
    assert resumed["checkpoint"]["approval_resume"]["status"] == "READY_FOR_EXACT_TOOL_EXECUTION"
    observation = asyncio.run(engine.execute_tool(
        run_id,
        "worktree.bind",
        arguments,
        approval_id=approval_id,
    ))
    assert observation["status"] == "completed"
    assert (engine.store.get_run(run_id) or {})["checkpoint"]["approval_resume"]["status"] == "CONSUMED_COMPLETED"
