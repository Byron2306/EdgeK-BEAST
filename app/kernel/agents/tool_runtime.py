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


class ToolExecutionFailed(RuntimeError):
    """Tool failure that preserves the structured observation for repair loops."""

    def __init__(self, observation: ToolObservation):
        super().__init__(observation.error or f"tool {observation.tool_id} failed")
        self.observation = observation


_EXCLUDED_DIRS = {".git", ".beast", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".nim": "nim",
    ".nims": "nim",
    ".nimble": "nim",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".sh": "shell",
    ".json": "json",
    ".md": "markdown",
}


def _shell_quote(value: Any) -> str:
    return "'" + str(value if value is not None else "").replace("'", "'\\''") + "'"


def _safe_remote_relative(value: Any) -> str:
    relative = str(value or ".").replace("\\", "/").strip().lstrip("/")
    if relative in {"", "."}:
        return "."
    parts = relative.split("/")
    if any(not part or part == ".." for part in parts):
        raise ValueError("path escapes target workspace root")
    if any("\0" in part for part in parts):
        raise ValueError("path contains unsupported characters")
    return relative


def _target_payload(context: ToolExecutionContext) -> dict[str, Any]:
    payload = context.execution_target_payload if isinstance(context.execution_target_payload, dict) else {}
    nested = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    return {**nested, **payload}


def _remote_target_descriptor(context: ToolExecutionContext) -> dict[str, str]:
    payload = _target_payload(context)
    kind = str(payload.get("kind") or payload.get("target_kind") or context.execution_target or "local").strip().lower()
    if kind == "devcontainer":
        kind = "container"
    if kind == "ssh":
        host = str(payload.get("host") or "").strip()
        base = str(payload.get("remoteRoot") or payload.get("remote_root") or payload.get("path") or "~").strip()
        port = str(payload.get("port") or payload.get("sshPort") or payload.get("ssh_port") or "").strip()
        identity_file = str(payload.get("identityFile") or payload.get("identity_file") or payload.get("keyPath") or "").strip()
        known_hosts = str(payload.get("knownHosts") or payload.get("known_hosts") or payload.get("knownHostsFile") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@._:-]{0,252}", host):
            raise ValueError("SSH execution target requires a safe host")
        if not base or ".." in base.split("/") or not re.fullmatch(r"[~\/@A-Za-z0-9._+\-]+", base):
            raise ValueError("SSH execution target requires a safe workspace path")
        if port and (not port.isdigit() or not 0 < int(port) < 65536):
            raise ValueError("SSH execution target requires a valid port")
        for label, value in {"identity_file": identity_file, "known_hosts": known_hosts}.items():
            if value and (not value.startswith("/") or ".." in value.split("/") or not re.fullmatch(r"[\/A-Za-z0-9._+\-]+", value)):
                raise ValueError(f"SSH execution target requires a safe {label} path")
        descriptor = {"kind": "ssh", "host": host, "base": base}
        if port:
            descriptor["port"] = port
        if identity_file:
            descriptor["identity_file"] = identity_file
        if known_hosts:
            descriptor["known_hosts"] = known_hosts
        return descriptor
    if kind == "container":
        container = str(payload.get("containerId") or payload.get("container_id") or payload.get("id") or payload.get("name") or "").strip()
        base = str(payload.get("workspaceFolder") or payload.get("workspace_folder") or payload.get("path") or "/workspace").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", container):
            raise ValueError("container execution target requires a safe container id")
        if not base or ".." in base.split("/") or not re.fullmatch(r"[~\/@A-Za-z0-9._+\-]+", base):
            raise ValueError("container execution target requires a safe workspace folder")
        return {"kind": "container", "container": container, "base": base}
    return {"kind": "local"}


async def _bounded_process(command: str, args: list[str], *, timeout: float, output_limit: int = 512000) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise TimeoutError(f"target command timed out after {timeout:g}s")
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "stdout": stdout[:output_limit].decode("utf-8", errors="replace"),
        "stderr": stderr[:output_limit].decode("utf-8", errors="replace"),
        "truncated": len(stdout) > output_limit or len(stderr) > output_limit,
    }


