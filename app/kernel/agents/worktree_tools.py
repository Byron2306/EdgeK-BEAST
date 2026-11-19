"""Isolated mutation and verification tools bound to BEAST Worktree Forge."""
from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.kernel.agents.tool_models import ToolEffect, ToolExecutionContext, ToolRisk, ToolSpec
from app.kernel.agents.tool_registry import AgentToolRegistry
from app.kernel.agents.tool_runtime import _remote_target_descriptor, _run_target_shell, _safe_remote_relative, _shell_quote
from app.kernel.workspaces.worktree_forge import WorktreeForge


def _is_remote_target(context: ToolExecutionContext) -> bool:
    return str(context.execution_target or "local").strip().lower() not in {"", "local"}


def _remote_mutation_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise ValueError("remote mutation requires a relative file path")
    relative = _safe_remote_relative(raw)
    if relative == "." or any(part in {".git", ".beast"} for part in relative.split("/")):
        raise PermissionError("remote mutation cannot modify Git or BEAST governance metadata")
    return relative


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
        if not descriptor["base"].startswith("/"):
            raise ValueError("remote coding requires an absolute workspace root")
        script = (
            f"cd {_shell_quote(descriptor['base'])} && "
            "git rev-parse --is-inside-work-tree >/dev/null && "
            "mkdir -p .beast/agent-worktrees && "
            f"git rev-parse --verify {_shell_quote(base_ref)} >/dev/null && "
            f"test ! -e {_shell_quote(worktree_root)} && "
            f"! git show-ref --verify --quiet {_shell_quote('refs/heads/' + branch)} && "
            f"git worktree add -b {_shell_quote(branch)} {_shell_quote(worktree_root)} {_shell_quote(base_ref)} >/dev/null && "
            f"cd {_shell_quote(worktree_root)} && printf 'BEAST_WORKTREE\\n' && pwd && git rev-parse HEAD && git branch --show-current"
        )
        result = await _run_target_shell(context, script, timeout=45.0, output_limit=128000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or result["stdout"] or f"remote worktree bind failed with exit {result['returncode']}")
        lines = [line for line in result["stdout"].splitlines() if line]
        marker = lines.index("BEAST_WORKTREE") if "BEAST_WORKTREE" in lines else -1
        if marker < 0 or len(lines) < marker + 4:
            raise RuntimeError("remote worktree bind returned incomplete identity evidence")
        resolved_root = lines[marker + 1]
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


