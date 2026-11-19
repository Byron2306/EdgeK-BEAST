from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.ide import build_ide_router
from app.routes.ide_routes.agent_runs import _prefer_direct_ollama_planner, _prefer_direct_planner
from app.kernel.agents.run_worker import TURN_RUNTIMES
from app.routes.ide_routes import agent_runs as agent_run_routes


class DummyCodeCortex:
    def build_snapshot(self, *_args, **_kwargs):
        return {"status": "dummy"}

    def related_context(self, *_args, **_kwargs):
        return []

    def context_for(self, *_args, **_kwargs):
        return []


def client_for(root: Path) -> TestClient:
    app = FastAPI()
    app.include_router(build_ide_router(root, code_cortex_router=DummyCodeCortex()))
    return TestClient(app)


def test_agent_run_crud_replay_cancel_and_resume(tmp_path):
    client = client_for(tmp_path)
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "root_path": str(tmp_path),
        "objective": "Inspect safely",
        "mode": "analysis",
    }).json()["session"]

    created = client.post("/edgek/agent-runs", json={
        "root_path": str(tmp_path),
        "session_id": session["session_id"],
        "objective": "Inspect safely",
    })
    assert created.status_code == 200
    run_id = created.json()["run"]["run_id"]

    detail = client.get(f"/edgek/agent-runs/{run_id}", params={"root_path": str(tmp_path)})
    assert detail.json()["run"]["state"] == "created"

    events = client.get(f"/edgek/agent-runs/{run_id}/events", params={"root_path": str(tmp_path)})
    assert events.json()["count"] == 1
    assert events.json()["events"][0]["event_type"] == "agent.run.created"

    cancelled = client.post(f"/edgek/agent-runs/{run_id}/cancel", json={
        "root_path": str(tmp_path), "reason": "test"
    })
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["state"] == "cancelling"

    verify = client.get(f"/edgek/agent-runs/{run_id}/verify", params={"root_path": str(tmp_path)})
    assert verify.json()["head_matches"] is True


def test_turn_rehydrates_a_missing_in_process_planner_runtime(tmp_path, monkeypatch):
    client = client_for(tmp_path)
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "root_path": str(tmp_path),
        "objective": "Continue the durable run",
        "mode": "agent",
        "provider": "nvidia_nim",
        "model": "nvidia/test-model",
    }).json()["session"]
    run = client.post("/edgek/agent-runs", json={
        "root_path": str(tmp_path),
        "session_id": session["session_id"],
        "objective": "Continue the durable run",
        "provider": "nvidia_nim",
        "model": "nvidia/test-model",
        "request": {"launch_strategy": "typed_planner"},
        "launch": False,
    }).json()["run"]
    run_id = run["run_id"]
    TURN_RUNTIMES.pop(run_id, None)
    relaunched = []

    class RehydratedRuntime:
        async def run_one_turn(self, requested_run_id):
            assert requested_run_id == run_id
            return {"run_id": run_id, "state": "completed"}

    def fake_launch(app, root, durable_run, **kwargs):
        relaunched.append((root, durable_run["run_id"]))
        TURN_RUNTIMES[run_id] = RehydratedRuntime()
        return {"active": True, "reused": False}

    monkeypatch.setattr(agent_run_routes, "_launch_for_run", fake_launch)
    try:
        response = client.post(
            f"/edgek/agent-runs/{run_id}/turn",
            params={"root_path": str(tmp_path)},
            json={"root_path": str(tmp_path)},
        )
    finally:
        TURN_RUNTIMES.pop(run_id, None)

    assert response.status_code == 200
    assert relaunched == [(tmp_path.resolve(), run_id)]


def test_legacy_simulation_is_recorded_as_durable_run(tmp_path):
    client = client_for(tmp_path)
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "root_path": str(tmp_path),
        "objective": "Explain the workspace",
        "mode": "analysis",
    }).json()["session"]

    with client.stream("GET", f"/edgek/ide/agent-sessions/{session['session_id']}/run-events", params={
        "root_path": str(tmp_path),
        "prompt": "Explain the workspace",
        "simulate": "true",
    }) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "agent_run_started" in body
    assert '"run_id"' in body
    assert "agent_run_done" in body

    registry = client.get("/edgek/agent-runs", params={
        "root_path": str(tmp_path), "session_id": session["session_id"]
    }).json()
    assert registry["count"] == 1
    run = registry["runs"][0]
    assert run["state"] == "completed"

    replay = client.get(f"/edgek/agent-runs/{run['run_id']}/events", params={
        "root_path": str(tmp_path)
    }).json()
    types = [event["event_type"] for event in replay["events"]]
    assert "agent.run.created" in types
    assert "agent.run.started" in types
    assert "agent.run.completed" in types


