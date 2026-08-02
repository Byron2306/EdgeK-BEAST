"""Agent Sessions routes for the BEAST IDE facade."""

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
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import TERMINAL_STATES
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


def register_agent_sessions_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _compile_agent_action_ir_sourceplan = ctx._compile_agent_action_ir_sourceplan
    _json_hash = ctx._json_hash
    _root = ctx._root
    _validate_agent_sourceplan = ctx._validate_agent_sourceplan

    def _payload_root(payload: dict[str, Any] | None) -> Path:
        payload = payload or {}
        return _root(payload.get("root_path") or payload.get("workspace_root"))

    @router.get("/edgek/ide/agent-sessions")
    async def edgek_ide_agent_sessions(root_path: str = None):
        root = _root(root_path)
        return AgentSessionStore(root).list()

    @router.get("/edgek/ide/conductor/dispatches")
    async def edgek_ide_conductor_dispatches(root_path: str = None, workflow_id: str = "", limit: int = 20):
        """Read durable bounded-dispatch receipts for IDE/TUI/CLI inspection."""
        root = _root(root_path)
        return ConductorWorkflowBuilder(data_dir=str(root / ".beast" / "intelligence")).list_dispatches(
            workflow_id=workflow_id,
            limit=max(1, min(int(limit), 100)),
        )

    @router.get("/edgek/ide/agent-sessions/{session_id}")
    async def edgek_ide_agent_session_detail(session_id: str, root_path: str = None):
        root = _root(root_path)
        return AgentSessionStore(root).get(session_id)

    @router.post("/edgek/ide/agent-sessions/create")
    async def edgek_ide_agent_session_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _payload_root(payload)
        return AgentSessionStore(root).create(
            objective=str(payload.get("objective") or payload.get("task") or "BEAST agent session"),
            mode=str(payload.get("mode") or "architect"),
            budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else None,
            tools=[str(item) for item in (payload.get("tools") or [])],
            files=[str(item) for item in (payload.get("files") or [])],
            agent_id=str(payload.get("agent_id") or ""),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            execution_target=str(payload.get("execution_target") or "local"),
            execution_target_payload=payload.get("execution_target_payload") if isinstance(payload.get("execution_target_payload"), dict) else {},
        )

    @router.post("/edgek/ide/agent-sessions/update")
    async def edgek_ide_agent_session_update(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _payload_root(payload)
        session_id = str(payload.get("session_id") or "")
        return AgentSessionStore(root).update(
            session_id,
            status=str(payload.get("status") or ""),
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else None,
            output=payload.get("output") if isinstance(payload.get("output"), dict) else None,
            files=[str(item) for item in payload.get("files")] if isinstance(payload.get("files"), list) else None,
            tools=[str(item) for item in payload.get("tools")] if isinstance(payload.get("tools"), list) else None,
            budget_delta=payload.get("budget_delta") if isinstance(payload.get("budget_delta"), dict) else None,
            execution_target=str(payload.get("execution_target") or "") if "execution_target" in payload else None,
            execution_target_payload=payload.get("execution_target_payload") if isinstance(payload.get("execution_target_payload"), dict) else ({ } if "execution_target_payload" in payload else None),
        )

    @router.post("/edgek/ide/agent-sessions/capabilities/grant")
    async def edgek_ide_agent_session_capabilities_grant(payload: dict[str, Any] = None):
        """Persist a narrowly approved capability for a later agent turn.

        This endpoint never executes a shell command and never grants write
        authority.  ``run_isolated_verifier`` only permits BEAST's existing
        allowlisted verifier runner in a temporary workspace. SourcePlan
        remains the only route to a source mutation.
        """
        payload = payload or {}
        root = _payload_root(payload)
        session_id = str(payload.get("session_id") or "")
        requested = [str(item) for item in payload.get("capabilities") or []]
        allowed = {"workspace_search", "read_related_files", "use_verified_skill", "run_isolated_verifier"}
        grants = [item for item in requested if item in allowed]
        if not session_id or not grants:
            return {"ok": False, "error": "session_id and at least one supported read-only capability are required"}
        paths: list[str] = []
        for item in payload.get("paths") or []:
            rel = str(item or "")
            safe = _safe_relative(root, rel)
            if safe is not None and safe.is_file():
                paths.append(rel)
        store = AgentSessionStore(root)
        current = store.get(session_id)
        if not current.get("ok"):
            return current
        session = current.get("session") if isinstance(current.get("session"), dict) else {}
        tools = list(dict.fromkeys([*(session.get("tools") or []), *[f"granted:{item}" for item in grants]]))
        files = list(dict.fromkeys([*(session.get("files") or []), *paths[:12]]))
        return store.update(
            session_id,
            tools=tools,
            files=files,
            evidence=[{
                "beast_object_type": "beast_agent_capability_grant",
                "session_id": session_id,
                "request_id": str(payload.get("request_id") or ""),
                "capabilities": grants,
                "paths": paths[:12],
                "authority": "read_only_next_turn",
                "writes": "SourcePlan approval required",
                "timestamp": time.time(),
            }],
        )

    @router.post("/edgek/ide/agent-sessions/pause")
    async def edgek_ide_agent_session_pause(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_payload_root(payload)).pause(str(payload.get("session_id") or ""))

    @router.post("/edgek/ide/agent-sessions/resume")
    async def edgek_ide_agent_session_resume(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_payload_root(payload)).resume(str(payload.get("session_id") or ""))

    @router.post("/edgek/ide/agent-sessions/cancel")
    async def edgek_ide_agent_session_cancel(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _payload_root(payload)
        session_id = str(payload.get("session_id") or "")
        reason = str(payload.get("reason") or "")
        session_result = AgentSessionStore(root).cancel(session_id, reason=reason)
        engine = AgentRunEngine(root)
        terminal = {state.value for state in TERMINAL_STATES}
        cancelled_runs = []
        for run in engine.store.list_runs(session_id=session_id, limit=50):
            if str(run.get("state") or "") in terminal:
                continue
            cancelled_runs.append(await engine.cancel(str(run.get("run_id") or ""), reason or "session_cancelled"))
        session_result["agent_runs"] = cancelled_runs
        return session_result

    @router.post("/edgek/ide/agent-sessions/sourceplan-draft")
    async def edgek_ide_agent_session_sourceplan_draft(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_payload_root(payload)).sourceplan_draft(
            str(payload.get("session_id") or ""),
            output=str(payload.get("output") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/action-ir-sourceplan")
    async def edgek_ide_agent_session_action_ir_sourceplan(payload: dict[str, Any] = None):
        payload = payload or {}
        return _compile_agent_action_ir_sourceplan(
            _payload_root(payload),
            output=str(payload.get("output") or ""),
            provider=str(payload.get("provider") or "desktop_agent"),
            requested_files=[str(item) for item in payload.get("files") or [] if item],
            active_file=str(payload.get("active_file") or ""),
            objective=str(payload.get("objective") or ""),
            selection=payload.get("selection") if isinstance(payload.get("selection"), dict) else None,
            execution_target=str(payload.get("execution_target") or "local"),
            execution_target_payload=payload.get("execution_target_payload") if isinstance(payload.get("execution_target_payload"), dict) else {},
        )

    @router.post("/edgek/ide/agent-sessions/verify-sourceplan")
    async def edgek_ide_agent_session_verify_sourceplan(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _payload_root(payload)
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        if not plan:
            raise HTTPException(status_code=400, detail="No agent SourcePlan was supplied for verification")
        validation = _validate_agent_sourceplan(
            root,
            plan,
            run_isolated_verifier=True,
            execution_target=str(payload.get("execution_target") or plan.get("execution_target") or "local"),
            execution_target_payload=payload.get("execution_target_payload") if isinstance(payload.get("execution_target_payload"), dict) else plan.get("execution_target_payload") if isinstance(plan.get("execution_target_payload"), dict) else {},
        )
        plan["validation"] = validation
        plan["status"] = "draft_validation_passed" if validation.get("ok") else "draft_validation_failed"
        plan.setdefault("output_evidence", {})["operator_requested_isolated_verification"] = {
            "status": validation.get("status"),
            "check_count": validation.get("check_count"),
            "isolated": validation.get("isolated_verifiers"),
        }
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_agent_isolated_verification",
            artifact_path=root / ".beast" / "ide" / "agent-verification",
            artifact_hash=_json_hash({"plan_id": plan.get("plan_id"), "validation": validation}),
            source="desktop_ide",
            task_id=str(plan.get("plan_id") or "agent_sourceplan_verification"),
            status=str(validation.get("status") or "checked"),
            summary=(
                "Ran agent requested isolated verifier checks: "
                f"{(validation.get('isolated_verifiers') or {}).get('passed', 0)} passed, "
                f"{(validation.get('isolated_verifiers') or {}).get('failed', 0)} failed"
            ),
            metadata={
                "plan_id": plan.get("plan_id"),
                "check_count": validation.get("check_count"),
                "isolated_verifiers": validation.get("isolated_verifiers"),
            },
        )
        return {
            "ok": bool(validation.get("ok")),
            "status": validation.get("status"),
            "validation": validation,
            "plan": plan,
            "evidence_receipt": receipt,
        }
    return None
