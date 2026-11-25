"""Default Direct Coder feature flags for the main TLI and gateway path."""
from __future__ import annotations

import os
from collections.abc import MutableMapping

DIRECT_CODER_ENV_DEFAULTS = {
    "BEAST_DIRECT_CODER_THINKING": "1",
    "BEAST_DIRECT_CODER_INTEGRATIONS": "1",
    "BEAST_SWARM_SPECIALIST": "1",
    "BEAST_SWARM_SPECIALIST_MODEL": "qwen2.5-coder:7b",
    "BEAST_COMPRESSION_TIERS": "1",
}


def apply_direct_coder_env_defaults(environ: MutableMapping[str, str] | None = None) -> None:
    """Set Direct Coder panel and integration flags when the operator left them unset.

    Explicit ``0`` / ``1`` values in the process environment are left alone.
    """
    target = os.environ if environ is None else environ
    for key, value in DIRECT_CODER_ENV_DEFAULTS.items():
        target.setdefault(key, value)
