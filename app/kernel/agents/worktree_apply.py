"""Apply a verified isolated worktree diff to the operator workspace.

The agent loop edits a git worktree so a bad model turn can never corrupt the
operator's checkout. Autopilot still has to deliver the finished change, so
this module performs the one write-back step the runtime owns.

Safety boundaries:

* only paths from the verified SourcePlan are considered;
* the operator's file must still match the worktree's base commit, otherwise a
  concurrent human edit wins and the apply is refused;
* symlinks and paths escaping either root are refused;
* writes are atomic and preserve the file mode.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


class ApplyBlocked(RuntimeError):
    """The worktree diff cannot be written back without operator review."""


def _run_git(root: Path, *args: str, timeout: float = 20.0) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ApplyBlocked(detail or f"git {' '.join(args)} failed")
    return result.stdout


def _normalize(relative: str) -> str:
    value = str(relative or "").strip().replace("\\", "/")
    if not value or value.startswith("/"):
        raise ApplyBlocked(f"unsafe apply path: {relative!r}")
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} or part.startswith(".git") for part in parts):
        raise ApplyBlocked(f"unsafe apply path: {relative!r}")
    return PurePosixPath(*parts).as_posix()


def _inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ApplyBlocked(f"path escapes workspace: {relative}") from exc
    return candidate


def _base_bytes(worktree: Path, base_commit: str, relative: str) -> bytes | None:
    ref = f"{base_commit or 'HEAD'}:{relative}"
    result = subprocess.run(
        ["git", "-C", str(worktree), "show", ref],
        capture_output=True,
        timeout=20,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _atomic_write(destination: Path, data: bytes, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.beast-apply-{os.getpid()}")
    try:
        temporary.write_bytes(data)
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_worktree_diff(
    worktree_root: str | Path,
    files: Iterable[str] | None = None,
    *,
    max_chars: int = 60000,
) -> dict[str, Any]:
    """Return a bounded unified diff for the verified worktree changes."""
    worktree = Path(worktree_root).expanduser().resolve()
    if not worktree.is_dir():
        return {"diff": "", "added": 0, "removed": 0, "truncated": False}
    paths: list[str] = []
    for item in files or ():
        try:
            paths.append(_normalize(item))
        except ApplyBlocked:
            continue
    if paths:
        subprocess.run(
            ["git", "-C", str(worktree), "add", "-N", "--", *paths],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
    command = ["git", "-C", str(worktree), "diff", "--no-color", "--no-ext-diff"]
    if paths:
        command.extend(["--", *paths])
    result = subprocess.run(command, capture_output=True, timeout=20)
    if result.returncode != 0:
        return {"diff": "", "added": 0, "removed": 0, "truncated": False}
    patch = result.stdout.decode("utf-8", errors="replace")
    added = removed = 0
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {
        "diff": patch[:max_chars],
        "added": added,
        "removed": removed,
        "truncated": len(patch) > max_chars,
    }


def apply_workspace_files(
    *,
    workspace_root: str | Path,
    worktree_root: str | Path,
    base_commit: str,
    files: Iterable[str],
) -> dict[str, Any]:
    """Copy verified files from the worktree into the operator workspace."""
    workspace = Path(workspace_root).expanduser().resolve()
    worktree = Path(worktree_root).expanduser().resolve()
    if not workspace.is_dir():
        raise ApplyBlocked(f"workspace does not exist: {workspace}")
    if not worktree.is_dir():
        raise ApplyBlocked(f"worktree does not exist: {worktree}")
    if workspace == worktree:
        raise ApplyBlocked("workspace and worktree are the same directory")

    normalized: list[str] = []
    for item in files:
        path = _normalize(item)
        if path not in normalized:
            normalized.append(path)
    if not normalized:
        raise ApplyBlocked("SourcePlan listed no files to apply")

    applied: list[dict[str, Any]] = []
    deleted: list[str] = []
    for relative in normalized:
        source = _inside(worktree, relative)
        destination = _inside(workspace, relative)
        if source.is_symlink() or destination.is_symlink():
            raise ApplyBlocked(f"refusing to apply symlink: {relative}")
        base = _base_bytes(worktree, base_commit, relative)
        current = destination.read_bytes() if destination.is_file() else None
        if base is not None:
            if current != base:
                raise ApplyBlocked(
                    f"{relative} changed in the operator workspace after bind; "
                    "review the worktree diff before applying"
                )
        elif current is not None:
            raise ApplyBlocked(
                f"{relative} already exists in the operator workspace; "
                "refusing to overwrite an unverified file"
            )
        if not source.exists():
            # Worktree deletion: the base equality check above proved the
            # operator has the original content, so removing it is safe.
            destination.unlink()
            deleted.append(relative)
            continue
        if not source.is_file():
            raise ApplyBlocked(f"not a regular file: {relative}")
        data = source.read_bytes()
        mode = stat.S_IMODE(source.stat().st_mode) or 0o644
        _atomic_write(destination, data, mode)
        applied.append({
            "path": relative,
            "bytes": len(data),
            "sha256": __import__("hashlib").sha256(data).hexdigest(),
            "created": base is None,
        })
    return {
        "ok": True,
        "workspace": str(workspace),
        "worktree": str(worktree),
        "applied": applied,
        "deleted": deleted,
    }
