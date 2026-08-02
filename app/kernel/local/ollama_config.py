"""Shared local Ollama connection policy.

Keeping this small policy in one module prevents the registry, planner, and
deployment adapters from silently selecting different local models.
"""

from __future__ import annotations

import os


DEFAULT_OLLAMA_MODEL = "qwen2.5:0.5b"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def ollama_model(explicit: str = "") -> str:
    return (
        str(explicit or "").strip()
        or os.environ.get("BEAST_OLLAMA_MODEL", "").strip()
        or os.environ.get("OLLAMA_MODEL", "").strip()
        or DEFAULT_OLLAMA_MODEL
    )


def ollama_base_url(explicit: str = "") -> str:
    return (
        str(explicit or "").strip()
        or os.environ.get("BEAST_OLLAMA_BASE_URL", "").strip()
        or os.environ.get("OLLAMA_HOST", "").strip()
        or os.environ.get("OLLAMA_BASE_URL", "").strip()
        or DEFAULT_OLLAMA_BASE_URL
    ).rstrip("/")
