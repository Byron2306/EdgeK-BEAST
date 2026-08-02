from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.ide import build_ide_router


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
