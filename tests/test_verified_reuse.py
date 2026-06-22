"""Tests for Phase 3: Verified Reuse functionality."""

import pytest

from app.kernel.verified_reuse import VerifiedReuseEngine
from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR
from app.kernel.capability_impact import CapabilityImpactFingerprint
from app.kernel.deterministic_executor import DeterministicTransformExecutor


def test_verified_reuse_engine_matches_task_to_capability():
    """Test that VerifiedReuseEngine can match a task to a promoted capability."""
    engine = VerifiedReuseEngine()
    
    task_envelope = {
        "task_class": "schema_validation",
        "purpose": "schema_validation",
        "metadata": {},
    }
    
    available_caps = [
        {
            "candidate_name": "schema-check-v1",
            "task_class": "schema_validation",
            "confidence": 0.85,
            "impact_fingerprint": {"state": "active", "confidence": 0.85, "fingerprint_hash": "sha256:abc"},
            "visible_tests_equal_or_better": True,
            "hidden_tests_equal_or_better": True,
            "scope_checks_equal_or_better": True,
            "rollback_equal_or_better": True,
            "security_checks_equal_or_better": True,
            "paired_ablation_runs": 3,
            "approved_for_enforcement": True,
        }
    ]
    
    matched, confidence, reason = engine.match_task_to_capability(task_envelope, available_caps)
    
    assert matched is not None
    assert matched["candidate_name"] == "schema-check-v1"
    assert confidence > 0.80
    assert reason in ("exact_task_signature_match", "task_class_match")


def test_verified_reuse_engine_rejects_stale_fingerprint():
    """Test that reuse is rejected when fingerprint requires revalidation."""
    engine = VerifiedReuseEngine()
    
    task_envelope = {"task_class": "test", "metadata": {}}
    available_caps = [
        {
            "candidate_name": "stale-cap",
            "task_class": "test",
            "confidence": 0.50,
            "impact_fingerprint": {"state": "shadow_revalidation", "confidence": 0.40},
            "visible_tests_equal_or_better": True,
            "hidden_tests_equal_or_better": True,
            "scope_checks_equal_or_better": True,
            "rollback_equal_or_better": True,
            "security_checks_equal_or_better": True,
            "paired_ablation_runs": 1,
            "approved_for_enforcement": True,
        }
    ]
    
    decision = engine.compute_reuse_decision(task_envelope, available_caps)
    
    # When fingerprint is stale, no match succeeds, so falls back to cloud_inference
    assert decision["decision"] == "cloud_inference"
    assert decision["verification"]["safe_to_reuse"] is False


def test_verified_reuse_engine_requires_all_checks():
    """Test that reuse requires ALL 5 verification checks + ablation + approval."""
    engine = VerifiedReuseEngine()
    
    task_envelope = {"task_class": "test", "metadata": {}}
    
    # Missing one check
    available_caps = [
        {
            "candidate_name": "incomplete-cap",
            "task_class": "test",
            "confidence": 0.75,
            "impact_fingerprint": {"state": "active", "confidence": 0.75},
            "visible_tests_equal_or_better": True,
            "hidden_tests_equal_or_better": True,
            "scope_checks_equal_or_better": True,
            "rollback_equal_or_better": False,  # Missing this one
            "security_checks_equal_or_better": True,
            "paired_ablation_runs": 1,
            "approved_for_enforcement": True,
        }
    ]
    
    decision = engine.compute_reuse_decision(
        task_envelope, available_caps, current_repo_state=available_caps[0]["impact_fingerprint"]
    )
    
    assert decision["decision"] == "escalate"
    assert "missing_verification" in decision.get("verification", {}).get("reason", "")


def test_verified_reuse_engine_approves_safe_reuse():
    """Test that a fully verified capability is approved for reuse."""
    engine = VerifiedReuseEngine()
    
    task_envelope = {"task_class": "schema_validation", "metadata": {}}
    available_caps = [
        {
            "candidate_name": "verified-schema-v2",
            "task_class": "schema_validation",
            "confidence": 0.92,
            "impact_fingerprint": {"state": "active", "confidence": 0.92, "fingerprint_hash": "sha256:def"},
            "visible_tests_equal_or_better": True,
            "hidden_tests_equal_or_better": True,
            "scope_checks_equal_or_better": True,
            "rollback_equal_or_better": True,
            "security_checks_equal_or_better": True,
            "paired_ablation_runs": 5,
            "approved_for_enforcement": True,
        }
    ]
    
    decision = engine.compute_reuse_decision(
        task_envelope, available_caps, current_repo_state=available_caps[0]["impact_fingerprint"]
    )
    
    assert decision["decision"] == "reuse"
    assert decision["matched_capability"] == "verified-schema-v2"
    assert decision["confidence"] >= 0.60
    assert decision["verification"]["safe_to_reuse"] is True


