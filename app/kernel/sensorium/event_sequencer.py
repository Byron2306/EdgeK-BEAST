"""Thread-safe bounded ordering for read-only Sensorium events."""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Deque, Dict, List, Optional

from app.kernel.sensorium.contracts import SensorEvent
from app.kernel.sensorium.privacy import SensorPrivacyGate


@dataclass(frozen=True)
class SequencedEvent:
    offset: int
    event: SensorEvent
    admitted_at: str

    def to_dict(self, *, include_payload: bool = True) -> Dict[str, Any]:
        payload = {
            "offset": self.offset,
            "admitted_at": self.admitted_at,
            "event": self.event.to_dict(),
        }
        if not include_payload:
            payload["event"].pop("payload", None)
        return payload


@dataclass(frozen=True)
class PublishReceipt:
    admitted: SequencedEvent
    generated: List[SequencedEvent]
    redaction_findings: List[str]
    displaced_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "sensorium_publish_receipt",
            "version": "1.0",
            "admitted_offset": self.admitted.offset,
            "admitted_event_id": self.admitted.event.event_id,
            "generated_event_ids": [entry.event.event_id for entry in self.generated],
            "redaction_findings": list(self.redaction_findings),
            "displaced_count": self.displaced_count,
        }


class SensoriumEventSequencer:
    """Retain a bounded ordered window and make displacement observable."""

    def __init__(self, *, capacity: int = 512, privacy_gate: Optional[SensorPrivacyGate] = None, journal=None):
        if capacity < 2:
            raise ValueError("Sensorium capacity must be at least 2")
        self.capacity = int(capacity)
        self.privacy_gate = privacy_gate or SensorPrivacyGate()
        self._entries: Deque[SequencedEvent] = deque()
        self._lock = RLock()
        self._offset = 0
        self._loss_sequence = 0
        self._published = 0
        self._displaced = 0
        self._privacy_redactions = 0
        self.journal = journal
        if self.journal is not None:
            restored = self.journal.replay(tail=self.capacity)
            self._entries.extend(restored)
            metrics = self.journal.metrics()
            self._offset = int(metrics["durable_offset"])
            self._published = int(metrics["durable_events"])

    def publish(self, event: SensorEvent) -> PublishReceipt:
        sanitized, findings = self.privacy_gate.sanitize(event)
        sanitized.validate()
        with self._lock:
            dropped: List[SequencedEvent] = []
            generated: List[SequencedEvent] = []
            if len(self._entries) >= self.capacity:
                while len(self._entries) > self.capacity - 2:
                    dropped.append(self._entries.popleft())
                loss = self._loss_event(sanitized, dropped)
                loss_entry = self._append(loss)
                generated.append(loss_entry)
                self._displaced += len(dropped)
            admitted = self._append(sanitized)
            self._published += 1
            self._privacy_redactions += len(findings)
            return PublishReceipt(
                admitted=admitted,
                generated=generated,
                redaction_findings=findings,
                displaced_count=len(dropped),
            )

    def snapshot(self, *, since_offset: int = 0, limit: int = 100) -> List[SequencedEvent]:
        if limit < 1:
            return []
        with self._lock:
            selected = [entry for entry in self._entries if entry.offset > since_offset]
            return list(selected[:limit])

    def latest(self, limit: int = 25) -> List[SequencedEvent]:
        if limit < 1:
            return []
        with self._lock:
            return list(self._entries)[-limit:]

    def metrics(self) -> Dict[str, Any]:
        with self._lock:
            first = self._entries[0].offset if self._entries else 0
            last = self._entries[-1].offset if self._entries else 0
            return {
                "beast_object_type": "sensorium_sequencer_metrics",
                "version": "1.0",
                "capacity": self.capacity,
                "retained": len(self._entries),
                "published": self._published,
                "generated_loss_events": self._loss_sequence,
                "displaced": self._displaced,
                "privacy_redactions": self._privacy_redactions,
                "first_retained_offset": first,
                "last_offset": last,
                "read_only": True,
                "journal": self.journal.metrics() if self.journal is not None else {"configured": False},
            }

    def _append(self, event: SensorEvent) -> SequencedEvent:
        self._offset += 1
        entry = SequencedEvent(
            offset=self._offset,
            event=event,
            admitted_at=datetime.now(timezone.utc).isoformat(),
        )
        if self.journal is not None:
            self.journal.append(entry)
        self._entries.append(entry)
        return entry

    def _loss_event(self, incoming: SensorEvent, dropped: List[SequencedEvent]) -> SensorEvent:
        self._loss_sequence += 1
        by_source = Counter(entry.event.source for entry in dropped)
        by_mission = Counter(
            entry.event.attribution.get("mission_id", "unattributed")
            for entry in dropped
        )
        by_mission_source: Dict[str, Counter[str]] = {}
        for entry in dropped:
            mission_id = entry.event.attribution.get("mission_id", "unattributed")
            by_mission_source.setdefault(mission_id, Counter())[entry.event.source] += 1
        dropped_ids = [entry.event.event_id for entry in dropped]
        attribution = {
            key: value
            for key, value in incoming.attribution.items()
            if key in {"mission_id", "workspace_id", "crystal_instance_id"}
        }
        loss = SensorEvent(
            event_type="sensorium.loss",
            source="sensorium_event_sequencer",
            source_instance="local",
            boot_id=incoming.boot_id,
            source_sequence=self._loss_sequence,
            cpu_sequence=0,
            monotonic_ns=time.monotonic_ns(),
            wall_time=datetime.now(timezone.utc).isoformat(),
            attribution=attribution,
            confidence=1.0,
            confidence_method="sequencer_retention_accounting",
            gaps_before=len(dropped),
            loss_counter=self._displaced + len(dropped),
            privacy={
                "class": "internal",
                "raw_retention": "ephemeral",
                "export_allowed": False,
                "redaction_status": "passed",
            },
            payload_schema="beast.sensorium.loss.v1",
            payload={
                "reason": "bounded_retention_displacement",
                "dropped_count": len(dropped),
                "dropped_event_ids": dropped_ids,
                "dropped_by_source": dict(sorted(by_source.items())),
                "dropped_by_mission": dict(sorted(by_mission.items())),
                "dropped_by_mission_source": {
                    mission_id: dict(sorted(counts.items()))
                    for mission_id, counts in sorted(by_mission_source.items())
                },
                "capacity": self.capacity,
            },
        ).sealed()
        loss.validate()
        return loss
