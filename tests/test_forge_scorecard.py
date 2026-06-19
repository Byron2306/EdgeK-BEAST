import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.forge_scorecard import ForgeScorecardBuilder
from app.main import app


def test_forge_scorecard_constrains_broad_provider_router_refactor():
    builder = ForgeScorecardBuilder()
    envelope = {
        "task_id": "tsk_forge_router",
        "task_class": "refactor_request",
        "risk_level": "medium",
        "intent": "Refactor the provider router and adapter compatibility layer.",
        "inputs": {"user_request": "Refactor app/adapters/huggingface_adapter.py and app/main.py provider routing."},
        "success_criteria": ["router behavior preserved", "provider tests pass"],
    }
    context_packet = {
        "packet_id": "pkt_router",
        "route_id": "route_quality_refactor_request",
        "handoff_hash": "sha256:test",
        "included_evidence": [
            {"kind": "file_snippet", "source": "app/adapters/huggingface_adapter.py"},
            {"kind": "file_snippet", "source": "app/main.py"},
        ],
        "excluded_evidence": [],
        "packet_stats": {"included_count": 2},
    }

    scorecard = builder.build(envelope, context_packet=context_packet)

    assert scorecard["beast_object_type"] == "forge_scorecard"
    assert scorecard["scorecard_id"].startswith("forge_")
    assert scorecard["scorecard_hash"].startswith("sha256:")
    assert scorecard["compatibility_tests_required"] is True
    assert scorecard["minimal_patch_first"] is True
    assert scorecard["decision"] in ("proceed_with_constraints", "approval_required")
    assert any("compatibility tests" in item for item in scorecard["recommendations"])


def test_forge_scorecard_allows_small_bounded_fix():
    builder = ForgeScorecardBuilder()
    envelope = {
        "task_id": "tsk_forge_small",
        "task_class": "small_patch",
        "risk_level": "low",
        "intent": "Fix a typo in docs/BEAST_V2_ROADMAP.md.",
        "inputs": {"user_request": "Fix docs/BEAST_V2_ROADMAP.md typo."},
        "success_criteria": ["documentation updated", "no code behavior changes"],
    }
    context_packet = {
        "packet_id": "pkt_docs",
        "handoff_hash": "sha256:test",
        "included_evidence": [{"kind": "file_snippet", "source": "docs/BEAST_V2_ROADMAP.md"}],
        "excluded_evidence": [],
        "packet_stats": {"included_count": 1},
    }

    scorecard = builder.build(envelope, context_packet=context_packet)

    assert scorecard["decision"] == "proceed"
    assert scorecard["compatibility_tests_required"] is False
    assert scorecard["required_gates"]["human_approval_required"] is False


@pytest.mark.asyncio
async def test_forge_scorecard_endpoint_builds_context_when_needed():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/forge/scorecard",
            json={
                "user_request": "Refactor app/adapters/huggingface_adapter.py provider route safely",
                "task_class": "refactor_request",
                "run_quality": False,
            },
        )

    assert response.status_code == 200
    scorecard = response.json()
    assert scorecard["beast_object_type"] == "forge_scorecard"
    assert scorecard["scorecard_hash"].startswith("sha256:")
    assert scorecard["context_packet_id"].startswith("pkt_")
    assert scorecard["compatibility_tests_required"] is True
