from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .digests import canonical_json, canonicalize, semantic_payload, sha256_digest, verify_digest

REVOCATION_VERSION = "4.12"
REVOCATION_OBJECT_TYPE = "beast_authority_revocation"
POLICY_GENERATION_OBJECT_TYPE = "beast_policy_generation_record"
REVOCATION_CHECK_OBJECT_TYPE = "beast_revocation_check_receipt"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RevocationTarget(str, Enum):
    APPROVAL = "APPROVAL"
    SCOPE_GRANT = "SCOPE_GRANT"
    CAPABILITY = "CAPABILITY"
    APPROVAL_CARD = "APPROVAL_CARD"
    POLICY_GENERATION = "POLICY_GENERATION"
    RUN = "RUN"
    TOOL = "TOOL"


@dataclass(frozen=True)
class AuthorityRevocation:
    revocation_id: str
    target_type: str
    target_id: str
    reason: str
    operator_id: str
    policy_generation: str
    created_at: str
    effective_at: str
    metadata: Mapping[str, Any]
    authority: str = "revocation_only"
    grants_authority: bool = False
    reversible: bool = False
    version: str = REVOCATION_VERSION
    beast_object_type: str = REVOCATION_OBJECT_TYPE
    revocation_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["revocation_digest"] = self.revocation_digest or sha256_digest(
            semantic_payload(payload, exclude={"revocation_digest"})
        )
        return payload


@dataclass(frozen=True)
class PolicyGenerationRecord:
    generation_id: str
    parent_generation: str
    policy_digest: str
    status: str
    operator_id: str
    reason: str
    created_at: str
    activated_at: str
    superseded_at: str
    authority: str = "policy_administration_record_only"
    retroactive_grant_allowed: bool = False
    version: str = REVOCATION_VERSION
    beast_object_type: str = POLICY_GENERATION_OBJECT_TYPE
    generation_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["generation_digest"] = self.generation_digest or sha256_digest(
            semantic_payload(payload, exclude={"generation_digest"})
        )
        return payload


