from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cli.api import ActionResult
from app.kernel.agents.run_events import canonical_event_type
from app.routes.ide import build_ide_router
from app.routes.sourceplan import build_sourceplan_router


class CodeCortex:
    def build_snapshot(self, *_args, **_kwargs):
        return {"status": "ready"}

    def related_context(self, *_args, **_kwargs):
        return []

    def context_for(self, *_args, **_kwargs):
        return []

    def get_file_summary(self, _root, path):
        return {"ok": True, "summary": {"language": "python", "symbols": [{"name": "value", "kind": "function", "line": 1, "end_line": 2}], "imports": [], "routes": [], "path": path}}

    def get_dependents(self, *_args, **_kwargs):
        return {"results": []}

    def search_symbols(self, *_args, **_kwargs):
        return {"results": []}

    def get_editing_context(self, *_args, **_kwargs):
        return {"results": []}


class FakeCoordinator:
    def __init__(self, _root):
        self.advisory_context = [{"source": "vector_rag", "id": "hit-1", "content": "advisory", "authority": "advisory_only"}]

    def prepare(self, **_kwargs):
        return {
            "events": [{
                "event_type": "agent.integration.fired",
                "payload": {
                    "capability": "vector_rag",
                    "status": "fired",
                    "mode": "advisory_retrieval",
                    "reason": "retrieval_completed",
                    "metrics": {"hits": 1},
                    "artifacts": {},
                    "authority": "advisory_or_existing_gate_only",
                },
            }]
        }


def _client(root: Path) -> TestClient:
    app = FastAPI()
    app.include_router(build_ide_router(root, code_cortex_router=CodeCortex()))
    app.include_router(build_sourceplan_router(root))
    return TestClient(app)


def test_integration_sse_events_keep_their_exact_durable_event_type() -> None:
    assert canonical_event_type("agent_run_integration", {"status": "fired"}) == "agent.integration.fired"
    assert canonical_event_type("agent_run_integration", {"status": "skipped"}) == "agent.integration.skipped"
    assert canonical_event_type("agent_run_integration", {"status": "failed"}) == "agent.integration.failed"


def test_agent_coder_streams_and_persists_normalized_integration_evidence(tmp_path: Path, monkeypatch) -> None:
    from app.routes.ide_routes import agent_run_stream

    (tmp_path / "service.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(agent_run_stream, "CoderIntegrationCoordinator", FakeCoordinator)

    async def fake_stream(_self, *_args, **_kwargs):
        yield {"type": "error", "error": "provider deliberately unavailable in route test"}

    monkeypatch.setattr(agent_run_stream.BeastApiClient, "stream_live_turn", fake_stream)
    client = _client(tmp_path)
    session = client.post(
        "/edgek/ide/agent-sessions/create",
        json={
            "root_path": str(tmp_path),
            "objective": "Change value safely",
            "mode": "implementer",
            "provider": "tgi",
            "model": "test-model",
            "files": ["service.py"],
            "tools": [
                "granted:workspace_search",
                "granted:read_related_files",
                "granted:use_verified_skill",
                "granted:run_isolated_verifier",
            ],
        },
    ).json()["session"]

    with client.stream(
        "GET",
        f"/edgek/ide/agent-sessions/{session['session_id']}/run-events",
        params=[
            ("root_path", str(tmp_path)),
            ("prompt", "Change value safely"),
            ("context_files", "service.py"),
        ],
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: agent_run_integration" in body
    assert '"capability":"vector_rag"' in body.replace(" ", "")
    runs = client.get("/edgek/agent-runs", params={"root_path": str(tmp_path), "session_id": session["session_id"]}).json()
    run_id = runs["runs"][0]["run_id"]
    events = client.get(f"/edgek/agent-runs/{run_id}/events", params={"root_path": str(tmp_path)}).json()["events"]
    fired = [event for event in events if event["event_type"] == "agent.integration.fired"]
    assert len(fired) == 1
    assert fired[0]["payload"]["capability"] == "vector_rag"
    assert fired[0]["payload"]["metrics"] == {"hits": 1}


def test_verified_agent_sourceplan_apply_runs_sealed_postflight_and_persists_events(tmp_path: Path, monkeypatch) -> None:
    from app.routes import sourceplan

    class PostflightCoordinator:
        def __init__(self, _root):
            pass

        def complete(self, **_kwargs):
            return {
                "events": [
                    {
                        "event_type": "agent.integration.fired",
                        "payload": {
                            "capability": "memory_hull.seal",
                            "status": "fired",
                            "mode": "sealed_local_residue",
                            "reason": "seal_verified",
                            "metrics": {"verified": True},
                            "artifacts": {"residue_id": "residue-safe"},
                            "authority": "advisory_or_existing_gate_only",
                        },
                    }
                ]
            }

    def fake_apply(_self, _plan, approved=False):
        assert approved is True
        return ActionResult(True, "applied", "applied", {"applied": ["service.py"], "verification": {"ok": True}})

    monkeypatch.setattr(sourceplan, "CoderIntegrationCoordinator", PostflightCoordinator)
    monkeypatch.setattr(sourceplan.BeastApiClient, "apply_patch_plan", fake_apply)
    client = _client(tmp_path)
    session = client.post(
        "/edgek/ide/agent-sessions/create",
        json={"root_path": str(tmp_path), "objective": "Apply safely", "mode": "implementer"},
    ).json()["session"]
    run = client.post(
        "/edgek/agent-runs",
        json={"root_path": str(tmp_path), "session_id": session["session_id"], "objective": "Apply safely"},
    ).json()["run"]

    applied = client.post(
        "/edgek/sourceplan/apply",
        json={
            "root_path": str(tmp_path),
            "approved": True,
            "plan": {
                "plan_id": "plan-safe",
                "objective": "Apply safely",
                "agent_session_id": session["session_id"],
                "agent_run_id": run["run_id"],
                "files_allowed": ["service.py"],
                "operations": [],
            },
        },
    )

    assert applied.status_code == 200
    integration = applied.json()["integration_events"]
    assert integration[0]["payload"]["capability"] == "memory_hull.seal"
    events = client.get(f"/edgek/agent-runs/{run['run_id']}/events", params={"root_path": str(tmp_path)}).json()["events"]
    types = [event["event_type"] for event in events]
    assert "agent.episode.sealed" in types
    assert "agent.integration.fired" in types
