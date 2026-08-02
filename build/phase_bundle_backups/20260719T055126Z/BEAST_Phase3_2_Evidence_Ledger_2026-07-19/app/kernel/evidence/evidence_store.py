"""Append-only SQLite and content-addressed storage for evidence crystals."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.kernel.evidence.evidence_digest import canonical_bytes, sha256_bytes


class EvidenceStore:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.root = self.workspace_root / ".beast" / "evidence"
        self.objects_root = self.root / "objects"
        self.db_path = self.root / "evidence.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS evidence_objects(
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    version TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL UNIQUE,
                    object_path TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_artifacts(
                    artifact_id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    object_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(evidence_id) REFERENCES evidence_objects(evidence_id)
                );
            """)

    def _path_for_digest(self, digest: str, suffix: str = ".json") -> Path:
        value = digest.removeprefix("sha256:")
        return self.objects_root / value[:2] / value[2:4] / f"{value}{suffix}"

    @staticmethod
    def _write_once(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise RuntimeError(f"content-address collision at {path}")
            return
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def put_artifact(self, evidence_id: str, artifact_id: str, kind: str, value: Any) -> dict[str, Any]:
        payload = canonical_bytes(value)
        digest = sha256_bytes(payload)
        path = self._path_for_digest(digest)
        self._write_once(path, payload)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO evidence_artifacts(artifact_id,evidence_id,kind,digest,object_path,created_at) VALUES(?,?,?,?,?,?)",
                (artifact_id, evidence_id, kind, digest, str(path), time.time()),
            )
        return {"artifact_id": artifact_id, "kind": kind, "digest": digest, "object_path": str(path)}

    def put(self, evidence: dict[str, Any]) -> dict[str, Any]:
        evidence_id = str(evidence["evidence_id"])
        payload = canonical_bytes(evidence)
        digest = sha256_bytes(canonical_bytes({k: v for k, v in evidence.items() if k != "evidence_digest"}))
        if digest != evidence.get("evidence_digest"):
            raise ValueError("evidence digest does not match canonical object")
        path = self._path_for_digest(digest)
        self._write_once(path, payload)
        with self._lock, self._connect() as connection:
            existing = connection.execute("SELECT * FROM evidence_objects WHERE run_id=?", (str(evidence["run_id"]),)).fetchone()
            if existing:
                if str(existing["evidence_digest"]) != digest:
                    raise PermissionError("promoted AgentRun already crystallized into different immutable evidence")
                return self.get(str(existing["evidence_id"])) or {}
            connection.execute(
                "INSERT INTO evidence_objects(evidence_id,run_id,kind,version,evidence_digest,object_path,created_at) VALUES(?,?,?,?,?,?,?)",
                (evidence_id, str(evidence["run_id"]), str(evidence["kind"]), str(evidence["version"]), digest, str(path), float(evidence["created_at"])),
            )
        return self.get(evidence_id) or {}

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evidence_objects WHERE evidence_id=?", (evidence_id,)).fetchone()
        if not row:
            return None
        path = Path(str(row["object_path"]))
        if not path.is_file():
            raise RuntimeError("evidence object file is missing")
        return json.loads(path.read_text(encoding="utf-8"))

    def get_by_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT evidence_id FROM evidence_objects WHERE run_id=?", (run_id,)).fetchone()
        return self.get(str(row["evidence_id"])) if row else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT evidence_id FROM evidence_objects ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
        return [item for row in rows if (item := self.get(str(row["evidence_id"]))) is not None]
