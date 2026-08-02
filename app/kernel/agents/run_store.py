"""SQLite WAL durability and hash-chained replay for BEAST agent runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.kernel.agents.run_state import AgentRunState, TERMINAL_STATES, normalize_state, require_transition


_RUNTIME_INSTANCE_ID = uuid.uuid4().hex


def _now() -> float:
    return time.time()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _slug(value: str, fallback: str = "run") -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return (clean or fallback)[:48]


class AgentRunStore:
    """Workspace-scoped durable run/event store.

    This is a specialized read model and replay ledger. Sensorium remains the
    platform-wide observation journal; Phase 2A mirrors run events there on a
    best-effort basis through ``AgentRunEngine``.
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "agent_runs"
        if self.store_dir.parent.exists() and not os.access(self.store_dir.parent, os.W_OK):
            scope = hashlib.sha256(str(self.workspace_root).encode("utf-8")).hexdigest()[:16]
            base = Path(os.environ.get("BEAST_AGENT_RUN_STATE_DIR", "~/.local/state/edgek-beast/agent_runs")).expanduser()
            self.store_dir = base / scope
        self.db_path = self.store_dir / "agent_runs.sqlite3"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()
        self._claim_runtime_instance()


    def _claim_runtime_instance(self) -> None:
        """Pause orphaned active runs exactly once when a new process opens the store."""
        active = tuple(
            state.value for state in AgentRunState
            if state not in TERMINAL_STATES and state not in {AgentRunState.CREATED, AgentRunState.PAUSED}
        )
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value FROM agent_run_meta WHERE key='runtime_instance'"
            ).fetchone()
            previous = str(row[0]) if row else ""
            if previous != _RUNTIME_INSTANCE_ID and active:
                placeholders = ",".join("?" for _ in active)
                connection.execute(
                    f"UPDATE agent_runs SET state=?,error=?,updated_at=? WHERE state IN ({placeholders})",
                    (AgentRunState.PAUSED.value, "runtime_restarted; resume required", _now(), *active),
                )
            connection.execute(
                "INSERT INTO agent_run_meta(key,value) VALUES('runtime_instance',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_RUNTIME_INSTANCE_ID,),
            )
            connection.execute("COMMIT")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_run_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    state TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    cancel_reason TEXT NOT NULL DEFAULT '',
                    last_sequence INTEGER NOT NULL DEFAULT 0,
                    head_hash TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_state ON agent_runs(state, updated_at DESC);
                CREATE TABLE IF NOT EXISTS agent_run_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    legacy_type TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    PRIMARY KEY(run_id, sequence),
                    FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS agent_run_approvals (
                    approval_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    resolution_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    resolved_at REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(run_id, approval_id),
                    FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_agent_approvals_run ON agent_run_approvals(run_id, created_at);
                """
            )

    def create_run(
        self,
        *,
        session_id: str,
        objective: str,
        mode: str = "agent",
        provider: str = "",
        model: str = "",
        request: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> dict[str, Any]:
        created = _now()
        identifier = run_id.strip() or f"{_slug(session_id or mode)}-{uuid.uuid4().hex[:12]}"
        record = {
            "run_id": identifier,
            "session_id": str(session_id or ""),
            "objective": str(objective or "BEAST agent run"),
            "mode": str(mode or "agent"),
            "provider": str(provider or ""),
            "model": str(model or ""),
            "state": AgentRunState.CREATED.value,
            "root_path": str(self.workspace_root),
            "request_json": json.dumps(request or {}, sort_keys=True, default=str),
            "checkpoint_json": json.dumps({}, sort_keys=True),
            "budget_json": json.dumps(budget or {}, sort_keys=True, default=str),
            "created_at": created,
            "updated_at": created,
        }
        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT INTO agent_runs(
                        run_id,session_id,objective,mode,provider,model,state,root_path,
                        request_json,checkpoint_json,budget_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(record[key] for key in (
                        "run_id", "session_id", "objective", "mode", "provider", "model", "state",
                        "root_path", "request_json", "checkpoint_json", "budget_json", "created_at", "updated_at",
                    )),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                existing = self.get_run(identifier)
                if existing:
                    return existing
                raise
        self.append_event(identifier, "agent.run.created", {
            "session_id": record["session_id"],
            "objective": record["objective"],
            "mode": record["mode"],
            "provider": record["provider"],
            "model": record["model"],
        })
        return self.get_run(identifier) or {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(row) if row else None

    def list_runs(self, *, session_id: str = "", state: str = "", limit: int = 50) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            values.append(session_id)
        if state:
            clauses.append("state=?")
            values.append(normalize_state(state).value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(int(limit), 250)))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM agent_runs{where} ORDER BY updated_at DESC LIMIT ?", values
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def transition(self, run_id: str, state: str | AgentRunState, *, error: str = "") -> dict[str, Any]:
        target = normalize_state(state)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                connection.execute("ROLLBACK")
                raise KeyError(f"unknown agent run: {run_id}")
            current = normalize_state(str(row["state"]))
            require_transition(current, target)
            connection.execute(
                "UPDATE agent_runs SET state=?,error=?,updated_at=? WHERE run_id=?",
                (target.value, str(error or ""), _now(), run_id),
            )
            connection.execute("COMMIT")
        return self.get_run(run_id) or {}

    def checkpoint(self, run_id: str, value: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(value or {}, sort_keys=True, default=str)
        with self._connect() as connection:
            connection.execute(
                "UPDATE agent_runs SET checkpoint_json=?,updated_at=? WHERE run_id=?",
                (payload, _now(), run_id),
            )
        return self.get_run(run_id) or {}

    def merge_budget(self, run_id: str, delta: dict[str, Any]) -> dict[str, Any]:
        record = self.get_run(run_id)
        if not record:
            raise KeyError(f"unknown agent run: {run_id}")
        budget = dict(record.get("budget") or {})
        for key, value in (delta or {}).items():
            try:
                budget[str(key)] = float(budget.get(str(key)) or 0) + float(value)
            except (TypeError, ValueError):
                budget[str(key)] = value
        with self._connect() as connection:
            connection.execute(
                "UPDATE agent_runs SET budget_json=?,updated_at=? WHERE run_id=?",
                (json.dumps(budget, sort_keys=True, default=str), _now(), run_id),
            )
        return self.get_run(run_id) or {}

    def request_cancel(self, run_id: str, reason: str = "") -> dict[str, Any]:
        record = self.get_run(run_id)
        if not record:
            raise KeyError(f"unknown agent run: {run_id}")
        if normalize_state(record["state"]) not in TERMINAL_STATES:
            self.transition(run_id, AgentRunState.CANCELLING)
        with self._connect() as connection:
            connection.execute(
                "UPDATE agent_runs SET cancel_requested=1,cancel_reason=?,updated_at=? WHERE run_id=?",
                (str(reason or "operator_cancelled"), _now(), run_id),
            )
        return self.get_run(run_id) or {}

    def clear_cancel(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                "UPDATE agent_runs SET cancel_requested=0,cancel_reason='',updated_at=? WHERE run_id=?",
                (_now(), run_id),
            )
        return self.get_run(run_id) or {}

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT cancel_requested FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        return bool(row and int(row[0]))

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        legacy_type: str = "",
    ) -> dict[str, Any]:
        value = dict(payload or {})
        created = _now()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT last_sequence,head_hash FROM agent_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if not row:
                connection.execute("ROLLBACK")
                raise KeyError(f"unknown agent run: {run_id}")
            sequence = int(row["last_sequence"]) + 1
            previous_hash = str(row["head_hash"] or "")
            body = {
                "run_id": run_id,
                "sequence": sequence,
                "event_type": str(event_type),
                "legacy_type": str(legacy_type or ""),
                "created_at": created,
                "payload": value,
            }
            event_hash = "sha256:" + hashlib.sha256(previous_hash.encode("utf-8") + _canonical(body)).hexdigest()
            event_id = f"evt-{hashlib.sha256(_canonical({**body, 'event_hash': event_hash})).hexdigest()[:24]}"
            connection.execute(
                """INSERT INTO agent_run_events(
                    run_id,sequence,event_id,event_type,legacy_type,created_at,payload_json,previous_hash,event_hash
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, sequence, event_id, str(event_type), str(legacy_type or ""), created,
                    json.dumps(value, sort_keys=True, ensure_ascii=False, default=str), previous_hash, event_hash,
                ),
            )
            connection.execute(
                "UPDATE agent_runs SET last_sequence=?,head_hash=?,updated_at=? WHERE run_id=?",
                (sequence, event_hash, created, run_id),
            )
            connection.execute("COMMIT")
        return {
            "event_id": event_id,
            "run_id": run_id,
            "sequence": sequence,
            "event_type": str(event_type),
            "legacy_type": str(legacy_type or ""),
            "created_at": created,
            "payload": value,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        }

    def events(self, run_id: str, *, after: int = 0, limit: int = 250) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT run_id,sequence,event_id,event_type,legacy_type,created_at,payload_json,previous_hash,event_hash
                   FROM agent_run_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?""",
                (run_id, max(0, int(after)), max(1, min(int(limit), 100000))),
            ).fetchall()
        return [self._event_row(row) for row in rows]

    def verify_chain(self, run_id: str) -> dict[str, Any]:
        previous = ""
        expected = 1
        events = self.events(run_id, after=0, limit=1_000_000)
        for event in events:
            body = {
                "run_id": run_id,
                "sequence": event["sequence"],
                "event_type": event["event_type"],
                "legacy_type": event["legacy_type"],
                "created_at": event["created_at"],
                "payload": event["payload"],
            }
            calculated = "sha256:" + hashlib.sha256(previous.encode("utf-8") + _canonical(body)).hexdigest()
            if event["sequence"] != expected or event["previous_hash"] != previous or event["event_hash"] != calculated:
                return {"ok": False, "run_id": run_id, "sequence": event["sequence"], "reason": "chain_mismatch"}
            previous = event["event_hash"]
            expected += 1
        run = self.get_run(run_id)
        return {
            "ok": bool(run),
            "run_id": run_id,
            "events": len(events),
            "head_hash": previous,
            "stored_head_hash": str((run or {}).get("head_hash") or ""),
            "head_matches": bool(run) and previous == str(run.get("head_hash") or ""),
        }

    def create_approval(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(request.get("request_id") or request.get("approval_id") or f"approval-{uuid.uuid4().hex[:16]}")
        created = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO agent_run_approvals(
                    approval_id,run_id,status,request_json,resolution_json,created_at,resolved_at
                ) VALUES(?,?, 'pending', ?, '{}', ?, 0)""",
                (approval_id, run_id, json.dumps(request, sort_keys=True, default=str), created),
            )
        return self.get_approval(run_id, approval_id) or {}

    def get_approval(self, run_id: str, approval_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM agent_run_approvals WHERE run_id=? AND approval_id=?", (run_id, approval_id)).fetchone()
        return self._approval_row(row) if row else None

    def approvals(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_run_approvals WHERE run_id=? ORDER BY created_at", (run_id,)
            ).fetchall()
        return [self._approval_row(row) for row in rows]

    def list_approvals(self, run_id: str) -> list[dict[str, Any]]:
        """Compatibility alias for planner/runtime consumers.

        The durable store historically exposed ``approvals`` while newer
        worker code uses the explicit ``list_approvals`` contract. Keep both
        names backed by the same query so approval state remains shared.
        """
        return self.approvals(run_id)

    def resolve_approval(self, run_id: str, approval_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
        current = self.get_approval(run_id, approval_id)
        if not current or current["run_id"] != run_id:
            raise KeyError(f"unknown approval for run: {approval_id}")
        status = "approved" if bool(resolution.get("approved")) else "rejected"
        with self._connect() as connection:
            connection.execute(
                "UPDATE agent_run_approvals SET status=?,resolution_json=?,resolved_at=? WHERE approval_id=? AND run_id=?",
                (status, json.dumps(resolution, sort_keys=True, default=str), _now(), approval_id, run_id),
            )
        return self.get_approval(run_id, approval_id) or {}

    def recover_interrupted_runs(self) -> int:
        active = tuple(state.value for state in AgentRunState if state not in TERMINAL_STATES and state not in {AgentRunState.CREATED, AgentRunState.PAUSED})
        placeholders = ",".join("?" for _ in active)
        if not active:
            return 0
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE agent_runs SET state=?,error=?,updated_at=? WHERE state IN ({placeholders})",
                (AgentRunState.PAUSED.value, "runtime_restarted; resume required", _now(), *active),
            )
        return int(cursor.rowcount or 0)

    @staticmethod
    def _json(value: str, fallback: Any) -> Any:
        try:
            decoded = json.loads(value)
            return decoded
        except Exception:
            return fallback

    def _run_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "beast_object_type": "beast_agent_run",
            "version": "2.0",
            "run_id": str(row["run_id"]),
            "session_id": str(row["session_id"]),
            "objective": str(row["objective"]),
            "mode": str(row["mode"]),
            "provider": str(row["provider"]),
            "model": str(row["model"]),
            "state": str(row["state"]),
            "root_path": str(row["root_path"]),
            "request": self._json(str(row["request_json"]), {}),
            "checkpoint": self._json(str(row["checkpoint_json"]), {}),
            "budget": self._json(str(row["budget_json"]), {}),
            "cancel_requested": bool(row["cancel_requested"]),
            "cancel_reason": str(row["cancel_reason"]),
            "last_sequence": int(row["last_sequence"]),
            "head_hash": str(row["head_hash"]),
            "error": str(row["error"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def _event_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": str(row["event_id"]),
            "run_id": str(row["run_id"]),
            "sequence": int(row["sequence"]),
            "event_type": str(row["event_type"]),
            "legacy_type": str(row["legacy_type"]),
            "created_at": float(row["created_at"]),
            "payload": self._json(str(row["payload_json"]), {}),
            "previous_hash": str(row["previous_hash"]),
            "event_hash": str(row["event_hash"]),
        }

    def _approval_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "beast_object_type": "beast_agent_approval",
            "version": "2.0",
            "approval_id": str(row["approval_id"]),
            "run_id": str(row["run_id"]),
            "status": str(row["status"]),
            "request": self._json(str(row["request_json"]), {}),
            "resolution": self._json(str(row["resolution_json"]), {}),
            "created_at": float(row["created_at"]),
            "resolved_at": float(row["resolved_at"]),
        }
