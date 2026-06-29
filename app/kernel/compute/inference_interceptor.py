"""Phase 1 shadow interceptor around governed provider execution."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.compute.compute_ir import ComputeGateDecision, ComputePlan, ComputeReceipt
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.governance.deterministic_executor import DeterministicTransformExecutor, DeterministicTransformResult
from app.kernel.capability.capability_impact import CapabilityImpactFingerprint
from app.kernel.local.local_model_adapter import LocalModelAdapter
from app.kernel.storage.outcome_evidence import NegativeCapabilityStore, OutcomeEvidence, default_outcome_store


@dataclass
class ComputeInterception:
    plan: ComputePlan
    gate: ComputeGateDecision
    started_at: float
    deterministic_shadow_results: list[DeterministicTransformResult] = field(default_factory=list)
    calibration: Dict[str, Any] = field(default_factory=dict)
    verified_reuse_decision: Dict[str, Any] = field(default_factory=dict)
    reuse_response_payload: Optional[Dict[str, Any]] = None
    adaptive_routing: Any = None
    reuse_observation: Dict[str, Any] = field(default_factory=dict)
    local_model_result: Dict[str, Any] = field(default_factory=dict)
    escrow_id: str = ""
    prec_phase: str = "execute"
    counterfactual_crystals: list[Dict[str, Any]] = field(default_factory=list)


class InferenceComputeInterceptor:
    def __init__(
        self,
        governor: Optional[ComputeGovernor] = None,
        ledger: Optional[ComputeLedger] = None,
        transform_executor: Optional[DeterministicTransformExecutor] = None,
        promoted_capability_store: Optional[Path] = None,
        local_model_adapter: Optional[LocalModelAdapter] = None,
        approval_audit_store: Any = None,
        outcome_store: Optional[NegativeCapabilityStore] = None,
    ) -> None:
        self.governor = governor or ComputeGovernor()
        self.ledger = ledger or ComputeLedger()
        self.transform_executor = transform_executor or DeterministicTransformExecutor(self.governor.allowlist)
        self.promoted_capability_store = promoted_capability_store or (
            Path(__file__).resolve().parents[2] / "data" / "promoted_capabilities.json"
        )
        self.local_model_adapter = local_model_adapter or LocalModelAdapter()
        self.approval_audit_store = approval_audit_store
        self.outcome_store = outcome_store or NegativeCapabilityStore()

    def begin(self, ir: Any, provider: str) -> ComputeInterception:
        plan = self.governor.build_plan(ir, provider)
        gate = self.governor.evaluate(plan)
        metadata = dict(getattr(ir, "metadata", None) or {})
        shadow_results = self.transform_executor.execute(
            plan.deterministic_candidates,
            metadata.get("deterministic_work"),
        )
        gate = self._enforce_complete_transform(plan, gate, shadow_results)
        verified_reuse_decision, reuse_response = self._enforce_verified_reuse(plan, gate, metadata)
        if reuse_response is not None:
            gate = replace(
                gate,
                decision="reuse",
                candidate_decision="reuse",
                enforced=True,
                confidence=float(verified_reuse_decision.get("confidence") or 0.0),
                ambiguous=False,
                selected_rung="verified_reuse",
                recommended_rung="verified_reuse",
                reason=str(verified_reuse_decision.get("reason") or "Verified reuse accepted."),
            )
        adaptive_routing = self.governor.route_adaptively(
            plan,
            gate,
            provider_candidates=metadata.get("provider_candidates"),
            estimated_cost_usd=self._optional_float(metadata.get("estimated_cost_usd")),
            risk_class=str(metadata.get("risk_class") or "low"),
            negative_capabilities=self.outcome_store.list_records(),
            friction_profiles=self.outcome_store.friction_profiles(),
        )
        gate = self._apply_adaptive_route(plan, gate, adaptive_routing, metadata)
        local_model_result = {}
        if gate.decision == "local_inference":
            local_model_result = self.local_model_adapter.execute(
                task_class=plan.task_class,
                prompt_hint=plan.request_fingerprint,
                max_tokens=plan.requested_output_tokens,
            ).to_dict()
        calibration = self._calibration(metadata.get("compute_calibration"))
        prec_phase = str(metadata.get("prec_phase") or metadata.get("prec_lifecycle_phase") or "execute")
        counterfactual_crystals = []
        economist_decision = getattr(adaptive_routing, "economist_decision", None)
        if economist_decision:
            counterfactual_crystals = [
                item.to_dict()
                for item in self.ledger.record_counterfactual_crystals(plan, economist_decision)
            ]
        estimated_cost = self._optional_float(metadata.get("estimated_cost_usd"))
        emergency = metadata.get("emergency_local_compute") if isinstance(metadata.get("emergency_local_compute"), dict) else {}
        escrow = self.ledger.reserve_escrow(
            plan,
            estimated_cost_usd=estimated_cost,
            emergency_claim=emergency.get("approved") is True,
            approved_by=str(emergency.get("approved_by") or ""),
            prec_phase=prec_phase,
        )
        self.ledger.record_plan(plan)
        self.ledger.record_gate(gate)
        return ComputeInterception(
            plan=plan,
            gate=gate,
            started_at=time.perf_counter(),
            deterministic_shadow_results=shadow_results,
            calibration=calibration,
            verified_reuse_decision=verified_reuse_decision,
            reuse_response_payload=reuse_response,
            adaptive_routing=adaptive_routing,
            local_model_result=local_model_result,
            escrow_id=escrow.escrow_id,
            prec_phase=prec_phase,
            counterfactual_crystals=counterfactual_crystals,
        )

    def complete(
        self,
        interception: ComputeInterception,
        *,
        response: Optional[Dict[str, Any]] = None,
        runtime_attempt_id: str = "",
        status: str = "completed",
        provider_execution_requested: bool = True,
        behavior_preserved: Optional[bool] = None,
        error_type: str = "",
        stream_report: Any = None,
    ) -> ComputeReceipt:
        response = response or {}
        usage = self._usage(response)
        latency_ms = max(0.0, (time.perf_counter() - interception.started_at) * 1000.0)
        predicted = interception.gate.predicted_avoidable_work
        input_basis = usage["input_tokens"] or interception.plan.estimated_input_tokens
        output_basis = usage["output_tokens"] or interception.plan.requested_output_tokens
        estimated_input = int(input_basis * 0.35) if predicted else 0
        estimated_output = int(output_basis * 0.20) if predicted else 0
        avoided_tokens_estimate = estimated_input + estimated_output
        cost_usd = usage["cost_usd"]
        predicted_savings_usd = None
        if cost_usd is not None and usage["total_tokens"] > 0:
            predicted_savings_usd = round(cost_usd * min(1.0, avoided_tokens_estimate / usage["total_tokens"]), 9)
        shadow_results = [item.to_dict() for item in interception.deterministic_shadow_results]
        calibrated = [item for item in interception.deterministic_shadow_results if item.behavior_preserved is not None]
        observed_avoidable = interception.calibration.get("observed_avoidable_tokens")
        estimation_error = avoided_tokens_estimate - observed_avoidable if observed_avoidable is not None else None
        receipt = ComputeReceipt(
            receipt_id="crec_" + uuid.uuid4().hex[:20],
            plan_id=interception.plan.plan_id,
            gate_id=interception.gate.gate_id,
            runtime_attempt_id=runtime_attempt_id,
            mode=interception.plan.mode,
            provider=interception.plan.provider,
            model=interception.plan.model,
            status=status,
            provider_execution_requested=provider_execution_requested,
            selected_rung=interception.gate.selected_rung,
            recommended_rung=interception.gate.recommended_rung,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            latency_ms=round(latency_ms, 3),
            cost_usd=cost_usd,
            early_stopped=bool(getattr(getattr(stream_report, "final_state", None), "early_stopped", False)),
            stream_stop_reason=str(getattr(getattr(stream_report, "final_state", None), "stop_reason", "") or ""),
            stream_tokens_saved=int(getattr(getattr(stream_report, "savings", None), "saved_tokens", 0) or 0),
            stream_repair_action=str(getattr(getattr(stream_report, "repair_decision", None), "action", "") or ""),
            upstream_cancel_requested=bool(getattr(getattr(stream_report, "cancellation", None), "requested", False)),
            predicted_avoidable_work=predicted,
            estimated_avoidable_input_tokens=estimated_input,
            estimated_avoidable_output_tokens=estimated_output,
            avoided_tokens_estimate=avoided_tokens_estimate,
            predicted_savings_usd=predicted_savings_usd,
            observed_avoidable_tokens=observed_avoidable,
            avoidable_token_estimation_error=estimation_error,
            calibration_source=str(interception.calibration.get("source") or ""),
            cost_observation_available=cost_usd is not None,
            counterfactual_estimates=True,
            gate_decision=interception.gate.decision,
            candidate_decision=interception.gate.candidate_decision,
            suppression_enforced=interception.gate.enforced and interception.gate.decision == "suppress",
            behavior_preserved=behavior_preserved,
            deterministic_shadow_results=shadow_results,
            deterministic_shadow_attempts=len(shadow_results),
            deterministic_shadow_verified=sum(item.verified for item in interception.deterministic_shadow_results),
            deterministic_shadow_calibrated=len(calibrated),
            deterministic_shadow_agreements=sum(item.behavior_preserved is True for item in calibrated),
            error_type=error_type,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.ledger.record_receipt(receipt)
        verified_delivery = self._verified_delivery(receipt, behavior_preserved, error_type)
        recovery_overhead_tokens = int(bool(receipt.stream_repair_action) or behavior_preserved is False) * max(0, receipt.total_tokens)
        self.ledger.settle_escrow(
            interception.plan.plan_id,
            receipt,
            verified_delivery=verified_delivery,
            recovery_overhead_tokens=recovery_overhead_tokens,
            recovery_overhead_cost_usd=receipt.cost_usd if recovery_overhead_tokens else None,
            prec_phase=interception.prec_phase,
        )
        self.ledger.resolve_counterfactuals(
            task_class=interception.plan.task_class,
            provider=receipt.provider,
            model=receipt.model,
            outcome=self._counterfactual_resolution_outcome(receipt, behavior_preserved, error_type),
            receipt_id=receipt.receipt_id,
        )
        self._record_approval_audit(interception, receipt)
        self._record_reuse_observation(interception, receipt, behavior_preserved)
        self._record_outcome(interception, receipt, error_type, behavior_preserved)
        return receipt

    def _record_outcome(self, interception, receipt, error_type, behavior_preserved) -> None:
        decision = interception.gate.decision
        selected = []
        capability_id = f"provider:{receipt.provider}"
        scope = {"provider": receipt.provider, "model": receipt.model, "route": decision}
        if decision == "reuse":
            name = str((interception.verified_reuse_decision or {}).get("matched_capability") or "verified_reuse")
            capability_id = name
            selected = [name]
        elif decision == "deterministic":
            verified = [item.candidate_name for item in interception.deterministic_shadow_results if item.verified]
            capability_id = verified[0] if verified else "deterministic_transform"
            selected = verified
        elif decision == "require_approval":
            capability_id = f"approval:{receipt.provider}"
        failed = bool(error_type) or receipt.status.lower() in {"failed", "error", "provider_error"} or behavior_preserved is False
        repaired = bool(receipt.stream_repair_action) or (behavior_preserved is False and receipt.status == "completed")
        outcome = "failure" if failed and not repaired else "recovered" if repaired else "success"
        self.outcome_store.record(OutcomeEvidence.create(
            capability_id=capability_id,
            task_class=interception.plan.task_class,
            outcome=outcome,
            failure_category=str(error_type or receipt.stream_repair_action or ("behavior_not_preserved" if behavior_preserved is False else "")),
            failure_code=receipt.status if outcome != "success" else "",
            scope=scope,
            repair_depth=int(repaired),
            latency_ms=receipt.latency_ms,
            cost_usd=receipt.cost_usd,
            input_tokens=receipt.input_tokens,
            output_tokens=receipt.output_tokens,
            confidence_before=interception.gate.confidence,
            confidence_after=interception.gate.confidence if behavior_preserved is not False else 0.0,
            selected_capabilities=selected or [capability_id],
            rejected_capabilities=[
                str(item.get("alternative_provider") or "")
                for item in interception.counterfactual_crystals
                if item.get("alternative_provider")
            ],
        ))

    @staticmethod
    def _verified_delivery(receipt, behavior_preserved, error_type) -> bool:
        if error_type:
            return False
        if behavior_preserved is False:
            return False
        return receipt.status.lower() in {
            "completed", "succeeded", "success", "local_inference_selected",
            "deterministic_selected", "reuse_selected",
        }

    @staticmethod
    def _counterfactual_resolution_outcome(receipt, behavior_preserved, error_type) -> str:
        if error_type:
            return str(error_type)
        if behavior_preserved is False:
            return "failure"
        if receipt.stream_repair_action:
            return "recovered"
        if receipt.status.lower() in {"failed", "error", "provider_error"}:
            return "failure"
        return "success"

    @staticmethod
    def _calibration(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        source = str(payload.get("source") or "")
        if source not in {"paired_ablation", "provider_usage_attribution"}:
            return {}
        try:
            observed = int(payload.get("observed_avoidable_tokens"))
        except (TypeError, ValueError):
            return {}
        if observed < 0:
            return {}
        return {"source": source, "observed_avoidable_tokens": observed}

    @staticmethod
    def execution_route(interception: ComputeInterception) -> str:
        """Return the execution route based on the gate decision.
        
        Returns one of: "provider", "deterministic", "approval", "escalate"
        """
        decision = interception.gate.decision
        if decision == "deterministic":
            return "deterministic"
        if decision == "reuse":
            return "reuse"
        if decision == "escalate":
            return "escalate"
        if decision == "require_approval":
            return "approval"
        if decision == "local_inference":
            return "local"
        # Default: cloud_inference uses provider path
        return "provider"

    @staticmethod
    def should_call_provider(interception: ComputeInterception) -> bool:
        """Return True if the provider should be called for this interception."""
        return InferenceComputeInterceptor.execution_route(interception) == "provider"

    @staticmethod
    def deterministic_response(interception: ComputeInterception) -> Dict[str, Any]:
        eligible = [
            item for item in interception.deterministic_shadow_results
            if item.complete_task and item.verified and item.behavior_preserved is True
        ]
        if interception.gate.decision != "deterministic" or len(eligible) != 1:
            raise ValueError("no enforceable deterministic response is available")
        item = eligible[0]
        return {
            "object": "beast.deterministic_transform",
            "candidate": item.candidate_name,
            "result": item.output,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    @staticmethod
    def reuse_response(interception: ComputeInterception) -> Dict[str, Any]:
        if interception.gate.decision != "reuse" or not interception.reuse_response_payload:
            raise ValueError("no verified reuse response is available")
        response = dict(interception.reuse_response_payload)
        response.setdefault("object", "beast.verified_reuse")
        response.setdefault("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        return response

    def local_inference_response(self, interception: ComputeInterception) -> Dict[str, Any]:
        routing = interception.adaptive_routing
        if interception.gate.decision != "local_inference" or routing is None:
            raise ValueError("no local inference response is available")
        local_result = dict(interception.local_model_result or {})
        if not local_result:
            local_result = self.local_model_adapter.execute(
                task_class=interception.plan.task_class,
                prompt_hint=interception.plan.request_fingerprint,
                max_tokens=interception.plan.requested_output_tokens,
            ).to_dict()
            interception.local_model_result = local_result
        response = {
            "object": "beast.local_inference_route",
            "route": routing.route,
            "decision": routing.decision,
            "reason": routing.reason,
            "economist_decision": routing.economist_decision,
            "local_model": local_result,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        return response

    @staticmethod
    def _enforce_complete_transform(plan, gate, results):
        if plan.mode not in {"phase2_enforce", "phase3_enforce", "phase4_enforce"}:
            return gate
        proof_hashes = {
            str(item.get("candidate_name") or ""): str(item.get("expected_output_sha256") or "")
            for item in plan.displacement_proofs if isinstance(item, dict)
        }
        eligible = [
            item for item in results
            if item.candidate_name in plan.enforceable_displacements
            and item.complete_task and item.verified and item.behavior_preserved is True
            and bool(proof_hashes.get(item.candidate_name))
            and proof_hashes[item.candidate_name] == item.output_sha256
        ]
        if len(eligible) != 1:
            return gate
        return replace(
            gate,
            decision="deterministic",
            candidate_decision="deterministic",
            enforced=True,
            confidence=1.0,
            ambiguous=False,
            selected_rung="deterministic_transform",
            recommended_rung="deterministic_transform",
            reason=f"Phase 2 enforced verified complete transform: {eligible[0].candidate_name}",
        )

    def _enforce_verified_reuse(self, plan, gate, metadata):
        if plan.mode not in {"phase3_enforce", "phase4_enforce"}:
            return {}, None
        if gate.decision == "deterministic":
            return {}, None
        capabilities = self._available_capabilities(metadata)
        if not isinstance(capabilities, list):
            return {}, None
        task_envelope = {
            "task_class": plan.task_class,
            "purpose": metadata.get("purpose") or metadata.get("beast_task_class") or plan.task_class,
            "metadata": self._safe_reuse_metadata(metadata),
        }
        selected = self.governor.reuse_engine.match_task_to_capability(task_envelope, capabilities)[0]
        current_repo_state = self._current_repo_state_for_reuse(selected, metadata)
        decision = self.governor.reuse_engine.compute_reuse_decision(
            task_envelope,
            capabilities,
            current_repo_state=current_repo_state,
        )
        if decision.get("decision") != "reuse":
            return decision, None
        matched_name = decision.get("matched_capability")
        capability = next(
            (item for item in capabilities if isinstance(item, dict) and item.get("candidate_name") == matched_name),
            None,
        )
        replay = self._replay_capability(capability, metadata)
        if replay.get("verified") is not True:
            blocked = {
                **decision,
                "decision": "escalate",
                "verification": {
                    **dict(decision.get("verification") or {}),
                    "safe_to_reuse": False,
                    "reason": replay.get("reason", "deterministic_replay_failed"),
                },
                "reason": f"Reuse blocked: {replay.get('reason', 'deterministic_replay_failed')}; escalate to verify",
            }
            return blocked, None
        response = {
            "object": "beast.verified_reuse",
            "capability": matched_name,
            "result": replay.get("output"),
            "reuse_decision": {
                "decision": decision.get("decision"),
                "matched_capability": matched_name,
                "confidence": decision.get("confidence"),
                "reason": decision.get("reason"),
            },
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        return decision, response

    def _available_capabilities(self, metadata):
        capabilities = []
        for key in ("promoted_capabilities", "verified_capabilities"):
            value = metadata.get(key)
            if isinstance(value, list):
                capabilities.extend(item for item in value if isinstance(item, dict))
        capabilities.extend(self._load_promoted_capabilities())
        deduped = {}
        for item in capabilities:
            name = str(item.get("candidate_name") or "")
            if name:
                deduped[name] = item
        return list(deduped.values())

    def _load_promoted_capabilities(self):
        path = self.promoted_capability_store
        if not path or not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("capabilities"), list):
            return [item for item in payload["capabilities"] if isinstance(item, dict)]
        return []

    def _current_repo_state_for_reuse(self, capability, metadata):
        explicit = metadata.get("current_repo_state")
        if isinstance(explicit, dict):
            return explicit
        if not isinstance(capability, dict):
            return None
        boundary = capability.get("impact_boundary") or capability.get("fingerprint_boundary") or {}
        if not isinstance(boundary, dict):
            return None
        root = boundary.get("root") or metadata.get("repo_root")
        if not root:
            return None
        try:
            return CapabilityImpactFingerprint().build(
                Path(str(root)),
                target_paths=boundary.get("target_paths", ()),
                dependency_paths=boundary.get("dependency_paths", ()),
                test_paths=boundary.get("test_paths", ()),
                symbols=boundary.get("symbols", {}),
                tool_schema_hashes=boundary.get("tool_schema_hashes", ()),
                policy_version=str(boundary.get("policy_version") or "unknown"),
                confidence=float(boundary.get("confidence", capability.get("confidence", 1.0)) or 1.0),
            )
        except (OSError, ValueError, TypeError):
            return None

    def _replay_capability(self, capability, metadata):
        if not isinstance(capability, dict):
            return {"verified": False, "reason": "matched_capability_missing"}
        replay = capability.get("deterministic_replay") or capability.get("replay") or {}
        if not isinstance(replay, dict):
            return {"verified": False, "reason": "deterministic_replay_required"}
        candidate = str(replay.get("candidate_name") or capability.get("allowed_transform") or capability.get("candidate_name") or "")
        expected_hash = str(replay.get("expected_output_sha256") or capability.get("expected_output_sha256") or "")
        work = replay.get("deterministic_work")
        if work is None:
            work = metadata.get("deterministic_work")
        if not candidate or not expected_hash:
            return {"verified": False, "reason": "deterministic_replay_contract_incomplete"}
        results = self.transform_executor.execute([candidate], work)
        if len(results) != 1:
            return {"verified": False, "reason": "deterministic_replay_unavailable"}
        result = results[0]
        if not result.verified:
            return {"verified": False, "reason": "deterministic_replay_verifier_failed"}
        if result.output_sha256 != expected_hash:
            return {"verified": False, "reason": "deterministic_replay_hash_mismatch"}
        return {"verified": True, "output": result.output, "output_sha256": result.output_sha256}

    def _record_reuse_observation(self, interception, receipt, behavior_preserved):
        decision = interception.verified_reuse_decision or {}
        if decision.get("decision") != "reuse":
            return
        observation = {
            "beast_object_type": "verified_reuse_observation",
            "version": "1.0",
            "receipt_id": receipt.receipt_id,
            "matched_capability": decision.get("matched_capability"),
            "behavior_preserved": behavior_preserved,
            "false_reuse": behavior_preserved is False,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        interception.reuse_observation = observation
        metrics = getattr(self.governor.reuse_engine, "metrics", None)
        if metrics is not None:
            metrics.record_decision(decision)
            if behavior_preserved is False:
                metrics.record_false_reuse()

    def _record_approval_audit(self, interception, receipt):
        store = self.approval_audit_store
        if store is None:
            return
        if receipt.gate_decision == "require_approval" and receipt.status == "approval_required":
            store.record(
                event_type="approval_requested",
                plan_id=receipt.plan_id,
                gate_id=receipt.gate_id,
                status="pending",
                reason=interception.gate.reason,
                approved=None,
                metadata={"provider": receipt.provider, "model": receipt.model},
            )

    def _apply_adaptive_route(self, plan, gate, routing, metadata):
        if plan.mode != "phase4_enforce":
            return gate
        if gate.decision in {"deterministic", "reuse"}:
            return gate
        approval = metadata.get("compute_approval") if isinstance(metadata.get("compute_approval"), dict) else {}
        approved = approval.get("approved") is True
        if routing.decision == "require_approval" and approved and self.approval_audit_store is not None:
            self.approval_audit_store.record(
                event_type="approval_resumed",
                plan_id=plan.plan_id,
                gate_id=gate.gate_id,
                status="approved",
                reason=str(approval.get("reason") or "explicit compute approval"),
                approved=True,
                metadata={"approved_by": str(approval.get("approved_by") or "unknown")},
            )
            self.outcome_store.record(OutcomeEvidence.create(
                capability_id=f"approval:{plan.provider}",
                task_class=plan.task_class,
                outcome="recovered",
                failure_category="approval_pause",
                failure_code="approved_resume",
                scope={"provider": plan.provider, "model": plan.model, "route": "approval"},
                repair_depth=1,
                selected_capabilities=[f"approval:{plan.provider}"],
            ))
        if routing.decision == "require_approval" and not approved:
            return replace(
                gate,
                decision="require_approval",
                candidate_decision=gate.candidate_decision,
                enforced=True,
                confidence=gate.confidence,
                ambiguous=False,
                selected_rung="approval",
                recommended_rung="approval",
                reason=routing.reason,
            )
        if routing.decision == "escalate":
            return replace(
                gate,
                decision="escalate",
                enforced=True,
                selected_rung="escalate",
                recommended_rung="escalate",
                reason=routing.reason,
            )
        if routing.decision == "local_inference":
            return replace(
                gate,
                decision="local_inference",
                enforced=True,
                ambiguous=False,
                selected_rung="local_inference",
                recommended_rung="local_inference",
                reason=routing.reason,
            )
        return gate

    @staticmethod
    def _safe_reuse_metadata(metadata):
        allowed = {}
        for key in ("task_class", "beast_task_class", "purpose", "risk_class", "route_provider", "provider"):
            if key in metadata:
                allowed[key] = str(metadata.get(key))[:160]
        return allowed

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _usage(response: Dict[str, Any]) -> Dict[str, Any]:
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        input_tokens = InferenceComputeInterceptor._integer(
            usage.get("prompt_tokens", usage.get("input_tokens", usage.get("prompt_token_count", 0)))
        )
        output_tokens = InferenceComputeInterceptor._integer(
            usage.get("completion_tokens", usage.get("output_tokens", usage.get("candidates_token_count", 0)))
        )
        total_tokens = InferenceComputeInterceptor._integer(usage.get("total_tokens", usage.get("total_token_count", 0)))
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        cost = usage.get("cost_usd", usage.get("total_cost"))
        if cost in (None, "") and usage.get("cost_in_usd_ticks") not in (None, ""):
            try:
                cost = float(usage["cost_in_usd_ticks"]) / 10_000_000_000
            except (TypeError, ValueError):
                cost = None
        # Expanded cost extraction for provider-specific fields
        if cost in (None, ""):
            for key in ("estimated_cost", "cost", "total_cost_usd", "upstream_inference_cost"):
                val = usage.get(key)
                if val not in (None, ""):
                    try:
                        cost = float(val)
                        break
                    except (TypeError, ValueError):
                        continue
                # Also check nested cost_details
                if isinstance(usage.get("cost_details"), dict):
                    val = usage["cost_details"].get(key)
                    if val not in (None, ""):
                        try:
                            cost = float(val)
                            break
                        except (TypeError, ValueError):
                            continue
        try:
            cost_usd = max(0.0, float(cost)) if cost not in (None, "") else None
        except (TypeError, ValueError):
            cost_usd = None
        return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens, "cost_usd": cost_usd}

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0


compute_ledger = ComputeLedger()
compute_interceptor = InferenceComputeInterceptor(ledger=compute_ledger, outcome_store=default_outcome_store())
