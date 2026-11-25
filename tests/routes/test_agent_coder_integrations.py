from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cli.api import ActionResult
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_events import canonical_event_type, legacy_event_projection, parse_sse_chunk
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


def test_canonical_integration_events_round_trip_to_legacy_agent_run_integration(tmp_path: Path) -> None:
    """WP003D: canonical agent.integration.{fired,skipped,failed} must project back
    to the Desktop IDE listener name agent_run_integration, with and without a
    stored legacy_type, including through the SSE serializer.
    """
    engine = AgentRunEngine(tmp_path)
    for index, status in enumerate(("fired", "skipped", "failed"), start=1):
        canonical = f"agent.integration.{status}"
        source_payload = {"capability": "vector_rag", "reason": f"round_trip_{status}"}
        name, projected = legacy_event_projection(canonical, source_payload)
        assert name == "agent_run_integration"
        assert projected["status"] == status
        assert projected["capability"] == "vector_rag"
        assert canonical_event_type(name, projected) == canonical

        event = {
            "sequence": index,
            "event_type": canonical,
            "created_at": 1,
            "payload": source_payload,
            "legacy_type": "",
        }
        frame = engine.sse_event(event, projection="legacy")
        assert "event: agent_run_integration\n" in frame
        parsed = parse_sse_chunk(frame)
        assert parsed is not None
        event_name, payload = parsed
        assert event_name == "agent_run_integration"
        assert payload["status"] == status
        assert payload["capability"] == "vector_rag"
        assert canonical_event_type(event_name, payload) == canonical

        stored = dict(event)
        stored["legacy_type"] = "agent_run_integration"
        stored["sequence"] = index + 10
        stored_frame = engine.sse_event(stored, projection="legacy")
        assert "event: agent_run_integration\n" in stored_frame
        stored_parsed = parse_sse_chunk(stored_frame)
        assert stored_parsed is not None
        stored_name, stored_payload = stored_parsed
        assert stored_name == "agent_run_integration"
        assert stored_payload["status"] == status

    _, contradictory = legacy_event_projection(
        "agent.integration.fired", {"status": "failed"}
    )
    assert contradictory["status"] == "fired"


def test_crystal_lifecycle_events_project_to_desktop_coder_stream() -> None:
    cases = {
        "agent.crystal.formed": "formed",
        "agent.crystal.activated": "activated",
        "agent.crystal.completed": "reused",
        "agent.crystal.reduction_receipt": "credited",
        "agent.crystal.formation_refused": "refused",
        "agent.crystal.formation_failed": "failed",
    }
    for canonical, lifecycle in cases.items():
        name, payload = legacy_event_projection(canonical, {
            "crystal_id": "coding-crystal:test",
            "heldout_successes": 3,
            "heldout_attempts": 3,
            "lattice_admitted": True,
        })
        assert name == "agent_run_crystal"
        assert payload["lifecycle"] == lifecycle
        assert payload["crystal_id"] == "coding-crystal:test"


