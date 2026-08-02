"""Shared least-authority tool gate for IDE, CLI, TUI, and MCP lanes.

The loop deliberately knows nothing about provider/tool implementations.  A
caller registers a small named executor for a declared capability, then this
module decides whether that capability is visible for the current phase and
emits a durable-shaped receipt for every allow, denial, skip, and result.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Dict, Iterable, Mapping

from app.kernel.agents.mode_router import ModeRouter
from app.kernel.capability.tool_buckets import bucket_tools, exposure_receipt


class LeastAuthorityToolLoop:
    """Authorize narrowly declared tools without granting ambient authority."""

    def __init__(self, mode_router: ModeRouter | None = None):
        self.mode_router = mode_router or ModeRouter()

    def plan(
        self,
        tools: Iterable[Mapping[str, Any]], *, phase: str, risk: str = "low",
        approved: bool = False, network: bool = False,
    ) -> Dict[str, Any]:
        rows = [dict(item) for item in tools if isinstance(item, Mapping)]
        bucket_phase = self._bucket_phase(phase)
        visible = bucket_tools(rows, phase=bucket_phase, risk=risk, approved=approved, network=network)
        return {
            "beast_object_type": "least_authority_tool_plan",
            "version": "1.0",
            "phase": phase, "bucket_phase": bucket_phase,
            "risk": risk,
            "approved": bool(approved),
            "exposure": exposure_receipt(rows, phase=bucket_phase, risk=risk, approved=approved, network=network),
            "tools": [self.authorize(item, phase=phase, risk=risk, approved=approved, network=network) for item in rows],
            "visible_tools": [str(item.get("name") or "") for item in visible],
        }

    def authorize(
        self, tool: Mapping[str, Any], *, phase: str, risk: str = "low",
        approved: bool = False, network: bool = False,
    ) -> Dict[str, Any]:
        item = dict(tool)
        name = str(item.get("name") or "").strip()
        category = str(item.get("category") or "planning")
        bucket = str(item.get("bucket") or "Observe")
        mutating = bool(item.get("mutating"))
        bucket_phase = self._bucket_phase(phase)
        visible = any(str(row.get("name") or "") == name for row in bucket_tools(
            [item], phase=bucket_phase, risk=risk, approved=approved, network=network, mutating=mutating,
        ))
        route = self.mode_router.select(phase=phase, risk=risk)
        mode = str(route.get("selected_mode") or "scout")
        mode_decision = self.mode_router.tool_allowed(mode, name, category)
        allowed = bool(name and visible and mode_decision.get("allowed"))
        if mutating:
            allowed = False
        reason = "allowed" if allowed else (
            "mutating tools require SourcePlan approval and are never executed by this loop" if mutating
            else "hidden by risk/phase bucket" if not visible else str(mode_decision.get("reason") or "blocked by mode")
        )
        return self._receipt(name, phase, risk, allowed, reason, {
            "bucket": bucket, "bucket_phase": bucket_phase, "category": category, "mode": mode,
            "mode_route": route, "mutating": mutating, "network": bool(network),
        })

    def execute(
        self, tool: Mapping[str, Any], executor: Callable[[], Any], *, phase: str, risk: str = "low",
        approved: bool = False, network: bool = False,
    ) -> Dict[str, Any]:
        receipt = self.authorize(tool, phase=phase, risk=risk, approved=approved, network=network)
        if not receipt["allowed"]:
            return {**receipt, "executed": False, "result": None}
        try:
            result = executor()
            return {**receipt, "executed": True, "result": result}
        except Exception as exc:
            return {**receipt, "executed": True, "ok": False, "reason": f"executor failed: {type(exc).__name__}: {exc}", "result": None}

    def mutation_gate(
        self, name: str, *, phase: str, risk: str = "high", approved: bool = False,
        sourceplan_bound: bool = False,
    ) -> Dict[str, Any]:
        """Authorize entry to an existing governed mutation workflow.

        This is deliberately not ``execute``: callers must still perform their
        own preview, verification, rollback, and approval checks.
        """
        permitted = bool(approved and sourceplan_bound)
        reason = "approved governed mutation workflow" if permitted else (
            "explicit operator approval is required" if not approved else "a bound SourcePlan/workflow is required"
        )
        receipt = self._receipt(name, phase, risk, permitted, reason, {
            "mutation_gate": True, "sourceplan_bound": bool(sourceplan_bound),
            "execution_rule": "This receipt permits entry only; direct mutation executors remain forbidden.",
        })
        receipt["mutation_permitted"] = permitted
        receipt["execution_rule"] = "This receipt permits entry only; direct mutation executors remain forbidden."
        return receipt

    @staticmethod
    def _receipt(name: str, phase: str, risk: str, allowed: bool, reason: str, detail: Dict[str, Any]) -> Dict[str, Any]:
        body = {"tool": name, "phase": phase, "risk": risk, "allowed": allowed, "reason": reason, "detail": detail}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return {
            "beast_object_type": "least_authority_tool_receipt",
            "version": "1.0", "receipt_id": f"tool_{digest[:16]}", "receipt_hash": f"sha256:{digest}",
            "timestamp": time.time(), "ok": bool(allowed), **body,
        }

    @staticmethod
    def _bucket_phase(phase: str) -> str:
        value = str(phase or "").strip().lower()
        if value in {"review", "verify", "debugger", "evidence_logger"}:
            return "Verify"
        if value in {"implementer", "implementation", "edit"}:
            return "Modify"
        if value in {"architect", "planning", "reason"}:
            return "Reason"
        return "Observe"
