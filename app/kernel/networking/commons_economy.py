"""Receipt-backed, non-financial Compute Reduction Economy simulation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.security.crystal_seal import canonical_bytes, seal_crystal_payload, verify_crystal_seal


class ComputeReductionEconomy:
    """Scores reproduced useful reduction without creating money or tokens."""

    RISK_DIVISOR = {"low": 1.0, "medium": 1.5, "high": 2.0}

    def __init__(self, registry: Any, root: Optional[Path] = None):
        self.registry = registry
        self.root = (root or registry.root / "economy").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "credits.json"

    def duplicate_report(self, *, max_spaces: Optional[int] = None) -> Dict[str, Any]:
        groups: Dict[str, List[str]] = {}
        rows = [row for row in self.registry.list_spaces().get("spaces") or [] if row.get("valid")]
        truncated = False
        if max_spaces is not None and len(rows) > max_spaces:
            rows = rows[:max(0, int(max_spaces))]
            truncated = True
        for row in rows:
            detail = self.registry.get(str(row["space_id"]))
            fingerprint = self._semantic_fingerprint(detail)
            groups.setdefault(fingerprint, []).append(str(row["space_id"]))
        duplicates = [
            {"fingerprint": fingerprint, "canonical_space_id": sorted(ids)[0], "space_ids": sorted(ids)}
            for fingerprint, ids in groups.items() if len(ids) > 1
        ]
        return {
            "beast_object_type": "compute_reduction_duplicate_report",
            "version": "1.0",
            "groups": duplicates,
            "duplicate_spaces": sum(len(item["space_ids"]) - 1 for item in duplicates),
            "policy": "exact semantic evidence duplicates receive zero additional credit",
            "truncated": truncated,
            "scanned_spaces": len(rows),
        }

    def adoption_history(self, space_id: Optional[str] = None) -> Dict[str, Any]:
        rows = []
        for adoption in self.registry.adoptions():
            if space_id and adoption.get("space_id") != space_id:
                continue
            payload = dict(adoption)
            seal = payload.pop("local_seal", {})
            # Older adoption receipts were sealed before the crystal-chain
            # reference was attached. The chain hash is append-only provenance,
            # not part of the operator adoption decision itself.
            payload.pop("crystal_chain_block_hash", None)
            payload.pop("receipt_path", None)
            valid = bool(adoption.get("adopted") and verify_crystal_seal(payload, seal).get("verified"))
            rows.append({
                "adoption_id": adoption.get("adoption_id"),
                "space_id": adoption.get("space_id"),
                "manifest_hash": adoption.get("manifest_hash"),
                "approved_by": adoption.get("approved_by"),
                "created_at": adoption.get("created_at"),
                "artifact_count": len(adoption.get("artifact_references") or []),
                "valid": valid,
            })
        return {
            "beast_object_type": "verified_commons_adoption_history",
            "version": "1.0",
            "count": len(rows),
            "verified_count": sum(1 for item in rows if item["valid"]),
            "adoptions": rows,
        }

    def proof(self, space_id: str, *, duplicate_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        detail = self.registry.get(space_id)
        manifest = detail["manifest"]
        receipt = detail["reduction_receipt"]
        manifest_hash = manifest.get("manifest_hash")
        valid_adoptions = [
            item for item in self.adoption_history(space_id)["adoptions"]
            if item["valid"] and item.get("manifest_hash") == manifest_hash
        ]
        valid_reproductions = []
        live_reproductions = []
        for reproduction in detail.get("reproductions") or []:
            if reproduction.get("manifest_hash") != manifest_hash:
                continue
            payload = dict(reproduction)
            seal = payload.pop("local_seal", {})
            if not reproduction.get("reproduced") or not verify_crystal_seal(payload, seal).get("verified"):
                continue
            valid_reproductions.append(reproduction)
            if reproduction.get("mode") == "live_verifier" and reproduction.get("live_verifier_passed") is True:
                live_reproductions.append(reproduction)
        duplicate = next(
            (
                group for group in (duplicate_report or self.duplicate_report())["groups"]
                if space_id in group["space_ids"] and group["canonical_space_id"] != space_id
            ),
            None,
        )
        displacement = receipt.get("displacement") or {}
        resources = receipt.get("resource_deltas") or {}
        risk = str((manifest.get("safety") or {}).get("risk") or "high").lower()
        observed_tokens = int(displacement.get("tokens_avoided") or 0) if not displacement.get("counterfactual") else 0
        calls = max(0, int(displacement.get("provider_calls_avoided") or 0))
        call_evidence = 0.1 * min(calls, 2) if displacement.get("counterfactual") else 0.25 * min(calls, 2)
        displacement_score = min(1.0, min(0.5, observed_tokens / 20_000) + call_evidence + (0.3 if resources.get("gpu_avoided") else 0.0))
        verification_confidence = max((float(item.get("trust_score") or 0) for item in live_reproductions), default=0.0)
        reuse_score = min(1.0, 0.25 * len(valid_adoptions) + 0.15 * len(live_reproductions))
        safety_checks = [
            bool(detail["manifest_validation"].get("valid")),
            bool(detail["receipt_validation"].get("valid")),
            bool(receipt.get("rollback_available")),
            bool((manifest.get("privacy") or {}).get("contains_secrets") is False),
        ]
        safety_score = sum(int(item) for item in safety_checks) / len(safety_checks)
        maintenance_burden = 1.0 + 0.05 * len(manifest.get("artifacts") or [])
        raw_score = (
            verification_confidence
            * (0.5 + 0.5 * reuse_score)
            * safety_score
            * (0.5 + 0.5 * displacement_score)
            / maintenance_burden
            / self.RISK_DIVISOR.get(risk, 2.0)
        )
        useful_reduction_score = 0.0 if duplicate else round(min(1.0, raw_score), 6)
        anti_gaming = {
            "manifest_and_receipt_valid": bool(detail["manifest_validation"].get("valid") and detail["receipt_validation"].get("valid")),
            "local_live_reproduction_required": bool(live_reproductions),
            "verified_adoption_required": bool(valid_adoptions),
            "counterfactual_tokens_excluded": bool(displacement.get("counterfactual") or displacement.get("tokens_avoided") is None),
            "duplicate_penalty_applied": bool(duplicate),
            "evidence_caps_applied": True,
            "one_credit_per_evidence_fingerprint": True,
        }
        eligible = bool(
            anti_gaming["manifest_and_receipt_valid"]
            and live_reproductions
            and valid_adoptions
            and not duplicate
        )
        evidence = {
            "manifest_hash": manifest_hash,
            "adoption_ids": sorted(str(item["adoption_id"]) for item in valid_adoptions),
            "reproduction_ids": sorted(str(item["reproduction_id"]) for item in live_reproductions),
        }
        evidence_fingerprint = "sha256:" + hashlib.sha256(canonical_bytes(evidence)).hexdigest()
        return {
            "beast_object_type": "proof_of_useful_compute_reduction",
            "version": "1.0",
            "space_id": space_id,
            "eligible": eligible,
            "useful_reduction_score": useful_reduction_score,
            "components": {
                "verification_confidence": verification_confidence,
                "reuse_score": reuse_score,
                "safety_score": safety_score,
                "displacement_score": round(displacement_score, 6),
                "maintenance_burden": round(maintenance_burden, 6),
                "risk_divisor": self.RISK_DIVISOR.get(risk, 2.0),
                "observed_tokens_credited": observed_tokens,
            },
            "evidence": evidence,
            "evidence_fingerprint": evidence_fingerprint,
            "anti_gaming": anti_gaming,
            "claim_boundary": "Value derives from local reproduction and adoption; claimed or counterfactual tokens earn no observed-token credit.",
        }

    def simulate(self, space_id: Optional[str] = None, *, limit: int = 10) -> Dict[str, Any]:
        ids = [space_id] if space_id else [str(item["space_id"]) for item in self.registry.list_spaces().get("spaces") or [] if item.get("valid")]
        ids = ids[: max(1, min(int(limit), 100))]
        duplicate_report = self.duplicate_report(max_spaces=max(25, len(ids)))
        rows = []
        for current in ids:
            proof = self.proof(current, duplicate_report=duplicate_report)
            rows.append({
                "space_id": current,
                "eligible": proof["eligible"],
                "useful_reduction_score": proof["useful_reduction_score"],
                "simulated_credit_units": min(500, int(round(proof["useful_reduction_score"] * 1000))) if proof["eligible"] else 0,
                "evidence_fingerprint": proof["evidence_fingerprint"],
            })
        return {
            "beast_object_type": "compute_reduction_reward_simulation",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "unit": "non_financial_commons_credit",
            "transferable": False,
            "redeemable": False,
            "financial_value": None,
            "spaces": rows,
            "returned_spaces": len(rows),
            "total_simulated_units": sum(item["simulated_credit_units"] for item in rows),
            "backtest_boundary": "Point-in-time local evidence only; simulation is not a guarantee of future compute reduction.",
        }

    def issue_credit(self, space_id: str, *, approved: bool, approved_by: str, reason: str) -> Dict[str, Any]:
        if not approved or not reason.strip():
            raise ValueError("credit issuance requires explicit approval and a reason")
        proof = self.proof(space_id)
        if not proof["eligible"]:
            raise ValueError("Space is not eligible for reproduced useful-reduction credit")
        state = self._load()
        existing = state["by_evidence"].get(proof["evidence_fingerprint"])
        if existing:
            return {**existing, "duplicate_issuance": True}
        units = min(500, int(round(proof["useful_reduction_score"] * 1000)))
        credit = {
            "beast_object_type": "non_financial_compute_reduction_credit",
            "version": "1.0",
            "space_id": space_id,
            "evidence_fingerprint": proof["evidence_fingerprint"],
            "credit_units": units,
            "unit": "commons_credit",
            "transferable": False,
            "redeemable": False,
            "financial_value": None,
            "approved_by": approved_by,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        credit["credit_id"] = "ccredit_" + hashlib.sha256(canonical_bytes(credit)).hexdigest()[:20]
        credit["local_seal"] = seal_crystal_payload(credit, purpose="non_financial_compute_reduction_credit")
        state["by_evidence"][proof["evidence_fingerprint"]] = credit
        self._save(state)
        return credit

    def state(self, *, full: bool = False) -> Dict[str, Any]:
        state = self._load()
        credits = list(state["by_evidence"].values())
        adoption_history = self.adoption_history() if full else self._adoption_summary()
        duplicate_report = self.duplicate_report() if full else self._duplicate_summary_from_credits(credits)
        return {
            "beast_object_type": "compute_reduction_economy_state",
            "version": "1.0",
            "mode": "non_financial_simulation",
            "credits": credits,
            "credit_count": len(credits),
            "issued_units": sum(int(item.get("credit_units") or 0) for item in credits),
            "duplicates": duplicate_report,
            "adoption_history": adoption_history,
            "full_analysis": bool(full),
            "anti_gaming_rules": [
                "local live reproduction required",
                "verified local adoption required",
                "counterfactual tokens excluded from observed credit",
                "exact semantic duplicates receive no additional credit",
                "one issuance per evidence fingerprint",
                "credits are capped, non-transferable, and non-redeemable",
            ],
        }

    def _adoption_summary(self) -> Dict[str, Any]:
        rows = self.registry.adoptions()
        return {
            "beast_object_type": "verified_commons_adoption_history",
            "version": "1.0",
            "count": len(rows),
            "verified_count": sum(1 for item in rows if item.get("adopted")),
            "adoptions": rows[:8],
            "truncated": len(rows) > 8,
        }

    @staticmethod
    def _duplicate_summary_from_credits(credits: List[Dict[str, Any]]) -> Dict[str, Any]:
        seen: Dict[str, List[str]] = {}
        for credit in credits:
            fingerprint = str(credit.get("evidence_fingerprint") or "")
            if not fingerprint:
                continue
            seen.setdefault(fingerprint, []).append(str(credit.get("space_id") or "unknown"))
        duplicates = [
            {"fingerprint": fingerprint, "canonical_space_id": sorted(ids)[0], "space_ids": sorted(ids)}
            for fingerprint, ids in seen.items() if len(set(ids)) > 1
        ]
        return {
            "beast_object_type": "compute_reduction_duplicate_report",
            "version": "1.0",
            "groups": duplicates,
            "duplicate_spaces": sum(len(set(item["space_ids"])) - 1 for item in duplicates),
            "policy": "exact semantic evidence duplicates receive zero additional credit",
            "fast_summary": True,
            "source": "issued_credit_evidence_fingerprints",
        }

    @staticmethod
    def _semantic_fingerprint(detail: Dict[str, Any]) -> str:
        manifest = detail["manifest"]
        receipt = detail["reduction_receipt"]
        payload = {
            "task_class": manifest.get("task_class"),
            "artifacts": sorted(str(item.get("sha256") or "") for item in manifest.get("artifacts") or []),
            "optimized_route": (receipt.get("optimized_route") or {}).get("route_id"),
            "verifier_bundles": manifest.get("verifier_bundles") or [],
        }
        return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()

    def _load(self) -> Dict[str, Any]:
        if not self.ledger_path.exists():
            return {"by_evidence": {}}
        try:
            loaded = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"by_evidence": {}}
        loaded.setdefault("by_evidence", {})
        return loaded

    def _save(self, state: Dict[str, Any]) -> None:
        temp = self.ledger_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.ledger_path)
