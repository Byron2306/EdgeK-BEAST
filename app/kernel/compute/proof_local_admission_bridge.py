"""Advisory proof-local admission bridge for crystal runtime decisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseRequest
from app.kernel.compute.proof_local_compute import ProofRoutePlanner, ProofRouteRequest


SECRET_MARKERS = ("api_key", "authorization:", "bearer ", "hf_", "nvapi-", "password=", "secret=")


@dataclass(frozen=True)
class ProofLocalAdmissionContext:
    expected_repo_fingerprint: str = ""
    actual_repo_fingerprint: str = ""
    expected_provider_fingerprint: str = ""
    actual_provider_fingerprint: str = ""
    expected_lattice_hash: str = ""
    actual_lattice_hash: str = ""
    expected_risk_tier: str = ""
    actual_risk_tier: str = ""
    verifier_passed: bool = True
    candidate_response_preview: str = ""
    privacy_class: str = "public_metadata_only"
    required_verifiers: List[str] = field(default_factory=list)
    max_transfer_bytes: int = 5_000_000
    max_lan_rtt_ms: int = 200
    allow_trusted_lan: bool = True

    @classmethod
    def from_metadata(cls, metadata: Dict[str, Any]) -> "ProofLocalAdmissionContext":
        return cls(
            expected_repo_fingerprint=str(metadata.get("expected_repo_fingerprint") or metadata.get("repo_fingerprint") or ""),
            actual_repo_fingerprint=str(metadata.get("actual_repo_fingerprint") or metadata.get("repo_fingerprint") or ""),
            expected_provider_fingerprint=str(metadata.get("expected_provider_fingerprint") or ""),
            actual_provider_fingerprint=str(metadata.get("actual_provider_fingerprint") or ""),
            expected_lattice_hash=str(metadata.get("expected_lattice_hash") or ""),
            actual_lattice_hash=str(metadata.get("actual_lattice_hash") or ""),
            expected_risk_tier=str(metadata.get("expected_risk_tier") or metadata.get("risk_tier") or ""),
            actual_risk_tier=str(metadata.get("actual_risk_tier") or metadata.get("risk_tier") or ""),
            verifier_passed=bool(metadata.get("verifier_passed", True)),
            candidate_response_preview=str(metadata.get("candidate_response_preview") or ""),
            privacy_class=str(metadata.get("privacy_class") or "public_metadata_only"),
            required_verifiers=[str(item) for item in metadata.get("required_verifiers") or []],
            max_transfer_bytes=int(metadata.get("max_transfer_bytes") or 5_000_000),
            max_lan_rtt_ms=int(metadata.get("max_lan_rtt_ms") or 200),
            allow_trusted_lan=bool(metadata.get("allow_trusted_lan", True)),
        )


class ProofLocalAdmissionBridge:
    """Create the documented proof-local route receipt before reuse/provider fallback."""

    def __init__(self, planner: Optional[ProofRoutePlanner] = None) -> None:
        self.planner = planner or ProofRoutePlanner()

    def evaluate(
        self,
        request: CrystalReuseRequest,
        *,
        advertisements: Optional[Iterable[Dict[str, Any]]] = None,
        context: Optional[ProofLocalAdmissionContext] = None,
    ) -> Dict[str, Any]:
        context = context or ProofLocalAdmissionContext.from_metadata(request.metadata)
        blockers = self._blockers(context)
        proof_request = ProofRouteRequest(
            task_class=request.task_class,
            space_id=str(request.metadata.get("space_id") or ""),
            manifest_hash=str(request.metadata.get("manifest_hash") or ""),
            privacy_class=context.privacy_class,
            required_verifiers=context.required_verifiers,
            max_lan_rtt_ms=context.max_lan_rtt_ms,
            max_transfer_bytes=context.max_transfer_bytes,
            risk_class=context.actual_risk_tier or "low",
            allow_trusted_lan=context.allow_trusted_lan and not blockers,
            fallback="local_crystal_gateway",
        )
        plan = self.planner.plan(proof_request, list(advertisements or []))
        receipt = {
            "beast_object_type": "proof_local_crystal_admission_receipt",
            "version": "1.0",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "request": {
                "task_class": request.task_class,
                "prompt_hash": request.prompt_hash,
                "repo_fingerprint": request.repo_fingerprint,
                "policy_version": request.policy_version,
                "privacy_class": context.privacy_class,
            },
            "proof_route_request": proof_request.__dict__,
            "proof_route_plan": plan,
            "reuse_allowed": not blockers,
            "provider_fallback_allowed": True,
            "blockers": blockers,
            "admission_order": [
                "task_policy_context",
                "proof_local_route_request",
                "commons_space_or_local_crystal",
                "semantic_page_lattice_chain",
                "crystal_reuse_gateway",
                "local_or_provider_fallback",
            ],
            "claim_boundary": "advisory proof-local admission receipt; crystal gateway/staleness policy still enforce reuse.",
        }
        receipt["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return receipt

    def _blockers(self, context: ProofLocalAdmissionContext) -> List[Dict[str, Any]]:
        blockers: List[Dict[str, Any]] = []
        self._mismatch(blockers, "repo_fingerprint_mismatch", context.expected_repo_fingerprint, context.actual_repo_fingerprint)
        self._mismatch(
            blockers,
            "provider_fingerprint_mismatch",
            context.expected_provider_fingerprint,
            context.actual_provider_fingerprint,
        )
        self._mismatch(blockers, "stale_lattice_hash", context.expected_lattice_hash, context.actual_lattice_hash)
        self._mismatch(blockers, "risk_tier_changed_requires_approval", context.expected_risk_tier, context.actual_risk_tier)
        if not context.verifier_passed:
            blockers.append({"reason": "failed_verifier", "reuse_allowed": False})
        lowered = context.candidate_response_preview.lower()
        if any(marker in lowered for marker in SECRET_MARKERS):
            blockers.append({"reason": "secret_present_in_response", "reuse_allowed": False})
        return blockers

    @staticmethod
    def _mismatch(blockers: List[Dict[str, Any]], reason: str, expected: str, actual: str) -> None:
        if expected and actual and expected != actual:
            blockers.append({"reason": reason, "expected": expected, "actual": actual, "reuse_allowed": False})
