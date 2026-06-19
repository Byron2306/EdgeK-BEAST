import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.canon_registry import CanonRegistry
from app.kernel.promotion_loop import PromotionLoop
from app.kernel.skill_registry import SkillRegistry
from app.kernel.task_envelope import TaskEnvelopeBuilder
from app.kernel.tool_laziness import ToolLazinessLearner
from app.main import app


def test_promotion_check_uses_chronicles_and_tool_laziness(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    task_builder = TaskEnvelopeBuilder(
        policies={"providers": {"huggingface": {"enabled": True}}},
        data_dir=str(tmp_path / "data"),
    )
    for _ in range(2):
        task_builder.diagnose_provider(
            {"provider": "huggingface", "user_request": "Diagnose Hugging Face credential failure"},
            workspace_root=str(tmp_path),
            write_chronicle=True,
        )
    laziness = ToolLazinessLearner(db_path=str(tmp_path / "tool_laziness.db"))
    skill_registry = SkillRegistry(db_path=str(tmp_path / "skills.db"))
    loop = PromotionLoop(
        task_envelope_builder=task_builder,
        canon_registry=CanonRegistry(),
        tool_laziness_learner=laziness,
        skill_registry=skill_registry,
        data_dir=str(tmp_path / "data"),
    )

    candidate = loop.check(
        task_class="provider_debugging",
        provider="huggingface",
        category="auth_or_credentials",
        min_repetitions=2,
        persist=True,
    )

    assert candidate["beast_object_type"] == "promotion_candidate"
    assert candidate["candidate_id"].startswith("promo_")
    assert candidate["eligible"] is True
    assert candidate["approval_status"] == "pending_approval"
    assert candidate["candidate_type"] == "diagnostic_playbook"
    assert candidate["priority_score"] > 0
    assert candidate["promotion_status"] == "candidate"
    assert {"observed", "candidate", "validated", "approved", "promoted", "degraded", "retired"} <= set(candidate["allowed_promotion_statuses"])
    assert candidate["ranking"]["status"] in {"observe", "prioritize", "promote_next"}
    assert "expected_value" in candidate["ranking"]["components"]
    assert candidate["ranking_metrics"]["stable_output_schema"] is True
    assert "failure_rate_after_promotion" in candidate["ranking_metrics"]
    assert candidate["evidence"]["chronicle_count"] == 2
    assert candidate["tool_laziness"]["available"] is True
    assert candidate["tool_laziness"]["samples"] >= 1
    assert loop.get_candidate(candidate["candidate_id"])["candidate_id"] == candidate["candidate_id"]


def test_promotion_requires_eligibility_then_registers_skill(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    task_builder = TaskEnvelopeBuilder(
        policies={"providers": {"huggingface": {"enabled": True}}},
        data_dir=str(tmp_path / "data"),
    )
    for _ in range(2):
        task_builder.diagnose_provider(
            {"provider": "huggingface", "user_request": "Diagnose Hugging Face credential failure"},
            workspace_root=str(tmp_path),
            write_chronicle=True,
        )
    loop = PromotionLoop(
        task_envelope_builder=task_builder,
        canon_registry=CanonRegistry(),
        tool_laziness_learner=ToolLazinessLearner(db_path=str(tmp_path / "tool_laziness.db")),
        skill_registry=SkillRegistry(db_path=str(tmp_path / "skills.db")),
        data_dir=str(tmp_path / "data"),
    )
    candidate = loop.check(
        task_class="provider_debugging",
        provider="huggingface",
        category="auth_or_credentials",
        min_repetitions=2,
    )

    result = loop.promote(candidate=candidate, approved_by="test")

    assert result["promoted"] is True
    assert result["skill"]["category"] == "v2_promotion"
    assert result["skill"]["metadata"]["candidate_id"] == candidate["candidate_id"]
    assert result["candidate"]["promotion_status"] == "promoted"


def test_promotion_check_uses_normalized_insight_for_meta_tool_recipe(tmp_path):
    loop = PromotionLoop(
        canon_registry=CanonRegistry(),
        tool_laziness_learner=ToolLazinessLearner(db_path=str(tmp_path / "tool_laziness.db")),
        data_dir=str(tmp_path / "data"),
    )
    insight_packet = {
        "beast_object_type": "insight_packet",
        "summary": {
            "top_capability_family": "lint_syntax",
            "family_counts": {"lint_syntax": 2},
            "capability_counts": {"linter:py_compile": 2},
        },
        "evidence": [
            {
                "evidence_id": "ev_py_compile",
                "promotion_candidate": True,
                "recommended_capability_id": "linter:py_compile",
                "capability_family": "lint_syntax",
                "priority_score": 0.81,
                "summary": "Repeated Python import failure",
            },
            {
                "evidence_id": "ev_py_compile_2",
                "promotion_candidate": True,
                "recommended_capability_id": "linter:py_compile",
                "capability_family": "lint_syntax",
                "priority_score": 0.72,
            },
        ],
    }

    candidate = loop.check(
        artifacts={"insight_packet": insight_packet},
        min_repetitions=2,
        persist=False,
    )

    assert candidate["eligible"] is True
    assert candidate["candidate_type"] == "meta_tool_recipe"
    assert candidate["priority_score"] >= 0.55
    assert candidate["ranking"]["status"] in {"prioritize", "promote_next"}
    assert candidate["ranking_metrics"]["avoided_cloud_calls"] == 1
    assert candidate["ranking_metrics"]["rollback_or_rejection_count"] == 0
    assert candidate["evidence"]["insight_promotion_count"] == 2
    assert candidate["evidence"]["recommended_capability_id"] == "linter:py_compile"
    assert candidate["promotion_action"]["capability_family"] == "lint_syntax"
    assert any("linter:py_compile" in item for item in candidate["recommendations"])


@pytest.mark.asyncio
async def test_promotion_and_tool_laziness_endpoints_are_available():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        laziness = await client.post(
            "/edgek/tool-laziness/record",
            json={
                "tool_name": "promotion_candidate",
                "scenario": "endpoint:test",
                "called": True,
                "useful": True,
                "tokens_spent": 42,
                "value_score": 0.7,
            },
        )
        candidate = await client.post(
            "/edgek/skills/promotion-check",
            json={"task_class": "provider_debugging", "provider": "huggingface", "min_repetitions": 1, "persist": False},
        )
        listing = await client.get("/edgek/skills/promotion-candidates")

    assert laziness.status_code == 200
    assert "decision" in laziness.json()
    assert candidate.status_code == 200
    assert candidate.json()["beast_object_type"] == "promotion_candidate"
    assert "tool_laziness" in candidate.json()
    assert listing.status_code == 200
    assert "promotion_candidates" in listing.json()
