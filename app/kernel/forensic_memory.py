"""
Append-only L4 forensic memory.

SQLite is the source of truth. Lexical retrieval is always available; dense
vectors can be layered on later without changing the event contract.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ForensicMemory:
    """Append-only event ledger for runtime/proxy/interception forensics."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "forensic_l4.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forensic_events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    event_kind TEXT NOT NULL,
                    layer TEXT,
                    source_type TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    provider TEXT,
                    route_id TEXT,
                    trace_id TEXT,
                    status TEXT,
                    severity TEXT NOT NULL,
                    priority_score REAL NOT NULL,
                    redaction_status TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    lexical_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(forensic_events)").fetchall()}
            if "layer" not in columns:
                conn.execute("ALTER TABLE forensic_events ADD COLUMN layer TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forensic_kind ON forensic_events(event_kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forensic_layer ON forensic_events(layer)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forensic_provider ON forensic_events(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forensic_status ON forensic_events(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forensic_priority ON forensic_events(priority_score)")

    def append(self, event: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        evidence = evidence or event.get("evidence") or {}
        created_at = str(event.get("created_at") or evidence.get("created_at") or self._utc_now())
        event_kind = str(event.get("event_kind") or event.get("kind") or self._infer_kind(evidence))
        layer = str(event.get("layer") or evidence.get("interception_layer") or self._relationship_id(evidence, "interception_layer") or "L4")
        source_uri = str(event.get("source_uri") or evidence.get("source_uri") or f"forensic://{event_kind}")
        stable = json.dumps({
            "event_kind": event_kind,
            "source_uri": source_uri,
            "event": event,
            "evidence_id": evidence.get("evidence_id"),
            "created_at": created_at,
        }, sort_keys=True, default=str)
        event_id = str(event.get("event_id") or "for_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16])
        lexical_text = self._lexical_text(event, evidence)
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO forensic_events
                (event_id, event_kind, layer, source_type, source_uri, provider, route_id, trace_id,
                 status, severity, priority_score, redaction_status, event_json, evidence_json,
                 lexical_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                event_kind,
                layer,
                str(event.get("source_type") or evidence.get("source_type") or "forensic_event"),
                source_uri,
                event.get("provider") or evidence.get("provider"),
                event.get("route_id"),
                event.get("trace_id"),
                event.get("status"),
                str(event.get("severity") or evidence.get("severity") or "info"),
                float(event.get("priority_score") or evidence.get("priority_score") or 0.0),
                str(event.get("redaction_status") or "metadata_only"),
                json.dumps(event, sort_keys=True, default=str),
                json.dumps(evidence, sort_keys=True, default=str),
                lexical_text,
                created_at,
            ))
        return {"written": True, "event_id": event_id, "db": str(self.db_path)}

    def query(
        self,
        query: str = "",
        *,
        event_kind: Optional[str] = None,
        layer: Optional[str] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        clauses = []
        params: List[Any] = []
        if event_kind:
            clauses.append("event_kind = ?")
            params.append(event_kind)
        if layer:
            clauses.append("layer = ?")
            params.append(str(layer).upper())
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 100)))
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT sequence_id, event_id, event_kind, layer, source_type, source_uri, provider,
                       route_id, trace_id, status, severity, priority_score, redaction_status,
                       event_json, evidence_json, lexical_text, created_at
                FROM forensic_events
                {where}
                ORDER BY sequence_id DESC
                LIMIT ?
            """, params).fetchall()
        scored = [self._row_to_result(row, query) for row in rows]
        if query:
            scored.sort(key=lambda item: (item["lexical_score"], item["priority_score"], item["sequence_id"]), reverse=True)
        return {
            "beast_object_type": "forensic_l4_query",
            "version": "1.0",
            "query": query,
            "filters": {"event_kind": event_kind, "layer": layer, "provider": provider, "status": status},
            "result_count": len(scored),
            "retrieval_mode": "lexical_fallback",
            "vector_available": False,
            "results": scored,
        }

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM forensic_events").fetchone()[0]
            kinds = conn.execute("SELECT event_kind, COUNT(*) FROM forensic_events GROUP BY event_kind").fetchall()
            layers = conn.execute("SELECT layer, COUNT(*) FROM forensic_events WHERE layer IS NOT NULL GROUP BY layer").fetchall()
            providers = conn.execute("SELECT provider, COUNT(*) FROM forensic_events WHERE provider IS NOT NULL GROUP BY provider").fetchall()
        return {
            "beast_object_type": "forensic_l4_state",
            "version": "1.0",
            "events": total,
            "event_kinds": {row[0]: row[1] for row in kinds},
            "layers": {row[0]: row[1] for row in layers},
            "providers": {row[0]: row[1] for row in providers},
            "retrieval": {
                "source_of_truth": "sqlite",
                "lexical_fallback": True,
                "dense_vectors_optional": True,
                "metadata_filters_before_scoring": True,
            },
            "db": str(self.db_path),
        }

    def _row_to_result(self, row: Any, query: str) -> Dict[str, Any]:
        lexical_text = row[15] or ""
        return {
            "sequence_id": row[0],
            "event_id": row[1],
            "event_kind": row[2],
            "layer": row[3],
            "source_type": row[4],
            "source_uri": row[5],
            "provider": row[6],
            "route_id": row[7],
            "trace_id": row[8],
            "status": row[9],
            "severity": row[10],
            "priority_score": row[11],
            "redaction_status": row[12],
            "event": json.loads(row[13] or "{}"),
            "evidence": json.loads(row[14] or "{}"),
            "lexical_score": self._lexical_score(query, lexical_text),
            "created_at": row[16],
        }

    def _lexical_score(self, query: str, text: str) -> float:
        if not query:
            return 0.0
        tokens = [token.lower() for token in query.split() if len(token) >= 3]
        lowered = text.lower()
        if not tokens:
            return 0.0
        hits = sum(lowered.count(token) for token in tokens)
        return round(hits / max(len(tokens), 1), 5)

    def _lexical_text(self, event: Dict[str, Any], evidence: Dict[str, Any]) -> str:
        return " ".join(
            str(value)
            for value in [
                event.get("event_kind"),
                event.get("layer"),
                event.get("status"),
                event.get("provider"),
                event.get("route_id"),
                event.get("trace_id"),
                event.get("summary"),
                event.get("message"),
                evidence.get("summary"),
                evidence.get("interception_layer"),
                " ".join(evidence.get("signals") or []),
                " ".join(evidence.get("recommended_actions") or []),
            ]
            if value
        )

    def _infer_kind(self, evidence: Dict[str, Any]) -> str:
        artifact = str(evidence.get("artifact_type") or "")
        if ":" in artifact:
            return artifact.split(":", 1)[1]
        return str(evidence.get("source_type") or "forensic")

    def _relationship_id(self, evidence: Dict[str, Any], relationship_type: str) -> Optional[str]:
        for relationship in evidence.get("relationships") or []:
            if relationship.get("type") == relationship_type and relationship.get("id"):
                return str(relationship["id"])
        return None

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
