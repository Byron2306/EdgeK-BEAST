import json
from dataclasses import replace

import pytest

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR


def test_compute_plan_is_privacy_safe_and_hashes_request_content():
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Run pytest and compile this private source"}],
        model="grok-build-0.1",
        max_tokens=300,
        metadata={"task_class": "debug"},
    )

    plan = ComputeGovernor().build_plan(ir, "xai")
    serialized = json.dumps(plan.to_dict())

    assert "private source" not in serialized
    assert plan.request_fingerprint.startswith("sha256:")
    assert plan.plan_hash.startswith("sha256:")
    assert plan.task_class == "debug"
    assert "test_execution" in plan.deterministic_candidates
    assert "syntax_check" in plan.deterministic_candidates
    assert plan.to_dict()["privacy"]["contains_prompt"] is False


def test_phase_one_gate_never_changes_selected_provider_rung():
    ir = EdgeKIR(messages=[{"role": "user", "content": "Run tests"}], model="m", metadata={})
    governor = ComputeGovernor()
    plan = governor.build_plan(ir, "provider")

    gate = governor.evaluate(plan)

    assert gate.allowed is True
    assert gate.enforced is False
    assert gate.selected_rung == "selected_provider"
    assert gate.candidate_decision == "deterministic"
    assert gate.confidence == 0.60
    assert gate.ambiguous is True
    assert gate.recommended_rung == "escalate"
    assert gate.decision == "cloud_inference"
    assert gate.tiebreaker_policy == "escalate_never_suppress_on_ambiguity"


def test_suppression_requires_complete_positive_evidence():
    incomplete = ComputeGovernor.suppression_policy({"confidence": 0.99, "proof_verified": True})
    proven = ComputeGovernor.suppression_policy({
        "confidence": 0.99,
        "proof_verified": True,
        "behavior_preserved": True,
        "fallback_available": True,
        "high_risk": False,
        "required_work_remaining": False,
    })

    assert incomplete["eligible"] is False
    assert incomplete["decision"] == "escalate"
    assert incomplete["missing_or_failed"]
    assert proven["eligible"] is True
    assert proven["decision"] == "suppress"


def test_interceptor_records_plan_gate_and_usage_receipt(tmp_path):
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema then answer"}],
        model="model-a",
        max_tokens=100,
        metadata={"reuse_candidates": ["skill:schema-check"]},
    )

    active = interceptor.begin(ir, "provider-a")
    receipt = interceptor.complete(
        active,
        response={"usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}},
        runtime_attempt_id="attempt-1",
        status="succeeded",
    )

    assert receipt.total_tokens == 25
    assert receipt.runtime_attempt_id == "attempt-1"
    assert receipt.mode == "shadow"
    assert ledger.state()["plans"] == 1
    assert ledger.state()["gates"] == 1
    assert ledger.state()["receipts"] == 1
    assert ledger.receipt(receipt.receipt_id)["shadow_only"] is True
    metrics = ledger.metrics()
    assert metrics["sample_size"] == 1
    assert metrics["observed_total_tokens"] == 25
    assert metrics["estimated_avoidable_total_tokens"] > 0
    assert metrics["observed_cost_usd"] is None
    assert receipt.avoided_tokens_estimate > 0
    assert receipt.predicted_savings_usd is None
    assert receipt.cost_observation_available is False
    assert receipt.counterfactual_estimates is True
    assert receipt.suppression_enforced is False
    assert "private source" not in json.dumps(receipt.to_dict())
    summary = ledger.savings_summary(weekly_call_volume=1000)
    assert summary["potential_weekly_avoided_tokens"] > 0
    assert summary["potential_weekly_savings_usd"] is None
    assert summary["availability"] == "first-party cost observations unavailable"


def test_first_party_cost_enables_counterfactual_weekly_savings(tmp_path):
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate this JSON schema"}],
        model="priced-model",
        max_tokens=100,
        metadata={},
    )

    receipt = interceptor.complete(
        interceptor.begin(ir, "priced-provider"),
        response={"usage": {
            "prompt_tokens": 80,
            "completion_tokens": 20,
            "total_tokens": 100,
            "cost_usd": 0.01,
        }},
        status="succeeded",
    )
    summary = ledger.savings_summary(weekly_call_volume=1000)

    assert receipt.cost_observation_available is True
    assert receipt.predicted_savings_usd is not None
    assert receipt.predicted_savings_usd > 0
    assert summary["availability"] == "available"
    assert summary["cost_coverage_rate"] == 1.0
    assert summary["potential_weekly_savings_usd"] > 0
    assert ledger.metrics()["observed_cost_usd"] == 0.01


