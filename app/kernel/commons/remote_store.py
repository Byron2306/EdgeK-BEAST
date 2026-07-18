"""Durable Hugging Face-like bucket and revision store for Commons nodes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence

from .remote_protocol import canonical_json, sha256_bytes


_SEGMENT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


def _segment(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SEGMENT.fullmatch(normalized) or normalized in {".", ".."}:
        raise ValueError(f"invalid Commons {label}")
    return normalized


class CommonsBucketStore:
    """SQLite metadata plus immutable content-addressed blob bytes."""

    def __init__(self, root: str | Path, *, maximum_blob_bytes: int = 4 * 1024**3):
        self.root = Path(root)
        self.blob_root = self.root / "blobs" / "sha256"
        self.db_path = self.root / "commons-node.sqlite3"
        self.maximum_blob_bytes = int(maximum_blob_bytes)
        self.root.mkdir(parents=True, exist_ok=True)
        self.blob_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS buckets (
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    visibility TEXT NOT NULL CHECK(visibility IN ('public','private')),
                    description TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(owner,name)
                );
                CREATE TABLE IF NOT EXISTS blobs (
                    digest TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    committed_by TEXT NOT NULL,
                    committed_at REAL NOT NULL,
                    PRIMARY KEY(owner,name,revision),
                    FOREIGN KEY(owner,name) REFERENCES buckets(owner,name) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS revisions_digest_idx ON revisions(manifest_digest);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def bucket_id(owner: str, name: str) -> str:
        return f"{owner}/{name}"

    def create_bucket(self, *, owner: str, name: str, visibility: str, description: str, actor: str) -> dict[str, Any]:
        owner = _segment(owner, "owner")
        name = _segment(name, "bucket name")
        visibility = str(visibility or "private").lower()
        if visibility not in {"public", "private"}:
            raise ValueError("Commons bucket visibility must be public or private")
        description = str(description or "").strip()[:1000]
        if not actor:
            raise PermissionError("Commons bucket creation requires an authenticated actor")
        now = time.time()
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO buckets(owner,name,visibility,description,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (owner, name, visibility, description, actor, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise FileExistsError(f"Commons bucket already exists: {owner}/{name}") from exc
        return self.get_bucket(owner, name, include_private=True)

    def get_bucket(self, owner: str, name: str, *, include_private: bool = False) -> dict[str, Any]:
        owner = _segment(owner, "owner")
        name = _segment(name, "bucket name")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT b.*, COUNT(r.revision) AS revision_count FROM buckets b "
                "LEFT JOIN revisions r ON r.owner=b.owner AND r.name=b.name "
                "WHERE b.owner=? AND b.name=? GROUP BY b.owner,b.name",
                (owner, name),
            ).fetchone()
        if row is None or (row["visibility"] == "private" and not include_private):
            raise FileNotFoundError(f"Commons bucket not found: {owner}/{name}")
        return self._bucket_row(row)

    def list_buckets(self, *, include_private: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        where = "" if include_private else "WHERE b.visibility='public'"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT b.*, COUNT(r.revision) AS revision_count FROM buckets b "
                "LEFT JOIN revisions r ON r.owner=b.owner AND r.name=b.name "
                f"{where} GROUP BY b.owner,b.name ORDER BY b.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._bucket_row(row) for row in rows]

    @staticmethod
    def _bucket_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "bucket_id": f"{row['owner']}/{row['name']}",
            "owner": row["owner"],
            "name": row["name"],
            "visibility": row["visibility"],
            "description": row["description"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "revision_count": int(row["revision_count"] or 0),
        }

    def put_blob(self, payload: bytes, *, expected_digest: str, actor: str) -> dict[str, Any]:
        if not payload or len(payload) > self.maximum_blob_bytes:
            raise ValueError("Commons blob size is outside node policy")
        actual = sha256_bytes(payload)
        if not _DIGEST.fullmatch(expected_digest) or actual != expected_digest:
            raise ValueError("Commons blob digest does not match request path")
        target = self.blob_root / expected_digest[7:]
        with self._lock:
            if target.exists():
                if target.is_symlink() or not target.is_file() or sha256_bytes(target.read_bytes()) != expected_digest:
                    raise ValueError("existing Commons blob violates immutable identity")
            else:
                descriptor, temporary = tempfile.mkstemp(prefix=".commons-blob-", suffix=".tmp", dir=self.blob_root)
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR IGNORE INTO blobs(digest,size,created_by,created_at) VALUES(?,?,?,?)",
                    (expected_digest, len(payload), actor, time.time()),
                )
        return {"digest": expected_digest, "size": len(payload), "status": "stored"}

    def get_blob(self, digest: str) -> bytes:
        if not _DIGEST.fullmatch(str(digest)):
            raise ValueError("invalid Commons blob digest")
        target = self.blob_root / digest[7:]
        if target.is_symlink() or not target.is_file():
            raise FileNotFoundError(digest)
        if target.stat().st_size > self.maximum_blob_bytes:
            raise ValueError("Commons blob exceeds node policy")
        payload = target.read_bytes()
        if sha256_bytes(payload) != digest:
            raise ValueError("Commons blob custody verification failed")
        return payload

    def has_blob(self, digest: str) -> bool:
        if not _DIGEST.fullmatch(str(digest)):
            return False
        target = self.blob_root / digest[7:]
        return target.is_file() and not target.is_symlink()

    def commit_revision(
        self, *, owner: str, name: str, revision: str, manifest: Mapping[str, Any],
        actor: str, replace: bool = False,
    ) -> dict[str, Any]:
        owner = _segment(owner, "owner")
        name = _segment(name, "bucket name")
        revision = _segment(revision, "revision")
        bucket = self.get_bucket(owner, name, include_private=True)
        files = manifest.get("files") or []
        if not isinstance(files, Sequence) or isinstance(files, (str, bytes)) or not files:
            raise ValueError("Commons revision manifest requires files")
        normalized_files = []
        missing = []
        seen_paths: set[str] = set()
        for item in files:
            if not isinstance(item, Mapping):
                raise ValueError("invalid Commons manifest file")
            path = str(item.get("path") or "").replace("\\", "/").strip("/")
            digest = str(item.get("digest") or "")
            size = int(item.get("size") or 0)
            if not path or ".." in path.split("/") or path in seen_paths or not _DIGEST.fullmatch(digest) or size <= 0:
                raise ValueError("invalid or duplicate Commons manifest file binding")
            seen_paths.add(path)
            if not self.has_blob(digest):
                missing.append(digest)
            normalized_files.append({"path": path, "digest": digest, "size": size})
        if missing:
            raise FileNotFoundError("missing Commons blobs: " + ",".join(sorted(set(missing))))
        authority = str(manifest.get("authority") or "remote_hypothesis")
        maximum_authority = str(manifest.get("maximum_authority") or "verify_only")
        if authority != "remote_hypothesis" or maximum_authority != "verify_only":
            raise PermissionError("remote Commons revisions may carry verify-only hypothesis authority")
        document = {
            "beast_object_type": "commons_bucket_revision_manifest",
            "schema_version": "1.0",
            "bucket_id": bucket["bucket_id"],
            "revision": revision,
            "authority": authority,
            "maximum_authority": maximum_authority,
            "files": normalized_files,
            "metadata": dict(manifest.get("metadata") or {}),
            "proof": dict(manifest.get("proof") or {}),
            "committed_by": actor,
        }
        digest = sha256_bytes(canonical_json(document))
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        now = time.time()
        with self._lock, self._connect() as connection:
            try:
                if replace:
                    connection.execute(
                        "INSERT INTO revisions(owner,name,revision,manifest_digest,manifest_json,committed_by,committed_at) VALUES(?,?,?,?,?,?,?) "
                        "ON CONFLICT(owner,name,revision) DO UPDATE SET manifest_digest=excluded.manifest_digest, manifest_json=excluded.manifest_json, committed_by=excluded.committed_by, committed_at=excluded.committed_at",
                        (owner, name, revision, digest, encoded, actor, now),
                    )
                else:
                    connection.execute(
                        "INSERT INTO revisions(owner,name,revision,manifest_digest,manifest_json,committed_by,committed_at) VALUES(?,?,?,?,?,?,?)",
                        (owner, name, revision, digest, encoded, actor, now),
                    )
                connection.execute("UPDATE buckets SET updated_at=? WHERE owner=? AND name=?", (now, owner, name))
            except sqlite3.IntegrityError as exc:
                raise FileExistsError(f"Commons revision already exists: {owner}/{name}@{revision}") from exc
        return {"manifest": document, "manifest_digest": digest, "committed_at": now}

    def get_revision(self, owner: str, name: str, revision: str, *, include_private: bool = False) -> dict[str, Any]:
        bucket = self.get_bucket(owner, name, include_private=include_private)
        revision = _segment(revision, "revision")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM revisions WHERE owner=? AND name=? AND revision=?",
                (bucket["owner"], bucket["name"], revision),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Commons revision not found: {owner}/{name}@{revision}")
        document = json.loads(row["manifest_json"])
        if sha256_bytes(canonical_json(document)) != row["manifest_digest"]:
            raise ValueError("Commons revision metadata custody verification failed")
        return {
            "manifest": document,
            "manifest_digest": row["manifest_digest"],
            "committed_by": row["committed_by"],
            "committed_at": row["committed_at"],
        }

    def list_revisions(self, owner: str, name: str, *, include_private: bool = False) -> list[dict[str, Any]]:
        bucket = self.get_bucket(owner, name, include_private=include_private)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT revision,manifest_digest,committed_by,committed_at FROM revisions "
                "WHERE owner=? AND name=? ORDER BY committed_at DESC",
                (bucket["owner"], bucket["name"]),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            buckets = int(connection.execute("SELECT COUNT(*) FROM buckets").fetchone()[0])
            revisions = int(connection.execute("SELECT COUNT(*) FROM revisions").fetchone()[0])
            blobs = connection.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM blobs").fetchone()
        return {
            "buckets": buckets,
            "revisions": revisions,
            "blobs": int(blobs[0]),
            "bytes": int(blobs[1]),
            "maximum_blob_bytes": self.maximum_blob_bytes,
        }
