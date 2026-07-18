"""Non-privileged adapters for BEAST-owned Sensorium observations."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from app.kernel.sensorium.contracts import SensorEvent
from app.kernel.sensorium.physical_effects import physical_effect_payload


def current_boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    return "boot-id-unavailable"


class BeastOwnedEventFactory:
    """Build observations from events BEAST already owns or receives."""

    def __init__(self, *, boot_id: Optional[str] = None, source_instance: str = "local"):
        self.boot_id = boot_id or current_boot_id()
        self.source_instance = source_instance
        self._sequences: Dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def build(
        self,
        *,
        event_type: str,
        source: str,
        payload_schema: str,
        payload: Dict[str, Any],
        mission_id: str = "",
        workspace_id: str = "",
        process_lease_id: str = "",
        crystal_instance_id: str = "",
        confidence: float = 1.0,
        confidence_method: str = "beast_owned_event",
        privacy_class: str = "internal",
        export_allowed: bool = False,
    ) -> SensorEvent:
        with self._lock:
            self._sequences[source] += 1
            sequence = self._sequences[source]
        attribution = {
            key: value
            for key, value in {
                "mission_id": mission_id,
                "workspace_id": workspace_id,
                "process_lease_id": process_lease_id,
                "crystal_instance_id": crystal_instance_id,
            }.items()
            if value
        }
        return SensorEvent(
            event_type=event_type,
            source=source,
            source_instance=self.source_instance,
            boot_id=self.boot_id,
            source_sequence=sequence,
            cpu_sequence=0,
            monotonic_ns=time.monotonic_ns(),
            wall_time=datetime.now(timezone.utc).isoformat(),
            attribution=attribution,
            confidence=confidence,
            confidence_method=confidence_method,
            gaps_before=0,
            loss_counter=0,
            privacy={
                "class": privacy_class,
                "raw_retention": "ephemeral",
                "export_allowed": export_allowed,
                "redaction_status": "not_scanned",
            },
            payload_schema=payload_schema,
            payload=dict(payload),
        )

    def process_event(self, action: str, payload: Dict[str, Any], **scope: Any) -> SensorEvent:
        return self.build(
            event_type=f"process.{action}",
            source="beast_owned_process_adapter",
            payload_schema=f"beast.sensor.process.{action}.v1",
            payload=payload,
            **scope,
        )

    def pressure_sample(self, payload: Dict[str, Any], **scope: Any) -> SensorEvent:
        return self.build(
            event_type="pressure.sample",
            source="beast_pressure_adapter",
            payload_schema="beast.sensor.pressure.sample.v1",
            payload=payload,
            **scope,
        )

    def interception_event(self, action: str, payload: Dict[str, Any], **scope: Any) -> SensorEvent:
        return self.build(
            event_type=f"interception.{action}",
            source="beast_interception_adapter",
            payload_schema=f"beast.sensor.interception.{action}.v1",
            payload=payload,
            **scope,
        )

    def file_effect(self, action: str, payload: Dict[str, Any], **scope: Any) -> SensorEvent:
        return self.build(
            event_type=f"file.{action}",
            source="beast_file_effect_adapter",
            payload_schema=f"beast.sensor.file.{action}.v1",
            payload=payload,
            **scope,
        )

    def port_lease_event(self, action: str, payload: Dict[str, Any], **scope: Any) -> SensorEvent:
        return self.build(
            event_type=f"port_lease.{action}",
            source="beast_port_lease_adapter",
            payload_schema=f"beast.sensor.port_lease.{action}.v1",
            payload=payload,
            **scope,
        )

    def physical_event(
        self,
        *,
        event_type: str,
        source: str,
        payload_schema: str,
        operation: str,
        phase: str,
        subject: str,
        result: str,
        payload: Optional[Dict[str, Any]] = None,
        **options: Any,
    ) -> SensorEvent:
        """Build an observation with typed causal/effect facts."""
        facts = dict(payload or {})
        effect_options = {
            key: facts.pop(key)
            for key in (
                "reads", "requires", "writes", "produces", "descriptor_refs",
                "caused_by_event_ids", "branch", "state_transition",
            )
            if key in facts
        }
        facts.update(physical_effect_payload(
            operation=operation,
            phase=phase,
            subject=subject,
            result=result,
            **effect_options,
        ))
        return self.build(
            event_type=event_type,
            source=source,
            payload_schema=payload_schema,
            payload=facts,
            **options,
        )
