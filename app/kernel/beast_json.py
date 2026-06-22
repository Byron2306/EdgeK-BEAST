"""Fast JSON utilities for BEAST using orjson when available.

Falls back to standard json for environments without orjson.
"""

from __future__ import annotations

import json
from typing import Any

try:
    import orjson
    _HAS_ORJSON = True
except ImportError:
    _HAS_ORJSON = False


def dumps(obj: Any, **kwargs) -> str:
    """Serialize object to JSON string (fast path if orjson available)."""
    if _HAS_ORJSON:
        # orjson returns bytes; decode to str for API compatibility
        return orjson.dumps(obj, **kwargs).decode("utf-8")
    return json.dumps(obj, **kwargs)


def loads(s: str, **kwargs) -> Any:
    """Deserialize JSON string to object."""
    if _HAS_ORJSON:
        return orjson.loads(s)
    return json.loads(s, **kwargs)


def dump(obj: Any, fp, **kwargs) -> None:
    """Serialize object to file-like object."""
    if _HAS_ORJSON:
        fp.write(orjson.dumps(obj, **kwargs).decode("utf-8"))
    else:
        json.dump(obj, fp, **kwargs)


def load(fp, **kwargs) -> Any:
    """Deserialize from file-like object."""
    if _HAS_ORJSON:
        return orjson.loads(fp.read())
    return json.load(fp, **kwargs)