"""Overview routes for the BEAST IDE facade."""

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


def register_overview_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _classify_related = ctx._classify_related
    _event = ctx._event
    _gather_ide_state = ctx._gather_ide_state
    _root = ctx._root
    _symbol_outline_for_text = ctx._symbol_outline_for_text
    code_cortex_router = ctx.code_cortex_router

    @router.get("/edgek/ide/snapshot")
    async def edgek_ide_snapshot(
        root_path: str = None,
        active_file: str = "",
        objective: str = "",
        phase: str = "scout",
        risk: str = "",
        evidence_limit: int = 12,
        detail: bool = False,
    ):
        root = _root(root_path)
        query = objective or active_file or "BEAST IDE mission"
        if not detail or str(objective or "").strip().lower() in {"desktop-health", "gateway-ready"}:
            return {
                "beast_object_type": "beast_ide_snapshot",
                "version": "1.0",
                "status": "ready",
                "mode": "lightweight_health_probe",
                "workspace_root": str(root),
                "active_file": active_file,
                "objective": query,
                "mission_cockpit": {"status": "ready", "workspace_root": str(root), "objective": query},
                "sourceplan_queue": [],
                "worktrees": {},
                "policy": {"mode_route": {}, "reintegration_health": {}, "architecture_decisions": []},
                "code_cortex": {"status": "deferred"},
                "evidence_bus": {"status": "deferred", "receipts": []},
                "mission_lattice": {"status": "deferred"},
                "agent_sessions": [],
                "operator_actions": [],
            }
        try:
            state = await asyncio.to_thread(_gather_ide_state, root, query, phase, risk, evidence_limit)
        except Exception as error:
            state = {
                "cockpit": {
                    "status": "degraded",
                    "workspace_root": str(root),
                    "objective": query,
                    "errors": [str(error)],
                    "sourceplan_queue": [],
                    "worktrees": {},
                    "mode_route": {},
                    "reintegration_health": {},
                },
                "code_cortex": {"status": "degraded", "error": str(error)},
                "evidence": {"status": "degraded", "error": str(error), "receipts": []},
                "lattice": {"status": "degraded", "error": str(error)},
                "agent_sessions": [],
                "architecture": [],
            }
        cockpit = state["cockpit"]
        code_cortex = state["code_cortex"]
        evidence = state["evidence"]
        lattice = state["lattice"]
        agent_sessions = state["agent_sessions"]
        architecture = state["architecture"]
        return {
            "beast_object_type": "beast_ide_snapshot",
            "version": "1.0",
            "phase": "phase_1_vscode_shell",
            "gateway_url": "http://127.0.0.1:8000",
            "ide_capabilities": [
                "mission_control",
                "source_workbench",
                "event_bus",
                "inline_intelligence",
                "agent_session_workspace",
                "worktree_native_missions",
            ],
            "workspace_root": str(root),
            "active_file": active_file,
            "objective": query,
            "look_and_feel": {
                "source": "beast_tui",
                "palette": {
                    "background": "#050607",
                    "panel": "#0b1113",
                    "border": "#1f3a3d",
                    "acid": "#a6ff3f",
                    "cyan": "#33f6ff",
                    "warning": "#ffd166",
                    "danger": "#ff4d6d",
                    "text": "#d7fbe8",
                    "muted": "#7a8c8d",
                },
            },
            "mission_cockpit": cockpit,
            "sourceplan_queue": cockpit.get("sourceplan_queue") or [],
            "worktrees": cockpit.get("worktrees") if isinstance(cockpit.get("worktrees"), dict) else {},
            "policy": {
                "mode_route": cockpit.get("mode_route") if isinstance(cockpit.get("mode_route"), dict) else {},
                "reintegration_health": cockpit.get("reintegration_health") if isinstance(cockpit.get("reintegration_health"), dict) else {},
                "architecture_decisions": architecture,
            },
            "code_cortex": code_cortex,
            "evidence_bus": evidence,
            "mission_lattice": lattice,
            "agent_sessions": agent_sessions,
            "operator_actions": [
                "edgekBeast.sourcePlanFromSelection",
                "edgekBeast.scoreCurrentPlan",
                "edgekBeast.openSourceWorkbench",
                "edgekBeast.showEvidence",
                "edgekBeast.showAgentSessions",
                "edgekBeast.createAgentSession",
                "edgekBeast.createWorktreeMission",
                "edgekBeast.replayLatticeCandidate",
            ],
        }

    @router.get("/edgek/ide/events")
    async def edgek_ide_events(
        root_path: str = None,
        active_file: str = "",
        objective: str = "",
        phase: str = "scout",
        risk: str = "",
        interval: float = 2.0,
        once: bool = False,
    ):
        async def generate():
            root = _root(root_path)
            query = objective or active_file or "BEAST IDE mission"
            last_payloads: dict[str, str] = {}
            while True:
                # Offload the synchronous cockpit/cortex/evidence/lattice scan to a worker
                # thread; running it inline here blocks the single event loop and starves
                # concurrent agent run-events streams (see _gather_ide_state).
                state = await asyncio.to_thread(_gather_ide_state, root, query, phase, risk, 12)
                cockpit = state["cockpit"]
                code_cortex = state["code_cortex"]
                evidence = state["evidence"]
                lattice = state["lattice"]
                agent_sessions = state["agent_sessions"]
                policy = {
                    "mode_route": cockpit.get("mode_route") if isinstance(cockpit.get("mode_route"), dict) else {},
                    "reintegration_health": cockpit.get("reintegration_health") if isinstance(cockpit.get("reintegration_health"), dict) else {},
                    "architecture_decisions": state["architecture"],
                }
                events = {
                    "sourceplan": {"queue": cockpit.get("sourceplan_queue") or []},
                    "policy": policy,
                    "evidence": evidence,
                    "context": {"active_file": active_file, "objective": query, "code_cortex": code_cortex},
                    "worktree": cockpit.get("worktrees") if isinstance(cockpit.get("worktrees"), dict) else {},
                    "lattice": lattice,
                    "agent_session": agent_sessions,
                }
                for event_type, payload in events.items():
                    encoded = json.dumps(payload, sort_keys=True, default=str)
                    if once or last_payloads.get(event_type) != encoded:
                        last_payloads[event_type] = encoded
                        yield _event(event_type, payload)
                if once:
                    break
                # Floor raised to 2.0s: each tick's snapshot can take several seconds, so a
                # shorter interval just piles up overlapping worker-thread scans.
                await asyncio.sleep(max(2.0, min(float(interval), 30.0)))

        return StreamingResponse(generate(), media_type="text/event-stream")

    @router.get("/edgek/ide/related-context")
    async def edgek_ide_related_context(path: str, root_path: str = None, limit: int = 80):
        root = _root(root_path)
        dependents = code_cortex_router.get_dependents(root, path, limit=max(1, min(int(limit), 500)))
        raw = dependents.get("dependents") or dependents.get("related_files") or dependents.get("files") or []
        related = []
        for item in raw:
            if isinstance(item, str):
                related_path = item
                record: dict[str, Any] = {"path": related_path}
            elif isinstance(item, dict):
                related_path = str(item.get("path") or item.get("file") or item.get("dependent") or "")
                record = dict(item)
                record["path"] = related_path
            else:
                continue
            if not related_path:
                continue
            record["relationship_kind"] = _classify_related(related_path)
            related.append(record)
        priority = {"test": 0, "route": 1, "surface": 2, "model": 3, "related": 4}
        related.sort(key=lambda item: (priority.get(str(item.get("relationship_kind")), 9), str(item.get("path"))))
        return {
            "beast_object_type": "beast_ide_related_context",
            "version": "1.0",
            "workspace_root": str(root),
            "path": path,
            "count": len(related),
            "related": related[: max(1, min(int(limit), 500))],
            "code_cortex": dependents,
        }

    @router.get("/edgek/ide/symbol-outline")
    async def edgek_ide_symbol_outline(path: str, root_path: str = None, max_chars: int = 900000, max_symbols: int = 300):
        root = _root(root_path)
        target = _safe_relative(root, path)
        if target is None or not target.exists() or not target.is_file():
            return {
                "ok": False,
                "beast_object_type": "beast_ide_symbol_outline",
                "version": "1.0",
                "workspace_root": str(root),
                "path": path,
                "error": "file not found or path escaped workspace",
                "symbols": [],
            }
        raw = target.read_text(encoding="utf-8", errors="replace")
        bounded = raw[: max(1000, min(int(max_chars), 2_000_000))]
        lines = bounded.splitlines()
        symbols = _symbol_outline_for_text(path, bounded, max_symbols=max_symbols)
        return {
            "ok": True,
            "beast_object_type": "beast_ide_symbol_outline",
            "version": "1.0",
            "workspace_root": str(root),
            "path": path,
            "file_bytes": target.stat().st_size,
            "line_count": len(raw.splitlines()),
            "parsed_chars": len(bounded),
            "truncated": len(bounded) < len(raw),
            "symbol_count": len(symbols),
            "symbols": symbols,
            "guidance": "Use symbol-sized selections for agent patch requests; large files should not be rewritten as one replacement block.",
        }

    @router.get("/edgek/ide/symbol-search")
    async def edgek_ide_symbol_search(root_path: str = None, query: str = "", limit: int = 80, max_files: int = 700):
        root = _root(root_path)
        needle = query.strip().lower()
        capped_limit = max(1, min(int(limit), 500))
        capped_files = max(1, min(int(max_files), 3000))

        def scan_symbols() -> tuple[int, list[dict[str, Any]]]:
            suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".md"}
            matches: list[dict[str, Any]] = []
            scanned = 0
            for candidate in _bounded_workspace_files(root,suffixes,capped_files):
                scanned += 1
                try:
                    text = candidate.read_text(encoding="utf-8", errors="replace")[:900000]
                except Exception:
                    continue
                rel = str(candidate.relative_to(root))
                for symbol in _symbol_outline_for_text(rel, text, max_symbols=200):
                    haystack = f"{symbol.get('name')} {symbol.get('kind')} {rel}".lower()
                    if needle and needle not in haystack:
                        continue
                    matches.append({**symbol, "path": rel})
                    if len(matches) >= capped_limit:
                        break
                if len(matches) >= capped_limit:
                    break
            return scanned, matches

        scanned, matches = await asyncio.to_thread(scan_symbols)
        return {
            "ok": True,
            "beast_object_type": "beast_ide_symbol_search",
            "version": "1.0",
            "workspace_root": str(root),
            "query": query,
            "scanned_files": scanned,
            "match_count": len(matches),
            "symbols": matches,
            "code_cortex_front_door": True,
        }

    @router.get("/edgek/ide/text-search")
    async def edgek_ide_text_search(root_path: str = None, query: str = "", limit: int = 80, max_files: int = 800):
        root = _root(root_path)
        needle = str(query or "").strip()
        if not needle:
            return {"ok": False, "beast_object_type": "beast_ide_text_search", "error": "empty_query", "query": needle, "matches": []}
        capped_limit = max(1, min(int(limit), 500))
        capped_files = max(1, min(int(max_files), 3000))

        def scan_text() -> tuple[int, list[dict[str, Any]]]:
            suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".html", ".css", ".yml", ".yaml", ".toml"}
            matches: list[dict[str, Any]] = []
            scanned = 0
            lowered = needle.lower()
            for candidate in _bounded_workspace_files(root,suffixes,capped_files):
                if len(matches)>=capped_limit: break
                scanned += 1
                try:
                    lines = candidate.read_text(encoding="utf-8", errors="replace")[:900000].splitlines()
                except Exception:
                    continue
                rel = str(candidate.relative_to(root))
                for line_number, line in enumerate(lines, start=1):
                    if lowered in line.lower():
                        matches.append({"path": rel, "line": line_number, "preview": line.strip()[:240]})
                        if len(matches) >= capped_limit:
                            break
            return scanned, matches

        scanned, matches = await asyncio.to_thread(scan_text)
        return {
            "ok": True,
            "beast_object_type": "beast_ide_text_search",
            "version": "1.0",
            "workspace_root": str(root),
            "query": needle,
            "scanned_files": scanned,
            "match_count": len(matches),
            "matches": matches,
            "code_cortex_front_door": True,
        }

    @router.get("/edgek/ide/code-intel")
    async def edgek_ide_code_intel(root_path: str = None, path: str = "", query: str = "", limit: int = 80):
        root = _root(root_path)
        target = _safe_relative(root, path)
        text = ""
        diagnostics: list[dict[str, Any]] = []
        symbols: list[dict[str, Any]] = []
        if target and target.exists() and target.is_file():
            text = target.read_text(encoding="utf-8", errors="replace")[:900000]
            symbols = _symbol_outline_for_text(path, text, max_symbols=300)
            for index, line in enumerate(text.splitlines(), start=1):
                if re.search(r"\b(TODO|FIXME|XXX)\b", line, re.IGNORECASE):
                    diagnostics.append({"severity": "warning", "line": index, "message": "Unresolved TODO/FIXME before SourcePlan apply."})
                if re.search(r"\b(eval|exec)\s*\(", line):
                    diagnostics.append({"severity": "error", "line": index, "message": "Dynamic execution requires policy/security review."})
                if re.search(r"\bexcept\s*:\s*$", line):
                    diagnostics.append({"severity": "warning", "line": index, "message": "Bare except hides failure evidence."})
                if re.search(r"\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"]{8,}", line, re.IGNORECASE):
                    diagnostics.append({"severity": "error", "line": index, "message": "Possible hard-coded secret; use provider secret setup."})
        base_query = query.strip() or (Path(path).stem if path else "")
        related_payload = await edgek_ide_text_search(root_path=str(root), query=base_query, limit=limit, max_files=900) if base_query else {"matches": []}
        related = []
        for item in related_payload.get("matches") or []:
            rel_path = str(item.get("path") or "")
            kind = _classify_related(rel_path)
            if rel_path == path:
                kind = "self_reference"
            related.append({**item, "relationship_kind": kind})
        return {
            "ok": True,
            "beast_object_type": "beast_ide_code_intel",
            "version": "1.0",
            "workspace_root": str(root),
            "path": path,
            "query": base_query,
            "symbols": symbols[:300],
            "diagnostics": diagnostics[:200],
            "related": related[: max(1, min(int(limit), 500))],
            "stale_context": {"active_sourceplan_stale": False, "guidance": "Reload/rebase SourcePlan before apply if hashes drift."},
            "code_cortex_front_door": True,
        }
    return None
