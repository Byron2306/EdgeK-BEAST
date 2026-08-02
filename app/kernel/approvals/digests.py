from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

DIGEST_PREFIX = "sha256:"


def canonicalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): canonicalize(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    if isinstance(value, set):
        return sorted((canonicalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_digest(value: Any) -> str:
    return DIGEST_PREFIX + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def verify_digest(value: Any, claimed_digest: str) -> bool:
    return bool(claimed_digest) and sha256_digest(value) == claimed_digest


def semantic_payload(value: Mapping[str, Any], *, exclude: set[str] | None = None) -> dict[str, Any]:
    ignored = {"request_digest", "receipt_digest", "event_digest", "transition_digest"}
    if exclude:
        ignored.update(exclude)
    return {key: item for key, item in value.items() if key not in ignored}
