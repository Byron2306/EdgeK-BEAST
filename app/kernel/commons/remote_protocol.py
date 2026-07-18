"""Signed, replay-resistant HTTP protocol for remote Commons nodes.

The protocol deliberately does not depend on the older ARDA fabric runtime.  It
uses the same hard requirements (identity, nonce, audience, freshness, replay
state and cryptographic binding) without inheriting its simulated handshake.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Iterable, Mapping

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


PROTOCOL_VERSION = "beast-commons-http-signature-v1"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_request(
    *, method: str, target: str, body_digest: str, timestamp: int, nonce: str,
    counter: int, node_id: str, key_id: str,
) -> bytes:
    fields = (
        PROTOCOL_VERSION,
        method.upper(),
        target,
        body_digest,
        str(timestamp),
        nonce,
        str(counter),
        node_id,
        key_id,
    )
    return "\n".join(fields).encode("utf-8")


@dataclass(frozen=True)
class TrustedClient:
    node_id: str
    key_id: str
    public_key: Ed25519PublicKey
    scopes: frozenset[str]

    def permits(self, required: str) -> bool:
        return required in self.scopes or "commons:admin" in self.scopes


class CommonsClientTrustStore:
    """Explicit client key and scope allowlist loaded from YAML or JSON."""

    def __init__(self, clients: Iterable[TrustedClient]):
        self._clients = {(item.node_id, item.key_id): item for item in clients}

    @classmethod
    def from_file(cls, path: str | Path) -> "CommonsClientTrustStore":
        source = Path(path).expanduser().resolve()
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        records = payload.get("clients") or []
        if isinstance(records, Mapping):
            records = [dict(value or {}, node_id=node_id) for node_id, value in records.items()]
        if not isinstance(records, list):
            raise ValueError("Commons client trust store must contain a clients list or mapping")
        clients: list[TrustedClient] = []
        for record in records:
            if not isinstance(record, Mapping):
                raise ValueError("invalid Commons trusted client record")
            node_id = str(record.get("node_id") or "").strip()
            key_id = str(record.get("key_id") or "").strip()
            scopes = frozenset(str(item) for item in (record.get("scopes") or ()))
            if not node_id or not key_id or not scopes:
                raise ValueError("Commons trusted client requires node_id, key_id and scopes")
            if record.get("public_key_pem_b64"):
                pem = base64.b64decode(str(record["public_key_pem_b64"]), validate=True)
            elif record.get("public_key_path"):
                key_path = (source.parent / str(record["public_key_path"])).resolve()
                if key_path != source.parent and source.parent not in key_path.parents:
                    raise ValueError("Commons client key path escapes trust-store directory")
                pem = key_path.read_bytes()
            else:
                raise ValueError(f"public key missing for Commons client {node_id}")
            key = serialization.load_pem_public_key(pem)
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError(f"Commons client {node_id} key must be Ed25519")
            clients.append(TrustedClient(node_id, key_id, key, scopes))
        return cls(clients)

    def get(self, node_id: str, key_id: str) -> TrustedClient | None:
        return self._clients.get((node_id, key_id))

    def snapshot(self) -> dict:
        return {
            "client_count": len(self._clients),
            "clients": [
                {"node_id": item.node_id, "key_id": item.key_id, "scopes": sorted(item.scopes)}
                for item in sorted(self._clients.values(), key=lambda value: (value.node_id, value.key_id))
            ],
        }


class SqliteReplayLedger:
    """Durable nonce/counter consumption with a bounded reordering window."""

    def __init__(self, path: str | Path, *, counter_reorder_window: int = 30_000_000_000):
        self.path = Path(path)
        self.counter_reorder_window = max(0, int(counter_reorder_window))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS request_nonces (
                    node_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    counter INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY (node_id, key_id, nonce)
                );
                CREATE TABLE IF NOT EXISTS request_counters (
                    node_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    counter INTEGER NOT NULL,
                    PRIMARY KEY (node_id, key_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS request_counter_once_idx
                    ON request_nonces(node_id,key_id,counter);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def consume(self, *, node_id: str, key_id: str, nonce: str, counter: int, expires_at: int) -> bool:
        now = int(time.time())
        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM request_nonces WHERE expires_at <= ?", (now,))
                row = connection.execute(
                    "SELECT counter FROM request_counters WHERE node_id=? AND key_id=?",
                    (node_id, key_id),
                ).fetchone()
                previous = int(row[0]) if row is not None else -1
                if row is not None and counter <= previous - self.counter_reorder_window:
                    connection.rollback()
                    return False
                connection.execute(
                    "INSERT INTO request_nonces(node_id,key_id,nonce,counter,expires_at) VALUES(?,?,?,?,?)",
                    (node_id, key_id, nonce, counter, expires_at),
                )
                if counter > previous:
                    connection.execute(
                        "INSERT INTO request_counters(node_id,key_id,counter) VALUES(?,?,?) "
                        "ON CONFLICT(node_id,key_id) DO UPDATE SET counter=excluded.counter",
                        (node_id, key_id, counter),
                    )
                connection.commit()
                return True
            except sqlite3.IntegrityError:
                connection.rollback()
                return False


@dataclass(frozen=True)
class AuthenticatedRequest:
    node_id: str
    key_id: str
    scopes: frozenset[str]
    counter: int


class CommonsRequestVerifier:
    def __init__(self, trust_store: CommonsClientTrustStore, replay: SqliteReplayLedger, *, maximum_skew_seconds: int = 90):
        self.trust_store = trust_store
        self.replay = replay
        self.maximum_skew_seconds = max(5, int(maximum_skew_seconds))

    def verify(self, *, method: str, target: str, body: bytes, headers: Mapping[str, str], required_scope: str) -> AuthenticatedRequest:
        lowered = {str(key).lower(): str(value) for key, value in headers.items()}
        node_id = lowered.get("x-commons-node-id", "")
        key_id = lowered.get("x-commons-key-id", "")
        nonce = lowered.get("x-commons-nonce", "")
        signature = lowered.get("x-commons-signature", "")
        try:
            timestamp = int(lowered.get("x-commons-timestamp", ""))
            counter = int(lowered.get("x-commons-counter", ""))
        except ValueError as exc:
            raise PermissionError("invalid Commons signature timestamp or counter") from exc
        if not node_id or not key_id or len(nonce) < 24 or not signature or counter < 0:
            raise PermissionError("incomplete Commons request signature")
        now = int(time.time())
        if abs(now - timestamp) > self.maximum_skew_seconds:
            raise PermissionError("stale Commons request signature")
        trusted = self.trust_store.get(node_id, key_id)
        if trusted is None or not trusted.permits(required_scope):
            raise PermissionError("Commons client key or scope is not trusted")
        signed = canonical_request(
            method=method, target=target, body_digest=sha256_bytes(body), timestamp=timestamp,
            nonce=nonce, counter=counter, node_id=node_id, key_id=key_id,
        )
        try:
            trusted.public_key.verify(base64.b64decode(signature, validate=True), signed)
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise PermissionError("Commons request signature verification failed") from exc
        if not self.replay.consume(
            node_id=node_id, key_id=key_id, nonce=nonce, counter=counter,
            expires_at=timestamp + self.maximum_skew_seconds + 1,
        ):
            raise PermissionError("Commons request replay refused")
        return AuthenticatedRequest(node_id, key_id, trusted.scopes, counter)


class CommonsRequestSigner:
    """Thread-safe signer with a process-monotonic nanosecond counter."""

    def __init__(self, private_key: Ed25519PrivateKey, *, node_id: str, key_id: str):
        if not node_id or not key_id:
            raise ValueError("Commons request signer requires node_id and key_id")
        self.private_key = private_key
        self.node_id = node_id
        self.key_id = key_id
        self._lock = threading.Lock()
        self._last_counter = 0

    @classmethod
    def from_pem_file(cls, path: str | Path, *, node_id: str, key_id: str) -> "CommonsRequestSigner":
        key = serialization.load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("Commons request signing key must be Ed25519")
        return cls(key, node_id=node_id, key_id=key_id)

    def headers(self, *, method: str, target: str, body: bytes) -> dict[str, str]:
        timestamp = int(time.time())
        nonce = base64.urlsafe_b64encode(hashlib.sha256(f"{time.time_ns()}:{self.node_id}".encode()).digest()).decode().rstrip("=")
        with self._lock:
            counter = max(time.time_ns(), self._last_counter + 1)
            self._last_counter = counter
        signed = canonical_request(
            method=method, target=target, body_digest=sha256_bytes(body), timestamp=timestamp,
            nonce=nonce, counter=counter, node_id=self.node_id, key_id=self.key_id,
        )
        return {
            "X-Commons-Protocol": PROTOCOL_VERSION,
            "X-Commons-Node-ID": self.node_id,
            "X-Commons-Key-ID": self.key_id,
            "X-Commons-Timestamp": str(timestamp),
            "X-Commons-Nonce": nonce,
            "X-Commons-Counter": str(counter),
            "X-Commons-Signature": base64.b64encode(self.private_key.sign(signed)).decode("ascii"),
        }


def canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
