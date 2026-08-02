"""Operator-facing live run timeline projection for Phase 5.7."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable

from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console.event_projection import DurableConsoleEventProjection

VERSION = "5.7"
OBJECT_TYPE = "beast_live_run_timeline_console"
CATEGORIES = {
    "run", "plan", "context", "tool", "approval", "worktree",
    "verification", "budget", "provider", "sourceplan", "recovery",
}
SEVERITIES = {"info", "warning", "error", "critical"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _csv_set(value: str | Iterable[str], allowed: set[str]) -> set[str]:
    if isinstance(value, str):
        items = [item.strip().lower() for item in value.split(",") if item.strip()]
    else:
        items = [str(item).strip().lower() for item in value if str(item).strip()]
    invalid = sorted(set(items) - allowed)
    if invalid:
        raise ValueError("unsupported timeline filter: " + ", ".join(invalid))
    return set(items)


class LiveRunTimelineConsole:
    """Builds a read-only operator timeline from the durable 5.2 projection."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store = AgentRunStore(self.workspace_root)
        self.projection = DurableConsoleEventProjection(self.workspace_root)

    def build(
        self,
        run_id: str,
        *,
        cursor: str = "",
        limit: int = 100,
        categories: str | Iterable[str] = "",
        severities: str | Iterable[str] = "",
        step_id: str = "",
        query: str = "",
        view: str = "expanded",
        now: float | None = None,
    ) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        category_filter = _csv_set(categories, CATEGORIES)
        severity_filter = _csv_set(severities, SEVERITIES)
        page = self.projection.page(run_id, cursor=cursor, limit=limit, view=view)
        needle = query.strip().lower()
        requested_step = step_id.strip()
        visible = []
        for event in page["events"]:
            if category_filter and event["category"] not in category_filter:
                continue
            if severity_filter and event["severity"] not in severity_filter:
                continue
            if requested_step and str(event.get("step_id") or "") != requested_step:
                continue
            if needle:
                searchable = " ".join([
                    str(event.get("summary") or ""), str(event.get("event_type") or ""),
                    str(event.get("step_id") or ""), json.dumps(event.get("compact") or {}, sort_keys=True),
                    json.dumps(event.get("detail") or {}, sort_keys=True, default=str),
                ]).lower()
                if needle not in searchable:
                    continue
            visible.append(self._card(event))
        clock = float(now if now is not None else time.time())
        created_at = float(run.get("created_at") or 0)
        updated_at = float(run.get("updated_at") or created_at)
        terminal = str(run.get("state") or "").lower() in {"completed", "failed", "cancelled", "rejected"}
        elapsed_to = updated_at if terminal and updated_at else clock
        state = str(run.get("state") or "unknown").lower()
        paused = state in {"paused", "waiting_for_approval", "waiting_for_input"}
        recoverable = paused or state in {"failed", "recoverable", "interrupted"}
        groups: dict[str, list[dict[str, Any]]] = {}
        for card in visible:
            groups.setdefault(card["step_group"], []).append(card)
        console = {
            "version": VERSION,
            "beast_object_type": OBJECT_TYPE,
            "run_id": run_id,
            "run_state": state,
            "paused": paused,
            "recoverable": recoverable,
            "terminal": terminal,
            "elapsed_seconds": max(0.0, elapsed_to - created_at) if created_at else 0.0,
            "active_operation": self._active_operation(visible, state),
            "filters": {
                "categories": sorted(category_filter), "severities": sorted(severity_filter),
                "step_id": requested_step, "query": query,
            },
            "summary": self._summary(visible, page),
            "groups": [{"step_group": key, "events": value, "count": len(value)} for key, value in groups.items()],
            "events": visible,
            "has_more": page["has_more"],
            "next_cursor": page["next_cursor"],
            "projection_head_digest": page["projection_head_digest"],
            "projection_chain": page["chain"],
            "refresh": {
                "mode": "cursor_poll", "recommended_interval_ms": 1500,
                "reconnect_safe": True, "duplicate_suppression": True,
            },
            "authority": "live_timeline_console_read_only",
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
            "grants_promotion_authority": False,
        }
        console["console_digest"] = _digest(console)
        return console

    def verify(self, console: dict[str, Any]) -> bool:
        if console.get("beast_object_type") != OBJECT_TYPE:
            return False
        claimed = str(console.get("console_digest") or "")
        semantic = dict(console)
        semantic.pop("console_digest", None)
        return claimed == _digest(semantic)

    @staticmethod
    def _card(event: dict[str, Any]) -> dict[str, Any]:
        occurred = float(event.get("occurred_at") or 0)
        detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
        step = str(event.get("step_id") or detail.get("step_id") or "")
        return {
            "projection_event_id": event["projection_event_id"],
            "ordinal": event["ordinal"],
            "occurred_at": occurred,
            "category": event["category"],
            "severity": event["severity"],
            "event_type": event["event_type"],
            "step_id": step,
            "step_group": step or "run-level",
            "summary": event["summary"],
            "status": str((event.get("compact") or {}).get("status") or detail.get("status") or ""),
            "tool_id": str((event.get("compact") or {}).get("tool_id") or detail.get("tool_id") or ""),
            "approval_id": str((event.get("compact") or {}).get("approval_id") or detail.get("approval_id") or ""),
            "evidence_digest": str(event.get("evidence_digest") or ""),
            "expandable": bool(detail),
            "detail": detail,
            "projection_digest": event["projection_digest"],
            "authority": "timeline_event_display_only",
        }

    @staticmethod
    def _summary(events: list[dict[str, Any]], page: dict[str, Any]) -> dict[str, Any]:
        counts = {category: 0 for category in sorted(CATEGORIES)}
        severities = {severity: 0 for severity in sorted(SEVERITIES)}
        for event in events:
            counts[event["category"]] += 1
            severities[event["severity"]] += 1
        return {
            "visible_count": len(events),
            "projected_count": int(page.get("projection_event_count") or 0),
            "category_counts": counts,
            "severity_counts": severities,
            "latest_ordinal": max((int(event["ordinal"]) for event in events), default=0),
        }

    @staticmethod
    def _active_operation(events: list[dict[str, Any]], state: str) -> dict[str, Any]:
        for event in reversed(events):
            if event["category"] in {"tool", "verification", "approval", "worktree", "provider"}:
                return {"category": event["category"], "summary": event["summary"], "step_id": event["step_id"], "state": state}
        return {"category": "run", "summary": state.replace("_", " "), "step_id": "", "state": state}