class RevocationPolicyStore:
    """Durable deny-only authority revocation and policy generation administration."""

    def __init__(self, root_path: str | Path):
        self.root = Path(root_path).expanduser().resolve()
        self.state_dir = self.root / ".beast" / "approvals"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "revocation_policy.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS authority_revocations (
                revocation_id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                revocation_json TEXT NOT NULL,
                revocation_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                UNIQUE(target_type, target_id)
            );
            CREATE INDEX IF NOT EXISTS idx_revocations_target
                ON authority_revocations(target_type, target_id);
            CREATE TABLE IF NOT EXISTS policy_generations (
                generation_id TEXT PRIMARY KEY,
                parent_generation TEXT NOT NULL,
                policy_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                generation_json TEXT NOT NULL,
                generation_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_policy_status
                ON policy_generations(status, created_at DESC);
            CREATE TABLE IF NOT EXISTS administration_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                event_json TEXT NOT NULL,
                previous_event_digest TEXT NOT NULL,
                event_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            """)

    def _head(self, db: sqlite3.Connection) -> str:
        row = db.execute("SELECT event_digest FROM administration_events ORDER BY sequence DESC LIMIT 1").fetchone()
        return str(row[0]) if row else ""

    def _event(self, db: sqlite3.Connection, event_type: str, subject_id: str, payload_digest: str) -> dict[str, Any]:
        event = {
            "version": REVOCATION_VERSION,
            "beast_object_type": "beast_policy_administration_event",
            "event_type": event_type,
            "subject_id": subject_id,
            "payload_digest": payload_digest,
            "previous_event_digest": self._head(db),
            "created_at": _utcnow(),
        }
        event["event_digest"] = sha256_digest(event)
        db.execute(
            "INSERT INTO administration_events(event_type,subject_id,event_json,previous_event_digest,event_digest,created_at) VALUES(?,?,?,?,?,?)",
            (event_type, subject_id, canonical_json(event), event["previous_event_digest"], event["event_digest"], event["created_at"]),
        )
        return event

    def revoke(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        target_type = RevocationTarget(str(payload.get("target_type") or "").upper()).value
        target_id = str(payload.get("target_id") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        operator_id = str(payload.get("operator_id") or "").strip()
        policy_generation = str(payload.get("policy_generation") or "").strip()
        if not target_id or not reason or not operator_id or not policy_generation:
            raise ValueError("target_id, reason, operator_id, and policy_generation are required")
        now = _utcnow()
        record = AuthorityRevocation(
            revocation_id=str(payload.get("revocation_id") or f"revoke_{uuid4().hex}"),
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            operator_id=operator_id,
            policy_generation=policy_generation,
            created_at=now,
            effective_at=now,
            metadata=canonicalize(payload.get("metadata") or {}),
        ).to_dict()
        if not self.verify_revocation(record):
            raise RuntimeError("revocation digest generation failed")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT revocation_json FROM authority_revocations WHERE target_type=? AND target_id=?",
                    (target_type, target_id),
                ).fetchone()
                if existing:
                    db.execute("COMMIT")
                    return json.loads(existing[0])
                db.execute(
                    "INSERT INTO authority_revocations VALUES(?,?,?,?,?,?)",
                    (record["revocation_id"], target_type, target_id, canonical_json(record), record["revocation_digest"], record["created_at"]),
                )
                self._event(db, "authority.revoked", record["revocation_id"], record["revocation_digest"])
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return record

    def is_revoked(self, target_type: str, target_id: str) -> bool:
        target = RevocationTarget(str(target_type).upper()).value
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM authority_revocations WHERE target_type=? AND target_id=?",
                (target, str(target_id)),
            ).fetchone()
        return bool(row)

    def assert_active(self, artifact: Mapping[str, Any]) -> None:
        checks = [
            (RevocationTarget.APPROVAL.value, artifact.get("approval_id")),
            (RevocationTarget.SCOPE_GRANT.value, artifact.get("grant_id")),
            (RevocationTarget.CAPABILITY.value, artifact.get("capability_id")),
            (RevocationTarget.APPROVAL_CARD.value, artifact.get("card_id")),
            (RevocationTarget.RUN.value, artifact.get("run_id")),
            (RevocationTarget.TOOL.value, artifact.get("tool_id")),
            (RevocationTarget.POLICY_GENERATION.value, artifact.get("policy_generation")),
        ]
        for target_type, target_id in checks:
            if target_id and self.is_revoked(target_type, str(target_id)):
                raise ValueError(f"{target_type.lower()} is revoked: {target_id}")

    def check(self, artifact: Mapping[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        try:
            self.assert_active(artifact)
        except ValueError as exc:
            reasons.append(str(exc))
        receipt = {
            "version": REVOCATION_VERSION,
            "beast_object_type": REVOCATION_CHECK_OBJECT_TYPE,
            "active": not reasons,
            "reasons": reasons,
            "checked_at": _utcnow(),
            "authority": "revocation_status_only",
            "grants_authority": False,
        }
        receipt["receipt_digest"] = sha256_digest(receipt)
        return receipt

    def create_policy_generation(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        generation_id = str(payload.get("generation_id") or "").strip()
        operator_id = str(payload.get("operator_id") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        policy = payload.get("policy") if isinstance(payload.get("policy"), Mapping) else {}
        if not generation_id or not operator_id or not reason or not policy:
            raise ValueError("generation_id, operator_id, reason, and policy are required")
        parent = str(payload.get("parent_generation") or "").strip()
        now = _utcnow()
        record = PolicyGenerationRecord(
            generation_id=generation_id,
            parent_generation=parent,
            policy_digest=sha256_digest(policy),
            status="DRAFT",
            operator_id=operator_id,
            reason=reason,
            created_at=now,
            activated_at="",
            superseded_at="",
        ).to_dict()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM policy_generations WHERE generation_id=?", (generation_id,)).fetchone():
                    raise ValueError("policy generation already exists")
                if parent and not db.execute("SELECT 1 FROM policy_generations WHERE generation_id=?", (parent,)).fetchone():
                    raise ValueError("parent policy generation does not exist")
                db.execute(
                    "INSERT INTO policy_generations VALUES(?,?,?,?,?,?,?)",
                    (generation_id, parent, record["policy_digest"], record["status"], canonical_json(record), record["generation_digest"], record["created_at"]),
                )
                self._event(db, "policy.generation.created", generation_id, record["generation_digest"])
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return record

    def activate_policy_generation(self, generation_id: str, *, operator_id: str, reason: str) -> dict[str, Any]:
        if not operator_id or not reason:
            raise ValueError("operator_id and reason are required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT generation_json FROM policy_generations WHERE generation_id=?", (generation_id,)).fetchone()
                if not row:
                    raise KeyError(f"unknown policy generation: {generation_id}")
                record = json.loads(row[0])
                if record["status"] == "REVOKED":
                    raise ValueError("revoked policy generation cannot be activated")
                now = _utcnow()
                active_rows = db.execute("SELECT generation_id,generation_json FROM policy_generations WHERE status='ACTIVE'").fetchall()
                for active in active_rows:
                    old = json.loads(active["generation_json"])
                    old["status"] = "SUPERSEDED"; old["superseded_at"] = now
                    old["generation_digest"] = sha256_digest(semantic_payload(old, exclude={"generation_digest"}))
                    db.execute("UPDATE policy_generations SET status=?,generation_json=?,generation_digest=? WHERE generation_id=?", (old["status"], canonical_json(old), old["generation_digest"], old["generation_id"]))
                record["status"] = "ACTIVE"; record["activated_at"] = now
                record["generation_digest"] = sha256_digest(semantic_payload(record, exclude={"generation_digest"}))
                db.execute("UPDATE policy_generations SET status=?,generation_json=?,generation_digest=? WHERE generation_id=?", (record["status"], canonical_json(record), record["generation_digest"], generation_id))
                self._event(db, "policy.generation.activated", generation_id, record["generation_digest"])
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return record

    def current_policy_generation(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT generation_json FROM policy_generations WHERE status='ACTIVE' ORDER BY created_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def revoke_policy_generation(self, generation_id: str, *, operator_id: str, reason: str) -> dict[str, Any]:
        current = self.current_policy_generation()
        if current and current.get("generation_id") == generation_id:
            raise ValueError("active policy generation must be superseded before revocation")
        record = self.revoke({
            "target_type": RevocationTarget.POLICY_GENERATION.value,
            "target_id": generation_id,
            "reason": reason,
            "operator_id": operator_id,
            "policy_generation": current.get("generation_id") if current else "administrative-bootstrap",
        })
        with self._connect() as db:
            row = db.execute("SELECT generation_json FROM policy_generations WHERE generation_id=?", (generation_id,)).fetchone()
            if not row:
                raise KeyError(f"unknown policy generation: {generation_id}")
            generation = json.loads(row[0]); generation["status"] = "REVOKED"
            generation["generation_digest"] = sha256_digest(semantic_payload(generation, exclude={"generation_digest"}))
            db.execute("UPDATE policy_generations SET status=?,generation_json=?,generation_digest=? WHERE generation_id=?", (generation["status"], canonical_json(generation), generation["generation_digest"], generation_id))
        return {"revocation": record, "generation": generation}

    def list_revocations(self, *, target_type: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if target_type:
                rows = db.execute("SELECT revocation_json FROM authority_revocations WHERE target_type=? ORDER BY created_at DESC", (RevocationTarget(str(target_type).upper()).value,)).fetchall()
            else:
                rows = db.execute("SELECT revocation_json FROM authority_revocations ORDER BY created_at DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    @staticmethod
    def verify_revocation(record: Mapping[str, Any]) -> bool:
        if record.get("beast_object_type") != REVOCATION_OBJECT_TYPE or str(record.get("version")) != REVOCATION_VERSION:
            return False
        if record.get("authority") != "revocation_only" or record.get("grants_authority") is not False or record.get("reversible") is not False:
            return False
        try:
            RevocationTarget(str(record.get("target_type") or ""))
        except ValueError:
            return False
        return verify_digest(semantic_payload(record, exclude={"revocation_digest"}), str(record.get("revocation_digest") or ""))
