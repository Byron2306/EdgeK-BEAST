from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.ide import build_ide_router


class ExecutionCodeCortex:
    def build_snapshot(self, *_args, **_kwargs):
        return {"status": "dummy"}

    def related_context(self, *_args, **_kwargs):
        return []

    def context_for(self, *_args, **_kwargs):
        return []

    def get_editing_context(self, *_args, **_kwargs):
        return {"results": []}

    def get_file_summary(self, _root, path):
        return {
            "ok": True,
            "summary": {
                "path": path,
                "language": "python",
                "symbols": [{"name": "example", "kind": "function", "line": 1, "end_line": 2}],
                "imports": [],
                "routes": [],
            },
        }

    def get_dependents(self, *_args, **_kwargs):
        return {"results": []}


def app_for(root: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(build_ide_router(root, code_cortex_router=ExecutionCodeCortex()))
    return app


def wait_for_state(client: TestClient, root: Path, run_id: str, states: set[str], timeout: float = 8.0):
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = client.get(f"/edgek/agent-runs/{run_id}", params={"root_path": str(root)}).json()["run"]
        if str(last.get("state")) in states:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run did not reach {states}; last={last}")


def test_post_launch_owns_execution_and_legacy_replay(tmp_path):
    client = TestClient(app_for(tmp_path))
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "root_path": str(tmp_path),
        "objective": "Explain this workspace",
        "mode": "analysis",
    }).json()["session"]

    created = client.post("/edgek/agent-runs", json={
        "root_path": str(tmp_path),
        "session_id": session["session_id"],
        "objective": "Explain this workspace",
        "mode": "analysis",
        "launch": True,
        "request": {
            "transport": "durable_agent_run_v2",
            "prompt": "Explain this workspace",
            "simulate": True,
            "approval_timeout_seconds": 30,
        },
    })
    assert created.status_code == 200
    payload = created.json()
    assert payload["execution"]["active"] is True
    run_id = payload["run"]["run_id"]

    run = wait_for_state(client, tmp_path, run_id, {"completed"})
    assert run["request"]["transport"] == "durable_agent_run_v2"
    assert run["execution"]["active"] is False

    replay = client.get(f"/edgek/agent-runs/{run_id}/events", params={"root_path": str(tmp_path)}).json()
    event_types = [event["event_type"] for event in replay["events"]]
    assert "agent.run.worker.started" in event_types
    assert "agent.run.started" in event_types
    assert "agent.run.completed" in event_types

    with client.stream("GET", f"/edgek/agent-runs/{run_id}/events", params={
        "root_path": str(tmp_path),
        "after": 0,
        "follow": "true",
        "projection": "legacy",
    }) as response:
        body = "".join(response.iter_text())
        assert response.status_code == 200
        assert "event: agent_run_started" in body
        assert "event: agent_run_done" in body
        assert "id: " in body


def test_durable_approval_pauses_worker_and_resumes_same_run(tmp_path):
    (tmp_path / "sample.py").write_text("def example():\n    return 1\n", encoding="utf-8")
    client = TestClient(app_for(tmp_path))
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "root_path": str(tmp_path),
        "objective": "Inspect sample",
        "mode": "analysis",
        "files": ["sample.py"],
    }).json()["session"]
    created = client.post("/edgek/agent-runs", json={
        "root_path": str(tmp_path),
        "session_id": session["session_id"],
        "objective": "Inspect sample",
        "mode": "analysis",
        "launch": True,
        "request": {
            "prompt": "Inspect sample",
            "context_files": ["sample.py"],
            "simulate": True,
            "approval_timeout_seconds": 30,
        },
    }).json()
    run_id = created["run"]["run_id"]
    waiting = wait_for_state(client, tmp_path, run_id, {"waiting_for_approval"})
    assert waiting["execution"]["active"] is True

    approvals = client.get(f"/edgek/agent-runs/{run_id}/approvals", params={"root_path": str(tmp_path)}).json()["approvals"]
    assert approvals and approvals[0]["status"] == "pending"
    approval_id = approvals[0]["approval_id"]

    resolved = client.post(f"/edgek/agent-runs/{run_id}/approvals/{approval_id}", json={
        "root_path": str(tmp_path),
        "approved": False,
        "scope": "once",
    })
    assert resolved.status_code == 200
    assert resolved.json()["approval"]["status"] == "rejected"

    final = wait_for_state(client, tmp_path, run_id, {"completed"})
    assert final["run_id"] == run_id
    assert client.get(f"/edgek/agent-runs/{run_id}/verify", params={"root_path": str(tmp_path)}).json()["head_matches"] is True


