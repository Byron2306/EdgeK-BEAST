"""Isolated mutation and verification tools bound to BEAST Worktree Forge."""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

from app.kernel.agents.tool_models import ToolEffect, ToolExecutionContext, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import AgentToolRegistry
from app.kernel.workspaces.worktree_forge import WorktreeForge


def _worktree_root(context: ToolExecutionContext) -> Path:
    if not context.worktree_root:
        raise PermissionError("an isolated worktree is required")
    root = Path(context.worktree_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError("bound worktree does not exist")
    return root


def _safe_worktree_path(context: ToolExecutionContext, relative: str) -> Path:
    root = _worktree_root(context)
    candidate = (root / str(relative or "")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes isolated worktree") from exc
    if ".git" in candidate.relative_to(root).parts:
        raise PermissionError("agent tools cannot mutate .git metadata")
    return candidate


async def _worktree_bind(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    forge = WorktreeForge(context.workspace_root)
    result = await asyncio.to_thread(
        forge.create,
        objective=str(arguments.get("objective") or f"AgentRun {context.run_id}"),
        risk=str(arguments.get("risk") or "medium"),
        provider=str(arguments.get("provider") or ""),
        mode="agent",
        base_ref=str(arguments.get("base_ref") or "HEAD"),
        task_id=str(arguments.get("task_id") or context.run_id),
    )
    if not result.get("ok"):
        raise RuntimeError(str((result.get("task") or {}).get("error") or "worktree creation failed"))
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    root = str(task.get("worktree_path") or "")
    if context.engine is not None:
        context.engine.merge_checkpoint(context.run_id, {
            "worktree_task_id": str(task.get("task_id") or ""),
            "worktree_root": root,
            "worktree_branch": str(task.get("branch") or ""),
            "worktree_base_commit": str(task.get("base_commit") or ""),
        })
    return {
        "task_id": task.get("task_id"),
        "worktree_root": root,
        "branch": task.get("branch"),
        "base_commit": task.get("base_commit"),
        "status": task.get("status"),
    }


async def _worktree_write_file(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    path = _safe_worktree_path(context, str(arguments.get("path") or ""))
    content = str(arguments.get("content") or "")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("write exceeds 2 MiB mutation boundary")
    existed = path.exists()
    before = path.read_bytes() if existed and path.is_file() else b""
    if existed and not path.is_file():
        raise ValueError("target is not a regular file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "path": path.relative_to(_worktree_root(context)).as_posix(),
        "created": not existed,
        "before_sha256": hashlib.sha256(before).hexdigest() if existed else "",
        "after_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "bytes_written": len(content.encode("utf-8")),
    }


async def _worktree_replace_exact(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    path = _safe_worktree_path(context, str(arguments.get("path") or ""))
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("file exceeds 4 MiB mutation boundary")
    old_text = str(arguments.get("old_text") or "")
    new_text = str(arguments.get("new_text") or "")
    expected = max(1, min(int(arguments.get("expected_occurrences") or 1), 100))
    text = path.read_text(encoding="utf-8", errors="strict")
    found = text.count(old_text)
    if not old_text or found != expected:
        raise ValueError(f"replace_exact expected {expected} occurrence(s), found {found}")
    updated = text.replace(old_text, new_text, expected)
    path.write_text(updated, encoding="utf-8")
    return {
        "path": path.relative_to(_worktree_root(context)).as_posix(),
        "replacements": expected,
        "before_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
    }


async def _worktree_run_verification(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    root = _worktree_root(context)
    command = arguments.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("command must be a non-empty string array")
    if len(command) > 32:
        raise ValueError("verification command exceeds 32 arguments")
    timeout = max(1.0, min(float(arguments.get("timeout_seconds") or 120), 600.0))
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise TimeoutError(f"verification exceeded {timeout:g}s")
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    result = {
        "command": command,
        "returncode": process.returncode,
        "ok": process.returncode == 0,
        "stdout": out[-20000:],
        "stderr": err[-12000:],
    }
    if context.engine is not None:
        context.engine.merge_checkpoint(context.run_id, {
            "verification": {
                "ok": bool(result["ok"]),
                "command": command,
                "returncode": process.returncode,
                "stdout_sha256": hashlib.sha256(out.encode("utf-8")).hexdigest(),
                "stderr_sha256": hashlib.sha256(err.encode("utf-8")).hexdigest(),
            }
        })
    if process.returncode != 0:
        raise RuntimeError(f"verification failed with exit code {process.returncode}: {err[-2000:] or out[-2000:]}")
    return result


async def _worktree_diff(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    task_id = str((context.engine.store.get_run(context.run_id).get("checkpoint") or {}).get("worktree_task_id") or "") if context.engine else ""
    if not task_id:
        raise ValueError("bound worktree task id is missing")
    return await asyncio.to_thread(WorktreeForge(context.workspace_root).diff, task_id, max(1000, min(int(arguments.get("max_chars") or 40000), 100000)))


async def _worktree_sourceplan(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    run = context.engine.store.get_run(context.run_id) if context.engine else {}
    checkpoint = run.get("checkpoint") if isinstance(run, dict) and isinstance(run.get("checkpoint"), dict) else {}
    verification = checkpoint.get("verification") if isinstance(checkpoint.get("verification"), dict) else {}
    if not verification.get("ok"):
        raise PermissionError("SourcePlan synthesis requires a passing worktree verification receipt")
    task_id = str(checkpoint.get("worktree_task_id") or "")
    if not task_id:
        raise ValueError("bound worktree task id is missing")
    result = await asyncio.to_thread(
        WorktreeForge(context.workspace_root).sourceplan_draft_from_diff,
        task_id,
        max(1000, min(int(arguments.get("max_chars") or 60000), 120000)),
    )
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "SourcePlan synthesis failed"))
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    if context.engine is not None:
        context.engine.merge_checkpoint(context.run_id, {
            "sourceplan": {
                "plan_id": str(plan.get("plan_id") or ""),
                "status": str(plan.get("status") or "draft"),
                "worktree_task_id": task_id,
                "file_count": len(plan.get("files") or []),
                "requires_operator_translation": bool(plan.get("requires_operator_translation")),
            }
        })
        context.engine.emit(context.run_id, "agent.sourceplan.ready", {
            "plan_id": plan.get("plan_id"),
            "worktree_task_id": task_id,
            "files": plan.get("files") or [],
            "requires_operator_translation": bool(plan.get("requires_operator_translation")),
        })
    return result


def register_worktree_tools(registry: AgentToolRegistry) -> AgentToolRegistry:
    mutation_approval = True
    registry.register(ToolSpec(
        tool_id="worktree.bind", version="1", title="Create isolated worktree",
        description="Create and bind an isolated Git worktree to this AgentRun.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","properties":{"objective":{"type":"string"},"risk":{"type":"string"},"provider":{"type":"string"},"base_ref":{"type":"string"},"task_id":{"type":"string"}},"additionalProperties":False},
        timeout_seconds=45, requires_approval=mutation_approval, idempotent=False, handler=_worktree_bind,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.write_file", version="1", title="Write isolated file",
        description="Create or replace a UTF-8 file only inside the bound worktree.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","required":["path","content"],"properties":{"path":{"type":"string"},"content":{"type":"string"}},"additionalProperties":False},
        timeout_seconds=10, requires_approval=mutation_approval, requires_worktree=True, idempotent=False, handler=_worktree_write_file,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.replace_exact", version="1", title="Replace exact text in worktree",
        description="Perform a bounded exact replacement only inside the bound worktree.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","required":["path","old_text","new_text"],"properties":{"path":{"type":"string"},"old_text":{"type":"string"},"new_text":{"type":"string"},"expected_occurrences":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=10, requires_approval=mutation_approval, requires_worktree=True, idempotent=False, handler=_worktree_replace_exact,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.verify", version="1", title="Run worktree verification",
        description="Run an explicit argv verification command inside the bound worktree without a shell.", category="verification",
        risk=ToolRisk.HIGH, effect=ToolEffect.EXECUTION,
        input_schema={"type":"object","required":["command"],"properties":{"command":{"type":"array"},"timeout_seconds":{"type":"number"}},"additionalProperties":False},
        timeout_seconds=610, requires_approval=True, requires_worktree=True, idempotent=False, handler=_worktree_run_verification,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.diff", version="1", title="Inspect worktree diff",
        description="Read the current isolated worktree diff.", category="worktree",
        risk=ToolRisk.LOW, effect=ToolEffect.READ,
        input_schema={"type":"object","properties":{"max_chars":{"type":"integer"}},"additionalProperties":False},
        requires_worktree=True, handler=_worktree_diff,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.sourceplan_draft", version="1", title="Synthesize SourcePlan draft",
        description="Build a non-applying SourcePlan draft from a verified worktree diff.", category="sourceplan",
        risk=ToolRisk.MEDIUM, effect=ToolEffect.READ,
        input_schema={"type":"object","properties":{"max_chars":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=30, requires_worktree=True, handler=_worktree_sourceplan,
    ))
    return registry
