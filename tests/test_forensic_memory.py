import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.storage.forensic_memory import ForensicMemory
from app.kernel.networking.interception_events import InterceptionEventFactory
from app.kernel.governance.runtime import RuntimeGovernor
from app.main import app


def test_forensic_memory_appends_and_queries_with_metadata_first(tmp_path):
    memory = ForensicMemory(str(tmp_path / "forensic_l4.db"))
    evidence = InterceptionEventFactory().build({
        "event_kind": "circuit",
        "provider": "huggingface",
        "status": "open",
        "summary": "Circuit opened after timeout",
    })

    written = memory.append({"event_kind": "circuit", "provider": "huggingface", "status": "open"}, evidence)
    result = memory.query("timeout circuit", event_kind="circuit", layer="L3", provider="huggingface")

    assert written["written"] is True
    assert memory.state()["retrieval"]["source_of_truth"] == "sqlite"
    assert memory.state()["layers"]["L3"] == 1
    assert result["retrieval_mode"] == "lexical_fallback"
    assert result["vector_available"] is False
    assert result["results"][0]["provider"] == "huggingface"
    assert result["results"][0]["layer"] == "L3"
    assert result["results"][0]["lexical_score"] > 0


def test_runtime_governor_emits_forensic_events_for_rejections_and_failures(tmp_path):
    memory = ForensicMemory(str(tmp_path / "forensic_l4.db"))
    governor = RuntimeGovernor(
        policies={
            "meta_rules": {
                "stasis_wall_enabled": True,
                "stasis_wall_max_concurrent": 1,
                "circuit_breaker_enabled": True,
                "circuit_breaker_failure_threshold": 1,
            }
        },
        db_path=str(tmp_path / "runtime.db"),
        forensic_memory=memory,
    )

    first = governor.begin_execution("openai", "model")
    rejected = governor.begin_execution("openai", "model")
    governor.complete_execution(first.attempt_id, "openai", success=False, error_message="boom timeout")
    blocked = governor.begin_execution("openai", "model")
    query = memory.query("timeout circuit stasis", provider="openai", limit=10)

    assert rejected.allowed is False
    assert blocked.allowed is False
    assert memory.state()["events"] >= 3
    assert {item["event_kind"] for item in query["results"]} >= {"throttle", "error", "circuit"}


@pytest.mark.asyncio
async def test_forensic_memory_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        event = await client.post(
            "/edgek/interception/event",
            json={
                "event_kind": "routing",
                "route_id": "route_test",
                "summary": "fallback route selected",
                "persist": True,
            },
        )
        state = await client.get("/edgek/forensics/l4/state")
        mesh = await client.get("/edgek/interception/mesh")
        query = await client.post("/edgek/forensics/l4/query", json={"query": "fallback route", "event_kind": "routing", "layer": "L3"})

    assert event.status_code == 200
    assert event.json()["forensic_memory"]["written"] is True
    assert state.status_code == 200
    assert state.json()["retrieval"]["lexical_fallback"] is True
    assert mesh.status_code == 200
    assert "L4" in mesh.json()["layers"]
    assert query.status_code == 200
    assert query.json()["results"]
    assert query.json()["results"][0]["layer"] == "L3"
