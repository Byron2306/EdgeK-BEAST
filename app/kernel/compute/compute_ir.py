"""Typed artifacts for BEAST inference compute governance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ComputeBudget:
    cloud_calls: int = 1
    input_tokens: int = 0
    output_tokens: int = 256
    latency_ms: int = 120_000
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ComputePlan:
    plan_id: str
    request_fingerprint: str
    mode: str
    task_class: str
    provider: str
    model: str
    message_count: int
    input_chars: int
    estimated_input_tokens: int
    requested_output_tokens: int
    unresolved_work: List[str] = field(default_factory=list)
    deterministic_candidates: List[str] = field(default_factory=list)
    reuse_candidates: List[str] = field(default_factory=list)
    enforceable_displacements: List[str] = field(default_factory=list)
    displacement_proofs: List[Dict[str, Any]] = field(default_factory=list)
    escalation_ladder: List[str] = field(default_factory=list)
    budgets: ComputeBudget = field(default_factory=ComputeBudget)
    created_at: str = ""
    plan_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["beast_object_type"] = "compute_plan"
        result["version"] = "1.0"
        result["privacy"] = {
            "contains_prompt": False,
            "contains_source_code": False,
            "content_fingerprints_only": True,
        }
        return result


@dataclass(frozen=True)
class ComputeGateDecision:
    gate_id: str
    plan_id: str
    mode: str
    decision: str
    candidate_decision: str
    allowed: bool
    enforced: bool
    confidence: float
    ambiguous: bool
    tiebreaker_policy: str
    selected_rung: str
    recommended_rung: str
    reason: str
    predicted_avoidable_work: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["beast_object_type"] = "compute_gate_decision"
        result["version"] = "1.0"
        return result


@dataclass(frozen=True)
class ComputeReceipt:
    receipt_id: str
    plan_id: str
    gate_id: str
    runtime_attempt_id: str
    mode: str
    provider: str
    model: str
    status: str
    provider_execution_requested: bool
    selected_rung: str
    recommended_rung: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    cost_usd: Optional[float]
    early_stopped: bool
    stream_stop_reason: str = ""
    stream_tokens_saved: int = 0
    stream_repair_action: str = ""
    upstream_cancel_requested: bool = False
    predicted_avoidable_work: List[str] = field(default_factory=list)
    estimated_avoidable_input_tokens: int = 0
    estimated_avoidable_output_tokens: int = 0
    avoided_tokens_estimate: int = 0
    predicted_savings_usd: Optional[float] = None
    observed_avoidable_tokens: Optional[int] = None
    avoidable_token_estimation_error: Optional[int] = None
    calibration_source: str = ""
    cost_observation_available: bool = False
    counterfactual_estimates: bool = True
    gate_decision: str = "cloud_inference"
    candidate_decision: str = "cloud_inference"
    suppression_enforced: bool = False
    behavior_preserved: Optional[bool] = None
    deterministic_shadow_results: List[Dict[str, Any]] = field(default_factory=list)
    deterministic_shadow_attempts: int = 0
    deterministic_shadow_verified: int = 0
    deterministic_shadow_calibrated: int = 0
    deterministic_shadow_agreements: int = 0
    error_type: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["beast_object_type"] = "compute_receipt"
        result["version"] = "1.0"
        result["shadow_only"] = self.mode in {"shadow", "phase2_shadow"}
        return result


@dataclass(frozen=True)
class CounterfactualCrystal:
    crystal_id: str
    plan_id: str
    task_class: str
    selected_provider: str
    selected_model: str = ""
    alternative_provider: str = ""
    alternative_model: str = ""
    alternative_rank: int = 0
    selected_score: float = 0.0
    alternative_score: float = 0.0
    predicted_failure_class: str = ""
    predicted_cost_usd: Optional[float] = None
    predicted_latency_ms: Optional[float] = None
    predicted_confidence: float = 0.0
    rejection_reason: str = ""
    state: str = "speculative"
    resolution_outcome: str = ""
    resolution_receipt_id: str = ""
    created_at: str = ""
    resolved_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["beast_object_type"] = "counterfactual_crystal"
        result["version"] = "1.0"
        result["privacy"] = {
            "contains_prompt": False,
            "contains_source_code": False,
            "route_metadata_only": True,
        }
        return result


@dataclass(frozen=True)
class ComputeEscrowRecord:
    escrow_id: str
    plan_id: str
    task_class: str
    provider: str
    model: str
    status: str
    reserved_prec_phase: str = "execute"
    settled_prec_phase: str = ""
    reserved_cloud_calls: int = 0
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    reserved_latency_ms: int = 0
    reserved_cost_usd: Optional[float] = None
    actual_cloud_calls: int = 0
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    actual_latency_ms: float = 0.0
    actual_cost_usd: Optional[float] = None
    refunded_input_tokens: int = 0
    refunded_output_tokens: int = 0
    refunded_latency_ms: float = 0.0
    refunded_cost_usd: Optional[float] = None
    recovery_overhead_tokens: int = 0
    recovery_overhead_cost_usd: Optional[float] = None
    verified_delivery: bool = False
    emergency_claim: bool = False
    approved_by: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["beast_object_type"] = "compute_escrow_record"
        result["version"] = "1.0"
        result["privacy"] = {
            "contains_prompt": False,
            "contains_source_code": False,
            "budget_metadata_only": True,
        }
        return result


@dataclass(frozen=True)
class DeterministicDisplacementProof:
    """Phase 2: Verified proof that a deterministic transform is safe for enforcement.
    
    Only objects of this type should allow phase2_enforce mode to trigger.
    Created after paired shadow ablation confirms behavior preservation.
    """
    candidate_name: str
    task_class: str
    risk_class: str  # "low", "medium", "high"
    allowed_transform: str  # e.g., "syntax_check", "schema_validation"
    verifier_command: str  # Command or function to verify the transform
    visible_tests_equal_or_better: bool
    hidden_tests_equal_or_better: bool
    scope_checks_equal_or_better: bool
    rollback_equal_or_better: bool
    security_checks_equal_or_better: bool
    paired_ablation_runs: int  # Number of successful paired ablation runs
    confidence: float
    approved_for_enforcement: bool
    policy_version: str
    impact_fingerprint: Optional[Dict[str, Any]] = None
    expected_output_sha256: str = ""
    created_at: str = ""
    proof_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["beast_object_type"] = "deterministic_displacement_proof"
        result["version"] = "1.0"
        return result

    def is_enforceable(self) -> bool:
        """Check if this proof meets all criteria for enforcement."""
        if not self.approved_for_enforcement:
            return False
        if self.paired_ablation_runs < 1:
            return False
        if self.confidence < 0.80:
            return False
        if self.risk_class == "high":
            return False
        # All verification checks must pass
        checks = [
            self.visible_tests_equal_or_better,
            self.hidden_tests_equal_or_better,
            self.scope_checks_equal_or_better,
            self.rollback_equal_or_better,
            self.security_checks_equal_or_better,
        ]
        return all(checks)