def _count_patch_lines(patch: str) -> tuple[int, int]:
    added = removed = 0
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _worktree_patch(context: ToolExecutionContext, relative: str = "", limit: int = 40000) -> dict[str, Any]:
    """Return a bounded unified diff for one file (or the whole worktree)."""
    if context.worktree_root is None:
        return {}
    try:
        root = _worktree_root(context)
    except (PermissionError, FileNotFoundError):
        return {}
    if relative:
        # New files are untracked until staged with --intent-to-add; that only
        # touches the index inside the throwaway worktree.
        subprocess.run(
            ["git", "-C", str(root), "add", "-N", "--", relative],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
        )
    command = ["git", "-C", str(root), "diff", "--no-color", "--no-ext-diff"]
    if relative:
        command.extend(["--", relative])
    try:
        result = subprocess.run(command, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    patch = result.stdout.decode("utf-8", errors="replace")
    added, removed = _count_patch_lines(patch)
    return {
        "diff": patch[:limit],
        "diff_added": added,
        "diff_removed": removed,
        "diff_truncated": len(patch) > limit,
    }


async def _worktree_write_file(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        relative = _remote_mutation_path(arguments.get("path") or "")
        content = str(arguments.get("content") or "")
        if len(content.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("write exceeds 2 MiB mutation boundary")
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        script = (
            f"cd {_shell_quote(root)} && "
            "python3 - <<'PY'\n"
            "import base64, hashlib, pathlib\n"
            "root = pathlib.Path.cwd().resolve()\n"
            f"source_root = pathlib.Path({json.dumps(descriptor['base'])}).resolve()\n"
            f"relative = pathlib.Path({json.dumps(relative)})\n"
            "source_file = (source_root / relative).resolve()\n"
            "source_file.relative_to(source_root)\n"
            "if source_file.exists() or source_file.is_symlink():\n"
            "    raise SystemExit('existing source files require replace_exact')\n"
            "destination = root / relative\n"
            "destination.parent.mkdir(parents=True, exist_ok=True)\n"
            "resolved_parent = destination.parent.resolve()\n"
            "resolved_parent.relative_to(root)\n"
            "resolved_destination = resolved_parent / destination.name\n"
            f"content = base64.b64decode({json.dumps(encoded)})\n"
            "with resolved_destination.open('xb') as handle:\n"
            "    handle.write(content)\n"
            "print(hashlib.sha256(content).hexdigest())\n"
            "PY"
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
        "action_diff": _action_patch(relative, "", content),
        **_worktree_patch(context, relative),
    }


async def _worktree_replace_exact(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if _is_remote_target(context):
        descriptor = _remote_target_descriptor(context)
        root = _remote_worktree_root(context)
        relative = _remote_mutation_path(arguments.get("path") or "")
        old_text = str(arguments.get("old_text") or "")
        new_text = str(arguments.get("new_text") or "")
        expected = max(1, min(int(arguments.get("expected_occurrences") or 1), 100))
        if not old_text:
            raise ValueError("old_text is required")
        payload = base64.b64encode(f"{old_text}\0{new_text}".encode("utf-8")).decode("ascii")
        script = (
            f"cd {_shell_quote(root)} && "
            "python3 - <<'PY'\n"
            "import base64, hashlib, pathlib\n"
            "root = pathlib.Path.cwd().resolve()\n"
            f"relative = pathlib.Path({json.dumps(relative)})\n"
            "path = (root / relative).resolve(strict=True)\n"
            "path.relative_to(root)\n"
            "if not path.is_file() or path.stat().st_size > 4194304:\n"
            "    raise SystemExit('replace_exact requires a regular file <= 4MiB')\n"
            f"old, new = base64.b64decode({json.dumps(payload)}).decode('utf-8').split('\\0', 1)\n"
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
        "action_diff": _action_patch(relative, text, updated),
        **_worktree_patch(context, relative),
    }


def _action_patch(path: str, before: str, after: str) -> str:
    # The canonical Git diff remains available even if the inline view is too large.
    if len(before) + len(after) > 512_000:
        return ""
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", lineterm="",
    )
    return "\n".join(itertools.islice(lines, 80))[:8000]


def _local_worktree_command(argv: list[str]) -> list[str]:
    command = list(argv)
    if command[0] in {"pytest", "py.test"}:
        command = [sys.executable, "-m", "pytest", *command[1:]]
    elif command[0] in {"python", "python3"}:
        command[0] = sys.executable
    if command[:3] == [sys.executable, "-m", "pytest"]:
        explicit_async_plugin = any(
            arg.removeprefix("-p") in {"asyncio", "pytest_asyncio", "pytest_asyncio.plugin",
                                       "no:asyncio", "no:pytest_asyncio", "no:pytest_asyncio.plugin"}
            for arg in command[3:]
        )
        if not explicit_async_plugin and importlib.util.find_spec("pytest_asyncio") is not None:
            command[3:3] = ["-p", "pytest_asyncio.plugin"]
    return command


def _local_worktree_env() -> dict[str, str]:
    # Use the gateway environment without copying a virtualenv into the worktree.
    return {
        **os.environ,
        "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.environ.get("PATH", ""))),
        "GIT_OPTIONAL_LOCKS": "0",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
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
    command = _local_worktree_command(requested_command)
    timeout = max(1.0, min(float(arguments.get("timeout_seconds") or 120), 600.0))
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_local_worktree_env(),
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
        observations = (checkpoint.get("planner") or {}).get("observations") or []
        observed_new_paths = tuple(
            str((obs.get("result") or {}).get("path") or "")
            for obs in observations if isinstance(obs, dict)
            and obs.get("tool_id") == "worktree.write_file" and obs.get("status") == "completed"
        )
        result = WorktreeForge(context.workspace_root).sourceplan_draft_from_diff(
            task_id, max_chars, require_diff=True, observed_new_paths=observed_new_paths,
        )
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "SourcePlan synthesis failed"))
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    if not plan.get("files"):
        raise ValueError("SourcePlan requires a non-empty worktree diff")
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


_WORKTREE_EXCLUDED_DIRS = frozenset({
    ".git", ".beast", ".beast-python-tools", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "dist", "build", ".next", ".nuxt", "target", "coverage", ".idea", ".vscode",
})


def _worktree_relative(context: ToolExecutionContext, value: Any) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if raw.startswith("/"):
        raise ValueError("worktree tools require a path relative to the worktree root")
    return raw or "."


def _worktree_iter_files(root: Path, start: Path):
    """Yield files under ``start`` without entering heavy or generated trees."""
    if start.is_file():
        yield start
        return
    for candidate in start.rglob("*"):
        try:
            relative_parts = candidate.relative_to(root).parts
        except ValueError:
            continue
        if any(part in _WORKTREE_EXCLUDED_DIRS or part.startswith(".beast-") for part in relative_parts):
            continue
        if candidate.is_file() and not candidate.is_symlink():
            yield candidate


def _worktree_result(context: ToolExecutionContext) -> dict[str, Any]:
    return {
        "execution_target": str(context.execution_target or "local"),
        "execution_target_payload": dict(context.execution_target_payload or {}),
        "target_execution": "isolated_worktree",
        "worktree_root": str(context.worktree_root or ""),
    }


async def _worktree_read_file(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    """Read a bounded range from the isolated worktree (never the live workspace)."""
    if _is_remote_target(context):
        raise NotImplementedError("worktree.read_file currently requires a local worktree")
    relative = _worktree_relative(context, arguments.get("path"))
    target = _safe_worktree_path(context, relative)
    if not target.is_file():
        raise FileNotFoundError(f"worktree file not found: {relative}")
    if target.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("worktree.read_file refuses files larger than 8 MiB")
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = max(1, int(arguments.get("start_line") or 1))
    count = max(1, min(int(arguments.get("line_count") or 200), 1000))
    selected = lines[start - 1 : start - 1 + count]
    end = start + len(selected) - 1 if selected else start
    return {
        "path": relative,
        "start_line": start,
        "end_line": end,
        "total_lines": len(lines),
        "content": "\n".join(selected),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "truncated": end < len(lines),
        **_worktree_result(context),
    }


async def _worktree_list(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    """List one directory inside the isolated worktree."""
    if _is_remote_target(context):
        raise NotImplementedError("worktree.list currently requires a local worktree")
    root = _worktree_root(context)
    relative = _worktree_relative(context, arguments.get("path"))
    target = _safe_worktree_path(context, relative)
    if not target.is_dir():
        raise FileNotFoundError(f"worktree directory not found: {relative}")
    limit = max(1, min(int(arguments.get("limit") or 200), 1000))
    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name in _WORKTREE_EXCLUDED_DIRS or child.name.startswith(".beast-"):
            continue
        entries.append({
            "name": child.name,
            "path": child.relative_to(root).as_posix(),
            "kind": "directory" if child.is_dir() else "file",
            "size": child.stat().st_size if child.is_file() else None,
        })
        if len(entries) >= limit:
            break
    return {
        "path": relative,
        "entries": entries,
        "count": len(entries),
        **_worktree_result(context),
    }


async def _worktree_search_text(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    """Search the isolated worktree so the model sees its own edits, not the base tree."""
    if _is_remote_target(context):
        raise NotImplementedError("worktree.search_text currently requires a local worktree")
    root = _worktree_root(context)
    query = str(arguments.get("query") or "")
    if not query:
        raise ValueError("query is required")
    relative = _worktree_relative(context, arguments.get("path"))
    start = _safe_worktree_path(context, relative)
    if not start.exists():
        raise FileNotFoundError(f"worktree path not found: {relative}")
    limit = max(1, min(int(arguments.get("limit") or 100), 500))
    case_sensitive = bool(arguments.get("case_sensitive"))
    needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    for candidate in _worktree_iter_files(root, start):
        try:
            if candidate.stat().st_size > 2 * 1024 * 1024:
                continue
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            haystack = line if case_sensitive else line.lower()
            if needle in haystack:
                matches.append({
                    "path": candidate.relative_to(root).as_posix(),
                    "line": line_no,
                    "preview": line[:500],
                })
                if len(matches) >= limit:
                    return {
                        "query": query,
                        "matches": matches,
                        "count": len(matches),
                        "truncated": True,
                        **_worktree_result(context),
                    }
    return {
        "query": query,
        "matches": matches,
        "count": len(matches),
        "truncated": False,
        **_worktree_result(context),
    }


async def _worktree_run(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    """Run an argv command inside the worktree.

    This is the agent's shell: tests, linters, builds, ``git diff`` and small
    probes. It never touches the operator's workspace and never grants
    promotion authority; only ``worktree.verify`` is the completion gate.
    """
    if _is_remote_target(context):
        raise NotImplementedError("worktree.run currently requires a local worktree")
    root = _worktree_root(context)
    command = arguments.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("command must be a non-empty string array")
    if len(command) > 64:
        raise ValueError("command exceeds 64 arguments")
    requested = list(command)
    resolved = _local_worktree_command(requested)
    timeout = max(1.0, min(float(arguments.get("timeout_seconds") or 120), 600.0))
    process = await asyncio.create_subprocess_exec(
        *resolved,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_local_worktree_env(),
    )
    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        process.kill()
        stdout, stderr = await process.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    return {
        "command": requested,
        "resolved_command": resolved,
        "returncode": process.returncode,
        "ok": process.returncode == 0 and not timed_out,
        "timed_out": timed_out,
        "stdout": out[-20000:],
        "stderr": err[-12000:],
        **_worktree_result(context),
    }


def register_worktree_tools(registry: AgentToolRegistry) -> AgentToolRegistry:
    # All worktree tools operate exclusively inside an isolated worktree — they
    # never touch the operator's workspace. Autopilot owns these; no per-call
    # approval prompts. The only governance gate is worktree→workspace apply,
    # which requires explicit operator consent (/apply or autopilot apply_on_completion).
    registry.register(ToolSpec(
        tool_id="worktree.bind", version="1", title="Create isolated worktree",
        description="Create and bind an isolated Git worktree to this AgentRun.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","properties":{"objective":{"type":"string"},"risk":{"type":"string"},"provider":{"type":"string"},"base_ref":{"type":"string"},"task_id":{"type":"string"}},"additionalProperties":False},
        timeout_seconds=45, requires_approval=False, idempotent=False, targets=("local","ssh","container"), handler=_worktree_bind,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.write_file", version="1", title="Write isolated file",
        description="Create or replace a UTF-8 file only inside the bound worktree.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","required":["path","content"],"properties":{"path":{"type":"string"},"content":{"type":"string"}},"additionalProperties":False},
        timeout_seconds=10, requires_approval=False, requires_worktree=True, idempotent=False, targets=("local","ssh","container"), handler=_worktree_write_file,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.replace_exact", version="1", title="Replace exact text in worktree",
        description="Perform a bounded exact replacement only inside the bound worktree.", category="worktree",
        risk=ToolRisk.HIGH, effect=ToolEffect.ISOLATED_MUTATION,
        input_schema={"type":"object","required":["path","old_text","new_text"],"properties":{"path":{"type":"string"},"old_text":{"type":"string"},"new_text":{"type":"string"},"expected_occurrences":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=10, requires_approval=False, requires_worktree=True, idempotent=False, targets=("local","ssh","container"), handler=_worktree_replace_exact,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.read_file", version="1", title="Read isolated file",
        description="Read a bounded line range from the bound worktree so the model sees its own edits.", category="inspection",
        risk=ToolRisk.LOW, effect=ToolEffect.READ,
        input_schema={"type":"object","required":["path"],"properties":{"path":{"type":"string"},"start_line":{"type":"integer"},"line_count":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=15, requires_worktree=True, targets=("local",), handler=_worktree_read_file,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.list", version="1", title="List isolated directory",
        description="List one directory inside the bound worktree, skipping generated and VCS trees.", category="inspection",
        risk=ToolRisk.LOW, effect=ToolEffect.READ,
        input_schema={"type":"object","properties":{"path":{"type":"string"},"limit":{"type":"integer"}},"additionalProperties":False},
        timeout_seconds=15, requires_worktree=True, targets=("local",), handler=_worktree_list,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.search_text", version="1", title="Search isolated worktree",
        description="Search file contents inside the bound worktree for a substring.", category="inspection",
        risk=ToolRisk.LOW, effect=ToolEffect.READ,
        input_schema={"type":"object","required":["query"],"properties":{"query":{"type":"string"},"path":{"type":"string"},"limit":{"type":"integer"},"case_sensitive":{"type":"boolean"}},"additionalProperties":False},
        timeout_seconds=25, requires_worktree=True, targets=("local",), handler=_worktree_search_text,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.verify", version="1", title="Run worktree verification",
        description="Run an explicit argv verification command inside the bound worktree without a shell.", category="verification",
        risk=ToolRisk.HIGH, effect=ToolEffect.EXECUTION,
        input_schema={"type":"object","required":["command"],"properties":{"command":{"type":"array","items":{"type":"string"}},"timeout_seconds":{"type":"number"}},"additionalProperties":False},
        timeout_seconds=610, requires_approval=False, requires_worktree=True, idempotent=False, targets=("local","ssh","container"), handler=_worktree_run_verification,
    ))
    registry.register(ToolSpec(
        tool_id="worktree.run", version="1", title="Run isolated command",
        description="Run an argv command (tests, linters, builds, git) inside the bound worktree. Never touches the workspace.", category="execution",
        risk=ToolRisk.HIGH, effect=ToolEffect.EXECUTION,
        input_schema={"type":"object","required":["command"],"properties":{"command":{"type":"array","items":{"type":"string"}},"timeout_seconds":{"type":"number"}},"additionalProperties":False},
        timeout_seconds=610, requires_approval=False, requires_worktree=True, idempotent=False, targets=("local",), handler=_worktree_run,
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
