"""Durable AgentRun API for BEAST IDE, CLI, and future ACP clients."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import TERMINAL_STATES, normalize_state
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.routes.ide_context import IdeRouteContext


def register_agent_runs_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _root = ctx._root

    @router.post("/edgek/agent-runs")
    async def edgek_agent_run_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        session_result = AgentSessionStore(root).get(session_id)
        if not session_result.get("ok"):
            raise HTTPException(status_code=404, detail=str(session_result.get("error") or "unknown session"))
        session = session_result.get("session") if isinstance(session_result.get("session"), dict) else {}
        run = AgentRunEngine(root).create_run(
            session_id=session_id,
            objective=str(payload.get("objective") or session.get("objective") or "BEAST agent run"),
            mode=str(payload.get("mode") or session.get("mode") or "agent"),
            provider=str(payload.get("provider") or session.get("provider") or ""),
            model=str(payload.get("model") or session.get("model") or ""),
            request=payload.get("request") if isinstance(payload.get("request"), dict) else {},
            budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else session.get("budget") if isinstance(session.get("budget"), dict) else {},
            run_id=str(payload.get("run_id") or ""),
        )
        return {"ok": True, "run": run}

    @router.get("/edgek/agent-runs")
    async def edgek_agent_runs(
        root_path: str = None,
        session_id: str = "",
        state: str = "",
        limit: int = 50,
    ):
        root = _root(root_path)
        runs = AgentRunEngine(root).store.list_runs(session_id=session_id, state=state, limit=limit)
        return {
            "beast_object_type": "beast_agent_run_registry",
            "version": "2.0",
            "ok": True,
            "workspace_root": str(root),
            "count": len(runs),
            "runs": runs,
        }

    @router.get("/edgek/agent-runs/{run_id}")
    async def edgek_agent_run_detail(run_id: str, root_path: str = None):
        run = AgentRunEngine(_root(root_path)).store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        return {"ok": True, "run": run}

    @router.get("/edgek/agent-runs/{run_id}/events")
    async def edgek_agent_run_events(
        request: Request,
        run_id: str,
        root_path: str = None,
        after: int = 0,
        limit: int = 250,
        follow: bool = Query(default=False),
    ):
        engine = AgentRunEngine(_root(root_path))
        if not engine.store.get_run(run_id):
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        accept = str(request.headers.get("accept") or "")
        if not follow and "text/event-stream" not in accept:
            events = engine.store.events(run_id, after=after, limit=limit)
            return {"ok": True, "run_id": run_id, "after": after, "count": len(events), "events": events}

        async def stream():
            cursor = max(0, int(after))
            quiet = 0
            while True:
                if await request.is_disconnected():
                    return
                events = engine.store.events(run_id, after=cursor, limit=limit)
                if events:
                    quiet = 0
                    for event in events:
                        cursor = int(event["sequence"])
                        yield engine.sse_event(event)
                else:
                    quiet += 1
                    run = engine.store.get_run(run_id) or {}
                    if str(run.get("state") or "") in {state.value for state in TERMINAL_STATES}:
                        return
                    if quiet % 50 == 0:
                        yield f": keepalive run={run_id} after={cursor}\n\n"
                    await asyncio.sleep(0.2)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-BEAST-Agent-Run-ID": run_id,
        })

    @router.post("/edgek/agent-runs/{run_id}/cancel")
    async def edgek_agent_run_cancel(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        engine = AgentRunEngine(_root(payload.get("root_path")))
        if not engine.store.get_run(run_id):
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        return await engine.cancel(run_id, str(payload.get("reason") or "operator_cancelled"))

    @router.post("/edgek/agent-runs/{run_id}/resume")
    async def edgek_agent_run_resume(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        engine = AgentRunEngine(_root(payload.get("root_path")))
        try:
            run = engine.resume(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "run": run}

    @router.get("/edgek/agent-runs/{run_id}/verify")
    async def edgek_agent_run_verify(run_id: str, root_path: str = None):
        result = AgentRunEngine(_root(root_path)).store.verify_chain(run_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=f"unknown or invalid agent run: {run_id}")
        return result

    @router.get("/edgek/agent-runs/{run_id}/approvals")
    async def edgek_agent_run_approvals(run_id: str, root_path: str = None):
        engine = AgentRunEngine(_root(root_path))
        if not engine.store.get_run(run_id):
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        approvals = engine.store.approvals(run_id)
        return {"ok": True, "run_id": run_id, "count": len(approvals), "approvals": approvals}

    @router.post("/edgek/agent-runs/{run_id}/approvals/{approval_id}")
    async def edgek_agent_run_approval_resolve(run_id: str, approval_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        engine = AgentRunEngine(root)
        try:
            approval = engine.store.resolve_approval(run_id, approval_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        run = engine.store.get_run(run_id) or {}
        request_payload = approval.get("request") if isinstance(approval.get("request"), dict) else {}
        if bool(payload.get("approved")) and run.get("session_id"):
            capabilities = request_payload.get("capabilities") if isinstance(request_payload.get("capabilities"), list) else []
            ids = [str(item.get("id") or "") for item in capabilities if isinstance(item, dict)]
            paths = [
                str(path)
                for item in capabilities if isinstance(item, dict)
                for path in (item.get("paths") if isinstance(item.get("paths"), list) else [])
            ]
            session_store = AgentSessionStore(root)
            current = session_store.get(str(run["session_id"]))
            if current.get("ok"):
                session = current.get("session") if isinstance(current.get("session"), dict) else {}
                tools = list(dict.fromkeys([*(session.get("tools") or []), *[f"granted:{item}" for item in ids if item]]))
                files = list(dict.fromkeys([*(session.get("files") or []), *paths[:12]]))
                session_store.update(str(run["session_id"]), tools=tools, files=files, evidence=[{
                    "beast_object_type": "beast_agent_run_approval_resolution",
                    "run_id": run_id,
                    "approval_id": approval_id,
                    "approved": True,
                    "capabilities": ids,
                    "paths": paths[:12],
                }])
        event = engine.emit(run_id, "agent.approval.resolved", {
            "approval_id": approval_id,
            "approved": bool(payload.get("approved")),
            "scope": payload.get("scope") or "once",
        })
        state = normalize_state(str((engine.store.get_run(run_id) or {}).get("state") or "created"))
        if state.value == "waiting_for_approval":
            # Phase 2A approval requests expand optional read/verifier scope.
            # A rejection is durable but the legacy run may continue within
            # its original operator-selected boundary.
            engine.store.transition(run_id, "planning")
        return {"ok": True, "approval": approval, "event": event, "run": engine.store.get_run(run_id)}

    return None
