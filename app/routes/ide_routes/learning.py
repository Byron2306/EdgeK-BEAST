"""Learning routes for the BEAST IDE facade."""

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


def register_learning_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _json_hash = ctx._json_hash
    _root = ctx._root
    edgek_ide_sourceplan_lifecycle = ctx.handlers['sourceplan_lifecycle']

    @router.post("/edgek/ide/learning-queue/propose")
    async def edgek_ide_learning_queue_propose(request: Request, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        note = str(payload.get("note") or payload.get("objective") or "Promote successful governed IDE workflow.")
        lifecycle = await edgek_ide_sourceplan_lifecycle(request, {"root_path": str(root), "plan": plan}) if plan else {}
        checks = [
            {"name": "sourceplan_present", "passed": bool(plan)},
            {"name": "verification_passed", "passed": bool((lifecycle.get("verification") or {}).get("ok", lifecycle.get("can_apply")))},
            {"name": "operation_ledger_present", "passed": bool((lifecycle.get("operation_ledger") or {}).get("operation_count"))},
            {"name": "evidence_related", "passed": bool((lifecycle.get("evidence") or {}).get("match_count"))},
            {"name": "rollback_required", "passed": bool((lifecycle.get("action_contract") or {}).get("rollback_required", True))},
        ]
        score = round(100 * sum(1 for item in checks if item["passed"]) / len(checks), 2)
        proposal_id = "learn_" + hashlib.sha256(f"{root}|{note}|{time.time()}".encode("utf-8")).hexdigest()[:12]
        proposal = {
            "ok": True,
            "beast_object_type": "beast_ide_learning_proposal",
            "version": "1.0",
            "proposal_id": proposal_id,
            "created_at": int(time.time()),
            "status": "candidate_ready" if score >= 80 else "needs_more_evidence",
            "score": score,
            "note": note,
            "plan_id": str(plan.get("plan_id") or ""),
            "requires_human_review": True,
            "crystalization_direct_write_allowed": False,
            "checks": checks,
        }
        out_dir = root / ".beast" / "ide" / "learning" / "proposals"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{proposal_id}.json"
        out_path.write_text(json.dumps(proposal, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_learning_proposal",
            artifact_path=out_path,
            artifact_hash=_json_hash(proposal),
            source="desktop_ide",
            task_id=str(plan.get("plan_id") or proposal_id),
            status=proposal["status"],
            summary=note,
            metadata={"score": score},
        )
        return {**proposal, "path": str(out_path), "evidence_receipt": receipt}
    return None
