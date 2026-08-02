"""Durable, restart-safe event projection for the Agent Operations Console."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.kernel.agents.run_store import AgentRunStore

VERSION = "5.2"
OBJECT_TYPE = "beast_console_event_projection_page"
EVENT_OBJECT_TYPE = "beast_console_projected_event"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _payload(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _cursor_encode(run_id: str, ordinal: int) -> str:
    raw = _canonical({"run_id": run_id, "ordinal": int(ordinal), "version": VERSION})
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str, run_id: str) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid console event cursor") from exc
    if value.get("version") != VERSION or value.get("run_id") != run_id:
        raise ValueError("console event cursor does not belong to this run")
    return max(0, int(value.get("ordinal") or 0))


class DurableConsoleEventProjection:
    """Projects durable runtime evidence into a canonical console timeline.

    Projection rows are idempotently keyed by their durable source identity.
    Reopening this class after process restart and synchronizing the same run
    yields the same ordered events and projection-chain head.
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store = AgentRunStore(self.workspace_root)
        self.db_path = self.workspace_root / ".beast" / "operations_console" / "event_projection.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS console_projected_events (
                    run_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    projection_event_id TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_sequence INTEGER NOT NULL DEFAULT 0,
                    occurred_at REAL NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    step_id TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL,
                    compact_json TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL DEFAULT '',
                    source_digest TEXT NOT NULL,
                    previous_projection_digest TEXT NOT NULL,
                    projection_digest TEXT NOT NULL,
                    PRIMARY KEY(run_id, ordinal),
                    UNIQUE(run_id, source_key),
                    UNIQUE(projection_event_id)
                );
                CREATE INDEX IF NOT EXISTS idx_console_projection_run_time
                    ON console_projected_events(run_id, occurred_at, ordinal);
                """
            )

    def synchronize(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        source_events = self.store.events(run_id, after=0, limit=1_000_000)
        approvals = self.store.approvals(run_id)
        sources: list[dict[str, Any]] = []
        for event in source_events:
            sources.append(self._from_run_event(event))
        for approval in approvals:
            sources.extend(self._from_approval(approval))
        sources.sort(key=lambda item: (float(item["occurred_at"]), int(item["source_sequence"]), str(item["source_key"])))

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT source_key FROM console_projected_events WHERE run_id=?", (run_id,)
            ).fetchall()
            existing_keys = {str(row[0]) for row in existing}
            tail = connection.execute(
                "SELECT ordinal,projection_digest FROM console_projected_events WHERE run_id=? ORDER BY ordinal DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            ordinal = int(tail["ordinal"]) if tail else 0
            previous = str(tail["projection_digest"]) if tail else ""
            inserted = 0
            for source in sources:
                if source["source_key"] in existing_keys:
                    continue
                ordinal += 1
                event = self._materialize(run_id, ordinal, previous, source)
                connection.execute(
                    """INSERT INTO console_projected_events(
                        run_id,ordinal,projection_event_id,source_key,source_kind,source_sequence,
                        occurred_at,category,severity,event_type,step_id,summary,compact_json,
                        detail_json,evidence_digest,source_digest,previous_projection_digest,projection_digest
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id, ordinal, event["projection_event_id"], source["source_key"], source["source_kind"],
                        source["source_sequence"], source["occurred_at"], event["category"], event["severity"],
                        event["event_type"], event["step_id"], event["summary"], json.dumps(event["compact"], sort_keys=True, default=str),
                        json.dumps(event["detail"], sort_keys=True, default=str), event["evidence_digest"],
                        event["source_digest"], previous, event["projection_digest"],
                    ),
                )
                previous = event["projection_digest"]
                inserted += 1
            connection.execute("COMMIT")
        return {"run_id": run_id, "source_count": len(sources), "inserted": inserted, "event_count": ordinal, "head_digest": previous}

    def page(self, run_id: str, *, cursor: str = "", limit: int = 100, view: str = "compact") -> dict[str, Any]:
        sync = self.synchronize(run_id)
        after = _cursor_decode(cursor, run_id)
        page_limit = max(1, min(int(limit), 500))
        if view not in {"compact", "expanded"}:
            raise ValueError("view must be compact or expanded")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM console_projected_events WHERE run_id=? AND ordinal>? ORDER BY ordinal LIMIT ?",
                (run_id, after, page_limit + 1),
            ).fetchall()
        has_more = len(rows) > page_limit
        rows = rows[:page_limit]
        events = [self._row(row, expanded=view == "expanded") for row in rows]
        last = int(rows[-1]["ordinal"]) if rows else after
        page = {
            "version": VERSION,
            "beast_object_type": OBJECT_TYPE,
            "run_id": run_id,
            "view": view,
            "events": events,
            "count": len(events),
            "has_more": has_more,
            "next_cursor": _cursor_encode(run_id, last) if has_more else "",
            "projection_event_count": sync["event_count"],
            "projection_head_digest": sync["head_digest"],
            "chain": self.verify_chain(run_id),
            "authority": "console_event_projection_read_only",
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
            "grants_promotion_authority": False,
        }
        page["page_digest"] = _digest(page)
        return page

    def verify_page(self, page: dict[str, Any]) -> bool:
        if page.get("beast_object_type") != OBJECT_TYPE:
            return False
        claimed = str(page.get("page_digest") or "")
        semantic = dict(page)
        semantic.pop("page_digest", None)
        return claimed == _digest(semantic)

    def verify_chain(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM console_projected_events WHERE run_id=? ORDER BY ordinal", (run_id,)
            ).fetchall()
        previous = ""
        expected = 1
        for row in rows:
            event = self._row(row, expanded=True)
            semantic = self._semantic_for_digest(event, previous)
            if int(row["ordinal"]) != expected or str(row["previous_projection_digest"]) != previous:
                return {"ok": False, "run_id": run_id, "ordinal": int(row["ordinal"]), "reason": "projection_chain_sequence_mismatch"}
            if str(row["projection_digest"]) != _digest(semantic):
                return {"ok": False, "run_id": run_id, "ordinal": int(row["ordinal"]), "reason": "projection_digest_mismatch"}
            previous = str(row["projection_digest"])
            expected += 1
        return {"ok": True, "run_id": run_id, "events": len(rows), "head_digest": previous, "stored_head_digest": previous, "head_matches": True}

    @staticmethod
    def _category(event_type: str, payload: dict[str, Any]) -> str:
        value = event_type.lower()
        for token, category in (
            ("approval", "approval"), ("tool", "tool"), ("verify", "verification"),
            ("test", "verification"), ("lint", "verification"), ("worktree", "worktree"),
            ("sourceplan", "sourceplan"), ("source_plan", "sourceplan"), ("context", "context"),
            ("budget", "budget"), ("provider", "provider"), ("route", "provider"),
            ("plan", "plan"), ("recovery", "recovery"), ("pause", "recovery"),
        ):
            if token in value:
                return category
        if payload.get("tool_id"):
            return "tool"
        return "run"

    @staticmethod
    def _severity(event_type: str, payload: dict[str, Any]) -> str:
        text = " ".join((event_type, str(payload.get("status") or ""), str(payload.get("severity") or ""))).lower()
        if any(token in text for token in ("critical", "fatal", "revoked", "denied")):
            return "critical"
        if any(token in text for token in ("failed", "error", "timeout", "expired", "rejected")):
            return "error"
        if any(token in text for token in ("warning", "nearly_exhausted", "paused", "waiting")):
            return "warning"
        return "info"

    @classmethod
    def _from_run_event(cls, event: dict[str, Any]) -> dict[str, Any]:
        payload = _payload(event.get("payload"))
        event_type = str(event.get("event_type") or "agent.event")
        source_digest = str(event.get("event_hash") or _digest(event))
        return {
            "source_key": f"run_event:{event.get('event_id')}",
            "source_kind": "agent_run_event",
            "source_sequence": int(event.get("sequence") or 0),
            "occurred_at": float(event.get("created_at") or 0),
            "event_type": event_type,
            "payload": payload,
            "source_digest": source_digest,
        }

    @classmethod
    def _from_approval(cls, approval: dict[str, Any]) -> list[dict[str, Any]]:
        request = _payload(approval.get("request"))
        approval_id = str(approval.get("approval_id") or "")
        created = {
            "source_key": f"approval:{approval_id}:created",
            "source_kind": "approval_record",
            "source_sequence": 0,
            "occurred_at": float(approval.get("created_at") or 0),
            "event_type": "agent.approval.card.available",
            "payload": {"approval_id": approval_id, "status": "pending", "tool_id": request.get("tool_id"), "summary": f"Approval requested for {request.get('tool_id') or 'tool'}"},
            "source_digest": _digest({"approval_id": approval_id, "request": request, "created_at": approval.get("created_at")}),
        }
        results = [created]
        if str(approval.get("status") or "pending") != "pending":
            resolution = _payload(approval.get("resolution"))
            results.append({
                "source_key": f"approval:{approval_id}:resolved",
                "source_kind": "approval_record",
                "source_sequence": 0,
                "occurred_at": float(approval.get("resolved_at") or approval.get("created_at") or 0),
                "event_type": "agent.approval.card.resolved",
                "payload": {"approval_id": approval_id, "status": approval.get("status"), "summary": f"Approval {approval.get('status')}", "resolution": resolution},
                "source_digest": _digest({"approval_id": approval_id, "status": approval.get("status"), "resolution": resolution, "resolved_at": approval.get("resolved_at")}),
            })
        return results

    @classmethod
    def _materialize(cls, run_id: str, ordinal: int, previous: str, source: dict[str, Any]) -> dict[str, Any]:
        payload = _payload(source["payload"])
        event_type = str(source["event_type"])
        category = cls._category(event_type, payload)
        severity = cls._severity(event_type, payload)
        summary = str(payload.get("summary") or payload.get("message") or event_type.replace("agent.", "").replace(".", " ").strip())
        evidence_digest = str(payload.get("evidence_digest") or payload.get("receipt_digest") or payload.get("observation_digest") or "")
        compact = {"tool_id": payload.get("tool_id") or payload.get("tool"), "status": payload.get("status"), "approval_id": payload.get("approval_id")}
        compact = {key: value for key, value in compact.items() if value not in (None, "")}
        event = {
            "version": VERSION,
            "beast_object_type": EVENT_OBJECT_TYPE,
            "projection_event_id": "console_evt_" + hashlib.sha256(f"{run_id}:{source['source_key']}".encode()).hexdigest()[:24],
            "run_id": run_id,
            "ordinal": ordinal,
            "occurred_at": source["occurred_at"],
            "category": category,
            "severity": severity,
            "event_type": event_type,
            "step_id": str(payload.get("step_id") or ""),
            "summary": summary,
            "compact": compact,
            "detail": payload,
            "evidence_digest": evidence_digest,
            "source_digest": source["source_digest"],
            "previous_projection_digest": previous,
            "authority": "console_event_projection_read_only",
        }
        event["projection_digest"] = _digest(cls._semantic_for_digest(event, previous))
        return event

    @staticmethod
    def _semantic_for_digest(event: dict[str, Any], previous: str) -> dict[str, Any]:
        return {
            "version": VERSION,
            "projection_event_id": event["projection_event_id"],
            "run_id": event["run_id"],
            "ordinal": event["ordinal"],
            "occurred_at": event["occurred_at"],
            "category": event["category"],
            "severity": event["severity"],
            "event_type": event["event_type"],
            "step_id": event["step_id"],
            "summary": event["summary"],
            "compact": event["compact"],
            "detail": event["detail"],
            "evidence_digest": event["evidence_digest"],
            "source_digest": event["source_digest"],
            "previous_projection_digest": previous,
            "authority": "console_event_projection_read_only",
        }

    @staticmethod
    def _row(row: sqlite3.Row, *, expanded: bool) -> dict[str, Any]:
        event = {
            "version": VERSION,
            "beast_object_type": EVENT_OBJECT_TYPE,
            "projection_event_id": str(row["projection_event_id"]),
            "run_id": str(row["run_id"]),
            "ordinal": int(row["ordinal"]),
            "occurred_at": float(row["occurred_at"]),
            "category": str(row["category"]),
            "severity": str(row["severity"]),
            "event_type": str(row["event_type"]),
            "step_id": str(row["step_id"]),
            "summary": str(row["summary"]),
            "compact": json.loads(str(row["compact_json"])),
            "evidence_digest": str(row["evidence_digest"]),
            "source_digest": str(row["source_digest"]),
            "previous_projection_digest": str(row["previous_projection_digest"]),
            "projection_digest": str(row["projection_digest"]),
            "authority": "console_event_projection_read_only",
        }
        if expanded:
            event["detail"] = json.loads(str(row["detail_json"]))
        return event
