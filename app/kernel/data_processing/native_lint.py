"""BEAST Quality Cascade native lint execution adapter.

Never installs software, runs shell commands, or treats a missing tool as PASS.
Caller must have authenticated and pinned an authorized trusted workspace.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from app.kernel.data_processing.quality_cascade import CascadeCheck


def run_native_lint(cascade: Any, workspace: Path, language: str, relative_paths: list[str]) -> CascadeCheck:
    """Invoke an actual installed linter through QualityCascade's bounded runner."""
    name = "ruff" if language == "python" else "eslint"
    if not relative_paths:
        return CascadeCheck(name, "failed", "No lint targets selected", {"reason": "no_lint_targets"})
    if language == "python":
        # Prefer the explicitly trusted workspace tool, then the selected
        # Python interpreter's environment. Do not require shell PATH edits.
        # sys.executable is the interpreter executing the Swarm process.
        workspace_tool = workspace / ".venv" / "bin" / "ruff"
        interpreter_tool = Path(sys.executable).parent / "ruff"
        candidates = (workspace_tool, interpreter_tool)
        executable = next(
            (str(candidate) for candidate in candidates
             if candidate.is_file() and candidate.stat().st_mode & 0o111),
            None,
        )
        if executable is None:
            executable = shutil.which("ruff")
        if not executable:
            return CascadeCheck(name, "skipped", "Ruff unavailable; no lint was executed", {"reason": "linter_unavailable", "language": language})
        command = [executable, "check", "--no-cache", "--output-format", "concise", "--", *relative_paths]
    elif language == "javascript":
        # ESLint must come from the trusted workspace, never download through npx.
        local = workspace / "node_modules" / ".bin" / "eslint"
        if not local.is_file() or not local.resolve().is_relative_to(workspace) or not local.stat().st_mode & 0o111:
            return CascadeCheck(name, "skipped", "Workspace ESLint unavailable; no lint was executed", {"reason": "linter_unavailable", "language": language})
        command = [str(local), *relative_paths]
    else:
        return CascadeCheck(name, "failed", "Unsupported lint language", {"reason": "unsupported_language"})
    result = cascade._run_command(command, workspace, 60)
    if result.get("status") == "skipped":
        return CascadeCheck(name, "skipped", result.get("summary", "Linter not executed"), {**result, "language": language, "targets": relative_paths})
    code = result.get("returncode")
    if code is None:
        status = "failed"
    else:
        status = "passed" if code == 0 and result.get("status") == "completed" else "failed"
    return CascadeCheck(name, status, "Native lint passed" if status == "passed" else "Native lint failed", {**result, "language": language, "targets": relative_paths})
