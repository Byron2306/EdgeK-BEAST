"""Actions routes for the BEAST IDE facade."""

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


def register_actions_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _ide_action_manifest = ctx._ide_action_manifest
    _json_hash = ctx._json_hash
    _root = ctx._root

    @router.get("/edgek/ide/actions/manifest")
    async def edgek_ide_actions_manifest(
        root_path: str = None,
        page: str = "",
        query: str = "",
    ):
        _root(root_path)
        actions = _ide_action_manifest()
        needle = query.strip().lower()
        page_filter = page.strip().lower()
        if page_filter:
            actions = [item for item in actions if item.get("page") == page_filter or page_filter in item.get("tags", [])]
        if needle:
            actions = [
                item for item in actions
                if needle in item.get("id", "").lower()
                or needle in item.get("label", "").lower()
                or needle in item.get("description", "").lower()
                or any(needle in str(tag).lower() for tag in item.get("tags", []))
            ]
        return {
            "beast_object_type": "beast_ide_action_manifest",
            "version": "1.0",
            "count": len(actions),
            "actions": actions,
            "governance": {
                "direct_mutation_allowed": False,
                "writes_require_sourceplan": True,
                "risky_actions_require_approval": True,
                "terminal_execution_requires_safety_governor": True,
                "worktree_recommended_for_high_risk": True,
                "receipts_are_authoritative": True,
            },
        }

    @router.post("/edgek/ide/actions/plan")
    async def edgek_ide_action_plan(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        action_id = str(payload.get("action_id") or "")
        action = next((item for item in _ide_action_manifest() if item["id"] == action_id), None)
        if not action:
            return {
                "beast_object_type": "beast_ide_action_plan",
                "action_id": action_id,
                "status": "unknown_action",
                "allowed": False,
                "reason": "Action is not declared in the BEAST IDE manifest.",
            }
        plan = {
            "beast_object_type": "beast_ide_action_plan",
            "version": "1.0",
            "action_id": action_id,
            "label": action["label"],
            "page": action["page"],
            "status": "planned",
            "allowed": True,
            "client_handler": action["client_handler"],
            "endpoint": action.get("endpoint"),
            "method": action.get("method"),
            "risk": action.get("risk"),
            "approval_required": action.get("approval_required", False),
            "sourceplan_required": action.get("sourceplan_required", False),
            "worktree_recommended": action.get("worktree_recommended", False),
            "provider_required": action.get("provider_required", False),
            "direct_mutation_allowed": False,
            "server_side_execution": False,
            "execution_note": "The desktop client runs declared handlers; the backend manifest only plans and governs action visibility.",
        }
        out_dir = root / ".beast" / "ide" / "actions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{_raw_hash_text(action_id)[:16]}.json"
        out_path.write_text(json.dumps(plan, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_action_plan",
            artifact_path=out_path,
            artifact_hash=_json_hash(plan),
            source="desktop_ide",
            task_id=action_id,
            status="planned",
            summary=f"IDE action planned: {action['label']}",
            metadata={"page": action["page"], "risk": action.get("risk")},
        )
        return {**plan, "path": str(out_path), "evidence_receipt": receipt}
    return None
