"""Local BEAST runtime configuration helpers."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Dict, Mapping, Optional


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = ROOT / ".beast" / "beast.env"


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_local_env(path: Optional[Path] = None, *, override: bool = False) -> Dict[str, str]:
    target = path or DEFAULT_ENV_PATH
    values = parse_env_file(target)
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def write_local_env(updates: Mapping[str, str], path: Optional[Path] = None) -> Dict[str, str]:
    target = path or DEFAULT_ENV_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    current = parse_env_file(target)
    merged = {**current, **{str(key): str(value) for key, value in updates.items()}}
    lines = [
        "# Local BEAST runtime configuration.",
        "# This file is intentionally ignored by git.",
    ]
    for key in sorted(merged):
        lines.append(f"{key}={merged[key]}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    load_local_env(target, override=True)
    return merged


def ensure_signing_key(existing: str = "") -> str:
    return existing or secrets.token_hex(32)