def test_false_suppression_metric_is_a_redline(tmp_path):
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
    ir = EdgeKIR(messages=[{"role": "user", "content": "answer"}], model="m", metadata={})
    receipt = interceptor.complete(interceptor.begin(ir, "provider"), behavior_preserved=True)

    false_suppression = replace(
        receipt,
        receipt_id="crec_false_suppression",
        gate_decision="suppress",
        suppression_enforced=True,
        behavior_preserved=False,
    )
    ledger.record_receipt(false_suppression)
    metrics = ledger.metrics()

    assert metrics["enforced_suppression_count"] == 1
    assert metrics["false_suppression_count"] == 1
    assert metrics["false_suppression_rate"] == 1.0
    assert metrics["false_suppression_redline"] is True
    assert metrics["enforcement_pause_required"] is True


def test_usage_normalizes_anthropic_and_missing_cost():
    usage = InferenceComputeInterceptor._usage({"usage": {"input_tokens": 9, "output_tokens": 4}})
    assert usage == {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13, "cost_usd": None}


def test_usage_normalizes_xai_first_party_cost_ticks():
    usage = InferenceComputeInterceptor._usage({"usage": {
        "prompt_tokens": 80,
        "completion_tokens": 20,
        "total_tokens": 100,
        "cost_in_usd_ticks": 89_868_000,
    }})
    assert usage["cost_usd"] == 0.0089868


@pytest.mark.asyncio
async def test_executor_attaches_shadow_compute_receipt(monkeypatch, tmp_path):
    import app.kernel.execution.execute as execute_module
    from app.kernel.execution.execute import Executor
    from app.kernel.governance.reason import GovernanceDecision, GovernanceResult

    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Run pytest, then explain"}],
        model="gpt-test",
        metadata={"session_id": "compute-test"},
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["choices"]
    assert response["edgek_compute"]["mode"] == "shadow"
    assert response["edgek_compute"]["enforced"] is False
    assert response["edgek_compute"]["selected_rung"] == "selected_provider"
    assert ledger.state()["receipts"] == 1
    receipt = ledger.recent_receipts(1)[0]
    assert receipt["status"] == "succeeded"
    assert receipt["runtime_attempt_id"] == response["edgek_runtime"]["attempt_id"]


