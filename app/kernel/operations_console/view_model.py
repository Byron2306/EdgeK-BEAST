"""Canonical, restart-safe Agent Operations Console snapshot projection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console.event_projection import DurableConsoleEventProjection
from app.kernel.operations_console.objective_plan import ObjectivePlanWorkspace
from app.kernel.operations_console.context_manifest import ContextManifestStore

VERSION = "5.1"
OBJECT_TYPE = "beast_agent_operations_console_snapshot"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _first(payloads: Iterable[dict[str, Any]], *keys: str, default: Any = None) -> Any:
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", [], {}):
                return value
    return default


class AgentOperationsConsoleViewModel:
    """Projects durable run evidence into one canonical console snapshot.

    Phase 5.1 is deliberately read-only. It does not reconstruct state from a
    conversation, mutate a run, approve a tool, execute work, or promote a
    SourcePlan. It only reports durable truth already present in the workspace.
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store = AgentRunStore(self.workspace_root)

    def build(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")

        events = self.store.events(run_id, after=0, limit=100_000)
        approvals = self.store.approvals(run_id)
        projection = DurableConsoleEventProjection(self.workspace_root).page(run_id, limit=25, view="compact")
        payloads = [_dict(event.get("payload")) for event in events]
        checkpoint = _dict(run.get("checkpoint"))
        request = _dict(run.get("request"))
        budget = _dict(run.get("budget"))

        durable_mission = ObjectivePlanWorkspace(self.workspace_root).current(run_id)
        plan = self._plan(payloads, checkpoint, request)
        if durable_mission.get("revision_id"):
            plan = {**durable_mission["plan"], "version": durable_mission["plan_version"], "revision_reason": durable_mission["reason"]}
        durable_context = ContextManifestStore(self.workspace_root).manifest(run_id)
        context = durable_context if durable_context.get("item_count") else self._context(payloads, checkpoint, request)
        tools = self._tools(events)
        worktree = self._worktree(payloads, checkpoint, run)
        verification = self._verification(events, checkpoint)
        sourceplan = self._sourceplan(payloads, checkpoint)
        recovery = self._recovery(run, checkpoint)
        route = self._provider_route(payloads, run)

        snapshot = {
            "version": VERSION,
            "beast_object_type": OBJECT_TYPE,
            "run_id": run_id,
            "workspace_root": str(self.workspace_root),
            "conversation_first": True,
            "run": {
                "session_id": str(run.get("session_id") or ""),
                "state": str(run.get("state") or ""),
                "mode": str(run.get("mode") or ""),
                "objective": str(durable_mission.get("objective") or run.get("objective") or ""),
                "success_criteria": _list(durable_mission.get("success_criteria") or _first(payloads, "success_criteria", default=request.get("success_criteria", []))),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "error": str(run.get("error") or ""),
                "cancel_requested": bool(run.get("cancel_requested")),
            },
            "plan": plan,
            "timeline": {
                "event_count": projection["projection_event_count"],
                "head_hash": projection["projection_head_digest"],
                "chain": projection["chain"],
                "latest_sequence": int(run.get("last_sequence") or 0),
                "latest_events": projection["events"],
                "projection_version": "5.2",
            },
            "context_manifest": context,
            "tool_activity": tools,
            "approvals": {
                "count": len(approvals),
                "pending": sum(1 for item in approvals if str(item.get("status")) == "pending"),
                "items": approvals,
            },
            "worktree": worktree,
            "verification": verification,
            "budget": self._budget(budget, payloads),
            "provider_route": route,
            "sourceplan": sourceplan,
            "recovery": recovery,
            "authority": "console_projection_read_only",
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
            "grants_promotion_authority": False,
        }
        snapshot["snapshot_digest"] = _digest(snapshot)
        return snapshot

    def verify(self, snapshot: dict[str, Any]) -> bool:
        if snapshot.get("beast_object_type") != OBJECT_TYPE:
            return False
        claimed = str(snapshot.get("snapshot_digest") or "")
        semantic = dict(snapshot)
        semantic.pop("snapshot_digest", None)
        return claimed == _digest(semantic)

    @staticmethod
    def _timeline_event(event: dict[str, Any]) -> dict[str, Any]:
        payload = _dict(event.get("payload"))
        summary = str(payload.get("summary") or payload.get("message") or event.get("event_type") or "")
        return {
            "event_id": event.get("event_id"),
            "sequence": event.get("sequence"),
            "event_type": event.get("event_type"),
            "created_at": event.get("created_at"),
            "summary": summary,
            "event_hash": event.get("event_hash"),
        }

    @staticmethod
    def _plan(payloads: list[dict[str, Any]], checkpoint: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        plan = _dict(checkpoint.get("plan"))
        if not plan:
            plan = _dict(_first(reversed(payloads), "plan", "current_plan", default=request.get("plan", {})))
        steps = _list(plan.get("steps"))
        return {
            "version": plan.get("version", 1 if plan else 0),
            "status": str(plan.get("status") or ("available" if plan else "not_created")),
            "active_step_id": str(plan.get("active_step_id") or checkpoint.get("step_id") or ""),
            "steps": steps,
            "step_count": len(steps),
            "revision_reason": str(plan.get("revision_reason") or ""),
        }

    @staticmethod
    def _context(payloads: list[dict[str, Any]], checkpoint: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        manifest = _dict(checkpoint.get("context_manifest"))
        if not manifest:
            manifest = _dict(_first(reversed(payloads), "context_manifest", "context_packet", default={}))
        items = _list(manifest.get("items"))
        if not items:
            items = [{"path": str(path), "status": "accepted", "source": "request"} for path in _list(request.get("context_files"))]
        return {
            "status": str(manifest.get("status") or ("available" if items else "not_built")),
            "item_count": len(items),
            "accepted_count": sum(1 for item in items if str(_dict(item).get("status") or "").lower() in {"accepted", "admitted"}),
            "items": items,
            "manifest_digest": str(manifest.get("manifest_digest") or (_digest(items) if items else "")),
        }

    @staticmethod
    def _tools(events: list[dict[str, Any]]) -> dict[str, Any]:
        tool_events = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            payload = _dict(event.get("payload"))
            if "tool" in event_type or payload.get("tool_id") or payload.get("tool"):
                tool_events.append({
                    "sequence": event.get("sequence"),
                    "event_type": event_type,
                    "tool_id": str(payload.get("tool_id") or payload.get("tool") or ""),
                    "status": str(payload.get("status") or event_type.rsplit(".", 1)[-1]),
                    "receipt_digest": str(payload.get("receipt_digest") or payload.get("observation_digest") or ""),
                })
        return {"count": len(tool_events), "items": tool_events[-50:]}

    @staticmethod
    def _worktree(payloads: list[dict[str, Any]], checkpoint: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        value = _dict(checkpoint.get("worktree")) or _dict(_first(reversed(payloads), "worktree", "worktree_state", default={}))
        return {
            "required": str(run.get("mode") or "").lower() == "agent",
            "status": str(value.get("status") or ("unknown" if value else "not_created")),
            "path": str(value.get("path") or value.get("worktree_path") or ""),
            "base_commit": str(value.get("base_commit") or ""),
            "changed_files": _list(value.get("changed_files")),
            "dirty": bool(value.get("dirty")),
        }

    @staticmethod
    def _verification(events: list[dict[str, Any]], checkpoint: dict[str, Any]) -> dict[str, Any]:
        items = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            payload = _dict(event.get("payload"))
            if any(token in event_type for token in ("verify", "test", "lint", "typecheck", "security")):
                items.append({
                    "sequence": event.get("sequence"),
                    "event_type": event_type,
                    "status": str(payload.get("status") or ("passed" if payload.get("ok") is True else "failed" if payload.get("ok") is False else "recorded")),
                    "command": str(payload.get("command") or ""),
                    "evidence_digest": str(payload.get("evidence_digest") or payload.get("receipt_digest") or ""),
                })
        current = _dict(checkpoint.get("verification"))
        return {"status": str(current.get("status") or (items[-1]["status"] if items else "not_started")), "count": len(items), "items": items[-50:]}

    @staticmethod
    def _budget(budget: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
        usage = _dict(_first(reversed(payloads), "budget_usage", "usage", default={}))
        return {"limits": budget, "usage": usage, "exhausted": bool(usage.get("exhausted")), "remaining": _dict(usage.get("remaining"))}

    @staticmethod
    def _provider_route(payloads: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
        route = _dict(_first(reversed(payloads), "provider_route", "route", default={}))
        return {
            "provider": str(route.get("provider") or run.get("provider") or ""),
            "model": str(route.get("model") or run.get("model") or ""),
            "reason": str(route.get("reason") or "run_configuration"),
            "fallback_chain": _list(route.get("fallback_chain")),
            "local": bool(route.get("local")),
        }

    @staticmethod
    def _sourceplan(payloads: list[dict[str, Any]], checkpoint: dict[str, Any]) -> dict[str, Any]:
        value = _dict(checkpoint.get("sourceplan")) or _dict(_first(reversed(payloads), "sourceplan", "source_plan", default={}))
        return {
            "status": str(value.get("status") or ("ready" if value else "not_created")),
            "sourceplan_id": str(value.get("sourceplan_id") or value.get("plan_id") or ""),
            "digest": str(value.get("digest") or value.get("sourceplan_digest") or ""),
            "promotion_ready": bool(value.get("promotion_ready")),
            "promotion_authorized": bool(value.get("promotion_authorized")),
        }

    @staticmethod
    def _recovery(run: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
        state = str(run.get("state") or "")
        paused = state == "paused"
        return {
            "restart_safe": True,
            "reconstruction_from_conversation_required": False,
            "paused": paused,
            "recoverable": paused or bool(checkpoint.get("recovery")),
            "reason": str(run.get("error") or _dict(checkpoint.get("recovery")).get("reason") or ""),
            "checkpoint_present": bool(checkpoint),
        }
