"""Worktrees routes for the BEAST IDE facade."""

from __future__ import annotations
import asyncio
import ast
import difflib
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, List
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from app.cli.api import ActionResult, BeastApiClient
from app.kernel.compute.action_ir import ACTION_IR_KIND, ActionIR
from app.kernel.compute.action_resolver import build_file_references, resolve_action_ir
from app.kernel.adapters.provider_handoff import build_provider_handoff, render_provider_handoff_prompt
from app.kernel.data_processing.semantic_raid import SemanticRaidStore
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.security.safety_governor import SafetyGovernor
from app.kernel.workspaces import system_inspector
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.kernel.workspaces.worktree_forge import WorktreeForge
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder
from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.capability.skill_tree import SkillTree
from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.routes.ide_support.common import bounded_workspace_files as _bounded_workspace_files, extract_json_object as _extract_json_object, hash_text as _hash_text, is_compact_local_coder as _is_compact_local_coder, pair_programmer_limits as _pair_programmer_limits, raw_hash_text as _raw_hash_text, safe_relative as _safe_relative
from app.routes.ide_context import IdeRouteContext


def register_worktrees_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _root = ctx._root

    @router.post("/edgek/ide/worktree-mission/create")
    async def edgek_ide_worktree_mission_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        try:
            forge = WorktreeForge(root)
            objective = str(payload.get("objective") or "BEAST isolated mission")
            mode = str(payload.get("mode") or "implementer")
            provider = str(payload.get("provider") or "")
            files = [str(item) for item in (payload.get("files") or [])]

            def _create_mission() -> dict[str, Any]:
                mission = forge.create(
                    objective=objective,
                    risk=str(payload.get("risk") or "medium"),
                    provider=provider,
                    mode=mode,
                    base_ref=str(payload.get("base_ref") or "HEAD"),
                    task_id=str(payload.get("task_id") or ""),
                )
                if mission.get("ok") and isinstance(mission.get("task"), dict):
                    # Keep the session record next to the central worktree registry
                    # rather than in a focused child worktree.
                    AgentSessionStore(forge.workspace_root).create(
                        objective=objective,
                        mode=mode,
                        budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else None,
                        tools=["worktree", "sourceplan", "verifier", "evidence_bus"],
                        files=files,
                        agent_id=str(mission["task"].get("task_id") or ""),
                        provider=provider,
                    )
                return mission

            mission = await asyncio.to_thread(_create_mission)
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
        return WorktreeForge(_root(root_path)).list()

    @router.post("/edgek/ide/worktree-mission/test")
    async def edgek_ide_worktree_mission_test(payload: dict[str, Any] = None):
        payload = payload or {}
        command = payload.get("command") if isinstance(payload.get("command"), list) else None
        return WorktreeForge(_root(payload.get("root_path"))).test(
            str(payload.get("task_id") or ""),
            command=[str(item) for item in command] if command else None,
            timeout=float(payload.get("timeout", 120.0)),
        )

    @router.post("/edgek/ide/worktree-mission/diff")
    async def edgek_ide_worktree_mission_diff(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).diff(
            str(payload.get("task_id") or ""),
            max_chars=max(1000, min(int(payload.get("max_chars", 60000)), 200000)),
        )

    @router.post("/edgek/ide/worktree-mission/promote")
    async def edgek_ide_worktree_mission_promote(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).promote(
            str(payload.get("task_id") or ""),
            approved=bool(payload.get("approved", False)),
            require_tests=bool(payload.get("require_tests", True)),
        )

    @router.post("/edgek/ide/worktree-mission/sourceplan-draft")
    async def edgek_ide_worktree_mission_sourceplan_draft(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).sourceplan_draft_from_diff(
            str(payload.get("task_id") or ""),
            max_chars=max(1000, min(int(payload.get("max_chars", 60000)), 200000)),
        )

    @router.post("/edgek/ide/worktree-mission/close")
    async def edgek_ide_worktree_mission_close(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).archive(
            str(payload.get("task_id") or ""),
            reason=str(payload.get("reason") or "closed from BEAST IDE"),
        )
    return None