def test_planner_routes_execute_and_expose_checkpoint(tmp_path):
    (tmp_path / "README.md").write_text("BEAST planner proof\n", encoding="utf-8")
    with client_for(tmp_path) as client:
        session = client.post("/edgek/ide/agent-sessions/create", json={
            "root_path": str(tmp_path), "objective": "Inspect README", "mode": "analysis"
        }).json()["session"]
        created = client.post("/edgek/agent-runs", json={
            "root_path": str(tmp_path),
            "session_id": session["session_id"],
            "objective": "Inspect README",
            "launch": False,
        }).json()
        run_id = created["run"]["run_id"]
        launched = client.post(f"/edgek/agent-runs/{run_id}/planner/execute", json={
            "root_path": str(tmp_path),
            "max_turns": 3,
            "simulate_decisions": [
                {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "README.md"}},
                {"decision_type": "complete", "summary": "README contains the planner proof marker."},
            ],
        })
        assert launched.status_code == 200
        import time
        deadline = time.monotonic() + 5
        state = ""
        while time.monotonic() < deadline:
            detail = client.get(f"/edgek/agent-runs/{run_id}", params={"root_path": str(tmp_path)}).json()["run"]
            state = detail["state"]
            if state == "completed":
                break
            time.sleep(0.02)
        assert state == "completed"
        planner = client.get(f"/edgek/agent-runs/{run_id}/planner", params={"root_path": str(tmp_path)})
        assert planner.status_code == 200
        body = planner.json()["planner"]
        assert body["turn"] == 2
        assert body["observations"][0]["tool_id"] == "workspace.read_range"


def test_nim_typed_planner_does_not_select_ollama_route():
    assert _prefer_direct_ollama_planner({
        "provider": "nvidia_nim",
        "mode": "chat",
        "request": {"launch_strategy": "typed_planner"},
    }) is False


def test_explicit_typed_planner_strategy_is_provider_neutral():
    assert _prefer_direct_planner({
        "provider": "fireworks",
        "mode": "agent",
        "request": {"launch_strategy": "typed_planner"},
    }) is True


def test_legacy_simulation_without_typed_strategy_keeps_compatibility_worker():
    assert _prefer_direct_planner({
        "provider": "fireworks",
        "mode": "analysis",
        "request": {"simulate": True},
    }) is False


def test_agent_run_create_accepts_workspace_root_and_task_aliases(tmp_path):
    client = client_for(tmp_path)
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(tmp_path),
        "task": "Inspect the temporary workspace",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
    }).json()["session"]

    created = client.post("/edgek/agent-runs", json={
        "workspace_root": str(tmp_path),
        "session_id": session["session_id"],
        "task": "Inspect the temporary workspace",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
        "launch": False,
    })
    assert created.status_code == 200
    run = created.json()["run"]
    assert run["root_path"] == str(tmp_path.resolve())
    assert run["objective"] == "Inspect the temporary workspace"
    assert run["request"]["prompt"] == "Inspect the temporary workspace"
    assert run["request"]["workspace_root"] == str(tmp_path.resolve())


def test_agent_run_planner_execute_accepts_workspace_root_alias(tmp_path):
    client = client_for(tmp_path)
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(tmp_path),
        "task": "Inspect README",
        "mode": "analysis",
    }).json()["session"]
    created = client.post("/edgek/agent-runs", json={
        "workspace_root": str(tmp_path),
        "session_id": session["session_id"],
        "task": "Inspect README",
        "mode": "analysis",
        "launch": False,
    }).json()
    run_id = created["run"]["run_id"]

    launched = client.post(f"/edgek/agent-runs/{run_id}/planner/execute", json={
        "workspace_root": str(tmp_path),
        "max_turns": 2,
        "simulate_decisions": [
            {"decision_type": "blocked", "blocker": "workspace proof"},
        ],
    })
    assert launched.status_code == 200
    assert launched.json()["execution"]["engine"] == "typed_planner_v1"


def test_agent_run_events_accept_workspace_root_query_alias(tmp_path):
    client = client_for(tmp_path)
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(tmp_path),
        "task": "Inspect safely",
        "mode": "analysis",
    }).json()["session"]
    run_id = client.post("/edgek/agent-runs", json={
        "workspace_root": str(tmp_path),
        "session_id": session["session_id"],
        "task": "Inspect safely",
        "launch": False,
    }).json()["run"]["run_id"]

    detail = client.get(f"/edgek/agent-runs/{run_id}", params={"root_path": str(tmp_path)}).json()["run"]
    assert detail["root_path"] == str(tmp_path.resolve())
    events = client.get(f"/edgek/agent-runs/{run_id}/events", params={"workspace_root": str(tmp_path)}).json()
    assert events["count"] == 1
    assert events["events"][0]["event_type"] == "agent.run.created"


