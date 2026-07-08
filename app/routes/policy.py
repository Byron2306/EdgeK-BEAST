"""Policy route family for mode, Spec Covenant, and safety gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from app.kernel.agents.mode_router import ModeRouter
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.policy.spec_covenant import SpecCovenantCompiler
from app.kernel.security.safety_governor import SafetyGovernor


def build_policy_router(default_root: str | Path, mode_router: ModeRouter) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    @router.get("/edgek/architecture-decisions")
    async def edgek_architecture_decisions():
        return architecture_decision_register()

    @router.get("/edgek/mode-router/catalog")
    async def edgek_mode_router_catalog():
        return mode_router.definitions()

    @router.post("/edgek/mode-router/select")
    async def edgek_mode_router_select(payload: Dict[str, Any] = None):
        payload = payload or {}
        return mode_router.select(
            phase=str(payload.get("phase") or ""),
            risk=str(payload.get("risk") or ""),
            requested_mode=str(payload.get("requested_mode") or ""),
            provider=str(payload.get("provider") or ""),
            sourceplan=payload.get("sourceplan") if isinstance(payload.get("sourceplan"), dict) else {},
        )

    @router.post("/edgek/spec-covenant/compile")
    async def edgek_spec_covenant_compile(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return SpecCovenantCompiler(root).compile(
            objective=str(payload.get("objective") or ""),
            files=[str(item) for item in (payload.get("files") or [])],
            mode=str(payload.get("mode") or ""),
            operator_notes=str(payload.get("operator_notes") or ""),
            max_rules=max(1, min(int(payload.get("max_rules", 18)), 100)),
        )

    @router.post("/edgek/spec-covenant/batches")
    async def edgek_spec_covenant_batches(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        covenant = payload.get("covenant") if isinstance(payload.get("covenant"), dict) else {}
        return SpecCovenantCompiler(root).spec_to_sourceplan_batches(
            covenant,
            batch_size=max(1, min(int(payload.get("batch_size", 5)), 50)),
        )

    @router.post("/edgek/safety-governor/classify-command")
    async def edgek_safety_governor_classify_command(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return SafetyGovernor(root).classify_command(
            str(payload.get("command") or ""),
            mode=str(payload.get("mode") or ""),
            task_id=str(payload.get("task_id") or ""),
            operator_override=str(payload.get("operator_override") or ""),
        )

    @router.post("/edgek/safety-governor/scan-workspace")
    async def edgek_safety_governor_scan_workspace(payload: Dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        return SafetyGovernor(root).scan_workspace(
            files=[str(item) for item in payload.get("files") or []] or None,
            max_files=max(1, min(int(payload.get("max_files", 250)), 1000)),
        )

    return router