def test_durable_canonical_integrations_replay_through_legacy_sse_route(tmp_path: Path) -> None:
    """WP003D: persisted postflight-style events must reach the real replay route."""
    engine = AgentRunEngine(tmp_path)
    run = engine.create_run(
        session_id="integration-replay-session",
        objective="Replay integration evidence",
        run_id="integration-replay-run",
    )
    run_id = run["run_id"]

    for status in ("fired", "skipped", "failed"):
        engine.emit(
            run_id,
            f"agent.integration.{status}",
            {
                "run_id": run_id,
                "capability": "vector_rag",
                "stage": "execution",
                "operation": "advisory_retrieval",
                "mode": "advisory_retrieval",
                "reason": f"route_replay_{status}",
                "effect_committed": False,
            },
        )

    # Direct canonical writes have no stored legacy name; this is the path that
    # previously replayed under agent.integration.* and escaped the IDE listener.
    reopened = AgentRunEngine(tmp_path)
    durable = [
        event
        for event in reopened.store.events(run_id)
        if event["event_type"].startswith("agent.integration.")
    ]
    assert len(durable) == 3
    assert all(not event["legacy_type"] for event in durable)
    reopened.store.transition(run_id, "completed")

    client = _client(tmp_path)
    with client.stream(
        "GET",
        f"/edgek/agent-runs/{run_id}/events",
        params={
            "root_path": str(tmp_path),
            "after": 0,
            "follow": "true",
            "projection": "legacy",
        },
        headers={"Accept": "text/event-stream"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    frames = [
        frame
        for frame in body.split("\n\n")
        if "event: agent_run_integration\n" in frame
    ]
    assert len(frames) == 3

    for frame, expected in zip(frames, durable, strict=True):
        event_id = next(
            line.removeprefix("id: ")
            for line in frame.splitlines()
            if line.startswith("id: ")
        )
        assert int(event_id) == expected["sequence"]
        parsed = parse_sse_chunk(frame)
        assert parsed is not None
        event_name, payload = parsed
        assert event_name == "agent_run_integration"
        assert payload["run_id"] == run_id
        assert payload["capability"] == "vector_rag"
        assert canonical_event_type(event_name, payload) == expected["event_type"]
        assert payload["status"] == expected["event_type"].rsplit(".", 1)[-1]


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


def test_agent_coder_sends_governed_transformed_context_to_provider(tmp_path: Path, monkeypatch) -> None:
    from app.routes.ide_routes import agent_run_stream

    (tmp_path / "service.py").write_text(
        "def value():\n    hidden_body = 1\n    return hidden_body\n", encoding="utf-8"
    )
    captured: dict = {}

    class TransformCoordinator:
        def __init__(self, _root):
            self.advisory_context = [{
                "source": "vector_rag",
                "id": "hit-1",
                "content": "advisory",
                "authority": "advisory_only",
            }]

        def prepare(self, **kwargs):
            assert kwargs["source_files"]["service.py"].startswith("def value()")
            return {
                "events": [{
                    "event_type": "agent.integration.fired",
                    "payload": {
                        "capability": "compression.longcodezip",
                        "status": "fired",
                        "stage": "execution",
                        "operation": "context_compression",
                        "mode": "governed_compression",
                        "reason": "fidelity_passed",
                        "authority": "advisory_or_existing_gate_only",
                    },
                }],
                "source_files": {
                    "service.py": "def value():\n    ...  # [beast-lcz: body elided 2 lines]\n"
                },
                "source_context": "def value():\n    ...  # [beast-lcz: body elided 2 lines]\n",
                "diagnostic_context": '{"transformed_diagnostics":true}',
                "repo_map": "service.py:\n  L1 def value()",
            }

    async def fake_stream(_self, prompt, *_args, **kwargs):
        captured["prompt"] = prompt
        captured["options"] = kwargs
        yield {"type": "error", "error": "provider deliberately unavailable in route test"}

    monkeypatch.setattr(agent_run_stream, "CoderIntegrationCoordinator", TransformCoordinator)
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
    assert captured["options"]["context_overrides"] == {
        "service.py": "def value():\n    ...  # [beast-lcz: body elided 2 lines]\n"
    }
    assert "transformed_diagnostics" in captured["prompt"]
    assert "Bounded repository map from RepoRelay" in captured["prompt"]


def test_agent_coder_preflight_includes_quality_cascade(tmp_path: Path, monkeypatch) -> None:
    from app.routes.ide_routes import agent_run_stream
    import os

    (tmp_path / "service.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(agent_run_stream, "CoderIntegrationCoordinator", FakeCoordinator)
    
    # Enable Quality Cascade
    os.environ["BEAST_QUALITY_CASCADE"] = "1"

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
    assert '"capability":"quality_cascade"' in body.replace(" ", "")
    assert '"reason":"quality_cascade_not_passed"' in body.replace(" ", "") or '"reason":"quality_cascade_passed"' in body.replace(" ", "")


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
