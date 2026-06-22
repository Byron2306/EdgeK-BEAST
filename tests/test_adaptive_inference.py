"""Tests for Phase 4: Adaptive Inference functionality."""

import pytest

from app.kernel.adaptive_inference import (
    AdaptiveInferenceController,
    BudgetCheckResult,
    AdaptiveRoutingDecision,
)
from app.kernel.compute_governor import ComputeGovernor
from app.kernel.compute_ir import ComputeBudget, ComputePlan, ComputeGateDecision
from app.kernel.compute_ledger import ComputeLedger
from app.kernel.approval_audit import ApprovalAuditStore
from app.kernel.outcome_evidence import NegativeCapabilityStore
from app.kernel.inference_interceptor import InferenceComputeInterceptor
from app.kernel.perceive import EdgeKIR


def test_budget_check_detects_token_violations():
    """Test that budget checker catches input/output token overruns."""
    controller = AdaptiveInferenceController()
    
    plan = ComputePlan(
        plan_id="p1",
        request_fingerprint="f1",
        mode="shadow",
        task_class="test",
        provider="p",
        model="m",
        message_count=1,
        input_chars=100,
        estimated_input_tokens=1000,
        requested_output_tokens=500,
        budgets=ComputeBudget(input_tokens=500, output_tokens=200),
    )
    
    result = controller.check_budget(plan)
    
    assert result.within_budget is False
    assert "input_tokens_exceeded" in result.violations
    assert "output_tokens_exceeded" in result.violations


def test_budget_check_detects_cost_violation():
    """Test that budget checker catches USD cost overruns."""
    controller = AdaptiveInferenceController()
    
    plan = ComputePlan(
        plan_id="p2",
        request_fingerprint="f2",
        mode="shadow",
        task_class="test",
        provider="p",
        model="m",
        message_count=1,
        input_chars=100,
        estimated_input_tokens=100,
        requested_output_tokens=50,
        budgets=ComputeBudget(cost_usd=0.01),
    )
    
    result = controller.check_budget(plan, estimated_cost=0.05)
    
    assert result.within_budget is False
    assert "cost_usd_exceeded" in result.violations


def test_budget_check_fails_closed_for_zero_cloud_calls_and_unknown_cost():
    controller = AdaptiveInferenceController()
    plan = ComputePlan(
        plan_id="budget-closed", request_fingerprint="f", mode="shadow",
        task_class="test", provider="p", model="m", message_count=1,
        input_chars=10, estimated_input_tokens=3, requested_output_tokens=10,
        budgets=ComputeBudget(cloud_calls=0, cost_usd=0.01),
    )
    result = controller.check_budget(plan, estimated_cost=None)
    assert result.within_budget is False
    assert "cloud_calls_exceeded" in result.violations
    assert "cost_estimate_unavailable" in result.violations


def test_adaptive_routing_requires_approval_on_budget_violation():
    """Test that budget violations trigger require_approval decision."""
    controller = AdaptiveInferenceController()
    
    plan = ComputePlan(
        plan_id="p3",
        request_fingerprint="f3",
        mode="shadow",
        task_class="test",
        provider="p",
        model="m",
        message_count=1,
        input_chars=100,
        estimated_input_tokens=1000,
        requested_output_tokens=100,
        budgets=ComputeBudget(input_tokens=100),
    )
    
    gate = ComputeGateDecision(
        gate_id="g1", plan_id="p3", mode="shadow", decision="cloud_inference",
        candidate_decision="cloud_inference", allowed=True, enforced=False,
        confidence=0.8, ambiguous=False, tiebreaker_policy="escalate",
        selected_rung="selected_provider", recommended_rung="selected_provider",
        reason="test",
    )
    
    routing = controller.route_adaptively(plan, gate)
    
    assert routing.decision == "require_approval"
    assert routing.route == "approval"
    assert routing.requires_approval is True


def test_adaptive_routing_requires_approval_on_high_risk():
    """Test that high-risk actions (destructive/privileged) require approval."""
    controller = AdaptiveInferenceController()
    
    plan = ComputePlan(
        plan_id="p4",
        request_fingerprint="f4",
        mode="shadow",
        task_class="test",
        provider="p",
        model="m",
        message_count=1,
        input_chars=100,
        estimated_input_tokens=100,
        requested_output_tokens=50,
        budgets=ComputeBudget(),
    )
    
    gate = ComputeGateDecision(
        gate_id="g2", plan_id="p4", mode="shadow", decision="cloud_inference",
        candidate_decision="cloud_inference", allowed=True, enforced=False,
        confidence=0.8, ambiguous=False, tiebreaker_policy="escalate",
        selected_rung="selected_provider", recommended_rung="selected_provider",
        reason="test",
    )
    
    routing = controller.route_adaptively(plan, gate, risk_class="destructive")
    
    assert routing.decision == "require_approval"
    assert routing.requires_approval is True
    assert "high-risk" in routing.reason.lower() or "destructive" in routing.reason.lower()


