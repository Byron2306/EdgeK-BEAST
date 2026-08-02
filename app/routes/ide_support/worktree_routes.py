"""Worktree mission route registrar for the BEAST IDE facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter

from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.kernel.workspaces.worktree_forge import WorktreeForge


def register_worktree_mission_routes(router: APIRouter, *, resolve_root: Callable[[Any], Path]) -> None:
    @router.post("/edgek/ide/worktree-mission/create")
    async def edgek_ide_worktree_mission_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = resolve_root(payload.get("root_path"))
        try:
            forge = WorktreeForge(root)
            mission = forge.create(
                objective=str(payload.get("objective") or "BEAST isolated mission"),
                risk=str(payload.get("risk") or "medium"),
                provider=str(payload.get("provider") or ""),
                mode=str(payload.get("mode") or "implementer"),
                base_ref=str(payload.get("base_ref") or "HEAD"),
                task_id=str(payload.get("task_id") or ""),
            )
            if mission.get("ok") and isinstance(mission.get("task"), dict):
                # Keep the session record next to the central worktree registry
                # rather than in a focused child worktree.
                AgentSessionStore(forge.workspace_root).create(
                    objective=str(payload.get("objective") or "BEAST isolated mission"),
                    mode=str(payload.get("mode") or "implementer"),
                    budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else None,
                    tools=["worktree", "sourceplan", "verifier", "evidence_bus"],
                    files=[str(item) for item in (payload.get("files") or [])],
                    agent_id=str(mission["task"].get("task_id") or ""),
                    provider=str(payload.get("provider") or ""),
                )
            return mission
        except Exception as exc:
            # The renderer needs a structured result that it can display and
            # recover from, not Starlette's opaque HTTP 500 page.
            return {
                "ok": False,
                "error": f"Unable to create isolated worktree mission: {exc}",
                "error_type": type(exc).__name__,
                "workspace_root": str(root),
            }

    @router.get("/edgek/ide/worktree-mission/list")
    async def edgek_ide_worktree_mission_list(root_path: str = None):
        """Return the persisted worktree mission registry without a full IDE snapshot."""
        return WorktreeForge(resolve_root(root_path)).list()

    @router.post("/edgek/ide/worktree-mission/test")
    async def edgek_ide_worktree_mission_test(payload: dict[str, Any] = None):
        payload = payload or {}
        command = payload.get("command") if isinstance(payload.get("command"), list) else None
        return WorktreeForge(resolve_root(payload.get("root_path"))).test(
            str(payload.get("task_id") or ""),
            command=[str(item) for item in command] if command else None,
            timeout=float(payload.get("timeout", 120.0)),
        )

    @router.post("/edgek/ide/worktree-mission/diff")
    async def edgek_ide_worktree_mission_diff(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(resolve_root(payload.get("root_path"))).diff(
            str(payload.get("task_id") or ""),
            max_chars=max(1000, min(int(payload.get("max_chars", 60000)), 200000)),
        )

    @router.post("/edgek/ide/worktree-mission/promote")
    async def edgek_ide_worktree_mission_promote(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(resolve_root(payload.get("root_path"))).promote(
            str(payload.get("task_id") or ""),
            approved=bool(payload.get("approved", False)),
            require_tests=bool(payload.get("require_tests", True)),
        )

    @router.post("/edgek/ide/worktree-mission/sourceplan-draft")
    async def edgek_ide_worktree_mission_sourceplan_draft(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(resolve_root(payload.get("root_path"))).sourceplan_draft_from_diff(
            str(payload.get("task_id") or ""),
            max_chars=max(1000, min(int(payload.get("max_chars", 60000)), 200000)),
        )

    @router.post("/edgek/ide/worktree-mission/close")
    async def edgek_ide_worktree_mission_close(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(resolve_root(payload.get("root_path"))).archive(
            str(payload.get("task_id") or ""),
            reason=str(payload.get("reason") or "closed from BEAST IDE"),
        )
