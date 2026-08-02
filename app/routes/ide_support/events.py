"""Event formatting helpers for the BEAST IDE route layer."""

from __future__ import annotations

import json
import time
from typing import Any


def ide_event(event_type: str, payload: dict[str, Any]) -> str:
    data = {
        "beast_object_type": "beast_ide_event",
        "version": "1.0",
        "event_type": event_type,
        "created_at": int(time.time()),
        "payload": payload,
    }
    return f"event: {event_type}\ndata: {json.dumps(data, sort_keys=True)}\n\n"
