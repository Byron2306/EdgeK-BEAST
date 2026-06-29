"""Shadow-mode planning and gating for inference compute demand."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.compute.adaptive_inference import AdaptiveInferenceController, AdaptiveRoutingDecision
from app.kernel.compute.compute_ir import ComputeBudget, ComputeGateDecision, ComputePlan, DeterministicDisplacementProof
from app.kernel.governance.deterministic import Phase2Allowlist
from app.kernel.data_processing.verified_reuse import VerifiedReuseEngine
from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric


class ComputeGovernor:
    """Identify avoidable probabilistic work without changing execution in Phase 1."""

    DETERMINISTIC_SIGNALS = {
        "syntax_check": ("syntax", "compile", "parse error", "py_compile"),
        "test_execution": ("pytest", "run tests", "test suite", "hidden test"),
        "lint_format": ("lint", "format", "ruff", "eslint"),
        "schema_validation": ("schema", "validate json", "contract"),
        "route_diagnostics": ("route", "authentication", "api key", "provider config"),
        "patch_compilation": ("patch", "diff", "apply hunk", "replace exact"),
        "dependency_check": ("dependency", "requirements", "package", "install"),
    }
    SUPPRESSION_CONFIDENCE_THRESHOLD = 0.95

    def __init__(
        self,
        *,
        mode: str | None = None,
        allowlist: Phase2Allowlist = None,
        reuse_engine: VerifiedReuseEngine = None,
        adaptive_controller: AdaptiveInferenceController = None,
        engine_fabric: InferenceEngineFabric = None,
    ) -> None:
        configured = mode if mode is not None else os.environ.get("BEAST_COMPUTE_GOVERNOR_MODE", "shadow")
        allowed_modes = {"shadow", "phase2_shadow", "phase2_enforce", "phase3_enforce", "phase4_enforce"}
        if configured not in allowed_modes:
            self.mode = "shadow"
        else:
            self.mode = configured
        self.allowlist = allowlist or Phase2Allowlist()
        self.reuse_engine = reuse_engine or VerifiedReuseEngine()
        self.adaptive_controller = adaptive_controller or AdaptiveInferenceController()
        self.engine_fabric = engine_fabric or InferenceEngineFabric()

    def serving_inventory(self, *, probe: bool = False) -> Dict[str, Any]:
        """Expose engine capability while retaining routing authority here."""
        return self.engine_fabric.inventory(probe=probe)

    def gate_proof_local_route(
        self,
        route_plan: Dict[str, Any],
        *,
        risk_class: str = "low",
        approval_granted: bool = False,
        local_replay_verified: bool = False,
    ) -> Dict[str, Any]:
        """Apply hard authority gates to an advisory LAN proof-route plan."""
        selected = route_plan.get("selected") if isinstance(route_plan.get("selected"), dict) else None
        checks = {
            "candidate_available": selected is not None,
            "not_high_risk_or_approved": risk_class != "high" or approval_granted,
            "local_replay_verified": bool(local_replay_verified),
            "candidate_remains_advisory": bool(selected and selected.get("authority") == "advisory_requires_local_replay"),
        }
        allowed = all(checks.values())
        if not selected:
            decision = "fallback"
            reason = "no compatible fresh LAN proof candidate"
        elif risk_class == "high" and not approval_granted:
            decision = "require_approval"
            reason = "high-risk LAN reuse requires explicit local approval"
        elif not local_replay_verified:
            decision = "quarantine_and_replay"
            reason = "remote proof is advisory until local replay verifies behavior"
        else:
            decision = "trusted_lan_replay"
            reason = "fresh signed candidate passed local replay and Governor gates"
        return {
            "beast_object_type": "proof_local_compute_gate", "version": "1.0",
            "decision": decision, "allowed": allowed, "checks": checks,
            "selected": selected, "fallback": route_plan.get("fallback") or "local_ollama",
            "provider_execution_requested": False if allowed else None,
            "reason": reason,
            "authority": "compute_governor",
        }

    def build_plan(self, ir: Any, provider: str) -> ComputePlan:
        messages = list(getattr(ir, "messages", None) or [])
        model = str(getattr(ir, "model", None) or "unknown")
        metadata = dict(getattr(ir, "metadata", None) or {})
        text_parts = [self._message_text(item) for item in messages]
        input_chars = sum(len(item) for item in text_parts)
        estimated_tokens = max(1, math.ceil(input_chars / 4)) if input_chars else 0
        requested_output = max(1, int(getattr(ir, "max_tokens", None) or 256))
        task_class = str(
            metadata.get("task_class")
            or metadata.get("beast_task_class")
            or metadata.get("purpose")
            or "chat_completion"
        )[:120]
        deterministic = self._deterministic_candidates(text_parts, metadata)
        reuse = self._reuse_candidates(metadata)
        # Phase 2: enforceable_displacements are verified proofs (allowlisted + ablation-proven)
        # These come from metadata or external proof registry, not keyword detection
        displacement_proofs = self._validated_displacement_proofs(metadata, deterministic)
        enforceable = sorted({proof.candidate_name for proof in displacement_proofs})
        # Also filter deterministic_candidates to only allowlisted ones for Phase 2 consideration
        if self.mode in ("phase2_shadow", "phase2_enforce"):
            deterministic = [d for d in deterministic if self.allowlist.is_allowlisted(d)]
        unresolved = ["response_generation"]
        if getattr(ir, "tools", None):
            unresolved.insert(0, "tool_selection")
        if deterministic:
            unresolved.append("separate_semantic_decision_from_deterministic_execution")
        request_fingerprint = self._fingerprint(messages, model, provider, getattr(ir, "tools", None))
        plan_id = "cmp_" + uuid.uuid4().hex[:20]
        created_at = self._now()
        budgets = ComputeBudget(
            cloud_calls=1,
            input_tokens=estimated_tokens,
            output_tokens=requested_output,
            latency_ms=max(1000, int(metadata.get("compute_latency_budget_ms") or 120_000)),
            cost_usd=self._optional_float(metadata.get("compute_cost_budget_usd")),
        )
        raw = {
            "plan_id": plan_id, "request_fingerprint": request_fingerprint, "mode": self.mode,
            "task_class": task_class, "provider": provider, "model": model,
            "message_count": len(messages), "input_chars": input_chars,
            "estimated_input_tokens": estimated_tokens, "requested_output_tokens": requested_output,
            "unresolved_work": unresolved, "deterministic_candidates": deterministic,
            "reuse_candidates": reuse, "enforceable_displacements": enforceable,
            "displacement_proofs": [proof.to_dict() for proof in displacement_proofs],
            "escalation_ladder": ["chronicle", "deterministic_transform", "ollama_scout", "micro_model", "selected_provider"],
            "budgets": budgets.to_dict(), "created_at": created_at,
        }
        plan_hash = "sha256:" + hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
        return ComputePlan(
            plan_id=plan_id, request_fingerprint=request_fingerprint, mode=self.mode,
            task_class=task_class, provider=provider, model=model,
            message_count=len(messages), input_chars=input_chars,
            estimated_input_tokens=estimated_tokens, requested_output_tokens=requested_output,
            unresolved_work=unresolved, deterministic_candidates=deterministic,
            reuse_candidates=reuse, enforceable_displacements=enforceable,
            displacement_proofs=[proof.to_dict() for proof in displacement_proofs],
            escalation_ladder=raw["escalation_ladder"],
            budgets=budgets, created_at=created_at, plan_hash=plan_hash,
        )

    def evaluate(self, plan: ComputePlan) -> ComputeGateDecision:
        avoidable = list(plan.deterministic_candidates)
        if plan.reuse_candidates:
            avoidable.append("possible_verified_reuse")

        # Candidate names are advisory only. Verified reuse requires a real
        # promoted-capability source plus current repository state; fabricating
        # those records here would turn an untrusted name into safety evidence.
        verified_reuse_decision = None
        if plan.reuse_candidates:
            candidate_decision = "reuse"
            confidence = 0.55
        elif plan.deterministic_candidates:
            candidate_decision = "deterministic"
            confidence = 0.60
        else:
            candidate_decision = "cloud_inference"
            confidence = 0.85

        displacement_proofs = self._proofs_from_payload(getattr(plan, "displacement_proofs", []) or [])
        valid_proof_candidates = {
            proof.candidate_name
            for proof in displacement_proofs
            if self._proof_is_valid_for_plan(proof, plan.deterministic_candidates)
        }
        enforceable_displacements = sorted(
            set(getattr(plan, "enforceable_displacements", []) or []) & valid_proof_candidates
        )

        ambiguous = confidence < 0.75
        recommended_decision = "escalate" if ambiguous else candidate_decision
        recommended_rung = "escalate" if ambiguous else "selected_provider"

        # Now, set the final decision and enforced flag.
        if self.mode == "phase2_shadow" or self.mode == "shadow":
            # In shadow modes, we always run the provider and never enforce.
            decision = "cloud_inference"
            enforced = False
            selected_rung = "selected_provider"
        else:  # phase2_enforce
            # Phase 2 enforcement ONLY triggers when we have enforceable_displacements with proof.
            # This prevents keyword-detected candidates from becoming enforced displacements.
            if self.mode == "phase2_enforce" and enforceable_displacements:
                # Proof eligibility is real, but no deterministic transform
                # executor is connected to Executor.execute() yet. Do not claim
                # enforcement or suppress the provider path.
                decision = "cloud_inference"
                enforced = False
                selected_rung = "selected_provider"
                candidate_decision = "deterministic"
                confidence = 0.95
            else:
                decision = "cloud_inference"
                enforced = False
                selected_rung = "selected_provider"

        if self.mode == "phase2_enforce" and enforceable_displacements and not enforced:
            reason = (
                "Phase 2 proof eligible, but deterministic executor is unavailable; "
                "provider execution is preserved."
            )
        elif self.mode == "phase2_enforce" and enforced:
            reason = (
                f"Phase 2 enforce: enforcing deterministic displacement via verified proof. "
                f"Ambiguity policy recommends {recommended_decision}."
            )
        elif candidate_decision == "reuse":
            reason = "Reuse candidate observed; promoted capability lookup and current fingerprint verification are required."
        else:
            if self.mode == "phase2_enforce" and not enforceable_displacements:
                reason = (
                    "Phase 2 enforce: no verified enforceable_displacements; "
                    "deterministic_candidates are hypotheses pending paired ablation proof."
                )
            else:
                reason = (
                    f"Phase 1 observed candidate={candidate_decision}; ambiguity policy recommends "
                    f"{recommended_decision}, but shadow mode preserves provider execution."
                )

        return ComputeGateDecision(
            gate_id="cgate_" + uuid.uuid4().hex[:20],
            plan_id=plan.plan_id,
            mode=self.mode,
            decision=decision,
            candidate_decision=candidate_decision,
            allowed=True,
            enforced=enforced,
            confidence=confidence,
            ambiguous=ambiguous,
            tiebreaker_policy="escalate_never_suppress_on_ambiguity",
            selected_rung=selected_rung,
            recommended_rung=recommended_rung,
            reason=reason,
            predicted_avoidable_work=avoidable,
            created_at=self._now(),
        )

    def route_adaptively(
        self,
        plan: ComputePlan,
        gate: ComputeGateDecision,
        provider_candidates: Optional[List[Dict[str, Any]]] = None,
        estimated_cost_usd: Optional[float] = None,
        risk_class: str = "low",
        negative_capabilities: Optional[List[Dict[str, Any]]] = None,
        friction_profiles: Optional[List[Dict[str, Any]]] = None,
    ) -> AdaptiveRoutingDecision:
        """Phase 4 helper: compute adaptive routing combining budgets, economist, and risk.
        
        This is the Phase 4 entry point that applies budget enforcement,
        Provider Economist routing, and approval gates.
        """
        return self.adaptive_controller.route_adaptively(
            plan=plan,
            gate=gate,
            provider_candidates=provider_candidates,
            estimated_cost_usd=estimated_cost_usd,
            risk_class=risk_class,
            negative_capabilities=negative_capabilities,
            friction_profiles=friction_profiles,
        )

    @classmethod
    def suppression_policy(cls, evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Require positive, complete evidence before recommending suppression."""
        evidence = dict(evidence or {})
        confidence = cls._optional_float(evidence.get("confidence")) or 0.0
        checks = {
            "proof_verified": evidence.get("proof_verified") is True,
            "behavior_preserved": evidence.get("behavior_preserved") is True,
            "fallback_available": evidence.get("fallback_available") is True,
            "confidence_sufficient": confidence >= cls.SUPPRESSION_CONFIDENCE_THRESHOLD,
            "not_high_risk": evidence.get("high_risk") is False,
            "no_required_work": evidence.get("required_work_remaining") is False,
        }
        eligible = all(checks.values())
        return {
            "beast_object_type": "compute_suppression_policy_decision",
            "version": "1.0",
            "eligible": eligible,
            "decision": "suppress" if eligible else "escalate",
            "confidence": confidence,
            "threshold": cls.SUPPRESSION_CONFIDENCE_THRESHOLD,
            "checks": checks,
            "missing_or_failed": sorted(name for name, passed in checks.items() if not passed),
            "tiebreaker_policy": "escalate_never_suppress_on_ambiguity",
        }

    def _deterministic_candidates(self, text_parts: Iterable[str], metadata: Dict[str, Any]) -> List[str]:
        text = "\n".join(text_parts).lower()[:50_000]
        candidates = []
        declared = metadata.get("deterministic_candidates") or []
        if isinstance(declared, list):
            candidates.extend(str(item) for item in declared if str(item).strip())
        for name, signals in self.DETERMINISTIC_SIGNALS.items():
            if any(re.search(r"\b" + re.escape(signal) + r"\b", text) for signal in signals):
                candidates.append(name)
        return sorted(set(candidates))

    def _validated_displacement_proofs(
        self, metadata: Dict[str, Any], deterministic_candidates: List[str]
    ) -> List[DeterministicDisplacementProof]:
        proofs = self._proofs_from_payload(metadata.get("displacement_proofs") or [])
        return [proof for proof in proofs if self._proof_is_valid_for_plan(proof, deterministic_candidates)]

    @staticmethod
    def _proofs_from_payload(payload: Any) -> List[DeterministicDisplacementProof]:
        if not isinstance(payload, list):
            return []
        field_names = set(DeterministicDisplacementProof.__dataclass_fields__)
        proofs = []
        for item in payload:
            if isinstance(item, DeterministicDisplacementProof):
                proofs.append(item)
                continue
            if not isinstance(item, dict):
                continue
            values = {key: value for key, value in item.items() if key in field_names}
            try:
                proofs.append(DeterministicDisplacementProof(**values))
            except (TypeError, ValueError):
                continue
        return proofs

    def _proof_is_valid_for_plan(
        self, proof: DeterministicDisplacementProof, deterministic_candidates: List[str]
    ) -> bool:
        if not proof.is_enforceable():
            return False
        if not self.allowlist.is_allowlisted(proof.candidate_name):
            return False
        if proof.candidate_name not in deterministic_candidates:
            return False
        if proof.allowed_transform != proof.candidate_name:
            return False
        impact = proof.impact_fingerprint
        if impact is not None:
            if not isinstance(impact, dict):
                return False
            if impact.get("state") not in (None, "active"):
                return False
            if impact.get("reusable") is False:
                return False
        return True

    @staticmethod
    def _reuse_candidates(metadata: Dict[str, Any]) -> List[str]:
        raw = metadata.get("reuse_candidates") or metadata.get("skills") or []
        if isinstance(raw, dict):
            raw = list(raw.keys())
        if not isinstance(raw, list):
            return []
        return sorted({str(item)[:160] for item in raw if str(item).strip()})

    @staticmethod
    def _fingerprint(messages: List[Any], model: str, provider: str, tools: Any) -> str:
        safe_messages = []
        for item in messages:
            role = str(item.get("role") or "unknown") if isinstance(item, dict) else "unknown"
            text = ComputeGovernor._message_text(item)
            safe_messages.append({"role": role, "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()})
        tool_names = []
        for tool in tools or []:
            if isinstance(tool, dict):
                function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
                tool_names.append(str(function.get("name") or tool.get("name") or ""))
        raw = json.dumps({"messages": safe_messages, "model": model, "provider": provider, "tools": sorted(tool_names)}, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _message_text(item: Any) -> str:
        if not isinstance(item, dict):
            return str(item or "")
        content = item.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(part.get("text") or "") if isinstance(part, dict) else str(part) for part in content)
        return str(content or "")

    @staticmethod
    def _optional_float(value: Any):
        if value in (None, ""):
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
