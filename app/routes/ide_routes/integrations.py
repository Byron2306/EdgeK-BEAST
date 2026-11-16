"""Read-only IDE routes for the canonical integration catalog."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter

from app.routes.ide_support.integration_catalog import build_integration_catalog


def register_integration_routes(router: APIRouter, *, resolve_root: Callable[[str | None], Path]) -> None:
    @router.get("/edgek/ide/integrations")
    async def edgek_ide_integrations(root_path: str | None = None):
        root = resolve_root(root_path)
        return await asyncio.to_thread(build_integration_catalog, root)


__all__ = ["register_integration_routes"]
