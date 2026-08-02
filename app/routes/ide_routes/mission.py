"""Mission routes for the BEAST IDE facade."""

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


def register_mission_routes(router: APIRouter, ctx: IdeRouteContext) -> dict[str, Any] | None:
    _json_hash = ctx._json_hash
    _latest_child_dir = ctx._latest_child_dir
    _mission_route_plan = ctx._mission_route_plan
    _operation_ledger = ctx._operation_ledger
    _read_json_file = ctx._read_json_file
    _receipt_command = ctx._receipt_command
    _render_runbook_markdown = ctx._render_runbook_markdown
    _request_base_url = ctx._request_base_url
    _root = ctx._root
    _sourceplan_action_contract = ctx._sourceplan_action_contract
    _sourceplan_repo_patch = ctx._sourceplan_repo_patch
    _timeline_entry = ctx._timeline_entry
    fallback_root = ctx.fallback_root

    @router.get("/edgek/ide/mission-timeline")
    async def edgek_ide_mission_timeline(
        root_path: str = None,
        objective: str = "",
        active_file: str = "",
        limit: int = 80,
    ):
        root = _root(root_path)
        query = objective or active_file or "BEAST desktop mission"
        cockpit = MissionCockpit(root).summary(objective=query, phase="desktop", risk="")
        evidence = EvidenceBus(root).summary(limit=max(1, min(int(limit), 200)))
        sessions = AgentSessionStore(root).list().get("sessions") or []
        worktrees = (cockpit.get("worktrees") or {}).get("tasks") if isinstance(cockpit.get("worktrees"), dict) else []
        sourceplans = cockpit.get("sourceplan_queue") if isinstance(cockpit.get("sourceplan_queue"), list) else []
        entries: list[dict[str, Any]] = []
        for item in sessions:
            if not isinstance(item, dict):
                continue
            entries.append(_timeline_entry(
                "agent_session",
                str(item.get("objective") or item.get("session_id") or "Agent session"),
                item.get("updated_at") or item.get("created_at"),
                status=str(item.get("status") or ""),
                detail=f"{item.get('mode') or 'mode'} · {item.get('provider') or 'provider'}",
                ref=str(item.get("session_id") or ""),
                payload=item,
            ))
        for item in worktrees or []:
            if not isinstance(item, dict):
                continue
            entries.append(_timeline_entry(
                "worktree",
                str(item.get("objective") or item.get("task_id") or "Worktree mission"),
                item.get("updated_at") or item.get("created_at"),
                status=str(item.get("status") or ""),
                detail=f"{item.get('risk') or 'risk'} · {item.get('branch') or ''}".strip(" ·"),
                ref=str(item.get("task_id") or ""),
                payload=item,
            ))
        for item in sourceplans:
            if not isinstance(item, dict):
                continue
            entries.append(_timeline_entry(
                "sourceplan",
                str(item.get("objective") or item.get("plan_id") or "SourcePlan"),
                item.get("updated_at") or item.get("created_at"),
                status=str(item.get("status") or ""),
                detail=str(item.get("provider") or item.get("risk_level") or ""),
                ref=str(item.get("plan_id") or ""),
                payload=item,
            ))
        for item in evidence.get("recent") or []:
            if not isinstance(item, dict):
                continue
            entries.append(_timeline_entry(
                "evidence",
                str(item.get("summary") or item.get("artifact_type") or "Evidence"),
                item.get("updated_at") or item.get("created_at"),
                status=str(item.get("status") or ""),
                detail=f"{item.get('source') or ''} · {item.get('artifact_type') or ''}".strip(" ·"),
                ref=str(item.get("receipt_id") or item.get("task_id") or ""),
                payload=item,
            ))
        entries.sort(key=lambda item: float(item.get("timestamp") or 0), reverse=True)
        return {
            "beast_object_type": "beast_ide_mission_timeline",
            "version": "1.0",
            "workspace_root": str(root),
            "objective": query,
            "count": len(entries),
            "entries": entries[: max(1, min(int(limit), 250))],
            "sources": {
                "agent_sessions": len(sessions),
                "worktrees": len(worktrees or []),
                "sourceplans": len(sourceplans),
                "evidence": int(evidence.get("receipt_count") or 0),
            },
        }

    @router.post("/edgek/ide/sourceplan/lifecycle")
    async def edgek_ide_sourceplan_lifecycle(request: Request, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        plan_id = str(plan.get("plan_id") or payload.get("plan_id") or "")
        if not plan:
            return {
                "ok": False,
                "beast_object_type": "beast_ide_sourceplan_lifecycle",
                "error": "missing_plan",
                "plan_id": plan_id,
            }
        client = BeastApiClient(_request_base_url(request), timeout=8.0, workspace=root)
        preview = client.preview_patch_plan(plan)
        scorecard = client.sourceplan_scorecard(plan)
        supplied_verification = payload.get("verification") if isinstance(payload.get("verification"), dict) else None
        if supplied_verification is not None:
            verification = ActionResult(
                ok=bool(supplied_verification.get("ok")),
                summary=str(supplied_verification.get("summary") or supplied_verification.get("message") or "verification supplied by governed verify endpoint"),
                data=supplied_verification,
                error=str(supplied_verification.get("error") or ""),
            )
        elif bool(payload.get("include_verification", True)):
            verification = client.verify_patch_plan(plan)
        else:
            verification = ActionResult(ok=False, summary="Verification not yet requested; use Verify SourcePlan.", data={"skipped": True}, error="")
        evidence = EvidenceBus(root).related(plan_id, limit=20) if plan_id else {"receipts": [], "match_count": 0}
        preview_data = preview.data or {}
        scorecard_data = scorecard.data or {}
        verification_data = verification.data or {}
        operations = preview_data.get("operations") if isinstance(preview_data.get("operations"), list) else []
        lifecycle = {
            "ok": bool(preview.ok),
            "beast_object_type": "beast_ide_sourceplan_lifecycle",
            "version": "1.0",
            "workspace_root": str(root),
            "plan_id": plan_id,
            "status": str(plan.get("status") or "draft"),
            "provider": str(plan.get("provider") or ""),
            "objective": str(plan.get("objective") or ""),
            "preview": preview_data,
            "scorecard": scorecard_data,
            "verification": verification_data,
            "evidence": evidence,
            "operation_count": len(operations),
            "selected_count": int(preview_data.get("selected_count") or 0),
            "stale_count": int(preview_data.get("stale_count") or 0),
            "risk": str(scorecard_data.get("risk") or scorecard_data.get("risk_level") or ""),
            "can_apply": bool(preview.ok and verification.ok and not preview_data.get("stale_count")),
            "errors": list(preview_data.get("errors") or []) + list(verification_data.get("errors") or []),
        }
        lifecycle["action_contract"] = _sourceplan_action_contract(plan, scorecard_data)
        lifecycle["operation_ledger"] = _operation_ledger(plan, preview_data, verification_data)
        lifecycle["stages"] = [
            {"stage": "draft", "ok": True, "detail": lifecycle["status"]},
            {"stage": "preview", "ok": bool(preview.ok), "detail": preview.error or preview.summary},
            {"stage": "scorecard", "ok": bool(scorecard.ok), "detail": scorecard.error or scorecard.summary},
            {"stage": "verify", "ok": bool(verification.ok), "detail": verification.error or verification.summary},
            {"stage": "evidence", "ok": bool((evidence.get("receipts") or [])), "detail": f"{evidence.get('match_count', 0)} related receipt(s)"},
        ]
        return lifecycle

    @router.get("/edgek/ide/receipts/chooser")
    async def edgek_ide_receipts_chooser(
        root_path: str = None,
        action: str = "",
        key: str = "",
        limit: int = 80,
    ):
        root = _root(root_path)
        bus = EvidenceBus(root)
        payload = bus.related(key, limit=limit) if key else bus.query(limit=limit)
        receipts = []
        for item in payload.get("receipts") or []:
            if not isinstance(item, dict):
                continue
            receipts.append({
                "receipt_id": item.get("receipt_id"),
                "task_id": item.get("task_id"),
                "artifact_type": item.get("artifact_type"),
                "source": item.get("source"),
                "status": item.get("status"),
                "summary": item.get("summary"),
                "artifact_path": item.get("artifact_path"),
                "updated_at": item.get("updated_at") or item.get("created_at"),
                "valid_for_action": bool(item.get("receipt_id")),
                "action": action or "inspect",
                "resolved_command": _receipt_command(item, action or "inspect"),
            })
        return {
            "beast_object_type": "beast_ide_receipt_chooser",
            "version": "1.0",
            "workspace_root": str(root),
            "action": action or "",
            "key": key or "",
            "receipt_count": len(receipts),
            "receipts": receipts,
            "read_only": True,
            "browser_execution_allowed": False,
        }

    @router.post("/edgek/ide/mission-runbook/export")
    async def edgek_ide_mission_runbook_export(request: Request, payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        active_file = str(payload.get("active_file") or "")
        objective = str(payload.get("objective") or active_file or "BEAST desktop mission")
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        timeline = await edgek_ide_mission_timeline(root_path=str(root), objective=objective, active_file=active_file, limit=120)
        evidence = EvidenceBus(root).summary(limit=80)
        lifecycle: dict[str, Any] = {}
        if plan:
            lifecycle = await edgek_ide_sourceplan_lifecycle(request, {"root_path": str(root), "plan": plan})
        runbook_id = "runbook_" + hashlib.sha256(f"{root}|{objective}|{time.time()}".encode("utf-8")).hexdigest()[:12]
        runbook_dir = root / ".beast" / "ide" / "runbooks" / runbook_id
        runbook_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "beast_object_type": "beast_ide_mission_runbook",
            "version": "1.0",
            "runbook_id": runbook_id,
            "workspace_root": str(root),
            "objective": objective,
            "active_file": active_file,
            "created_at": int(time.time()),
            "summary": {
                "timeline_entries": timeline.get("count", 0),
                "evidence_receipts": evidence.get("receipt_count", 0),
                "sourceplan_operations": (lifecycle.get("operation_ledger") or {}).get("operation_count", 0),
                "sourceplan_can_apply": bool(lifecycle.get("can_apply")),
            },
            "sourceplan": {
                "plan_id": plan.get("plan_id") if plan else "",
                "status": plan.get("status") if plan else "",
                "objective": plan.get("objective") if plan else "",
            },
            "action_contract": lifecycle.get("action_contract") or {},
            "operation_ledger": lifecycle.get("operation_ledger") or {},
            "policy_stages": lifecycle.get("stages") or [],
            "evidence": evidence,
            "timeline": timeline,
            "safety_boundary": {
                "read_only_export": True,
                "does_not_apply_source": True,
                "does_not_execute_commands": True,
                "receipts_are_authoritative": True,
            },
        }
        json_text = json.dumps(data, indent=2, sort_keys=True, default=str) + "\n"
        md_text = _render_runbook_markdown(data)
        json_path = runbook_dir / "runbook.json"
        md_path = runbook_dir / "runbook.md"
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_mission_runbook",
            artifact_path=json_path,
            artifact_hash="sha256:" + hashlib.sha256(json_text.encode("utf-8")).hexdigest(),
            source="desktop_ide",
            task_id=str(plan.get("plan_id") or runbook_id),
            status="exported",
            summary=objective,
            relationships={"markdown_path": str(md_path.relative_to(root)), "active_file": active_file},
            metadata={
                "runbook_id": runbook_id,
                "operation_count": int(data["summary"]["sourceplan_operations"]),
                "timeline_entries": int(data["summary"]["timeline_entries"]),
            },
        )
        return {
            "ok": True,
            "beast_object_type": "beast_ide_mission_runbook_export",
            "version": "1.0",
            "runbook_id": runbook_id,
            "paths": {"json": str(json_path), "markdown": str(md_path)},
            "manifest": data["summary"],
            "evidence_receipt": receipt,
            "markdown_preview": md_text[:4000],
        }

    @router.post("/edgek/ide/mission-runbook/verify")
    async def edgek_ide_mission_runbook_verify(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        runbook_id = str(payload.get("runbook_id") or "")
        runbook_dir = root / ".beast" / "ide" / "runbooks" / runbook_id if runbook_id else _latest_child_dir(root / ".beast" / "ide" / "runbooks")
        if not runbook_dir:
            return {"ok": False, "beast_object_type": "beast_ide_mission_runbook_verify", "error": "runbook_missing"}
        json_path = runbook_dir / "runbook.json"
        md_path = runbook_dir / "runbook.md"
        data = _read_json_file(json_path)
        json_text = json_path.read_text(encoding="utf-8") if json_path.exists() else ""
        md_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        runbook_id = str(data.get("runbook_id") or runbook_dir.name)
        related = EvidenceBus(root).related(runbook_id, limit=20)
        expected_json_hash = next(
            (str(item.get("artifact_hash") or "") for item in related.get("receipts") or [] if item.get("artifact_type") == "beast_ide_mission_runbook"),
            "",
        )
        actual_json_hash = "sha256:" + hashlib.sha256(json_text.encode("utf-8")).hexdigest() if json_text else ""
        checks = [
            {"check": "json_exists", "passed": json_path.exists(), "path": str(json_path)},
            {"check": "markdown_exists", "passed": md_path.exists(), "path": str(md_path)},
            {"check": "object_type_matches", "passed": data.get("beast_object_type") == "beast_ide_mission_runbook"},
            {"check": "json_hash_matches_evidence", "passed": bool(expected_json_hash) and expected_json_hash == actual_json_hash, "expected": expected_json_hash, "actual": actual_json_hash},
            {"check": "markdown_nonempty", "passed": bool(md_text.strip())},
        ]
        result = {
            "ok": all(item["passed"] for item in checks),
            "beast_object_type": "beast_ide_mission_runbook_verify",
            "version": "1.0",
            "runbook_id": runbook_id,
            "status": "valid" if all(item["passed"] for item in checks) else "invalid",
            "checks": checks,
            "paths": {"json": str(json_path), "markdown": str(md_path)},
            "related_evidence": related,
        }
        receipt_path = runbook_dir / "verify.json"
        receipt_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        EvidenceBus(root).register(
            artifact_type="beast_ide_mission_runbook_verify",
            artifact_path=receipt_path,
            artifact_hash=_json_hash(result),
            source="desktop_ide",
            task_id=runbook_id,
            status=result["status"],
            summary=f"Runbook verify {runbook_id}",
            relationships={"runbook_json": str(json_path.relative_to(root)) if root in json_path.parents else str(json_path)},
        )
        return result

    @router.get("/edgek/ide/mission-route")
    async def edgek_ide_mission_route(root_path: str = None, objective: str = "", active_file: str = "", risk: str = ""):
        return {
            **_mission_route_plan(objective or active_file or "BEAST desktop mission", active_file=active_file, risk=risk),
            "workspace_root": str(_root(root_path)),
        }

    @router.post("/edgek/ide/sourceplan/handoff-package")
    async def edgek_ide_sourceplan_handoff_package(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        if not plan:
            return {"ok": False, "beast_object_type": "beast_ide_sourceplan_handoff_package", "error": "missing_plan"}
        handoff_id = "handoff_" + hashlib.sha256(f"{root}|{plan.get('plan_id')}|{time.time()}".encode("utf-8")).hexdigest()[:12]
        folder = root / ".beast" / "ide" / "handoffs" / handoff_id
        folder.mkdir(parents=True, exist_ok=True)
        patch_text, operations, blocked = _sourceplan_repo_patch(root, plan)
        manifest = {
            "ok": not blocked and bool(operations),
            "beast_object_type": "beast_ide_sourceplan_handoff_package",
            "version": "1.0",
            "handoff_id": handoff_id,
            "plan_id": str(plan.get("plan_id") or ""),
            "created_at": int(time.time()),
            "workspace_root": str(root),
            "status": "ready" if operations and not blocked else "blocked",
            "direct_apply_allowed": False,
            "browser_apply_allowed": False,
            "git_write_allowed": False,
            "operations": operations,
            "blocked": blocked,
            "repo_patch_sha256": _hash_text(patch_text),
            "rules": [
                "Handoff packages patches and instructions only.",
                "BEAST Desktop does not apply this package directly.",
                "Operator must inspect and apply manually or re-enter SourcePlan apply.",
                "Secrets-like paths, absolute paths, and traversal are blocked.",
            ],
        }
        instructions = "\n".join([
            f"# BEAST Handoff Package: {handoff_id}",
            "",
            "Review `repo.patch` and `handoff-manifest.json` before doing anything outside BEAST.",
            "Do not run git write commands unless this package has been independently approved.",
            "",
            f"Status: {manifest['status']}",
            f"Operations: {len(operations)}",
            f"Blocked: {len(blocked)}",
            "",
        ])
        manifest_path = folder / "handoff-manifest.json"
        patch_path = folder / "repo.patch"
        instructions_path = folder / "APPLY_INSTRUCTIONS.md"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        patch_path.write_text(patch_text, encoding="utf-8")
        instructions_path.write_text(instructions, encoding="utf-8")
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_sourceplan_handoff_package",
            artifact_path=manifest_path,
            artifact_hash=_json_hash(manifest),
            source="desktop_ide",
            task_id=str(plan.get("plan_id") or handoff_id),
            status=manifest["status"],
            summary=str(plan.get("objective") or "SourcePlan handoff package"),
            relationships={"patch": str(patch_path.relative_to(root)), "instructions": str(instructions_path.relative_to(root))},
            metadata={"operation_count": len(operations), "blocked_count": len(blocked)},
        )
        return {**manifest, "paths": {"manifest": str(manifest_path), "patch": str(patch_path), "instructions": str(instructions_path)}, "evidence_receipt": receipt, "patch_preview": patch_text[:6000]}

    @router.post("/edgek/ide/release-readiness/check")
    async def edgek_ide_release_readiness_check(payload: dict[str, Any] = None):
        payload = payload or {}
        # This is a readiness check for the BEAST desktop product, not an
        # arbitrary selected coding workspace. Keep the workspace as context
        # for the receipt while always inspecting the installed IDE source.
        workspace_scope = _root(payload.get("root_path"))
        root = fallback_root
        def compute_release_readiness() -> dict[str, Any]:
            files = {
                "desktop_package": root / "desktop-ide" / "package.json",
                "desktop_main": root / "desktop-ide" / "main.js",
                # RC4 replaced the retired monolithic app.js with the release
                # shell and page modules.
                "desktop_renderer": root / "desktop-ide" / "renderer" / "js" / "beast-release-app.js",
                "desktop_html": root / "desktop-ide" / "renderer" / "index.html",
                "desktop_smoke": root / "desktop-ide" / "scripts" / "smoke-desktop-ide.js",
                "desktop_launch_smoke": root / "desktop-ide" / "scripts" / "launch-smoke-desktop-ide.js",
                "ide_routes": root / "app" / "routes" / "ide.py",
                "desktop_tests": root / "tests" / "test_desktop_ide_manifest.py",
            }

            def read_if_exists(path: Path) -> str:
                return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

            def run_smoke(script_path: Path, *, missing_error: str) -> dict[str, Any]:
                if not script_path.exists():
                    return {"ran": False, "ok": False, "error": missing_error}
                try:
                    completed = subprocess.run(
                        ["node", str(script_path)],
                        cwd=str(root / "desktop-ide"),
                        capture_output=True,
                        text=True,
                        timeout=20,
                        check=False,
                    )
                    return {
                        "ran": True,
                        "ok": completed.returncode == 0,
                        "returncode": completed.returncode,
                        "stdout": completed.stdout[-4000:],
                        "stderr": completed.stderr[-4000:],
                    }
                except Exception as exc:
                    return {"ran": True, "ok": False, "error": str(exc)}

            route_text = "\n".join([
                read_if_exists(files["ide_routes"]),
                *[read_if_exists(path) for path in sorted((root / "app" / "routes" / "ide_routes").glob("*.py"))],
            ])
            renderer_root = root / "desktop-ide" / "renderer" / "js"
            renderer_text = "\n".join(
                read_if_exists(path) for path in sorted(renderer_root.rglob("*.js"))
            )
            package_text = read_if_exists(files["desktop_package"])
            smoke_result = run_smoke(files["desktop_smoke"], missing_error="desktop smoke script missing")
            launch_smoke_result = run_smoke(files["desktop_launch_smoke"], missing_error="desktop launch smoke script missing")
            checks = [
                *[{"check": f"{name}_exists", "passed": path.exists(), "path": str(path)} for name, path in files.items()],
                {"check": "monaco_packaged", "passed": "monaco-editor" in package_text},
                {"check": "desktop_smoke_script_registered", "passed": '"smoke"' in package_text and "smoke-desktop-ide.js" in package_text},
                {"check": "desktop_smoke_passed", "passed": bool(smoke_result.get("ok")), "detail": smoke_result},
                {"check": "desktop_launch_smoke_registered", "passed": '"smoke:launch"' in package_text and "launch-smoke-desktop-ide.js" in package_text},
                {"check": "desktop_launch_smoke_passed", "passed": bool(launch_smoke_result.get("ok")), "detail": launch_smoke_result},
                {"check": "runbook_routes_present", "passed": "mission-runbook/export" in route_text and "mission-runbook/verify" in route_text},
                {"check": "handoff_route_present", "passed": "sourceplan/handoff-package" in route_text},
                {"check": "release_route_present", "passed": "release-readiness/check" in route_text},
                {"check": "learning_route_present", "passed": "learning-queue/propose" in route_text},
                {"check": "renderer_controls_present", "passed": "BeastWorkspacePage" in renderer_text and "BeastWorktreesPage" in renderer_text and "BeastRouter" in renderer_text},
                {"check": "terminal_maturity_controls_present", "passed": "startChat" in renderer_text and "terminal-chat-trace" in renderer_text and "terminal-chat-output" in renderer_text},
                {"check": "workspace_persistence_controls_present", "passed": "beast.v2.workspace.root" in renderer_text and "restoreTabs" in renderer_text and "setRoot" in renderer_text},
                {"check": "fake_gateway_not_used_in_ide_routes", "passed": ("http://gateway-" + "local") not in route_text},
            ]
            result = {
                "ok": all(item["passed"] for item in checks),
                "beast_object_type": "beast_ide_release_readiness",
                "version": "1.0",
                "created_at": int(time.time()),
                "status": "pass" if all(item["passed"] for item in checks) else "warn",
                "summary": {"checks": len(checks), "passed": len([item for item in checks if item["passed"]]), "failed": len([item for item in checks if not item["passed"]])},
                "checks": checks,
                "smoke": smoke_result,
                "launch_smoke": launch_smoke_result,
                "read_only": True,
                "workspace_scope": str(workspace_scope),
                "product_root": str(root),
            }
            out_dir = root / ".beast" / "ide" / "release" / "checks"
            storage_fallback = ""
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                # A selected workspace can be readable but not writable (for
                # example, a shared checkout). Readiness itself is non-mutating;
                # keep its receipt available in a scoped temporary location.
                digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
                out_dir = Path(tempfile.gettempdir()) / "beast-ide-release" / digest / "checks"
                out_dir.mkdir(parents=True, exist_ok=True)
                storage_fallback = str(out_dir)
            out_path = out_dir / f"release_{int(time.time())}.json"
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            if storage_fallback:
                result["receipt_storage"] = {"mode": "temporary_fallback", "path": storage_fallback}
            try:
                EvidenceBus(root).register(
                    artifact_type="beast_ide_release_readiness",
                    artifact_path=out_path,
                    artifact_hash=_json_hash(result),
                    source="desktop_ide",
                    task_id="desktop_ide_release",
                    status=result["status"],
                    summary=f"{result['summary']['passed']}/{result['summary']['checks']} readiness checks passed",
                )
            except OSError as exc:
                result["evidence_warning"] = f"Readiness receipt was saved, but workspace evidence registration was unavailable: {exc}"
            return result

        try:
            return await asyncio.to_thread(compute_release_readiness)
        except Exception as exc:
            return {
                "ok": False,
                "status": "error",
                "beast_object_type": "beast_ide_release_readiness",
                "read_only": True,
                "error": str(exc),
                "summary": {"checks": 0, "passed": 0, "failed": 0},
            }

    @router.get("/edgek/ide/tooling-snapshot")
    async def edgek_ide_tooling_snapshot(root_path: str = None, active_file: str = ""):
        root = _root(root_path)

        def build_tooling_snapshot() -> dict[str, Any]:
            def read_json(path: Path) -> dict[str, Any]:
                try:
                    return json.loads(path.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    return {}

            def command_version(command: str, args: list[str] = None) -> dict[str, Any]:
                args = args or ["--version"]
                if not shutil.which(command):
                    return {"ok": False, "command": command, "error": "not found"}
                try:
                    completed = subprocess.run(
                        [command, *args],
                        cwd=str(root),
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    output = (completed.stdout or completed.stderr or "").strip().splitlines()
                    return {
                        "ok": completed.returncode == 0,
                        "command": command,
                        "version": output[0] if output else "available",
                        "returncode": completed.returncode,
                    }
                except Exception as exc:
                    return {"ok": False, "command": command, "error": str(exc)}

            def syntax_check(rel_path: str) -> dict[str, Any]:
                if not rel_path:
                    return {"ok": True, "status": "idle", "detail": "No active file selected."}
                target = _safe_relative(root, rel_path)
                if not target or not target.exists():
                    return {"ok": False, "status": "blocked", "path": rel_path, "detail": "Active file is not inside the workspace or does not exist."}
                suffix = target.suffix.lower()
                try:
                    if suffix == ".json":
                        json.loads(target.read_text(encoding="utf-8", errors="replace"))
                        return {"ok": True, "status": "pass", "kind": "json", "path": rel_path}
                    if suffix == ".py":
                        ast.parse(target.read_text(encoding="utf-8", errors="replace"))
                        return {"ok": True, "status": "pass", "kind": "python", "path": rel_path}
                    if suffix in {".js", ".mjs", ".cjs"} and shutil.which("node"):
                        completed = subprocess.run(
                            ["node", "--check", str(target)],
                            cwd=str(root),
                            capture_output=True,
                            text=True,
                            timeout=10,
                            check=False,
                        )
                        return {
                            "ok": completed.returncode == 0,
                            "status": "pass" if completed.returncode == 0 else "warn",
                            "kind": "node",
                            "path": rel_path,
                            "stdout": completed.stdout[-2000:],
                            "stderr": completed.stderr[-2000:],
                        }
                    return {"ok": True, "status": "skipped", "kind": suffix or "text", "path": rel_path, "detail": "No syntax checker registered for this file type."}
                except Exception as exc:
                    return {"ok": False, "status": "warn", "path": rel_path, "error": str(exc)}

            root_package = read_json(root / "package.json")
            desktop_package = read_json(root / "desktop-ide" / "package.json")
            scripts = {
                "root": sorted((root_package.get("scripts") or {}).keys()),
                "desktop": sorted((desktop_package.get("scripts") or {}).keys()),
            }
            cursor_config = root / ".cursor" / "mcp.json"
            snapshot = {
                "ok": True,
            "beast_object_type": "beast_ide_tooling_snapshot",
            "version": "1.0",
            "source": "gateway",
            "repoRoot": str(root),
            "activeFile": active_file,
            "syntax": syntax_check(active_file),
            "linting": {
                "scripts": scripts,
                "has_root_lint": any("lint" in item for item in scripts["root"]),
                "has_desktop_smoke": "smoke" in scripts["desktop"],
                "has_launch_smoke": "smoke:launch" in scripts["desktop"],
                "recommendation": "Use the project lint script through the governed terminal." if any("lint" in item for item in scripts["root"]) else "No root lint script detected; use syntax checks and focused tests until a lint contract is added.",
            },
            "mcp": {
                "configured": cursor_config.exists(),
                "cursor_config": str(cursor_config),
                "expected_routes": ["/edgek/mcp/state", "/edgek/mcp/servers", "/edgek/mcp/audit", "/edgek/mcp/executions", "/edgek/mcp/approvals"],
                "status": "configured" if cursor_config.exists() else "no local .cursor/mcp.json",
            },
            "plugins": {
                "vscode_extension_present": (root / "vscode-extension").exists(),
                "desktop_ide_present": (root / "desktop-ide").exists(),
                "expected_routes": ["/edgek/plugins", "/edgek/plugins/manifest/prepare", "/edgek/plugins/manifest/validate", "/edgek/plugins/install"],
                "status": "local surfaces present" if (root / "vscode-extension").exists() or (root / "desktop-ide").exists() else "no local plugin surfaces detected",
            },
            "environments": [
                command_version("python3", ["--version"]),
                command_version("node", ["--version"]),
                command_version("npm", ["--version"]),
                command_version("git", ["--version"]),
            ],
            "read_only": True,
        }
            return snapshot

        return await asyncio.to_thread(build_tooling_snapshot)
    return {'sourceplan_lifecycle': edgek_ide_sourceplan_lifecycle}
