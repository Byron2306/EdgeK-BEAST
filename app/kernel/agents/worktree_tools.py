"""Isolated mutation and verification tools bound to BEAST Worktree Forge."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any

from app.kernel.agents.tool_models import ToolEffect, ToolExecutionContext, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import AgentToolRegistry
from app.kernel.agents.tool_runtime import _remote_target_descriptor, _run_target_shell, _safe_remote_relative, _shell_quote
from app.kernel.workspaces.worktree_forge import WorktreeForge


def _is_remote_target(context: ToolExecutionContext) -> bool:
    return str(context.execution_target or "local").strip().lower() not in {"", "local"}


def _remote_worktree_root(context: ToolExecutionContext) -> str:
    root = str(context.worktree_root or "").strip()
    if not root:
        raise PermissionError("a target-side isolated worktree is required")
    if ".." in root.split("/") or not re.fullmatch(r"[~\/@A-Za-z0-9._+\-]+", root):
        raise ValueError("target-side worktree root is outside safe path syntax")
    return root


def _remote_result_context(context: ToolExecutionContext, descriptor: dict[str, str]) -> dict[str, Any]:
    return {
        "target_execution": f"remote_{descriptor['kind']}",
        "execution_target": str(context.execution_target or "local"),
        "execution_target_payload": dict(context.execution_target_payload or {}),
        "remote_root": descriptor.get("base", ""),
        "transport": descriptor["kind"],
    }


def _marker_section(stdout: str, start: str, end: str | None = None) -> str:
    if start not in stdout:
        return ""
    tail = stdout.split(start, 1)[1]
    if end and end in tail:
        tail = tail.split(end, 1)[0]
    return tail.lstrip("\r\n")


def _diff_files_from_evidence(*values: str) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for value in values:
        for line in str(value or "").splitlines():
            path = ""
            diff_match = re.match(r"^diff --git a/(.*?) b/(.*?)$", line)
            if diff_match:
                path = diff_match.group(2)
            elif re.match(r"^[ MADRCU?!]{1,2}\s+", line):
                path = re.sub(r"^[ MADRCU?!]{1,2}\s+", "", line).strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[1].strip()
            elif (
                line.strip()
                and not line.startswith((" ", "\t", "BEAST_", "+++", "---", "@@", "+", "-"))
                and not re.search(r"\|\s+\d+", line)
                and "/" not in line[:8]
            ):
                path = line.strip()
            if not path or path.startswith(".git/") or ".." in path.split("/"):
                continue
            if path not in seen:
                seen.add(path)
                files.append(path)
    return files[:200]


def _remote_sourceplan_draft_from_diff(
    *,
    context: ToolExecutionContext,
    descriptor: dict[str, str],
    task_id: str,
    root: str,
    diff_result: dict[str, Any],
    max_chars: int,
) -> dict[str, Any]:
    patch = str(diff_result.get("diff") or "")
    files = list(diff_result.get("files") or [])
    if not files:
        files = _diff_files_from_evidence(
            str(diff_result.get("name_only") or ""),
            str(diff_result.get("status") or ""),
            patch,
        )
    plan_id = f"remote-worktree-promotion-{task_id}"
    translation_notes = [
        {
            "path": "*",
            "reason": "remote target SourcePlan is evidence-only until target-side apply/promotion is available",
        }
    ]
    plan = {
        "beast_object_type": "sourceplan",
        "kind": "beast_remote_source_patch_plan",
        "version": "1.0",
        "plan_id": plan_id,
        "objective": f"Promote verified remote worktree mission: {task_id}",
        "status": "draft",
        "source": "remote_worktree_native_mission",
        "worktree_task_id": task_id,
        "worktree_path": root,
        "branch": str(diff_result.get("branch") or ""),
        "base_ref": str(diff_result.get("base_ref") or ""),
        "base_label": str(diff_result.get("base_ref") or ""),
        "diff_range": "remote-worktree",
        "files": files,
        "selected_files": files,
        "diff_stat": str(diff_result.get("stat") or ""),
        "worktree_diff": patch[:max_chars],
        "diff_truncated": bool(diff_result.get("truncated")) or len(patch) > max_chars,
        "operations": [],
        "selected_operations": [],
        "requires_operator_translation": True,
        "translation_notes": translation_notes,
        "governance_note": "Remote worktree promotion remains governed: target-side preview, approve, verify, rollback, and evidence closure are required before any write.",
        **_remote_result_context(context, descriptor),
    }
    receipt = {
        "beast_object_type": "beast_remote_sourceplan_draft_receipt",
        "version": "1.0",
        "task_id": task_id,
        "plan_id": plan_id,
        "ok": True,
        "files": files,
        "diff_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        **_remote_result_context(context, descriptor),
    }
    return {"ok": True, "plan": plan, "receipt": receipt, "task_id": task_id, **_remote_result_context(context, descriptor)}


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


def _advance_mutation_epoch(context: ToolExecutionContext, *, path: str, operation: str) -> int:
    if context.engine is None:
        return 0
    run = context.engine.store.get_run(context.run_id) or {}
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    epoch = max(0, int(checkpoint.get("worktree_mutation_epoch") or 0)) + 1
    context.engine.merge_checkpoint(context.run_id, {
        "worktree_mutation_epoch": epoch,
        "verification": {
            "ok": False,
            "stale": True,
            "reason": "worktree mutated after last verification",
            "mutation_epoch": epoch,
        },
        "sourceplan": {},
    })
    context.engine.emit(context.run_id, "agent.worktree.mutated", {
        "mutation_epoch": epoch,
        "path": path,
        "operation": operation,
    })
    return epoch


async def _worktree_bind(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        safe_run = re.sub(r"[^A-Za-z0-9_.-]", "-", context.run_id)[:80] or "run"
        base_ref = str(arguments.get("base_ref") or "HEAD")
        if not re.fullmatch(r"[A-Za-z0-9_./:@+\-]{1,160}", base_ref) or ".." in base_ref.split("/"):
            raise ValueError("remote worktree base_ref is outside safe syntax")
        branch = f"beast-agent-{safe_run}"
        worktree_root = f"{descriptor['base'].rstrip('/')}/.beast/agent-worktrees/{safe_run}"
        script = (
            f"cd {_shell_quote(descriptor['base'])} && "
            "mkdir -p .beast/agent-worktrees && "
            f"git rev-parse --verify {_shell_quote(base_ref)} >/dev/null && "
            f"git worktree remove --force {_shell_quote(worktree_root)} >/dev/null 2>&1 || true; "
            f"git branch -D {_shell_quote(branch)} >/dev/null 2>&1 || true; "
            f"git worktree add -B {_shell_quote(branch)} {_shell_quote(worktree_root)} {_shell_quote(base_ref)} >/tmp/beast-worktree-add.out 2>&1 && "
            f"cd {_shell_quote(worktree_root)} && printf 'BEAST_WORKTREE\\n' && pwd && git rev-parse HEAD && git branch --show-current"
        )
        result = await _run_target_shell(context, script, timeout=45.0, output_limit=128000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or result["stdout"] or f"remote worktree bind failed with exit {result['returncode']}")
        lines = [line for line in result["stdout"].splitlines() if line]
        marker = lines.index("BEAST_WORKTREE") if "BEAST_WORKTREE" in lines else -1
        resolved_root = lines[marker + 1] if marker >= 0 and len(lines) > marker + 1 else worktree_root
        base_commit = lines[marker + 2] if marker >= 0 and len(lines) > marker + 2 else ""
        resolved_branch = lines[marker + 3] if marker >= 0 and len(lines) > marker + 3 else branch
        if context.engine is not None:
            context.engine.merge_checkpoint(context.run_id, {
                "worktree_task_id": f"remote-{safe_run}",
                "worktree_root": resolved_root,
                "worktree_branch": resolved_branch,
                "worktree_base_commit": base_commit,
                "worktree_remote": True,
                "worktree_execution_target": str(context.execution_target or ""),
                "worktree_execution_target_payload": dict(context.execution_target_payload or {}),
            })
        return {
            "task_id": f"remote-{safe_run}",
            "worktree_root": resolved_root,
            "branch": resolved_branch,
            "base_commit": base_commit,
            "status": "bound",
            **_remote_result_context(context, descriptor),
        }
    forge = WorktreeForge(context.workspace_root)
    # WorktreeForge is already internally bounded with subprocess timeouts.
    # Running it through asyncio.to_thread has proven to hang in this runtime,
    # which stalls the full agent loop before the first mutation step.
    result = forge.create(
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
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        relative = _safe_remote_relative(arguments.get("path") or "")
        content = str(arguments.get("content") or "")
        if len(content.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("write exceeds 2 MiB mutation boundary")
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        remote_file = f"{root.rstrip('/')}/{relative}"
        source_file = f"{descriptor['base'].rstrip('/')}/{relative}"
        script = (
            f"test ! -e {_shell_quote(source_file)} && "
            f"test ! -e {_shell_quote(remote_file)} && "
            f"cd {_shell_quote(root)} && mkdir -p {_shell_quote(str(Path(relative).parent))} && "
            f"printf %s {_shell_quote(encoded)} | base64 -d > {_shell_quote(relative)} && "
            f"sha256sum -- {_shell_quote(relative)} | awk '{{print $1}}'"
        )
        result = await _run_target_shell(context, script, timeout=20.0, output_limit=64000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or result["stdout"] or f"remote write_file failed with exit {result['returncode']}")
        epoch = _advance_mutation_epoch(context, path=relative, operation="write_file")
        return {
            "path": relative,
            "mutation_epoch": epoch,
            "created": True,
            "before_sha256": "",
            "after_sha256": result["stdout"].strip().splitlines()[-1] if result["stdout"].strip() else hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "bytes_written": len(content.encode("utf-8")),
            **_remote_result_context(context, descriptor),
        }
    path = _safe_worktree_path(context, str(arguments.get("path") or ""))
    content = str(arguments.get("content") or "")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("write exceeds 2 MiB mutation boundary")
    source_path = (Path(context.workspace_root).resolve() / str(arguments.get("path") or "")).resolve()
    try:
        source_path.relative_to(Path(context.workspace_root).resolve())
    except ValueError:
        raise ValueError("path escapes workspace root") from None
    if source_path.exists():
        raise ValueError("existing files require bounded worktree.replace_exact; write_file is creation-only")
    existed = path.exists()
    before = path.read_bytes() if existed and path.is_file() else b""
    if existed and not path.is_file():
        raise ValueError("target is not a regular file")
    if existed:
        raise ValueError("existing files require bounded worktree.replace_exact; write_file is creation-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    relative = path.relative_to(_worktree_root(context)).as_posix()
    epoch = _advance_mutation_epoch(context, path=relative, operation="write_file")
    return {
        "path": relative,
        "mutation_epoch": epoch,
        "created": not existed,
        "before_sha256": hashlib.sha256(before).hexdigest() if existed else "",
        "after_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "bytes_written": len(content.encode("utf-8")),
    }


async def _worktree_replace_exact(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        relative = _safe_remote_relative(arguments.get("path") or "")
        old_text = str(arguments.get("old_text") or "")
        new_text = str(arguments.get("new_text") or "")
        expected = max(1, min(int(arguments.get("expected_occurrences") or 1), 100))
        if not old_text:
            raise ValueError("old_text is required")
        payload = base64.b64encode(f"{old_text}\0{new_text}".encode("utf-8")).decode("ascii")
        script = (
            f"cd {_shell_quote(root)} && "
            f"test -f {_shell_quote(relative)} && "
            f"test $(wc -c < {_shell_quote(relative)}) -le 4194304 && "
            "python3 - <<'PY'\n"
            "import base64, hashlib, pathlib\n"
            f"path = pathlib.Path({_shell_quote(relative)})\n"
            f"old, new = base64.b64decode({_shell_quote(payload)}).decode('utf-8').split('\\0', 1)\n"
            f"expected = {expected}\n"
            "text = path.read_text(encoding='utf-8')\n"
            "found = text.count(old)\n"
            "if found != expected:\n"
            "    raise SystemExit(f'replace_exact expected {expected} occurrence(s), found {found}')\n"
            "updated = text.replace(old, new, expected)\n"
            "path.write_text(updated, encoding='utf-8')\n"
            "print(hashlib.sha256(text.encode('utf-8')).hexdigest())\n"
            "print(hashlib.sha256(updated.encode('utf-8')).hexdigest())\n"
            "PY"
        )
        result = await _run_target_shell(context, script, timeout=20.0, output_limit=128000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or result["stdout"] or f"remote replace_exact failed with exit {result['returncode']}")
        hashes = [line.strip() for line in result["stdout"].splitlines() if re.fullmatch(r"[a-f0-9]{64}", line.strip())]
        epoch = _advance_mutation_epoch(context, path=relative, operation="replace_exact")
        return {
            "path": relative,
            "mutation_epoch": epoch,
            "replacements": expected,
            "before_sha256": hashes[0] if hashes else "",
            "after_sha256": hashes[1] if len(hashes) > 1 else "",
            **_remote_result_context(context, descriptor),
        }
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
    relative = path.relative_to(_worktree_root(context)).as_posix()
    epoch = _advance_mutation_epoch(context, path=relative, operation="replace_exact")
    return {
        "path": relative,
        "mutation_epoch": epoch,
        "replacements": expected,
        "before_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
    }


async def _worktree_run_verification(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        command = arguments.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise ValueError("command must be a non-empty string array")
        if len(command) > 32:
            raise ValueError("verification command exceeds 32 arguments")
        timeout = max(1.0, min(float(arguments.get("timeout_seconds") or 120), 600.0))
        script = (
            f"cd {_shell_quote(root)} && "
            "export GIT_OPTIONAL_LOCKS=0 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 && "
            + " ".join(_shell_quote(part) for part in command)
        )
        result_shell = await _run_target_shell(context, script, timeout=timeout, output_limit=512000)
        out = str(result_shell.get("stdout") or "")
        err = str(result_shell.get("stderr") or "")
        result = {
            "command": list(command),
            "resolved_command": list(command),
            "returncode": int(result_shell.get("returncode") or 0),
            "ok": bool(result_shell.get("ok")),
            "stdout": out[-20000:],
            "stderr": err[-12000:],
            **_remote_result_context(context, descriptor),
        }
        if context.engine is not None:
            run = context.engine.store.get_run(context.run_id) or {}
            checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
            mutation_epoch = max(0, int(checkpoint.get("worktree_mutation_epoch") or 0))
            context.engine.merge_checkpoint(context.run_id, {
                "verification": {
                    "ok": bool(result["ok"]),
                    "stale": False,
                    "mutation_epoch": mutation_epoch,
                    "command": list(command),
                    "resolved_command": list(command),
                    "returncode": int(result_shell.get("returncode") or 0),
                    "stdout_sha256": hashlib.sha256(out.encode("utf-8")).hexdigest(),
                    "stderr_sha256": hashlib.sha256(err.encode("utf-8")).hexdigest(),
                    "stdout_tail": out[-4000:],
                    "stderr_tail": err[-4000:],
                    "execution_target": str(context.execution_target or "local"),
                    "execution_target_payload": dict(context.execution_target_payload or {}),
                    "target_execution": f"remote_{descriptor['kind']}",
                }
            })
            context.engine.emit(
                context.run_id,
                "agent.verification.passed" if result["ok"] else "agent.verification.failed",
                {
                    "ok": bool(result["ok"]),
                    "mutation_epoch": mutation_epoch,
                    "command": list(command),
                    "returncode": int(result_shell.get("returncode") or 0),
                    "execution_target": str(context.execution_target or "local"),
                    "execution_target_payload": dict(context.execution_target_payload or {}),
                    "target_execution": f"remote_{descriptor['kind']}",
                },
            )
        if not result["ok"]:
            result["error"] = f"verification failed with exit code {result['returncode']}: {err[-2000:] or out[-2000:]}"
        return result
    root = _worktree_root(context)
    command = arguments.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("command must be a non-empty string array")
    if len(command) > 32:
        raise ValueError("verification command exceeds 32 arguments")
    requested_command = list(command)
    command = list(requested_command)
    if command[0] in {"python", "python3"}:
        command[0] = sys.executable
    timeout = max(1.0, min(float(arguments.get("timeout_seconds") or 120), 600.0))
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
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
        "command": requested_command,
        "resolved_command": command,
        "returncode": process.returncode,
        "ok": process.returncode == 0,
        "stdout": out[-20000:],
        "stderr": err[-12000:],
        "execution_target": str(context.execution_target or "local"),
        "execution_target_payload": dict(context.execution_target_payload or {}),
    }
    if context.engine is not None:
        run = context.engine.store.get_run(context.run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        mutation_epoch = max(0, int(checkpoint.get("worktree_mutation_epoch") or 0))
        context.engine.merge_checkpoint(context.run_id, {
            "verification": {
                "ok": bool(result["ok"]),
                "stale": False,
                "mutation_epoch": mutation_epoch,
                "command": requested_command,
                "resolved_command": command,
                "returncode": process.returncode,
                "stdout_sha256": hashlib.sha256(out.encode("utf-8")).hexdigest(),
                "stderr_sha256": hashlib.sha256(err.encode("utf-8")).hexdigest(),
                "stdout_tail": out[-4000:],
                "stderr_tail": err[-4000:],
                "execution_target": str(context.execution_target or "local"),
                "execution_target_payload": dict(context.execution_target_payload or {}),
            }
        })
        context.engine.emit(
            context.run_id,
            "agent.verification.passed" if result["ok"] else "agent.verification.failed",
            {
                "ok": bool(result["ok"]),
                "mutation_epoch": mutation_epoch,
                "command": requested_command,
                "resolved_command": command,
                "returncode": process.returncode,
                "execution_target": str(context.execution_target or "local"),
                "execution_target_payload": dict(context.execution_target_payload or {}),
            },
        )
    if process.returncode != 0:
        result["error"] = f"verification failed with exit code {process.returncode}: {err[-2000:] or out[-2000:]}"
    return result


async def _worktree_diff(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    task_id = str((context.engine.store.get_run(context.run_id).get("checkpoint") or {}).get("worktree_task_id") or "") if context.engine else ""
    if not task_id:
        raise ValueError("bound worktree task id is missing")
    max_chars = max(1000, min(int(arguments.get("max_chars") or 40000), 100000))
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        script = (
            f"cd {_shell_quote(root)} && "
            "printf 'BEAST_DIFF_STATUS\\n' && "
            "git status --short && "
            "printf 'BEAST_DIFF_STAT\\n' && "
            "git diff --stat -- . && "
            "printf 'BEAST_DIFF_NAME_ONLY\\n' && "
            "git diff --name-only -- . && "
            "printf 'BEAST_DIFF_PATCH\\n' && "
            f"git diff --no-color --no-ext-diff -- . | head -c {max_chars}"
        )
        result = await _run_target_shell(context, script, timeout=20.0, output_limit=max_chars + 32000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or result["stdout"] or f"remote worktree.diff failed with exit {result['returncode']}")
        stdout = str(result.get("stdout") or "")
        status = _marker_section(stdout, "BEAST_DIFF_STATUS", "BEAST_DIFF_STAT").strip()
        stat = _marker_section(stdout, "BEAST_DIFF_STAT", "BEAST_DIFF_NAME_ONLY").strip()
        name_only = _marker_section(stdout, "BEAST_DIFF_NAME_ONLY", "BEAST_DIFF_PATCH").strip()
        patch = _marker_section(stdout, "BEAST_DIFF_PATCH").rstrip("\r\n")
        files = _diff_files_from_evidence(name_only) or _diff_files_from_evidence(status, patch)
        return {
            "ok": True,
            "task_id": task_id,
            "worktree_root": root,
            "status": status,
            "stat": stat,
            "name_only": name_only,
            "files": files,
            "diff": patch,
            "truncated": bool(result.get("truncated")) or len(patch) >= max_chars,
            "commands": [{
                "ok": True,
                "args": ["target-shell", "git diff"],
                "stdout": stdout[-4000:],
                "stderr": str(result.get("stderr") or "")[-4000:],
                "returncode": int(result.get("returncode") or 0),
            }],
            **_remote_result_context(context, descriptor),
        }
    return WorktreeForge(context.workspace_root).diff(task_id, max_chars)


async def _worktree_sourceplan(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    run = context.engine.store.get_run(context.run_id) if context.engine else {}
    checkpoint = run.get("checkpoint") if isinstance(run, dict) and isinstance(run.get("checkpoint"), dict) else {}
    verification = checkpoint.get("verification") if isinstance(checkpoint.get("verification"), dict) else {}
    mutation_epoch = max(0, int(checkpoint.get("worktree_mutation_epoch") or 0))
    verification_epoch = max(-1, int(verification.get("mutation_epoch") if verification.get("mutation_epoch") is not None else -1))
    if not verification.get("ok") or verification.get("stale") or verification_epoch != mutation_epoch:
        raise PermissionError("SourcePlan synthesis requires a current passing verification receipt for the latest mutation epoch")
    task_id = str(checkpoint.get("worktree_task_id") or "")
    if not task_id:
        raise ValueError("bound worktree task id is missing")
    max_chars = max(1000, min(int(arguments.get("max_chars") or 60000), 120000))
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        diff_result = await _worktree_diff({"max_chars": max_chars}, context)
        result = _remote_sourceplan_draft_from_diff(
            context=context,
            descriptor=descriptor,
            task_id=task_id,
            root=root,
            diff_result=diff_result,
            max_chars=max_chars,
        )
    else:
        result = WorktreeForge(context.workspace_root).sourceplan_draft_from_diff(
            task_id,
            max_chars,
        )
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "SourcePlan synthesis failed"))
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    if context.engine is not None:
        event_payload = {
            "plan_id": plan.get("plan_id"),
            "worktree_task_id": task_id,
            "files": plan.get("files") or [],
            "plan": plan,
            "requires_operator_translation": bool(plan.get("requires_operator_translation")),
        }
        context.engine.merge_checkpoint(context.run_id, {
            "sourceplan": {
                "plan_id": str(plan.get("plan_id") or ""),
                "status": str(plan.get("status") or "draft"),
                "worktree_task_id": task_id,
                "file_count": len(plan.get("files") or []),
                "requires_operator_translation": bool(plan.get("requires_operator_translation")),
                "execution_target": str(context.execution_target or "local"),
                "execution_target_payload": dict(context.execution_target_payload or {}),
                "target_execution": str(result.get("target_execution") or ""),
            }
        })
        context.engine.emit(context.run_id, "agent.sourceplan.ready", event_payload)
        try:
            from app.kernel.agents.planning_integrations import PlanningIntegrationRuntime
            PlanningIntegrationRuntime(str(context.workspace_root)).sync_phase7_handoff(
                context.run_id,
                "agent.sourceplan.ready",
                event_payload,
                run=context.engine.store.get_run(context.run_id),
            )
        except Exception as exc:
            context.engine.emit(context.run_id, "agent.plan.integration.failed", {
                "integration_id": "phase7_handoff_promotion",
                "reason": f"{type(exc).__name__}: {exc}",
                "event_type": "agent.sourceplan.ready",
            })
    return result


def register_worktree_tools(registry: AgentToolRegistry) -> AgentToolRegistry:
    mutation_approval = True
    registry.register(ToolSpec(
        tool_id="worktree.bind", version="1", title="Create isolated worktree",
        description="Create and bind an isolated Git worktree to this AgentRun.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","properties":{"objective":{"type":"string"},"risk":{"type":"string"},"provider":{"type":"string"},"base_ref":{"type":"string"},"task_id":{"type":"string"}},"additionalProperties":False},
        timeout_seconds=45, requires_approval=mutation_approval, idempotent=False, targets=("local","ssh","container"), handler=_worktree_bind,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.write_file", version="1", title="Write isolated file",
        description="Create or replace a UTF-8 file only inside the bound worktree.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","required":["path","content"],"properties":{"path":{"type":"string"},"content":{"type":"string"}},"additionalProperties":False},
        timeout_seconds=10, requires_approval=mutation_approval, requires_worktree=True, idempotent=False, targets=("local","ssh","container"), handler=_worktree_write_file,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.replace_exact", version="1", title="Replace exact text in worktree",
        description="Perform a bounded exact replacement only inside the bound worktree.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","required":["path","old_text","new_text"],"properties":{"path":{"type":"string"},"old_text":{"type":"string"},"new_text":{"type":"string"},"expected_occurrences":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=10, requires_approval=mutation_approval, requires_worktree=True, idempotent=False, targets=("local","ssh","container"), handler=_worktree_replace_exact,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.verify", version="1", title="Run worktree verification",
        description="Run an explicit argv verification command inside the bound worktree without a shell.", category="verification",
        risk=ToolRisk.HIGH, effect=ToolEffect.EXECUTION,
        input_schema={"type":"object","required":["command"],"properties":{"command":{"type":"array"},"timeout_seconds":{"type":"number"}},"additionalProperties":False},
        timeout_seconds=610, requires_approval=True, requires_worktree=True, idempotent=False, targets=("local","ssh","container"), handler=_worktree_run_verification,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.diff", version="1", title="Inspect worktree diff",
        description="Read the current isolated worktree diff.", category="worktree",
        risk=ToolRisk.LOW, effect=ToolEffect.READ,
        input_schema={"type":"object","properties":{"max_chars":{"type":"integer"}},"additionalProperties":False},
        requires_worktree=True, targets=("local","ssh","container"), handler=_worktree_diff,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.sourceplan_draft", version="1", title="Synthesize SourcePlan draft",
        description="Build a non-applying SourcePlan draft from a verified worktree diff.", category="sourceplan",
        risk=ToolRisk.MEDIUM, effect=ToolEffect.READ,
        input_schema={"type":"object","properties":{"max_chars":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=30, requires_worktree=True, targets=("local","ssh","container"), handler=_worktree_sourceplan,
    ))
    return registry
