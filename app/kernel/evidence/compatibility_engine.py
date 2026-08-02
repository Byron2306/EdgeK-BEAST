"""Deterministic evidence compatibility evaluation.

Compatibility classifies a retrieved crystal for a supplied current fingerprint.
It never authorizes application, mutation, promotion, or governance bypass.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.kernel.evidence.evidence_digest import sha256_digest
from app.kernel.evidence.evidence_ledger import EvidenceLedger
from app.kernel.evidence.evidence_store import EvidenceStore
from app.kernel.evidence.fingerprint_store import FingerprintStore

VERDICTS = {"EXACT", "ADAPTABLE", "REFERENCE", "REJECTED", "REVOKED"}


def _set(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        value = [value]
    return {str(v).strip().lower() for v in value if str(v).strip()}


def _languages(bundle: dict[str, Any]) -> set[str]:
    paths = ((bundle.get("task") or {}).get("components") or {}).get("affected_paths") or []
    suffixes = {Path(str(path)).suffix.lower() for path in paths}
    mapping = {".py":"python", ".js":"javascript", ".jsx":"javascript", ".ts":"typescript", ".tsx":"typescript", ".rs":"rust", ".go":"go", ".java":"java", ".kt":"kotlin", ".cs":"csharp"}
    return {mapping[s] for s in suffixes if s in mapping}


def _components(bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return ((bundle.get("task") or {}).get("components") or {}, (bundle.get("environment") or {}).get("components") or {})


@dataclass(frozen=True)
class CompatibilityPolicy:
    minimum_reference_score: float = 0.25
    require_policy_profile_match: bool = True
    require_runtime_system_match: bool = True

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CompatibilityPolicy":
        return cls(
            minimum_reference_score=max(0.0, min(float(payload.get("minimum_reference_score", 0.25)), 1.0)),
            require_policy_profile_match=bool(payload.get("require_policy_profile_match", True)),
            require_runtime_system_match=bool(payload.get("require_runtime_system_match", True)),
        )


class CompatibilityEngine:
    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).expanduser().resolve()
        self.store = EvidenceStore(self.root)
        self.fingerprints = FingerprintStore(self.root)
        self.ledger = EvidenceLedger(self.root)

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        evidence_id = str(payload.get("evidence_id") or "").strip()
        if not evidence_id:
            raise ValueError("evidence_id is required")
        evidence = self.store.get(evidence_id)
        if not evidence:
            raise KeyError(f"unknown evidence crystal: {evidence_id}")
        candidate = self.fingerprints.get(evidence_id)
        if not candidate:
            return self._receipt(evidence_id, "REJECTED", {}, ["missing_candidate_fingerprint"], payload)
        current = payload.get("current_fingerprint")
        if not isinstance(current, dict):
            raise ValueError("current_fingerprint is required")
        policy = CompatibilityPolicy.from_payload(payload)
        state = self.ledger.state(evidence_id)
        if state["status"] in {"revoked", "expired"}:
            return self._receipt(evidence_id, "REVOKED", {"ledger_state": False}, [f"ledger_{state['status']}"], payload, state=state)

        ct, ce = _components(candidate)
        qt, qe = _components(current)
        checks = {
            "task_digest": (candidate.get("task") or {}).get("digest") == (current.get("task") or {}).get("digest"),
            "environment_digest": (candidate.get("environment") or {}).get("digest") == (current.get("environment") or {}).get("digest"),
            "policy_profile": ce.get("policy_profile") == qe.get("policy_profile"),
            "runtime_system": (ce.get("runtime") or {}).get("system") == (qe.get("runtime") or {}).get("system"),
            "runtime_machine": (ce.get("runtime") or {}).get("machine") == (qe.get("runtime") or {}).get("machine"),
            "dependencies": ce.get("dependency_digest") == qe.get("dependency_digest"),
            "symbols": (ce.get("symbols") or {}).get("digest") == (qe.get("symbols") or {}).get("digest"),
            "git_head": (ce.get("git") or {}).get("head") == (qe.get("git") or {}).get("head"),
            "language_overlap": bool(_languages(candidate) & _languages(current)) or not _languages(candidate) or not _languages(current),
        }
        blockers: list[str] = []
        if policy.require_policy_profile_match and not checks["policy_profile"]:
            blockers.append("policy_profile_mismatch")
        if policy.require_runtime_system_match and not checks["runtime_system"]:
            blockers.append("runtime_system_mismatch")
        if not checks["language_overlap"]:
            blockers.append("language_mismatch")

        retrieval_score = float(payload.get("retrieval_score") or 0.0)
        if blockers:
            verdict = "REJECTED"
        elif checks["task_digest"] and checks["environment_digest"]:
            verdict = "EXACT"
        elif checks["task_digest"]:
            verdict = "ADAPTABLE"
        elif retrieval_score >= policy.minimum_reference_score:
            verdict = "REFERENCE"
        else:
            verdict = "REJECTED"
            blockers.append("insufficient_task_similarity")
        return self._receipt(evidence_id, verdict, checks, blockers, payload, state=state)

    def _receipt(self, evidence_id: str, verdict: str, checks: dict[str, bool], blockers: list[str], payload: dict[str, Any], *, state: dict[str, Any] | None = None) -> dict[str, Any]:
        if verdict not in VERDICTS:
            raise AssertionError(verdict)
        current = payload.get("current_fingerprint") if isinstance(payload.get("current_fingerprint"), dict) else {}
        core = {
            "version": "3.5",
            "evidence_id": evidence_id,
            "verdict": verdict,
            "checks": checks,
            "blockers": sorted(set(blockers)),
            "ledger_status": (state or {}).get("status", "unknown"),
            "candidate_bundle_digest": (self.fingerprints.get(evidence_id) or {}).get("bundle_digest"),
            "current_bundle_digest": current.get("bundle_digest"),
            "retrieval_receipt_digest": payload.get("retrieval_receipt_digest"),
            "retrieval_score": float(payload.get("retrieval_score") or 0.0),
            "requirements": {
                "fresh_verification_required": verdict in {"EXACT", "ADAPTABLE"},
                "adaptation_required": verdict == "ADAPTABLE",
                "reference_only": verdict == "REFERENCE",
                "human_promotion_required": verdict in {"EXACT", "ADAPTABLE"},
                "phase2_governance_bypass_allowed": False,
            },
            "authority": "classification_only",
            "reuse_authorized": False,
        }
        return {"beast_object_type": "beast_evidence_compatibility_receipt", **core, "receipt_digest": sha256_digest(core)}
