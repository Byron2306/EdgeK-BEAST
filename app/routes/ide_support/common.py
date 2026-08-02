"""Pure, framework-independent helpers used by the BEAST IDE API."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

IGNORED_WORKSPACE_DIRECTORIES = frozenset(
    {".git", ".beast", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".venv", "venv", "data", "logs"}
)
_INSTALLER_BACKUP_DIRECTORY = re.compile(r"^\.phase[0-9a-z-]*backup", re.IGNORECASE)


def is_ignored_workspace_directory(name: str) -> bool:
    """Return whether a directory is generated, vendored, or an installer backup."""
    value = str(name or "")
    return (
        value in IGNORED_WORKSPACE_DIRECTORIES
        or value.startswith(".beast-")
        or bool(_INSTALLER_BACKUP_DIRECTORY.match(value))
    )


def is_compact_local_coder(provider: str, model: str) -> bool:
    provider_id = str(provider or "").strip().lower().replace("-", "_")
    model_id = str(model or "").strip().lower()
    return provider_id in {"ollama", "local_ollama"} and (
        model_id.startswith("qwen2.5-coder:")
        or model_id in {"qwen2.5:0.5b", "qwen2.5:3b", "beast-crystal-qwen25-05b:latest", "beast-crystal-qwen25-3b:latest"}
    )


def pair_programmer_limits(
    provider: str,
    model: str,
    requested_tokens: int,
    requested_context_chars: int,
) -> tuple[int, int, int]:
    """Return bounded output, context, and file limits for a coding turn."""
    if is_compact_local_coder(provider, model):
        return (
            min(max(128, int(requested_tokens)), 1024),
            min(max(1200, int(requested_context_chars)), 2400),
            3,
        )
    if str(provider or "").strip().lower().replace("-", "_") in {"nvidia_nim", "nvidia", "nim"}:
        return (
            min(max(512, int(requested_tokens)), 4096),
            min(max(2400, int(requested_context_chars)), 12000),
            3,
        )
    return (
        min(max(256, int(requested_tokens)), 3072),
        min(max(1600, int(requested_context_chars)), 12000),
        4,
    )


def bounded_workspace_files(root: Path, suffixes: set[str], max_files: int) -> Iterator[Path]:
    """Walk a workspace with directory pruning and a hard file ceiling."""
    yielded = 0
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not is_ignored_workspace_directory(name)]
        for filename in filenames:
            candidate = Path(directory) / filename
            if candidate.suffix.lower() not in suffixes:
                continue
            yield candidate
            yielded += 1
            if yielded >= max_files:
                return


def raw_hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def hash_text(text: str) -> str:
    return "sha256:" + raw_hash_text(text)


def extract_json_object(text: str) -> dict[str, Any]:
    body = str(text or "").strip()
    fence = re.search(r"```(?:json|action_ir)?\s*(\{[\s\S]*?\})\s*```", body, re.IGNORECASE)
    if fence:
        body = fence.group(1).strip()
    starts = [index for index in (body.find("{"), body.find("[")) if index >= 0]
    if not starts:
        return {}
    start = min(starts)
    for end in range(len(body), start, -1):
        candidate = body[start:end].strip()
        try:
            payload = json.loads(candidate)
            if isinstance(payload, list):
                return {"actions": payload}
            return payload if isinstance(payload, dict) else {}
        except Exception:
            continue
    return {}


def safe_relative(root: Path, relative_path: str) -> Path | None:
    """Resolve a path only when it remains inside ``root``."""
    if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        return None
    resolved_root = root.resolve()
    target = (resolved_root / relative_path).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError:
        return None
    return target
