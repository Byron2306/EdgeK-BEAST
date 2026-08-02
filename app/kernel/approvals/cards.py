from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .digests import canonical_json, canonicalize, semantic_payload, sha256_digest, verify_digest
from .envelope import RichApprovalEnvelopeBuilder

CARD_VERSION = "4.11"
CARD_OBJECT_TYPE = "beast_durable_approval_card"
CARD_EVENT_OBJECT_TYPE = "beast_durable_approval_card_event"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@dataclass(frozen=True)
class DurableApprovalCard:
    card_id: str
    approval_id: str
    run_id: str
    step_id: str
    state: str
    envelope: Mapping[str, Any]
    request_digest: str
    envelope_digest: str
    classification_digest: str
    argument_digest: str
    expires_at: str
    redaction_status: str
    decision: Mapping[str, Any]
    decision_history: tuple[Mapping[str, Any], ...]
    recovery: Mapping[str, Any]
    created_at: str
    updated_at: str
    authority: str = "operator_review_record_only"
    capability_issued: bool = False
    execution_authorized: bool = False
    version: str = CARD_VERSION
    beast_object_type: str = CARD_OBJECT_TYPE
    card_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"card_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["card_digest"] = self.card_digest or sha256_digest(self.semantic_dict())
        return payload


class DurableApprovalCardStore:
    """Durable, restart-safe operator approval cards with append-only history."""

    def __init__(self, root_path: str | Path):
        self.root = Path(root_path).expanduser().resolve()
        self.state_dir = self.root / ".beast" / "approvals"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "approval_cards.sqlite3"
        self.envelopes = RichApprovalEnvelopeBuilder()
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
            CREATE TABLE IF NOT EXISTS approval_cards (
                card_id TEXT PRIMARY KEY,
                approval_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                state TEXT NOT NULL,
                card_json TEXT NOT NULL,
                card_digest TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_approval_cards_run ON approval_cards(run_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_approval_cards_state ON approval_cards(state, updated_at DESC);
            CREATE TABLE IF NOT EXISTS approval_card_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id TEXT NOT NULL,
                approval_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_json TEXT NOT NULL,
                previous_event_digest TEXT NOT NULL,
                event_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_approval_card_events_card ON approval_card_events(card_id, sequence);
            """)

    @staticmethod
    def _event_digest(event: Mapping[str, Any]) -> str:
        return sha256_digest({k: v for k, v in event.items() if k != "event_digest"})

    def _append_event(self, db: sqlite3.Connection, card: Mapping[str, Any], event_type: str, previous: str) -> dict[str, Any]:
        event = {
            "version": CARD_VERSION,
            "beast_object_type": CARD_EVENT_OBJECT_TYPE,
            "card_id": card["card_id"],
            "approval_id": card["approval_id"],
            "event_type": event_type,
            "card_digest": card["card_digest"],
            "previous_event_digest": previous,
            "created_at": _utcnow(),
        }
        event["event_digest"] = self._event_digest(event)
        db.execute(
            "INSERT INTO approval_card_events(card_id,approval_id,event_type,event_json,previous_event_digest,event_digest,created_at) VALUES(?,?,?,?,?,?,?)",
            (event["card_id"], event["approval_id"], event_type, canonical_json(event), previous, event["event_digest"], event["created_at"]),
        )
        return event

    def create(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        if not self.envelopes.verify(envelope):
            raise ValueError("approval envelope is invalid or tampered")
        request = envelope["approval_request"]
        now = _utcnow()
        card = DurableApprovalCard(
            card_id=f"card_{request['approval_id']}",
            approval_id=str(request["approval_id"]), run_id=str(request["run_id"]), step_id=str(request["step_id"]),
            state="PENDING", envelope=canonicalize(envelope), request_digest=str(request["request_digest"]),
            envelope_digest=str(envelope["envelope_digest"]), classification_digest=str(envelope["classification"]["classification_digest"]),
            argument_digest=str(envelope["argument_digest"]), expires_at=str(request["expires_at"]),
            redaction_status="SAFE_VIEW_ONLY", decision={}, decision_history=tuple(),
            recovery={"restart_safe": True, "reconstruction_required": False, "last_event_digest": ""},
            created_at=now, updated_at=now,
        ).to_dict()
        if not self.verify(card):
            raise RuntimeError("approval card digest generation failed")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM approval_cards WHERE approval_id=?", (card["approval_id"],)).fetchone():
                    raise ValueError("approval card already exists")
                event = self._append_event(db, card, "approval.card.created", "")
                card["recovery"]["last_event_digest"] = event["event_digest"]
                card["card_digest"] = sha256_digest(semantic_payload(card, exclude={"card_digest"}))
                db.execute("INSERT INTO approval_cards VALUES(?,?,?,?,?,?,?,?,?)", (
                    card["card_id"], card["approval_id"], card["run_id"], card["step_id"], card["state"],
                    canonical_json(card), card["card_digest"], card["expires_at"], card["updated_at"],
                ))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.get(card["approval_id"])

    def decide(self, approval_id: str, decision: Mapping[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT * FROM approval_cards WHERE approval_id=?", (approval_id,)).fetchone()
                if not row:
                    raise KeyError(f"unknown approval card: {approval_id}")
                card = json.loads(row["card_json"])
                if card["state"] not in {"PENDING", "REQUESTED"}:
                    raise ValueError("approval card is not awaiting a decision")
                if _parse_time(card["expires_at"]) <= datetime.now(timezone.utc):
                    raise ValueError("approval card has expired")
                supplied_request = str(decision.get("request_digest") or "")
                if supplied_request != card["request_digest"]:
                    raise ValueError("decision request digest does not match card")
                value = str(decision.get("decision") or "").upper()
                states = {"APPROVE": "APPROVED", "EDIT_AND_APPROVE": "EDITED_AND_APPROVED", "REJECT": "REJECTED", "REQUEST_REPLAN": "REPLAN_REQUESTED", "PERMANENTLY_DENY": "PERMANENTLY_DENIED"}
                if value not in states:
                    raise ValueError("unsupported approval decision")
                history = list(card.get("decision_history") or [])
                history.append(canonicalize(decision))
                card.update(state=states[value], decision=canonicalize(decision), decision_history=history, updated_at=_utcnow())
                previous = str((card.get("recovery") or {}).get("last_event_digest") or "")
                card["card_digest"] = sha256_digest(semantic_payload(card, exclude={"card_digest"}))
                event = self._append_event(db, card, f"approval.card.{states[value].lower()}", previous)
                card["recovery"]["last_event_digest"] = event["event_digest"]
                card["card_digest"] = sha256_digest(semantic_payload(card, exclude={"card_digest"}))
                db.execute("UPDATE approval_cards SET state=?,card_json=?,card_digest=?,updated_at=? WHERE approval_id=?", (card["state"], canonical_json(card), card["card_digest"], card["updated_at"], approval_id))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.get(approval_id)

    def get(self, approval_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT card_json FROM approval_cards WHERE approval_id=?", (approval_id,)).fetchone()
        if not row:
            raise KeyError(f"unknown approval card: {approval_id}")
        card = json.loads(row[0])
        if not self.verify(card):
            raise ValueError("durable approval card is invalid or tampered")
        return card

    def list(self, *, run_id: str | None = None, state: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses, values = [], []
        if run_id: clauses.append("run_id=?"); values.append(run_id)
        if state: clauses.append("state=?"); values.append(str(state).upper())
        sql = "SELECT card_json FROM approval_cards" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY updated_at DESC LIMIT ?"
        values.append(max(1, min(int(limit), 500)))
        with self._connect() as db:
            return [json.loads(row[0]) for row in db.execute(sql, values).fetchall()]

    def events(self, approval_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT event_json FROM approval_card_events WHERE approval_id=? ORDER BY sequence", (approval_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def verify_chain(self, approval_id: str) -> dict[str, Any]:
        events, previous = self.events(approval_id), ""
        for index, event in enumerate(events):
            if event.get("previous_event_digest") != previous or self._event_digest(event) != event.get("event_digest"):
                return {"ok": False, "approval_id": approval_id, "failed_index": index}
            previous = str(event["event_digest"])
        return {"ok": bool(events), "approval_id": approval_id, "event_count": len(events), "head_digest": previous}

    def recover(self) -> dict[str, Any]:
        expired, valid, invalid = [], [], []
        for card in self.list(limit=500):
            try:
                if not self.verify(card):
                    invalid.append(card.get("approval_id")); continue
                if card["state"] in {"PENDING", "REQUESTED"} and _parse_time(card["expires_at"]) <= datetime.now(timezone.utc):
                    expired.append(card["approval_id"])
                else:
                    valid.append(card["approval_id"])
            except Exception:
                invalid.append(card.get("approval_id"))
        return {"ok": not invalid, "valid": valid, "expired": expired, "invalid": invalid, "reconstruction_required": False}

    def verify(self, card: Mapping[str, Any]) -> bool:
        if card.get("beast_object_type") != CARD_OBJECT_TYPE or str(card.get("version")) != CARD_VERSION:
            return False
        if card.get("authority") != "operator_review_record_only" or card.get("capability_issued") is not False or card.get("execution_authorized") is not False:
            return False
        envelope = card.get("envelope") if isinstance(card.get("envelope"), Mapping) else {}
        if not self.envelopes.verify(envelope):
            return False
        request = envelope.get("approval_request") or {}
        checks = {
            "approval_id": request.get("approval_id"), "run_id": request.get("run_id"), "step_id": request.get("step_id"),
            "request_digest": request.get("request_digest"), "envelope_digest": envelope.get("envelope_digest"),
            "classification_digest": (envelope.get("classification") or {}).get("classification_digest"), "argument_digest": envelope.get("argument_digest"),
            "expires_at": request.get("expires_at"),
        }
        if any(str(card.get(k)) != str(v) for k, v in checks.items()):
            return False
        return verify_digest(semantic_payload(card, exclude={"card_digest"}), str(card.get("card_digest") or ""))
