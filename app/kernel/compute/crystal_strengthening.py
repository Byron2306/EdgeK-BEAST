"""Immediate, receipt-backed strengthening of verified repair patterns."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def _key(value: Dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class VerifiedCrystalStrengthener:
    """Persist verified episodes without silently authorizing reuse."""

    def __init__(self, root: str | Path):
        self.path = Path(root).expanduser().resolve() / "verified-repair-crystals.json"

    def strengthen(self, episode: Dict[str, Any]) -> Dict[str, Any]:
        if episode.get("visible_pass") is not True or episode.get("verification_status") != "passed":
            return {"status": "not_strengthened", "reason": "verified completion is required", "promotion_authorized": False}
        identity = {
            "task_family": str(episode.get("task_family") or "general"),
            "failure_signature": str(episode.get("failure_signature") or ""),
            "symbol_shape": str(episode.get("symbol_shape") or ""),
            "operation_family": str(episode.get("operation_family") or "replace_exact"),
        }
        crystal_key = _key(identity)
        records = self._load()
        record = records.get(crystal_key, {"identity": identity, "verified_occurrences": 0, "status": "advisory"})
        record["verified_occurrences"] = int(record.get("verified_occurrences") or 0) + 1
        record["resolved_residual"] = episode.get("resolved_residual") or {}
        record["verifier_contract"] = episode.get("verifier_contract") or ""
        record["applicability_key"] = episode.get("applicability_key") or record.get("applicability_key") or ""
        record["authority"] = episode.get("authority") or ["worktree_mutation", "worktree_verification"]
        count = record["verified_occurrences"]
        record["status"] = "advisory" if count == 1 else "scaffolded" if count == 2 else "deterministic_reuse_candidate"
        record["promotion_authorized"] = False
        records[crystal_key] = record
        self._save(records)
        return {"status": "strengthened", "crystal_key": crystal_key, "verified_occurrences": count, "assistance_mode": record["status"], "promotion_authorized": False}

    def lookup(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        crystal_key = _key({
            "task_family": str(identity.get("task_family") or "general"),
            "failure_signature": str(identity.get("failure_signature") or ""),
            "symbol_shape": str(identity.get("symbol_shape") or ""),
            "operation_family": str(identity.get("operation_family") or "replace_exact"),
        })
        record = self._load().get(crystal_key)
        if not record:
            return {"found": False, "assistance_mode": "fresh_bounded", "crystal_key": crystal_key, "execution_allowed": False}
        return {"found": True, "crystal_key": crystal_key, "assistance_mode": record.get("status", "advisory"), "verified_occurrences": record.get("verified_occurrences", 0), "execution_allowed": record.get("status") == "deterministic_reuse_candidate", "record": record}

    def demote(self, identity: Dict[str, Any], reason: str) -> Dict[str, Any]:
        crystal_key = _key(identity)
        records = self._load()
        record = records.get(crystal_key)
        if not record:
            return {"status": "not_found", "crystal_key": crystal_key}
        record["status"] = "advisory"
        record["demotion_reason"] = reason
        record["promotion_authorized"] = False
        records[crystal_key] = record
        self._save(records)
        return {"status": "demoted", "crystal_key": crystal_key, "assistance_mode": "advisory"}

    def _load(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, records: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