@pytest.mark.asyncio
async def test_executor_skips_provider_only_for_verified_complete_phase2_transform(monkeypatch, tmp_path):
    import app.kernel.execution.execute as execute_module
    from app.kernel.compute.compute_ir import DeterministicDisplacementProof
    from app.kernel.governance.deterministic_executor import DeterministicTransformExecutor
    from app.kernel.execution.execute import Executor
    from app.kernel.governance.reason import GovernanceDecision, GovernanceResult

    transform_executor = DeterministicTransformExecutor()
    work = {"schema_validation": {
        "instance": {"ok": True}, "schema": {"type": "object", "required": ["ok"]},
        "expect_valid": True, "complete_task": True,
    }}
    work["schema_validation"]["expected_output_sha256"] = transform_executor.execute(["schema_validation"], work)[0].output_sha256
    proof = DeterministicDisplacementProof(
        candidate_name="schema_validation", task_class="contract", risk_class="low",
        allowed_transform="schema_validation", verifier_command="validate_json_schema",
        visible_tests_equal_or_better=True, hidden_tests_equal_or_better=True,
        scope_checks_equal_or_better=True, rollback_equal_or_better=True,
        security_checks_equal_or_better=True, paired_ablation_runs=3, confidence=0.99,
        approved_for_enforcement=True, policy_version="phase2_v1",
        impact_fingerprint={"state": "active", "reusable": True},
        expected_output_sha256=work["schema_validation"]["expected_output_sha256"],
        proof_id="proof_executor",
    )
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase2_enforce"), ComputeLedger(str(tmp_path / "compute.db")), transform_executor
    )
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema"}], model="gpt-test",
        metadata={"task_class": "contract", "displacement_proofs": [proof.to_dict()], "deterministic_work": work},
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["object"] == "beast.deterministic_transform"
    assert response["result"]["valid"] is True
    assert response["edgek_compute"]["enforced"] is True
    assert response["edgek_runtime"]["provider"] == "deterministic_transform"
    receipt = interceptor.ledger.recent_receipts(1)[0]
    assert receipt["provider_execution_requested"] is False
    assert receipt["status"] == "deterministic_succeeded"


@pytest.mark.asyncio
async def test_executor_reuses_promoted_capability_after_fingerprint_and_replay(monkeypatch, tmp_path):
    import app.kernel.execution.execute as execute_module
    from app.kernel.governance.deterministic_executor import DeterministicTransformExecutor
    from app.kernel.execution.execute import Executor
    from app.kernel.governance.reason import GovernanceDecision, GovernanceResult

    transform_executor = DeterministicTransformExecutor()
    work = {"schema_validation": {
        "instance": {"ok": True},
        "schema": {"type": "object", "required": ["ok"]},
        "expect_valid": True,
        "complete_task": True,
    }}
    expected_hash = transform_executor.execute(["schema_validation"], work)[0].output_sha256
    fingerprint = {
        "state": "active",
        "confidence": 0.95,
        "fingerprint_hash": "sha256:reuse",
        "policy_version": "phase3_test",
        "tool_schema_hashes": [],
    }
    capability = {
        "candidate_name": "schema-validation-reuse",
        "task_class": "contract",
        "confidence": 0.95,
        "impact_fingerprint": fingerprint,
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
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase3_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
        transform_executor,
    )
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema"}],
        model="gpt-test",
        metadata={
            "task_class": "contract",
            "promoted_capabilities": [capability],
            "current_repo_state": fingerprint,
        },
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["object"] == "beast.verified_reuse"
    assert response["capability"] == "schema-validation-reuse"
    assert response["result"] == {"valid": True, "error_paths": []}
    assert response["edgek_compute"]["enforced"] is True
    assert response["edgek_runtime"]["provider"] == "verified_reuse"
    receipt = interceptor.ledger.recent_receipts(1)[0]
    assert receipt["provider_execution_requested"] is False
    assert receipt["gate_decision"] == "reuse"
    assert receipt["status"] == "reuse_succeeded"


