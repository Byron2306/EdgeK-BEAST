from dataclasses import replace

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ir import DeterministicDisplacementProof
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.governance.deterministic_executor import DeterministicTransformExecutor
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR


def _proof(**overrides):
    proof = DeterministicDisplacementProof(
        candidate_name="schema_validation",
        task_class="contract",
        risk_class="low",
        allowed_transform="schema_validation",
        verifier_command="validate_json_schema",
        visible_tests_equal_or_better=True,
        hidden_tests_equal_or_better=True,
        scope_checks_equal_or_better=True,
        rollback_equal_or_better=True,
        security_checks_equal_or_better=True,
        paired_ablation_runs=3,
        confidence=0.95,
        approved_for_enforcement=True,
        policy_version="phase2_v1",
        impact_fingerprint={"state": "active", "reusable": True},
        proof_id="proof_test",
    )
    return replace(proof, **overrides)


def _ir(metadata=None):
    return EdgeKIR(
        messages=[{"role": "user", "content": "Validate the JSON schema contract"}],
        model="test-model",
        metadata={"task_class": "contract", **(metadata or {})},
    )


def test_explicit_phase2_mode_overrides_shadow_environment(monkeypatch):
    monkeypatch.setenv("BEAST_COMPUTE_GOVERNOR_MODE", "shadow")
    assert ComputeGovernor(mode="phase2_enforce").mode == "phase2_enforce"
    assert ComputeGovernor().mode == "shadow"


def test_declared_displacement_without_proof_falls_back_to_cloud():
    governor = ComputeGovernor(mode="phase2_enforce")
    plan = governor.build_plan(
        _ir({"enforceable_displacements": ["schema_validation"]}), "provider"
    )
    gate = governor.evaluate(plan)

    assert plan.enforceable_displacements == []
    assert gate.decision == "cloud_inference"
    assert gate.enforced is False
    assert gate.selected_rung == "selected_provider"


def test_valid_proof_is_eligible_but_preserves_provider_without_executor():
    governor = ComputeGovernor(mode="phase2_enforce")
    plan = governor.build_plan(_ir({"displacement_proofs": [_proof().to_dict()]}), "provider")
    gate = governor.evaluate(plan)

    assert plan.enforceable_displacements == ["schema_validation"]
    assert len(plan.displacement_proofs) == 1
    assert gate.candidate_decision == "deterministic"
    assert gate.decision == "cloud_inference"
    assert gate.enforced is False
    assert gate.selected_rung == "selected_provider"
    assert "executor is unavailable" in gate.reason


def test_invalid_empty_or_low_confidence_proof_fails_closed_with_typed_gate():
    governor = ComputeGovernor(mode="phase2_enforce")
    for proof_payload in ([], [_proof(confidence=0.70).to_dict()]):
        plan = governor.build_plan(_ir({"displacement_proofs": proof_payload}), "provider")
        gate = governor.evaluate(plan)
        assert gate.decision == "cloud_inference"
        assert gate.enforced is False
        assert gate.allowed is True


def test_stale_impact_fingerprint_cannot_enforce():
    stale = _proof(impact_fingerprint={"state": "shadow_revalidation", "reusable": False})
    governor = ComputeGovernor(mode="phase2_enforce")
    gate = governor.evaluate(
        governor.build_plan(_ir({"displacement_proofs": [stale.to_dict()]}), "provider")
    )
    assert gate.decision == "cloud_inference"
    assert gate.enforced is False


def test_proof_for_undetected_candidate_cannot_enforce():
    governor = ComputeGovernor(mode="phase2_enforce")
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Choose an architecture"}],
        model="test-model",
        metadata={"task_class": "contract", "displacement_proofs": [_proof().to_dict()]},
    )
    plan = governor.build_plan(ir, "provider")
    gate = governor.evaluate(plan)
    assert plan.enforceable_displacements == []
    assert gate.decision == "cloud_inference"
    assert gate.enforced is False


def test_verified_complete_transform_can_use_deterministic_branch(tmp_path):
    executor = DeterministicTransformExecutor()
    work = {
        "schema_validation": {
            "instance": {"ok": True},
            "schema": {"type": "object", "required": ["ok"]},
            "expect_valid": True,
            "complete_task": True,
        }
    }
    work["schema_validation"]["expected_output_sha256"] = executor.execute(
        ["schema_validation"], work
    )[0].output_sha256
    proof = _proof(expected_output_sha256=work["schema_validation"]["expected_output_sha256"])
    ir = _ir({"displacement_proofs": [proof.to_dict()], "deterministic_work": work})
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase2_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
        executor,
    )

    active = interceptor.begin(ir, "provider")
    response = interceptor.deterministic_response(active)

    assert active.gate.decision == "deterministic"
    assert active.gate.enforced is True
    assert active.gate.selected_rung == "deterministic_transform"
    assert interceptor.should_call_provider(active) is False
    assert response["candidate"] == "schema_validation"
    assert response["result"] == {"valid": True, "error_paths": []}


def test_complete_transform_without_calibrated_agreement_preserves_provider(tmp_path):
    work = {
        "schema_validation": {
            "instance": {"ok": True},
            "schema": {"type": "object"},
            "complete_task": True,
            "expected_output_sha256": "sha256:wrong",
        }
    }
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase2_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
    )
    active = interceptor.begin(
        _ir({"displacement_proofs": [_proof().to_dict()], "deterministic_work": work}),
        "provider",
    )
    assert active.gate.decision == "cloud_inference"
    assert active.gate.enforced is False
    assert interceptor.should_call_provider(active) is True


def test_request_hash_cannot_replace_proof_bound_output_hash(tmp_path):
    executor = DeterministicTransformExecutor()
    work = {"schema_validation": {
        "instance": {"ok": True}, "schema": {"type": "object"},
        "expect_valid": True, "complete_task": True,
    }}
    work["schema_validation"]["expected_output_sha256"] = executor.execute(["schema_validation"], work)[0].output_sha256
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase2_enforce"), ComputeLedger(str(tmp_path / "compute.db")), executor
    )
    active = interceptor.begin(
        _ir({"displacement_proofs": [_proof().to_dict()], "deterministic_work": work}), "provider"
    )
    assert active.deterministic_shadow_results[0].behavior_preserved is True
    assert active.gate.enforced is False
    assert interceptor.should_call_provider(active) is True
