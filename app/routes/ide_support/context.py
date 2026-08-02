"""Shared route context for the BEAST IDE API facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class IdeRouteContext:
    """Small compatibility context for decomposing ``app.routes.ide`` safely."""

    def __init__(self, default_root: str | Path) -> None:
        self.fallback_root = Path(default_root).expanduser().resolve()

    def root(self, value: Any = None) -> Path:
        return Path(value or self.fallback_root).expanduser().resolve()
