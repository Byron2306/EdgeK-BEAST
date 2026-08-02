"""Bounded, observable execution runtime for typed BEAST agent tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app.kernel.agents.tool_models import (
    ToolEffect,
    ToolExecutionContext,
    ToolObservation,
    ToolRequest,
    ToolRisk,
    ToolSpec,
)
from app.kernel.agents.tool_registry import AgentToolRegistry


_EXCLUDED_DIRS = {".git", ".beast", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def _safe_path(root: Path, relative: str) -> Path:
    candidate = (root / str(relative or ".")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes workspace root") from exc
    return candidate


def _bounded_text(value: Any, limit: int) -> tuple[Any, bool]:
    encoded = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    if len(encoded) <= limit:
        return value, False
    if isinstance(value, dict):
        compact = dict(value)
        for key in ("content", "stdout", "stderr", "matches", "entries"):
            if key in compact:
                text = json.dumps(compact[key], default=str, ensure_ascii=False)
                compact[key] = text[: max(256, limit // 2)] + "\n…[truncated]"
                return compact, True
    return {"summary": encoded[:limit].decode("utf-8", errors="replace"), "truncated": True}, True


async def _workspace_list(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    root = Path(context.workspace_root).resolve()
    target = _safe_path(root, str(arguments.get("path") or "."))
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(str(target))
    limit = max(1, min(int(arguments.get("limit") or 200), 1000))
    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name in _EXCLUDED_DIRS or child.name.startswith(".beast-") or child.name.startswith(".phase1"):
            continue
        entries.append({
            "name": child.name,
            "path": child.relative_to(root).as_posix(),
            "kind": "directory" if child.is_dir() else "file",
            "size": child.stat().st_size if child.is_file() else None,
        })
        if len(entries) >= limit:
            break
    return {"path": target.relative_to(root).as_posix() if target != root else ".", "entries": entries, "count": len(entries)}


async def _workspace_read_range(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    root = Path(context.workspace_root).resolve()
    path = _safe_path(root, str(arguments.get("path") or ""))
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("file exceeds 4 MiB read boundary")
    start = max(1, int(arguments.get("start_line") or 1))
    count = max(1, min(int(arguments.get("line_count") or 200), 1000))
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    selected = lines[start - 1 : start - 1 + count]
    return {
        "path": path.relative_to(root).as_posix(),
        "start_line": start,
        "end_line": start + len(selected) - 1 if selected else start,
        "total_lines": len(lines),
        "content": "\n".join(selected),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


async def _workspace_search_text(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    root = Path(context.workspace_root).resolve()
    query = str(arguments.get("query") or "")
    if not query:
        raise ValueError("query is required")
    path = _safe_path(root, str(arguments.get("path") or "."))
    limit = max(1, min(int(arguments.get("limit") or 100), 500))
    case_sensitive = bool(arguments.get("case_sensitive"))
    needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    candidates = [path] if path.is_file() else path.rglob("*")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        relative_parts = candidate.relative_to(root).parts
        if any(part in _EXCLUDED_DIRS or part.startswith(".beast-") or part.startswith(".phase1") for part in relative_parts):
            continue
        try:
            if candidate.stat().st_size > 2 * 1024 * 1024:
                continue
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            haystack = line if case_sensitive else line.lower()
            if needle in haystack:
                matches.append({"path": candidate.relative_to(root).as_posix(), "line": line_no, "preview": line[:500]})
                if len(matches) >= limit:
                    return {"query": query, "matches": matches, "count": len(matches), "truncated": True}
    return {"query": query, "matches": matches, "count": len(matches), "truncated": False}


async def _git_status(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    root = Path(context.worktree_root or context.workspace_root).resolve()
    process = await asyncio.create_subprocess_exec(
        "git", "-C", str(root), "status", "--short", "--branch",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[:2000])
    return {"root": str(root), "status": stdout.decode("utf-8", errors="replace")}


def build_default_tool_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(ToolSpec(
        tool_id="workspace.list",
        version="1",
        title="List workspace path",
        description="List bounded entries beneath the workspace root.",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False},
        handler=_workspace_list,
    ))
    registry.register(ToolSpec(
        tool_id="workspace.read_range",
        version="1",
        title="Read file range",
        description="Read a bounded line range from a workspace text file.",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "line_count": {"type": "integer"}}, "additionalProperties": False},
        handler=_workspace_read_range,
    ))
    registry.register(ToolSpec(
        tool_id="workspace.search_text",
        version="1",
        title="Search workspace text",
        description="Search bounded workspace text without widening authority.",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "limit": {"type": "integer"}, "case_sensitive": {"type": "boolean"}}, "additionalProperties": False},
        timeout_seconds=20,
        handler=_workspace_search_text,
    ))
    registry.register(ToolSpec(
        tool_id="git.status",
        version="1",
        title="Inspect Git status",
        description="Read repository or worktree status without acquiring Git locks.",
        category="git",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_git_status,
    ))
    return registry


class AgentToolRuntime:
    def __init__(self, engine: Any, registry: AgentToolRegistry | None = None) -> None:
        self.engine = engine
        self.registry = registry or build_default_tool_registry()

    async def execute(self, run_id: str, request: ToolRequest) -> ToolObservation:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        self.engine.raise_if_cancelled(run_id)
        spec = self.registry.get(request.tool_id)
        arguments = self.registry.validate_arguments(spec, request.arguments)
        target = str(request.execution_target or "local")
        if target not in spec.targets:
            raise PermissionError(f"tool {spec.tool_id} does not support target {target}")
        if spec.effect == ToolEffect.PROMOTION:
            raise PermissionError("promotion tools are never agent-executable")
        if spec.requires_approval:
            approval = self.engine.store.get_approval(run_id, request.approval_id) if request.approval_id else None
            if not approval or approval.get("status") != "approved":
                raise PermissionError(f"tool {spec.tool_id} requires an approved capability")
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        worktree_root = str(checkpoint.get("worktree_root") or "")
        if spec.requires_worktree and not worktree_root:
            raise PermissionError(f"tool {spec.tool_id} requires an isolated worktree")
        context = ToolExecutionContext(
            run_id=run_id,
            workspace_root=str(run.get("root_path") or self.engine.workspace_root),
            execution_target=target,
            worktree_root=worktree_root,
            approval_id=request.approval_id,
        )
        started = time.time()
        self.engine.emit(run_id, "agent.tool.started", {
            "tool_id": spec.tool_id,
            "tool_version": spec.version,
            "arguments": arguments,
            "risk": spec.risk.value,
            "effect": spec.effect.value,
            "execution_target": target,
        })
        status = "completed"
        result: dict[str, Any] = {}
        error = ""
        truncated = False
        try:
            assert spec.handler is not None
            raw = await asyncio.wait_for(spec.handler(arguments, context), timeout=max(0.1, spec.timeout_seconds))
            result, truncated = _bounded_text(raw if isinstance(raw, dict) else {"value": raw}, spec.max_output_bytes)
        except asyncio.CancelledError:
            status = "cancelled"
            error = "tool execution cancelled"
            raise
        except Exception as exc:
            status = "failed"
            error = str(exc)
        completed = time.time()
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        observation = ToolObservation(
            observation_id=f"obs_{uuid.uuid4().hex}",
            run_id=run_id,
            tool_id=spec.tool_id,
            tool_version=spec.version,
            status=status,
            started_at=started,
            completed_at=completed,
            duration_ms=max(0, int((completed - started) * 1000)),
            arguments=arguments,
            result=result,
            error=error,
            truncated=truncated,
            evidence_digest=digest,
        )
        event_type = "agent.tool.completed" if status == "completed" else "agent.tool.failed"
        self.engine.emit(run_id, event_type, {"observation": observation.as_dict()})
        self.engine.checkpoint(run_id, {
            "last_observation_id": observation.observation_id,
            "last_tool_id": observation.tool_id,
            "last_tool_status": observation.status,
            "last_tool_evidence_digest": observation.evidence_digest,
        })
        if status != "completed":
            raise RuntimeError(error or f"tool {spec.tool_id} failed")
        return observation
