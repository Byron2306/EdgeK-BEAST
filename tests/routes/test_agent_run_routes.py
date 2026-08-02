from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.ide import build_ide_router
from app.routes.ide_routes.agent_runs import _prefer_direct_ollama_planner


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
