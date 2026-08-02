"""Canonical BEAST build identity loader.

The generated JSON is release metadata, not a policy authority. Runtime code may
report it, but must never derive permissions from version strings.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IDENTITY_PATH = _REPO_ROOT / "build" / "BUILD_IDENTITY.json"
_FALLBACK: dict[str, Any] = {
    "schema": "beast.build-identity.v1",
    "product": "BEAST IDE",
    "product_version": "unavailable",
    "release_id": "BEAST-IDE-UNAVAILABLE",
    "backend_gateway_version": "0.1.0",
    "backend_api_version": "3",
    "identity_digest": "unavailable",
}


@lru_cache(maxsize=1)
def load_build_identity() -> dict[str, Any]:
    """Return a bounded copy of the generated release identity."""
    try:
        payload = json.loads(_IDENTITY_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != "beast.build-identity.v1":
            return dict(_FALLBACK)
        return {str(key): value for key, value in payload.items()}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return dict(_FALLBACK)
