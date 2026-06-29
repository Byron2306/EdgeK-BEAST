"""Tests for Phase 6: Capability Crystallization functionality."""

import pytest

from app.kernel.capability.capability_crystallization import (
    CapabilityCrystallizationEngine,
    CrystallizationCandidate,
)


def test_register_shadow_run_creates_candidate():
    """Test that shadow runs register and track candidates."""
    engine = CapabilityCrystallizationEngine()
    
    candidate = engine.register_shadow_run(
        candidate_name="schema_check_v1",
        task_class="schema_validation",
        transform_type="deterministic",
        hidden_test_success=True,
        rollback_success=True,
        behavior_preserved=True,
    )
    
    assert candidate.candidate_name == "schema_check_v1"
    assert candidate.shadow_runs == 1
    assert candidate.hidden_test_successes == 1
    assert candidate.confidence > 0.0


def test_promotion_requires_minimum_shadow_runs():
    """Test that promotion requires at least 3 shadow runs."""
    engine = CapabilityCrystallizationEngine()
    
    # Register only 2 runs (below threshold)
    for _ in range(2):
        engine.register_shadow_run(
            candidate_name="test_cap",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
        )
    
    eligible, reason, _ = engine.check_promotion_eligibility(
        list(engine._candidates.keys())[0]
    )
    
    assert eligible is False
    assert "insufficient_shadow_runs" in reason


def test_promotion_requires_high_success_rates():
    """Test that promotion requires ≥95% success on hidden/rollback/behavior."""
    engine = CapabilityCrystallizationEngine()
    
    # 3 runs: 2 success, 1 failure (66% rate, below 95%)
    for i in range(3):
        engine.register_shadow_run(
            candidate_name="flaky_cap",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=(i < 2),
            rollback_success=(i < 2),
            behavior_preserved=(i < 2),
        )
    
    eligible, reason, _ = engine.check_promotion_eligibility(
        list(engine._candidates.keys())[0]
    )
    
    assert eligible is False
    assert "rate_below_threshold" in reason


def test_promotion_succeeds_with_all_criteria_met():
    """Test that a candidate with all criteria met gets promoted."""
    engine = CapabilityCrystallizationEngine()
    
    # 5 perfect runs (above all thresholds)
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="solid_cap",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
            impact_fingerprint={"state": "active", "confidence": 0.95},
        )
    
    eligible, reason, details = engine.check_promotion_eligibility(
        list(engine._candidates.keys())[0]
    )
    
    assert eligible is True
    assert reason == "eligible_for_promotion"
    assert details["shadow_runs"] == 5


def test_promote_candidate_attaches_impact_fingerprint():
    """Test that promotion creates a proof with attached fingerprint."""
    engine = CapabilityCrystallizationEngine()
    
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="fp_cap",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
            impact_fingerprint={"state": "active", "confidence": 0.92},
        )
    
    proof = engine.promote_candidate(list(engine._candidates.keys())[0])
    
    assert proof is not None
    assert proof.impact_fingerprint is not None
    assert proof.impact_fingerprint.get("state") == "active"
    assert proof.approved_for_enforcement is True


def test_demotion_on_stale_fingerprint():
    """Test that stale fingerprints trigger automatic demotion."""
    engine = CapabilityCrystallizationEngine()
    
    candidate_id = "demote_test"
    engine._candidates[candidate_id] = CrystallizationCandidate(
        candidate_id=candidate_id,
        candidate_name="stale",
        task_class="test",
        transform_type="deterministic",
        promotion_status="promoted",
        shadow_runs=10,
        hidden_test_successes=10,
        rollback_successes=10,
        behavior_preserved_count=10,
        confidence=0.90,
        impact_fingerprint={"state": "shadow_revalidation", "confidence": 0.40},
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    
    decision = engine.check_fingerprint_at_boundary(candidate_id)
    
    assert decision["valid"] is False
    assert engine._candidates[candidate_id].promotion_status == "demoted"


def test_metrics_track_promotion_demotion():
    """Test that metrics correctly track promotion and demotion counts."""
    engine = CapabilityCrystallizationEngine()
    
    # Register and promote one
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="promote_me",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
            impact_fingerprint={"state": "active", "confidence": 0.95},
        )
    
    engine.promote_candidate(list(engine._candidates.keys())[0])
    
    metrics = engine.update_metrics(displaced_tokens=1000, displaced_usd=0.01)
    
    assert metrics.promoted_count == 1
    assert metrics.total_candidates == 1
    assert metrics.total_compute_displaced_tokens == 1000
    assert metrics.deterministic_coverage == 1.0


def test_promotion_fails_closed_without_impact_fingerprint():
    engine = CapabilityCrystallizationEngine()
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="schema_validation",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
        )
    candidate_id = list(engine._candidates)[0]
    eligible, reason, _ = engine.check_promotion_eligibility(candidate_id)
    assert eligible is False
    assert reason == "impact_fingerprint_required"
    assert engine.promote_candidate(candidate_id) is None


def test_crystallized_proof_matches_phase2_candidate_contract():
    engine = CapabilityCrystallizationEngine()
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="schema_validation",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
            impact_fingerprint={"state": "active", "confidence": 0.95},
        )
    proof = engine.promote_candidate(list(engine._candidates)[0])
    assert proof is not None
    assert proof.allowed_transform == proof.candidate_name == "schema_validation"


def test_crystallization_state_persists_and_reloads(tmp_path):
    engine = CapabilityCrystallizationEngine(storage_path=tmp_path)
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="persisted_cap",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
            impact_fingerprint={"state": "active", "confidence": 0.95},
        )
    proof = engine.promote_candidate(list(engine._candidates)[0])
    engine.update_metrics(displaced_tokens=321)

    reloaded = CapabilityCrystallizationEngine(storage_path=tmp_path)

    assert proof is not None
    assert len(reloaded.list_promoted()) == 1
    assert reloaded.to_dict()["metrics"]["total_compute_displaced_tokens"] == 321


def test_runtime_boundary_check_auto_demotes_reloaded_candidate(tmp_path):
    engine = CapabilityCrystallizationEngine(storage_path=tmp_path)
    for _ in range(5):
        engine.register_shadow_run(
            candidate_name="boundary_cap",
            task_class="test",
            transform_type="deterministic",
            hidden_test_success=True,
            rollback_success=True,
            behavior_preserved=True,
            impact_fingerprint={"state": "shadow_revalidation", "confidence": 0.40},
        )
    candidate_id = list(engine._candidates)[0]
    engine._candidates[candidate_id] = CrystallizationCandidate(
        **{**engine._candidates[candidate_id].__dict__, "promotion_status": "promoted"}
    )
    engine._persist_state()

    reloaded = CapabilityCrystallizationEngine(storage_path=tmp_path)
    decision = reloaded.check_fingerprint_at_boundary(candidate_id)

    assert decision["valid"] is False
    assert reloaded.get_candidate(candidate_id).promotion_status == "demoted"


def test_shadow_failures_feed_negative_capability_evidence(tmp_path):
    engine = CapabilityCrystallizationEngine(storage_path=tmp_path)
    for _ in range(3):
        engine.register_shadow_run(
            candidate_name="fragile_transform",
            task_class="code_generation",
            transform_type="deterministic",
            hidden_test_success=False,
            rollback_success=True,
            behavior_preserved=False,
        )

    state = engine.to_dict()
    assert state["outcome_evidence"]["outcomes"] == 3
    assert state["outcome_evidence"]["active"] == 1
    assert state["negative_capabilities"][0]["failure_count"] == 3