def test_turn_writes_correlated_completion_receipt_for_read_only_status(tmp_path):
    from app.kernel.agents.run_engine import AgentRunEngine

    client = client_for(tmp_path)
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(session_id="receipt-test", objective="Observe a paused turn")["run_id"]
    request_id = "a" * 32

    class Runtime:
        async def run_one_turn(self, rid):
            assert rid == run_id
            return engine.store.transition(rid, "paused")

    TURN_RUNTIMES[run_id] = Runtime()
    try:
        response = client.post(f"/edgek/agent-runs/{run_id}/turn",
                               params={"root_path": str(tmp_path)}, json={"turn_request_id": request_id})
        assert response.status_code == 200
        durable = client.get(f"/edgek/agent-runs/{run_id}", params={"root_path": str(tmp_path)}).json()["run"]
        assert durable["state"] == "paused"
        assert durable["checkpoint"]["coder_turn_reply"] == {"id": request_id, "state": "paused"}
    finally:
        TURN_RUNTIMES.pop(run_id, None)


def test_gateway_resumes_exact_approved_bind_after_checkpoint_is_replaced(tmp_path, monkeypatch):
    import subprocess

    from app.kernel.agents.planner_provider import CallbackPlannerProvider
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime
    from app.kernel.agents.run_engine import AgentRunEngine

    workspace = tmp_path / "repo"
    workspace.mkdir()
    for args in (["init", "-q"], ["-c", "user.email=test@example.test", "-c",
                                 "user.name=Test", "commit", "--allow-empty", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=workspace, check=True)
    outside = tmp_path / "external"
    monkeypatch.setenv("BEAST_WORKTREE_ROOT", str(outside))
    client = client_for(workspace)
    engine = AgentRunEngine(workspace)
    run_id = engine.create_run(session_id="approval-test", objective="Edit a fixture", mode="agent",
                               request={"execution_target": "local"})["run_id"]
    calls = []

    async def plan(prompt, run, turn):
        calls.append(turn)
        if len(calls) == 1:
            return {"decision_type": "tool", "tool_id": "workspace.index", "arguments": {}}
        return {"decision_type": "tool", "tool_id": "worktree.bind",
                "arguments": {"base_ref": "HEAD", "task_id": f"proposal-{len(calls)}"}}

    base = f"/edgek/agent-runs/{run_id}"
    params = {"root_path": str(workspace)}

    def turn(number):
        reply = client.post(base + "/turn", params=params, json={"turn_request_id": f"{number:032x}"})
        assert reply.status_code == 200, reply.text
        return reply.json()["run"]

    TURN_RUNTIMES[run_id] = AgentPlannerRuntime(engine, CallbackPlannerProvider(plan))
    try:
        turn(1)
        assert turn(2)["state"] == "waiting_for_approval"
        approval, = engine.store.approvals(run_id)
        # Simulate losing all transient approval pointers to an unrelated checkpoint writer.
        engine.checkpoint(run_id, {"planner": engine.store.get_run(run_id)["checkpoint"]["planner"]})
        TURN_RUNTIMES[run_id] = AgentPlannerRuntime(AgentRunEngine(workspace), CallbackPlannerProvider(plan))
        assert turn(3)["state"] == "waiting_for_approval"
        assert len(calls) == 2
        reply = client.post(base + f"/approvals/{approval['approval_id']}",
                            json={**params, "approved": True})
        assert reply.status_code == 200, reply.text
        checkpoint = turn(4)["checkpoint"]
        assert len(calls) == 2
        assert Path(checkpoint["worktree_root"]).is_relative_to(outside)
        assert len(engine.store.approvals(run_id)) == 1
        binds = [e["payload"]["observation"] for e in engine.store.events(run_id, limit=500)
                 if e["event_type"] == "agent.tool.completed"
                 and e["payload"]["observation"]["tool_id"] == "worktree.bind"]
        assert len(binds) == 1
        assert binds[0]["arguments"] == approval["request"]["safe_arguments"]
        assert engine.store.get_approval(run_id, approval["approval_id"])["resume_claimed"]
    finally:
        TURN_RUNTIMES.pop(run_id, None)