async def _run_target_shell(context: ToolExecutionContext, script: str, *, timeout: float = 20.0, output_limit: int = 512000) -> dict[str, Any]:
    descriptor = _remote_target_descriptor(context)
    if descriptor["kind"] == "ssh":
        args = [
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=7",
            "-o", "StrictHostKeyChecking=yes",
        ]
        if descriptor.get("known_hosts"):
            args.extend(["-o", f"UserKnownHostsFile={descriptor['known_hosts']}"])
        if descriptor.get("identity_file"):
            args.extend(["-i", descriptor["identity_file"]])
        if descriptor.get("port"):
            args.extend(["-p", descriptor["port"]])
        args.extend([descriptor["host"], script])
        return await _bounded_process("ssh", args, timeout=timeout, output_limit=output_limit)
    if descriptor["kind"] == "container":
        return await _bounded_process(
            "docker",
            ["exec", "-i", "-w", descriptor["base"], descriptor["container"], "sh", "-lc", script],
            timeout=timeout,
            output_limit=output_limit,
        )
    raise ValueError("remote target shell requested for local execution target")


def _safe_path(root: Path, relative: str) -> Path:
    candidate = (root / str(relative or ".")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes workspace root") from exc
    return candidate


def _language_for(path_value: str) -> str:
    return _LANGUAGE_BY_SUFFIX.get(Path(str(path_value or "")).suffix.lower(), "text")


def _line_for(text: str, index: int) -> int:
    return text[: max(0, index)].count("\n") + 1


def _extract_workspace_symbols(relative: str, language: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = str(text or "")[: 1024 * 1024]
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    def add_symbol(match: re.Match[str], kind: str, group: int = 1) -> None:
        if len(symbols) >= 160:
            return
        symbols.append({
            "name": match.group(group),
            "kind": kind,
            "path": relative,
            "line": _line_for(source, match.start()),
            "detail": match.group(0).strip()[:180],
        })

    def add_import(target: str, kind: str = "import") -> None:
        value = str(target or "").strip().replace("#", "").strip()
        if value and len(imports) < 240:
            imports.append({"path": relative, "target": value[:240], "kind": kind})

    if language in {"javascript", "javascriptreact", "typescript", "typescriptreact"}:
        for pattern, kind in [
            (r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", "function"),
            (r"\b(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b", "class"),
            (r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^=\n]*?\)?\s*=>", "function"),
        ]:
            for match in re.finditer(pattern, source):
                add_symbol(match, kind)
        for match in re.finditer(r"\bimport\b[^'\"]*['\"]([^'\"]+)['\"]", source):
            add_import(match.group(1))
        for match in re.finditer(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", source):
            add_import(match.group(1), "require")
    elif language == "python":
        for pattern, kind in [(r"^\s*class\s+([A-Za-z_]\w*)\b", "class"), (r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", "function")]:
            for match in re.finditer(pattern, source, flags=re.MULTILINE):
                add_symbol(match, kind)
        for match in re.finditer(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\b", source, flags=re.MULTILINE):
            add_import(match.group(1))
        for match in re.finditer(r"^\s*import\s+([A-Za-z0-9_.,\s]+)", source, flags=re.MULTILINE):
            for item in match.group(1).split(","):
                add_import(item)
    elif language == "nim":
        for pattern, kind in [
            (r"^\s*(?:proc|func|method|iterator|template|macro|converter)\s+([A-Za-z_]\w*)\s*(?:\[|\(|\*|=|:)", "function"),
            (r"^\s*type\s+([A-Za-z_]\w*)\s*(?:\*|=)", "type"),
            (r"^\s*(?:let|var|const)\s+([A-Za-z_]\w*)\s*(?:\*|=|:)", "variable"),
        ]:
            for match in re.finditer(pattern, source, flags=re.MULTILINE):
                add_symbol(match, kind)
        for match in re.finditer(r"^\s*(?:import|include)\s+(.+)$", source, flags=re.MULTILINE):
            for item in match.group(1).split(","):
                add_import(item)
        for match in re.finditer(r"^\s*from\s+([A-Za-z0-9_./]+)\s+import\b", source, flags=re.MULTILINE):
            add_import(match.group(1))
    elif language == "go":
        for pattern, kind in [(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\(", "function"), (r"^type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b", "type")]:
            for match in re.finditer(pattern, source, flags=re.MULTILINE):
                add_symbol(match, kind)
    elif language == "rust":
        for pattern, kind in [(r"\b(?:pub\s+)?fn\s+([A-Za-z_]\w*)\s*\(", "function"), (r"\b(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)\b", "type")]:
            for match in re.finditer(pattern, source):
                add_symbol(match, kind)
    return symbols, imports


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
    if str(context.execution_target or "local") != "local":
        descriptor = _remote_target_descriptor(context)
        relative = _safe_remote_relative(arguments.get("path") or ".")
        limit = max(1, min(int(arguments.get("limit") or 200), 1000))
        excluded = " ".join(f"! -name {_shell_quote(name)}" for name in sorted(_EXCLUDED_DIRS))
        script = (
            f"cd {_shell_quote(descriptor['base'])} && "
            f"test -d {_shell_quote(relative)} && "
            f"find {_shell_quote(relative)} -maxdepth 1 -mindepth 1 {excluded} "
            f"-printf '%f\\t%P\\t%y\\t%s\\n' 2>/dev/null | sort | head -n {limit}"
        )
        result = await _run_target_shell(context, script, timeout=20.0, output_limit=512000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or f"remote workspace list failed with exit {result['returncode']}")
        entries = []
        prefix = "" if relative == "." else f"{relative.rstrip('/')}/"
        for line in result["stdout"].splitlines():
            name, rel, kind, size = (line.split("\t") + ["", "", "", ""])[:4]
            if not name:
                continue
            entries.append({
                "name": name,
                "path": f"{prefix}{rel or name}".replace("//", "/"),
                "kind": "directory" if kind == "d" else "file",
                "size": None if kind == "d" else int(size or 0),
            })
        return {
            "path": relative,
            "entries": entries,
            "count": len(entries),
            "target_execution": f"remote_{descriptor['kind']}",
            "execution_target": context.execution_target,
            "execution_target_payload": dict(context.execution_target_payload or {}),
            "remote_root": descriptor["base"],
            "transport": descriptor["kind"],
        }
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
    return {
        "path": target.relative_to(root).as_posix() if target != root else ".",
        "entries": entries,
        "count": len(entries),
        "target_execution": "local_snapshot",
        "execution_target": context.execution_target,
        "execution_target_payload": dict(context.execution_target_payload or {}),
    }


async def _workspace_read_range(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if str(context.execution_target or "local") != "local":
        descriptor = _remote_target_descriptor(context)
        relative = _safe_remote_relative(arguments.get("path") or "")
        start = max(1, int(arguments.get("start_line") or 1))
        count = max(1, min(int(arguments.get("line_count") or 200), 1000))
        end = start + count - 1
        script = (
            f"cd {_shell_quote(descriptor['base'])} && "
            f"test -f {_shell_quote(relative)} && "
            f"printf 'BEAST_META\\n' && wc -l < {_shell_quote(relative)} && "
            f"sha256sum -- {_shell_quote(relative)} | awk '{{print $1}}' && "
            f"printf 'BEAST_CONTENT\\n' && sed -n '{start},{end}p' -- {_shell_quote(relative)}"
        )
        result = await _run_target_shell(context, script, timeout=20.0, output_limit=1024 * 1024)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or f"remote workspace read failed with exit {result['returncode']}")
        lines = result["stdout"].splitlines()
        marker = lines.index("BEAST_META") if "BEAST_META" in lines else -1
        content_marker = lines.index("BEAST_CONTENT") if "BEAST_CONTENT" in lines else -1
        total_lines = int(lines[marker + 1]) if marker >= 0 and len(lines) > marker + 1 and lines[marker + 1].strip().isdigit() else 0
        sha256 = lines[marker + 2].strip() if marker >= 0 and len(lines) > marker + 2 else ""
        content = "\n".join(lines[content_marker + 1 :]) if content_marker >= 0 else ""
        selected_count = len(content.splitlines()) if content else 0
        return {
            "path": relative,
            "start_line": start,
            "end_line": start + selected_count - 1 if selected_count else start,
            "total_lines": total_lines,
            "content": content,
            "sha256": sha256,
            "target_execution": f"remote_{descriptor['kind']}",
            "execution_target": context.execution_target,
            "execution_target_payload": dict(context.execution_target_payload or {}),
            "remote_root": descriptor["base"],
            "transport": descriptor["kind"],
        }
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
        "target_execution": "local_snapshot",
        "execution_target": context.execution_target,
        "execution_target_payload": dict(context.execution_target_payload or {}),
    }


async def _workspace_search_text(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    if str(context.execution_target or "local") != "local":
        descriptor = _remote_target_descriptor(context)
        query = str(arguments.get("query") or "")
        if not query:
            raise ValueError("query is required")
        relative = _safe_remote_relative(arguments.get("path") or ".")
        limit = max(1, min(int(arguments.get("limit") or 100), 500))
        flags = "-RInF" if bool(arguments.get("case_sensitive")) else "-RInFi"
        excludes = " ".join(f"--exclude-dir={_shell_quote(name)}" for name in sorted(_EXCLUDED_DIRS))
        script = (
            f"cd {_shell_quote(descriptor['base'])} && "
            f"grep {flags} --binary-files=without-match {excludes} -- {_shell_quote(query)} {_shell_quote(relative)} 2>/dev/null | head -n {limit}"
        )
        result = await _run_target_shell(context, script, timeout=25.0, output_limit=1024 * 1024)
        if not result["ok"] and result["returncode"] not in {1}:
            raise RuntimeError(result["stderr"] or f"remote workspace search failed with exit {result['returncode']}")
        matches = []
        for line in result["stdout"].splitlines():
            match = re.match(r"^(.*?):([0-9]+):(.*)$", line)
            if not match:
                continue
            matches.append({"path": match.group(1).replace("./", "", 1), "line": int(match.group(2)), "preview": match.group(3)[:500]})
        return {
            "query": query,
            "matches": matches,
            "count": len(matches),
            "truncated": len(matches) >= limit,
            "target_execution": f"remote_{descriptor['kind']}",
            "execution_target": context.execution_target,
            "execution_target_payload": dict(context.execution_target_payload or {}),
            "remote_root": descriptor["base"],
            "transport": descriptor["kind"],
        }
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
                    return {"query": query, "matches": matches, "count": len(matches), "truncated": True, "target_execution": "local_snapshot", "execution_target": context.execution_target, "execution_target_payload": dict(context.execution_target_payload or {})}
    return {"query": query, "matches": matches, "count": len(matches), "truncated": False, "target_execution": "local_snapshot", "execution_target": context.execution_target, "execution_target_payload": dict(context.execution_target_payload or {})}


async def _workspace_index(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    limit = max(1, min(int(arguments.get("limit") or 1200), 5000))
    include_symbols = bool(arguments.get("include_symbols", True))
    if str(context.execution_target or "local") != "local":
        descriptor = _remote_target_descriptor(context)
        remote_python = r'''
import hashlib, json, os, re, sys
from pathlib import Path

root = Path(".").resolve()
limit = int(os.environ.get("BEAST_INDEX_LIMIT", "1200"))
include_symbols = os.environ.get("BEAST_INDEX_SYMBOLS", "1") == "1"
excluded = {".git", ".beast", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
suffixes = {
    ".py": "python", ".js": "javascript", ".jsx": "javascriptreact", ".ts": "typescript", ".tsx": "typescriptreact",
    ".nim": "nim", ".nims": "nim", ".nimble": "nim", ".go": "go", ".rs": "rust", ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp", ".sh": "shell", ".json": "json", ".md": "markdown",
}

def language_for(path):
    return suffixes.get(Path(path).suffix.lower(), "text")

def line_for(text, index):
    return text[:max(0, index)].count("\n") + 1

def add_import(rows, path, target, kind="import"):
    value = str(target or "").strip().replace("#", "").strip()
    if value and len(rows) < 1000:
        rows.append({"path": path, "target": value[:240], "kind": kind})

def extract(path, language, text):
    text = text[:1024 * 1024]
    symbols, imports = [], []
    def add(match, kind, group=1):
        if len(symbols) < 1000:
            symbols.append({"path": path, "name": match.group(group), "kind": kind, "line": line_for(text, match.start()), "detail": match.group(0).strip()[:180]})
    if language in {"javascript", "javascriptreact", "typescript", "typescriptreact"}:
        for pattern, kind in [
            (r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", "function"),
            (r"\b(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b", "class"),
            (r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^=\n]*?\)?\s*=>", "function"),
        ]:
            for match in re.finditer(pattern, text):
                add(match, kind)
        for match in re.finditer(r"\bimport\b[^'\"]*['\"]([^'\"]+)['\"]", text):
            add_import(imports, path, match.group(1))
        for match in re.finditer(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
            add_import(imports, path, match.group(1), "require")
    elif language == "python":
        for pattern, kind in [(r"^\s*class\s+([A-Za-z_]\w*)\b", "class"), (r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", "function")]:
            for match in re.finditer(pattern, text, flags=re.MULTILINE):
                add(match, kind)
        for match in re.finditer(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\b", text, flags=re.MULTILINE):
            add_import(imports, path, match.group(1))
        for match in re.finditer(r"^\s*import\s+([A-Za-z0-9_.,\s]+)", text, flags=re.MULTILINE):
            for item in match.group(1).split(","):
                add_import(imports, path, item)
    elif language == "nim":
        for pattern, kind in [
            (r"^\s*(?:proc|func|method|iterator|template|macro|converter)\s+([A-Za-z_]\w*)\s*(?:\[|\(|\*|=|:)", "function"),
            (r"^\s*type\s+([A-Za-z_]\w*)\s*(?:\*|=)", "type"),
            (r"^\s*(?:let|var|const)\s+([A-Za-z_]\w*)\s*(?:\*|=|:)", "variable"),
        ]:
            for match in re.finditer(pattern, text, flags=re.MULTILINE):
                add(match, kind)
        for match in re.finditer(r"^\s*(?:import|include)\s+(.+)$", text, flags=re.MULTILINE):
            for item in match.group(1).split(","):
                add_import(imports, path, item)
        for match in re.finditer(r"^\s*from\s+([A-Za-z0-9_./]+)\s+import\b", text, flags=re.MULTILINE):
            add_import(imports, path, match.group(1))
    elif language == "go":
        for pattern, kind in [(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\(", "function"), (r"^type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b", "type")]:
            for match in re.finditer(pattern, text, flags=re.MULTILINE):
                add(match, kind)
    elif language == "rust":
        for pattern, kind in [(r"\b(?:pub\s+)?fn\s+([A-Za-z_]\w*)\s*\(", "function"), (r"\b(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)\b", "type")]:
            for match in re.finditer(pattern, text):
                add(match, kind)
    return symbols, imports

files, symbols, imports, tests = [], [], [], []
languages, symbol_kinds = {}, {}
for current, dirs, names in os.walk(root):
    dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".beast-") and not d.startswith(".phase"))
    for name in sorted(names):
        if len(files) >= limit:
            break
        full = Path(current) / name
        try:
            stat = full.stat()
            rel = full.relative_to(root).as_posix()
        except OSError:
            continue
        language = language_for(rel)
        files.append({"path": rel, "language": language, "size": stat.st_size, "mtime_ms": int(stat.st_mtime * 1000)})
        languages[language] = languages.get(language, 0) + 1
        if re.search(r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_|.*_test|.*\.(?:spec|test))\.(?:py|js|jsx|ts|tsx)$", rel, flags=re.I):
            tests.append(rel)
        if include_symbols and language != "text" and stat.st_size <= 1024 * 1024:
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            file_symbols, file_imports = extract(rel, language, text)
            for item in file_symbols:
                symbols.append(item)
                symbol_kinds[item["kind"]] = symbol_kinds.get(item["kind"], 0) + 1
            imports.extend(file_imports)
    if len(files) >= limit:
        break
digest = hashlib.sha256(json.dumps({"files": files, "symbols": symbols[:500], "tests": tests[:200]}, sort_keys=True).encode("utf-8")).hexdigest()
print(json.dumps({
    "beast_object_type": "beast_workspace_index_snapshot",
    "version": "1.0",
    "ok": True,
    "source": "agent_target_deep_index",
    "files": files,
    "symbols": symbols[:1000],
    "imports": imports[:1000],
    "tests": tests[:300],
    "summary": {
        "file_count": len(files),
        "symbol_count": len(symbols),
        "import_count": len(imports),
        "test_file_count": len(tests),
        "languages": languages,
        "symbol_kinds": symbol_kinds,
    },
    "index_digest": "sha256:" + digest,
    "truncated": len(files) >= limit,
}))
'''
        script = (
            f"cd {_shell_quote(descriptor['base'])} && "
            f"BEAST_INDEX_LIMIT={limit} BEAST_INDEX_SYMBOLS={'1' if include_symbols else '0'} "
            f"python3 -c {_shell_quote(remote_python)}"
        )
        result = await _run_target_shell(context, script, timeout=30.0, output_limit=768000)
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or f"remote workspace index failed with exit {result['returncode']}")
        try:
            payload = json.loads(result["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError("remote workspace index returned malformed JSON") from exc
        payload.update({
            "target_execution": f"remote_{descriptor['kind']}",
            "execution_target": context.execution_target,
            "execution_target_payload": dict(context.execution_target_payload or {}),
            "remote_root": descriptor["base"],
            "transport": descriptor["kind"],
        })
        return payload

    root = Path(context.workspace_root).resolve()
    files: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    languages: dict[str, int] = {}
    symbol_kinds: dict[str, int] = {}
    for candidate in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if len(files) >= limit:
            break
        if not candidate.is_file():
            continue
        relative_parts = candidate.relative_to(root).parts
        if any(part in _EXCLUDED_DIRS or part.startswith(".beast-") or part.startswith(".phase1") for part in relative_parts):
            continue
        relative = candidate.relative_to(root).as_posix()
        try:
            stat = candidate.stat()
        except OSError:
            continue
        language = _language_for(relative)
        files.append({"path": relative, "language": language, "size": stat.st_size, "mtime_ms": int(stat.st_mtime * 1000)})
        languages[language] = languages.get(language, 0) + 1
        if not include_symbols or language == "text" or stat.st_size > 1024 * 1024:
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        file_symbols, file_imports = _extract_workspace_symbols(relative, language, text)
        for item in file_symbols:
            symbols.append(item)
            symbol_kinds[item["kind"]] = symbol_kinds.get(item["kind"], 0) + 1
        imports.extend(file_imports)
    tests = [item["path"] for item in files if re.search(r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_|.*_test|.*\.(?:spec|test))\.(?:py|js|jsx|ts|tsx)$", item["path"], flags=re.IGNORECASE)]
    digest = hashlib.sha256(json.dumps({"files": files, "symbols": symbols[:500], "tests": tests[:200]}, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "beast_object_type": "beast_workspace_index_snapshot",
        "version": "1.0",
        "ok": True,
        "source": "agent_local_index",
        "files": files[:limit],
        "symbols": symbols[:1000],
        "imports": imports[:1000],
        "tests": tests[:300],
        "summary": {
            "file_count": len(files),
            "symbol_count": len(symbols),
            "import_count": len(imports),
            "test_file_count": len(tests),
            "languages": languages,
            "symbol_kinds": symbol_kinds,
        },
        "index_digest": f"sha256:{digest}",
        "truncated": len(files) >= limit,
        "target_execution": "local_snapshot",
        "execution_target": context.execution_target,
        "execution_target_payload": dict(context.execution_target_payload or {}),
    }


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
        tool_id="workspace.index",
        version="1",
        title="Index workspace",
        description="Build a bounded file/language/import/symbol/test snapshot before planning edits.",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}, "include_symbols": {"type": "boolean"}}, "additionalProperties": False},
        timeout_seconds=30,
        max_output_bytes=262144,
        targets=("local", "ssh", "container"),
        handler=_workspace_index,
    ))
    registry.register(ToolSpec(
        tool_id="workspace.list",
        version="1",
        title="List workspace path",
        description="List bounded entries beneath the workspace root.",
        category="workspace",
        risk=ToolRisk.LOW,
        effect=ToolEffect.READ,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False},
        targets=("local", "ssh", "container"),
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
        targets=("local", "ssh", "container"),
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
        targets=("local", "ssh", "container"),
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
    from app.kernel.agents.worktree_tools import register_worktree_tools
    register_worktree_tools(registry)
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
        target_payload = request.execution_target_payload if isinstance(request.execution_target_payload, dict) else {}
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
            execution_target_payload=target_payload,
            worktree_root=worktree_root,
            approval_id=request.approval_id,
            engine=self.engine,
        )
        started = time.time()
        self.engine.emit(run_id, "agent.tool.started", {
            "tool_id": spec.tool_id,
            "tool_version": spec.version,
            "arguments": arguments,
            "risk": spec.risk.value,
            "effect": spec.effect.value,
            "execution_target": target,
            "execution_target_payload": target_payload,
        })
        status = "completed"
        result: dict[str, Any] = {}
        error = ""
        truncated = False
        try:
            assert spec.handler is not None
            raw = await asyncio.wait_for(spec.handler(arguments, context), timeout=max(0.1, spec.timeout_seconds))
            result, truncated = _bounded_text(raw if isinstance(raw, dict) else {"value": raw}, spec.max_output_bytes)
            if isinstance(raw, dict) and raw.get("ok") is False:
                status = "failed"
                error = str(raw.get("error") or raw.get("message") or f"tool {spec.tool_id} reported failure")
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
        self.engine.merge_checkpoint(run_id, {
            "last_observation_id": observation.observation_id,
            "last_tool_id": observation.tool_id,
            "last_tool_status": observation.status,
            "last_tool_evidence_digest": observation.evidence_digest,
        })
        if status != "completed":
            raise ToolExecutionFailed(observation)
        return observation