def test_adaptive_routing_escalates_on_ambiguity():
    """Test that ambiguous gates trigger escalation (cloud fallback available)."""
    controller = AdaptiveInferenceController()
    
    plan = ComputePlan(
        plan_id="p5",
        request_fingerprint="f5",
        mode="shadow",
        task_class="test",
        provider="p",
        model="m",
        message_count=1,
        input_chars=100,
        estimated_input_tokens=100,
        requested_output_tokens=50,
        budgets=ComputeBudget(),
    )
    
    gate = ComputeGateDecision(
        gate_id="g3", plan_id="p5", mode="shadow", decision="cloud_inference",
        candidate_decision="cloud_inference", allowed=True, enforced=False,
        confidence=0.6, ambiguous=True, tiebreaker_policy="escalate",
        selected_rung="selected_provider", recommended_rung="escalate",
        reason="test",
    )
    
    routing = controller.route_adaptively(plan, gate)
    
    assert routing.decision == "escalate"
    assert routing.route == "escalate"
    assert routing.ambiguity_fallback is True
    assert controller.should_invoke_cloud_fallback(routing) is True


def test_adaptive_routing_defaults_to_cloud_inference():
    """Test that non-ambiguous, within-budget, low-risk plans route to cloud."""
    controller = AdaptiveInferenceController()
    
    plan = ComputePlan(
        plan_id="p6",
        request_fingerprint="f6",
        mode="shadow",
        task_class="test",
        provider="p",
        model="m",
        message_count=1,
        input_chars=100,
        estimated_input_tokens=100,
        requested_output_tokens=50,
        budgets=ComputeBudget(),
    )
    
    gate = ComputeGateDecision(
        gate_id="g4", plan_id="p6", mode="shadow", decision="cloud_inference",
        candidate_decision="cloud_inference", allowed=True, enforced=False,
        confidence=0.85, ambiguous=False, tiebreaker_policy="escalate",
        selected_rung="selected_provider", recommended_rung="selected_provider",
        reason="test",
    )
    
    routing = controller.route_adaptively(plan, gate)
    
    assert routing.decision == "cloud_inference"
    assert routing.route == "provider"
    assert routing.ambiguity_fallback is True  # Cloud kept as fallback


def test_governor_adaptive_routing_helper():
    """Test that ComputeGovernor exposes route_adaptively() helper."""
    governor = ComputeGovernor(mode="shadow")
    
    plan = governor.build_plan(
        EdgeKIR(messages=[{"role": "user", "content": "test"}], model="m"),
        "provider",
    )
    gate = governor.evaluate(plan)
    
    routing = governor.route_adaptively(plan, gate, risk_class="low")
    
    assert hasattr(routing, "decision")
    # The routing decision should be one of the Phase 4 outcomes
    assert routing.decision in ("local_inference", "cloud_inference", "require_approval", "escalate", "reuse", "deterministic")


def test_phase4_local_route_executes_dedicated_local_adapter(tmp_path):
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase4_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
    )
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "Summarize bounded local task"}],
        model="m",
        max_tokens=64,
        metadata={
            "task_class": "bounded_microtask",
            "provider_candidates": [{
                "provider": "local_adapter",
                "recommended_role": "primary_patch_provider",
                "latency_ms": 100,
                "auth_confidence": 1.0,
                "hidden_clean_completed": 1,
                "sample_size": 1,
                "hidden_clean_per_usd": 1000,
            }],
        },
    )

    active = interceptor.begin(ir, "groq")
    response = interceptor.local_inference_response(active)
    receipt = interceptor.complete(
        active,
        response=response,
        status="local_inference_selected",
        provider_execution_requested=False,
    )

    assert active.gate.decision == "local_inference"
    assert response["local_model"]["adapter"] == "LocalModelAdapter"
    assert response["local_model"]["status"] == "succeeded"
    assert receipt.provider_execution_requested is False


def test_phase4_approval_audit_persists_request_and_resume(tmp_path):
    audit = ApprovalAuditStore(tmp_path / "approval.jsonl")
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase4_enforce"),
        ComputeLedger(str(tmp_path / "compute.db")),
        approval_audit_store=audit,
    )
    base_metadata = {
        "compute_cost_budget_usd": 0.01,
        "estimated_cost_usd": 0.05,
        "risk_class": "low",
    }
    paused = interceptor.begin(
        EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", metadata=base_metadata),
        "groq",
    )
    interceptor.complete(paused, status="approval_required", provider_execution_requested=False)

    resumed = interceptor.begin(
        EdgeKIR(
            messages=[{"role": "user", "content": "Answer"}],
            model="m",
            metadata={**base_metadata, "compute_approval": {"approved": True, "approved_by": "tester"}},
        ),
        "groq",
    )
    events = audit.events()

    assert paused.gate.decision == "require_approval"
    assert resumed.gate.decision == "cloud_inference"
    assert [event["event_type"] for event in events] == ["approval_requested", "approval_resumed"]
    assert events[0]["status"] == "pending"
    assert events[1]["approved"] is True


