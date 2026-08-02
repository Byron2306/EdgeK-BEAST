"""Immutable storage and verification for deterministic fingerprint bundles."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.kernel.evidence.evidence_digest import canonical_bytes, sha256_bytes, sha256_digest
from app.kernel.evidence.evidence_store import EvidenceStore


class FingerprintStore:
    def __init__(self, workspace_root: str | Path):
        self.evidence_store = EvidenceStore(workspace_root)
        self.db_path = self.evidence_store.db_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS evidence_fingerprints(
                    evidence_id TEXT PRIMARY KEY,
                    bundle_digest TEXT NOT NULL,
                    object_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(evidence_id) REFERENCES evidence_objects(evidence_id)
                )
            """)

    def put(self, evidence_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
        if not self.evidence_store.get(evidence_id):
            raise KeyError(f"unknown evidence crystal: {evidence_id}")
        expected = sha256_digest({k: v for k, v in bundle.items() if k != "bundle_digest"})
        if bundle.get("bundle_digest") != expected:
            raise ValueError("fingerprint bundle digest mismatch")
        payload = canonical_bytes(bundle)
        path = self.evidence_store._path_for_digest(sha256_bytes(payload))
        self.evidence_store._write_once(path, payload)
        with self._connect() as connection:
            existing = connection.execute("SELECT * FROM evidence_fingerprints WHERE evidence_id=?", (evidence_id,)).fetchone()
            if existing:
                if str(existing["bundle_digest"]) != expected:
                    raise PermissionError("evidence fingerprint is immutable")
                return self.get(evidence_id) or {}
            connection.execute(
                "INSERT INTO evidence_fingerprints(evidence_id,bundle_digest,object_path,created_at) VALUES(?,?,?,?)",
                (evidence_id, expected, str(path), time.time()),
            )
        return self.get(evidence_id) or {}

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evidence_fingerprints WHERE evidence_id=?", (evidence_id,)).fetchone()
        if not row:
            return None
        path = Path(str(row["object_path"]))
        if not path.is_file():
            raise RuntimeError("fingerprint object file is missing")
        return json.loads(path.read_text(encoding="utf-8"))

    def verify(self, evidence_id: str) -> dict[str, Any]:
        bundle = self.get(evidence_id)
        if not bundle:
            raise KeyError(f"unknown evidence fingerprint: {evidence_id}")
        expected = sha256_digest({k: v for k, v in bundle.items() if k != "bundle_digest"})
        task = bundle.get("task") or {}
        environment = bundle.get("environment") or {}
        checks = {
            "bundle_digest": expected == bundle.get("bundle_digest"),
            "task_digest": sha256_digest(task.get("components") or {}) == task.get("digest"),
            "environment_digest": sha256_digest(environment.get("components") or {}) == environment.get("digest"),
        }
        return {"ok": all(checks.values()), "evidence_id": evidence_id, "checks": checks, "bundle_digest": bundle.get("bundle_digest")}
