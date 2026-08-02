"""Durable AgentRun API for BEAST IDE, CLI, and future ACP clients."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from app.kernel.approvals import (
    ApprovalContractFactory,
    ApprovalRecoveryService,
    ApprovalRiskClassifier,
    RichApprovalEnvelopeBuilder,
    DurableApprovalCardStore,
    ApprovalScopeEngine,
    RequestBoundCapabilityIssuer,
    ExactStepResumeRuntime,
    PermissionModeEngine,
    SensitiveDataController,
    policy_from_sensitive_payload,
    ExternalContentAdmissionController,
    policy_from_external_payload,
    DurableApprovalStore,
    RevocationPolicyStore,
    Phase4EndToEndClosure,
    policy_from_payload,
)
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.commons.route_damping import RouteFlapDampener
from app.kernel.operations_console import (AgentOperationsConsoleViewModel, DurableConsoleEventProjection, WorkbenchModeEngine, ObjectivePlanWorkspace, ContextManifestStore, ContextManifestConsole, LiveRunTimelineConsole, WorktreeChangesDiffConsole, VerificationConsole)
from app.kernel.operations_console.context_console import ContextManifestConsole
from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.nim_planner_provider import NIMPlannerProvider
from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway
from app.kernel.local.ollama_kv_manager import OllamaKVManager
from app.kernel.agents.planner_provider import CallbackPlannerProvider, CapabilityScoredPlannerProvider, FallbackPlannerProvider, HeuristicPlannerProvider, ScriptedPlannerProvider
from app.kernel.agents.provider_quality import ProviderQualityLedger
from app.kernel.agents.planner_resilience import build_resilient_nim_provider, build_resilient_ollama_provider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.promotion_engine import PromotionEngine
from app.kernel.evidence.evidence_builder import EvidenceBuilder
from app.kernel.evidence.evidence_store import EvidenceStore
from app.kernel.evidence.evidence_ledger import EvidenceLedger
from app.kernel.evidence.fingerprint_store import FingerprintStore
from app.kernel.evidence.fingerprint_engine import compare_fingerprints
from app.kernel.evidence.evidence_retrieval import EvidenceRetriever
from app.kernel.evidence.compatibility_engine import CompatibilityEngine
from app.kernel.evidence.equivalence_engine import FreshVerificationEquivalenceEngine
from app.kernel.evidence.sourceplan_handoff import SourcePlanReuseHandoffEngine
from app.kernel.evidence.operator_approval import OperatorReviewApprovalEngine
from app.kernel.evidence.capability_consumption import OneUseSourcePlanApplyEngine
from app.kernel.evidence.post_apply_gate import PostApplyVerificationPromotionGate
from app.kernel.evidence.promotion_closure import PromotionExecutionRollbackClosure
from app.kernel.evidence.phase3_closure import Phase3EndToEndProofClosure
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
    finally:
        # Provider lifecycle belongs to the stream/planner adapter. The
        # detached worker owns only durable observation of that stream.
        pass


def _launch(app: Any, root: Path, run_id: str) -> dict[str, Any]:
    existing = AGENT_RUN_WORKERS.get(run_id)
    handle = AGENT_RUN_WORKERS.launch(run_id, lambda: _execute_legacy_agent_run(app, root, run_id))
    return {
        "active": not handle.task.done(),
        "task_name": handle.task.get_name(),
        "reused": existing is not None,
    }


def _prefer_direct_ollama_planner(run: dict[str, Any]) -> bool:
    provider = str(run.get("provider") or "").strip().lower()
    mode = str(run.get("mode") or "").strip().lower()
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    strategy = str(request.get("launch_strategy") or request.get("execution_adapter") or "").strip().lower()
    proof = str(request.get("proof") or "").strip().lower()
    if provider in {"ollama", "local_ollama"} and strategy in {"planner", "typed_planner", "ollama_planner"}:
        return True
    if proof == "canonical_agent_run_ollama_v1":
        return True
    return provider in {"ollama", "local_ollama"} and mode in {"agent", "analysis", "implementer", "edit"}


def _prefer_direct_planner(run: dict[str, Any]) -> bool:
    provider = str(run.get("provider") or "").strip().lower()
    return _prefer_direct_ollama_planner(run) or provider in {"nvidia_nim", "nim", "local_nim"}


def _planner_provider_base_url() -> str:
    """Return Ollama's native origin, never the BEAST gateway origin."""
    return str(
        os.environ.get("BEAST_OLLAMA_BASE_URL")
        or os.environ.get("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def _ollama_base_url(run: dict[str, Any]) -> str:
    """Resolve the request-scoped native Ollama origin for IDE AgentRuns."""
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    explicit = (
        request.get("ollama_base_url")
        or request.get("provider_base_url")
        or request.get("ollama_host")
    )
    return str(explicit or _planner_provider_base_url()).rstrip("/")


def _planner_max_turns(run: dict[str, Any], request_payload: dict[str, Any]) -> int:
    requested = (run.get("budget") or {}).get("max_turns") or request_payload.get("max_turns")
    if requested is not None:
        return max(1, min(int(requested), 64))
    provider = str(run.get("provider") or "").strip().lower()
    mode = str(run.get("mode") or "").strip().lower()
    if provider in {"ollama", "local_ollama"} and mode in {"agent", "edit", "implementer"}:
        return 5
    return 8


def _normalized_execution_request(payload: dict[str, Any], request_payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    request = dict(request_payload or {})
    execution_target = str(
        payload.get("execution_target")
        or request.get("execution_target")
        or session.get("execution_target")
        or "local"
    ).strip() or "local"
    request["execution_target"] = execution_target
    target_payload = (
        payload.get("execution_target_payload")
        if isinstance(payload.get("execution_target_payload"), dict)
        else request.get("execution_target_payload")
        if isinstance(request.get("execution_target_payload"), dict)
        else session.get("execution_target_payload")
        if isinstance(session.get("execution_target_payload"), dict)
        else {}
    )
    if target_payload:
        request["execution_target_payload"] = dict(target_payload)
    return request


def _ollama_route_dampener(root: Path) -> RouteFlapDampener:
    return RouteFlapDampener(
        path=root / ".beast" / "agent_runs" / "ollama_route_damping.json",
        suppress_at=float(os.environ.get("BEAST_OLLAMA_ROUTE_SUPPRESS_AT", "400")),
        half_life_seconds=float(os.environ.get("BEAST_OLLAMA_ROUTE_HALF_LIFE_SECONDS", "1800")),
    )


def _nim_route_dampener(root: Path) -> RouteFlapDampener:
    return RouteFlapDampener(
        path=root / ".beast" / "agent_runs" / "nim_route_damping.json",
        suppress_at=float(os.environ.get("BEAST_NIM_ROUTE_SUPPRESS_AT", "400")),
        half_life_seconds=float(os.environ.get("BEAST_NIM_ROUTE_HALF_LIFE_SECONDS", "1800")),
    )


def _planner_quality_ledger(root: Path) -> ProviderQualityLedger:
    return ProviderQualityLedger(root)


def _semantic_hard_edit(run: dict[str, Any]) -> bool:
    request = run.get("request") if isinstance(run.get("request"), dict) else {}
    semantic_risk = request.get("semantic_risk") if isinstance(request.get("semantic_risk"), dict) else {}
    if bool(semantic_risk.get("high")):
        return True
    try:
        if float(semantic_risk.get("score") or 0.0) >= 4.0:
            return True
    except (TypeError, ValueError):
        pass
    return False


async def _execute_planner_run(
    root: Path,
    run_id: str,
    *,
    base_url: str,
    scripted_decisions: list[dict[str, Any]] | None = None,
    max_turns: int = 8,
    crystal_gateway: Any = None,
    context_packet_builder: Any = None,
    execution_gateway: Any = None,
    compute_governor: Any = None,
    pressure_controller: Any = None,
) -> None:
    engine = AgentRunEngine(root)
    run = engine.store.get_run(run_id)
    if not run:
        return
    if scripted_decisions is not None:
        provider = ScriptedPlannerProvider(scripted_decisions)
    elif _prefer_direct_ollama_planner(run):
        approvals = engine.store.list_approvals(run_id)
        resolved = [item for item in approvals if bool(item.get("resolved")) and bool(item.get("result", {}).get("approved"))]
        approval_id = str((resolved[-1] if resolved else {}).get("request_id") or "")
        route_dampener = _ollama_route_dampener(root)
        primary = OllamaPlannerProvider(
            model=str(run.get("model") or ""),
            base_url=base_url or None,
            default_approval_id=approval_id,
            engine=str((run.get("request") or {}).get("planner_engine") or os.environ.get("BEAST_PLANNER_ENGINE", "ollama")),
            llama_cpp_base_url=os.environ.get("LLAMA_CPP_BASE_URL"),
            crystal_gateway=crystal_gateway or CrystalReuseGateway(),
            execution_gateway=execution_gateway,
            compute_governor=compute_governor,
            pressure_controller=pressure_controller,
            forge_kv_manager=OllamaKVManager(ollama_url=base_url or "http://127.0.0.1:11434"),
            route_dampener=route_dampener,
            route_id=f"ollama:{str(run.get('model') or '').strip() or 'default'}",
            on_token=lambda text: engine.emit(run_id, "agent.model.delta", {"text": str(text)}),
            timeout_seconds=float(os.environ.get("BEAST_OLLAMA_PLANNER_TIMEOUT", "30")),
        )
        sticky_after = max(1, int(os.environ.get("BEAST_OLLAMA_STICKY_FAILOVER_AFTER", "2")))
        slow_ms = max(1000.0, float(os.environ.get("BEAST_OLLAMA_STICKY_SLOW_MS", "15000")))
        nim_enabled = os.environ.get("BEAST_NIM_FALLBACK", "0").strip().lower() in {"1", "true", "yes"}
        local_route = build_resilient_ollama_provider(
            primary=primary,
            nim_fallback_enabled=nim_enabled,
            nim_kwargs={
                "model": str(os.environ.get("BEAST_NIM_MODEL") or ""),
                "base_url": os.environ.get("NVIDIA_NIM_BASE_URL"),
                "on_token": lambda text: engine.emit(run_id, "agent.model.delta", {"text": str(text)}),
            },
            sticky_after=sticky_after,
            slow_ms=slow_ms,
            on_provider_fallback=lambda source, target, reason: engine.emit(run_id, "agent.provider.fallback", {"from": source, "to": target, "reason": reason}),
            on_sticky_fallback=lambda source, target, reason, observed_slow_ms: engine.emit(run_id, "agent.provider.sticky_fallback", {"from": source, "to": target, "reason": reason, "slow_ms": observed_slow_ms}),
        )
        nim_model = str(os.environ.get("BEAST_NIM_MODEL") or "").strip()
        nim_base_url = str(os.environ.get("NVIDIA_NIM_BASE_URL") or "").strip()
        if nim_model and nim_base_url:
            nim_primary = NIMPlannerProvider(
                model=nim_model,
                base_url=nim_base_url,
                route_dampener=_nim_route_dampener(root),
                route_id=f"nim:{nim_model}",
                on_token=lambda text: engine.emit(run_id, "agent.model.delta", {"text": str(text)}),
            )
            strong_route = build_resilient_nim_provider(
                primary=nim_primary,
                sticky_after=max(1, int(os.environ.get("BEAST_NIM_STICKY_FAILOVER_AFTER", "2"))),
                slow_ms=max(1000.0, float(os.environ.get("BEAST_NIM_STICKY_SLOW_MS", "15000"))),
                on_sticky_fallback=lambda source, target, reason, observed_slow_ms: engine.emit(run_id, "agent.provider.sticky_fallback", {"from": source, "to": target, "reason": reason, "slow_ms": observed_slow_ms}),
            )
            provider = CapabilityScoredPlannerProvider(
                [
                    {"name": "local-small", "provider": local_route, "capability_score": 0.34, "cost_score": 0.96},
                    {"name": "strong-cloud", "provider": strong_route, "capability_score": 0.95, "cost_score": 0.24},
                    {"name": "heuristic", "provider": HeuristicPlannerProvider(), "capability_score": 0.12, "cost_score": 0.99},
                ],
                hard_edit_threshold=float(os.environ.get("BEAST_AGENT_HARD_EDIT_THRESHOLD", "0.68")),
                quality_ledger=_planner_quality_ledger(root),
                on_switch=lambda old, new, reason: engine.emit(run_id, "agent.provider.switch", {
                    "from": old,
                    "to": new,
                    "reason": reason,
                    "task_type": ProviderQualityLedger.task_type(engine.store.get_run(run_id) or run),
                    "semantic_hard_edit": _semantic_hard_edit(engine.store.get_run(run_id) or run),
                }),
            )
        else:
            provider = local_route
    elif str(run.get("provider") or "").strip().lower() in {"nvidia_nim", "nim", "local_nim"}:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        route_dampener = _nim_route_dampener(root)
        primary = NIMPlannerProvider(
            model=str(run.get("model") or request.get("nim_model") or ""),
            base_url=str(request.get("nim_base_url") or os.environ.get("NVIDIA_NIM_BASE_URL") or ""),
            route_dampener=route_dampener,
            route_id=f"nim:{str(run.get('model') or request.get('nim_model') or '').strip() or 'default'}",
            on_token=lambda text: engine.emit(run_id, "agent.model.delta", {"text": str(text)}),
        )
        slow_ms = max(1000.0, float(os.environ.get("BEAST_NIM_STICKY_SLOW_MS", "15000")))
        provider = build_resilient_nim_provider(
            primary=primary,
            sticky_after=max(1, int(os.environ.get("BEAST_NIM_STICKY_FAILOVER_AFTER", "2"))),
            slow_ms=slow_ms,
            on_sticky_fallback=lambda source, target, reason, observed_slow_ms: engine.emit(run_id, "agent.provider.sticky_fallback", {"from": source, "to": target, "reason": reason, "slow_ms": observed_slow_ms}),
        )
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
    runtime = AgentPlannerRuntime(
        engine,
        provider,
        max_turns=max_turns,
        context_packet_builder=context_packet_builder,
        execution_gateway=execution_gateway,
        compute_governor=compute_governor,
    )
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
    crystal_gateway: Any = None,
    context_packet_builder: Any = None,
    execution_gateway: Any = None,
    compute_governor: Any = None,
    pressure_controller: Any = None,
) -> dict[str, Any]:
    existing = AGENT_RUN_WORKERS.get(run_id)
    handle = AGENT_RUN_WORKERS.launch(
        run_id,
        lambda: _execute_planner_run(
            root, run_id, base_url=base_url, scripted_decisions=scripted_decisions, max_turns=max_turns, crystal_gateway=crystal_gateway, context_packet_builder=context_packet_builder, execution_gateway=execution_gateway, compute_governor=compute_governor, pressure_controller=pressure_controller
        ),
    )
    return {
        "active": not handle.task.done(),
        "task_name": handle.task.get_name(),
        "reused": existing is not None,
        "engine": "typed_planner_v1",
    }


def _recoverable_restart_pause(run: dict[str, Any]) -> bool:
    state = normalize_state(str(run.get("state") or "created"))
    error = str(run.get("error") or "").strip().lower()
    return state == state.PAUSED and error == "runtime_restarted; resume required"


def _launch_for_run(
    app: Any,
    root: Path,
    run: dict[str, Any],
    *,
    ctx: IdeRouteContext,
    scripted_decisions: list[dict[str, Any]] | None = None,
    max_turns: int | None = None,
) -> dict[str, Any]:
    run_id = str(run.get("run_id") or "")
    request_payload = run.get("request") if isinstance(run.get("request"), dict) else {}
    if _prefer_direct_planner(run):
        planner_turns = max_turns if max_turns is not None else _planner_max_turns(run, request_payload)
        return _launch_planner(
            root,
            run_id,
            base_url=_ollama_base_url(run),
            scripted_decisions=scripted_decisions,
            max_turns=planner_turns,
            crystal_gateway=ctx.crystal_gateway,
            context_packet_builder=ctx.context_packet_builder,
            execution_gateway=ctx.execution_gateway,
            compute_governor=ctx.compute_governor,
            pressure_controller=ctx.pressure_controller,
        )
    return _launch(app, root, run_id)


def register_agent_runs_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _root = ctx._root
    _request_base_url = ctx._request_base_url

    def _root_candidates(*values: Any) -> list[Path]:
        candidates: list[Path] = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            candidate = _root(text)
            if candidate not in candidates:
                candidates.append(candidate)
        fallback = _root(None)
        if fallback not in candidates:
            candidates.append(fallback)
        return candidates

    def _payload_root(payload: dict[str, Any] | None) -> Path:
        payload = payload or {}
        return _root(payload.get("root_path") or payload.get("workspace_root"))

    def _request_prompt(payload: dict[str, Any] | None, request_payload: dict[str, Any] | None, session: dict[str, Any] | None) -> str:
        payload = payload or {}
        request_payload = request_payload or {}
        session = session or {}
        return str(
            payload.get("task")
            or payload.get("objective")
            or request_payload.get("prompt")
            or request_payload.get("task")
            or session.get("objective")
            or "BEAST agent run"
        )

    def _resolve_run_engine(run_id: str, *root_hints: Any) -> tuple[AgentRunEngine, dict[str, Any]]:
        for candidate in _root_candidates(*root_hints):
            engine = AgentRunEngine(candidate)
            run = engine.store.get_run(run_id)
            if run:
                return engine, run
        raise HTTPException(status_code=404, detail=f"unknown agent run: {run_id}")

    def _maybe_auto_recover(
        app: Any,
        engine: AgentRunEngine,
        run: dict[str, Any],
        *,
        auto_recover: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        current = run
        execution = AGENT_RUN_WORKERS.status(str(current.get("run_id") or ""))
        if execution.get("active") or not auto_recover or not _recoverable_restart_pause(current):
            return current, execution
        resumed = engine.resume(str(current.get("run_id") or ""))
        root = Path(str(resumed.get("root_path") or engine.workspace_root)).expanduser().resolve()
        execution = _launch_for_run(app, root, resumed, ctx=ctx)
        latest = engine.store.get_run(str(resumed.get("run_id") or "")) or resumed
        return latest, execution

    @router.post("/edgek/agent-runs")
    async def edgek_agent_run_create(request: Request, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _payload_root(payload)
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        session_result = AgentSessionStore(root).get(session_id)
        if not session_result.get("ok"):
            raise HTTPException(status_code=404, detail=str(session_result.get("error") or "unknown session"))
        session = session_result.get("session") if isinstance(session_result.get("session"), dict) else {}
        request_payload = _normalized_execution_request(payload, payload.get("request") if isinstance(payload.get("request"), dict) else {}, session)
        prompt = _request_prompt(payload, request_payload, session)
        if not str(request_payload.get("prompt") or "").strip():
            request_payload["prompt"] = prompt
        if not str(request_payload.get("workspace_root") or "").strip():
            request_payload["workspace_root"] = str(root)
        run = AgentRunEngine(root).create_run(
            session_id=session_id,
            objective=prompt,
            mode=str(payload.get("mode") or session.get("mode") or "agent"),
            provider=str(payload.get("provider") or session.get("provider") or ""),
            model=str(payload.get("model") or session.get("model") or ""),
            request=request_payload,
            budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else session.get("budget") if isinstance(session.get("budget"), dict) else {},
            run_id=str(payload.get("run_id") or ""),
        )
        if bool(payload.get("launch")):
            execution = _launch_for_run(request.app, root, run, ctx=ctx)
        else:
            execution = AGENT_RUN_WORKERS.status(str(run["run_id"]))
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
    async def edgek_agent_run_detail(run_id: str, request: Request, root_path: str = None, auto_recover: bool = Query(default=False)):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, execution = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        run["execution"] = execution
        return {"ok": True, "run": run}

    @router.get("/edgek/agent-runs/{run_id}/console")
    async def edgek_agent_run_console(run_id: str, request: Request, root_path: str = None, auto_recover: bool = Query(default=False)):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            snapshot = AgentOperationsConsoleViewModel(root).build(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "snapshot": snapshot}

    @router.get("/edgek/agent-runs/{run_id}/console/events")
    async def edgek_agent_run_console_events(
        run_id: str,
        root_path: str = None,
        cursor: str = "",
        limit: int = 100,
        view: str = "compact",
    ):
        try:
            page = DurableConsoleEventProjection(_root(root_path)).page(
                run_id, cursor=cursor, limit=limit, view=view
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "projection": page}

    @router.get("/edgek/agent-runs/{run_id}/mode")
    async def edgek_agent_run_mode(run_id: str, root_path: str = None):
        engine, run = _resolve_run_engine(run_id, root_path)
        workbench = WorkbenchModeEngine(Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve())
        return {"ok": True, "mode": str(run.get("mode") or "agent").upper(),
                "contract": workbench.contract(str(run.get("mode") or "agent")),
                "history": workbench.history(run_id)}

    @router.post("/edgek/agent-runs/{run_id}/mode")
    async def edgek_agent_run_mode_transition(run_id: str, payload: dict[str, Any], root_path: str = None):
        try:
            receipt = WorkbenchModeEngine(_root(root_path)).transition(
                run_id, str(payload.get("to_mode") or ""),
                operator_id=str(payload.get("operator_id") or ""),
                reason=str(payload.get("reason") or ""),
                conversion_confirmed=bool(payload.get("conversion_confirmed", False)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "transition": receipt}

    @router.get("/edgek/agent-runs/{run_id}/objective-plan")
    async def edgek_agent_run_objective_plan(run_id: str, request: Request, root_path: str = None, auto_recover: bool = Query(default=False)):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            workspace = ObjectivePlanWorkspace(root)
            return {"ok": True, "workspace": workspace.current(run_id), "history": workspace.history(run_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/agent-runs/{run_id}/objective-plan")
    async def edgek_agent_run_objective_plan_revise(run_id: str, payload: dict[str, Any], root_path: str = None):
        try:
            receipt = ObjectivePlanWorkspace(_root(root_path)).revise(
                run_id,
                objective=str(payload.get("objective") or ""),
                success_criteria=payload.get("success_criteria") or [],
                steps=payload.get("steps") or [],
                active_step_id=str(payload.get("active_step_id") or ""),
                operator_id=str(payload.get("operator_id") or ""),
                reason=str(payload.get("reason") or ""),
                expansion_confirmed=bool(payload.get("expansion_confirmed", False)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "revision": receipt}

    @router.post("/edgek/agent-runs/{run_id}/objective-plan/advance")
    async def edgek_agent_run_objective_plan_advance(run_id: str, payload: dict[str, Any], root_path: str = None):
        try:
            receipt = ObjectivePlanWorkspace(_root(root_path)).advance(
                run_id,
                completed_step_id=str(payload.get("completed_step_id") or ""),
                next_step_id=str(payload.get("next_step_id") or ""),
                operator_id=str(payload.get("operator_id") or ""),
                reason=str(payload.get("reason") or ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "revision": receipt}


    @router.get("/edgek/agent-runs/{run_id}/console/timeline")
    async def edgek_agent_run_timeline_console(
        run_id: str,
        request: Request,
        root_path: str = None,
        cursor: str = "",
        limit: int = 100,
        categories: str = "",
        severities: str = "",
        step_id: str = "",
        query: str = "",
        view: str = "expanded",
        auto_recover: bool = Query(default=False),
    ):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            timeline = LiveRunTimelineConsole(root).build(
                run_id, cursor=cursor, limit=limit, categories=categories,
                severities=severities, step_id=step_id, query=query, view=view,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "timeline_console": timeline}

    @router.get("/edgek/agent-runs/{run_id}/console/tool-approvals")
    async def edgek_agent_run_tool_approval_cards(run_id: str, request: Request, root_path: str = None, status: str = "", query: str = "", limit: int = 200, auto_recover: bool = Query(default=False)):
        from app.kernel.operations_console.tool_approval_console import ToolApprovalCardsConsole
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            return ToolApprovalCardsConsole(root).build(run_id, status=status, query=query, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.get("/edgek/agent-runs/{run_id}/console/worktree")
    async def edgek_agent_run_worktree_console(run_id: str, request: Request, root_path: str = None, path: str = "", query: str = "", change_type: str = "", max_diff_chars: int = 120000, auto_recover: bool = Query(default=False)):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            return WorktreeChangesDiffConsole(root).build(run_id, path=path, query=query, change_type=change_type, max_diff_chars=max_diff_chars)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.get("/edgek/agent-runs/{run_id}/console/verification")
    async def edgek_agent_run_verification_console(
        run_id: str,
        request: Request,
        root_path: str = None,
        category: str = "",
        status: str = "",
        query: str = "",
        limit: int = 250,
        auto_recover: bool = Query(default=False),
    ):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            return VerificationConsole(root).build(
                run_id, category=category, status=status, query=query, limit=limit
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.get("/edgek/agent-runs/{run_id}/console/context")
    async def edgek_agent_run_context_console(
        run_id: str,
        request: Request,
        root_path: str = None,
        status: str = "",
        privacy: str = "",
        visibility: str = "",
        query: str = "",
        auto_recover: bool = Query(default=False),
    ):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            projection = ContextManifestConsole(root).build(
                run_id,
                status=status,
                privacy=privacy,
                visibility=visibility,
                query=query,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "context_console": projection}

    @router.get("/edgek/agent-runs/{run_id}/context-manifest")
    async def edgek_agent_run_context_manifest(run_id: str, request: Request, root_path: str = None, auto_recover: bool = Query(default=False)):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        try:
            return {"ok": True, "manifest": ContextManifestStore(root).manifest(run_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/agent-runs/{run_id}/context-manifest/items")
    async def edgek_agent_run_context_add(run_id: str, payload: dict[str, Any], root_path: str = None):
        try:
            item = ContextManifestStore(_root(root_path)).add_item(run_id, source=str(payload.get("source") or ""), path=str(payload.get("path") or ""), start_line=int(payload.get("start_line") or 0), end_line=int(payload.get("end_line") or 0), content=payload.get("content"), content_hash=str(payload.get("content_hash") or ""), retrieval_reasons=payload.get("retrieval_reasons") or [], selection_origin=str(payload.get("selection_origin") or "suggested"), token_estimate=int(payload.get("token_estimate") or 0), privacy_level=str(payload.get("privacy_level") or "INTERNAL"), provider_visibility=str(payload.get("provider_visibility") or "LOCAL_ONLY"), item_id=str(payload.get("item_id") or ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/edgek/agent-runs/{run_id}/context-manifest/items/{item_id}/decision")
    async def edgek_agent_run_context_decide(run_id: str, item_id: str, payload: dict[str, Any], root_path: str = None):
        try:
            item = ContextManifestStore(_root(root_path)).decide(run_id, item_id, decision=str(payload.get("decision") or ""), operator_id=str(payload.get("operator_id") or ""), reason=str(payload.get("reason") or ""), provider=str(payload.get("provider") or ""), redaction_digest=str(payload.get("redaction_digest") or ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.get("/edgek/agent-runs/{run_id}/events")
    async def edgek_agent_run_events(
        request: Request,
        run_id: str,
        root_path: str = None,
        after: int = 0,
        limit: int = 250,
        follow: bool = Query(default=False),
        projection: str = Query(default="canonical", pattern="^(canonical|legacy)$"),
        auto_recover: bool = Query(default=False),
    ):
        engine, _ = _resolve_run_engine(run_id, root_path, request.query_params.get("workspace_root"))
        run = engine.store.get_run(run_id) or {}
        run, _ = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
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
        engine, _ = _resolve_run_engine(run_id, root_path)
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
        engine, _ = _resolve_run_engine(run_id, payload.get("root_path"), payload.get("workspace_root"))
        try:
            observation = await engine.execute_tool(
                run_id,
                tool_id,
                payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
                execution_target=str(payload.get("execution_target") or "local"),
                execution_target_payload=payload.get("execution_target_payload") if isinstance(payload.get("execution_target_payload"), dict) else {},
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
        engine, run = _resolve_run_engine(run_id, payload.get("root_path"), payload.get("workspace_root"))
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        if normalize_state(str(run.get("state") or "created")) in TERMINAL_STATES:
            raise HTTPException(status_code=409, detail="terminal runs cannot be relaunched")
        scripted = payload.get("simulate_decisions")
        if scripted is not None and not isinstance(scripted, list):
            raise HTTPException(status_code=400, detail="simulate_decisions must be a list")
        max_turns = max(1, min(int(payload.get("max_turns") or 8), 64))
        base_url = _ollama_base_url(run)
        execution = _launch_planner(
            root, run_id, base_url=base_url, scripted_decisions=scripted, max_turns=max_turns, crystal_gateway=ctx.crystal_gateway, context_packet_builder=ctx.context_packet_builder, execution_gateway=ctx.execution_gateway, compute_governor=ctx.compute_governor, pressure_controller=ctx.pressure_controller
        )
        return {"ok": True, "run": engine.store.get_run(run_id), "execution": execution}

    @router.get("/edgek/agent-runs/{run_id}/planner")
    async def edgek_agent_run_planner_state(run_id: str, request: Request, root_path: str = None, auto_recover: bool = Query(default=False)):
        engine, run = _resolve_run_engine(run_id, root_path)
        run, execution = _maybe_auto_recover(request.app, engine, run, auto_recover=auto_recover)
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        return {
            "beast_object_type": "beast_agent_planner_state",
            "version": "1.0",
            "ok": True,
            "run_id": run_id,
            "planner": checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {},
            "execution": execution,
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

    @router.post("/edgek/agent-runs/{run_id}/promotion/final-apply/evaluate")
    async def edgek_agent_run_promotion_final_apply_evaluate(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return PromotionEngine(_root(payload.get("root_path"))).evaluate_final_apply(
                run_id, requested_by=str(payload.get("requested_by") or "operator")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/edgek/agent-runs/{run_id}/promotion/final-apply")
    async def edgek_agent_run_promotion_final_apply(run_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        approval_id = str(payload.get("approval_id") or "")
        if not approval_id:
            raise HTTPException(status_code=400, detail="approval_id is required")
        try:
            return PromotionEngine(_root(payload.get("root_path"))).finalize(
                run_id,
                approval_id=approval_id,
                target_branch=str(payload.get("target_branch") or ""),
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


    @router.get("/edgek/evidence/{evidence_id}/fingerprint")
    async def edgek_evidence_fingerprint(evidence_id: str, root_path: str = None):
        store = FingerprintStore(_root(root_path))
        bundle = store.get(evidence_id)
        if not bundle:
            raise HTTPException(status_code=404, detail=f"unknown evidence fingerprint: {evidence_id}")
        return {"ok": True, "evidence_id": evidence_id, "fingerprint": bundle}

    @router.get("/edgek/evidence/{evidence_id}/fingerprint/verify")
    async def edgek_evidence_fingerprint_verify(evidence_id: str, root_path: str = None):
        try:
            return FingerprintStore(_root(root_path)).verify(evidence_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/evidence/fingerprints/compare")
    async def edgek_evidence_fingerprint_compare(payload: dict[str, Any] = None):
        payload = payload or {}
        left_id = str(payload.get("left_evidence_id") or "")
        right_id = str(payload.get("right_evidence_id") or "")
        if not left_id or not right_id:
            raise HTTPException(status_code=400, detail="left_evidence_id and right_evidence_id are required")
        store = FingerprintStore(_root(payload.get("root_path")))
        left = store.get(left_id)
        right = store.get(right_id)
        if not left or not right:
            raise HTTPException(status_code=404, detail="one or both evidence fingerprints do not exist")
        return {"ok": True, "left_evidence_id": left_id, "right_evidence_id": right_id, "comparison": compare_fingerprints(left, right)}

    @router.post("/edgek/evidence/search")
    async def edgek_evidence_search(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return EvidenceRetriever(_root(payload.get("root_path"))).search(
                payload,
                limit=int(payload.get("limit") or 10),
                minimum_score=float(payload.get("minimum_score") or 0.0),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/compatibility/evaluate")
    async def edgek_evidence_compatibility_evaluate(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return CompatibilityEngine(_root(payload.get("root_path"))).evaluate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/reuse/verify")
    async def edgek_evidence_reuse_verify(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return FreshVerificationEquivalenceEngine().evaluate(
                reuse_receipt=payload.get("reuse_receipt") or {},
                verification_receipt=payload.get("verification_receipt") or {},
                observed_outcome=payload.get("observed_outcome") or {},
                policy_controls=payload.get("policy_controls"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/reuse/sourceplan-handoff")
    async def edgek_evidence_reuse_sourceplan_handoff(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return SourcePlanReuseHandoffEngine().prepare(
                outcome_receipt=payload.get("outcome_receipt") or {},
                sourceplan=payload.get("sourceplan") or {},
                policy_controls=payload.get("policy_controls"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/reuse/operator-review")
    async def edgek_evidence_reuse_operator_review(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return OperatorReviewApprovalEngine().resolve(
                handoff_receipt=payload.get("handoff_receipt") or {},
                operator_decision=payload.get("operator_decision") or {},
                policy_controls=payload.get("policy_controls"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/reuse/sourceplan-apply")
    async def edgek_evidence_reuse_sourceplan_apply(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return OneUseSourcePlanApplyEngine().execute(
                approval_receipt=payload.get("approval_receipt") or {}, sourceplan=payload.get("sourceplan") or {},
                workspace_root=str(payload.get("root_path") or root), ledger_path=payload.get("ledger_path"),
                policy_controls=payload.get("policy_controls"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/reuse/post-apply-verify")
    async def edgek_evidence_reuse_post_apply_verify(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return PostApplyVerificationPromotionGate().evaluate(
                consumption_receipt=payload.get("consumption_receipt") or {},
                verification_receipt=payload.get("verification_receipt") or {},
                applied_state=payload.get("applied_state") or {},
                rollback_receipt=payload.get("rollback_receipt"),
                policy_controls=payload.get("policy_controls"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @router.post("/edgek/evidence/reuse/promote")
    async def edgek_evidence_reuse_promote(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return PromotionExecutionRollbackClosure().execute(
                eligibility_receipt=payload.get("eligibility_receipt") or {},
                promotion_authorization=payload.get("promotion_authorization") or {},
                worktree_root=str(payload.get("worktree_root") or ""),
                operator_workspace_root=str(payload.get("operator_workspace_root") or ""),
                applied_state=payload.get("applied_state") or {},
                operator_workspace_clean=bool(payload.get("operator_workspace_clean", False)),
                policy_controls=payload.get("policy_controls"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/edgek/evidence/{evidence_id}/ledger")
    async def edgek_evidence_ledger(evidence_id: str, root_path: str = None, after: int = 0, limit: int = 500):
        ledger = EvidenceLedger(_root(root_path))
        try:
            return {"ok": True, "state": ledger.state(evidence_id), "events": ledger.events(evidence_id, after=after, limit=limit)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/edgek/evidence/{evidence_id}/ledger/verify")
    async def edgek_evidence_ledger_verify(evidence_id: str, root_path: str = None):
        try:
            return EvidenceLedger(_root(root_path)).verify(evidence_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/evidence/{evidence_id}/usage")
    async def edgek_evidence_usage(evidence_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            event = EvidenceLedger(_root(payload.get("root_path"))).record_use(
                evidence_id,
                run_id=str(payload.get("run_id") or ""),
                outcome=str(payload.get("outcome") or "adopted"),
                actor=str(payload.get("actor") or "beast-runtime"),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
            return {"ok": True, "event": event}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/edgek/evidence/{evidence_id}/revoke")
    async def edgek_evidence_revoke(evidence_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            event = EvidenceLedger(_root(payload.get("root_path"))).revoke(
                evidence_id,
                reason=str(payload.get("reason") or ""),
                actor=str(payload.get("actor") or ""),
            )
            return {"ok": True, "event": event}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/edgek/evidence/{evidence_id}/supersede")
    async def edgek_evidence_supersede(evidence_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            event = EvidenceLedger(_root(payload.get("root_path"))).supersede(
                evidence_id,
                successor_evidence_id=str(payload.get("successor_evidence_id") or ""),
                reason=str(payload.get("reason") or ""),
                actor=str(payload.get("actor") or ""),
            )
            return {"ok": True, "event": event}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/edgek/evidence/{evidence_id}/metrics")
    async def edgek_evidence_metric(evidence_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            event = EvidenceLedger(_root(payload.get("root_path"))).record_metric(
                evidence_id,
                name=str(payload.get("name") or ""),
                value=float(payload.get("value")),
                unit=str(payload.get("unit") or ""),
                actor=str(payload.get("actor") or "beast-runtime"),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
            return {"ok": True, "event": event}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        engine, _ = _resolve_run_engine(run_id, payload.get("root_path"), payload.get("workspace_root"))
        try:
            run = engine.resume(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        root = Path(str(run.get("root_path") or engine.workspace_root)).expanduser().resolve()
        execution = _launch_for_run(request.app, root, run, ctx=ctx)
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

    @router.post("/edgek/evidence/reuse/phase3-close")
    async def edgek_evidence_phase3_close(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return Phase3EndToEndProofClosure().close(
                root_path=_root(payload.get("root_path")),
                phase_evidence=payload.get("phase_evidence") or {},
                receipt_chain=payload.get("receipt_chain") or {},
                regression_report=payload.get("regression_report") or {},
                policy_controls=payload.get("policy_controls"),
                output_directory=payload.get("output_directory"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/edgek/approvals/contracts/request")
    async def edgek_approval_contract_request(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return ApprovalContractFactory().create_request(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/edgek/approvals")
    async def edgek_approval_create(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            request = ApprovalContractFactory().create_request(payload.get("request") or payload)
            return DurableApprovalStore(_root(payload.get("root_path"))).create(request)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/edgek/approvals")
    async def edgek_approval_list(root_path: str = None, run_id: str = None, state: str = None, limit: int = 100):
        return {"ok": True, "approvals": DurableApprovalStore(_root(root_path)).list(run_id=run_id, state=state, limit=limit)}

    @router.get("/edgek/approvals/{approval_id}")
    async def edgek_approval_get(approval_id: str, root_path: str = None):
        try:
            store = DurableApprovalStore(_root(root_path))
            return {"ok": True, "approval": store.get(approval_id), "chain": store.verify_chain(approval_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/approvals/recover")
    async def edgek_approval_recover(payload: dict[str, Any] = None):
        payload = payload or {}
        return ApprovalRecoveryService(_root(payload.get("root_path"))).recover()

    @router.post("/edgek/approvals/classify")
    async def edgek_approval_classify(payload: dict[str, Any] = None):
        payload = payload or {}
        action = payload.get("action") if isinstance(payload.get("action"), dict) else payload
        policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        try:
            policy = policy_from_payload(policy_payload)
            classification = ApprovalRiskClassifier().classify(action, policy=policy)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "classification": classification}

    @router.post("/edgek/approvals/capabilities/issue")
    async def edgek_approval_capability_issue(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            capability = RequestBoundCapabilityIssuer().issue(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "capability": capability}

    @router.post("/edgek/approvals/capabilities/consume-resume")
    async def edgek_approval_capability_consume_resume(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        try:
            receipt = ExactStepResumeRuntime(root).consume_and_resume(
                capability=payload.get("capability") or {},
                request=payload.get("request") or {},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "ok": True,
            "receipt": receipt,
            "run": AgentRunEngine(root).store.get_run(str(receipt.get("run_id") or "")),
        }

    @router.get("/edgek/approvals/modes/{mode}")
    async def edgek_approval_permission_mode_profile(mode: str):
        try:
            return {"ok": True, "profile": PermissionModeEngine().profile(mode)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/edgek/approvals/modes/evaluate")
    async def edgek_approval_permission_mode_evaluate(payload: dict[str, Any] = None):
        payload = payload or {}
        action = payload.get("action") if isinstance(payload.get("action"), dict) else payload
        policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        try:
            decision = PermissionModeEngine().evaluate(
                action, policy=policy_from_payload(policy_payload)
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "decision": decision}

    @router.post("/edgek/approvals/sensitive/classify")
    async def edgek_approval_sensitive_classify(payload: dict[str, Any] = None):
        payload = payload or {}
        subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else payload
        policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        try:
            receipt = SensitiveDataController().classify(
                subject, policy=policy_from_sensitive_payload(policy_payload)
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "classification": receipt}

    @router.post("/edgek/approvals/sensitive/redact")
    async def edgek_approval_sensitive_redact(payload: dict[str, Any] = None):
        payload = payload or {}
        policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        try:
            receipt = SensitiveDataController().redact(
                payload.get("payload"),
                surface=str(payload.get("surface") or "model"),
                policy=policy_from_sensitive_payload(policy_payload),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "redaction": receipt}

    @router.post("/edgek/approvals/external/classify")
    async def edgek_approval_external_classify(payload: dict[str, Any] = None):
        payload = payload or {}
        subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else payload
        policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        try:
            receipt = ExternalContentAdmissionController().classify(
                subject, policy=policy_from_external_payload(policy_payload)
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "classification": receipt}

    @router.post("/edgek/approvals/external/admit")
    async def edgek_approval_external_admit(payload: dict[str, Any] = None):
        payload = payload or {}
        policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        try:
            receipt = ExternalContentAdmissionController().admit(
                payload.get("subject") if isinstance(payload.get("subject"), dict) else payload,
                classification=payload.get("classification") or {},
                operator_decision=payload.get("operator_decision") if isinstance(payload.get("operator_decision"), dict) else None,
                policy=policy_from_external_payload(policy_payload),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "admission": receipt}

    @router.post("/edgek/approvals/scopes/grant")
    async def edgek_approval_scope_grant(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            grant = ApprovalScopeEngine().create_grant(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "grant": grant}

    @router.post("/edgek/approvals/scopes/evaluate")
    async def edgek_approval_scope_evaluate(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            receipt = ApprovalScopeEngine().evaluate(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "scope_match": receipt}

    @router.post("/edgek/approvals/envelope")
    async def edgek_approval_envelope(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            envelope = RichApprovalEnvelopeBuilder().build(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "envelope": envelope}


    @router.post("/edgek/approvals/cards")
    async def edgek_approval_card_create(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            card = DurableApprovalCardStore(_root(payload.get("root_path"))).create(payload.get("envelope") or {})
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "card": card}

    @router.get("/edgek/approvals/cards/{approval_id}")
    async def edgek_approval_card_get(approval_id: str, root_path: str = None):
        store = DurableApprovalCardStore(_root(root_path))
        try:
            return {"ok": True, "card": store.get(approval_id), "chain": store.verify_chain(approval_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/edgek/approvals/cards/{approval_id}/decision")
    async def edgek_approval_card_decide(approval_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            card = DurableApprovalCardStore(_root(payload.get("root_path"))).decide(approval_id, payload.get("decision") or payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "card": card}

    @router.post("/edgek/approvals/cards/recover")
    async def edgek_approval_card_recover(payload: dict[str, Any] = None):
        payload = payload or {}
        return DurableApprovalCardStore(_root(payload.get("root_path"))).recover()

    @router.post("/edgek/approvals/admin/revoke")
    async def edgek_approval_admin_revoke(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            record = RevocationPolicyStore(_root(payload.get("root_path"))).revoke(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "revocation": record}

    @router.post("/edgek/approvals/admin/check")
    async def edgek_approval_admin_check(payload: dict[str, Any] = None):
        payload = payload or {}
        return {"ok": True, "check": RevocationPolicyStore(_root(payload.get("root_path"))).check(payload.get("artifact") or {})}

    @router.post("/edgek/approvals/admin/policies")
    async def edgek_approval_admin_policy_create(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            record = RevocationPolicyStore(_root(payload.get("root_path"))).create_policy_generation(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "policy_generation": record}

    @router.post("/edgek/approvals/admin/policies/{generation_id}/activate")
    async def edgek_approval_admin_policy_activate(generation_id: str, payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            record = RevocationPolicyStore(_root(payload.get("root_path"))).activate_policy_generation(
                generation_id, operator_id=str(payload.get("operator_id") or ""), reason=str(payload.get("reason") or "")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "policy_generation": record}

    @router.get("/edgek/approvals/admin/policies/current")
    async def edgek_approval_admin_policy_current(root_path: str = None):
        return {"ok": True, "policy_generation": RevocationPolicyStore(_root(root_path)).current_policy_generation()}

    @router.post("/edgek/approvals/closure/phase4")
    async def edgek_approval_phase4_closure(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            receipt = Phase4EndToEndClosure(_root(payload.get("root_path"))).close(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "closure": receipt}

    @router.post("/edgek/approvals/contracts/decision")
    async def edgek_approval_contract_decision(payload: dict[str, Any] = None):
        payload = payload or {}
        try:
            return ApprovalContractFactory().create_decision(
                payload.get("request") or {}, payload.get("decision") or {}
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return None
