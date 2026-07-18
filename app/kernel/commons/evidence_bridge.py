"""Privacy-safe Commons operations projected into Sensorium and evidence graph."""
from __future__ import annotations

from typing import Any, Mapping

from app.kernel.evidence.control_graph import ControlEvidenceGraph, EvidenceNode


class CommonsEvidenceBridge:
    def __init__(self, *, sensorium=None, evidence: ControlEvidenceGraph | None = None):
        self.sensorium = sensorium
        self.evidence = evidence or ControlEvidenceGraph()

    def emit(self, event_type: str, payload: Mapping[str, Any], *, workspace_id: str = "",
             mission_id: str = "", policy_generation: str = "unknown") -> EvidenceNode:
        safe = dict(payload)
        node = self.evidence.add(
            event_type.replace(".", "_"),
            {**safe, "issuer": "beast.commons", "policy_generation": policy_generation},
        )
        if self.sensorium is not None:
            self.sensorium.observe_owned(
                event_type=event_type, source="beast_commons_enterprise_plane",
                payload_schema=f"beast.sensor.{event_type}.v1", payload=safe,
                workspace_id=workspace_id, mission_id=mission_id,
                privacy_class="internal", export_allowed=False,
            )
        return node
