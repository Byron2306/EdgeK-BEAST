"""Durable AgentRun API for BEAST IDE, CLI, and future ACP clients."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.planner_provider import CallbackPlannerProvider, ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.promotion_engine import PromotionEngine
from app.kernel.evidence.evidence_builder import EvidenceBuilder
from app.kernel.evidence.evidence_store import EvidenceStore
from app.kernel.agents.run_state import TERMINAL_STATES, normalize_state
from app.kernel.agents.run_worker import AGENT_RUN_WORKERS
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.cli.api import BeastApiClient
from app.routes.ide_context import IdeRouteContext


def _legacy_execution_params(run: dict[str, Any]) -> list[tuple[str, str]]:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    params: list[tuple[str, str]] = [
        ("root_path", str(run.get("root_path") or "")),
        ("prompt", str(request.get("prompt") or run.get("objective") or "")),
        ("provider", str(run.get("provider") or "")),
        ("model", str(run.get("model") or "")),
        ("run_id", str(run.get("run_id") or "")),
        ("simulate", "true" if bool(request.get("simulate")) else "false"),
        ("max_tokens", str(int(request.get("max_tokens") or 2000))),
        ("context_max_chars_each", str(int(request.get("context_max_chars_each") or 30000))),
        ("max_repair_rounds", str(int(request.get("max_repair_rounds") or 3))),
        ("approval_timeout_seconds", str(int(request.get("approval_timeout_seconds") or 3600))),
    ]
    for path in request.get("context_files") if isinstance(request.get("context_files"), list) else []:
        params.append(("context_files", str(path)))
    return params


async def _execute_legacy_agent_run(app: Any, root: Path, run_id: str) -> None:
    """Drive the existing proven provider pipeline as a detached durable worker.

    The legacy route remains the execution adapter in Phase 2B. Its emitted
    events are recorded by ``AgentRunEngine`` and replayed independently to any
    number of clients. The initiating renderer no longer owns provider life.
    """

    engine = AgentRunEngine(root)
    run = engine.store.get_run(run_id)
    if not run:
        return
    session_id = str(run.get("session_id") or "")
    if not session_id:
        engine.fail(run_id, "durable run has no agent session")
        return
    engine.emit(run_id, "agent.run.worker.started", {
        "adapter": "legacy_pair_programmer_v2",
        "session_id": session_id,
    })
    path = f"/edgek/ide/agent-sessions/{quote(session_id, safe='')}/run-events"
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://beast.internal",
            timeout=httpx.Timeout(None),
        ) as client:
            async with client.stream("GET", path, params=_legacy_execution_params(run), headers={"Accept": "text/event-stream"}) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                    raise RuntimeError(f"legacy AgentRun adapter returned HTTP {response.status_code}: {body}")
                async for _chunk in response.aiter_bytes():
                    engine.raise_if_cancelled(run_id)
        final = engine.store.get_run(run_id) or {}
        if normalize_state(str(final.get("state") or "created")) not in TERMINAL_STATES:
            engine.fail(run_id, "AgentRun execution ended without a terminal event")
    except asyncio.CancelledError:
        final = engine.store.get_run(run_id) or {}
        if normalize_state(str(final.get("state") or "created")) not in TERMINAL_STATES:
            engine.finalize_cancel(run_id, str(final.get("cancel_reason") or "operator_cancelled"))
        raise
    except Exception as exc:
        final = engine.store.get_run(run_id) or {}
        if normalize_state(str(final.get("state") or "created")) not in TERMINAL_STATES:
            engine.fail(run_id, str(exc))


def _launch(app: Any, root: Path, run_id: str) -> dict[str, Any]:
    existing = AGENT_RUN_WORKERS.get(run_id)
    handle = AGENT_RUN_WORKERS.launch(run_id, lambda: _execute_legacy_agent_run(app, root, run_id))
    return {
        "active": not handle.task.done(),
        "task_name": handle.task.get_name(),
        "reused": existing is not None,
    }


async def _execute_planner_run(
    root: Path,
    run_id: str,
    *,
    base_url: str,
    scripted_decisions: list[dict[str, Any]] | None = None,
    max_turns: int = 8,
) -> None:
    engine = AgentRunEngine(root)
    run = engine.store.get_run(run_id)
    if not run:
        return
    if scripted_decisions is not None:
        provider = ScriptedPlannerProvider(scripted_decisions)
    else:
        client = BeastApiClient(base_url or "http://127.0.0.1:8000", workspace=root)

        async def _next(prompt: str, current_run: dict[str, Any], turn: int):
            parts: list[str] = []
            options = {
                "provider": str(current_run.get("provider") or "nvidia_nim"),
                "model": str(current_run.get("model") or "meta/llama-3.1-8b-instruct"),
                "context_files": [],
                "max_tokens": 900,
                "context_max_files": 0,
                "context_max_chars_each": 1200,
                "governance_level": "ide_agent_planner_next_action",
                "allow_fallback": False,
            }
            async for event in client.stream_live_turn(prompt, [], **options):
                if str(event.get("type") or "") == "token":
                    parts.append(str(event.get("text") or ""))
                elif str(event.get("type") or "") == "error":
                    raise RuntimeError(str(event.get("error") or "planner provider failed"))
            return "".join(parts)

        provider = CallbackPlannerProvider(_next)
    runtime = AgentPlannerRuntime(engine, provider, max_turns=max_turns)
    try:
        await runtime.run(run_id)
    except asyncio.CancelledError:
        final = engine.store.get_run(run_id) or {}
        if normalize_state(str(final.get("state") or "created")) not in TERMINAL_STATES:
            engine.finalize_cancel(run_id, str(final.get("cancel_reason") or "operator_cancelled"))
        raise
    except Exception as exc:
        final = engine.store.get_run(run_id) or {}
        if normalize_state(str(final.get("state") or "created")) not in TERMINAL_STATES:
            engine.fail(run_id, str(exc))


def _launch_planner(
    root: Path,
    run_id: str,
    *,
    base_url: str,
    scripted_decisions: list[dict[str, Any]] | None,
    max_turns: int,
) -> dict[str, Any]:
    existing = AGENT_RUN_WORKERS.get(run_id)
    handle = AGENT_RUN_WORKERS.launch(
        run_id,
        lambda: _execute_planner_run(
            root, run_id, base_url=base_url, scripted_decisions=scripted_decisions, max_turns=max_turns
        ),
    )
    return {
        "active": not handle.task.done(),
        "task_name": handle.task.get_name(),
        "reused": existing is not None,
        "engine": "typed_planner_v1",
    }


def register_agent_runs_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _root = ctx._root

    @router.post("/edgek/agent-runs")
    async def edgek_agent_run_create(request: Request, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        session_result = AgentSessionStore(root).get(session_id)
        if not session_result.get("ok"):
            raise HTTPException(status_code=404, detail=str(session_result.get("error") or "unknown session"))
        session = session_result.get("session") if isinstance(session_result.get("session"), dict) else {}
        request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        run = AgentRunEngine(root).create_run(
            session_id=session_id,
            objective=str(payload.get("objective") or request_payload.get("prompt") or session.get("objective") or "BEAST agent run"),
            mode=str(payload.get("mode") or session.get("mode") or "agent"),
            provider=str(payload.get("provider") or session.get("provider") or ""),
            model=str(payload.get("model") or session.get("model") or ""),
            request=request_payload,
            budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else session.get("budget") if isinstance(session.get("budget"), dict) else {},
            run_id=str(payload.get("run_id") or ""),
        )
        execution = _launch(request.app, root, str(run["run_id"])) if bool(payload.get("launch")) else AGENT_RUN_WORKERS.status(str(run["run_id"]))
        return {"ok": True, "run": AgentRunEngine(root).store.get_run(str(run["run_id"])), "execution": execution}

    @router.get("/edgek/agent-runs")
    async def edgek_agent_runs(
        root_path: str = None,
        session_id: str = "",
        state: str = "",
        limit: int = 50,
    ):
        root = _root(root_path)
        runs = AgentRunEngine(root).store.list_runs(session_id=session_id, state=state, limit=limit)
        for run in runs:
            run["execution"] = AGENT_RUN_WORKERS.status(str(run.get("run_id") or ""))
        return {
            "beast_object_type": "beast_agent_run_registry",
            "version": "2.1",
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
        run["execution"] = AGENT_RUN_WORKERS.status(run_id)
        return {"ok": True, "run": run}

    @router.get("/edgek/agent-runs/{run_id}/events")
    async def edgek_agent_run_events(
        request: Request,
        run_id: str,
        root_path: str = None,
        after: int = 0,
        limit: int = 250,
        follow: bool = Query(default=False),
        projection: str = Query(default="canonical", pattern="^(canonical|legacy)$"),
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
                        yield engine.sse_event(event, projection=projection)
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

    @router.get("/edgek/agent-runs/{run_id}/tools")
    async def edgek_agent_run_tools(
        run_id: str,
        root_path: str = None,
        category: str = "",
        effect: str = "",
    ):
        engine = AgentRunEngine(_root(root_path))
        if not engine.store.get_run(run_id):
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        tools = engine.list_tools(category=category, effect=effect)
        return {
            "beast_object_type": "beast_agent_tool_registry",
            "version": "1.0",
            "ok": True,
            "run_id": run_id,
            "count": len(tools),
            "tools": tools,
        }

    @router.post("/edgek/agent-runs/{run_id}/tools/{tool_id}/execute")
    async def edgek_agent_run_tool_execute(run_id: str, tool_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        engine = AgentRunEngine(_root(payload.get("root_path")))
        if not engine.store.get_run(run_id):
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        try:
            observation = await engine.execute_tool(
                run_id,
                tool_id,
                payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
                execution_target=str(payload.get("execution_target") or "local"),
                approval_id=str(payload.get("approval_id") or ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "beast_object_type": "beast_agent_tool_observation",
            "version": "1.0",
            "ok": True,
            "run_id": run_id,
            "observation": observation,
        }

    @router.post("/edgek/agent-runs/{run_id}/planner/execute")
    async def edgek_agent_run_planner_execute(request: Request, run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        engine = AgentRunEngine(root)
        run = engine.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        if normalize_state(str(run.get("state") or "created")) in TERMINAL_STATES:
            raise HTTPException(status_code=409, detail="terminal runs cannot be relaunched")
        scripted = payload.get("simulate_decisions")
        if scripted is not None and not isinstance(scripted, list):
            raise HTTPException(status_code=400, detail="simulate_decisions must be a list")
        max_turns = max(1, min(int(payload.get("max_turns") or 8), 64))
        base_url = str(request.base_url).rstrip("/")
        execution = _launch_planner(
            root, run_id, base_url=base_url, scripted_decisions=scripted, max_turns=max_turns
        )
        return {"ok": True, "run": engine.store.get_run(run_id), "execution": execution}

    @router.get("/edgek/agent-runs/{run_id}/planner")
    async def edgek_agent_run_planner_state(run_id: str, root_path: str = None):
        engine = AgentRunEngine(_root(root_path))
        run = engine.store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        return {
            "beast_object_type": "beast_agent_planner_state",
            "version": "1.0",
            "ok": True,
            "run_id": run_id,
            "planner": checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {},
            "execution": AGENT_RUN_WORKERS.status(run_id),
        }


    @router.post("/edgek/agent-runs/{run_id}/promotion/evaluate")
    async def edgek_agent_run_promotion_evaluate(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return PromotionEngine(_root(payload.get("root_path"))).evaluate(
                run_id, requested_by=str(payload.get("requested_by") or "operator")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.get("/edgek/agent-runs/{run_id}/promotion")
    async def edgek_agent_run_promotion_state(run_id: str, root_path: str = None):
        try:
            return PromotionEngine(_root(root_path)).state(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/agent-runs/{run_id}/promotion/commit-candidate")
    async def edgek_agent_run_promotion_commit(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        approval_id = str(payload.get("approval_id") or "")
        if not approval_id:
            raise HTTPException(status_code=400, detail="approval_id is required")
        try:
            return PromotionEngine(_root(payload.get("root_path"))).promote(
                run_id, approval_id=approval_id, commit_message=str(payload.get("commit_message") or "")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/edgek/agent-runs/{run_id}/evidence/crystallize")
    async def edgek_agent_run_evidence_crystallize(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            evidence = EvidenceBuilder(_root(payload.get("root_path"))).crystallize(run_id)
            return {"ok": True, "evidence": evidence}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/edgek/evidence")
    async def edgek_evidence_list(root_path: str = None, limit: int = 50):
        items = EvidenceStore(_root(root_path)).list(limit=limit)
        return {"ok": True, "count": len(items), "evidence": items}

    @router.get("/edgek/evidence/{evidence_id}")
    async def edgek_evidence_get(evidence_id: str, root_path: str = None):
        evidence = EvidenceStore(_root(root_path)).get(evidence_id)
        if not evidence:
            raise HTTPException(status_code=404, detail=f"unknown evidence crystal: {evidence_id}")
        return {"ok": True, "evidence": evidence}

    @router.get("/edgek/evidence/{evidence_id}/verify")
    async def edgek_evidence_verify(evidence_id: str, root_path: str = None):
        try:
            return EvidenceBuilder(_root(root_path)).verify(evidence_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/agent-runs/{run_id}/cancel")
    async def edgek_agent_run_cancel(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        engine = AgentRunEngine(_root(payload.get("root_path")))
        if not engine.store.get_run(run_id):
            raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")
        return await engine.cancel(run_id, str(payload.get("reason") or "operator_cancelled"))

    @router.post("/edgek/agent-runs/{run_id}/resume")
    async def edgek_agent_run_resume(request: Request, run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        engine = AgentRunEngine(root)
        try:
            run = engine.resume(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        execution = _launch(request.app, root, run_id)
        return {"ok": True, "run": engine.store.get_run(run_id), "execution": execution}

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
            engine.store.transition(run_id, "planning")
        return {"ok": True, "approval": approval, "event": event, "run": engine.store.get_run(run_id)}

    return None
