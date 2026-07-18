"""HTTP product boundary for the production ComputePlane."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException


def build_compute_mission_router(compute_plane: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/edgek/compute/missions")
    async def execute_compute_mission(payload: dict[str, Any]):
        return await _execute(payload, "api")

    async def _execute(payload: dict[str, Any], interface: str):
        try:
            receipt = compute_plane.execute_user_mission(payload, interface=interface)
            route = "provider_fallback" if receipt.__class__.__name__ == "ProviderFallbackReceipt" else "production_crystal"
            return {"status": "ok", "route": route, "receipt": asdict(receipt)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/edgek/compute/cli/missions")
    async def execute_cli_compute_mission(payload: dict[str, Any]):
        return await _execute(payload, "cli")

    @router.post("/edgek/compute/ide/missions")
    async def execute_ide_compute_mission(payload: dict[str, Any]):
        return await _execute(payload, "ide")

    return router
