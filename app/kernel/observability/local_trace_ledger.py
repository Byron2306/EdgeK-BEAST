"""Local SQLite/JSONL trace ledger for BEAST runtime observations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class LocalTraceLedger:
    def __init__(self, db_path: Path, jsonl_path: Path):
        self.db_path = Path(db_path)
        self.jsonl_path = Path(jsonl_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trace_events (
                    event_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_id ON trace_events(trace_id)")

    def record(self, trace_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = {
            "beast_object_type": "local_trace_event",
            "version": "1.0",
            "event_id": f"trace_evt_{uuid.uuid4().hex[:16]}",
            "trace_id": trace_id,
            "event_type": event_type,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trace_events(event_id, trace_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["trace_id"],
                    event["event_type"],
                    json.dumps(event["payload"], sort_keys=True, default=str),
                    event["created_at"],
                ),
            )

        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")

        return event
