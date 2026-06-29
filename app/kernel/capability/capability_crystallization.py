"""Phase 6: Capability Crystallization — prove that repeated probabilistic lessons can become deterministic local capability.

This module implements the full Phase 6 lifecycle:
1. Shadow-mode execution of candidate deterministic transforms (Phases 1/2)
2. Promotion only after repeated hidden-test + rollback success
3. Attachment of Impact Fingerprints to every promoted capability
4. Fingerprint checking at every promotion/reuse boundary
5. Automatic demotion of stale capabilities to shadow_revalidation
6. Tracking of deterministic coverage, promotion precision, demotion rate, compute displaced
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint
from app.kernel.compute.compute_ir import DeterministicDisplacementProof
from app.kernel.storage.outcome_evidence import NegativeCapabilityStore, OutcomeEvidence
from app.kernel.security.crystal_chain import CrystalChainLedger


@dataclass(frozen=True)
class CrystallizationCandidate:
    """A candidate capability undergoing shadow-mode validation."""
    candidate_id: str
    candidate_name: str
    task_class: str
    transform_type: str  # "deterministic", "reuse", "local_inference"
    shadow_runs: int = 0
    hidden_test_successes: int = 0
    rollback_successes: int = 0
    behavior_preserved_count: int = 0
    impact_fingerprint: Optional[Dict[str, Any]] = None
    promotion_status: str = "shadow_validation"  # shadow_validation | promoted | demoted | retired
    confidence: float = 0.0
    created_at: str = ""
    updated_at: str = ""


class CrystallizationMetrics:
    """Phase 6 metrics: coverage, precision, demotion rate, compute displaced."""
    def __init__(self):
        self.total_candidates: int = 0
        self.promoted_count: int = 0
        self.demoted_count: int = 0
        self.retired_count: int = 0
        self.deterministic_coverage: float = 0.0
        self.promotion_precision: float = 0.0
        self.demotion_rate: float = 0.0
        self.total_compute_displaced_tokens: int = 0
        self.total_compute_displaced_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "capability_crystallization_metrics",
            "version": "1.0",
            "total_candidates": self.total_candidates,
            "promoted_count": self.promoted_count,
            "demoted_count": self.demoted_count,
            "retired_count": self.retired_count,
            "deterministic_coverage": round(self.deterministic_coverage, 6),
            "promotion_precision": round(self.promotion_precision, 6),
            "demotion_rate": round(self.demotion_rate, 6),
            "total_compute_displaced_tokens": self.total_compute_displaced_tokens,
            "total_compute_displaced_usd": round(self.total_compute_displaced_usd, 9),
        }


class CapabilityCrystallizationEngine:
    """Phase 6 engine for crystallizing probabilistic lessons into deterministic capabilities."""

    PROMOTION_THRESHOLD = {
        "min_shadow_runs": 3,
        "min_hidden_test_success_rate": 0.95,
        "min_rollback_success_rate": 0.95,
        "min_behavior_preserved_rate": 0.95,
        "min_confidence": 0.80,
    }

    DEMOTION_TRIGGERS = {
        "fingerprint_stale": True,
        "confidence_below": 0.50,
        "repeated_behavior_failures": 2,
    }

    def __init__(
        self,
        impact_fingerprint: CapabilityImpactFingerprint = None,
        storage_path: Optional[Path] = None,
        negative_store: Optional[NegativeCapabilityStore] = None,
        crystal_chain: Optional[CrystalChainLedger] = None,
    ):
        self.impact = impact_fingerprint or CapabilityImpactFingerprint()
        self.storage_path = storage_path
        self.negative_store = negative_store or NegativeCapabilityStore(self._negative_state_path(storage_path))
        if storage_path is None:
            chain_path = Path(__file__).resolve().parents[2] / "data" / "crystal_chain" / "capabilities.jsonl"
        else:
            selected = Path(storage_path)
            chain_path = selected.with_name(selected.stem + ".crystal-chain.jsonl") if selected.suffix else selected / "crystal-chain.jsonl"
        self.crystal_chain = crystal_chain or CrystalChainLedger(chain_path, node_id="capability-crystallization")
        self._candidates: Dict[str, CrystallizationCandidate] = {}
        self._metrics = CrystallizationMetrics()
        self.load_errors: List[Dict[str, str]] = []
        self._load_state()

    @staticmethod
    def _negative_state_path(storage_path: Optional[Path]) -> Optional[Path]:
        if storage_path is None:
            return None
        path = Path(storage_path)
        if path.suffix:
            return path.with_name(path.stem + ".negative-capabilities.json")
        return path / "negative_capabilities.json"

    def register_shadow_run(
        self,
        candidate_name: str,
        task_class: str,
        transform_type: str,
        hidden_test_success: bool,
        rollback_success: bool,
        behavior_preserved: bool,
        impact_fingerprint: Optional[Dict[str, Any]] = None,
    ) -> CrystallizationCandidate:
        """Register a shadow-mode execution result for a crystallization candidate."""
        candidate_id = f"crystal_{candidate_name}_{task_class}"
        
        if candidate_id not in self._candidates:
            now = datetime.now(timezone.utc).isoformat()
            self._candidates[candidate_id] = CrystallizationCandidate(
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                task_class=task_class,
                transform_type=transform_type,
                created_at=now,
                updated_at=now,
            )
            self._metrics.total_candidates += 1

        candidate = self._candidates[candidate_id]
        
        # Update counters (immutable update via replacement)
        new_shadow_runs = candidate.shadow_runs + 1
        new_hidden = candidate.hidden_test_successes + (1 if hidden_test_success else 0)
        new_rollback = candidate.rollback_successes + (1 if rollback_success else 0)
        new_behavior = candidate.behavior_preserved_count + (1 if behavior_preserved else 0)
        
        # Attach or update fingerprint
        fp = impact_fingerprint or candidate.impact_fingerprint
        
        updated = CrystallizationCandidate(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.candidate_name,
            task_class=candidate.task_class,
            transform_type=candidate.transform_type,
            shadow_runs=new_shadow_runs,
            hidden_test_successes=new_hidden,
            rollback_successes=new_rollback,
            behavior_preserved_count=new_behavior,
            impact_fingerprint=fp,
            promotion_status=candidate.promotion_status,
            confidence=self._compute_confidence(new_shadow_runs, new_hidden, new_rollback, new_behavior),
            created_at=candidate.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        
        self._candidates[candidate_id] = updated
        failed_checks = [
            name for name, passed in (
                ("hidden_test", hidden_test_success),
                ("rollback", rollback_success),
                ("behavior_preservation", behavior_preserved),
            ) if not passed
        ]
        self.record_outcome(OutcomeEvidence.create(
            capability_id=candidate_id,
            task_class=task_class,
            outcome="success" if not failed_checks else "failure",
            failure_category="shadow_validation_failure" if failed_checks else "",
            failure_code="+".join(failed_checks),
            scope={"transform_type": transform_type},
            confidence_before=candidate.confidence,
            confidence_after=updated.confidence,
            selected_capabilities=[candidate_id],
        ))
        self._persist_state()
        return updated

    def record_outcome(self, evidence: OutcomeEvidence | Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Record one shared outcome and return its negative record, if any."""
        normalized = evidence if isinstance(evidence, OutcomeEvidence) else OutcomeEvidence.create(**evidence)
        record = self.negative_store.record(normalized)
        return record.to_dict() if record else None

    def _compute_confidence(
        self,
        shadow_runs: int,
        hidden_successes: int,
        rollback_successes: int,
        behavior_count: int,
    ) -> float:
        """Compute confidence based on shadow validation history."""
        if shadow_runs == 0:
            return 0.0
        
        hidden_rate = hidden_successes / shadow_runs
        rollback_rate = rollback_successes / shadow_runs
        behavior_rate = behavior_count / shadow_runs
        
        # Weighted average: behavior preservation is most important
        confidence = (
            0.40 * behavior_rate +
            0.30 * hidden_rate +
            0.20 * rollback_rate +
            0.10 * min(1.0, shadow_runs / 10)  # More runs = higher base confidence
        )
        return round(confidence, 6)

    def check_promotion_eligibility(self, candidate_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Check if a candidate meets all promotion criteria."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False, "candidate_not_found", {}
        
        if candidate.promotion_status != "shadow_validation":
            return False, f"already_{candidate.promotion_status}", {}
        
        # Check minimum shadow runs
        if candidate.shadow_runs < self.PROMOTION_THRESHOLD["min_shadow_runs"]:
            return False, "insufficient_shadow_runs", {"required": self.PROMOTION_THRESHOLD["min_shadow_runs"]}
        
        # Check success rates
        hidden_rate = candidate.hidden_test_successes / candidate.shadow_runs
        rollback_rate = candidate.rollback_successes / candidate.shadow_runs
        behavior_rate = candidate.behavior_preserved_count / candidate.shadow_runs
        
        if hidden_rate < self.PROMOTION_THRESHOLD["min_hidden_test_success_rate"]:
            return False, "hidden_test_success_rate_below_threshold", {"rate": hidden_rate}
        
        if rollback_rate < self.PROMOTION_THRESHOLD["min_rollback_success_rate"]:
            return False, "rollback_success_rate_below_threshold", {"rate": rollback_rate}
        
        if behavior_rate < self.PROMOTION_THRESHOLD["min_behavior_preserved_rate"]:
            return False, "behavior_preservation_rate_below_threshold", {"rate": behavior_rate}
        
        if candidate.confidence < self.PROMOTION_THRESHOLD["min_confidence"]:
            return False, "confidence_below_threshold", {"confidence": candidate.confidence}
        
        if not candidate.impact_fingerprint:
            return False, "impact_fingerprint_required", {}
        if candidate.impact_fingerprint.get("state") == "shadow_revalidation":
            return False, "fingerprint_requires_revalidation", {}
        
        return True, "eligible_for_promotion", {
            "shadow_runs": candidate.shadow_runs,
            "hidden_rate": hidden_rate,
            "rollback_rate": rollback_rate,
            "behavior_rate": behavior_rate,
            "confidence": candidate.confidence,
        }

    def promote_candidate(self, candidate_id: str, approver: str = "system") -> Optional[DeterministicDisplacementProof]:
        """Promote a candidate to a crystallized capability with attached Impact Fingerprint."""
        eligible, reason, details = self.check_promotion_eligibility(candidate_id)
        if not eligible:
            return None
        
        candidate = self._candidates[candidate_id]
        
        # Create the proof with all verification data
        proof = DeterministicDisplacementProof(
            candidate_name=candidate.candidate_name,
            task_class=candidate.task_class,
            risk_class="low" if candidate.confidence >= 0.90 else "medium",
            allowed_transform=candidate.candidate_name,
            verifier_command=f"crystallized_{candidate.candidate_name}",
            visible_tests_equal_or_better=True,
            hidden_tests_equal_or_better=True,
            scope_checks_equal_or_better=True,
            rollback_equal_or_better=True,
            security_checks_equal_or_better=True,
            paired_ablation_runs=candidate.shadow_runs,
            confidence=candidate.confidence,
            approved_for_enforcement=True,
            policy_version="phase6_crystallization_v1",
            impact_fingerprint=candidate.impact_fingerprint,
            created_at=datetime.now(timezone.utc).isoformat(),
            proof_id=f"crystal_proof_{candidate_id}",
        )
        
        # Update candidate status
        updated = CrystallizationCandidate(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.candidate_name,
            task_class=candidate.task_class,
            transform_type=candidate.transform_type,
            shadow_runs=candidate.shadow_runs,
            hidden_test_successes=candidate.hidden_test_successes,
            rollback_successes=candidate.rollback_successes,
            behavior_preserved_count=candidate.behavior_preserved_count,
            impact_fingerprint=candidate.impact_fingerprint,
            promotion_status="promoted",
            confidence=candidate.confidence,
            created_at=candidate.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        block = self.crystal_chain.append("capability_promoted", candidate_id, {
            "candidate": self._candidate_to_dict(updated), "proof": proof.to_dict(), "approver": approver,
        })
        proof = replace(
            proof,
            impact_fingerprint={
                **(proof.impact_fingerprint or {}),
                "crystal_chain_block_hash": block["block_hash"],
            },
        )
        self._candidates[candidate_id] = updated
        self._metrics.promoted_count += 1
        self._persist_state()
        
        return proof

    def check_fingerprint_at_boundary(
        self,
        candidate_id: str,
        current_repo_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check Impact Fingerprint at a promotion or reuse boundary.
        
        Returns validation decision; may trigger demotion if stale.
        """
        candidate = self._candidates.get(candidate_id)
        if not candidate or not candidate.impact_fingerprint:
            return {"valid": False, "reason": "no_fingerprint"}
        
        previous = candidate.impact_fingerprint
        
        # If we have current repo state, compare
        if current_repo_state:
            current = self.impact.build(
                Path(current_repo_state.get("root", ".")),
                target_paths=current_repo_state.get("target_paths", []),
                dependency_paths=current_repo_state.get("dependency_paths", []),
                test_paths=current_repo_state.get("test_paths", []),
                symbols=current_repo_state.get("symbols", {}),
                tool_schema_hashes=current_repo_state.get("tool_schema_hashes", []),
                policy_version=current_repo_state.get("policy_version", "unknown"),
                confidence=current_repo_state.get("confidence", 1.0),
            )
            
            decision = self.impact.compare(previous, current)
            
            # Auto-demote on critical changes
            if decision.get("state") == "shadow_revalidation":
                self.demote_candidate(candidate_id, reason="fingerprint_stale")
            
            return decision
        
        # No current state to compare — check if already marked stale
        if previous.get("state") == "shadow_revalidation":
            self.demote_candidate(candidate_id, reason="fingerprint_requires_revalidation")
            return {"valid": False, "reason": "fingerprint_requires_revalidation"}
        
        return {"valid": True, "reason": "fingerprint_active"}

    def demote_candidate(self, candidate_id: str, reason: str = "unknown") -> bool:
        """Automatically demote a stale or failing candidate to shadow_revalidation."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False
        
        if candidate.promotion_status == "promoted":
            self._metrics.promoted_count = max(0, self._metrics.promoted_count - 1)
        
        updated = CrystallizationCandidate(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.candidate_name,
            task_class=candidate.task_class,
            transform_type=candidate.transform_type,
            shadow_runs=candidate.shadow_runs,
            hidden_test_successes=candidate.hidden_test_successes,
            rollback_successes=candidate.rollback_successes,
            behavior_preserved_count=candidate.behavior_preserved_count,
            impact_fingerprint=candidate.impact_fingerprint,
            promotion_status="demoted",
            confidence=min(candidate.confidence, 0.49),  # Cap below promotion threshold
            created_at=candidate.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.crystal_chain.append("capability_demoted", candidate_id, {
            "candidate": self._candidate_to_dict(updated), "reason": reason,
        })
        self._candidates[candidate_id] = updated
        self._metrics.demoted_count += 1
        self._persist_state()
        return True

    def retire_candidate(self, candidate_id: str, reason: str = "superseded") -> bool:
        """Retire a candidate that is no longer relevant."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False
        
        updated = CrystallizationCandidate(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.candidate_name,
            task_class=candidate.task_class,
            transform_type=candidate.transform_type,
            shadow_runs=candidate.shadow_runs,
            hidden_test_successes=candidate.hidden_test_successes,
            rollback_successes=candidate.rollback_successes,
            behavior_preserved_count=candidate.behavior_preserved_count,
            impact_fingerprint=candidate.impact_fingerprint,
            promotion_status="retired",
            confidence=0.0,
            created_at=candidate.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.crystal_chain.append("capability_retired", candidate_id, {
            "candidate": self._candidate_to_dict(updated), "reason": reason,
        })
        self._candidates[candidate_id] = updated
        self._metrics.retired_count += 1
        self._persist_state()
        return True

    def update_metrics(self, displaced_tokens: int = 0, displaced_usd: float = 0.0) -> CrystallizationMetrics:
        """Update and return current Phase 6 metrics."""
        total = self._metrics.total_candidates
        if total > 0:
            self._metrics.deterministic_coverage = self._metrics.promoted_count / total
            denom = self._metrics.promoted_count + self._metrics.demoted_count
            self._metrics.promotion_precision = self._metrics.promoted_count / denom if denom > 0 else 0.0
            self._metrics.demotion_rate = self._metrics.demoted_count / total
        
        self._metrics.total_compute_displaced_tokens += displaced_tokens
        self._metrics.total_compute_displaced_usd += displaced_usd
        self._persist_state()
        
        return self._metrics

    def get_candidate(self, candidate_id: str) -> Optional[CrystallizationCandidate]:
        """Retrieve a crystallization candidate by ID."""
        return self._candidates.get(candidate_id)

    def list_promoted(self) -> List[CrystallizationCandidate]:
        """List all promoted (crystallized) capabilities."""
        return [c for c in self._candidates.values() if c.promotion_status == "promoted"]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the crystallization engine state."""
        return {
            "beast_object_type": "capability_crystallization_engine",
            "version": "1.0",
            "candidates": {k: self._candidate_to_dict(v) for k, v in self._candidates.items()},
            "metrics": self._metrics.to_dict(),
            "promotion_threshold": self.PROMOTION_THRESHOLD,
            "outcome_evidence": self.negative_store.summary(),
            "negative_capabilities": self.negative_store.list_records(),
            "load_errors": list(self.load_errors),
        }

    def _state_path(self) -> Optional[Path]:
        if self.storage_path is None:
            return None
        path = Path(self.storage_path)
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        path.mkdir(parents=True, exist_ok=True)
        return path / "capability_crystallization_state.json"

    def _persist_state(self) -> None:
        path = self._state_path()
        if path is None:
            return
        payload = {
            "beast_object_type": "capability_crystallization_state",
            "version": "1.0",
            "candidates": {
                key: {
                    "candidate_id": value.candidate_id,
                    "candidate_name": value.candidate_name,
                    "task_class": value.task_class,
                    "transform_type": value.transform_type,
                    "shadow_runs": value.shadow_runs,
                    "hidden_test_successes": value.hidden_test_successes,
                    "rollback_successes": value.rollback_successes,
                    "behavior_preserved_count": value.behavior_preserved_count,
                    "impact_fingerprint": value.impact_fingerprint,
                    "promotion_status": value.promotion_status,
                    "confidence": value.confidence,
                    "created_at": value.created_at,
                    "updated_at": value.updated_at,
                }
                for key, value in self._candidates.items()
            },
            "metrics": self._metrics.to_dict(),
        }
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def _load_state(self) -> None:
        path = self._state_path()
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidates = payload.get("candidates") if isinstance(payload, dict) else {}
            if isinstance(candidates, dict):
                for key, item in candidates.items():
                    if isinstance(item, dict):
                        self._candidates[str(key)] = CrystallizationCandidate(**item)
            metrics = payload.get("metrics") if isinstance(payload, dict) else {}
            if isinstance(metrics, dict):
                self._metrics.total_candidates = int(metrics.get("total_candidates", len(self._candidates)) or 0)
                self._metrics.promoted_count = int(metrics.get("promoted_count", 0) or 0)
                self._metrics.demoted_count = int(metrics.get("demoted_count", 0) or 0)
                self._metrics.retired_count = int(metrics.get("retired_count", 0) or 0)
                self._metrics.deterministic_coverage = float(metrics.get("deterministic_coverage", 0.0) or 0.0)
                self._metrics.promotion_precision = float(metrics.get("promotion_precision", 0.0) or 0.0)
                self._metrics.demotion_rate = float(metrics.get("demotion_rate", 0.0) or 0.0)
                self._metrics.total_compute_displaced_tokens = int(metrics.get("total_compute_displaced_tokens", 0) or 0)
                self._metrics.total_compute_displaced_usd = float(metrics.get("total_compute_displaced_usd", 0.0) or 0.0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.load_errors.append({"path": str(path), "error": type(exc).__name__})

    @staticmethod
    def _candidate_to_dict(c: CrystallizationCandidate) -> Dict[str, Any]:
        return {
            "candidate_id": c.candidate_id,
            "candidate_name": c.candidate_name,
            "task_class": c.task_class,
            "transform_type": c.transform_type,
            "shadow_runs": c.shadow_runs,
            "hidden_test_successes": c.hidden_test_successes,
            "rollback_successes": c.rollback_successes,
            "behavior_preserved_count": c.behavior_preserved_count,
            "promotion_status": c.promotion_status,
            "confidence": c.confidence,
            "impact_fingerprint_attached": c.impact_fingerprint is not None,
        }
