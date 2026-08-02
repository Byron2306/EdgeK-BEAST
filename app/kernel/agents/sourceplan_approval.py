"""Deterministic verified-diff SourcePlan and one-use approval contract."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class VerifiedDiffSourcePlan:
    """Build reviewable change authority without applying or promoting it."""

    def build(self, *, action_ir: Dict[str, Any], diff: Dict[str, Any], execution: Dict[str, Any], verification: Dict[str, Any], forge_assistance: Dict[str, Any] | None = None, crystal_assistance: Dict[str, Any] | None = None, model_contribution: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if verification.get("status") != "passed" or verification.get("passed") is not True:
            raise PermissionError("SourcePlan requires fresh passing verification")
        if not execution.get("mutation_applied") or not execution.get("receipt_digest"):
            raise PermissionError("SourcePlan requires a mutation receipt")
        actions = action_ir.get("actions") if isinstance(action_ir.get("actions"), list) else []
        paths = sorted({str((item.get("target") or {}).get("path") or "") for item in actions if isinstance(item, dict)})
        paths = [path for path in paths if path]
        plan = {
            "beast_object_type": "verified_diff_sourceplan", "version": "1.0",
            "plan_id": "sourceplan-" + uuid.uuid4().hex[:16], "status": "review_pending",
            "operations": action_ir, "changed_paths": paths,
            "diff": {"stat": diff.get("stat", ""), "patch": diff.get("diff", "")[:60000]},
            "verification": verification, "authority": execution.get("authority", {}),
            "receipts": {
                "mutation": execution.get("receipt_digest"),
                "forge": (forge_assistance or {}).get("assistance_digest", ""),
                "crystal": (crystal_assistance or {}).get("assistance_key", ""),
                "model": (model_contribution or {}).get("model_packet_digest", ""),
            },
            "operator_decision": "pending",
        }
        plan["plan_digest"] = _digest(plan)
        return plan

    def approve(self, plan: Dict[str, Any], *, operator_id: str, reason: str) -> Dict[str, Any]:
        if plan.get("status") != "review_pending" or plan.get("operator_decision") != "pending":
            raise PermissionError("SourcePlan is not pending operator review")
        if not operator_id or not reason.strip():
            raise ValueError("operator identity and approval reason are required")
        approval = {"approval_id": "approval-" + uuid.uuid4().hex[:16], "operator_id": operator_id, "reason": reason, "plan_digest": plan.get("plan_digest"), "one_use": True}
        return {"status": "approved", "approval": approval, "plan_digest": plan.get("plan_digest")}
