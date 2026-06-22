"""Persisted approval audit events for Phase 4 compute routing."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ApprovalAuditStore:
    """Append-only JSONL audit store for approval pause/resume lifecycle."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event_type: str,
        plan_id: str,
        gate_id: str,
        status: str,
        reason: str = "",
        approved: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = {
            "beast_object_type": "compute_approval_audit_event",
            "version": "1.0",
            "event_id": "caud_" + uuid.uuid4().hex[:20],
            "event_type": event_type,
            "plan_id": plan_id,
            "gate_id": gate_id,
            "status": status,
            "reason": reason,
            "approved": approved,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        return event

    def events(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows[-max(0, int(limit)) :]
