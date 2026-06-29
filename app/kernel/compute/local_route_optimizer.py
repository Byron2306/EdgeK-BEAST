import json
import sqlite3
from pathlib import Path
from typing import Optional

class LocalRouteOptimizer:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS route_scores (
                    task_class TEXT NOT NULL,
                    engine_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    successes INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    avg_latency_ms REAL NOT NULL DEFAULT 0,
                    avg_tokens INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(task_class, engine_id, model)
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(route_scores)").fetchall()}
            if "metadata" not in columns:
                conn.execute("ALTER TABLE route_scores ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")

    def record(
        self,
        *,
        task_class: str,
        runtime_engine: str = "",
        engine_id: str = "",
        model: str,
        success: bool,
        latency_ms: float,
        tokens: int,
        teacher_engine: Optional[str] = None,
    ):
        selected_engine = runtime_engine or engine_id
        if not selected_engine:
            selected_engine = "unknown"
        with sqlite3.connect(self.db_path) as conn:
            # Record with teacher engine context
            conn.execute("""
                INSERT INTO route_scores(task_class, engine_id, model, successes, failures, avg_latency_ms, avg_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_class, engine_id, model) DO UPDATE SET
                successes = successes + excluded.successes,
                failures = failures + excluded.failures,
                avg_latency_ms = excluded.avg_latency_ms,
                avg_tokens = excluded.avg_tokens
            """, (task_class, selected_engine, model, 1 if success else 0, 0 if success else 1, latency_ms, tokens))
            
            # Store metadata about training teacher if provided
            if teacher_engine:
                conn.execute("""
                    UPDATE route_scores SET metadata = ?
                    WHERE task_class = ? AND engine_id = ? AND model = ?
                """, (json.dumps({"teacher": teacher_engine}), task_class, selected_engine, model))

    def choose_route(self, request) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT engine_id, successes, failures, avg_latency_ms
                FROM route_scores
                WHERE task_class = ?
            """, (request.task_class,)).fetchall()

        if not rows:
            return None

        def score(row):
            engine_id, successes, failures, latency = row
            reliability = successes / max(1, successes + failures)
            latency_penalty = min(0.3, latency / 100000.0)
            return reliability - latency_penalty

        return sorted(rows, key=score, reverse=True)[0][0]