def test_resume_relaunches_persisted_request(tmp_path):
    client = TestClient(app_for(tmp_path))
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "root_path": str(tmp_path),
        "objective": "Resume me",
        "mode": "analysis",
    }).json()["session"]
    created = client.post("/edgek/agent-runs", json={
        "root_path": str(tmp_path),
        "session_id": session["session_id"],
        "objective": "Resume me",
        "mode": "analysis",
        "launch": False,
        "request": {"prompt": "Resume me", "simulate": True, "approval_timeout_seconds": 30},
    }).json()
    run_id = created["run"]["run_id"]
    assert created["run"]["state"] == "created"
    assert created["execution"]["active"] is False

    resumed = client.post(f"/edgek/agent-runs/{run_id}/resume", json={"root_path": str(tmp_path)})
    assert resumed.status_code == 200
    assert resumed.json()["execution"]["active"] is True
    assert wait_for_state(client, tmp_path, run_id, {"completed"})["state"] == "completed"


def test_resume_preserves_planner_execution_path(tmp_path):
    client = TestClient(app_for(tmp_path))
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(tmp_path),
        "task": "Inspect README with planner",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
    }).json()["session"]
    created = client.post("/edgek/agent-runs", json={
        "workspace_root": str(tmp_path),
        "session_id": session["session_id"],
        "task": "Inspect README with planner",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
        "launch": False,
        "request": {
            "prompt": "Inspect README with planner",
            "simulate": True,
            "approval_timeout_seconds": 30,
        },
    }).json()
    run_id = created["run"]["run_id"]

    resumed = client.post(f"/edgek/agent-runs/{run_id}/resume", json={"workspace_root": str(tmp_path)})
    assert resumed.status_code == 200
    assert resumed.json()["execution"]["engine"] == "typed_planner_v1"


def test_run_detail_auto_recovers_runtime_restarted_pause(tmp_path):
    client = TestClient(app_for(tmp_path))
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(tmp_path),
        "task": "Recover planner run",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
    }).json()["session"]
    created = client.post("/edgek/agent-runs", json={
        "workspace_root": str(tmp_path),
        "session_id": session["session_id"],
        "task": "Recover planner run",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
        "launch": False,
    }).json()
    run_id = created["run"]["run_id"]

    store = client.app.state  # keep reference alive for app lifetime
    del store
    from app.kernel.agents.run_store import AgentRunStore
    AgentRunStore(tmp_path).transition(run_id, "paused", error="runtime_restarted; resume required")

    recovered = client.get(
        f"/edgek/agent-runs/{run_id}",
        params={"workspace_root": str(tmp_path), "auto_recover": "true"},
    )
    assert recovered.status_code == 200
    payload = recovered.json()["run"]
    assert payload["execution"]["active"] is True
    assert payload["execution"]["engine"] == "typed_planner_v1"

    events = client.get(
        f"/edgek/agent-runs/{run_id}/events",
        params={"workspace_root": str(tmp_path)},
    ).json()["events"]
    assert any(event["event_type"] == "agent.run.resumed" for event in events)


def test_verification_console_auto_recovers_runtime_restarted_pause(tmp_path):
    client = TestClient(app_for(tmp_path))
    session = client.post("/edgek/ide/agent-sessions/create", json={
        "workspace_root": str(tmp_path),
        "task": "Recover verification console",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
    }).json()["session"]
    created = client.post("/edgek/agent-runs", json={
        "workspace_root": str(tmp_path),
        "session_id": session["session_id"],
        "task": "Recover verification console",
        "mode": "analysis",
        "provider": "ollama",
        "model": "qwen2.5-coder:1.5b",
        "launch": False,
    }).json()
    run_id = created["run"]["run_id"]

    from app.kernel.agents.run_store import AgentRunStore
    AgentRunStore(tmp_path).transition(run_id, "paused", error="runtime_restarted; resume required")

    recovered = client.get(
        f"/edgek/agent-runs/{run_id}/console/verification",
        params={"workspace_root": str(tmp_path), "auto_recover": "true"},
    )
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["run_id"] == run_id
    assert body["status"] == "NOT_STARTED"

    events = client.get(
        f"/edgek/agent-runs/{run_id}/events",
        params={"workspace_root": str(tmp_path)},
    ).json()["events"]
    assert any(event["event_type"] == "agent.run.resumed" for event in events)
