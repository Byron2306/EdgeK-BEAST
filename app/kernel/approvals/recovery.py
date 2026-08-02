from __future__ import annotations
from pathlib import Path
from typing import Any
from .store import DurableApprovalStore

class ApprovalRecoveryService:
    def __init__(self, root_path: str | Path):
        self.store = DurableApprovalStore(root_path)

    def recover(self, *, now=None) -> dict[str, Any]:
        rebuilt = self.store.rebuild_projection()
        expired = self.store.expire_due(now=now)
        pending = self.store.list(state="PENDING", limit=500)
        resumable = [{"approval_id": item["approval_id"], "run_id": item["run_id"], "step_id": item["step_id"], "request_digest": item["request"]["request_digest"]} for item in pending]
        return {"ok": True, "rebuilt": rebuilt, "expired": expired, "pending": resumable, "capabilities_issued": 0, "steps_resumed": 0}
