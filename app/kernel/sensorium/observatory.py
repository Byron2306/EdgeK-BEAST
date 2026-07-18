"""Compact, payload-free Runtime Observatory projection."""
from __future__ import annotations

from typing import Any, Mapping


def project_observatory(sensorium_state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "beast_object_type": "runtime_observatory",
        "authority": "read_only",
        "actuator_available": False,
        "process_forest": sensorium_state.get("process_forest", ()),
        "socket_topology": sensorium_state.get("socket_topology", ()),
        "recent_event_types": sensorium_state.get("recent_event_types", {}),
        "recent_closed_episodes": sensorium_state.get("recent_closed_episodes", ()),
    }