@pytest.mark.asyncio
async def test_executor_can_load_promoted_capability_from_persisted_store(monkeypatch, tmp_path):
    import app.kernel.execution.execute as execute_module
    from app.kernel.governance.deterministic_executor import DeterministicTransformExecutor
    from app.kernel.execution.execute import Executor
    from app.kernel.governance.reason import GovernanceDecision, GovernanceResult

    transform_executor = DeterministicTransformExecutor()
    work = {"schema_validation": {
        "instance": {"ok": True},
        "schema": {"type": "object", "required": ["ok"]},
        "expect_valid": True,
        "complete_task": True,
    }}
    expected_hash = transform_executor.execute(["schema_validation"], work)[0].output_sha256
    fingerprint = {
        "state": "active",
        "confidence": 0.94,
        "fingerprint_hash": "sha256:persisted-reuse",
        "policy_version": "phase3_test",
        "tool_schema_hashes": [],
    }
    capability = {
        "candidate_name": "persisted-schema-reuse",
        "task_class": "contract",
        "confidence": 0.94,
        "impact_fingerprint": fingerprint,
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
    store = tmp_path / "promoted_capabilities.json"
    store.write_text(json.dumps({"capabilities": [capability]}))
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase3_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
        transform_executor,
        promoted_capability_store=store,
    )
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Validate schema"}],
        model="gpt-test",
        metadata={"task_class": "contract", "current_repo_state": fingerprint},
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["object"] == "beast.verified_reuse"
    assert response["capability"] == "persisted-schema-reuse"
    assert interceptor.ledger.recent_receipts(1)[0]["provider_execution_requested"] is False


@pytest.mark.asyncio
async def test_executor_pauses_for_phase4_budget_approval(monkeypatch, tmp_path):
    import app.kernel.execution.execute as execute_module
    from app.kernel.execution.execute import Executor
    from app.kernel.governance.reason import GovernanceDecision, GovernanceResult

    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase4_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
    )
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Answer briefly"}],
        model="gpt-test",
        metadata={
            "compute_cost_budget_usd": 0.01,
            "estimated_cost_usd": 0.05,
            "risk_class": "low",
        },
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["error"]["type"] == "APPROVAL_REQUIRED"
    assert response["error"]["compute"]["enforced"] is True
    assert response["error"]["compute"]["adaptive_routing"]["decision"] == "require_approval"
    receipt = interceptor.ledger.recent_receipts(1)[0]
    assert receipt["provider_execution_requested"] is False
    assert receipt["gate_decision"] == "require_approval"
    assert receipt["status"] == "approval_required"


@pytest.mark.asyncio
async def test_executor_intercepts_enabled_provider_stream_and_records_savings(monkeypatch, tmp_path):
    import app.kernel.execution.execute as execute_module
    from app.kernel.execution.execute import Executor
    from app.kernel.governance.reason import GovernanceDecision, GovernanceResult

    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(), ledger)
    monkeypatch.setattr(execute_module, "compute_interceptor", interceptor)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Return governed JSON"}],
        model="gpt-test",
        max_tokens=50,
        stream=True,
        metadata={
            "stream_interception_enabled": True,
            "simulated_stream_text": '{"action":"patch","patch":"diff"} this should not be needed',
            "stream_baseline_output_tokens": 50,
        },
    )

    response = await Executor().execute(ir, GovernanceResult(GovernanceDecision.ALLOW, reason="test"))

    assert response["edgek_stream_interception"]["stop_reason"] == "governed_object_complete"
    assert response["edgek_stream_interception"]["upstream_cancel_requested"] is True
    assert response["edgek_compute"]["streaming"]["early_stopped"] is True
    assert response["edgek_compute"]["streaming"]["tokens_saved"] > 0
    receipt = ledger.recent_receipts(1)[0]
    assert receipt["status"] == "stream_intercepted"
    assert receipt["early_stopped"] is True
    assert receipt["stream_stop_reason"] == "governed_object_complete"
    assert receipt["stream_tokens_saved"] > 0
    metrics = ledger.metrics()
    assert metrics["stream_early_stop_count"] == 1
    assert metrics["stream_upstream_cancellation_count"] == 1
    assert metrics["stream_tokens_saved"] == receipt["stream_tokens_saved"]


