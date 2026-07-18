"""SourcePlan route family."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.cli.api import BeastApiClient


def build_sourceplan_router(default_root: str | Path) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    @router.post("/edgek/sourceplan/scorecard")
    async def edgek_sourceplan_scorecard(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).sourceplan_scorecard(plan)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "scorecard failed")
        return result.data

    @router.post("/edgek/sourceplan/preview")
    async def edgek_sourceplan_preview(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).render_patch_diff(plan)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "preview failed")
        return result.data

    @router.post("/edgek/sourceplan/verify")
    async def edgek_sourceplan_verify(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).verify_patch_plan(plan)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "verification failed")
        return result.data

    @router.post("/edgek/sourceplan/apply")
    async def edgek_sourceplan_apply(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        result = BeastApiClient("http://gateway-local", workspace=root).apply_patch_plan(
            plan,
            approved=bool(payload.get("approved", False)),
        )
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "apply failed")
        return result.data

    @router.post("/edgek/sourceplan/rollback-latest")
    async def edgek_sourceplan_rollback_latest(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        result = BeastApiClient("http://gateway-local", workspace=root).rollback_last_patch()
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or result.summary or "rollback failed")
        return result.data

    @router.post("/edgek/sourceplan/lattice-replay")
    async def edgek_sourceplan_lattice_replay(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else None
        return BeastApiClient("http://gateway-local", workspace=root).mission_lattice_replay_scaffold(
            plan,
            scorecard=scorecard,
            limit=max(1, min(int(payload.get("limit", 5)), 50)),
        )

    return router
