from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .digests import canonical_json, sha256_digest
from .models import ApprovalContractFactory
from .state import ApprovalState, TERMINAL_STATES, normalize_state

SCHEMA_VERSION = "4.2"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class DurableApprovalStore:
    """SQLite-backed append-only approval event store with rebuildable projections."""

    def __init__(self, root_path: str | Path):
        self.root = Path(root_path).expanduser().resolve()
        self.state_dir = self.root / ".beast" / "approvals"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "approvals.sqlite3"
        self.factory = ApprovalContractFactory()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS approval_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                approval_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_json TEXT NOT NULL,
                previous_event_digest TEXT NOT NULL,
                event_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_approval_events_id ON approval_events(approval_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_approval_events_run ON approval_events(run_id, sequence);
            CREATE TABLE IF NOT EXISTS approval_projection (
                approval_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                state TEXT NOT NULL,
                request_json TEXT NOT NULL,
                decision_json TEXT,
                latest_transition_json TEXT,
                latest_event_digest TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_projection_run_step_active
            ON approval_projection(run_id, step_id)
            WHERE state IN ('REQUESTED','PENDING','APPROVED','EDITED_AND_APPROVED');
            CREATE TABLE IF NOT EXISTS approval_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR REPLACE INTO approval_meta(key, value) VALUES('schema_version', '4.2');
            """)

    @staticmethod
    def _event_digest(event: Mapping[str, Any]) -> str:
        return sha256_digest({k: v for k, v in event.items() if k != "event_digest"})

    def _append(self, db: sqlite3.Connection, *, request: Mapping[str, Any], event_type: str,
                payload: Mapping[str, Any], previous_digest: str) -> dict[str, Any]:
        event = {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_durable_approval_event",
            "approval_id": request["approval_id"],
            "run_id": request["run_id"],
            "step_id": request["step_id"],
            "event_type": event_type,
            "payload": payload,
            "previous_event_digest": previous_digest,
            "created_at": _utcnow().isoformat().replace("+00:00", "Z"),
        }
        event["event_digest"] = self._event_digest(event)
        db.execute(
            "INSERT INTO approval_events(approval_id,run_id,step_id,event_type,event_json,previous_event_digest,event_digest,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (request["approval_id"], request["run_id"], request["step_id"], event_type,
             canonical_json(event), previous_digest, event["event_digest"], event["created_at"]),
        )
        return event

    def create(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.factory.validate_request(request)
        if normalize_state(request["state"]) != ApprovalState.REQUESTED:
            raise ValueError("new durable approval must begin in REQUESTED")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM approval_projection WHERE approval_id=?", (request["approval_id"],)).fetchone():
                    raise ValueError("approval already exists")
                event = self._append(db, request=request, event_type="agent.approval.requested", payload={"request": request}, previous_digest="")
                transition = self.factory.create_transition(request, from_state="REQUESTED", to_state="PENDING", actor="beast-approval-store", reason="persisted for operator review")
                event2 = self._append(db, request=request, event_type="agent.approval.pending", payload={"transition": transition}, previous_digest=event["event_digest"])
                db.execute("INSERT INTO approval_projection VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    request["approval_id"], request["run_id"], request["step_id"], "PENDING",
                    canonical_json(request), None, canonical_json(transition), event2["event_digest"], request["expires_at"], event2["created_at"]
                ))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.get(str(request["approval_id"]))

    def transition(self, approval_id: str, *, to_state: str, actor: str, reason: str,
                   decision: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT * FROM approval_projection WHERE approval_id=?", (approval_id,)).fetchone()
                if not row:
                    raise KeyError(f"unknown approval: {approval_id}")
                request = json.loads(row["request_json"])
                current = normalize_state(row["state"])
                target = normalize_state(to_state)
                if decision:
                    self.factory.validate_decision(decision, request=request)
                transition = self.factory.create_transition(request, from_state=current, to_state=target,
                    actor=actor, reason=reason, decision=decision,
                    previous_transition_digest=(json.loads(row["latest_transition_json"] or "{}").get("transition_digest") or ""))
                event = self._append(db, request=request, event_type=f"agent.approval.{target.value.lower()}",
                    payload={"transition": transition, "decision": decision or {}}, previous_digest=row["latest_event_digest"])
                db.execute("UPDATE approval_projection SET state=?,decision_json=?,latest_transition_json=?,latest_event_digest=?,updated_at=? WHERE approval_id=?", (
                    target.value, canonical_json(decision) if decision else row["decision_json"], canonical_json(transition), event["event_digest"], event["created_at"], approval_id
                ))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.get(approval_id)

    def get(self, approval_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM approval_projection WHERE approval_id=?", (approval_id,)).fetchone()
        if not row:
            raise KeyError(f"unknown approval: {approval_id}")
        return self._row(row)

    def list(self, *, run_id: str | None = None, state: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses, values = [], []
        if run_id:
            clauses.append("run_id=?"); values.append(run_id)
        if state:
            clauses.append("state=?"); values.append(normalize_state(state).value)
        sql = "SELECT * FROM approval_projection" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY updated_at DESC LIMIT ?"
        values.append(max(1, min(int(limit), 500)))
        with self._connect() as db:
            return [self._row(row) for row in db.execute(sql, values).fetchall()]

    def events(self, approval_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT event_json FROM approval_events WHERE approval_id=? ORDER BY sequence", (approval_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def verify_chain(self, approval_id: str) -> dict[str, Any]:
        events = self.events(approval_id)
        previous = ""
        for index, event in enumerate(events):
            if event.get("previous_event_digest") != previous or self._event_digest(event) != event.get("event_digest"):
                return {"ok": False, "approval_id": approval_id, "failed_index": index}
            previous = str(event["event_digest"])
        return {"ok": bool(events), "approval_id": approval_id, "event_count": len(events), "head_digest": previous}

    def expire_due(self, *, now: datetime | None = None) -> list[str]:
        now = now or _utcnow()
        expired = []
        for item in self.list(limit=500):
            state = normalize_state(item["state"])
            if state not in TERMINAL_STATES and _parse_time(item["request"]["expires_at"]) <= now:
                self.transition(item["approval_id"], to_state="EXPIRED", actor="beast-approval-recovery", reason="approval expired")
                expired.append(item["approval_id"])
        return expired

    def rebuild_projection(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT event_json FROM approval_events ORDER BY sequence").fetchall()
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("DELETE FROM approval_projection")
                projections: dict[str, dict[str, Any]] = {}
                for row in rows:
                    event = json.loads(row[0]); aid = event["approval_id"]; payload = event.get("payload") or {}
                    if "request" in payload:
                        request = payload["request"]
                        projections[aid] = {"request": request, "state": "REQUESTED", "decision": None, "transition": None, "head": event["event_digest"], "updated": event["created_at"]}
                    projection = projections.get(aid)
                    if not projection:
                        raise ValueError(f"event chain begins without request: {aid}")
                    transition = payload.get("transition")
                    if transition:
                        projection["state"] = transition["to_state"]; projection["transition"] = transition
                    if payload.get("decision"):
                        projection["decision"] = payload["decision"]
                    projection["head"] = event["event_digest"]; projection["updated"] = event["created_at"]
                for aid, p in projections.items():
                    req = p["request"]
                    db.execute("INSERT INTO approval_projection VALUES(?,?,?,?,?,?,?,?,?,?)", (
                        aid, req["run_id"], req["step_id"], p["state"], canonical_json(req),
                        canonical_json(p["decision"]) if p["decision"] else None,
                        canonical_json(p["transition"]) if p["transition"] else None,
                        p["head"], req["expires_at"], p["updated"]
                    ))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK"); raise
        return {"ok": True, "approval_count": len(projections), "event_count": len(rows)}

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_durable_approval_projection",
            "approval_id": row["approval_id"], "run_id": row["run_id"], "step_id": row["step_id"],
            "state": row["state"], "request": json.loads(row["request_json"]),
            "decision": json.loads(row["decision_json"]) if row["decision_json"] else None,
            "latest_transition": json.loads(row["latest_transition_json"]) if row["latest_transition_json"] else None,
            "latest_event_digest": row["latest_event_digest"], "updated_at": row["updated_at"],
        }
