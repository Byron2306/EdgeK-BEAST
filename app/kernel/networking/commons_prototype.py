"""Completion and Crystal promotion flow for the first BEAST Compute Space."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.security.crystal_seal import canonical_bytes, seal_crystal_payload


class CommonsCrystalPromoter:
    def __init__(self, registry: Any, economy: Any, root: Optional[Path] = None):
        self.registry = registry
        self.economy = economy
        project_root = Path(__file__).resolve().parents[2]
        default_registry = (project_root / "data" / "commons_spaces").resolve()
        default_root = (
            project_root / "data" / "crystallization" / "commons_spaces"
            if registry.root == default_registry
            else registry.root / "_crystals"
        )
        self.root = (root or default_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def promote(self, space_id: str, *, approved: bool, approved_by: str, reason: str) -> Dict[str, Any]:
        if not approved or not reason.strip():
            raise ValueError("Crystal promotion requires explicit approval and a reason")
        proof = self.economy.proof(space_id)
        live_ids = proof["evidence"]["reproduction_ids"]
        if not proof["eligible"] or len(live_ids) < 3:
            raise ValueError("Crystal promotion requires adoption and three verified live reproductions")
        detail = self.registry.get(space_id)
        manifest = detail["manifest"]
        crystal_id = "space_crystal_" + hashlib.sha256(str(manifest["manifest_hash"]).encode()).hexdigest()[:20]
        path = self.root / f"{crystal_id}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_evidence = existing.get("promotion_evidence") or {}
            if existing_evidence.get("evidence_fingerprint") == proof["evidence_fingerprint"]:
                return {**existing, "already_promoted": True, "path": str(path)}
        space_root = self.registry.root / space_id
        plan = {}
        candidate = {}
        for artifact in manifest.get("artifacts") or []:
            artifact_path = space_root / str(artifact.get("path") or "")
            if artifact.get("artifact_type") == "orchestration_plan":
                plan = json.loads(artifact_path.read_text(encoding="utf-8"))
            elif artifact.get("artifact_type") == "promotion_candidate":
                candidate = json.loads(artifact_path.read_text(encoding="utf-8"))
        crystal = {
            "beast_object_type": "fused_commons_space_crystal",
            "version": "1.0",
            "crystal_id": crystal_id,
            "space_id": space_id,
            "name": (candidate.get("candidate") or {}).get("name") or manifest.get("name"),
            "task_class": manifest.get("task_class"),
            "authority": "advisory_reuse",
            "approved_for_enforcement": False,
            "route": plan.get("route") or plan.get("required_route") or [],
            "subagents": plan.get("subagents") or plan.get("required_subagents") or [],
            "verifier_bundles": manifest.get("verifier_bundles") or [],
            "artifact_references": manifest.get("artifacts") or [],
            "impact_fingerprint": {
                "state": "active",
                "manifest_hash": manifest.get("manifest_hash"),
                "artifact_hashes": sorted(str(item.get("sha256") or "") for item in manifest.get("artifacts") or []),
            },
            "promotion_evidence": {
                "adoption_ids": proof["evidence"]["adoption_ids"],
                "live_reproduction_ids": live_ids,
                "useful_reduction_score": proof["useful_reduction_score"],
                "evidence_fingerprint": proof["evidence_fingerprint"],
            },
            "approved_by": approved_by,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        crystal["local_seal"] = seal_crystal_payload(crystal, purpose="fused_commons_space_crystal")
        path.write_text(json.dumps(crystal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {**crystal, "already_promoted": False, "path": str(path)}

    def state(self) -> Dict[str, Any]:
        crystals = []
        for path in sorted(self.root.glob("*.json")):
            try:
                crystals.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return {
            "beast_object_type": "commons_space_crystal_registry",
            "version": "1.0",
            "count": len(crystals),
            "crystals": crystals,
        }


class FirstPrototypeRunner:
    def __init__(self, registry: Any, economy: Any, promoter: CommonsCrystalPromoter):
        self.registry = registry
        self.economy = economy
        self.promoter = promoter

    def complete(
        self,
        *,
        space_id: str,
        target: Path,
        approved: bool,
        approved_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not approved or not reason.strip():
            raise ValueError("prototype completion requires explicit approval and a reason")
        detail = self.registry.get(space_id)
        manifest_hash = detail["manifest"].get("manifest_hash")
        current_adoptions = [
            item for item in detail.get("adoptions") or []
            if item.get("adopted") and item.get("manifest_hash") == manifest_hash
        ]
        adoption = current_adoptions[0] if current_adoptions else self.registry.adopt(
            space_id,
            approved=True,
            dry_run=False,
            approved_by=approved_by,
            reason=reason,
        )
        current_live = [
            item for item in detail.get("reproductions") or []
            if item.get("manifest_hash") == manifest_hash
            and item.get("mode") == "live_verifier"
            and item.get("live_verifier_passed") is True
            and item.get("reproduced") is True
        ]
        new_replays = []
        for _ in range(max(0, 3 - len(current_live))):
            new_replays.append(self.registry.replay(
                space_id,
                target=target,
                deterministic_only=False,
                approved=True,
                contributor_id="local_prototype",
            ))
        crystal = self.promoter.promote(
            space_id,
            approved=True,
            approved_by=approved_by,
            reason=reason,
        )
        simulation = self.economy.simulate(space_id)
        credit = self.economy.issue_credit(
            space_id,
            approved=True,
            approved_by=approved_by,
            reason=reason,
        )
        final_detail = self.registry.get(space_id)
        result = {
            "beast_object_type": "beast_commons_first_prototype_completion",
            "version": "1.0",
            "space_id": space_id,
            "completed": True,
            "checklist": {
                "packaged_artifacts": len(final_detail["manifest"].get("artifacts") or []),
                "manifest_valid": final_detail["manifest_validation"].get("valid"),
                "reduction_receipt_valid": final_detail["receipt_validation"].get("valid"),
                "tui_surface": "Compute Spaces",
                "adopted": True,
                "live_reproductions": len([
                    item for item in final_detail.get("reproductions") or []
                    if item.get("manifest_hash") == manifest_hash and item.get("mode") == "live_verifier" and item.get("reproduced")
                ]),
                "crystal_promoted": bool(crystal.get("crystal_id")),
                "non_financial_credit_issued": bool(credit.get("credit_id")),
            },
            "adoption_id": adoption.get("adoption_id"),
            "new_reproduction_ids": [item.get("reproduction_id") for item in new_replays],
            "crystal_id": crystal.get("crystal_id"),
            "credit_id": credit.get("credit_id"),
            "reward_simulation": simulation,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result["completion_hash"] = "sha256:" + hashlib.sha256(canonical_bytes(result)).hexdigest()
        return result