def test_compute_interceptor_emits_provider_and_approval_outcomes(tmp_path):
    outcomes = NegativeCapabilityStore(tmp_path / "outcomes.json")
    audit = ApprovalAuditStore(tmp_path / "approval.jsonl")
    interceptor = InferenceComputeInterceptor(
        ComputeGovernor(mode="phase4_enforce"), ComputeLedger(str(tmp_path / "compute.db")),
        approval_audit_store=audit, outcome_store=outcomes,
    )
    metadata = {"compute_cost_budget_usd": 0.01, "estimated_cost_usd": 0.05}
    paused = interceptor.begin(EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", metadata=metadata), "groq")
    interceptor.complete(paused, status="approval_required", provider_execution_requested=False)
    resumed = interceptor.begin(EdgeKIR(
        messages=[{"role": "user", "content": "Answer"}], model="m",
        metadata={**metadata, "compute_approval": {"approved": True, "approved_by": "tester"}},
    ), "groq")
    interceptor.complete(resumed, response={"usage": {"total_tokens": 10}}, status="completed")

    capability_ids = {item["capability_id"] for item in outcomes.outcomes.values()}
    assert "approval:groq" in capability_ids
    assert "provider:groq" in capability_ids


def test_phase3_counterfactual_crystals_resolve_when_rejected_route_runs(tmp_path):
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase4_enforce"), ledger)
    candidates = [
        {
            "provider": "nim", "model": "nemotron", "recommended_role": "clean_patch_candidate",
            "auth_confidence": 1.0, "hidden_clean_per_usd": 100, "avg_latency_ms": 3000,
        },
        {
            "provider": "groq", "model": "llama", "recommended_role": "clean_patch_candidate",
            "auth_confidence": 0.9, "hidden_clean_per_usd": 80, "avg_latency_ms": 45_000,
        },
    ]
    first = interceptor.begin(
        EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", metadata={
            "task_class": "code_generation",
            "provider_candidates": candidates,
        }),
        "nim",
    )
    interceptor.complete(first, response={"usage": {"total_tokens": 20}}, status="completed", behavior_preserved=True)

    assert first.counterfactual_crystals
    assert ledger.counterfactual_summary()["states"]["advisory"] >= 1

    second_candidates = [
        {**candidates[1], "hidden_clean_per_usd": 130, "avg_latency_ms": 2500},
        {**candidates[0], "hidden_clean_per_usd": 70},
    ]
    second = interceptor.begin(
        EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", metadata={
            "task_class": "code_generation",
            "provider_candidates": second_candidates,
        }),
        "groq",
    )
    receipt = interceptor.complete(
        second,
        response={"usage": {"total_tokens": 25}},
        status="completed",
        behavior_preserved=True,
    )
    resolved = [row for row in ledger.recent_counterfactuals() if row.get("state") == "resolved"]

    assert resolved
    assert resolved[0]["alternative_provider"] == "groq"
    assert resolved[0]["resolution_receipt_id"] == receipt.receipt_id
    assert ledger.counterfactual_summary()["resolved"] >= 1


def test_phase4_compute_escrow_reserves_settles_and_refunds(tmp_path):
    ledger = ComputeLedger(str(tmp_path / "compute.db"))
    interceptor = InferenceComputeInterceptor(ComputeGovernor(mode="phase4_enforce"), ledger)
    active = interceptor.begin(
        EdgeKIR(messages=[{"role": "user", "content": "Answer"}], model="m", max_tokens=100, metadata={
            "task_class": "budgeted_answer",
            "prec_phase": "execute",
            "estimated_cost_usd": 0.05,
            "compute_cost_budget_usd": 0.10,
        }),
        "groq",
    )
    reserved = ledger.escrow_for_plan(active.plan.plan_id)
    receipt = interceptor.complete(
        active,
        response={"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "cost_usd": 0.02}},
        status="completed",
        behavior_preserved=True,
    )
    settled = ledger.escrow_for_plan(active.plan.plan_id)
    summary = ledger.escrow_summary()

    assert reserved.status == "reserved"
    assert reserved.reserved_prec_phase == "execute"
    assert reserved.reserved_cost_usd == 0.05
    assert settled.status == "settled_verified"
    assert settled.settled_prec_phase == "execute"
    assert settled.actual_cost_usd == receipt.cost_usd
    assert settled.refunded_cost_usd == 0.03
    assert settled.verified_delivery is True
    assert summary["verified_delivery_rate"] == 1.0
    assert summary["settled_prec_phases"]["execute"] == 1
