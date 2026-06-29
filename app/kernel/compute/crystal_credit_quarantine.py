"""Quarantine stored crystal credits when runtime safety gates fail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseRequest
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage, SemanticComputeCredit


@dataclass
class CrystalCreditQuarantine:
    storage: DurableInferenceStorage
    semantic_cache: LocalSemanticCache | None = None

    def quarantine_for_request(
        self,
        request: CrystalReuseRequest,
        *,
        reason: str,
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        targets = self._matching_active_credits(request)
        quarantined = []
        for credit in targets:
            updated = self.storage.mark_stale(credit.credit_id, reason=reason, evidence=evidence)
            if updated is not None:
                quarantined.append({
                    "credit_id": updated.credit_id,
                    "artifact_type": updated.artifact_type,
                    "reuse_state": updated.reuse_state,
                    "quarantine_reason": reason,
                })
        semantic_cache_receipt = None
        if self.semantic_cache is not None:
            semantic_cache_receipt = self.semantic_cache.quarantine(
                task_class=request.task_class,
                repo_fingerprint=request.repo_fingerprint or "n/a",
                credit_ids=[item["credit_id"] for item in quarantined],
                reason=reason,
            )
        return {
            "beast_object_type": "crystal_credit_quarantine_receipt",
            "version": "1.0",
            "reason": reason,
            "matched_count": len(targets),
            "quarantined_count": len(quarantined),
            "quarantined": quarantined,
            "semantic_cache": semantic_cache_receipt,
        }

    def _matching_active_credits(self, request: CrystalReuseRequest) -> List[SemanticComputeCredit]:
        matches: List[SemanticComputeCredit] = []
        parameter_hash = self.storage._parameter_hash(request.parameters)
        answer_id = self.storage._answer_credit_id(request.prompt_hash, request.model, parameter_hash)
        for credit in self.storage.credits.values():
            if credit.reuse_state != "active":
                continue
            if credit.credit_id == answer_id:
                matches.append(credit)
                continue
            if credit.task_class == request.task_class and credit.repo_fingerprint == (request.repo_fingerprint or "n/a"):
                matches.append(credit)
        return matches
