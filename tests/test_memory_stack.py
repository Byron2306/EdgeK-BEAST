import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.memory_stack import MemoryStack
from app.kernel.runtime import RuntimeGovernor
from app.kernel.task_envelope import TaskEnvelopeBuilder
from app.main import app


def test_memory_stack_reports_l0_to_l4(tmp_path):
    runtime = RuntimeGovernor(
        policies={"meta_rules": {"runtime_provider_timeout_seconds": 10}},
        db_path=str(tmp_path / "runtime.db"),
    )
    builder = TaskEnvelopeBuilder(
        policies={"providers": {"huggingface": {"enabled": True}}},
        runtime_governor=runtime,
        data_dir=str(tmp_path / "data"),
    )
    builder.provider_diagnostic_route_card("huggingface")
    builder.diagnose_provider(
        {"provider": "huggingface", "user_request": "Diagnose Hugging Face"},
        workspace_root=str(tmp_path),
        write_chronicle=True,
    )

    stack = MemoryStack(
        policies={
            "meta_rules": {"daily_max_requests": 1000},
            "providers": {"huggingface": {"enabled": True}},
            "mcp_server_classes": {"local_read_only": {}},
        },
        runtime_governor=runtime,
        task_envelope_builder=builder,
    ).state()

    assert stack["beast_object_type"] == "memory_stack"
    assert set(stack["layers"]) == {"L0", "L1", "L2", "L3", "L4"}
    assert stack["layers"]["L0"]["name"] == "Meta Rules"
    assert stack["layers"]["L1"]["name"] == "Insight Index"
    assert stack["layers"]["L4"]["counts"]["chronicles"] == 1
    assert "workspace graph nodes/edges" in stack["retrieval_views"]


@pytest.mark.asyncio
async def test_memory_stack_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/edgek/memory/stack")

    assert response.status_code == 200
    payload = response.json()
    assert payload["layers"]["L0"]["scope"] == "Immutable Governance"
    assert payload["layers"]["L2"]["name"] == "Workspace Graph"
    assert "truth_stores" in payload
