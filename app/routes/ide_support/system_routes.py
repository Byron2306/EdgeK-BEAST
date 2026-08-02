"""Read-only system inspection route registrar for the BEAST IDE facade."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter

from app.kernel.workspaces import system_inspector


def register_system_inspection_routes(router: APIRouter, *, resolve_root: Callable[[Any], Path]) -> None:
    @router.get("/edgek/ide/system-snapshot")
    async def edgek_ide_system_snapshot(root_path: str = None, process_query: str = "", port_limit: int = 60, process_limit: int = 30):
        root = resolve_root(root_path)
        return await asyncio.to_thread(
            system_inspector.system_snapshot,
            root,
            port_limit=max(1, min(int(port_limit), 500)),
            process_limit=max(1, min(int(process_limit), 200)),
            process_query=process_query,
        )

    @router.get("/edgek/ide/ports")
    async def edgek_ide_ports(limit: int = 300):
        return await asyncio.to_thread(system_inspector.list_listening_ports, max(1, min(int(limit), 1000)))

    @router.get("/edgek/ide/processes")
    async def edgek_ide_processes(query: str = "", limit: int = 120, sort: str = "memory"):
        return await asyncio.to_thread(system_inspector.list_processes, query, max(1, min(int(limit), 500)), sort)

    @router.get("/edgek/ide/process/{pid}")
    async def edgek_ide_process_detail(pid: int):
        return await asyncio.to_thread(system_inspector.process_detail, int(pid))

    @router.get("/edgek/ide/environment")
    async def edgek_ide_environment(root_path: str = None):
        root = resolve_root(root_path)
        return await asyncio.to_thread(system_inspector.environment_report, root)

    @router.get("/edgek/ide/packages")
    async def edgek_ide_packages(root_path: str = None):
        root = resolve_root(root_path)
        return await asyncio.to_thread(system_inspector.package_report, root)

    @router.get("/edgek/ide/extensions")
    async def edgek_ide_extensions(root_path: str = None):
        root = resolve_root(root_path)
        return await asyncio.to_thread(system_inspector.extensions_report, root)

    @router.get("/edgek/ide/catalog")
    async def edgek_ide_catalog(root_path: str = None):
        root = resolve_root(root_path)
        return await asyncio.to_thread(system_inspector.catalog_report, root)
