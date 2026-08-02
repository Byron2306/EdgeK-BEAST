"""Editor Sourceplans routes for the BEAST IDE facade."""

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


def register_editor_sourceplans_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _root = ctx._root

    @router.post("/edgek/ide/sourceplan/from-editor")
    async def edgek_ide_sourceplan_from_editor(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        rel = str(payload.get("path") or payload.get("file") or "").strip()
        target = _safe_relative(root, rel)
        if target is None:
            return {
                "ok": False,
                "error": "unsafe_or_empty_path",
                "path": rel,
                "beast_object_type": "beast_desktop_editor_sourceplan_draft",
            }
        original_text = str(payload.get("original_text") or "")
        new_text = str(payload.get("new_text") or "")
        objective = str(payload.get("objective") or f"Apply governed desktop editor changes to {rel}")
        provider = str(payload.get("provider") or "nvidia_nim")
        disk_text = ""
        if target.exists() and target.is_file():
            try:
                disk_text = target.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                return {
                    "ok": False,
                    "error": f"read_failed: {exc}",
                    "path": rel,
                    "beast_object_type": "beast_desktop_editor_sourceplan_draft",
                }
        if disk_text != original_text:
            return {
                "ok": False,
                "stale_context": True,
                "error": "current_file_changed_since_editor_opened",
                "path": rel,
                "current_hash": _hash_text(disk_text),
                "editor_base_hash": _hash_text(original_text),
                "beast_object_type": "beast_desktop_editor_sourceplan_draft",
            }
        if new_text == original_text:
            return {
                "ok": False,
                "error": "no_editor_changes",
                "path": rel,
                "current_hash": _hash_text(disk_text),
                "beast_object_type": "beast_desktop_editor_sourceplan_draft",
            }

        plan_id = "desktop_editor_" + hashlib.sha256(
            f"{root}|{rel}|{time.time()}|{_hash_text(new_text)}".encode("utf-8", errors="replace")
        ).hexdigest()[:12]
        expected_hash = _raw_hash_text(original_text)
        if original_text:
            operation = {
                "op_id": "desktop_001",
                "op": "replace_exact",
                "path": rel,
                "old": original_text,
                "new": new_text,
                "old_text": original_text,
                "new_text": new_text,
                "description": f"Desktop editor replacement for {rel}.",
                "beast_managed": False,
                "source_edit": True,
                "provider_generated": False,
                "selected": True,
                "expected_hash": expected_hash,
            }
        else:
            operation = {
                "op_id": "desktop_001",
                "op": "create_or_replace",
                "path": rel,
                "content": new_text,
                "old": original_text,
                "new": new_text,
                "old_text": original_text,
                "new_text": new_text,
                "description": f"Desktop editor replacement for empty file {rel}.",
                "beast_managed": False,
                "source_edit": True,
                "provider_generated": False,
                "selected": True,
                "expected_hash": expected_hash,
            }
        plan = {
            "plan_id": plan_id,
            "kind": "beast_desktop_editor_source_patch_plan",
            "status": "draft_requires_approval",
            "objective": objective,
            "provider": provider,
            "workspace": str(root),
            "risk_level": "medium",
            "approval_required": True,
            "provider_generated": False,
            "desktop_editor_generated": True,
            "files_allowed": [rel],
            "files_blocked": [],
            "operations": [operation],
            "selected_operations": ["desktop_001"],
            "apply_policy": {
                "source_edits_require": ["selected file", "expected hash", "approval", "verification", "rollback"],
                "rollback_required": True,
                "run_py_compile": True,
                "run_tests": False,
            },
            "prec_mapping": {
                "perceive": "Desktop editor captured the exact source buffer and current file hash.",
                "reason": "The staged file is compiled into one explicit SourcePlan operation.",
                "economize": "Only the selected file is eligible for apply.",
                "crystallize": "Apply still requires BEAST preview, approval, verification, rollback, and evidence closure.",
            },
            "steps": [
                {"step": 1, "action": "preview_diff", "detail": "Review the desktop editor diff."},
                {"step": 2, "action": "verify", "detail": "Run SourcePlan verification before apply."},
                {"step": 3, "action": "apply", "detail": "Apply the selected editor operation with rollback."},
                {"step": 4, "action": "close_evidence", "detail": "Close the mission through Chronicle and Evidence Bus receipts."},
            ],
            "created_at": int(time.time()),
        }
        preview = BeastApiClient("http://offline", workspace=root).preview_patch_plan(plan)
        preview_data = preview.data or {}
        return {
            "ok": bool(preview.ok and not preview_data.get("stale_count")),
            "beast_object_type": "beast_desktop_editor_sourceplan_draft",
            "plan": plan,
            "preview": preview_data,
            "preview_text": str(preview_data.get("diff") or preview.summary or ""),
            "error": preview.error,
            "stale_context": bool(preview_data.get("stale_count")),
        }

    @router.post("/edgek/ide/sourceplan/from-selection")
    async def edgek_ide_sourceplan_from_selection(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        rel = str(payload.get("path") or payload.get("file") or "").strip()
        target = _safe_relative(root, rel)
        if target is None:
            return {
                "ok": False,
                "error": "unsafe_or_empty_path",
                "path": rel,
                "beast_object_type": "beast_desktop_selection_sourceplan_draft",
            }
        original_text = str(payload.get("original_text") or "")
        selection_text = str(payload.get("selection_text") or "")
        replacement_text = str(payload.get("replacement_text") or "")
        objective = str(payload.get("objective") or f"Apply governed selected edit to {rel}")
        provider = str(payload.get("provider") or "nvidia_nim")
        if not selection_text:
            return {
                "ok": False,
                "error": "empty_selection",
                "path": rel,
                "beast_object_type": "beast_desktop_selection_sourceplan_draft",
            }
        disk_text = ""
        if target.exists() and target.is_file():
            try:
                disk_text = target.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                return {
                    "ok": False,
                    "error": f"read_failed: {exc}",
                    "path": rel,
                    "beast_object_type": "beast_desktop_selection_sourceplan_draft",
                }
        if disk_text != original_text:
            return {
                "ok": False,
                "stale_context": True,
                "error": "current_file_changed_since_editor_opened",
                "path": rel,
                "current_hash": _hash_text(disk_text),
                "editor_base_hash": _hash_text(original_text),
                "beast_object_type": "beast_desktop_selection_sourceplan_draft",
            }
        match_count = original_text.count(selection_text)
        if match_count != 1:
            return {
                "ok": False,
                "error": f"selection_matched_{match_count}_times",
                "path": rel,
                "beast_object_type": "beast_desktop_selection_sourceplan_draft",
            }
        if replacement_text == selection_text:
            return {
                "ok": False,
                "error": "no_selection_change",
                "path": rel,
                "beast_object_type": "beast_desktop_selection_sourceplan_draft",
            }
        plan_id = "desktop_selection_" + hashlib.sha256(
            f"{root}|{rel}|{time.time()}|{_hash_text(selection_text)}|{_hash_text(replacement_text)}".encode("utf-8", errors="replace")
        ).hexdigest()[:12]
        line_start = int(payload.get("line_start") or 0)
        line_end = int(payload.get("line_end") or 0)
        operation = {
            "op_id": "selection_001",
            "op": "replace_exact",
            "path": rel,
            "old": selection_text,
            "new": replacement_text,
            "old_text": selection_text,
            "new_text": replacement_text,
            "description": f"Desktop selected edit for {rel}:{line_start or '?'}-{line_end or '?'}",
            "beast_managed": False,
            "source_edit": True,
            "provider_generated": False,
            "selected": True,
            "expected_hash": _raw_hash_text(original_text),
            "selection": {
                "line_start": line_start,
                "line_end": line_end,
                "char_start": int(payload.get("char_start") or 0),
                "char_end": int(payload.get("char_end") or 0),
            },
        }
        plan = {
            "plan_id": plan_id,
            "kind": "beast_desktop_selection_source_patch_plan",
            "status": "draft_requires_approval",
            "objective": objective,
            "provider": provider,
            "workspace": str(root),
            "risk_level": "low",
            "approval_required": True,
            "provider_generated": False,
            "desktop_selection_generated": True,
            "files_allowed": [rel],
            "files_blocked": [],
            "operations": [operation],
            "selected_operations": ["selection_001"],
            "apply_policy": {
                "source_edits_require": ["selected file", "expected hash", "approval", "verification", "rollback"],
                "rollback_required": True,
                "run_py_compile": True,
                "run_tests": False,
            },
            "prec_mapping": {
                "perceive": "Desktop editor captured a unique selected source range and file hash.",
                "reason": "The selected source range is compiled into one exact operation.",
                "economize": "Only the selected snippet is eligible for apply.",
                "crystallize": "Apply remains governed by preview, approval, verification, rollback, and evidence closure.",
            },
            "steps": [
                {"step": 1, "action": "preview_diff", "detail": "Review the selected edit hunk."},
                {"step": 2, "action": "verify", "detail": "Run SourcePlan verification before apply."},
                {"step": 3, "action": "apply", "detail": "Apply the exact selected operation with rollback."},
                {"step": 4, "action": "close_evidence", "detail": "Close through Chronicle and Evidence Bus receipts."},
            ],
            "created_at": int(time.time()),
        }
        preview = BeastApiClient("http://offline", workspace=root).preview_patch_plan(plan)
        preview_data = preview.data or {}
        return {
            "ok": bool(preview.ok and not preview_data.get("stale_count")),
            "beast_object_type": "beast_desktop_selection_sourceplan_draft",
            "plan": plan,
            "preview": preview_data,
            "preview_text": str(preview_data.get("diff") or preview.summary or ""),
            "error": preview.error,
            "stale_context": bool(preview_data.get("stale_count")),
        }
    return None
