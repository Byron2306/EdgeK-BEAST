"""Phase 3: Verified Reuse - avoid recomputing outcomes already captured as local capabilities.

Phase 3 enables BEAST to match task envelopes to Chronicle lessons and promoted capabilities,
requiring an active Impact Fingerprint before reuse, and replaying deterministic verification
before accepting a reused outcome.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint


class VerifiedReuseEngine:
    """Match tasks to verified capabilities and determine safe reuse."""

    def __init__(self, impact_fingerprint: Optional[CapabilityImpactFingerprint] = None):
        self.impact = impact_fingerprint or CapabilityImpactFingerprint()
        self.metrics = VerifiedReuseMetrics()

    def match_task_to_capability(
        self,
        task_envelope: Dict[str, Any],
        available_capabilities: List[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], float, str]:
        """Match a task envelope to a promoted capability.
        
        Returns: (matched_capability, confidence, reason)
        """
        if not available_capabilities:
            return None, 0.0, "no_capabilities_available"
        
        task_class = task_envelope.get("task_class", "")
        task_hash = self._task_signature(task_envelope)
        
        best_match = None
        best_confidence = 0.0
        best_reason = ""
        
        for cap in available_capabilities:
            # Check task class match
            cap_task_class = cap.get("task_class", "")
            if cap_task_class != task_class:
                continue
            
            # Check fingerprint validity
            fingerprint = cap.get("impact_fingerprint")
            if not fingerprint:
                continue
            
            # Verify fingerprint is active
            if fingerprint.get("state") == "shadow_revalidation":
                continue
            
            # Compute match confidence
            confidence = cap.get("confidence", 0.5)
            
            # Check if task signature matches
            cap_signature = cap.get("task_signature", "")
            if cap_signature == task_hash:
                confidence = min(confidence * 1.2, 0.95)  # Boost for exact match
                reason = "exact_task_signature_match"
            else:
                reason = "task_class_match"
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = cap
                best_reason = reason
        
        if best_match:
            return best_match, best_confidence, best_reason
        
        return None, 0.0, "no_matching_capability"
    
    def verify_reuse_safety(
        self,
        capability: Dict[str, Any],
        current_repo_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verify that reusing a capability is safe given current repository state.
        
        Requires:
        - Active Impact Fingerprint
        - Behavior preservation profile
        - Verifier contract
        - Risk class allowed
        """
        fingerprint = capability.get("impact_fingerprint", {})

        if not current_repo_state:
            return {
                "safe_to_reuse": False,
                "reason": "current_repo_state_required",
                "confidence": 0.0,
            }
        
        # Check fingerprint is active
        if fingerprint.get("state") == "shadow_revalidation":
            return {
                "safe_to_reuse": False,
                "reason": "fingerprint_requires_revalidation",
                "confidence": 0.0,
            }
        
        # Check confidence threshold
        impact_decision = self.impact.compare(fingerprint, current_repo_state)
        if not impact_decision.get("reusable", False):
            return {
                "safe_to_reuse": False,
                "reason": "current_repository_drift_requires_revalidation",
                "confidence": impact_decision.get("confidence", 0.0),
                "impact_decision": impact_decision,
            }

        confidence = min(
            float(fingerprint.get("confidence", capability.get("confidence", 0.0)) or 0.0),
            float(impact_decision.get("confidence", 0.0) or 0.0),
        )
        if confidence < 0.60:
            return {
                "safe_to_reuse": False,
                "reason": "confidence_below_threshold",
                "confidence": confidence,
            }
        
        # Check all required verification fields exist
        required_checks = [
            "visible_tests_equal_or_better",
            "hidden_tests_equal_or_better",
            "scope_checks_equal_or_better",
            "rollback_equal_or_better",
            "security_checks_equal_or_better",
        ]
        
        for check in required_checks:
            if not capability.get(check, False):
                return {
                    "safe_to_reuse": False,
                    "reason": f"missing_verification_{check}",
                    "confidence": confidence,
                }
        
        # Check paired ablation runs
        ablation_runs = capability.get("paired_ablation_runs", 0)
        if ablation_runs < 1:
            return {
                "safe_to_reuse": False,
                "reason": "insufficient_paired_ablation",
                "confidence": confidence,
            }
        
        # Check approved for enforcement
        if not capability.get("approved_for_enforcement", False):
            return {
                "safe_to_reuse": False,
                "reason": "not_approved_for_enforcement",
                "confidence": confidence,
            }
        
        return {
            "safe_to_reuse": True,
            "reason": "all_verification_checks_passed",
            "confidence": confidence,
            "impact_fingerprint_hash": fingerprint.get("fingerprint_hash"),
            "impact_decision": impact_decision,
        }
    
    def compute_reuse_decision(
        self,
        task_envelope: Dict[str, Any],
        available_capabilities: List[Dict[str, Any]],
        current_repo_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute the verified reuse decision for a task.
        
        Returns a decision record with:
        - decision: "reuse" | "escalate" | "cloud_inference"
        - matched_capability: capability dict or None
        - confidence: match confidence
        - verification: safety verification result
        - reason: human-readable explanation
        """
        matched, match_confidence, match_reason = self.match_task_to_capability(
            task_envelope, available_capabilities
        )
        
        if not matched:
            return {
                "beast_object_type": "verified_reuse_decision",
                "version": "1.0",
                "decision": "cloud_inference",
                "matched_capability": None,
                "confidence": 0.0,
                "verification": {"safe_to_reuse": False, "reason": match_reason},
                "reason": f"No matching capability: {match_reason}",
            }
        
        # Verify reuse safety
        verification = self.verify_reuse_safety(matched, current_repo_state)
        
        if verification["safe_to_reuse"]:
            return {
                "beast_object_type": "verified_reuse_decision",
                "version": "1.0",
                "decision": "reuse",
                "matched_capability": matched.get("candidate_name"),
                "confidence": verification["confidence"],
                "verification": verification,
                "reason": f"Verified reuse: {match_reason}, {verification['reason']}",
            }
        else:
            return {
                "beast_object_type": "verified_reuse_decision",
                "version": "1.0",
                "decision": "escalate",
                "matched_capability": matched.get("candidate_name"),
                "confidence": match_confidence,
                "verification": verification,
                "reason": f"Reuse blocked: {verification['reason']}; escalate to verify",
            }
    
    @staticmethod
    def _task_signature(task_envelope: Dict[str, Any]) -> str:
        """Compute a stable signature for a task envelope."""
        # Extract key fields for matching
        key_fields = {
            "task_class": task_envelope.get("task_class", ""),
            "purpose": task_envelope.get("purpose", ""),
            "metadata_hash": hashlib.sha256(
                json.dumps(task_envelope.get("metadata", {}), sort_keys=True).encode()
            ).hexdigest()[:16],
        }
        canonical = json.dumps(key_fields, sort_keys=True, separators=(",", ":"))
        return "sig:" + hashlib.sha256(canonical.encode()).hexdigest()[:32]


class VerifiedReuseMetrics:
    """Track Phase 3 reuse metrics: hit rate, avoided calls, false-reuse rate."""

    def __init__(self):
        self.total_reuse_decisions = 0
        self.reuse_approved = 0
        self.reuse_escalated = 0
        self.reuse_fallback = 0  # cloud_inference when no match
        self.false_reuse_count = 0  # Would need external verification to populate

    def record_decision(self, decision: Dict[str, Any]) -> None:
        """Record a reuse decision for metrics."""
        self.total_reuse_decisions += 1
        d = decision.get("decision", "unknown")
        if d == "reuse":
            self.reuse_approved += 1
        elif d == "escalate":
            self.reuse_escalated += 1
        elif d == "cloud_inference":
            self.reuse_fallback += 1

    def record_false_reuse(self) -> None:
        """Record a false reuse (behavior not preserved after reuse)."""
        self.false_reuse_count += 1

    def hit_rate(self) -> float:
        """Reuse hit rate: approved / total decisions."""
        if self.total_reuse_decisions == 0:
            return 0.0
        return self.reuse_approved / self.total_reuse_decisions

    def avoided_calls_estimate(self) -> int:
        """Estimated number of provider calls avoided via reuse."""
        return self.reuse_approved

    def false_reuse_rate(self) -> float:
        """False reuse rate: false_reuses / approved_reuses."""
        if self.reuse_approved == 0:
            return 0.0
        return self.false_reuse_count / self.reuse_approved

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metrics for reporting."""
        return {
            "beast_object_type": "verified_reuse_metrics",
            "version": "1.0",
            "total_reuse_decisions": self.total_reuse_decisions,
            "reuse_approved": self.reuse_approved,
            "reuse_escalated": self.reuse_escalated,
            "reuse_fallback_to_cloud": self.reuse_fallback,
            "false_reuse_count": self.false_reuse_count,
            "reuse_hit_rate": round(self.hit_rate(), 6),
            "avoided_calls_estimate": self.avoided_calls_estimate(),
            "false_reuse_rate": round(self.false_reuse_rate(), 6),
            "claim_boundary": "Metrics are internal counters; false_reuse requires external behavior verification.",
        }
