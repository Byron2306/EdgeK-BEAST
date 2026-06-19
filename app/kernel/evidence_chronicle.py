"""
Durable Chronicle writer for scored evidence envelopes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class EvidenceChronicleWriter:
    """Persist high-value evidence envelopes for later ranking and promotion."""

    def __init__(self, data_dir: Optional[str] = None, enabled: bool = True):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir = Path(data_dir)
        self.chronicle_dir = self.data_dir / "evidence_chronicles"
        self.enabled = enabled

    def maybe_write(
        self,
        evidence: Dict[str, Any],
        *,
        reason: str = "high_value_evidence",
        min_priority: float = 0.55,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"written": False, "reason": "disabled"}
        priority = float(evidence.get("priority_score") or 0.0)
        if priority < min_priority and not evidence.get("promotion_candidate"):
            return {"written": False, "reason": "below_priority_threshold", "priority_score": priority}
        return self.write(evidence, reason=reason)

    def write(self, evidence: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
        self.chronicle_dir.mkdir(parents=True, exist_ok=True)
        evidence_id = str(evidence.get("evidence_id") or "unknown_evidence")
        path = self.chronicle_dir / f"{evidence_id}.json"
        record = {
            "chronicle_type": "evidence_envelope",
            "version": "1.0",
            "reason": reason,
            "task_id": evidence.get("task_id"),
            "provider": evidence.get("provider"),
            "category": evidence.get("capability_family") or evidence.get("source_type"),
            "source_type": evidence.get("source_type"),
            "artifact_type": evidence.get("artifact_type"),
            "evidence": evidence,
            "created_at": evidence.get("created_at"),
        }
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "written": True,
            "path": str(path),
            "format": "json",
            "reason": reason,
            "priority_score": evidence.get("priority_score"),
        }
