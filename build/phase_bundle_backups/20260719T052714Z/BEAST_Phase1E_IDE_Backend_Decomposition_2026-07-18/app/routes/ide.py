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
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder
from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.capability.skill_tree import SkillTree
from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.routes.ide_support.common import (
    bounded_workspace_files as _bounded_workspace_files,
    extract_json_object as _extract_json_object,
    hash_text as _hash_text,
    is_compact_local_coder as _is_compact_local_coder,
    pair_programmer_limits as _pair_programmer_limits,
    raw_hash_text as _raw_hash_text,
    safe_relative as _safe_relative,
)
from app.routes.ide_support.action_ir import (
    action_ir_anchor_hints as _action_ir_anchor_hints_impl,
    action_ir_retry_prompt as _action_ir_retry_prompt_impl,
    reject_incomplete_function_replacements as _reject_incomplete_function_replacements,
)
from app.routes.ide_support.agent_session_routes import register_agent_session_routes
from app.routes.ide_support.context import IdeRouteContext
from app.routes.ide_support.events import ide_event as _event
from app.routes.ide_support.system_routes import register_system_inspection_routes
from app.routes.ide_support.worktree_routes import register_worktree_mission_routes


def build_ide_router(default_root: str | Path, *, code_cortex_router: Any) -> APIRouter:
    router = APIRouter()
    route_context = IdeRouteContext(default_root)
    fallback_root = route_context.fallback_root

    def _root(value: Any = None) -> Path:
        return route_context.root(value)

    def _action_ir_anchor_hints(root: Path | None, allowed_files: list[str]) -> str:
        return _action_ir_anchor_hints_impl(root, allowed_files, build_file_references=build_file_references)

    def _action_ir_retry_prompt(objective: str, previous_output: str, allowed_files: list[str], diagnostics: str = "", root: Path | None = None) -> str:
        return _action_ir_retry_prompt_impl(
            objective,
            previous_output,
            allowed_files,
            action_ir_kind=ACTION_IR_KIND,
            diagnostics=diagnostics,
            root=root,
            build_file_references=build_file_references,
        )

    def _compile_agent_action_ir_sourceplan(
        root: Path,
        *,
        output: str,
        provider: str,
        requested_files: list[str],
        active_file: str = "",
        objective: str = "",
        expected_handoff_hash: str = "",
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
        raw_actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
        if not raw_actions:
            return {
                "ok": False,
                "status": "empty_action_ir",
                "error": "Agent returned Action IR without any file-edit actions.",
                "requires_operator_translation": True,
                "allowed_files": allowed,
                "retry_options": [{"id": "require_file_edit", "label": "Retry with at least one exact file edit"}],
            }
        # Reject sequential edits before resolving individual anchors.  The
        # resolver intentionally evaluates every model anchor against the
        # original file, whereas SourcePlan validation applies operations in
        # order.  Letting two edits to the same target through therefore
        # guarantees that a later old-anchor can disappear after the first
        # edit.  Check both explicit paths and file refs here so the model
        # receives a focused repair instead of a misleading post-validation
        # anchor error.
        raw_target_keys: list[str] = []
        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            target = action.get("target") if isinstance(action.get("target"), dict) else action
            if not isinstance(target, dict):
                continue
            path = str(target.get("path") or "").strip()
            file_ref = str(target.get("file_ref") or target.get("ref") or "").strip()
            if path:
                raw_target_keys.append(f"path:{path}")
            elif file_ref:
                raw_target_keys.append(f"ref:{file_ref}")
        repeated_raw_targets = sorted({key for key in raw_target_keys if raw_target_keys.count(key) > 1})
        if repeated_raw_targets:
            labels = [key.split(":", 1)[1] for key in repeated_raw_targets]
            return {
                "ok": False,
                "status": "multiple_actions_same_file",
                "error": (
                    "Action IR contains sequential edits for the same file target: "
                    + ", ".join(labels[:5])
                    + ". Return one complete anchor replacement per file."
                ),
                "requires_operator_translation": True,
                "allowed_files": allowed,
                "retry_options": [{"id": "consolidate_file_actions", "label": "Retry with one complete replacement per file"}],
            }
        incomplete_function_error = _reject_incomplete_function_replacements(raw_actions)
        if incomplete_function_error:
            return {
                "ok": False,
                "status": "incomplete_function_replacement",
                "error": incomplete_function_error,
                "requires_operator_translation": True,
                "allowed_files": allowed,
                "retry_options": [{"id": "retry_complete_anchor", "label": "Retry with a complete function anchor"}],
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
            # Some OpenAI-compatible providers omit an otherwise requested
            # field while returning structurally valid JSON.  The gateway is
            # the trusted owner of this exact prompt/packet pair, so it may
            # bind an absent hash here; a supplied conflicting hash is still
            # rejected by ``resolve_action_ir`` below.
            handoff_hash_bound_by_gateway = False
            if expected_handoff_hash and not str(
                parsed.get("provider_handoff_hash") or parsed.get("handoff_hash") or ""
            ):
                parsed["provider_handoff_hash"] = expected_handoff_hash
                parsed["handoff_hash"] = expected_handoff_hash
                handoff_hash_bound_by_gateway = True
            file_refs = build_file_references(root, allowed)
            action_ir = ActionIR.from_dict(parsed)
            resolved, non_mutating = resolve_action_ir(
                root,
                action_ir,
                file_refs,
                allowed,
                expected_handoff_hash=expected_handoff_hash,
            )
            source_paths = [item.path for item in resolved]
            duplicate_paths = sorted({path for path in source_paths if source_paths.count(path) > 1})
            if duplicate_paths:
                return {
                    "ok": False,
                    "status": "multiple_actions_same_file",
                    "error": (
                        "Action IR contains sequential edits for the same file: "
                        + ", ".join(duplicate_paths[:5])
                        + ". Return one complete anchor replacement per file so validation can preserve exact anchors."
                    ),
                    "requires_operator_translation": True,
                    "allowed_files": allowed,
                    "retry_options": [{"id": "consolidate_file_actions", "label": "Retry with one complete replacement per file"}],
                }
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
            if not operations:
                return {
                    "ok": False,
                    "status": "no_resolved_edits",
                    "error": "Action IR did not resolve to any reviewable file edits.",
                    "requires_operator_translation": True,
                    "allowed_files": allowed,
                    "retry_options": [{"id": "require_exact_edit", "label": "Retry against the current file contents"}],
                }
            plan_id = "ide_air_" + hashlib.sha256(f"{root}|{provider}|{time.time()}".encode("utf-8")).hexdigest()[:12]
            plan = {
                "plan_id": plan_id,
                "kind": "beast_ide_agent_action_ir_sourceplan",
                "status": "draft_requires_approval",
                "objective": str(action_ir.objective or objective or "Apply agent Action IR through BEAST IDE"),
                "provider": provider,
                "provider_handoff_hash": expected_handoff_hash,
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
                    "provider_handoff_hash_bound_by_gateway": handoff_hash_bound_by_gateway,
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
                metadata={
                    "operation_count": len(operations),
                    "provider": provider,
                    "provider_handoff_hash": expected_handoff_hash,
                    "provider_handoff_hash_bound_by_gateway": handoff_hash_bound_by_gateway,
                },
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

    def _validate_agent_sourceplan(
        root: Path,
        plan: dict[str, Any],
        *,
        run_isolated_verifier: bool = False,
    ) -> dict[str, Any]:
        """Validate proposed source text without mutating or executing the workspace."""
        operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        proposed: dict[str, str] = {}
        checks: list[dict[str, Any]] = []
        failures: list[str] = []
        for operation in operations[:100]:
            rel = str(operation.get("path") or "")
            target = _safe_relative(root, rel)
            if target is None or not target.is_file():
                failures.append(f"{rel or '<missing>'}: target file is unavailable")
                continue
            if rel not in proposed:
                try:
                    proposed[rel] = target.read_text(encoding="utf-8")
                except Exception as exc:
                    failures.append(f"{rel}: {exc}")
                    continue
            old = str(operation.get("old") if operation.get("old") is not None else operation.get("old_text") or "")
            new = str(operation.get("new") if operation.get("new") is not None else operation.get("new_text") or "")
            if not old or proposed[rel].count(old) != 1:
                failures.append(f"{rel}: operation {operation.get('op_id') or '?'} no longer has one exact anchor")
                continue
            proposed[rel] = proposed[rel].replace(old, new, 1)

        node = shutil.which("node")
        syntax_checked = 0
        for rel, source in proposed.items():
            content_errors = []
            if "\x00" in source:
                content_errors.append("NUL byte present")
            if re.search(r"^(?:<<<<<<< |=======\s*$|>>>>>>> )", source, re.MULTILINE):
                content_errors.append("unresolved conflict marker present")
            content_passed = not content_errors
            checks.append({"path": rel, "kind": "content-safety", "passed": content_passed, "message": "; ".join(content_errors) or "No binary or conflict markers"})
            if not content_passed:
                failures.extend(f"{rel}: {item}" for item in content_errors)
            suffix = Path(rel).suffix.lower()
            try:
                if suffix == ".py":
                    ast.parse(source, filename=rel)
                    checks.append({"path": rel, "kind": "python-ast", "passed": True, "message": "Python syntax parsed"})
                    syntax_checked += 1
                elif suffix == ".json":
                    json.loads(source)
                    checks.append({"path": rel, "kind": "json-parse", "passed": True, "message": "JSON parsed"})
                    syntax_checked += 1
                elif suffix in {".js", ".cjs", ".mjs"} and node:
                    with tempfile.NamedTemporaryFile("w", suffix=suffix, encoding="utf-8", delete=False) as handle:
                        handle.write(source)
                        temp_name = handle.name
                    try:
                        result = subprocess.run([node, "--check", temp_name], text=True, capture_output=True, timeout=8, check=False)
                    finally:
                        Path(temp_name).unlink(missing_ok=True)
                    if result.returncode != 0:
                        raise SyntaxError((result.stderr or result.stdout or "JavaScript syntax check failed").strip()[:1000])
                    checks.append({"path": rel, "kind": "node-check", "passed": True, "message": "JavaScript syntax parsed"})
                    syntax_checked += 1
            except (SyntaxError, json.JSONDecodeError, subprocess.SubprocessError, OSError) as exc:
                message = str(exc).replace("\n", " ")[:1000]
                kind = "python-ast" if suffix == ".py" else "json-parse" if suffix == ".json" else "node-check"
                checks.append({"path": rel, "kind": kind, "passed": False, "message": message})
                failures.append(f"{rel}: {message}")

        requested = [str(item) for item in ((plan.get("action_ir") or {}).get("verify") or []) if item]
        for item in plan.get("non_mutating_requests") or []:
            if not isinstance(item, dict) or str(item.get("type") or "") != "run_verifier":
                continue
            parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
            command = str(parameters.get("command") or item.get("command") or "").strip()
            if command:
                requested.append(command)
        # Syntax/content validation is always local and non-mutating.  Actual
        # subprocess verifiers are a separate operator-approved capability:
        # the agent first requests it, then uses the persisted grant on a
        # later turn.  This makes "run tests" a real approval loop instead
        # of an invisible shell action hidden behind a model response.
        if run_isolated_verifier:
            isolated = _run_isolated_agent_verifiers(root, proposed, requested)
        else:
            commands = _agent_validation_commands(root, proposed, requested)
            rows = [{
                "path": "",
                "kind": "isolated-verifier",
                "passed": True,
                "status": "approval_required",
                "command": str(command.get("display") or "<verifier>"),
                "message": "Awaiting operator approval for an isolated verifier run",
                "isolated": True,
            } for command in commands[:6]]
            isolated = {
                "checks": rows,
                "failures": [],
                "summary": {
                    "status": "approval_required" if rows else "skipped",
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "commands": [
                        {"command": row["command"], "status": row["status"], "message": row["message"]}
                        for row in rows
                    ],
                },
            }
        checks.extend(isolated["checks"])
        failures.extend(isolated["failures"])
        status = "failed" if failures else "passed" if syntax_checked == len(proposed) and proposed else "partial"
        return {
            "ok": not failures and bool(proposed),
            "status": status,
            "file_count": len(proposed),
            "syntax_checked": syntax_checked,
            "check_count": len(checks),
            "checks": checks,
            "failures": failures[:20],
            "requested_verifiers": requested[:20],
            "isolated_verifiers": isolated["summary"],
            "command_policy": "allowlisted verifier commands run only after operator approval and only in a temporary isolated workspace; unsupported commands are recorded as skipped",
        }

    def _run_isolated_agent_verifiers(root: Path, proposed: dict[str, str], requested: list[str]) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        failures: list[str] = []
        if not proposed:
            return {"checks": checks, "failures": failures, "summary": {"status": "skipped", "passed": 0, "failed": 0, "skipped": 0, "commands": []}}

        commands = _agent_validation_commands(root, proposed, requested)
        if not commands:
            return {"checks": checks, "failures": failures, "summary": {"status": "skipped", "passed": 0, "failed": 0, "skipped": 0, "commands": []}}

        with tempfile.TemporaryDirectory(prefix="beast-ide-agent-verify-") as temp_name:
            temp_root = Path(temp_name)
            for rel, source in proposed.items():
                target = _safe_relative(temp_root, rel)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            for command in commands[:6]:
                for rel in command.get("extra_inputs") or []:
                    _copy_agent_verifier_input(root, temp_root, str(rel))
                if command.get("skipped"):
                    checks.append({
                        "path": "",
                        "kind": "isolated-verifier",
                        "passed": True,
                        "status": "skipped",
                        "command": command["display"],
                        "message": command["skipped"],
                        "isolated": True,
                    })
                    continue
                try:
                    result = subprocess.run(
                        command["argv"],
                        cwd=temp_root,
                        text=True,
                        capture_output=True,
                        timeout=command.get("timeout", 12),
                        check=False,
                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    )
                    output = ((result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")).strip()
                    passed = result.returncode == 0
                    check = {
                        "path": "",
                        "kind": "isolated-verifier",
                        "passed": passed,
                        "status": "passed" if passed else "failed",
                        "command": command["display"],
                        "returncode": result.returncode,
                        "message": (output or "Verifier completed")[:1600],
                        "isolated": True,
                    }
                    checks.append(check)
                    if not passed:
                        failures.append(f"{command['display']}: {(output or f'exited {result.returncode}')[:800]}")
                except (subprocess.SubprocessError, OSError) as exc:
                    message = str(exc).replace("\n", " ")[:800]
                    checks.append({
                        "path": "",
                        "kind": "isolated-verifier",
                        "passed": False,
                        "status": "failed",
                        "command": command["display"],
                        "message": message,
                        "isolated": True,
                    })
                    failures.append(f"{command['display']}: {message}")

        passed = sum(1 for item in checks if item.get("kind") == "isolated-verifier" and item.get("status") == "passed")
        failed = sum(1 for item in checks if item.get("kind") == "isolated-verifier" and item.get("status") == "failed")
        skipped = sum(1 for item in checks if item.get("kind") == "isolated-verifier" and item.get("status") == "skipped")
        status = "failed" if failed else "passed" if passed else "skipped"
        return {
            "checks": checks,
            "failures": failures,
            "summary": {
                "status": status,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "commands": [
                    {"command": item.get("command"), "status": item.get("status"), "message": item.get("message", "")[:240]}
                    for item in checks
                    if item.get("kind") == "isolated-verifier"
                ][:6],
            },
        }

    def _agent_validation_commands(root: Path, proposed: dict[str, str], requested: list[str]) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        py_files = [rel for rel in proposed if Path(rel).suffix.lower() == ".py"]
        js_files = [rel for rel in proposed if Path(rel).suffix.lower() in {".js", ".cjs", ".mjs"}]
        if py_files:
            commands.append({"display": "python -m py_compile " + " ".join(py_files[:24]), "argv": [sys.executable, "-m", "py_compile", *py_files[:24]], "timeout": 12, "extra_inputs": []})
        node = shutil.which("node")
        for rel in js_files[:8]:
            if node:
                commands.append({"display": f"node --check {rel}", "argv": [node, "--check", rel], "timeout": 8, "extra_inputs": []})
        for command in requested[:4]:
            commands.append(_normalize_agent_verifier_command(root, proposed, command))
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for command in commands:
            key = str(command.get("display") or command.get("argv"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(command)
        return unique

    def _normalize_agent_verifier_command(root: Path, proposed: dict[str, str], command: str) -> dict[str, Any]:
        display = " ".join(str(command or "").split())[:500]
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return {"display": display or "<invalid verifier>", "skipped": f"could not parse verifier command: {exc}", "extra_inputs": []}
        if not parts:
            return {"display": "<empty verifier>", "skipped": "empty verifier command", "extra_inputs": []}
        executable = Path(parts[0]).name
        if executable in {"python", "python3"} and len(parts) >= 4 and parts[1] == "-m" and parts[2] == "py_compile":
            paths = [item for item in parts[3:] if _safe_relative(root, item) is not None]
            if paths and all(path in proposed for path in paths):
                return {"display": display, "argv": [sys.executable, "-m", "py_compile", *paths[:24]], "timeout": 12, "extra_inputs": []}
            return {"display": display, "skipped": "py_compile verifier must target proposed files only", "extra_inputs": []}
        if executable in {"node", "nodejs"} and len(parts) == 3 and parts[1] == "--check":
            node = shutil.which("node") or shutil.which("nodejs")
            rel = parts[2]
            if node and rel in proposed and _safe_relative(root, rel) is not None:
                return {"display": display, "argv": [node, "--check", rel], "timeout": 8, "extra_inputs": []}
            return {"display": display, "skipped": "node --check verifier must target one proposed JavaScript file", "extra_inputs": []}
        if executable in {"pytest", "py.test"} or (executable in {"python", "python3"} and len(parts) >= 3 and parts[1] == "-m" and parts[2] == "pytest"):
            normalized = _bounded_pytest_verifier(root, proposed, parts)
            return {**normalized, "display": display}
        return {"display": display, "skipped": "verifier command is outside the BEAST IDE isolated allowlist", "extra_inputs": []}

    def _bounded_pytest_verifier(root: Path, proposed: dict[str, str], parts: list[str]) -> dict[str, Any]:
        pytest = shutil.which("pytest")
        prefix = [sys.executable, "-m", "pytest"] if parts[:3] == [parts[0], "-m", "pytest"] else ([pytest] if pytest else [sys.executable, "-m", "pytest"])
        args = parts[3:] if len(parts) >= 3 and parts[1] == "-m" and parts[2] == "pytest" else parts[1:]
        allowed_flags = {"-q", "-x", "-s", "--tb=short", "--disable-warnings", "--maxfail=1"}
        targets: list[str] = []
        filtered: list[str] = []
        for arg in args:
            if arg in allowed_flags:
                filtered.append(arg)
                continue
            if arg.startswith("-"):
                return {"skipped": f"pytest option {arg} is not allowed in isolated validation", "extra_inputs": []}
            safe = _safe_relative(root, arg)
            if safe is None or not safe.exists():
                return {"skipped": f"pytest target {arg} is unavailable or unsafe", "extra_inputs": []}
            if safe.is_dir():
                return {"skipped": f"pytest target {arg} is too broad; choose explicit test files", "extra_inputs": []}
            targets.append(arg)
            filtered.append(arg)
        if not targets:
            return {"skipped": "pytest verifier requires explicit test file targets", "extra_inputs": []}
        extras = list(dict.fromkeys([*targets, *proposed.keys(), "pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py"]))
        return {"argv": [*prefix, *filtered], "timeout": 20, "extra_inputs": extras}

    def _copy_agent_verifier_input(root: Path, temp_root: Path, rel: str) -> None:
        source = _safe_relative(root, rel)
        target = _safe_relative(temp_root, rel)
        if source is None or target is None or not source.exists() or not source.is_file():
            return
        if target.exists() or source.stat().st_size > 300_000:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def _request_base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    def _agent_related_context(root: Path, objective: str, selected_files: list[str], limit: int = 12) -> list[str]:
        """Return a small, workspace-bounded context expansion for an IDE agent.

        The renderer's context picker is useful for explicit scope, but a coding
        agent also needs the directly related implementation/test files that a
        VS Code user expects it to inspect.  This remains advisory context: all
        returned paths must already exist under the workspace and every edit is
        still constrained to this resulting allow-list and SourcePlan review.
        """
        discovered: list[str] = []

        def add(value: Any) -> None:
            candidate = str(value or "").replace("\\", "/").strip()
            target = _safe_relative(root, candidate)
            if target is None or not target.is_file():
                return
            relative = target.relative_to(root).as_posix()
            if relative not in discovered:
                discovered.append(relative)

        for path in selected_files:
            add(path)
        try:
            editing = code_cortex_router.get_editing_context(root, objective, limit=max(1, min(limit, 24)))
            for row in (editing.get("files") or editing.get("results") or []):
                add(row if isinstance(row, str) else row.get("path") if isinstance(row, dict) else "")
            for row in (editing.get("symbols") or []):
                if isinstance(row, dict):
                    add(row.get("path") or row.get("file"))
            for path in selected_files[:4]:
                dependents = code_cortex_router.get_dependents(root, path, limit=max(1, min(limit, 24)))
                for row in (dependents.get("dependents") or dependents.get("related_files") or dependents.get("files") or dependents.get("results") or []):
                    add(row if isinstance(row, str) else row.get("path") or row.get("file") or row.get("dependent") if isinstance(row, dict) else "")
        except Exception:
            # Context discovery must never make an explicit user-selected file
            # unusable; the selected scope remains a valid bounded fallback.
            pass
        return discovered[: max(1, min(limit, 24))]

    _ANSI_ESCAPE = re.compile(r"(?:\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07]*(?:\x07|\x1B\\))")

    def _sanitize_model_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove terminal control bytes from conversational history only.

        Exact source files and Action-IR anchors are deliberately not touched:
        altering them would make otherwise valid patch anchors unsafe.
        """
        cleaned: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            content = item.get("content")
            if isinstance(content, str):
                item["content"] = _ANSI_ESCAPE.sub("", content).replace("\r", "")
            cleaned.append(item)
        return cleaned

    def _skill_recipe_suggestions(root: Path, objective: str, *, limit: int = 3) -> list[dict[str, Any]]:
        """Return small, verified-recipe metadata for an optional model hint.

        Skills are never executable instructions on this path.  This function
        intentionally returns only identifiers, quality signals, and a short
        description; a model cannot use a historical skill to widen files,
        tools, or write authority.
        """
        terms = {item.lower() for item in re.findall(r"[A-Za-z_][A-Za-z0-9_/-]*", objective) if len(item) > 2}
        try:
            skills = SkillTree(data_dir=str(root / ".beast" / "intelligence" / "skills")).list_skills(limit=100)
        except Exception:
            return []
        ranked: list[tuple[int, dict[str, Any]]] = []
        for skill in skills:
            metadata = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
            validation = metadata.get("validation") if isinstance(metadata.get("validation"), dict) else {}
            verified = validation.get("status") in {"passed", "passed_with_warnings"} or metadata.get("verified") is True
            if not verified or float(skill.get("success_rate") or 0.0) < 0.8:
                continue
            text = " ".join((str(skill.get("name") or ""), str(skill.get("category") or ""), str(metadata.get("description") or ""))).lower()
            overlap = sum(1 for term in terms if term in text)
            if overlap:
                ranked.append((overlap, {
                    "skill_id": str(skill.get("id") or ""),
                    "name": str(skill.get("name") or ""),
                    "category": str(skill.get("category") or ""),
                    "success_rate": round(float(skill.get("success_rate") or 0.0), 3),
                    "usage_count": int(skill.get("usage_count") or 0),
                    "description": str(metadata.get("description") or "")[:280],
                    "verified": True,
                    "authority": "advisory_recipe_only",
                }))
        return [item for _score, item in sorted(ranked, key=lambda row: (-row[0], -row[1]["success_rate"], -row[1]["usage_count"]))[:max(1, min(limit, 8))]]

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
            action("agents.verify_requested_checks", "Run Agent Requested Checks", "agents", "Run allowlisted verifier commands requested by the coding agent in an isolated temporary workspace.", handler="verifyAgentRequestedChecks", endpoint="/edgek/ide/agent-sessions/verify-sourceplan", method="POST", tags=["agent", "verify", "sourceplan"], approval_required=True, sourceplan_required=True),
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
            action("tooling.grade_benchmark_packet", "Run Benchmark Grading Daemon", "tooling", "Trigger the public benchmark grading daemon for the full blind packet and load provisional plus structural verdicts.", handler="runBenchmarkGradingDaemon", endpoint="/edgek/benchmarks/public-grading-daemon", method="POST", tags=["tooling", "benchmark", "grading"]),
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

    def _tool_event(
        session_id: str,
        *,
        tool: str,
        text: str,
        phase: str = "observe",
        status: str = "completed",
        authority: str = "read-only/governed",
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "type": "tool_result",
            "tool": tool,
            "phase": phase,
            "status": status,
            "authority": authority,
            "text": text,
            "result": result or {},
        }

    def _tool_call_event(
        session_id: str,
        *,
        tool: str,
        text: str,
        phase: str = "observe",
        authority: str = "read-only/governed",
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "type": "tool_call",
            "tool": tool,
            "phase": phase,
            "status": "started",
            "authority": authority,
            "text": text,
            "parameters": parameters or {},
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

            route_text = read_if_exists(files["ide_routes"])
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

    register_system_inspection_routes(router, resolve_root=_root)

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

    register_agent_session_routes(
        router,
        resolve_root=_root,
        compile_action_ir_sourceplan=_compile_agent_action_ir_sourceplan,
        validate_agent_sourceplan=_validate_agent_sourceplan,
        json_hash=_json_hash,
    )

    @router.get("/edgek/ide/agent-sessions/{session_id}/run-events")
    async def edgek_ide_agent_session_run_events(
        request: Request,
        session_id: str,
        root_path: str = None,
        prompt: str = "",
        provider: str = "",
        model: str = "",
        context_files: List[str] | None = Query(default=None),
        simulate: bool = False,
        max_tokens: int = 2000,
        context_max_chars_each: int = 30000,
        max_repair_rounds: int = 3,
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
                    yield chunk
            except Exception as exc:
                yield _event("agent_run_error", {
                    "ok": False,
                    "session_id": session_id,
                    "error": f"Agent run stream terminated before completion: {exc}",
                })
                yield _event("agent_run_done", {
                    "ok": False,
                    "session_id": session_id,
                    "chars": 0,
                    "sourceplan_status": "stream_error",
                    "session": {},
                })

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
                "old": original_text,
                "new": new_text,
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

    register_worktree_mission_routes(router, resolve_root=_root)

    return router
