"""Phase 2 Deterministic Displacement Registry.

Manages the lifecycle of deterministic displacement proofs:
1. Candidate discovery (keyword signals → deterministic_candidates)
2. Paired shadow ablation (run in parallel, verify behavior preservation)
3. Proof creation (allowlist + verification results → DeterministicDisplacementProof)
4. Promotion to enforceable (proof approved → enforceable_displacements)
5. Enforcement gate (phase2_enforce only triggers on proven displacements)

This is the "promotion flow" that turns hypotheses into enforceable transforms.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.compute.compute_ir import DeterministicDisplacementProof
from app.kernel.governance.deterministic_allowlist import Phase2Allowlist, create_proof_from_allowlist


class DeterministicDisplacementRegistry:
    """Registry for managing deterministic displacement proofs and promotions."""

    def __init__(
        self,
        allowlist: Phase2Allowlist = None,
        storage_path: Optional[Path] = None,
    ):
        self.allowlist = allowlist or Phase2Allowlist()
        self.storage_path = storage_path
        self._proofs: Dict[str, DeterministicDisplacementProof] = {}
        self._promoted: List[str] = []  # candidate_names that are promoted

    def register_ablation_result(
        self,
        candidate_name: str,
        task_class: str,
        ablation_results: Dict[str, Any],
    ) -> Optional[DeterministicDisplacementProof]:
        """Register the result of a paired shadow ablation run.
        
        ablation_results should contain:
        - visible_tests_equal_or_better: bool
        - hidden_tests_equal_or_better: bool
        - scope_checks_equal_or_better: bool
        - rollback_equal_or_better: bool
        - security_checks_equal_or_better: bool
        - paired_ablation_runs: int (number of successful runs)
        - confidence: float
        - behavior_preserved: bool (overall result)
        """
        if not self.allowlist.is_allowlisted(candidate_name):
            return None  # Not on allowlist, cannot promote
        
        # Check if ablation passed all required checks
        spec = self.allowlist.get_spec(candidate_name)
        if not spec:
            return None
        
        required = spec.required_checks
        all_passed = all(ablation_results.get(check, False) for check in required)
        
        if not all_passed or not ablation_results.get("behavior_preserved", False):
            return None  # Ablation failed, cannot promote
        
        # Create the proof
        proof = create_proof_from_allowlist(
            candidate_name=candidate_name,
            task_class=task_class,
            allowlist=self.allowlist,
            visible_tests_equal_or_better=ablation_results.get("visible_tests_equal_or_better", False),
            hidden_tests_equal_or_better=ablation_results.get("hidden_tests_equal_or_better", False),
            scope_checks_equal_or_better=ablation_results.get("scope_checks_equal_or_better", False),
            rollback_equal_or_better=ablation_results.get("rollback_equal_or_better", False),
            security_checks_equal_or_better=ablation_results.get("security_checks_equal_or_better", False),
            paired_ablation_runs=ablation_results.get("paired_ablation_runs", 0),
            confidence=ablation_results.get("confidence", 0.0),
            approved_for_enforcement=ablation_results.get("approved_for_enforcement", False),
            policy_version=ablation_results.get("policy_version", "phase2_v1"),
            impact_fingerprint=ablation_results.get("impact_fingerprint"),
        )
        
        self._proofs[proof.proof_id] = proof
        return proof
    
    def approve_proof(self, proof_id: str, approver: str = "system") -> bool:
        """Approve a proof for enforcement.
        
        Returns True if approval succeeded.
        """
        proof = self._proofs.get(proof_id)
        if not proof:
            return False
        
        if not proof.is_enforceable():
            return False  # Proof doesn't meet criteria
        
        # Mark as approved (would need mutable proof in real impl, this is simplified)
        self._promoted.append(proof.candidate_name)
        return True
    
    def get_promoted_displacements(self, task_class: str = None) -> List[str]:
        """Get all promoted (enforceable) displacement candidates.
        
        Optionally filtered by task class.
        """
        if task_class:
            return [
                p.candidate_name for p in self._proofs.values()
                if p.candidate_name in self._promoted and p.task_class == task_class
            ]
        return list(self._promoted)
    
    def create_enforceable_plan_metadata(
        self,
        deterministic_candidates: List[str],
        task_class: str,
        ablation_results_by_candidate: Dict[str, Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create metadata for a ComputePlan that enables Phase 2 enforcement.
        
        This is the bridge: takes keyword-detected candidates + ablation results,
        produces enforceable_displacements metadata for the plan.
        
        Only candidates that:
        1. Are on the allowlist
        2. Have passing ablation results
        3. Meet proof criteria
        
        Will appear in enforceable_displacements.
        """
        ablation_results_by_candidate = ablation_results_by_candidate or {}
        enforceable = []
        proofs = []
        
        for candidate in deterministic_candidates:
            if not self.allowlist.is_allowlisted(candidate):
                continue  # Skip non-allowlisted
            
            ablation = ablation_results_by_candidate.get(candidate, {})
            
            # Try to create a proof
            proof = self.register_ablation_result(candidate, task_class, ablation)
            
            if proof and proof.is_enforceable():
                enforceable.append(candidate)
                proofs.append(proof.to_dict())
        
        return {
            "enforceable_displacements": enforceable,
            "displacement_proofs": proofs,
            "phase2_allowlist": self.allowlist.to_dict(),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry state."""
        return {
            "beast_object_type": "deterministic_displacement_registry",
            "version": "1.0",
            "allowlist": self.allowlist.to_dict(),
            "registered_proofs": len(self._proofs),
            "promoted_count": len(self._promoted),
            "promoted_candidates": self._promoted,
        }


def promote_candidate_after_ablation(
    candidate_name: str,
    task_class: str,
    ablation_run_count: int,
    verification_results: Dict[str, bool],
    registry: DeterministicDisplacementRegistry = None,
) -> Optional[DeterministicDisplacementProof]:
    """Convenience function: promote a candidate after successful ablation.
    
    This is the "promotion ceremony" - the moment a hypothesis becomes enforceable.
    """
    registry = registry or DeterministicDisplacementRegistry()
    
    # Merge ablation count into results
    results = dict(verification_results)
    results["paired_ablation_runs"] = ablation_run_count
    results["behavior_preserved"] = all(verification_results.values())
    results["approved_for_enforcement"] = True
    results["confidence"] = 0.90 if results["behavior_preserved"] else 0.50
    
    return registry.register_ablation_result(candidate_name, task_class, results)