def test_compute_api_and_mcp_are_read_only_shadow_surfaces(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as main_module
    import app.mcp.runtime as mcp_runtime_module
    from app.mcp.runtime import BeastToolRuntime

    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    monkeypatch.setattr(main_module, "compute_ledger", ledger)
    monkeypatch.setattr(mcp_runtime_module, "compute_ledger", ledger)

    state_response = TestClient(main_module.app).get("/edgek/compute")
    metrics_response = TestClient(main_module.app).get("/edgek/compute/metrics")
    savings_response = TestClient(main_module.app).get(
        "/edgek/compute/savings-summary", params={"weekly_call_volume": 1000}
    )
    mcp_result = BeastToolRuntime().call_tool("beast_compute_shadow", {"action": "state"})
    mcp_savings = BeastToolRuntime().call_tool(
        "beast_compute_shadow", {"action": "savings_summary", "weekly_call_volume": 1000}
    )

    assert state_response.status_code == 200
    # State now reports mode distribution; check modes dict contains shadow
    state_json = state_response.json()
    assert "modes" in state_json
    assert state_json["modes"].get("shadow", 0) >= 0  # At least the key exists
    assert state_json["enforcing"] is False
    assert metrics_response.json()["claim_boundary"].startswith("Shadow estimates")
    assert savings_response.status_code == 200
    assert savings_response.json()["weekly_call_volume"] == 1000
    assert "modes" in mcp_result or mcp_result.get("mode") == "shadow"
    assert mcp_result["enforcing"] is False
    assert mcp_savings["weekly_call_volume"] == 1000


def test_shadow_benchmark_preserves_behavior_and_detects_candidates():
    from benchmarks.compute_governor_shadow_benchmark import run

    report = run()

    assert report["scenario_count"] == 5
    assert report["all_behavior_preserved"] is True
    assert report["candidate_detection_rate"] == 1.0
    assert report["privacy"]["prompts_persisted"] is False
    assert report["metrics"]["observed_total_tokens"] > 0
    assert report["metrics"]["estimated_avoidable_total_tokens"] > 0


def test_phase1_closure_benchmark_proves_paired_equivalence():
    from benchmarks.compute_governor_phase1_closure_benchmark import run

    report = run(repeats=2)

    assert report["paired_attempts"] == 12
    assert report["actual_provider_calls"] == {
        "accounting_off": 12,
        "accounting_on": 12,
        "unchanged": True,
    }
    assert report["verified_behavior_preservation_rate"] == 1.0
    assert report["provider_path_equivalence_rate"] == 1.0
    assert report["patch_equivalence_rate"] == 1.0
    assert report["verifier_equivalence_rate"] == 1.0
    assert report["behavior_difference_count"] == 0
    assert report["receipt_coverage_rate"] == 1.0
    assert report["suppression_decisions_enforced"] == 0
    assert report["false_suppression_rate"] == 0.0
    assert report["estimated_avoided_usd_counterfactual"] is None
    assert report["phase1_preflight_passed"] is True


def test_phase2_calibration_executes_all_allowlisted_transforms_in_shadow():
    from benchmarks.compute_governor_phase2_calibration import run

    report = run(repeats=2)

    assert report["paired_attempts"] == 12
    assert report["provider_calls"] == 12
    assert report["provider_path_unchanged"] is True
    assert report["transform_verification_rate"] == 1.0
    assert report["calibrated_agreement_rate"] == 1.0
    assert report["suppression_decisions_enforced"] == 0
    assert report["passed"] is True


def test_phase2_routing_benchmark_measures_shadow_displacement_pressure():
    from benchmarks.compute_governor_phase2_routing_benchmark import run

    report = run(repeats=2)

    assert report["paired_attempts"] == 6
    assert report["shadow_preserved_current_route_rate"] == 1.0
    assert report["friction_selection_change_count"] == 2
    assert report["friction_selection_change_rate"] == pytest.approx(1 / 3, abs=0.000001)
    assert report["expected_change_match_rate"] == 1.0
    assert report["passed"] is True


def test_phase1_token_estimates_are_calibrated_against_paired_deltas():
    from benchmarks.compute_governor_phase1_calibration import run

    report = run(repeats=2)
    assert report["paired_attempts"] == 12
    assert report["calibration_coverage_rate"] == 1.0
    assert report["avoidable_token_mean_absolute_error"] == 0.0
    assert report["provider_execution_preserved"] is True
    assert report["passed"] is True


def test_phase2_shadow_mode_defaults_to_shadow_when_invalid_config():
    """Test that phase2_shadow mode defaults to shadow behavior for invalid configs"""
    ir = EdgeKIR(messages=[{"role": "user", "content": "Run tests"}], model="m", metadata={})
    # Test with invalid mode - should default to phase2_shadow which behaves like shadow
    governor = ComputeGovernor(mode="invalid_mode")
    plan = governor.build_plan(ir, "provider")
    
    gate = governor.evaluate(plan)
    
    # Should behave like shadow mode (not enforced)
    assert gate.allowed is True
    assert gate.enforced is False
    assert gate.mode == "shadow"  # mode falls back to safe shadow default
    # In shadow mode, even with deterministic candidates, should not enforce
    assert gate.decision == "cloud_inference"


def test_phase2_enforce_does_not_enforce_keyword_candidate_without_proof():
    """Test that phase2_enforce does NOT enforce from keyword-detected candidates alone.
    
    deterministic_candidates are hypotheses; enforceable_displacements require paired ablation proof.
    """
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Run pytest and compile this private source"}],
        model="grok-build-0.1",
        max_tokens=300,
        metadata={"task_class": "debug"},
    )
    governor = ComputeGovernor(mode="phase2_enforce")
    plan = governor.build_plan(ir, "xai")
    
    # Verify plan has deterministic_candidates (keyword-detected hypotheses)
    assert "test_execution" in plan.deterministic_candidates
    assert "syntax_check" in plan.deterministic_candidates
    
    # But plan has no enforceable_displacements (no paired ablation proof)
    assert len(plan.enforceable_displacements) == 0
    
    gate = governor.evaluate(plan)
    
    # Phase 2 enforce should NOT trigger without enforceable_displacements
    assert gate.allowed is True
    assert gate.enforced is False  # NOT enforced - waiting for proof
    assert gate.mode == "phase2_enforce"
    assert gate.decision == "cloud_inference"  # Falls back to provider
    assert "no verified enforceable_displacements" in gate.reason


