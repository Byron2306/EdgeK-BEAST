"""Exact, signed, atomically consumed one-use authorization capabilities."""
from __future__ import annotations

import base64
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Mapping


@dataclass(frozen=True)
class OneUseCapability:
    capability_id: str
    request_digest: str
    authority: str
    expires_at: float
    nonce: str
    signature: str
    audience: str = ""
    policy_generation: str = ""
    appraisal_ref: str = ""
    key_id: str = ""

    def body(self) -> bytes:
        return json.dumps(
            {
                "appraisal_ref": self.appraisal_ref,
                "audience": self.audience,
                "authority": self.authority,
                "capability_id": self.capability_id,
                "expires_at": self.expires_at,
                "key_id": self.key_id,
                "nonce": self.nonce,
                "policy_generation": self.policy_generation,
                "request_digest": self.request_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class OneUseCapabilityLedger:
    """Consume capabilities once, using a SQLite uniqueness transaction.

    Signature verification is mandatory by default. Isolated tests must opt
    out explicitly with ``require_verifier=False``.
    """

    def __init__(self, verifier=None, path: str | Path | None = None, *, require_verifier: bool = True):
        if require_verifier and verifier is None:
            raise RuntimeError("production capability verifier is required")
        self.verifier = verifier
        self.require_verifier = require_verifier
        self.path = Path(path) if path else None
        self._used: set[str] = set()
        self._revoked: set[str] = set()
        self._lock = Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        if self.path is None:
            raise RuntimeError("capability ledger has no durable path")
        connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize_database(self) -> None:
        connection = None
        try:
            connection = self._connect()
            connection.execute(
                "CREATE TABLE IF NOT EXISTS consumed_capabilities ("
                "capability_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
                "authority TEXT NOT NULL, issuer_key_id TEXT NOT NULL, consumed_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS revoked_capabilities ("
                "capability_id TEXT PRIMARY KEY, authority TEXT NOT NULL, "
                "issuer_key_id TEXT NOT NULL, revoked_at REAL NOT NULL, reason TEXT NOT NULL)"
            )
        except sqlite3.DatabaseError as exc:
            raise RuntimeError("capability ledger is not a valid SQLite database") from exc
        finally:
            if connection is not None:
                connection.close()

    def _select_verifier(self, authority: str):
        if isinstance(self.verifier, Mapping):
            return self.verifier.get(authority)
        return self.verifier

    @staticmethod
    def _parse(capability: Mapping[str, Any]) -> OneUseCapability:
        try:
            return OneUseCapability(
                capability_id=str(capability.get("capability_id") or ""),
                request_digest=str(capability.get("request_digest") or ""),
                authority=str(capability.get("authority") or ""),
                expires_at=float(capability.get("expires_at") or 0),
                nonce=str(capability.get("nonce") or ""),
                signature=str(capability.get("signature") or ""),
                audience=str(capability.get("audience") or ""),
                policy_generation=str(capability.get("policy_generation") or ""),
                appraisal_ref=str(capability.get("appraisal_ref") or ""),
                key_id=str(capability.get("key_id") or (capability.get("verification_material") or {}).get("key_id") or ""),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError("capability structure is invalid") from exc

    def consume(self, capability: Mapping[str, Any], *, request_digest: str,
                authority: str, now: float | None = None,
                expected_audience: str | None = None,
                expected_policy_generation: str | None = None,
                expected_appraisal_ref: str | None = None) -> OneUseCapability:
        now = time.time() if now is None else now
        item = self._parse(capability)
        if (
            not item.capability_id or not item.nonce or not item.signature
            or item.request_digest != request_digest or item.authority != authority
            or item.expires_at <= now
        ):
            raise PermissionError("capability does not exactly authorize this request")
        if self.require_verifier and (
            not item.key_id or not item.audience or not item.policy_generation or not item.appraisal_ref
        ):
            raise PermissionError("protected capability authority metadata is incomplete")
        if expected_audience is not None and item.audience != expected_audience:
            raise PermissionError("capability audience mismatch")
        if expected_policy_generation is not None and item.policy_generation != expected_policy_generation:
            raise PermissionError("capability policy generation mismatch")
        if expected_appraisal_ref is not None and item.appraisal_ref != expected_appraisal_ref:
            raise PermissionError("capability appraisal mismatch")

        verifier = self._select_verifier(authority)
        if verifier is None and self.require_verifier:
            raise RuntimeError("production capability verifier is required")
        if verifier is not None:
            try:
                verifier.verify(base64.b64decode(item.signature, validate=True), item.body())
            except Exception as exc:
                raise PermissionError("capability signature invalid") from exc

        if self.path is None:
            with self._lock:
                if item.capability_id in self._revoked:
                    raise PermissionError("capability is revoked")
                if item.capability_id in self._used:
                    raise PermissionError("capability already consumed")
                self._used.add(item.capability_id)
            return item

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            revoked = connection.execute(
                "SELECT 1 FROM revoked_capabilities WHERE capability_id = ?", (item.capability_id,)
            ).fetchone()
            if revoked:
                raise PermissionError("capability is revoked")
            try:
                connection.execute(
                    "INSERT INTO consumed_capabilities "
                    "(capability_id, request_digest, authority, issuer_key_id, consumed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (item.capability_id, item.request_digest, item.authority, item.key_id, now),
                )
            except sqlite3.IntegrityError as exc:
                raise PermissionError("capability already consumed") from exc
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return item

    def revoke(self, capability_id: str, *, authority: str, key_id: str, reason: str = "policy") -> None:
        if not capability_id or not authority or not key_id:
            raise ValueError("capability_id, authority, and key_id are required")
        if self.path is None:
            with self._lock:
                self._revoked.add(capability_id)
            return
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO revoked_capabilities "
                "(capability_id, authority, issuer_key_id, revoked_at, reason) VALUES (?, ?, ?, ?, ?)",
                (capability_id, authority, key_id, time.time(), reason),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def consumed(self, capability_id: str) -> bool:
        if self.path is None:
            with self._lock:
                return capability_id in self._used
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM consumed_capabilities WHERE capability_id = ?", (capability_id,)
            ).fetchone() is not None
        finally:
            connection.close()
