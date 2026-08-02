"""Append-only lifecycle ledger for immutable BEAST evidence crystals."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.kernel.evidence.evidence_digest import sha256_digest
from app.kernel.evidence.evidence_store import EvidenceStore


TERMINAL_EVIDENCE_STATES = {"revoked", "expired"}
VALID_EVENT_KINDS = {"created", "used", "superseded", "revoked", "expired", "verified", "metric"}


@dataclass(frozen=True)
class LedgerEvent:
    ledger_event_id: str
    evidence_id: str
    sequence: int
    kind: str
    created_at: float
    actor: str
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class EvidenceLedger:
    """Records lifecycle facts without mutating the underlying evidence object."""

    def __init__(self, workspace_root: str | Path):
        self.store = EvidenceStore(workspace_root)

    def _require_evidence(self, evidence_id: str) -> dict[str, Any]:
        evidence = self.store.get(evidence_id)
        if not evidence:
            raise KeyError(f"unknown evidence crystal: {evidence_id}")
        return evidence

    def append(self, evidence_id: str, kind: str, payload: dict[str, Any] | None = None, *, actor: str) -> dict[str, Any]:
        self._require_evidence(evidence_id)
        kind = str(kind).strip().lower()
        actor = str(actor).strip()
        if kind not in VALID_EVENT_KINDS:
            raise ValueError(f"unsupported evidence ledger event: {kind}")
        if not actor:
            raise ValueError("ledger actor is required")
        return self.store.append_ledger_event(evidence_id, kind, dict(payload or {}), actor=actor)

    def record_use(self, evidence_id: str, *, run_id: str, outcome: str = "adopted", actor: str = "beast-runtime", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not run_id:
            raise ValueError("run_id is required")
        status = self.state(evidence_id)
        if status["status"] in TERMINAL_EVIDENCE_STATES:
            raise PermissionError(f"evidence is {status['status']} and cannot be reused")
        return self.append(evidence_id, "used", {"run_id": run_id, "outcome": outcome, "metadata": metadata or {}}, actor=actor)

    def revoke(self, evidence_id: str, *, reason: str, actor: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("revocation reason is required")
        current = self.state(evidence_id)
        if current["status"] == "revoked":
            return current["latest_event"]
        return self.append(evidence_id, "revoked", {"reason": reason.strip()}, actor=actor)

    def supersede(self, evidence_id: str, *, successor_evidence_id: str, reason: str, actor: str) -> dict[str, Any]:
        if evidence_id == successor_evidence_id:
            raise ValueError("evidence cannot supersede itself")
        self._require_evidence(successor_evidence_id)
        if not reason.strip():
            raise ValueError("supersession reason is required")
        return self.append(evidence_id, "superseded", {"successor_evidence_id": successor_evidence_id, "reason": reason.strip()}, actor=actor)

    def record_metric(self, evidence_id: str, *, name: str, value: float, unit: str, actor: str = "beast-runtime", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not name.strip() or not unit.strip():
            raise ValueError("metric name and unit are required")
        return self.append(evidence_id, "metric", {"name": name.strip(), "value": float(value), "unit": unit.strip(), "metadata": metadata or {}}, actor=actor)

    def events(self, evidence_id: str, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        self._require_evidence(evidence_id)
        return self.store.ledger_events(evidence_id, after=after, limit=limit)

    def state(self, evidence_id: str) -> dict[str, Any]:
        evidence = self._require_evidence(evidence_id)
        events = self.events(evidence_id, limit=100000)
        status = "active"
        successor = None
        reason = ""
        uses = 0
        metrics: dict[str, dict[str, Any]] = {}
        for event in events:
            kind = event["kind"]
            payload = event.get("payload") or {}
            if kind == "used":
                uses += 1
            elif kind == "superseded":
                status = "superseded"
                successor = payload.get("successor_evidence_id")
                reason = str(payload.get("reason") or "")
            elif kind in {"revoked", "expired"}:
                status = kind
                reason = str(payload.get("reason") or "")
            elif kind == "metric":
                metrics[str(payload.get("name") or "unknown")] = payload
        return {
            "beast_object_type": "beast_evidence_ledger_state",
            "version": "3.2",
            "evidence_id": evidence_id,
            "evidence_digest": evidence.get("evidence_digest"),
            "status": status,
            "reason": reason,
            "successor_evidence_id": successor,
            "usage_count": uses,
            "metrics": metrics,
            "ledger_events": len(events),
            "ledger_head": events[-1]["event_hash"] if events else "",
            "latest_event": events[-1] if events else None,
        }

    def verify(self, evidence_id: str) -> dict[str, Any]:
        self._require_evidence(evidence_id)
        events = self.events(evidence_id, limit=100000)
        previous = ""
        expected_sequence = 1
        for event in events:
            body = {
                "ledger_event_id": event["ledger_event_id"],
                "evidence_id": evidence_id,
                "sequence": event["sequence"],
                "kind": event["kind"],
                "created_at": event["created_at"],
                "actor": event["actor"],
                "payload": event["payload"],
            }
            calculated = sha256_digest({"previous_hash": previous, "event": body})
            if event["sequence"] != expected_sequence or event["previous_hash"] != previous or event["event_hash"] != calculated:
                return {"ok": False, "evidence_id": evidence_id, "reason": "ledger_chain_mismatch", "sequence": event["sequence"]}
            previous = calculated
            expected_sequence += 1
        return {"ok": True, "evidence_id": evidence_id, "events": len(events), "head_hash": previous, "state": self.state(evidence_id)}
