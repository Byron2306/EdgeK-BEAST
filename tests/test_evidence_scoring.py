from app.kernel.storage.evidence_scoring import EvidenceScorer
from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app


def test_evidence_scorer_returns_explainable_score_breakdown():
    scorer = EvidenceScorer()

    result = scorer.score(
        relevance=0.9,
        confidence=0.85,
        severity="high",
        freshness=0.8,
        repeat_count=3,
        verification_strength=0.75,
        blast_radius=0.2,
    )

    assert 0.0 <= result.expected_value <= 1.0
    assert 0.0 <= result.priority_score <= 1.0
    assert 0.0 <= result.failure_probability <= 1.0
    assert 0.0 <= result.uncertainty <= 1.0
    assert result.promotion_candidate is True
    assert result.learning_status == "promotion_candidate"
    assert result.breakdown["score_schema_version"] == "1.0"
    assert "expected_value_components" in result.breakdown
    assert "failure_probability_components" in result.breakdown
    assert result.breakdown["local_scores"]["failure_probability"] == result.failure_probability
    assert "priority_components" in result.breakdown
    assert result.breakdown["priority_components"]["repeat_bonus"] > 0


def test_evidence_scorer_keeps_low_value_evidence_observable():
    scorer = EvidenceScorer()

    result = scorer.score(
        relevance=0.1,
        confidence=0.2,
        severity="info",
        freshness=0.2,
        repeat_count=1,
        verification_strength=0.1,
        blast_radius=0.9,
    )

    assert result.promotion_candidate is False
    assert result.learning_status == "observe"
    assert result.priority_score < 0.55


def test_evidence_scorer_accepts_policy_threshold_overrides():
    scorer = EvidenceScorer({
        "evidence_scoring": {
            "thresholds": {
                "promotion_repeat_count": 3,
                "promotion_expected_value": 0.9,
                "promotion_priority_score": 0.95,
            },
            "priority_weights": {
                "expected_value": 4.0,
            },
        }
    })

    result = scorer.score(
        relevance=0.7,
        confidence=0.7,
        severity="medium",
        freshness=0.7,
        repeat_count=2,
        verification_strength=0.6,
        blast_radius=0.3,
    )

    assert result.breakdown["thresholds"]["promotion_repeat_count"] == 3.0
    assert result.breakdown["priority_weights"]["expected_value"] == 4.0
    assert result.promotion_candidate is False


@pytest.mark.asyncio
async def test_evidence_score_endpoint_returns_breakdown():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/evidence/score",
            json={
                "relevance": 0.8,
                "confidence": 0.8,
                "severity": "high",
                "freshness": 0.9,
                "repeat_count": 2,
                "verification_strength": 0.7,
                "blast_radius": 0.2,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["promotion_candidate"] is True
    assert "failure_probability" in payload
    assert "uncertainty" in payload
    assert payload["breakdown"]["score_schema_version"] == "1.0"