def test_compute_governor_treats_reuse_names_as_unverified_hypotheses():
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate this schema"}],
        model="m",
        metadata={"reuse_candidates": ["schema-validator-v1"]},
    )
    governor = ComputeGovernor(mode="shadow")  # reuse logic is mode-independent
    plan = governor.build_plan(ir, "provider")
    
    assert "schema-validator-v1" in plan.reuse_candidates
    
    gate = governor.evaluate(plan)
    
    assert gate.candidate_decision == "reuse"
    assert gate.decision == "cloud_inference"
    assert gate.enforced is False
    assert gate.ambiguous is True
    assert "promoted capability lookup" in gate.reason


def test_verified_reuse_requires_current_repository_state():
    engine = VerifiedReuseEngine()
    capability = {
        "candidate_name": "cap",
        "task_class": "test",
        "confidence": 0.9,
        "impact_fingerprint": {"state": "active", "confidence": 0.9},
        "visible_tests_equal_or_better": True,
        "hidden_tests_equal_or_better": True,
        "scope_checks_equal_or_better": True,
        "rollback_equal_or_better": True,
        "security_checks_equal_or_better": True,
        "paired_ablation_runs": 3,
        "approved_for_enforcement": True,
    }
    decision = engine.compute_reuse_decision({"task_class": "test"}, [capability])
    assert decision["decision"] == "escalate"
    assert decision["verification"]["reason"] == "current_repo_state_required"


def _schema_reuse_capability(tmp_path, name="auto-schema-reuse"):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "app" / "contract.py").write_text("SCHEMA = {'type': 'object', 'required': ['ok']}\n")
    (repo / "tests" / "test_contract.py").write_text("def test_contract():\n    assert True\n")
    boundary = {
        "root": str(repo),
        "target_paths": ["app/contract.py"],
        "test_paths": ["tests/test_contract.py"],
        "policy_version": "phase3_test",
        "confidence": 0.95,
    }
    fingerprint = CapabilityImpactFingerprint().build(
        repo,
        target_paths=boundary["target_paths"],
        test_paths=boundary["test_paths"],
        policy_version=boundary["policy_version"],
        confidence=boundary["confidence"],
    )
    work = {"schema_validation": {
        "instance": {"ok": True},
        "schema": {"type": "object", "required": ["ok"]},
        "expect_valid": True,
        "complete_task": True,
    }}
    expected_hash = DeterministicTransformExecutor().execute(["schema_validation"], work)[0].output_sha256
    return {
        "candidate_name": name,
        "task_class": "contract",
        "confidence": 0.95,
        "impact_fingerprint": fingerprint,
        "impact_boundary": boundary,
        "visible_tests_equal_or_better": True,
        "hidden_tests_equal_or_better": True,
        "scope_checks_equal_or_better": True,
        "rollback_equal_or_better": True,
        "security_checks_equal_or_better": True,
        "paired_ablation_runs": 3,
        "approved_for_enforcement": True,
        "deterministic_replay": {
            "candidate_name": "schema_validation",
            "deterministic_work": work,
            "expected_output_sha256": expected_hash,
        },
    }


def test_interceptor_generates_current_impact_fingerprint_at_reuse_boundary(tmp_path):
    capability = _schema_reuse_capability(tmp_path)
    governor = ComputeGovernor(mode="phase3_enforce")
    interceptor = InferenceComputeInterceptor(governor, ComputeLedger(str(tmp_path / "compute.db")))
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema"}],
        model="m",
        metadata={"task_class": "contract", "promoted_capabilities": [capability]},
    )

    active = interceptor.begin(ir, "provider")

    assert active.gate.decision == "reuse"
    assert active.gate.enforced is True
    assert active.verified_reuse_decision["verification"]["safe_to_reuse"] is True
    assert active.verified_reuse_decision["verification"]["impact_decision"]["reusable"] is True


def test_false_reuse_observation_updates_metrics(tmp_path):
    capability = _schema_reuse_capability(tmp_path, name="false-schema-reuse")
    governor = ComputeGovernor(mode="phase3_enforce")
    interceptor = InferenceComputeInterceptor(governor, ComputeLedger(str(tmp_path / "compute.db")))
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema"}],
        model="m",
        metadata={"task_class": "contract", "promoted_capabilities": [capability]},
    )

    active = interceptor.begin(ir, "provider")
    response = interceptor.reuse_response(active)
    receipt = interceptor.complete(
        active,
        response=response,
        status="reuse_succeeded",
        provider_execution_requested=False,
        behavior_preserved=False,
    )
    metrics = governor.reuse_engine.metrics.to_dict()

    assert receipt.gate_decision == "reuse"
    assert active.reuse_observation["false_reuse"] is True
    assert metrics["reuse_approved"] == 1
    assert metrics["false_reuse_count"] == 1
    assert metrics["false_reuse_rate"] == 1.0
