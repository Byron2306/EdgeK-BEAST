"""Agent Run Stream routes for the BEAST IDE facade."""

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
from app.kernel.agents.run_engine import AgentRunCancelled, AgentRunEngine
from app.kernel.agents.run_state import AgentRunState, normalize_state
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


def register_agent_run_stream_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _action_ir_anchor_hints = ctx._action_ir_anchor_hints
    _action_ir_retry_prompt = ctx._action_ir_retry_prompt
    _compile_agent_action_ir_sourceplan = ctx._compile_agent_action_ir_sourceplan
    _event = ctx._event
    _request_base_url = ctx._request_base_url
    _root = ctx._root
    _sanitize_model_history = ctx._sanitize_model_history
    _skill_recipe_suggestions = ctx._skill_recipe_suggestions
    _tool_call_event = ctx._tool_call_event
    _tool_event = ctx._tool_event
    _validate_agent_sourceplan = ctx._validate_agent_sourceplan
    code_cortex_router = ctx.code_cortex_router

    @router.get("/edgek/ide/agent-sessions/{session_id}/run-events")
    async def edgek_ide_agent_session_run_events(
        request: Request,
        session_id: str,
        root_path: str = None,
        prompt: str = "",
        provider: str = "",
        model: str = "",
        context_files: List[str] | None = Query(default=None),
        run_id: str = "",
        simulate: bool = False,
        max_tokens: int = 2000,
        context_max_chars_each: int = 30000,
        max_repair_rounds: int = 3,
    ):
        run_runtime: dict[str, Any] = {"engine": None, "run_id": str(run_id or "")}

        async def _stream_repair_action_ir(
            client: BeastApiClient,
            *,
            objective: str,
            previous_output: str,
            provider_id: str,
            model_id: str,
            files: list[str],
            max_output_tokens: int,
            max_context_chars: int,
            diagnostics: str = "",
            root_path: Path | None = None,
            expected_handoff_hash: str = "",
            schema_recovery: bool = False,
        ) -> tuple[str, list[str]]:
            repair_prompt = _action_ir_retry_prompt(objective, previous_output, files, diagnostics, root_path)
            if schema_recovery:
                # A model that just produced prose instead of a structured
                # packet should not be given the same broad, competing task
                # again.  Recover one exact, reviewable edit from the primary
                # file; the normal resolver still validates it against the
                # complete operator-approved scope before it is shown.
                repair_prompt = (
                    "Return exactly one BEAST Action IR JSON object and nothing else. "
                    "Make one real replace_exact edit in the single attached file. "
                    "Use an exact old snippet from that file and a complete replacement.\n\n"
                    + _action_ir_retry_prompt(
                        objective,
                        str(previous_output or "")[:3200],
                        files[:1],
                        diagnostics,
                        root_path,
                    )
                )
            if expected_handoff_hash:
                repair_prompt += (
                    "\n\nThis repair remains bound to the original provider contract. "
                    "Set top-level provider_handoff_hash to exactly: "
                    f"{expected_handoff_hash}"
                )
            repair_parts: list[str] = []
            repair_tools: list[str] = []
            repair_options = {
                "provider": provider_id,
                "model": model_id,
                "context_files": files,
                "max_tokens": max(256, min(int(max_output_tokens), 2400)),
                "context_max_chars_each": max(1200, min(int(max_context_chars), 60000)),
                "governance_level": "ide_agent_session_action_ir_repair",
            }
            if "allow_fallback" in inspect.signature(client.stream_live_turn).parameters:
                repair_options["allow_fallback"] = False
            async for event in client.stream_live_turn(repair_prompt, [], **repair_options):
                event_type = str(event.get("type") or "event")
                if event_type == "token":
                    repair_parts.append(str(event.get("text") or ""))
                elif event_type == "tool":
                    repair_tools.append(str(event.get("text") or ""))
            return "".join(repair_parts), repair_tools

        async def _generate_agent_run_events():
            root = _root(root_path)
            store = AgentSessionStore(root)
            detail = store.get(session_id)
            if not detail.get("ok"):
                yield _event("agent_run_error", {"ok": False, "error": detail.get("error") or "unknown session"})
                yield _event("agent_run_done", {
                    "ok": False,
                    "session_id": session_id,
                    "chars": 0,
                    "sourceplan_status": "session_error",
                    "session": {},
                })
                return
            session = detail.get("session") if isinstance(detail.get("session"), dict) else {}
            session_mode = str(session.get("mode") or "").strip().lower()
            # Agent mode has two lanes. Implementation sessions produce
            # governed Action IR. Analysis sessions still inspect the bounded
            # workspace and emit tool turns, but they answer in prose instead
            # of forcing every "look over this file" request into SourcePlan
            # recovery.
            is_planning_agent = False
            is_chat_session = session_mode in {"chat", "analysis", "analyze"}
            run_prompt = (prompt or session.get("objective") or "Continue this BEAST agent session.").strip()
            run_provider = provider or str(session.get("provider") or "nvidia_nim")
            run_model = model or str(session.get("model") or "meta/llama-3.1-8b-instruct")
            run_max_tokens, context_char_limit, context_file_limit = _pair_programmer_limits(
                run_provider, run_model, max_tokens, context_max_chars_each
            )
            compact_local_coder = _is_compact_local_coder(run_provider, run_model)
            engine = AgentRunEngine(root)
            durable_run = engine.ensure_run(
                run_id=str(run_runtime.get("run_id") or ""),
                session_id=session_id,
                objective=run_prompt,
                mode=session_mode or "agent",
                provider=run_provider,
                model=run_model,
                request={
                    "transport": "legacy_pair_programmer_sse",
                    "context_files": [str(item) for item in (context_files or [])],
                    "simulate": bool(simulate),
                    "max_tokens": int(run_max_tokens),
                    "context_max_chars_each": int(context_char_limit),
                    "max_repair_rounds": int(max_repair_rounds),
                },
                budget=session.get("budget") if isinstance(session.get("budget"), dict) else {},
            )
            durable_run_id = str(durable_run.get("run_id") or "")
            run_runtime.update({"engine": engine, "run_id": durable_run_id})
            engine.attach_current_task(durable_run_id)
            current_state = normalize_state(str(durable_run.get("state") or "created"))
            if current_state == AgentRunState.CREATED:
                engine.store.transition(durable_run_id, AgentRunState.SCOPING)
            engine.raise_if_cancelled(durable_run_id)
            yield _event("agent_run_registered", {
                "ok": True,
                "session_id": session_id,
                "run_id": durable_run_id,
                "state": str((engine.store.get_run(durable_run_id) or {}).get("state") or "scoping"),
            })
            session_files = [str(item) for item in (session.get("files") or [])]
            session_tools = {str(item) for item in (session.get("tools") or [])}
            request_files = [str(item) for item in (context_files or [])]
            # An incoming request is the current operator-approved scope. Do
            # not append stale session files (often prior retrieval results).
            # Explicit UI attachments remain the baseline.  A previously
            # approved linked-file capability may extend that baseline on a
            # later turn, but only with paths persisted in the session grant.
            if request_files and "granted:read_related_files" in session_tools:
                selected_context = list(dict.fromkeys([*request_files, *session_files]))
            else:
                selected_context = list(dict.fromkeys(request_files if request_files else session_files))
            # The request context is an explicit operator boundary. Code
            # Cortex may recommend files through its dedicated UI workflow,
            # but the Pair Programmer must never silently read and attach
            # additional repository files for a provider turn—especially not
            # after the operator deliberately narrowed the visible scope.
            discovered_context: list[str] = []
            context_file_list = selected_context[:context_file_limit]
            # Flush an immediate event before any filesystem/index work so
            # the desktop never appears frozen while the agent prepares its
            # bounded read-only observation pass.
            yield _event("agent_run_stage", {
                "session_id": session_id,
                "text": f"preparing bounded repository context ({len(context_file_list)} file(s))",
            })
            await asyncio.sleep(0)
            # A selected path is not context until it has been read from this
            # exact workspace root.  Previously the UI reported the path as
            # "locked" before the provider client attempted the read, which
            # let an unreadable attachment masquerade as model context.
            client = BeastApiClient(_request_base_url(request), workspace=root)
            context_records = client.read_context_files(
                context_file_list,
                max_files=context_file_limit,
                max_chars_each=context_char_limit,
            )
            readable_context = [str(record.get("path") or "") for record in context_records if record.get("ok")]
            unreadable_context = [
                {"path": str(record.get("path") or ""), "error": str(record.get("error") or "unreadable")}
                for record in context_records if not record.get("ok")
            ]
            unreadable_requested = [
                item for item in unreadable_context if item["path"] in set(request_files)
            ]
            context_file_list = readable_context
            conversation_history = _sanitize_model_history(
                store.conversation_history(session_id, limit=3 if compact_local_coder else 12)
            )
            store.update(session_id, output={
                "kind": "agent_user_prompt",
                "text": run_prompt,
                "provider": run_provider,
                "model": run_model,
                "context_files": context_file_list,
            })
            store.update(session_id, status="running", files=context_file_list, output={
                "kind": "agent_run_started",
                "text": f"Run started: {run_prompt[:500]}",
                "provider": run_provider,
                "model": run_model,
            })
            yield _event("agent_run_started", {
                "ok": True,
                "session_id": session_id,
                "run_id": durable_run_id,
                "provider": run_provider,
                "model": run_model,
                "prompt": run_prompt,
                "simulate": bool(simulate),
            })
            if compact_local_coder:
                yield _event("agent_run_stage", {
                    "session_id": session_id,
                    "text": f"compact local Qwen route: {len(context_file_list)} files, {run_max_tokens} output tokens",
                })
            if len(context_file_list) > len(selected_context):
                yield _event("agent_run_stage", {
                    "session_id": session_id,
                    "text": f"repository context expanded: {len(selected_context)} selected → {len(context_file_list)} files",
                })
            yield _event("agent_run_context", {
                "ok": bool(context_file_list) or not request_files,
                "session_id": session_id,
                "files": context_file_list,
                "requested_files": request_files,
                "unreadable_files": unreadable_context,
                "content_loaded": bool(context_file_list),
                "active_file": request_files[0] if request_files else (context_file_list[0] if context_file_list else ""),
                "file_count": len(context_file_list),
            })
            if unreadable_requested:
                detail = "; ".join(f"{item['path']}: {item['error']}" for item in unreadable_requested[:4])
                failure = f"Attached context could not be read from the active workspace: {detail}"
                store.update(session_id, status="active", output={
                    "kind": "agent_context_error",
                    "text": failure,
                    "provider": run_provider,
                    "model": run_model,
                    "context_files": context_file_list,
                })
                yield _event("agent_run_error", {"session_id": session_id, "ok": False, "error": failure})
                yield _event("agent_run_done", {
                    "ok": False,
                    "session_id": session_id,
                    "chars": 0,
                    "sourceplan_status": "context_error",
                    "session": {"output": {"kind": "agent_context_error", "text": failure}},
                })
                return
            # Observe before planning.  This is a governed, read-only tool
            # pass, not a guess based solely on a truncated editor buffer.
            # The resulting map gives the provider symbols, imports, routes,
            # and direct dependents while the selected files remain the only
            # files it may edit.
            agent_observation: dict[str, Any] = {}
            # Observation events are emitted before provider dispatch. Keep
            # their durable tool trace available for both the successful and
            # deferred observation paths.
            tool_events: list[str] = []
            granted_capabilities = {
                item.removeprefix("granted:")
                for item in session_tools
                if item.startswith("granted:")
            }
            if context_file_list:
                yield _event("agent_run_stage", {"session_id": session_id, "text": "repository observation"})
                try:
                    yield _event("agent_run_tool", _tool_call_event(
                        session_id,
                        tool="Code Cortex",
                        text=f"Inspecting {len(context_file_list[:3])} selected file(s) and their direct dependents.",
                        phase="repository_observation",
                        parameters={"files": context_file_list[:3]},
                    ))

                    def _observe_selected_scope() -> dict[str, Any]:
                        summaries: list[dict[str, Any]] = []
                        dependents: dict[str, list[str]] = {}
                        for path in context_file_list[:3]:
                            summary = code_cortex_router.get_file_summary(root, path)
                            data = summary.get("summary") if isinstance(summary.get("summary"), dict) else {}
                            summaries.append({
                                "path": path,
                                "ok": bool(summary.get("ok")),
                                "language": data.get("language"),
                                "symbols": [
                                    {"name": item.get("name"), "kind": item.get("kind"), "line": item.get("line"), "end_line": item.get("end_line")}
                                    for item in (data.get("symbols") or [])[:32] if isinstance(item, dict)
                                ],
                                "imports": [str(item.get("module") or item.get("name") or "") for item in (data.get("imports") or [])[:16] if isinstance(item, dict)],
                                "routes": [str(item.get("path") or item.get("route") or "") for item in (data.get("routes") or [])[:12] if isinstance(item, dict)],
                            })
                            links = code_cortex_router.get_dependents(root, path, limit=12)
                            dependents[path] = [
                                str(item.get("path") or item.get("file") or "")
                                for item in (links.get("results") or [])[:12] if isinstance(item, dict)
                            ]
                        return {"tool": "code_cortex", "selected_files": summaries, "direct_dependents": dependents}

                    agent_observation = await asyncio.wait_for(
                        asyncio.to_thread(_observe_selected_scope), timeout=8.0
                    )
                    observed_symbols = sum(len(row.get("symbols") or []) for row in agent_observation.get("selected_files") or [])
                    tool_text = f"Code Cortex observed {len(context_file_list[:3])} selected file(s), {observed_symbols} symbols, and direct dependents"
                    tool_events.append(tool_text)
                    yield _event("agent_run_tool", _tool_event(
                        session_id, tool="Code Cortex", text=tool_text, phase="repository_observation",
                        result={"selected_files": len(context_file_list[:3]), "symbols": observed_symbols},
                    ))
                    related = list(dict.fromkeys(
                        path for rows in (agent_observation.get("direct_dependents") or {}).values()
                        for path in rows if path and path not in context_file_list
                    ))[:8]
                    recipes = _skill_recipe_suggestions(root, run_prompt, limit=3)
                    requested_capabilities: list[dict[str, Any]] = []
                    if "workspace_search" not in granted_capabilities:
                        requested_capabilities.append({
                            "id": "workspace_search",
                            "label": "Search workspace symbols and references",
                            "scope": "read-only source index",
                        })
                    if related and "read_related_files" not in granted_capabilities:
                        requested_capabilities.append({
                            "id": "read_related_files",
                            "label": "Read linked files discovered by Code Cortex",
                            "scope": ", ".join(related),
                            "paths": related,
                        })
                    if recipes and "use_verified_skill" not in granted_capabilities:
                        requested_capabilities.append({
                            "id": "use_verified_skill",
                            "label": "Use matching verified BEAST recipes as advisory guidance",
                            "scope": ", ".join(str(item.get("name") or item.get("skill_id")) for item in recipes),
                            "skills": [str(item.get("skill_id") or "") for item in recipes],
                        })
                    if not is_chat_session and "run_isolated_verifier" not in granted_capabilities:
                        requested_capabilities.append({
                            "id": "run_isolated_verifier",
                            "label": "Run allowlisted tests for the proposed patch",
                            "scope": "temporary isolated workspace only; never the working tree",
                        })
                    if requested_capabilities:
                        request_id = f"cap_{hashlib.sha256((session_id + run_prompt).encode()).hexdigest()[:12]}"
                        yield _event("agent_run_permission_request", {
                            "session_id": session_id,
                            "request_id": request_id,
                            "message": "The agent can expand its investigation before provider dispatch. Source writes still require SourcePlan approval; any verifier command is allowlisted and isolated.",
                            "capabilities": requested_capabilities,
                            "applies": "this agent turn when approved before dispatch",
                        })
                        requested_ids = {str(item.get("id") or "") for item in requested_capabilities}
                        yield _event("agent_run_stage", {
                            "session_id": session_id,
                            "text": "waiting for operator-approved tools",
                        })
                        deadline = time.monotonic() + 4.0
                        last_notice = 0.0
                        while time.monotonic() < deadline:
                            refreshed_detail = store.get(session_id)
                            refreshed_session = (
                                refreshed_detail.get("session")
                                if isinstance(refreshed_detail.get("session"), dict)
                                else {}
                            )
                            refreshed_tools = {
                                str(item)
                                for item in (refreshed_session.get("tools") or [])
                            }
                            refreshed_grants = {
                                item.removeprefix("granted:")
                                for item in refreshed_tools
                                if item.startswith("granted:")
                            }
                            if requested_ids & refreshed_grants:
                                session = refreshed_session
                                session_tools = refreshed_tools
                                session_files = [str(item) for item in (session.get("files") or [])]
                                granted_capabilities |= refreshed_grants
                                yield _event("agent_run_stage", {
                                    "session_id": session_id,
                                    "text": "operator-approved tools ready",
                                })
                                break
                            elapsed = time.monotonic()
                            if elapsed - last_notice >= 2.0:
                                last_notice = elapsed
                                yield _event("agent_run_stage", {
                                    "session_id": session_id,
                                    "text": "waiting for operator-approved tools",
                                })
                            await asyncio.sleep(0.25)
                except (asyncio.TimeoutError, Exception) as exc:
                    tool_text = f"Code Cortex observation deferred: {str(exc)[:140]}"
                    tool_events.append(tool_text)
                    yield _event("agent_run_tool", _tool_event(
                        session_id, tool="Code Cortex", text=tool_text, phase="repository_observation",
                        status="deferred", result={"error": str(exc)[:240]},
                    ))

            # Capability grants are durable and, when the desktop approval
            # arrives before provider dispatch, also take effect in the same
            # run.  That keeps the approval boundary real while avoiding the
            # old "approve it, then manually run again" dead end.
            if "read_related_files" in granted_capabilities:
                approved_related = [
                    path
                    for path in session_files
                    if path not in context_file_list and path not in request_files
                ][:12]
                if approved_related:
                    yield _event("agent_run_stage", {
                        "session_id": session_id,
                        "text": f"reading {len(approved_related)} approved linked file(s)",
                    })
                    yield _event("agent_run_tool", _tool_call_event(
                        session_id,
                        tool="Related File Read",
                        text=f"Reading {len(approved_related)} operator-approved linked file(s).",
                        phase="approved_context_read",
                        authority="operator-approved read-only",
                        parameters={"files": approved_related},
                    ))
                    related_records = client.read_context_files(
                        approved_related,
                        max_files=min(context_file_limit, len(approved_related)),
                        max_chars_each=context_char_limit,
                    )
                    readable_related = [
                        str(record.get("path") or "")
                        for record in related_records
                        if record.get("ok")
                    ]
                    context_file_list = list(dict.fromkeys([*context_file_list, *readable_related]))
            if "workspace_search" in granted_capabilities:
                yield _event("agent_run_stage", {"session_id": session_id, "text": "approved workspace search"})
                try:
                    yield _event("agent_run_tool", _tool_call_event(
                        session_id,
                        tool="Workspace Search",
                        text="Searching workspace symbols and editing context for this request.",
                        phase="approved_search",
                        authority="operator-approved read-only",
                        parameters={"query": run_prompt[:240]},
                    ))

                    def _search_workspace_scope() -> dict[str, Any]:
                        symbols = code_cortex_router.search_symbols(root, run_prompt, limit=24)
                        editing = code_cortex_router.get_editing_context(root, run_prompt, limit=12)
                        return {
                            "tool": "workspace_search",
                            "symbols": (symbols.get("results") or symbols.get("symbols") or [])[:24],
                            "editing_context": (editing.get("results") or editing.get("context") or [])[:12],
                        }

                    search_result = await asyncio.wait_for(
                        asyncio.to_thread(_search_workspace_scope), timeout=8.0
                    )
                    agent_observation["workspace_search"] = search_result
                    symbol_count = len(search_result["symbols"])
                    context_count = len(search_result["editing_context"])
                    tool_text = f"Workspace Search completed: {symbol_count} symbol result(s), {context_count} editing-context result(s)"
                    tool_events.append(tool_text)
                    yield _event("agent_run_tool", _tool_event(
                        session_id, tool="Workspace Search", text=tool_text, phase="approved_search",
                        result={"symbols": symbol_count, "editing_context": context_count},
                    ))
                except (asyncio.TimeoutError, Exception) as exc:
                    tool_text = f"Workspace Search deferred: {str(exc)[:140]}"
                    tool_events.append(tool_text)
                    yield _event("agent_run_tool", _tool_event(
                        session_id, tool="Workspace Search", text=tool_text, phase="approved_search",
                        status="deferred", result={"error": str(exc)[:240]},
                    ))

            if "read_related_files" in granted_capabilities:
                related_reads = [path for path in context_file_list if path not in request_files]
                agent_observation["approved_related_file_reads"] = related_reads[:12]
                tool_text = (
                    f"Related File Read completed: {len(related_reads)} approved linked file(s) added to this turn"
                    if related_reads else
                    "Related File Read ready: no approved linked files were available for this turn"
                )
                tool_events.append(tool_text)
                yield _event("agent_run_tool", _tool_event(
                    session_id, tool="Related File Read", text=tool_text, phase="approved_context_read",
                    authority="operator-approved read-only", result={"files": len(related_reads)},
                ))

            if "use_verified_skill" in granted_capabilities:
                yield _event("agent_run_tool", _tool_call_event(
                    session_id,
                    tool="Verified Skill Recipes",
                    text="Checking verified BEAST recipes that might guide this turn.",
                    phase="skill_selection",
                    authority="advisory only",
                    parameters={"limit": 3},
                ))
                recipes = _skill_recipe_suggestions(root, run_prompt, limit=3)
                agent_observation["verified_skill_recipes"] = recipes
                tool_text = (
                    "Verified Skill Recipes selected: "
                    + ", ".join(str(item.get("name") or item.get("skill_id") or "recipe") for item in recipes)
                    if recipes else "Verified Skill Recipes: no matching recipe was available"
                )
                tool_events.append(tool_text)
                yield _event("agent_run_tool", _tool_event(
                    session_id, tool="Verified Skill Recipes", text=tool_text, phase="skill_selection",
                    authority="advisory only", result={"recipes": len(recipes)},
                ))
            assistant_parts: list[str] = []
            direct_handoff: dict[str, Any] = {}
            direct_handoff_hash = ""
            preflight_intelligence: dict[str, Any] = {}
            try:
                if simulate:
                    yield _event("agent_run_stage", {"session_id": session_id, "text": "desktop simulation"})
                    simulated = (
                        f"BEAST simulated agent stream for: {run_prompt}\n\n"
                        "Observed through the IDE event layer. Convert this advisory output to SourcePlan before any source mutation."
                    )
                    for chunk in BeastApiClient("http://offline", workspace=root)._chunk_text(simulated, size=72):
                        assistant_parts.append(chunk)
                        yield _event("agent_run_token", {"session_id": session_id, "text": chunk})
                        await asyncio.sleep(0.01)
                else:
                    provider_prompt = run_prompt
                    if not is_chat_session:
                        yield _event("agent_run_stage", {"session_id": session_id, "text": "implementation planning"})
                        # This packet is the exact model input.  It is no
                        # longer merely a parallel preparation artifact, and
                        # its hash is enforced when the returned Action IR is
                        # compiled into the reviewable SourcePlan.
                        direct_handoff = build_provider_handoff(
                            root,
                            run_prompt,
                            context_file_list,
                            run_provider,
                            task_name="ide_pair_programmer",
                            verification="python -m pytest tests -q",
                            include_scout=False,
                        )
                        direct_handoff_hash = str(
                            (direct_handoff.get("trace") or {}).get("provider_handoff_hash") or ""
                        )
                        packet = (direct_handoff.get("input") or {}).get("context_packet")
                        envelope = (direct_handoff.get("input") or {}).get("task_envelope")
                        # Pathfinder and tool laziness decide which *optional*
                        # preparation lanes are worth using before provider
                        # dispatch. They do not add files, tools, or authority.
                        if isinstance(envelope, dict):
                            intelligence_dir = root / ".beast" / "intelligence"
                            preflight_builder = TaskEnvelopeBuilder(data_dir=str(intelligence_dir))
                            route_card = preflight_builder.generic_quality_route_card(
                                "live_coding", envelope, persist=False
                            )
                            laziness = ToolLazinessPlugin(
                                ToolLazinessLearner(str(intelligence_dir / "tool_laziness.db"))
                            ).recommend_tools(
                                ["context_packet", "provider", "workspace_graph", "skill_tree", "conductor"],
                                "pair_programmer_preflight",
                                required_tools=["context_packet", "provider"], min_samples=3,
                            )
                            recipes = _skill_recipe_suggestions(root, run_prompt)
                            insight_packet = InsightCompiler(
                                data_dir=str(intelligence_dir)
                            ).compile(
                                objective=run_prompt,
                                provider=run_provider,
                                task_class="live_coding",
                                limit=5,
                                current_task={"objective": run_prompt, "allowed_paths": context_file_list},
                                include_forensic_context=True,
                                forensic_limit=5,
                            )
                            preflight_intelligence = {
                                "task_envelope": envelope,
                                "pathfinder": route_card,
                                "tool_laziness": laziness,
                                "skill_recipes": recipes,
                                "insight_packet": insight_packet,
                                "boundary": {
                                    "selected_files_only": True,
                                    "recipe_authority": "advisory_only",
                                    "tool_authority": "recommendation_only",
                                },
                            }
                            direct_handoff.setdefault("input", {})["preflight"] = {
                                "pathfinder": {
                                    "route_id": route_card.get("route_id"),
                                    "preferred_order": route_card.get("preferred_order") or [],
                                    "avoid": route_card.get("avoid") or [],
                                },
                                "skill_recipes": recipes,
                                "insight": {
                                    "summary": insight_packet.get("summary") or {},
                                    "evidence_count": len(insight_packet.get("evidence") or []),
                                    "authority": "evidence_ranking_only",
                                },
                                "tool_laziness": {
                                    "tools_to_call": [item.get("name") for item in (laziness.get("tools_to_call") or [])],
                                    "tools_not_to_call": [item.get("name") for item in (laziness.get("tools_not_to_call") or [])],
                                },
                                "authority": "advisory only; selected_files and task.allowed_paths remain binding",
                            }
                            preflight_digest = _hash_text(json.dumps(direct_handoff["input"]["preflight"], sort_keys=True, default=str))
                            direct_handoff.setdefault("trace", {})["preflight_hash"] = preflight_digest
                            yield _event("agent_run_preflight", {
                                "session_id": session_id,
                                "route_id": route_card.get("route_id"),
                                "route_name": route_card.get("name"),
                                "recipes": recipes,
                                "insight_evidence": len(insight_packet.get("evidence") or []),
                                "required_tools": [item.get("name") for item in (laziness.get("tools_to_call") or [])],
                                "skipped_tools": [item.get("name") for item in (laziness.get("tools_not_to_call") or [])],
                                "authority": "advisory_only",
                            })
                        if isinstance(packet, dict):
                            try:
                                yield _event("agent_run_tool", _tool_call_event(
                                    session_id,
                                    tool="Semantic RAID",
                                    text="Mirroring the exact context packet into local evidence storage.",
                                    phase="context_packet_mirror",
                                    authority="local evidence mirror",
                                    parameters={"context_packet_id": (direct_handoff.get("input") or {}).get("context_packet_id")},
                                ))
                                shard = SemanticRaidStore(root / ".beast" / "semantic_raid").store_context_packet(packet)
                                direct_handoff["semantic_raid"] = shard.to_dict()
                                yield _event("agent_run_tool", _tool_event(
                                    session_id,
                                    tool="Semantic RAID",
                                    text=f"semantic RAID: context packet mirrored as {shard.shard_id}",
                                    phase="context_packet_mirror",
                                    authority="local evidence mirror",
                                    result={"shard_id": shard.shard_id},
                                ))
                            except Exception as exc:
                                yield _event("agent_run_tool", _tool_event(
                                    session_id,
                                    tool="Semantic RAID",
                                    text=f"semantic RAID deferred: {str(exc)[:140]}",
                                    phase="context_packet_mirror",
                                    status="deferred",
                                    authority="local evidence mirror",
                                    result={"error": str(exc)[:240]},
                                ))
                        # ``stream_live_turn`` appends the selected source
                        # context itself.  Do not also render the full
                        # handoff packet into the user prompt: doing both
                        # doubled context, inflated latency, and encouraged
                        # the model to emit sprawling multi-operation plans.
                        anchor_hints = _action_ir_anchor_hints(root, context_file_list)
                        observation_text = json.dumps(agent_observation, separators=(",", ":"), default=str)[:6000]
                        provider_prompt = (
                            "You are BEAST's implementation planner. Use the supplied read-only Code Cortex observations "
                            "and the exact selected source context to produce one reviewable source edit plan. "
                            "Return ONE JSON object only, with this contract:\n"
                            f'{{"kind":"{ACTION_IR_KIND}","objective":"...","actions":[{{"id":"a1","type":"replace_exact","target":{{"path":"selected/file.py","anchor_ref":"A1"}},"old":"exact current source (optional only when anchor_ref is supplied)","new":"complete replacement source","intent":"..."}},{{"id":"v1","type":"run_verifier","intent":"run focused checks","parameters":{{"command":"python -m pytest path/to/test.py -q"}}}}],"verify":["python -m pytest path/to/test.py -q"]}}\n'
                            "Every source-edit action MUST include a non-empty `new`; it must include non-empty `old` unless "
                            "it uses one of the supplied anchor_ref values. Never emit an intent-only action. Use at most one "
                            "source edit per file. You MAY include non-mutating `run_verifier` or `ask_for_context` actions when "
                            "they are needed for the next governed loop; those requests cannot edit files and run only after operator approval. "
                            "Do not emit markdown, prose, a diff, placeholders, or multiple sequential edits.\n\n"
                            f"Objective: {run_prompt[:2400]}\n\n"
                            f"Read-only Code Cortex observations (not edit authority):\n{observation_text}\n\n"
                            + (f"Resolvable anchors for selected files (use these exact IDs when useful):\n{anchor_hints}\n\n" if anchor_hints else "")
                            + "Selected source context follows in the system attachment."
                        )
                        yield _event("agent_run_tool", _tool_call_event(
                            session_id,
                            tool="Provider Handoff",
                            text="Handing the selected files and governed context packet to the model.",
                            phase="provider_input",
                            authority="selected files only",
                            parameters={"provider": run_provider, "model": run_model},
                        ))
                        yield _event("agent_run_tool", _tool_event(
                            session_id,
                            tool="Provider Handoff",
                            text="provider input: direct governed context packet "
                                + str((direct_handoff.get("input") or {}).get("context_packet_id") or "ready"),
                            phase="provider_input",
                            authority="selected files only",
                            result={"context_packet_id": (direct_handoff.get("input") or {}).get("context_packet_id")},
                        ))
                    stream_options = {
                        "provider": run_provider,
                        "model": run_model,
                        "context_files": context_file_list,
                        "max_tokens": run_max_tokens,
                        "context_max_chars_each": context_char_limit,
                        "max_continuations": 1 if is_chat_session else 0,
                        "governance_level": "ide_agent_session",
                    }
                    if "allow_fallback" in inspect.signature(client.stream_live_turn).parameters:
                        # A coding run needs intact Action IR.  Never append a
                        # conversational fallback to a partial edit contract.
                        stream_options["allow_fallback"] = is_chat_session
                    async for event in client.stream_live_turn(provider_prompt, conversation_history, **stream_options):
                        event_type = str(event.get("type") or "event")
                        if event_type == "token":
                            text = str(event.get("text") or "")
                            assistant_parts.append(text)
                            yield _event("agent_run_token", {"session_id": session_id, "text": text})
                        elif event_type == "stage":
                            yield _event("agent_run_stage", {"session_id": session_id, "text": event.get("text") or ""})
                        elif event_type == "compute":
                            yield _event("agent_run_compute", {
                                "session_id": session_id,
                                "context": event.get("context") if isinstance(event.get("context"), dict) else {},
                            })
                        elif event_type == "tool":
                            tool_text = str(event.get("text") or "")
                            tool_events.append(tool_text)
                            yield _event("agent_run_tool", {"session_id": session_id, "text": tool_text})
                        elif event_type == "done":
                            if event.get("assistant_text") and not assistant_parts:
                                assistant_parts.append(str(event.get("assistant_text") or ""))
                            tool_events.extend([str(item) for item in (event.get("tool_events") or [])])
                            event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
                            crystal_decision = event_data.get("crystal_reuse_decision") if isinstance(event_data.get("crystal_reuse_decision"), dict) else {}
                            crystal_record = event_data.get("crystal_record") if isinstance(event_data.get("crystal_record"), dict) else {}
                            if crystal_decision or crystal_record:
                                yield _event("agent_run_crystal", {
                                    "session_id": session_id,
                                    "decision": crystal_decision,
                                    "record": crystal_record,
                                    "reused": bool(BeastApiClient.crystal_decision_response(crystal_decision)),
                                })
                            yield _event("agent_run_provider_done", {"session_id": session_id, "ok": bool(event.get("ok", True)), "data": event.get("data") or {}})
                        elif event_type == "error":
                            failure = str(event.get("error") or "stream error")
                            # Preserve a partial coding response long enough
                            # for the bounded Action-IR repair pass below. A
                            # chat response, or an empty coding response, is a
                            # real terminal provider failure.
                            if not is_chat_session and assistant_parts:
                                tool_events.append(f"provider stream incomplete; repairing Action IR: {failure[:180]}")
                                yield _event("agent_run_tool", {
                                    "session_id": session_id,
                                    "text": "provider stream incomplete; attempting bounded Action IR repair",
                                })
                                break
                            store.update(
                                session_id,
                                status="active",
                                output={
                                    "kind": "chat_provider_error" if is_chat_session else "agent_provider_error",
                                    "text": failure,
                                    "provider": run_provider,
                                    "model": run_model,
                                },
                                evidence=[{
                                    "beast_object_type": "beast_agent_session_run_error",
                                    "session_id": session_id,
                                    "error": failure,
                                    "timestamp": time.time(),
                                }],
                            )
                            yield _event("agent_run_error", {"session_id": session_id, "ok": False, "error": failure})
                            yield _event("agent_run_done", {
                                "ok": False,
                                "session_id": session_id,
                                "chars": len("".join(assistant_parts)),
                                "sourceplan_status": "provider_error",
                                "session": {},
                            })
                            return
                assistant_text = "".join(assistant_parts)
                compile_result = ({"ok": True, "status": "chat_complete", "operation_count": 0, "plan": {}} if is_chat_session else _compile_agent_action_ir_sourceplan(
                    root,
                    output=assistant_text,
                    provider=run_provider,
                    requested_files=context_file_list,
                    objective=run_prompt,
                    expected_handoff_hash=direct_handoff_hash,
                ))
                repair_text = ""
                if not is_chat_session and not compile_result.get("ok") and not simulate and context_file_list:
                    schema_recovery = str(compile_result.get("status") or "") in {
                        "not_action_ir", "empty_action_ir", "incomplete_function_replacement", "multiple_actions_same_file",
                        # Missing old/new is a contract-shape failure.  Give
                        # the model the exact fresh anchor catalog rather than
                        # surfacing it as a terminal IDE error.
                        "action_ir_rejected",
                    }
                    repair_files = context_file_list[:1] if compact_local_coder or schema_recovery else context_file_list
                    repair_tokens = min(run_max_tokens, 640 if compact_local_coder else 2048) if schema_recovery or compact_local_coder else max_tokens
                    repair_context_chars = min(context_char_limit, 1800 if compact_local_coder else 2400) if schema_recovery or compact_local_coder else context_max_chars_each
                    yield _event("agent_run_stage", {"session_id": session_id, "text": "bounded local sourceplan repair" if compact_local_coder else ("focused Action IR recovery" if schema_recovery else "sourceplan repair")})
                    repair_diagnostics = "\n".join(
                        str(value)
                        for value in (
                            compile_result.get("error"),
                            *(
                                compile_result.get("missing_context_questions")
                                if isinstance(compile_result.get("missing_context_questions"), list)
                                else []
                            ),
                        )
                        if value
                    )
                    repair_text, repair_tools = await _stream_repair_action_ir(
                        client,
                        objective=run_prompt,
                        previous_output=assistant_text,
                        provider_id=run_provider,
                        model_id=run_model,
                        files=repair_files,
                        max_output_tokens=repair_tokens,
                        max_context_chars=repair_context_chars,
                        diagnostics=repair_diagnostics,
                        root_path=root,
                        expected_handoff_hash=direct_handoff_hash,
                        schema_recovery=schema_recovery,
                    )
                    for item in repair_tools[:20]:
                        tool_events.append(item)
                        yield _event("agent_run_tool", {"session_id": session_id, "text": item})
                    if repair_text.strip():
                        store.update(
                            session_id,
                            output={
                                "kind": "agent_action_ir_repair",
                                "text": repair_text,
                                "provider": run_provider,
                                "model": run_model,
                            },
                        )
                        compile_result = _compile_agent_action_ir_sourceplan(
                            root,
                            output=repair_text,
                            provider=run_provider,
                            requested_files=context_file_list,
                            objective=run_prompt,
                            expected_handoff_hash=direct_handoff_hash,
                        )
                validation: dict[str, Any] = {}
                if not is_chat_session and compile_result.get("ok"):
                    plan = compile_result.get("plan") if isinstance(compile_result.get("plan"), dict) else {}
                    validation = _validate_agent_sourceplan(
                        root,
                        plan,
                        run_isolated_verifier="granted:run_isolated_verifier" in session_tools,
                    )
                    plan["validation"] = validation
                    plan["status"] = "draft_validation_passed" if validation.get("ok") else "draft_validation_failed"
                    plan.setdefault("output_evidence", {})["proposal_validation"] = {
                        "status": validation.get("status"),
                        "check_count": validation.get("check_count"),
                        "syntax_checked": validation.get("syntax_checked"),
                    }
                    yield _event("agent_run_validation", {"session_id": session_id, **validation})
                    repair_budget = max(0, min(int(max_repair_rounds), 3))
                    repair_round = 0
                    while not validation.get("ok") and not simulate and context_file_list and repair_round < repair_budget:
                        repair_round += 1
                        repair_files = context_file_list[:1] if compact_local_coder else context_file_list
                        repair_tokens = min(run_max_tokens, 640) if compact_local_coder else max_tokens
                        repair_context_chars = min(context_char_limit, 1800) if compact_local_coder else context_max_chars_each
                        yield _event("agent_run_stage", {"session_id": session_id, "text": ("bounded local validation repair" if compact_local_coder else "proposal validation repair") + f" {repair_round}/{repair_budget}"})
                        validation_repair, validation_tools = await _stream_repair_action_ir(
                            client,
                            objective=run_prompt,
                            previous_output=repair_text or assistant_text,
                            provider_id=run_provider,
                            model_id=run_model,
                            files=repair_files,
                            max_output_tokens=repair_tokens,
                            max_context_chars=repair_context_chars,
                            diagnostics="\n".join(str(item) for item in validation.get("failures") or []),
                            root_path=root,
                            expected_handoff_hash=direct_handoff_hash,
                        )
                        for item in validation_tools[:20]:
                            tool_events.append(item)
                            yield _event("agent_run_tool", {"session_id": session_id, "text": item})
                        if validation_repair.strip():
                            store.update(session_id, output={
                                "kind": "agent_action_ir_validation_repair",
                                "text": validation_repair,
                                "provider": run_provider,
                                "model": run_model,
                                "repair_round": repair_round,
                                "diagnostics": validation.get("failures") or [],
                            })
                            compile_result = _compile_agent_action_ir_sourceplan(
                                root,
                                output=validation_repair,
                                provider=run_provider,
                                requested_files=context_file_list,
                                objective=run_prompt,
                                expected_handoff_hash=direct_handoff_hash,
                            )
                            if compile_result.get("ok"):
                                plan = compile_result.get("plan") if isinstance(compile_result.get("plan"), dict) else {}
                                validation = _validate_agent_sourceplan(
                                    root,
                                    plan,
                                    run_isolated_verifier="granted:run_isolated_verifier" in session_tools,
                                )
                                plan["validation"] = validation
                                plan["status"] = "draft_validation_passed" if validation.get("ok") else "draft_validation_failed"
                                plan.setdefault("output_evidence", {})["proposal_validation"] = {
                                    "status": validation.get("status"),
                                    "check_count": validation.get("check_count"),
                                    "syntax_checked": validation.get("syntax_checked"),
                                }
                                yield _event("agent_run_validation", {"session_id": session_id, "repair": True, "repair_round": repair_round, **validation})
                            else:
                                break
                        else:
                            break
                    if not validation.get("ok"):
                        compile_result = {
                            **compile_result,
                            "ok": False,
                            "status": "proposal_validation_failed",
                            "error": "Proposed edits failed bounded validation: " + "; ".join(str(item) for item in (validation.get("failures") or [])[:3]),
                            "validation": validation,
                            "requires_operator_translation": True,
                        }
                if not is_chat_session and compile_result.get("ok"):
                    # Pair Programmer used to stop at syntax validation. Run
                    # the same bounded SourcePlan scorecard used by the
                    # dedicated source workbench so policy, Code Cortex
                    # impact, safety, lattice, scheduling, worktree, and
                    # evidence guidance reach the proposal before review.
                    plan = compile_result.get("plan") if isinstance(compile_result.get("plan"), dict) else {}
                    yield _event("agent_run_stage", {"session_id": session_id, "text": "BEAST review scorecard"})
                    try:
                        scorecard_result = await asyncio.wait_for(
                            asyncio.to_thread(client.sourceplan_scorecard, plan), timeout=12.0
                        )
                        if scorecard_result.ok and isinstance(scorecard_result.data, dict):
                            scorecard = scorecard_result.data
                            plan["scorecard"] = scorecard
                            plan["risk_level"] = str(scorecard.get("risk_level") or plan.get("risk_level") or "high")
                            plan["review_workbench"] = scorecard.get("source_workbench") if isinstance(scorecard.get("source_workbench"), dict) else {}
                            yield _event("agent_run_scorecard", {
                                "session_id": session_id,
                                "risk_level": plan["risk_level"],
                                "decision": scorecard.get("decision"),
                                "policy_gate": scorecard.get("policy_gate_result") if isinstance(scorecard.get("policy_gate_result"), dict) else {},
                                "suggested_tests": scorecard.get("suggested_tests") if isinstance(scorecard.get("suggested_tests"), list) else [],
                                "worktree": scorecard.get("worktree_recommendation") if isinstance(scorecard.get("worktree_recommendation"), dict) else {},
                                "lattice": scorecard.get("mission_lattice") if isinstance(scorecard.get("mission_lattice"), dict) else {},
                            })
                        else:
                            yield _event("agent_run_tool", {"session_id": session_id, "text": "review scorecard deferred: unavailable"})
                    except (asyncio.TimeoutError, Exception) as exc:
                        yield _event("agent_run_tool", {"session_id": session_id, "text": f"review scorecard deferred: {str(exc)[:160]}"})
                    # Compose the V2 engines at the same governed boundary.
                    # They remain advisory: none may expand edit scope or
                    # apply a mutation. The resulting artifacts travel with
                    # the SourcePlan so every BEAST surface can inspect them.
                    try:
                        envelope_builder = TaskEnvelopeBuilder(data_dir=str(root / ".beast" / "intelligence"))
                        envelope = preflight_intelligence.get("task_envelope") if isinstance(preflight_intelligence.get("task_envelope"), dict) else envelope_builder.build({
                            "user_request": run_prompt, "provider": run_provider,
                            "task_class": "live_coding", "max_files": len(context_file_list),
                        }, dry_run=True)
                        route_card = preflight_intelligence.get("pathfinder") if isinstance(preflight_intelligence.get("pathfinder"), dict) else envelope_builder.generic_quality_route_card("live_coding", envelope, persist=False)
                        quality = await asyncio.wait_for(asyncio.to_thread(
                            envelope_builder.quality_cascade.run, envelope, route_card, str(root)
                        ), timeout=12.0)
                        laziness = preflight_intelligence.get("tool_laziness") if isinstance(preflight_intelligence.get("tool_laziness"), dict) else ToolLazinessPlugin(ToolLazinessLearner(str(root / ".beast" / "intelligence" / "tool_laziness.db"))).recommend_tools(
                            ["workspace_graph", "quality_cascade", "conductor", "provider"],
                            "governed_sourceplan_review", required_tools=["quality_cascade"], min_samples=3,
                        )
                        workflow = ConductorWorkflowBuilder(data_dir=str(root / ".beast" / "intelligence")).build(
                            envelope,
                            context_packet=(direct_handoff.get("input") or {}).get("context_packet") if isinstance((direct_handoff.get("input") or {}).get("context_packet"), dict) else None,
                            route_card=route_card, quality_report=quality,
                            forge_scorecard=plan.get("scorecard") if isinstance(plan.get("scorecard"), dict) else {},
                            run_swarm=False, persist=False,
                        )
                        dispatch = ConductorWorkflowBuilder(data_dir=str(root / ".beast" / "intelligence")).dispatch(
                            workflow,
                            {
                                "prepare_task": lambda: {"ok": True, "task_id": envelope.get("task_id")},
                                "pack_context": lambda: {"ok": True, "packet_id": ((direct_handoff.get("input") or {}).get("context_packet") or {}).get("packet_id")},
                                "select_route": lambda: {"ok": True, "route_id": route_card.get("route_id")},
                                "run_verification": lambda: {"ok": bool(validation.get("ok")), "status": validation.get("status"), "check_count": validation.get("check_count")},
                            },
                            persist=True,
                        )
                        canon = CanonRegistry().validate_bundle({
                            "task_envelope": envelope, "route_card": route_card,
                            "context_packet": (direct_handoff.get("input") or {}).get("context_packet"),
                            "quality_cascade_report": quality, "conductor_workflow_card": workflow,
                        })
                        plan["intelligence"] = {
                            "task_envelope": envelope, "pathfinder": route_card, "quality_cascade": quality,
                            "tool_laziness": laziness, "conductor": workflow, "conductor_dispatch": dispatch, "canon": canon,
                            "skill_recipes": preflight_intelligence.get("skill_recipes") or [],
                            "insight_packet": preflight_intelligence.get("insight_packet") or {},
                            "provider_handoff": {
                                "context_packet_id": (direct_handoff.get("input") or {}).get("context_packet_id"),
                                "provider_handoff_hash": direct_handoff_hash,
                                "preflight_hash": (direct_handoff.get("trace") or {}).get("preflight_hash"),
                            },
                            "authority": preflight_intelligence.get("boundary") or {"selected_files_only": True},
                        }
                        yield _event("agent_run_intelligence", {
                            "session_id": session_id, "quality": str(quality.get("status") or "completed"),
                            "workflow": str(workflow.get("decision") or "advisory"),
                            "dispatch": str(dispatch.get("stopped") or "completed"),
                            "canon_valid": bool(canon.get("valid")),
                            "tool_skips": int((laziness.get("summary") or {}).get("skip_count") or 0),
                        })
                    except (asyncio.TimeoutError, Exception) as exc:
                        yield _event("agent_run_tool", {"session_id": session_id, "text": f"intelligence fabric deferred: {str(exc)[:160]}"})
                sourceplan_status = str(compile_result.get("status") or "requires_operator_translation")
                if is_planning_agent:
                    sourceplan_status = "implementation_brief"
                    yield _event("agent_run_advisory", {
                        "ok": True,
                        "session_id": session_id,
                        "status": sourceplan_status,
                        "text": assistant_text,
                        "context_files": context_file_list,
                        "message": "Read-only investigation and implementation brief complete. No SourcePlan or file mutation was created.",
                    })
                elif not is_chat_session:
                    if compile_result.get("ok"):
                        plan = compile_result.get("plan") if isinstance(compile_result.get("plan"), dict) else {}
                        # Bind the proposal to its persistent agent session so
                        # SourcePlan apply/rollback receipts can become the
                        # next turn's grounded tool evidence.
                        plan["agent_session_id"] = session_id
                        for request_item in (plan.get("non_mutating_requests") or [])[:8]:
                            if not isinstance(request_item, dict):
                                continue
                            parameters = request_item.get("parameters") if isinstance(request_item.get("parameters"), dict) else {}
                            request_type = str(request_item.get("type") or "agent_request")
                            command = str(parameters.get("command") or request_item.get("command") or "")
                            query = str(parameters.get("query") or request_item.get("query") or request_item.get("intent") or "")
                            yield _event("agent_run_request", {
                                "session_id": session_id,
                                "type": "command_request" if request_type == "run_verifier" else "context_request" if request_type == "ask_for_context" else "agent_request",
                                "request_type": request_type,
                                "text": str(request_item.get("intent") or query or command or request_type),
                                "command": command,
                                "query": query,
                                "path": str(request_item.get("path") or ""),
                                "authority": "operator approval required; no source mutation",
                                "status": "requested",
                            })
                        yield _event("agent_run_sourceplan", {
                            "ok": True,
                            "session_id": session_id,
                            "status": sourceplan_status,
                            "operation_count": int(compile_result.get("operation_count") or 0),
                            "plan_id": str(plan.get("plan_id") or ""),
                            "plan": plan,
                            "evidence_receipt": compile_result.get("evidence_receipt") if isinstance(compile_result.get("evidence_receipt"), dict) else {},
                        })
                    elif sourceplan_status in {"not_action_ir", "empty_action_ir"} and (repair_text or assistant_text).strip():
                        # A provider can return a useful investigation or
                        # explanation without proposing a file edit. Preserve
                        # that answer as advisory output instead of treating a
                        # non-mutating response as a failed stream. It never
                        # becomes a SourcePlan or gains write authority.
                        sourceplan_status = "advisory_response"
                        yield _event("agent_run_advisory", {
                            "ok": True,
                            "session_id": session_id,
                            "status": sourceplan_status,
                            "text": repair_text or assistant_text,
                            "context_files": context_file_list,
                            "message": "The model returned advice, not a patch. No files were changed.",
                        })
                    else:
                        yield _event("agent_run_needs_operator", {
                            "ok": False,
                            "session_id": session_id,
                            "status": sourceplan_status,
                            "error": str(compile_result.get("error") or "Action IR compilation requires operator translation."),
                            "assistant_text": assistant_text,
                            "context_files": context_file_list,
                            "retry_options": compile_result.get("retry_options") if isinstance(compile_result.get("retry_options"), list) else [],
                        })
                result = store.update(
                    session_id,
                    status="active",
                    output={
                        "kind": "streamed_agent_output",
                        "text": assistant_text,
                        "tool_events": tool_events[:40],
                        "provider": run_provider,
                        "model": run_model,
                        "simulated": bool(simulate),
                        "sourceplan_status": sourceplan_status,
                        "sourceplan_operation_count": int(compile_result.get("operation_count") or 0),
                        "sourceplan_plan_id": str(((compile_result.get("plan") or {}).get("plan_id") or "")) if compile_result.get("ok") else "",
                        "sourceplan_plan": compile_result.get("plan") if compile_result.get("ok") and isinstance(compile_result.get("plan"), dict) else {},
                        "sourceplan_validation": validation,
                    },
                    evidence=[{
                        "beast_object_type": "beast_agent_session_sourceplan_status",
                        "session_id": session_id,
                        "status": sourceplan_status,
                        "operation_count": int(compile_result.get("operation_count") or 0),
                        "plan_id": str(((compile_result.get("plan") or {}).get("plan_id") or "")),
                        "error": str(compile_result.get("error") or ""),
                        "validation_status": str(validation.get("status") or ""),
                        "timestamp": time.time(),
                    }],
                    budget_delta={"tokens": max(1, len(assistant_text) // 4)},
                )
                yield _event("agent_run_done", {
                    "ok": True,
                    "session_id": session_id,
                    "chars": len(assistant_text),
                    "sourceplan_status": sourceplan_status,
                    "session": result.get("session") if result.get("ok") else {},
                })
            except Exception as exc:
                store.update(session_id, status="active", evidence=[{
                    "beast_object_type": "beast_agent_session_run_error",
                    "session_id": session_id,
                    "error": str(exc),
                    "timestamp": time.time(),
                }])
                yield _event("agent_run_error", {"ok": False, "session_id": session_id, "error": str(exc)})
                yield _event("agent_run_done", {
                    "ok": False,
                    "session_id": session_id,
                    "chars": 0,
                    "sourceplan_status": "run_error",
                    "session": {},
                })

        async def generate():
            try:
                async for chunk in _generate_agent_run_events():
                    engine = run_runtime.get("engine")
                    durable_run_id = str(run_runtime.get("run_id") or "")
                    if engine is not None and durable_run_id:
                        engine.raise_if_cancelled(durable_run_id)
                        engine.record_legacy_chunk(durable_run_id, chunk)
                    yield chunk
            except (AgentRunCancelled, asyncio.CancelledError) as exc:
                engine = run_runtime.get("engine")
                durable_run_id = str(run_runtime.get("run_id") or "")
                reason = str(getattr(exc, "reason", "") or "operator_cancelled")
                if engine is not None and durable_run_id:
                    engine.finalize_cancel(durable_run_id, reason)
                cancelled = _event("agent_run_done", {
                    "ok": False,
                    "session_id": session_id,
                    "run_id": durable_run_id,
                    "chars": 0,
                    "sourceplan_status": "cancelled",
                    "cancel_reason": reason,
                    "session": {},
                })
                if engine is not None and durable_run_id:
                    engine.record_legacy_chunk(durable_run_id, cancelled)
                yield cancelled
            except Exception as exc:
                engine = run_runtime.get("engine")
                durable_run_id = str(run_runtime.get("run_id") or "")
                if engine is not None and durable_run_id:
                    engine.fail(durable_run_id, str(exc))
                error_chunk = _event("agent_run_error", {
                    "ok": False,
                    "session_id": session_id,
                    "run_id": durable_run_id,
                    "error": f"Agent run stream terminated before completion: {exc}",
                })
                done_chunk = _event("agent_run_done", {
                    "ok": False,
                    "session_id": session_id,
                    "run_id": durable_run_id,
                    "chars": 0,
                    "sourceplan_status": "stream_error",
                    "session": {},
                })
                if engine is not None and durable_run_id:
                    engine.record_legacy_chunk(durable_run_id, error_chunk)
                    engine.record_legacy_chunk(durable_run_id, done_chunk)
                yield error_chunk
                yield done_chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return None
