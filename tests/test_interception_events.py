import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.insight_compiler import InsightCompiler
from app.kernel.interception_events import InterceptionEventFactory
from app.main import app


def test_interception_event_factory_scores_runtime_failure():
    factory = InterceptionEventFactory()

    evidence = factory.from_runtime_attempt({
        "attempt_id": "att_1",
        "provider": "huggingface",
        "model": "local",
        "session_id": "sess",
        "status": "failed",
        "duration_ms": 1800,
        "error_message": "timeout",
    })

    assert evidence["source_type"] == "interception_event"
    assert evidence["severity"] == "high"
    assert evidence["recommended_capability_id"] == "workflow:quality_cascade"
    assert "high_latency" in evidence["signals"]
    assert evidence["score_breakdown"]["score_schema_version"] == "1.0"


def test_interception_event_factory_maps_routing_and_broker_families():
    factory = InterceptionEventFactory()
    routing = factory.build({"event_kind": "routing", "route_id": "route_1", "summary": "fallback selected"})
    broker = factory.build({"event_kind": "broker", "summary": "MCP approval required"})

    assert routing["capability_family"] == "routing"
    assert routing["recommended_capability_id"] == "route:route_cards"
    assert broker["capability_family"] == "tool_bus"
    assert broker["recommended_capability_id"] == "tool:mcp_evaluate"
    assert routing["interception_layer"] == "L3"
    assert broker["interception_layer"] == "L2"


def test_interception_event_factory_exposes_layer_mesh_and_l4_range():
    factory = InterceptionEventFactory()
    mesh = factory.mesh()
    proxy = factory.build({"event_kind": "proxy_request", "summary": "gateway proxy observed"})
    shell = factory.build({"event_kind": "shell_command", "summary": "dry-run command intercepted"})
    packet = factory.build({"event_kind": "packet_observation", "summary": "large packet retained as forensic signal"})

    assert set(mesh["layers"]) == {"L1", "L2", "L3", "L4"}
    assert mesh["event_layers"]["proxy_request"] == "L1"
    assert mesh["event_layers"]["shell_command"] == "L2"
    assert mesh["event_layers"]["packet_observation"] == "L4"
    assert proxy["interception_layer"] == "L1"
    assert shell["interception_layer"] == "L2"
    assert packet["interception_layer"] == "L4"
    assert "intercept_layer_l4" in packet["signals"]
    assert {"type": "interception_layer", "id": "L4"} in packet["relationships"]


def test_insight_compiler_accepts_interception_event_live_evidence(tmp_path):
    evidence = InterceptionEventFactory().build({
        "event_kind": "circuit",
        "provider": "huggingface",
        "status": "rejected",
        "summary": "Circuit breaker open",
    })

    packet = InsightCompiler(data_dir=str(tmp_path)).compile(
        objective="provider circuit failure",
        current_task={
            "objective": "Diagnose circuit",
            "scope": "provider",
            "success_criteria": ["rank interception evidence"],
        },
        evidence_records=[evidence],
    )

    assert packet["evidence"][0]["source_type"] == "interception_event"
    assert packet["evidence"][0]["capability_family"] == "diagnostics"


@pytest.mark.asyncio
async def test_interception_event_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/interception/event",
            json={"event_kind": "throttle", "provider": "openai", "status": "rejected"},
        )
        mesh = await client.get("/edgek/interception/mesh")
        transparent = await client.get("/edgek/interception/transparent/state")

    assert response.status_code == 200
    assert response.json()["source_type"] == "interception_event"
    assert response.json()["recommended_capability_id"] == "workflow:provider_diagnostic"
    assert mesh.status_code == 200
    assert mesh.json()["beast_object_type"] == "interception_layer_mesh"
    assert transparent.status_code == 200
    assert transparent.json()["beast_object_type"] == "transparent_interception_state"
    assert "/tool-calls/*" in transparent.json()["routes"]["tool_calls"]
