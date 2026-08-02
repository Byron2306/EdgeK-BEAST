"""Agent-session route registrar for the BEAST IDE facade."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.routes.ide_support.common import safe_relative


def register_agent_session_routes(
    router: APIRouter,
    *,
    resolve_root: Callable[[Any], Path],
    compile_action_ir_sourceplan: Callable[..., dict[str, Any]],
    validate_agent_sourceplan: Callable[..., dict[str, Any]],
    json_hash: Callable[[Any], str],
) -> None:
    @router.get("/edgek/ide/agent-sessions")
    async def edgek_ide_agent_sessions(root_path: str = None):
        root = resolve_root(root_path)
        return AgentSessionStore(root).list()

    @router.get("/edgek/ide/conductor/dispatches")
    async def edgek_ide_conductor_dispatches(root_path: str = None, workflow_id: str = "", limit: int = 20):
        """Read durable bounded-dispatch receipts for IDE/TUI/CLI inspection."""
        root = resolve_root(root_path)
        return ConductorWorkflowBuilder(data_dir=str(root / ".beast" / "intelligence")).list_dispatches(
            workflow_id=workflow_id,
            limit=max(1, min(int(limit), 100)),
        )

    @router.get("/edgek/ide/agent-sessions/{session_id}")
    async def edgek_ide_agent_session_detail(session_id: str, root_path: str = None):
        root = resolve_root(root_path)
        return AgentSessionStore(root).get(session_id)

    @router.post("/edgek/ide/agent-sessions/create")
    async def edgek_ide_agent_session_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = resolve_root(payload.get("root_path"))
        return AgentSessionStore(root).create(
            objective=str(payload.get("objective") or "BEAST agent session"),
            mode=str(payload.get("mode") or "architect"),
            budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else None,
            tools=[str(item) for item in (payload.get("tools") or [])],
            files=[str(item) for item in (payload.get("files") or [])],
            agent_id=str(payload.get("agent_id") or ""),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/update")
    async def edgek_ide_agent_session_update(payload: dict[str, Any] = None):
        payload = payload or {}
        root = resolve_root(payload.get("root_path"))
        session_id = str(payload.get("session_id") or "")
        return AgentSessionStore(root).update(
            session_id,
            status=str(payload.get("status") or ""),
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else None,
            output=payload.get("output") if isinstance(payload.get("output"), dict) else None,
            files=[str(item) for item in payload.get("files")] if isinstance(payload.get("files"), list) else None,
            tools=[str(item) for item in payload.get("tools")] if isinstance(payload.get("tools"), list) else None,
            budget_delta=payload.get("budget_delta") if isinstance(payload.get("budget_delta"), dict) else None,
        )

    @router.post("/edgek/ide/agent-sessions/capabilities/grant")
    async def edgek_ide_agent_session_capabilities_grant(payload: dict[str, Any] = None):
        """Persist a narrowly approved capability for a later agent turn."""
        payload = payload or {}
        root = resolve_root(payload.get("root_path"))
        session_id = str(payload.get("session_id") or "")
        requested = [str(item) for item in payload.get("capabilities") or []]
        allowed = {"workspace_search", "read_related_files", "use_verified_skill", "run_isolated_verifier"}
        grants = [item for item in requested if item in allowed]
        if not session_id or not grants:
            return {"ok": False, "error": "session_id and at least one supported read-only capability are required"}
        paths: list[str] = []
        for item in payload.get("paths") or []:
            rel = str(item or "")
            safe = safe_relative(root, rel)
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
        return AgentSessionStore(resolve_root(payload.get("root_path"))).pause(str(payload.get("session_id") or ""))

    @router.post("/edgek/ide/agent-sessions/resume")
    async def edgek_ide_agent_session_resume(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(resolve_root(payload.get("root_path"))).resume(str(payload.get("session_id") or ""))

    @router.post("/edgek/ide/agent-sessions/cancel")
    async def edgek_ide_agent_session_cancel(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(resolve_root(payload.get("root_path"))).cancel(
            str(payload.get("session_id") or ""),
            reason=str(payload.get("reason") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/sourceplan-draft")
    async def edgek_ide_agent_session_sourceplan_draft(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(resolve_root(payload.get("root_path"))).sourceplan_draft(
            str(payload.get("session_id") or ""),
            output=str(payload.get("output") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/action-ir-sourceplan")
    async def edgek_ide_agent_session_action_ir_sourceplan(payload: dict[str, Any] = None):
        payload = payload or {}
        return compile_action_ir_sourceplan(
            resolve_root(payload.get("root_path")),
            output=str(payload.get("output") or ""),
            provider=str(payload.get("provider") or "desktop_agent"),
            requested_files=[str(item) for item in payload.get("files") or [] if item],
            active_file=str(payload.get("active_file") or ""),
            objective=str(payload.get("objective") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/verify-sourceplan")
    async def edgek_ide_agent_session_verify_sourceplan(payload: dict[str, Any] = None):
        payload = payload or {}
        root = resolve_root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        if not plan:
            raise HTTPException(status_code=400, detail="No agent SourcePlan was supplied for verification")
        validation = validate_agent_sourceplan(root, plan, run_isolated_verifier=True)
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
            artifact_hash=json_hash({"plan_id": plan.get("plan_id"), "validation": validation}),
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
