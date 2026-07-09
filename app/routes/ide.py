"""IDE shell route family.

These routes are intentionally presentation-friendly facades over existing
BEAST kernel owners. The VS Code extension should not rebuild Mission Cockpit,
Code Cortex, Evidence Bus, and ADR state by hand.
"""

from __future__ import annotations

import asyncio
import ast
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.cli.api import BeastApiClient
from app.kernel.compute.action_ir import ACTION_IR_KIND, ActionIR
from app.kernel.compute.action_resolver import build_file_references, resolve_action_ir
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.security.safety_governor import SafetyGovernor
from app.kernel.workspaces import system_inspector
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.kernel.workspaces.worktree_forge import WorktreeForge


def build_ide_router(default_root: str | Path, *, code_cortex_router: Any) -> APIRouter:
    router = APIRouter()
    fallback_root = Path(default_root).expanduser().resolve()

    def _root(value: Any = None) -> Path:
        return Path(value or fallback_root).expanduser().resolve()

    def _raw_hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def _hash_text(text: str) -> str:
        return "sha256:" + _raw_hash_text(text)

    def _extract_json_object(text: str) -> dict[str, Any]:
        body = str(text or "").strip()
        fence = re.search(r"```(?:json|action_ir)?\s*(\{[\s\S]*?\})\s*```", body, re.IGNORECASE)
        if fence:
            body = fence.group(1).strip()
        starts = [index for index in (body.find("{"), body.find("[")) if index >= 0]
        if not starts:
            return {}
        start = min(starts)
        for end in range(len(body), start, -1):
            candidate = body[start:end].strip()
            try:
                payload = json.loads(candidate)
                if isinstance(payload, list):
                    return {"actions": payload}
                return payload if isinstance(payload, dict) else {}
            except Exception:
                continue
        return {}

    def _action_ir_retry_prompt(objective: str, previous_output: str, allowed_files: list[str]) -> str:
        allowed = "\n".join(f"- {path}" for path in allowed_files) or "- provide one allowed file first"
        bounded_previous = str(previous_output or "")[:8000]
        return (
            "Return BEAST Action IR JSON only. Do not include markdown, prose, or explanation.\n\n"
            f"Objective: {objective or 'Convert the prior answer into a governed file edit.'}\n"
            "Allowed files:\n"
            f"{allowed}\n\n"
            f"Schema:\n{{\"kind\": \"{ACTION_IR_KIND}\", \"objective\": \"...\", \"actions\": [{{\"type\": \"replace_exact\", \"target\": {{\"path\": \"relative/file.py\"}}, \"old\": \"exact old snippet\", \"new\": \"replacement\"}}]}}\n\n"
            "Rules:\n"
            "1. Use only allowed files.\n"
            "2. Use exact old snippets that exist in the file today.\n"
            "3. Emit the smallest valid set of replace_exact actions.\n"
            "4. Return one JSON object and nothing else.\n\n"
            "Previous answer to convert:\n"
            f"{bounded_previous}"
        )

    def _compile_agent_action_ir_sourceplan(
        root: Path,
        *,
        output: str,
        provider: str,
        requested_files: list[str],
        active_file: str = "",
        objective: str = "",
    ) -> dict[str, Any]:
        allowed = [str(item) for item in requested_files if item]
        if active_file:
            allowed.insert(0, str(active_file))
        allowed = list(dict.fromkeys(allowed))
        parsed = _extract_json_object(output)
        is_action_ir = str(parsed.get("kind") or "") == ACTION_IR_KIND or isinstance(parsed.get("actions"), list)
        if not is_action_ir:
            return {
                "ok": False,
                "status": "not_action_ir",
                "error": "Agent output did not contain BEAST Action IR JSON.",
                "requires_operator_translation": True,
                "missing_context_questions": [
                    "Which exact file path and symbol/range should be edited?",
                    "What exact old snippet or anchor should be replaced?",
                    "Should BEAST draft a SourcePlan from the current editor selection instead?",
                ],
                "retry_options": [
                    {"id": "ask_for_action_ir", "label": "Ask agent for BEAST Action IR only"},
                    {"id": "narrow_selection", "label": "Narrow editor selection and retry"},
                    {"id": "sourceplan_from_selection", "label": "Use SourcePlan from selection"},
                ],
                "action_ir_schema": {
                    "kind": ACTION_IR_KIND,
                    "actions": [{"type": "replace_exact", "target": {"path": "relative/file.py"}, "old": "exact old snippet", "new": "replacement"}],
                },
            }
        if not allowed:
            return {
                "ok": False,
                "status": "no_allowed_files",
                "error": "No allowed context files were provided for Action IR resolution.",
                "missing_context_questions": ["Select or open the file the agent is allowed to edit."],
                "retry_options": [{"id": "include_active_file", "label": "Include active file and retry"}],
            }
        try:
            file_refs = build_file_references(root, allowed)
            action_ir = ActionIR.from_dict(parsed)
            resolved, non_mutating = resolve_action_ir(root, action_ir, file_refs, allowed)
            operations = []
            for index, item in enumerate(resolved):
                action = item.action
                operations.append({
                    "op_id": str(action.id or f"a{index + 1}"),
                    "op": "replace_exact",
                    "path": item.path,
                    "old": item.old,
                    "new": item.new,
                    "description": action.intent or f"Action IR {action.type} for {item.path}",
                    "beast_managed": False,
                    "source_edit": True,
                    "provider_generated": True,
                    "selected": True,
                    "expected_hash": item.expected_sha256,
                    "action_ir_id": action.id,
                    "action_ir_type": action.type,
                    "anchor_ref": action.target.anchor_ref,
                    "symbol": action.target.symbol,
                    "resolver": "action_ir.resolve_action_ir",
                })
            plan_id = "ide_air_" + hashlib.sha256(f"{root}|{provider}|{time.time()}".encode("utf-8")).hexdigest()[:12]
            plan = {
                "plan_id": plan_id,
                "kind": "beast_ide_agent_action_ir_sourceplan",
                "status": "draft_requires_approval",
                "objective": str(action_ir.objective or objective or "Apply agent Action IR through BEAST IDE"),
                "provider": provider,
                "workspace": str(root),
                "risk_level": "high",
                "approval_required": True,
                "provider_generated": True,
                "requires_operator_translation": False,
                "action_ir": action_ir.to_dict(),
                "output_evidence": {
                    "contract": ACTION_IR_KIND,
                    "schema_valid": True,
                    "path_valid": True,
                    "operation_valid": True,
                    "diff_compiled": True,
                    "compiled_operation_count": len(operations),
                },
                "non_mutating_requests": [item.to_dict() for item in non_mutating],
                "context_files": [{"path": path} for path in allowed],
                "files_allowed": allowed,
                "files_blocked": [],
                "operations": operations,
                "selected_operations": [op["op_id"] for op in operations],
                "apply_policy": {"source_edits_require": ["selected file", "expected hash", "approval", "verification", "rollback"], "rollback_required": True, "run_py_compile": True, "run_tests": False},
                "created_at": int(time.time()),
            }
            receipt = EvidenceBus(root).register(
                artifact_type="beast_ide_agent_action_ir_sourceplan",
                artifact_path=root / ".beast" / "ide" / "agent-action-ir",
                artifact_hash=_json_hash(plan),
                source="desktop_ide",
                task_id=plan_id,
                status="compiled_action_ir",
                summary=f"Compiled {len(operations)} Action IR operation(s) from agent output",
                metadata={"operation_count": len(operations), "provider": provider},
            )
            return {"ok": True, "status": "compiled_action_ir", "plan": plan, "operation_count": len(operations), "evidence_receipt": receipt}
        except Exception as exc:
            return {
                "ok": False,
                "status": "action_ir_rejected",
                "error": str(exc),
                "requires_operator_translation": True,
                "allowed_files": allowed,
                "missing_context_questions": [
                    "Does the Action IR old snippet exactly match the current file?",
                    "Is the target file included in the allowed context files?",
                    "Would a symbol-scoped range avoid stale or ambiguous context?",
                ],
                "retry_options": [
                    {"id": "reload_context", "label": "Reload file/context and retry"},
                    {"id": "ask_for_exact_old", "label": "Ask agent for exact old/new snippets"},
                    {"id": "sourceplan_from_selection", "label": "Draft from current selection"},
                ],
            }

    def _safe_relative(root: Path, rel: str) -> Path | None:
        if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            return None
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def _request_base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    def _classify_related(path: str) -> str:
        lowered = path.lower()
        if any(part in lowered for part in ("test", "spec", "__tests__")):
            return "test"
        if any(part in lowered for part in ("route", "router", "endpoint", "api")):
            return "route"
        if any(part in lowered for part in ("controller", "handler", "view", "page")):
            return "surface"
        if any(part in lowered for part in ("model", "schema", "entity")):
            return "model"
        return "related"

    def _symbol_outline_for_text(path: str, text: str, max_symbols: int = 300) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        suffix = Path(path).suffix.lower()
        if suffix == ".py":
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        kind = "class" if isinstance(node, ast.ClassDef) else "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                        symbols.append({
                            "name": node.name,
                            "kind": kind,
                            "line_start": int(getattr(node, "lineno", 1)),
                            "line_end": int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
                            "col_start": int(getattr(node, "col_offset", 0)) + 1,
                            "signature": "",
                        })
            except Exception:
                symbols = []
        if not symbols:
            patterns = [
                ("class", re.compile(r"^\s*class\s+([A-Za-z_][\w]*)", re.MULTILINE)),
                ("function", re.compile(r"^\s*(?:async\s+def|def|function)\s+([A-Za-z_][\w]*)", re.MULTILINE)),
                ("export", re.compile(r"^\s*export\s+(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z_][\w]*)", re.MULTILINE)),
            ]
            line_offsets = [0]
            for match in re.finditer(r"\n", text):
                line_offsets.append(match.end())
            def line_for_offset(offset: int) -> int:
                # Small enough for IDE outlines; avoids importing bisect for one call.
                line = 1
                for index, start in enumerate(line_offsets):
                    if start > offset:
                        break
                    line = index + 1
                return line
            for kind, pattern in patterns:
                for match in pattern.finditer(text):
                    line = line_for_offset(match.start())
                    symbols.append({
                        "name": match.group(1),
                        "kind": kind,
                        "line_start": line,
                        "line_end": line,
                        "col_start": max(1, match.start(1) - text.rfind("\n", 0, match.start(1))),
                        "signature": match.group(0).strip(),
                    })
        symbols.sort(key=lambda item: (int(item.get("line_start") or 0), str(item.get("name") or "")))
        return symbols[: max(1, min(int(max_symbols), 1000))]

    def _timeline_entry(kind: str, title: str, timestamp: Any, *, status: str = "", detail: str = "", ref: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            ts = float(timestamp or 0)
        except (TypeError, ValueError):
            ts = 0.0
        return {
            "kind": kind,
            "title": title,
            "status": status,
            "detail": detail,
            "ref": ref,
            "timestamp": ts,
            "payload": payload or {},
        }

    def _json_hash(payload: Any) -> str:
        body = json.dumps(payload, sort_keys=True, default=str)
        return "sha256:" + hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()

    def _sourceplan_action_contract(plan: dict[str, Any], scorecard: dict[str, Any]) -> dict[str, Any]:
        operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        files = sorted({str(op.get("path") or "") for op in operations if isinstance(op, dict) and op.get("path")})
        policy = plan.get("apply_policy") if isinstance(plan.get("apply_policy"), dict) else {}
        return {
            "beast_object_type": "beast_ide_action_contract_summary",
            "version": "1.0",
            "plan_id": str(plan.get("plan_id") or ""),
            "intent": str(plan.get("objective") or ""),
            "risk": str(plan.get("risk_level") or scorecard.get("risk") or scorecard.get("risk_level") or "unknown"),
            "status": str(plan.get("status") or "draft"),
            "approval_required": bool(plan.get("approval_required", True)),
            "sandbox_or_worktree_first": bool(plan.get("requires_worktree") or plan.get("worktree_task_id") or policy.get("worktree_required")),
            "allowed_write_roots": [str(plan.get("workspace") or "")],
            "files_allowed": list(plan.get("files_allowed") or files),
            "blocked_actions": [
                "direct_file_write",
                "git_push",
                "deploy",
                "direct_crystalization_write",
                "ungoverned_shell",
            ],
            "verification_required": True,
            "rollback_required": bool(policy.get("rollback_required", True)),
            "evidence_required": True,
            "rules": [
                "Approval records operator intent; it does not bypass SourcePlan checks.",
                "Apply requires selected operations, expected hashes, verification, rollback, and evidence closure.",
                "Workspace graph context is advisory; receipts and rollback snapshots are authoritative.",
            ],
        }

    def _operation_ledger(plan: dict[str, Any], preview: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        plan_ops = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        preview_ops = preview.get("operations") if isinstance(preview.get("operations"), list) else []
        selected_ids = {
            str(item) for item in (
                plan.get("selected_operations") if isinstance(plan.get("selected_operations"), list) else []
            )
        }
        if not selected_ids:
            selected_ids = {
                str(op.get("op_id") or f"op_{index + 1}")
                for index, op in enumerate(plan_ops)
                if isinstance(op, dict) and op.get("selected", True) is not False
            }
        preview_by_id = {
            str(op.get("op_id") or op.get("operation_id") or f"op_{index + 1}"): op
            for index, op in enumerate(preview_ops)
            if isinstance(op, dict)
        }
        verify_errors = verification.get("errors") if isinstance(verification.get("errors"), list) else []
        rows = []
        for index, op in enumerate(plan_ops):
            if not isinstance(op, dict):
                continue
            op_id = str(op.get("op_id") or op.get("operation_id") or f"op_{index + 1}")
            preview_op = preview_by_id.get(op_id, {})
            before = str(op.get("old") or op.get("old_text") or preview_op.get("old_text") or "")
            after = str(op.get("new") or op.get("new_text") or op.get("content") or preview_op.get("new_text") or "")
            stale_reason = str(preview_op.get("stale_reason") or op.get("stale_reason") or "")
            selected = op_id in selected_ids
            rows.append({
                "operation_id": op_id,
                "selected": selected,
                "status": "stale" if stale_reason else "selected" if selected else "skipped",
                "path": str(op.get("path") or preview_op.get("path") or ""),
                "operation": str(op.get("op") or op.get("type") or preview_op.get("op") or "edit"),
                "description": str(op.get("description") or preview_op.get("description") or ""),
                "before_sha256": _hash_text(before) if before else str(op.get("expected_hash") or ""),
                "after_sha256": _hash_text(after) if after else "",
                "stale_reason": stale_reason,
                "rollback_required": True,
                "verification_status": "blocked" if stale_reason or verify_errors else "pending" if not verification else "passed",
                "evidence_status": "pending",
                "hunk_count": len(preview_op.get("hunks") or preview_op.get("diff_lines") or []),
            })
        blocked = preview.get("blocked") if isinstance(preview.get("blocked"), list) else []
        return {
            "beast_object_type": "beast_ide_sourceplan_operation_ledger",
            "version": "1.0",
            "plan_id": str(plan.get("plan_id") or ""),
            "operation_count": len(rows),
            "selected_count": len([row for row in rows if row.get("selected")]),
            "stale_count": len([row for row in rows if row.get("stale_reason")]),
            "blocked_count": len(blocked),
            "operations": rows,
            "blocked_operations": blocked,
            "ledger_hash": _json_hash({"plan_id": plan.get("plan_id"), "operations": rows, "blocked": blocked}),
        }

    def _receipt_command(receipt: dict[str, Any], action: str) -> str:
        receipt_id = str(receipt.get("receipt_id") or "")
        task_id = str(receipt.get("task_id") or "")
        templates = {
            "sourceplan.apply": f"Use receipt {receipt_id} as evidence before SourcePlan apply.",
            "sourceplan.rollback": f"Use receipt {receipt_id} to inspect rollback/evidence before rollback.",
            "worktree.promote": f"Use receipt {receipt_id} while promoting worktree task {task_id or '<task-id>'}.",
            "terminal.execute": f"Use receipt {receipt_id} as command evidence for task {task_id or '<task-id>'}.",
        }
        return templates.get(action, f"Inspect receipt {receipt_id}")

    def _render_runbook_markdown(data: dict[str, Any]) -> str:
        lines = [
            f"# BEAST Mission Runbook: {data.get('runbook_id')}",
            "",
            f"- Workspace: `{data.get('workspace_root')}`",
            f"- Objective: {data.get('objective') or 'BEAST desktop mission'}",
            f"- Created: {data.get('created_at')}",
            f"- Active file: `{data.get('active_file') or 'none'}`",
            "",
            "## Summary",
            "",
        ]
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        for key, value in summary.items():
            lines.append(f"- {key}: {value}")
        contract = data.get("action_contract") if isinstance(data.get("action_contract"), dict) else {}
        if contract:
            lines.extend(["", "## Action Contract", ""])
            for key in ("plan_id", "intent", "risk", "status", "approval_required", "rollback_required", "evidence_required"):
                lines.append(f"- {key}: {contract.get(key)}")
        ledger = data.get("operation_ledger") if isinstance(data.get("operation_ledger"), dict) else {}
        rows = ledger.get("operations") if isinstance(ledger.get("operations"), list) else []
        lines.extend(["", "## SourcePlan Operations", ""])
        if rows:
            for row in rows:
                lines.append(f"- `{row.get('operation_id')}` {row.get('status')} `{row.get('path')}` {row.get('operation')}")
        else:
            lines.append("- No SourcePlan operations captured.")
        lines.extend(["", "## Evidence Tail", ""])
        evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
        for item in evidence.get("recent") or evidence.get("receipts") or []:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('receipt_id')}` {item.get('source')} {item.get('artifact_type')} {item.get('status')}")
        return "\n".join(lines) + "\n"

    def _read_json_file(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _latest_child_dir(parent: Path) -> Path | None:
        if not parent.exists():
            return None
        dirs = [path for path in parent.iterdir() if path.is_dir()]
        if not dirs:
            return None
        return sorted(dirs, key=lambda path: path.stat().st_mtime, reverse=True)[0]

    def _mission_route_plan(objective: str, active_file: str = "", risk: str = "") -> dict[str, Any]:
        text = f"{objective} {active_file} {risk}".lower()
        route = ["Mission"]
        if any(term in text for term in ("model", "provider", "nim", "ollama", "route")):
            route.append("Models")
        if any(term in text for term in ("agent", "session", "prompt", "tool")):
            route.append("Agents")
        if any(term in text for term in ("code", "file", "edit", "patch", "sourceplan", "worktree", "test")) or active_file:
            route.append("Tools")
        if any(term in text for term in ("review", "verify", "risk", "approval", "apply", "rollback", "test")):
            route.append("Review")
        if any(term in text for term in ("evidence", "receipt", "runbook", "audit", "proof")):
            route.append("Evidence")
        if any(term in text for term in ("crystal", "lattice", "memory", "learn", "promote")):
            route.append("Crystalization")
        if "Evidence" not in route and "Crystalization" in route:
            route.insert(route.index("Crystalization"), "Evidence")
        route = list(dict.fromkeys(route + ["Evidence"]))
        mcp_map = {
            "Mission": ["mission_cockpit"],
            "Models": ["provider_registry", "capability_plane"],
            "Agents": ["agent_sessions"],
            "Tools": ["code_cortex", "sourceplan", "worktree_forge"],
            "Review": ["policy_gate", "verifier"],
            "Evidence": ["evidence_bus", "runbook"],
            "Crystalization": ["mission_lattice", "memory_hull"],
        }
        return {
            "beast_object_type": "beast_ide_mission_route",
            "version": "1.0",
            "objective": objective,
            "active_file": active_file,
            "risk": risk,
            "active_face": route[0] if route else "Mission",
            "route": [
                {
                    "step": index + 1,
                    "face": face,
                    "status": "active" if index == 0 else "planned",
                    "tools": mcp_map.get(face, []),
                }
                for index, face in enumerate(route)
            ],
            "approval_required": any(term in text for term in ("edit", "write", "apply", "execute", "promote", "rollback")) or risk in {"high", "critical"},
            "direct_mutation_allowed": False,
        }

    def _ide_action_manifest() -> list[dict[str, Any]]:
        def action(
            action_id: str,
            label: str,
            page: str,
            description: str,
            *,
            surface: str = "desktop",
            risk: str = "low",
            handler: str = "",
            endpoint: str = "",
            method: str = "GET",
            tags: list[str] | None = None,
            approval_required: bool = False,
            sourceplan_required: bool = False,
            worktree_recommended: bool = False,
            provider_required: bool = False,
            local_fallback: bool = True,
        ) -> dict[str, Any]:
            return {
                "id": action_id,
                "label": label,
                "page": page,
                "surface": surface,
                "description": description,
                "risk": risk,
                "client_handler": handler or action_id.replace(".", "_"),
                "endpoint": endpoint,
                "method": method,
                "tags": tags or [],
                "approval_required": approval_required,
                "sourceplan_required": sourceplan_required,
                "worktree_recommended": worktree_recommended,
                "provider_required": provider_required,
                "local_fallback": local_fallback,
                "direct_mutation_allowed": False,
            }

        return [
            action("mission.refresh_snapshot", "Refresh Mission Snapshot", "mission", "Reload cockpit, policy, evidence, sessions, worktrees, and context.", handler="refreshSnapshot", endpoint="/edgek/ide/snapshot", tags=["mission", "status"]),
            action("mission.route", "Plan Mission Route", "mission", "Map the current objective through BEAST faces and governance steps.", handler="refreshMissionRoute", endpoint="/edgek/ide/mission-route", tags=["mission", "route"]),
            action("editor.save_sourceplan", "Save Via SourcePlan", "source", "Draft and apply staged editor changes through SourcePlan, approval, rollback, and evidence.", handler="saveViaSourcePlan", tags=["editor", "save", "sourceplan"], risk="high", approval_required=True, sourceplan_required=True, local_fallback=False),
            action("editor.revert_buffer", "Revert Editor Buffer", "source", "Discard staged editor changes and return to the last loaded file content.", handler="revertEditorBuffer", tags=["editor", "buffer"], approval_required=True),
            action("editor.reload_file", "Reload Active File", "source", "Reload the active file from disk and clear stale editor/SourcePlan state.", handler="reloadActiveFileFromDisk", tags=["editor", "reload"], approval_required=True),
            action("sourceplan.draft_editor", "Draft SourcePlan From Editor", "source", "Compile the active staged editor buffer into a governed SourcePlan draft.", handler="sourcePlanDraft", endpoint="/edgek/ide/sourceplan/from-editor", method="POST", tags=["sourceplan", "editor"], sourceplan_required=True),
            action("sourceplan.draft_selection", "Draft SourcePlan From Selection", "source", "Use the current editor selection as the seed for a SourcePlan-safe change.", handler="sourcePlanSelectionDraft", endpoint="/edgek/ide/sourceplan/from-selection", method="POST", tags=["sourceplan", "selection"], sourceplan_required=True),
            action("sourceplan.lifecycle", "Refresh SourcePlan Lifecycle", "source", "Rebuild the scorecard, action contract, operation ledger, and preview.", handler="refreshSourcePlanLifecycle", endpoint="/edgek/ide/sourceplan/lifecycle", method="POST", tags=["sourceplan", "policy"]),
            action("sourceplan.verify", "Verify SourcePlan", "source", "Run the verifier before any apply attempt.", handler="verifySourcePlan", endpoint="/edgek/sourceplan/verify", method="POST", tags=["sourceplan", "verify"], approval_required=True, sourceplan_required=True),
            action("sourceplan.apply", "Apply SourcePlan", "source", "Apply only after approval, hash checks, verification, rollback capture, and evidence closure.", handler="applySourcePlan", endpoint="/edgek/sourceplan/apply", method="POST", tags=["sourceplan", "apply"], risk="high", approval_required=True, sourceplan_required=True, worktree_recommended=True, local_fallback=False),
            action("sourceplan.export_runbook", "Export Mission Runbook", "source", "Export a Markdown runbook from the current SourcePlan, selected receipts, and verification state.", handler="exportMissionRunbook", endpoint="/edgek/ide/mission-runbook/export", method="POST", tags=["runbook", "evidence"]),
            action("sourceplan.verify_runbook", "Verify Runbook", "source", "Check runbook completeness before handoff or promotion.", handler="verifyMissionRunbook", endpoint="/edgek/ide/mission-runbook/verify", method="POST", tags=["runbook", "verify"]),
            action("sourceplan.handoff_package", "Create Handoff Package", "source", "Bundle SourcePlan, runbook, receipts, and action ledger for operator review.", handler="createHandoffPackage", endpoint="/edgek/ide/sourceplan/handoff-package", method="POST", tags=["handoff", "evidence"]),
            action("sourceplan.propose_learning", "Propose Learning", "source", "Queue a verified SourcePlan pattern for Crystal/Lattice learning without auto-promotion.", handler="proposeLearning", endpoint="/edgek/ide/learning-queue/propose", method="POST", tags=["lattice", "learning"], approval_required=True),
            action("code.symbol_search", "Search Workspace Symbols", "source", "Find functions/classes/routes across the workspace and open them as symbol-sized ranges.", handler="runSymbolSearch", endpoint="/edgek/ide/symbol-search", tags=["code", "symbol", "cortex"]),
            action("code.intel", "Refresh Code Intelligence", "source", "Load symbols, diagnostics, stale-context guidance, and related tests/routes from Code Cortex.", handler="refreshCodeIntelligence", endpoint="/edgek/ide/code-intel", tags=["code", "diagnostics", "references", "cortex"]),
            action("agents.create", "Create Agent Session", "agents", "Start a persistent governed session with mode, budget, tools, files, provider, and model.", handler="createAgentSession", endpoint="/edgek/ide/agent-sessions/create", method="POST", tags=["agent", "session"], provider_required=True),
            action("agents.send_prompt", "Send Agent Request", "agents", "Send the current prompt and context pack to the selected provider route.", handler="sendAgentPrompt", endpoint="/edgek/ide/agent-sessions/{session_id}/run-events", tags=["agent", "provider"], provider_required=True),
            action("agents.output_to_sourceplan", "Convert Agent Output To SourcePlan", "agents", "Compile selected agent output into SourcePlan operations or a blocked translation note.", handler="agentOutputToSourcePlan", endpoint="/edgek/ide/agent-sessions/sourceplan-draft", method="POST", tags=["agent", "sourceplan"], sourceplan_required=True),
            action("agents.output_action_ir", "Compile Agent Action IR", "agents", "Resolve BEAST Action IR from agent output into exact SourcePlan operations when safe.", handler="agentOutputToSourcePlan", endpoint="/edgek/ide/agent-sessions/action-ir-sourceplan", method="POST", tags=["agent", "action_ir", "sourceplan"], sourceplan_required=True),
            action("worktrees.create", "Create Mission Worktree", "worktrees", "Create an isolated mission workspace for high-risk or multi-file work.", handler="createWorktreeMission", endpoint="/edgek/ide/worktree-mission/create", method="POST", tags=["worktree", "mission"], worktree_recommended=True),
            action("worktrees.verify", "Verify Worktree Mission", "worktrees", "Run verification inside the selected mission worktree and save evidence.", handler="testWorktreeMission", endpoint="/edgek/ide/worktree-mission/test", method="POST", tags=["worktree", "verify"], approval_required=True),
            action("worktrees.diff", "Browse Worktree Diff", "worktrees", "Inspect the selected mission worktree diff before promotion.", handler="browseWorktreeDiff", endpoint="/edgek/ide/worktree-mission/diff", method="POST", tags=["worktree", "diff"]),
            action("worktrees.sourceplan_draft", "Draft Worktree Promotion SourcePlan", "worktrees", "Convert a bounded worktree diff into a SourcePlan promotion draft.", handler="draftWorktreeSourcePlan", endpoint="/edgek/ide/worktree-mission/sourceplan-draft", method="POST", tags=["worktree", "sourceplan"], sourceplan_required=True),
            action("worktrees.close", "Close Worktree Mission", "worktrees", "Close the selected mission worktree only after evidence and promotion status are visible.", handler="closeWorktreeMission", endpoint="/edgek/ide/worktree-mission/close", method="POST", tags=["worktree", "cleanup"], approval_required=True),
            action("evidence.search", "Search Evidence Bus", "evidence", "Filter receipts by source, artifact type, status, task, plan, receipt, or relation.", handler="searchEvidenceDrawer", endpoint="/edgek/evidence-bus/query", tags=["evidence", "search"]),
            action("evidence.choose_receipts", "Choose Evidence Receipts", "evidence", "Attach receipts to a governed action before export, apply, or handoff.", handler="chooseReceiptsForAction", endpoint="/edgek/ide/receipts/chooser", tags=["evidence", "receipt"]),
            action("terminal.classify", "Classify Terminal Command", "terminal", "Ask Safety Governor for policy before running any workspace command.", handler="classifyTerminalCommand", endpoint="/edgek/safety-governor/classify-command", method="POST", tags=["terminal", "policy"]),
            action("terminal.execute", "Execute Governed Command", "terminal", "Run only after Safety Governor classification and capture stdout/stderr as evidence.", handler="executeTerminalCommand", endpoint="/edgek/safety-governor/execute-command", method="POST", tags=["terminal", "evidence"], risk="high", approval_required=True, local_fallback=False),
            action("terminal.stream", "Stream Governed Command", "terminal", "Run after Safety Governor classification and stream stdout/stderr into evidence on close.", handler="executeTerminalCommand", endpoint="/edgek/ide/terminal/stream", tags=["terminal", "streaming", "evidence"], risk="high", approval_required=True, local_fallback=False),
            action("providers.refresh", "Refresh Provider Setup", "providers", "Reload selected provider, registry, secret route, and live smoke readiness.", handler="refreshProviderSetup", endpoint="/edgek/providers/registry", tags=["provider", "setup"]),
            action("providers.smoke_nvidia", "Smoke NVIDIA NIM", "providers", "Run an explicit NVIDIA NIM readiness check for the selected model.", handler="smokeNvidiaProvider", endpoint="/edgek/providers/nvidia-nim/live-smoke", method="POST", tags=["provider", "nvidia"], provider_required=True, local_fallback=False),
            action("tooling.refresh", "Refresh Tooling Plane", "tooling", "Check syntax, lint scripts, MCP, plugins, extensions, and local environment readiness.", handler="refreshToolingSnapshot", endpoint="/edgek/ide/tooling-snapshot", tags=["tooling", "lint", "syntax", "mcp", "plugins", "environment"]),
            action("tooling.syntax", "Syntax Check Active File", "tooling", "Run the active file through the available syntax checker.", handler="runSyntaxToolingCheck", endpoint="/edgek/ide/tooling-snapshot", tags=["tooling", "syntax"]),
            action("tooling.lint", "Show Lint Contract", "tooling", "Show lint scripts and governed terminal guidance.", handler="showLintToolingContract", endpoint="/edgek/ide/tooling-snapshot", tags=["tooling", "lint"]),
            action("tooling.mcp", "Inspect MCP", "tooling", "Inspect MCP config, routes, approvals, executions, and schema-pin surfaces.", handler="focusMcpTooling", endpoint="/edgek/ide/tooling-snapshot", tags=["tooling", "mcp"]),
            action("tooling.plugins", "Inspect Plugins And Extensions", "tooling", "Inspect plugin marketplace, VS Code extension, and desktop shell surfaces.", handler="focusPluginTooling", endpoint="/edgek/ide/tooling-snapshot", tags=["tooling", "plugins", "extensions"]),
            action("tooling.mcp_ops", "Refresh MCP Operations", "tooling", "Load MCP state, servers, approvals, audit, executions, and schema pins.", handler="refreshMcpOps", endpoint="/edgek/mcp/state", tags=["tooling", "mcp", "approvals", "schema"]),
            action("tooling.plugin_ops", "Refresh Plugin Operations", "tooling", "Load installed plugins and plugin validation/install surfaces.", handler="refreshPluginOps", endpoint="/edgek/plugins", tags=["tooling", "plugins", "extensions"]),
            action("tooling.environment", "Inspect Environment", "tooling", "Inspect Python, Node, npm, git, and workspace package scripts.", handler="focusEnvironmentTooling", endpoint="/edgek/ide/tooling-snapshot", tags=["tooling", "environment"]),
            action("system.refresh", "Refresh System Plane", "system", "Load listening ports, processes, environment, packages, and extensions.", handler="refreshSystemSnapshot", endpoint="/edgek/ide/system-snapshot", tags=["system", "ports", "processes", "environment", "packages"]),
            action("system.ports", "List Listening Ports", "system", "Show listening TCP/UDP ports with owning PID and process.", handler="refreshSystemPorts", endpoint="/edgek/ide/ports", tags=["system", "ports"]),
            action("system.processes", "Explore Processes", "system", "Find running processes by name/PID with CPU and memory.", handler="refreshSystemProcesses", endpoint="/edgek/ide/processes", tags=["system", "processes"]),
            action("system.kill", "Kill Process", "system", "Signal a process by PID after Safety Governor classification, approval, and evidence.", handler="killSystemProcess", endpoint="/edgek/ide/system/kill", method="POST", tags=["system", "processes", "kill"], risk="high", approval_required=True, local_fallback=False),
            action("system.free_port", "Free Port", "system", "Terminate the process holding a port after Safety Governor classification, approval, and evidence.", handler="freeSystemPort", endpoint="/edgek/ide/ports/free", method="POST", tags=["system", "ports", "kill"], risk="high", approval_required=True, local_fallback=False),
            action("system.environment", "Inspect Environment", "system", "Show Python/Node/venv interpreters, versions, PATH, and non-secret env vars.", handler="refreshSystemEnvironment", endpoint="/edgek/ide/environment", tags=["system", "environment"]),
            action("system.packages", "Manage Packages", "system", "List Python/Node dependencies, scripts, install state, and governed install commands.", handler="refreshSystemPackages", endpoint="/edgek/ide/packages", tags=["system", "packages"]),
            action("system.extensions", "Inspect Extensions", "system", "Inspect VS Code extension commands, desktop shell, plugins, and MCP servers.", handler="refreshSystemExtensions", endpoint="/edgek/ide/extensions", tags=["system", "extensions", "plugins"]),
            action("system.catalog", "Browse Recommended Catalog", "system", "Browse curated MCP servers, CLI tools, and editor extensions with live install state.", handler="refreshSystemCatalog", endpoint="/edgek/ide/catalog", tags=["system", "catalog", "mcp", "extensions", "tools"]),
            action("doctor.restart_gateway", "Restart Gateway", "doctor", "Restart the active BEAST gateway and preserve diagnostics if startup fails.", handler="restartGateway", tags=["doctor", "gateway"], approval_required=True),
            action("doctor.copy_report", "Copy Doctor Report", "doctor", "Copy active gateway URL, command, PID, health, route capability, and log tail.", handler="copyDoctorReport", tags=["doctor", "diagnostic"]),
            action("settings.release_readiness", "Check IDE Readiness", "settings", "Run the release-readiness checklist for packaging, gateway startup, and core desktop features.", handler="checkReleaseReadiness", endpoint="/edgek/ide/release-readiness/check", method="POST", local_fallback=True, tags=["settings", "readiness"]),
        ]

    def _sourceplan_repo_patch(root: Path, plan: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        chunks: list[str] = []
        compiled: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for index, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_id = str(op.get("op_id") or f"op_{index + 1}")
            rel = str(op.get("path") or "")
            target = _safe_relative(root, rel)
            if target is None:
                blocked.append({"operation_id": op_id, "path": rel, "reason": "unsafe_path"})
                continue
            lower = rel.lower()
            if any(secret in lower for secret in (".env", "id_rsa", "id_ed25519", "secrets", "credentials")):
                blocked.append({"operation_id": op_id, "path": rel, "reason": "secrets_like_path"})
                continue
            before = target.read_text(encoding="utf-8", errors="replace") if target.exists() and target.is_file() else str(op.get("old") or op.get("old_text") or "")
            after = str(op.get("new") or op.get("new_text") or op.get("content") or "")
            if not after and op.get("op") == "replace_exact":
                blocked.append({"operation_id": op_id, "path": rel, "reason": "empty_after_text"})
                continue
            diff = "".join(difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                lineterm="",
            ))
            if diff and not diff.endswith("\n"):
                diff += "\n"
            chunks.append(diff)
            compiled.append({
                "operation_id": op_id,
                "path": rel,
                "before_sha256": _hash_text(before),
                "after_sha256": _hash_text(after),
                "added_lines": sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")),
                "removed_lines": sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")),
            })
        return "\n".join(chunk for chunk in chunks if chunk), compiled, blocked

    def _gather_ide_state(root: Path, query: str, phase: str, risk: str, evidence_limit: int) -> dict[str, Any]:
        # These owners run synchronous repo scans / summaries that measured 4-10s each.
        # The gateway is single-worker uvicorn, so calling them directly inside an async
        # SSE generator blocks the event loop and starves concurrent agent run streams
        # (agent runs stall for 15-20s+ instead of ~1.5s). Callers MUST invoke this via
        # asyncio.to_thread so the loop stays free to service run-events.
        cockpit = MissionCockpit(root).summary(objective=query, phase=phase, risk=risk)
        code_cortex = code_cortex_router.get_editing_context(root, query, limit=12)
        if isinstance(code_cortex, dict):
            code_cortex = {"front_door": "code_cortex", **code_cortex}
        evidence = EvidenceBus(root).summary(limit=max(1, min(int(evidence_limit), 50)))
        lattice = MissionCrystalLattice(root).summary(limit=8)
        agent_sessions = AgentSessionStore(root).list()
        architecture = architecture_decision_register()
        return {
            "cockpit": cockpit,
            "code_cortex": code_cortex,
            "evidence": evidence,
            "lattice": lattice,
            "agent_sessions": agent_sessions,
            "architecture": architecture,
        }

    @router.get("/edgek/ide/snapshot")
    async def edgek_ide_snapshot(
        root_path: str = None,
        active_file: str = "",
        objective: str = "",
        phase: str = "scout",
        risk: str = "",
        evidence_limit: int = 12,
    ):
        root = _root(root_path)
        query = objective or active_file or "BEAST IDE mission"
        state = await asyncio.to_thread(_gather_ide_state, root, query, phase, risk, evidence_limit)
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

    def _event(event_type: str, payload: dict[str, Any]) -> str:
        data = {
            "beast_object_type": "beast_ide_event",
            "version": "1.0",
            "event_type": event_type,
            "created_at": int(time.time()),
            "payload": payload,
        }
        return f"event: {event_type}\ndata: {json.dumps(data, sort_keys=True)}\n\n"

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
            ignore = {".git", ".beast", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".venv", "venv"}
            suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".md"}
            matches: list[dict[str, Any]] = []
            scanned = 0
            for candidate in root.rglob("*"):
                if scanned >= capped_files:
                    break
                if any(part in ignore for part in candidate.relative_to(root).parts):
                    continue
                if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                    continue
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
            ignore = {".git", ".beast", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".venv", "venv"}
            suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".html", ".css", ".yml", ".yaml", ".toml"}
            matches: list[dict[str, Any]] = []
            scanned = 0
            lowered = needle.lower()
            for candidate in root.rglob("*"):
                if scanned >= capped_files or len(matches) >= capped_limit:
                    break
                try:
                    rel_parts = candidate.relative_to(root).parts
                except Exception:
                    continue
                if any(part in ignore for part in rel_parts):
                    continue
                if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                    continue
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
        client = BeastApiClient(_request_base_url(request), workspace=root)
        preview = client.preview_patch_plan(plan)
        scorecard = client.sourceplan_scorecard(plan)
        verification = client.verify_patch_plan(plan)
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
        root = _root(payload.get("root_path"))
        def compute_release_readiness() -> dict[str, Any]:
            files = {
                "desktop_package": root / "desktop-ide" / "package.json",
                "desktop_main": root / "desktop-ide" / "main.js",
                "desktop_renderer": root / "desktop-ide" / "renderer" / "app.js",
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

            route_text = read_if_exists(files["ide_routes"])
            renderer_text = read_if_exists(files["desktop_renderer"])
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
                {"check": "renderer_controls_present", "passed": "exportMissionRunbook" in renderer_text and "createHandoffPackage" in renderer_text},
                {"check": "terminal_maturity_controls_present", "passed": "terminalDecisionCard" in renderer_text and "recordTerminalExecution" in renderer_text and "terminalHistoryStorageKey" in renderer_text},
                {"check": "workspace_persistence_controls_present", "passed": "saveWorkspaceState" in renderer_text and "restoreWorkspaceTabs" in renderer_text and "openWorkspaceWindow" in renderer_text},
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
            }
            out_dir = root / ".beast" / "ide" / "release" / "checks"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"release_{int(time.time())}.json"
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            EvidenceBus(root).register(
                artifact_type="beast_ide_release_readiness",
                artifact_path=out_path,
                artifact_hash=_json_hash(result),
                source="desktop_ide",
                task_id="desktop_ide_release",
                status=result["status"],
                summary=f"{result['summary']['passed']}/{result['summary']['checks']} readiness checks passed",
            )
            return result

        return await asyncio.to_thread(compute_release_readiness)

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

    # ------------------------------------------------------------------
    # System plane: VS Code-like ports / processes / environment /
    # package management / extensions. Read endpoints are offloaded to a
    # worker thread (they shell out and scan the repo); process/port kill
    # is governed exactly like the terminal: SafetyGovernor classification,
    # operator approval, and an EvidenceBus receipt.
    # ------------------------------------------------------------------
    def _register_system_evidence(root: Path, result: dict[str, Any], *, context: str, task_id: str, approved: bool, operator_override: str) -> dict[str, Any]:
        payload = {
            "beast_object_type": "beast_ide_system_action",
            "version": "1.0",
            "context": context,
            "approved": approved,
            "operator_override": operator_override,
            "result": result,
            "created_at": int(time.time()),
        }
        out_dir = root / ".beast" / "evidence" / "system"
        out_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        out_path = out_dir / f"system_{int(time.time())}_{digest}.json"
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_system_action",
            artifact_path=out_path,
            artifact_hash="sha256:" + hashlib.sha256(out_path.read_bytes()).hexdigest(),
            source="ide_system_plane",
            task_id=task_id or "",
            status="ok" if result.get("ok") else "failed",
            summary=f"{context}: {result.get('command') or result.get('status')}",
            metadata={
                "pid": result.get("pid"),
                "signal": result.get("signal"),
                "status": result.get("status"),
                "context": context,
            },
        )
        result["evidence_receipt"] = receipt
        result["evidence_path"] = str(out_path)
        return receipt

    async def _governed_kill(root: Path, pid: int, sig: str, *, approved: bool, operator_override: str, task_id: str, dry_run: bool, context: str) -> dict[str, Any]:
        preview = await asyncio.to_thread(system_inspector.describe_kill_target, pid, sig)
        receipt = await asyncio.to_thread(
            SafetyGovernor(root).classify_command,
            preview["command"],
            mode="ide_system_kill",
            task_id=task_id,
            operator_override=operator_override,
        )
        decision = str(receipt.get("decision") or "allow")
        preview["safety"] = receipt
        preview["decision"] = decision
        preview["context"] = context
        if preview["protected"]:
            return {"ok": False, "error": "protected_process", "reason": preview["protected_reason"], **preview}
        if not preview["exists"]:
            return {"ok": False, "error": "no_such_process", **preview}
        if dry_run:
            return {"ok": True, "status": "dry_run", **preview}
        if decision == "block":
            return {"ok": False, "error": "blocked_by_safety_governor", **preview}
        if not approved:
            return {"ok": False, "error": "approval_required", **preview}
        result = await asyncio.to_thread(system_inspector.kill_process, pid, sig)
        result["safety"] = receipt
        result["decision"] = decision
        result["context"] = context
        _register_system_evidence(root, result, context=context, task_id=task_id, approved=approved, operator_override=operator_override)
        return result

    @router.get("/edgek/ide/system-snapshot")
    async def edgek_ide_system_snapshot(root_path: str = None, process_query: str = "", port_limit: int = 60, process_limit: int = 30):
        root = _root(root_path)
        return await asyncio.to_thread(
            system_inspector.system_snapshot,
            root,
            port_limit=max(1, min(int(port_limit), 500)),
            process_limit=max(1, min(int(process_limit), 200)),
            process_query=process_query,
        )

    @router.get("/edgek/ide/ports")
    async def edgek_ide_ports(limit: int = 300):
        return await asyncio.to_thread(system_inspector.list_listening_ports, max(1, min(int(limit), 1000)))

    @router.get("/edgek/ide/processes")
    async def edgek_ide_processes(query: str = "", limit: int = 120, sort: str = "memory"):
        return await asyncio.to_thread(system_inspector.list_processes, query, max(1, min(int(limit), 500)), sort)

    @router.get("/edgek/ide/process/{pid}")
    async def edgek_ide_process_detail(pid: int):
        return await asyncio.to_thread(system_inspector.process_detail, int(pid))

    @router.get("/edgek/ide/environment")
    async def edgek_ide_environment(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.environment_report, root)

    @router.get("/edgek/ide/packages")
    async def edgek_ide_packages(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.package_report, root)

    @router.get("/edgek/ide/extensions")
    async def edgek_ide_extensions(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.extensions_report, root)

    @router.get("/edgek/ide/catalog")
    async def edgek_ide_catalog(root_path: str = None):
        root = _root(root_path)
        return await asyncio.to_thread(system_inspector.catalog_report, root)

    @router.post("/edgek/ide/system/kill")
    async def edgek_ide_system_kill(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        pid = int(payload.get("pid") or 0)
        if pid <= 0:
            return {"ok": False, "error": "invalid_pid", "beast_object_type": "beast_ide_system_action"}
        return await _governed_kill(
            root,
            pid,
            str(payload.get("signal") or "TERM"),
            approved=bool(payload.get("approved", False)),
            operator_override=str(payload.get("operator_override") or ""),
            task_id=str(payload.get("task_id") or ""),
            dry_run=bool(payload.get("dry_run", False)),
            context="process_kill",
        )

    @router.post("/edgek/ide/ports/free")
    async def edgek_ide_ports_free(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        port = int(payload.get("port") or 0)
        if port <= 0:
            return {"ok": False, "error": "invalid_port", "beast_object_type": "beast_ide_system_action"}
        owners_payload = await asyncio.to_thread(system_inspector.find_port_owners, port)
        owners = owners_payload.get("owners") or []
        approved = bool(payload.get("approved", False))
        dry_run = bool(payload.get("dry_run", False))
        sig = str(payload.get("signal") or "TERM")
        if not owners:
            return {"ok": False, "error": "no_listener", "port": port, "owners": [], "beast_object_type": "beast_ide_system_action"}
        results = []
        for owner in owners:
            owner_pid = int(owner.get("pid") or 0)
            if owner_pid <= 0:
                continue
            results.append(await _governed_kill(
                root,
                owner_pid,
                sig,
                approved=approved,
                operator_override=str(payload.get("operator_override") or ""),
                task_id=str(payload.get("task_id") or ""),
                dry_run=dry_run,
                context=f"port_free:{port}",
            ))
        return {
            "ok": all(item.get("ok") for item in results) if results else False,
            "beast_object_type": "beast_ide_port_free",
            "version": "1.0",
            "port": port,
            "owner_count": len(owners),
            "results": results,
            "dry_run": dry_run,
        }

    @router.get("/edgek/ide/terminal/stream")
    async def edgek_ide_terminal_stream(
        root_path: str = None,
        command: str = "",
        cwd: str = "",
        timeout: int = 120,
        task_id: str = "",
        mode: str = "operator",
        approved: bool = False,
        operator_override: str = "",
    ):
        root = _root(root_path)
        run_cwd = Path(cwd or root).expanduser().resolve()
        try:
            run_cwd.relative_to(root)
        except ValueError:
            run_cwd = root
        bounded_timeout = max(1, min(int(timeout or 120), 900))
        command_text = str(command or "").strip()

        async def emit():
            started = time.time()

            def sse(event: str, payload: dict[str, Any]) -> str:
                return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

            if not command_text:
                yield sse("error", {"ok": False, "error": "empty command"})
                return
            yield sse("start", {
                "ok": True,
                "command": command_text,
                "cwd": str(run_cwd),
                "task_id": task_id,
                "mode": mode,
                "approved": approved,
                "timeout": bounded_timeout,
            })
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []
            returncode: int | None = None
            timed_out = False
            process = None
            try:
                process = await asyncio.create_subprocess_shell(
                    command_text,
                    cwd=str(run_cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

                async def pump(stream: Any, name: str, sink: list[str]):
                    while True:
                        chunk = await stream.readline()
                        if not chunk:
                            break
                        text = chunk.decode("utf-8", errors="replace")
                        sink.append(text)
                        del sink[:-400]
                        await queue.put(("chunk", {"stream": name, "text": text}))

                stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
                stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))
                wait_task = asyncio.create_task(process.wait())
                deadline = time.time() + bounded_timeout
                while True:
                    if wait_task.done() and queue.empty():
                        break
                    remaining = max(0.05, deadline - time.time())
                    if remaining <= 0.05 and not wait_task.done():
                        timed_out = True
                        process.kill()
                    try:
                        event, payload = await asyncio.wait_for(queue.get(), timeout=min(0.25, remaining))
                        yield sse(event, payload)
                    except asyncio.TimeoutError:
                        yield sse("heartbeat", {"running": not wait_task.done(), "elapsed_ms": int((time.time() - started) * 1000)})
                    if timed_out and wait_task.done() and queue.empty():
                        break
                returncode = int(await wait_task)
                await stdout_task
                await stderr_task
            except asyncio.CancelledError:
                if process and process.returncode is None:
                    process.kill()
                raise
            except Exception as exc:
                result = {
                    "ok": False,
                    "command": command_text,
                    "cwd": str(run_cwd),
                    "error": str(exc),
                    "duration_ms": int((time.time() - started) * 1000),
                }
                yield sse("error", result)
                return
            duration_ms = int((time.time() - started) * 1000)
            result = {
                "ok": returncode == 0 and not timed_out,
                "command": command_text,
                "cwd": str(run_cwd),
                "returncode": returncode,
                "duration_ms": duration_ms,
                "timeout": bounded_timeout,
                "timed_out": timed_out,
                "stdout": "".join(stdout_chunks)[-12000:],
                "stderr": "".join(stderr_chunks)[-12000:],
                "safety": {
                    "mode": mode,
                    "approved": approved,
                    "operator_override": operator_override,
                    "streamed": True,
                },
            }
            out_dir = root / ".beast" / "ide" / "terminal"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"terminal_{int(time.time())}_{_raw_hash_text(command_text)[:10]}.json"
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            receipt = EvidenceBus(root).register(
                artifact_type="beast_governed_terminal_execution",
                artifact_path=out_path,
                artifact_hash=_json_hash(result),
                source="governed_terminal",
                task_id=task_id or "desktop_terminal",
                status="ok" if result["ok"] else "failed",
                summary=f"Streamed terminal command: {command_text[:140]}",
                metadata={"returncode": returncode, "duration_ms": duration_ms, "timed_out": timed_out},
            )
            yield sse("done", {**result, "evidence_receipt": receipt, "path": str(out_path)})

        return StreamingResponse(emit(), media_type="text/event-stream")

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

    @router.get("/edgek/ide/actions/manifest")
    async def edgek_ide_actions_manifest(
        root_path: str = None,
        page: str = "",
        query: str = "",
    ):
        _root(root_path)
        actions = _ide_action_manifest()
        needle = query.strip().lower()
        page_filter = page.strip().lower()
        if page_filter:
            actions = [item for item in actions if item.get("page") == page_filter or page_filter in item.get("tags", [])]
        if needle:
            actions = [
                item for item in actions
                if needle in item.get("id", "").lower()
                or needle in item.get("label", "").lower()
                or needle in item.get("description", "").lower()
                or any(needle in str(tag).lower() for tag in item.get("tags", []))
            ]
        return {
            "beast_object_type": "beast_ide_action_manifest",
            "version": "1.0",
            "count": len(actions),
            "actions": actions,
            "governance": {
                "direct_mutation_allowed": False,
                "writes_require_sourceplan": True,
                "risky_actions_require_approval": True,
                "terminal_execution_requires_safety_governor": True,
                "worktree_recommended_for_high_risk": True,
                "receipts_are_authoritative": True,
            },
        }

    @router.post("/edgek/ide/actions/plan")
    async def edgek_ide_action_plan(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        action_id = str(payload.get("action_id") or "")
        action = next((item for item in _ide_action_manifest() if item["id"] == action_id), None)
        if not action:
            return {
                "beast_object_type": "beast_ide_action_plan",
                "action_id": action_id,
                "status": "unknown_action",
                "allowed": False,
                "reason": "Action is not declared in the BEAST IDE manifest.",
            }
        plan = {
            "beast_object_type": "beast_ide_action_plan",
            "version": "1.0",
            "action_id": action_id,
            "label": action["label"],
            "page": action["page"],
            "status": "planned",
            "allowed": True,
            "client_handler": action["client_handler"],
            "endpoint": action.get("endpoint"),
            "method": action.get("method"),
            "risk": action.get("risk"),
            "approval_required": action.get("approval_required", False),
            "sourceplan_required": action.get("sourceplan_required", False),
            "worktree_recommended": action.get("worktree_recommended", False),
            "provider_required": action.get("provider_required", False),
            "direct_mutation_allowed": False,
            "server_side_execution": False,
            "execution_note": "The desktop client runs declared handlers; the backend manifest only plans and governs action visibility.",
        }
        out_dir = root / ".beast" / "ide" / "actions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{_raw_hash_text(action_id)[:16]}.json"
        out_path.write_text(json.dumps(plan, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        receipt = EvidenceBus(root).register(
            artifact_type="beast_ide_action_plan",
            artifact_path=out_path,
            artifact_hash=_json_hash(plan),
            source="desktop_ide",
            task_id=action_id,
            status="planned",
            summary=f"IDE action planned: {action['label']}",
            metadata={"page": action["page"], "risk": action.get("risk")},
        )
        return {**plan, "path": str(out_path), "evidence_receipt": receipt}

    @router.get("/edgek/ide/agent-sessions")
    async def edgek_ide_agent_sessions(root_path: str = None):
        root = _root(root_path)
        return AgentSessionStore(root).list()

    @router.get("/edgek/ide/agent-sessions/{session_id}")
    async def edgek_ide_agent_session_detail(session_id: str, root_path: str = None):
        root = _root(root_path)
        return AgentSessionStore(root).get(session_id)

    @router.post("/edgek/ide/agent-sessions/create")
    async def edgek_ide_agent_session_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
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
        root = _root(payload.get("root_path"))
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

    @router.post("/edgek/ide/agent-sessions/pause")
    async def edgek_ide_agent_session_pause(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_root(payload.get("root_path"))).pause(str(payload.get("session_id") or ""))

    @router.post("/edgek/ide/agent-sessions/resume")
    async def edgek_ide_agent_session_resume(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_root(payload.get("root_path"))).resume(str(payload.get("session_id") or ""))

    @router.post("/edgek/ide/agent-sessions/cancel")
    async def edgek_ide_agent_session_cancel(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_root(payload.get("root_path"))).cancel(
            str(payload.get("session_id") or ""),
            reason=str(payload.get("reason") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/sourceplan-draft")
    async def edgek_ide_agent_session_sourceplan_draft(payload: dict[str, Any] = None):
        payload = payload or {}
        return AgentSessionStore(_root(payload.get("root_path"))).sourceplan_draft(
            str(payload.get("session_id") or ""),
            output=str(payload.get("output") or ""),
        )

    @router.post("/edgek/ide/agent-sessions/action-ir-sourceplan")
    async def edgek_ide_agent_session_action_ir_sourceplan(payload: dict[str, Any] = None):
        payload = payload or {}
        return _compile_agent_action_ir_sourceplan(
            _root(payload.get("root_path")),
            output=str(payload.get("output") or ""),
            provider=str(payload.get("provider") or "desktop_agent"),
            requested_files=[str(item) for item in payload.get("files") or [] if item],
            active_file=str(payload.get("active_file") or ""),
            objective=str(payload.get("objective") or ""),
        )

    @router.get("/edgek/ide/agent-sessions/{session_id}/run-events")
    async def edgek_ide_agent_session_run_events(
        request: Request,
        session_id: str,
        root_path: str = None,
        prompt: str = "",
        provider: str = "",
        model: str = "",
        context_files: List[str] | None = None,
        simulate: bool = False,
        max_tokens: int = 2000,
        context_max_chars_each: int = 30000,
    ):
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
        ) -> tuple[str, list[str]]:
            repair_prompt = _action_ir_retry_prompt(objective, previous_output, files)
            repair_parts: list[str] = []
            repair_tools: list[str] = []
            async for event in client.stream_live_turn(
                repair_prompt,
                [],
                provider=provider_id,
                model=model_id,
                context_files=files,
                max_tokens=max(256, min(int(max_output_tokens), 2400)),
                context_max_chars_each=max(1200, min(int(max_context_chars), 60000)),
                governance_level="ide_agent_session_action_ir_repair",
            ):
                event_type = str(event.get("type") or "event")
                if event_type == "token":
                    repair_parts.append(str(event.get("text") or ""))
                elif event_type == "tool":
                    repair_tools.append(str(event.get("text") or ""))
            return "".join(repair_parts), repair_tools

        async def generate():
            root = _root(root_path)
            store = AgentSessionStore(root)
            detail = store.get(session_id)
            if not detail.get("ok"):
                yield _event("agent_run_error", {"ok": False, "error": detail.get("error") or "unknown session"})
                return
            session = detail.get("session") if isinstance(detail.get("session"), dict) else {}
            run_prompt = (prompt or session.get("objective") or "Continue this BEAST agent session.").strip()
            run_provider = provider or str(session.get("provider") or "nvidia_nim")
            run_model = model or str(session.get("model") or "meta/llama-3.1-8b-instruct")
            session_files = [str(item) for item in (session.get("files") or [])]
            request_files = [str(item) for item in (context_files or [])]
            context_file_list = list(dict.fromkeys([*request_files, *session_files]))
            store.update(session_id, status="running", output={
                "kind": "agent_run_started",
                "text": f"Run started: {run_prompt[:500]}",
                "provider": run_provider,
                "model": run_model,
            })
            yield _event("agent_run_started", {
                "ok": True,
                "session_id": session_id,
                "provider": run_provider,
                "model": run_model,
                "prompt": run_prompt,
                "simulate": bool(simulate),
            })
            assistant_parts: list[str] = []
            tool_events: list[str] = []
            try:
                client = BeastApiClient(_request_base_url(request), workspace=root)
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
                    async for event in client.stream_live_turn(
                        run_prompt,
                        [],
                        provider=run_provider,
                        model=run_model,
                        context_files=context_file_list,
                        max_tokens=max(128, min(int(max_tokens), 16000)),
                        context_max_chars_each=max(1200, min(int(context_max_chars_each), 60000)),
                        governance_level="ide_agent_session",
                    ):
                        event_type = str(event.get("type") or "event")
                        if event_type == "token":
                            text = str(event.get("text") or "")
                            assistant_parts.append(text)
                            yield _event("agent_run_token", {"session_id": session_id, "text": text})
                        elif event_type == "stage":
                            yield _event("agent_run_stage", {"session_id": session_id, "text": event.get("text") or ""})
                        elif event_type == "tool":
                            tool_text = str(event.get("text") or "")
                            tool_events.append(tool_text)
                            yield _event("agent_run_tool", {"session_id": session_id, "text": tool_text})
                        elif event_type == "done":
                            if event.get("assistant_text") and not assistant_parts:
                                assistant_parts.append(str(event.get("assistant_text") or ""))
                            tool_events.extend([str(item) for item in (event.get("tool_events") or [])])
                            yield _event("agent_run_provider_done", {"session_id": session_id, "ok": bool(event.get("ok", True)), "data": event.get("data") or {}})
                        elif event_type == "error":
                            yield _event("agent_run_error", {"session_id": session_id, "ok": False, "error": event.get("error") or "stream error"})
                assistant_text = "".join(assistant_parts)
                compile_result = _compile_agent_action_ir_sourceplan(
                    root,
                    output=assistant_text,
                    provider=run_provider,
                    requested_files=context_file_list,
                    objective=run_prompt,
                )
                repair_text = ""
                if not compile_result.get("ok") and not simulate and context_file_list:
                    yield _event("agent_run_stage", {"session_id": session_id, "text": "sourceplan repair"})
                    repair_text, repair_tools = await _stream_repair_action_ir(
                        client,
                        objective=run_prompt,
                        previous_output=assistant_text,
                        provider_id=run_provider,
                        model_id=run_model,
                        files=context_file_list,
                        max_output_tokens=max_tokens,
                        max_context_chars=context_max_chars_each,
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
                        )
                sourceplan_status = str(compile_result.get("status") or "requires_operator_translation")
                if compile_result.get("ok"):
                    yield _event("agent_run_sourceplan", {
                        "ok": True,
                        "session_id": session_id,
                        "status": sourceplan_status,
                        "operation_count": int(compile_result.get("operation_count") or 0),
                        "plan_id": str(((compile_result.get("plan") or {}).get("plan_id") or "")),
                    })
                else:
                    yield _event("agent_run_needs_operator", {
                        "ok": False,
                        "session_id": session_id,
                        "status": sourceplan_status,
                        "error": str(compile_result.get("error") or "Action IR compilation requires operator translation."),
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
                        "sourceplan_plan_id": str(((compile_result.get("plan") or {}).get("plan_id") or "")),
                    },
                    evidence=[{
                        "beast_object_type": "beast_agent_session_sourceplan_status",
                        "session_id": session_id,
                        "status": sourceplan_status,
                        "operation_count": int(compile_result.get("operation_count") or 0),
                        "plan_id": str(((compile_result.get("plan") or {}).get("plan_id") or "")),
                        "error": str(compile_result.get("error") or ""),
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

        return StreamingResponse(generate(), media_type="text/event-stream")

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

    @router.post("/edgek/ide/worktree-mission/create")
    async def edgek_ide_worktree_mission_create(payload: dict[str, Any] = None):
        payload = payload or {}
        root = _root(payload.get("root_path"))
        mission = WorktreeForge(root).create(
            objective=str(payload.get("objective") or "BEAST isolated mission"),
            risk=str(payload.get("risk") or "medium"),
            provider=str(payload.get("provider") or ""),
            mode=str(payload.get("mode") or "implementer"),
            base_ref=str(payload.get("base_ref") or "HEAD"),
            task_id=str(payload.get("task_id") or ""),
        )
        if mission.get("ok") and isinstance(mission.get("task"), dict):
            AgentSessionStore(root).create(
                objective=str(payload.get("objective") or "BEAST isolated mission"),
                mode=str(payload.get("mode") or "implementer"),
                budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else None,
                tools=["worktree", "sourceplan", "verifier", "evidence_bus"],
                files=[str(item) for item in (payload.get("files") or [])],
                agent_id=str(mission["task"].get("task_id") or ""),
                provider=str(payload.get("provider") or ""),
            )
        return mission

    @router.post("/edgek/ide/worktree-mission/test")
    async def edgek_ide_worktree_mission_test(payload: dict[str, Any] = None):
        payload = payload or {}
        command = payload.get("command") if isinstance(payload.get("command"), list) else None
        return WorktreeForge(_root(payload.get("root_path"))).test(
            str(payload.get("task_id") or ""),
            command=[str(item) for item in command] if command else None,
            timeout=float(payload.get("timeout", 120.0)),
        )

    @router.post("/edgek/ide/worktree-mission/diff")
    async def edgek_ide_worktree_mission_diff(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).diff(
            str(payload.get("task_id") or ""),
            max_chars=max(1000, min(int(payload.get("max_chars", 60000)), 200000)),
        )

    @router.post("/edgek/ide/worktree-mission/promote")
    async def edgek_ide_worktree_mission_promote(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).promote(
            str(payload.get("task_id") or ""),
            approved=bool(payload.get("approved", False)),
            require_tests=bool(payload.get("require_tests", True)),
        )

    @router.post("/edgek/ide/worktree-mission/sourceplan-draft")
    async def edgek_ide_worktree_mission_sourceplan_draft(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).sourceplan_draft_from_diff(
            str(payload.get("task_id") or ""),
            max_chars=max(1000, min(int(payload.get("max_chars", 60000)), 200000)),
        )

    @router.post("/edgek/ide/worktree-mission/close")
    async def edgek_ide_worktree_mission_close(payload: dict[str, Any] = None):
        payload = payload or {}
        return WorktreeForge(_root(payload.get("root_path"))).archive(
            str(payload.get("task_id") or ""),
            reason=str(payload.get("reason") or "closed from BEAST IDE"),
        )

    return router
