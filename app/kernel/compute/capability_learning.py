from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


@dataclass(frozen=True, slots=True)
class CapabilityLearningEvent:
    event_type: str
    capability_type: str
    capability_id: str
    lifecycle_state: str
    authority: str
    evidence_digest: str
    receipt_digest: str
    provider_calls_used: int = 0
    provider_calls_avoided: int = 0
    fresh_work_units: int = 0
    reuse_hits: int = 0
    refusal_reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    observed_at: str = ""

    def __post_init__(self) -> None:
        for name in ("event_type", "capability_type", "capability_id", "lifecycle_state", "authority"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"{name} is required")
        for name in ("evidence_digest", "receipt_digest"):
            validate_digest(getattr(self, name), field_name=name)
        if min(self.provider_calls_used, self.provider_calls_avoided, self.fresh_work_units, self.reuse_hits) < 0:
            raise ValueError("capability learning counters must be non-negative")
        canonical_json(self.metadata)
        if not self.observed_at:
            object.__setattr__(self, "observed_at", utc_now_iso())

    @property
    def event_digest(self) -> str:
        return sha256_digest(self)


class CapabilityLearningLedger:
    """Append-only local ledger for learned BEAST capabilities.

    This ledger intentionally stores bounded lifecycle projections, not raw
    prompts, pixels, or provider payloads.  It is the operator-facing inventory
    layer over semantic crystals, visual assets, and future capability types.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[CapabilityLearningEvent] = []
        self.load()

    def record(self, **kwargs: Any) -> CapabilityLearningEvent:
        event = CapabilityLearningEvent(**kwargs)
        self._events.append(event)
        self._append(event)
        return event

    def events(self) -> tuple[CapabilityLearningEvent, ...]:
        return tuple(self._events)

    def report(self, *, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        events = self.events()
        by_type = Counter(item.capability_type for item in events)
        by_event = Counter(item.event_type for item in events)
        by_state = Counter(item.lifecycle_state for item in events)
        provider_calls_used = sum(item.provider_calls_used for item in events)
        provider_calls_avoided = sum(item.provider_calls_avoided for item in events)
        fresh_work_units = sum(item.fresh_work_units for item in events)
        reuse_hits = sum(item.reuse_hits for item in events)
        capability_events: dict[str, list[CapabilityLearningEvent]] = defaultdict(list)
        for event in events:
            capability_events[event.capability_id].append(event)
        capabilities = [
            self._capability_summary(capability_id, values)
            for capability_id, values in capability_events.items()
        ]
        capabilities.sort(key=lambda item: (item["last_observed_at"], item["capability_id"]), reverse=True)
        return {
            "beast_object_type": "capability_learning_report",
            "version": "1.0",
            "ledger_path": str(self.path),
            "event_count": len(events),
            "capability_count": len(capabilities),
            "by_capability_type": dict(sorted(by_type.items())),
            "by_event_type": dict(sorted(by_event.items())),
            "by_lifecycle_state": dict(sorted(by_state.items())),
            "provider_calls_used": provider_calls_used,
            "provider_calls_avoided": provider_calls_avoided,
            "fresh_work_units": fresh_work_units,
            "reuse_hits": reuse_hits,
            "capabilities": capabilities[:limit],
            "recent_events": [self._event_dict(item) for item in events[-limit:]][::-1],
            "ledger_digest": sha256_digest(tuple(item.event_digest for item in events)),
        }

    def load(self) -> None:
        self._events.clear()
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                payload = row.get("event")
                if not isinstance(payload, Mapping):
                    continue
                event = CapabilityLearningEvent(
                    event_type=str(payload["event_type"]),
                    capability_type=str(payload["capability_type"]),
                    capability_id=str(payload["capability_id"]),
                    lifecycle_state=str(payload["lifecycle_state"]),
                    authority=str(payload["authority"]),
                    evidence_digest=str(payload["evidence_digest"]),
                    receipt_digest=str(payload["receipt_digest"]),
                    provider_calls_used=int(payload.get("provider_calls_used") or 0),
                    provider_calls_avoided=int(payload.get("provider_calls_avoided") or 0),
                    fresh_work_units=int(payload.get("fresh_work_units") or 0),
                    reuse_hits=int(payload.get("reuse_hits") or 0),
                    refusal_reason=str(payload.get("refusal_reason") or ""),
                    metadata=dict(payload.get("metadata") or {}),
                    observed_at=str(payload.get("observed_at") or ""),
                )
                if row.get("event_digest") == event.event_digest:
                    self._events.append(event)
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue

    def _append(self, event: CapabilityLearningEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"event": asdict(event), "event_digest": event.event_digest}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        temporary.write_text(existing + canonical_json(row) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _event_dict(event: CapabilityLearningEvent) -> dict[str, Any]:
        return {**asdict(event), "event_digest": event.event_digest}

    @classmethod
    def _capability_summary(cls, capability_id: str, events: Iterable[CapabilityLearningEvent]) -> dict[str, Any]:
        values = tuple(sorted(events, key=lambda item: item.observed_at))
        latest = values[-1]
        return {
            "capability_id": capability_id,
            "capability_type": latest.capability_type,
            "lifecycle_state": latest.lifecycle_state,
            "authority": latest.authority,
            "event_count": len(values),
            "first_observed_at": values[0].observed_at,
            "last_observed_at": latest.observed_at,
            "provider_calls_used": sum(item.provider_calls_used for item in values),
            "provider_calls_avoided": sum(item.provider_calls_avoided for item in values),
            "fresh_work_units": sum(item.fresh_work_units for item in values),
            "reuse_hits": sum(item.reuse_hits for item in values),
            "refusal_count": sum(1 for item in values if item.event_type.endswith("refused")),
            "last_receipt_digest": latest.receipt_digest,
            "capability_digest": sha256_digest(tuple(item.event_digest for item in values)),
        }
