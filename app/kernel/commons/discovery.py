"""Transport-neutral candidate catalog for the Trust Commons.

Discovery is not admission. DNS-SD, static seeds, peer exchange, QR/bootstrap
documents, registries, or future transports can all submit the same signed
node envelope; only lattice/ARDA trust verification may promote a candidate.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Mapping


DISCOVERY_PROTOCOL = "beast-trust-commons-discovery-v1"
SOURCES = frozenset({"static_seed", "well_known", "dns_sd", "peer_exchange", "registry", "qr_bootstrap", "manual"})


class CommonsDiscoveryCatalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS commons_discovery_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    subject_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    trust_json TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    UNIQUE(source,origin,node_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def observe(
        self, *, candidate_id: str, source: str, origin: str, node_id: str,
        subject_digest: str, state: str, trust: Mapping[str, Any], document: Mapping[str, Any],
    ) -> dict[str, Any]:
        if source not in SOURCES:
            raise ValueError("unsupported Commons discovery source")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO commons_discovery_candidates(candidate_id,source,origin,node_id,subject_digest,state,trust_json,document_json,first_seen,last_seen) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,origin,node_id) DO UPDATE SET candidate_id=excluded.candidate_id,subject_digest=excluded.subject_digest,state=excluded.state,trust_json=excluded.trust_json,document_json=excluded.document_json,last_seen=excluded.last_seen",
                (candidate_id, source, origin, node_id, subject_digest, state,
                 json.dumps(dict(trust), sort_keys=True, separators=(",", ":")),
                 json.dumps(dict(document), sort_keys=True, separators=(",", ":"), default=str), now, now),
            )
        return self.find(source=source, origin=origin, node_id=node_id)

    def find(self, *, source: str, origin: str, node_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM commons_discovery_candidates WHERE source=? AND origin=? AND node_id=?",
                (source, origin, node_id),
            ).fetchone()
        if row is None:
            raise LookupError("Commons discovery candidate not found")
        return self._row(row)

    def list(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM commons_discovery_candidates ORDER BY last_seen DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "candidate_id": row["candidate_id"], "source": row["source"], "origin": row["origin"],
            "node_id": row["node_id"], "subject_digest": row["subject_digest"], "state": row["state"],
            "trust": json.loads(row["trust_json"] or "{}"), "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
        }

    def snapshot(self) -> dict[str, Any]:
        rows = self.list()
        return {
            "protocol": DISCOVERY_PROTOCOL,
            "candidate_count": len(rows),
            "trusted_candidate_count": sum(1 for row in rows if row["state"] == "trusted_candidate"),
            "sources": sorted(SOURCES),
            "candidates": rows,
            "admission_boundary": "discovery_never_implies_trust",
        }
