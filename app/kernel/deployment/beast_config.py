"""Centralized Configuration for BEAST.

Single source of truth for paths, URLs, thresholds, and environment overrides.
Usage:
    from app.kernel import beast_config as cfg
    cfg.OLLAMA_URL
    cfg.DATA_DIR / "kv_cache"
    cfg.KV_MAX_MEMORY_BYTES
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, get_args, get_origin, get_type_hints


@dataclass
class BeastConfig:
    """BEAST configuration with env var overrides and sensible defaults."""

    # --- Core Paths ---
    REPO_ROOT: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    DATA_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "data")
    LOGS_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "logs")

    # --- Ollama (CPU inference) ---
    OLLAMA_URL: str = "http://localhost:11434"
    # Small local default; override with BEAST_OLLAMA_MODEL when available.
    OLLAMA_MODEL: str = "qwen2.5:0.5b"
    OLLAMA_TIMEOUT: int = 180

    # --- KV Cache Transport ---
    # Keep KV residency subordinate to the local model and IDE.
    KV_MAX_MEMORY_BYTES: int = 512 * 1024 * 1024
    KV_CACHE_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "data" / "kv_cache")
    KV_TRANSPORT_ENDPOINT: str = ""
    KV_TRANSPORT_TOKEN: str = ""
    KV_TRANSPORT_MAX_BYTES: int = 64 * 1024 * 1024

    # --- Scheduler ---
    SCHEDULER_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "data" / "scheduler")
    SCHEDULER_MAX_CONCURRENT: int = 5

    # --- Ablation Harness ---
    ABLATION_TIMEOUT: int = 120
    ABLATION_PARALLEL: int = 1  # CPU-first default; increase on multi-core

    # --- Forge Node ---
    FORGE_NODE_ID: str = "default_forge"
    FORGE_WORK_INTERVAL: int = 300  # seconds
    FORGE_LEDGER_PATH: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "data" / "compute_ledger.json")

    # --- Compute Governor ---
    BEAST_COMPUTE_GOVERNOR_MODE: str = "shadow"
    BEAST_COMPUTE_WEEKLY_CALL_VOLUME: Optional[int] = None

    # --- Observability ---
    CORRELATION_ID_HEADER: str = "X-Beast-Correlation-Id"
    STRUCTURED_LOGGING: bool = True

    # --- Error / Circuit Breaker ---
    OLLAMA_CIRCUIT_BREAKER_THRESHOLD: int = 3
    OLLAMA_CIRCUIT_BREAKER_TIMEOUT: int = 30  # seconds

    def __post_init__(self):
        type_hints = get_type_hints(type(self))
        for key in self.__dataclass_fields__:
            env_key = key if key.startswith("BEAST_") else f"BEAST_{key}"
            if env_key in os.environ:
                val = os.environ[env_key]
                field_type = type_hints.get(key, str)
                type_args = get_args(field_type) if get_origin(field_type) is not None else ()
                if field_type is Path or Path in type_args:
                    setattr(self, key, Path(val))
                elif field_type is int or int in type_args:
                    setattr(self, key, int(val))
                elif field_type is bool or bool in type_args:
                    setattr(self, key, val.lower() in ("1", "true", "yes"))
                else:
                    setattr(self, key, val)

        # Ensure directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.KV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.SCHEDULER_DIR.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        return {k: str(v) if isinstance(v, Path) else v for k, v in self.__dict__.items()}


# Singleton instance
config = BeastConfig()

# Convenience aliases
OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
DATA_DIR = config.DATA_DIR
KV_CACHE_DIR = config.KV_CACHE_DIR
SCHEDULER_DIR = config.SCHEDULER_DIR
FORGE_LEDGER_PATH = config.FORGE_LEDGER_PATH
BEAST_COMPUTE_GOVERNOR_MODE = config.BEAST_COMPUTE_GOVERNOR_MODE
