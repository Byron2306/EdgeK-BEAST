"""Reviewed deterministic file/build transformation used by replay and runtime."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_workspace(value: str | Path) -> Path:
    root = Path(value)
    if not root.is_dir() or root.is_symlink():
        raise PermissionError("workspace descriptor is not a safe directory")
    return root.resolve()


def inspect_source(root: str | Path) -> dict[str, Any]:
    source = safe_workspace(root) / "source.json"
    eligible = False; parsed: dict[str, Any] = {}; reason = "source_missing"
    if source.is_file() and not source.is_symlink() and source.stat().st_size <= 4096:
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
            if (isinstance(value, dict) and isinstance(value.get("name"), str)
                    and 0 < len(value["name"]) <= 64 and isinstance(value.get("values"), list)
                    and len(value["values"]) <= 128
                    and all(isinstance(item, int) and not isinstance(item, bool) and abs(item) <= 1_000_000 for item in value["values"])):
                parsed, eligible, reason = value, True, "canonical_source_schema"
            else: reason = "source_schema_outside_contract"
        except (OSError, UnicodeError, json.JSONDecodeError):
            reason = "source_unreadable_or_invalid_json"
    raw = source.read_bytes() if source.is_file() and not source.is_symlink() else b""
    result = {"eligible": eligible, "reason": reason, "source_sha256": sha256_bytes(raw), "bytes": len(raw)}
    if eligible: result["parsed"] = parsed
    return result


def expected_artifact(source: Mapping[str, Any]) -> bytes:
    value = source["parsed"]
    product = {"count": len(value["values"]), "name": value["name"],
               "source_sha256": source["source_sha256"], "sum": sum(value["values"])}
    return (json.dumps(product, sort_keys=True, separators=(",", ":")) + "\n").encode()


def atomic_render(root: str | Path, source: Mapping[str, Any]) -> dict[str, Any]:
    workspace = safe_workspace(root); target = workspace / "generated.json"; encoded = expected_artifact(source)
    temporary = workspace / ".generated.json.tmp"
    temporary.write_bytes(encoded); os.chmod(temporary, 0o600); os.replace(temporary, target)
    return {"written": True, "refused": False, "bounded": True,
            "artifact_sha256": sha256_bytes(encoded), "bytes": len(encoded)}


def verify_artifact(root: str | Path, source: Mapping[str, Any]) -> dict[str, Any]:
    target = safe_workspace(root) / "generated.json"
    if not target.is_file() or target.is_symlink():
        return {"verified": False, "safe_refusal": False, "bytes_match": False, "tests_passed": False}
    actual = target.read_bytes(); matches = actual == expected_artifact(source)
    return {"verified": matches, "safe_refusal": False, "bytes_match": matches,
            "tests_passed": matches, "artifact_sha256": sha256_bytes(actual)}