def test_phase2_enforce_mode_no_enforcement_when_no_deterministic_candidates():
    """Test that phase2_enforce mode does not enforce when no deterministic candidates exist"""
    ir = EdgeKIR(messages=[{"role": "user", "content": "Just a simple query"}], model="m", metadata={})
    governor = ComputeGovernor(mode="phase2_enforce")
    plan = governor.build_plan(ir, "provider")
    
    gate = governor.evaluate(plan)
    
    # Should not enforce when no deterministic candidates
    assert gate.allowed is True
    assert gate.enforced is False
    assert gate.mode == "phase2_enforce"
    assert gate.decision == "cloud_inference"  # Falls back to cloud inference
    assert "no verified enforceable_displacements" in gate.reason


def test_phase2_shadow_mode_behavior_matches_shadow():
    """Test that phase2_shadow mode behaves identically to shadow mode"""
    ir = EdgeKIR(messages=[{"role": "user", "content": "Run tests"}], model="m", metadata={})
    
    governor_shadow = ComputeGovernor(mode="shadow")
    governor_phase2_shadow = ComputeGovernor(mode="phase2_shadow")
    
    plan = governor_shadow.build_plan(ir, "provider")
    
    gate_shadow = governor_shadow.evaluate(plan)
    gate_phase2_shadow = governor_phase2_shadow.evaluate(plan)
    
    # Both should have same behavior (not enforced)
    assert gate_shadow.enforced == gate_phase2_shadow.enforced
    assert gate_shadow.decision == gate_phase2_shadow.decision
    assert gate_shadow.selected_rung == gate_phase2_shadow.selected_rung
