"""Read-only worktree changes and diff console for Phase 5.9."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console.event_projection import DurableConsoleEventProjection

VERSION = "5.9"
OBJECT_TYPE = "beast_worktree_changes_diff_console"
CHANGE_TYPES = {"ADDED", "MODIFIED", "DELETED", "RENAMED", "COPIED", "UNTRACKED", "CONFLICTED"}
DEFAULT_PROHIBITED = (".git/", ".beast/approvals/", ".beast/operations_console/", ".env", ".ssh/", "secrets/")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


class WorktreeChangesDiffConsole:
    """Projects exact git changes, traceability, and SourcePlan readiness without promotion authority."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.runs = AgentRunStore(self.workspace_root)
        self.events = DurableConsoleEventProjection(self.workspace_root)

    def build(self, run_id: str, *, path: str = "", query: str = "", change_type: str = "", max_diff_chars: int = 120000) -> dict[str, Any]:
        run = self.runs.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        wanted = change_type.strip().upper()
        if wanted and wanted not in CHANGE_TYPES:
            raise ValueError(f"unsupported change type: {wanted}")
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        worktree = checkpoint.get("worktree") if isinstance(checkpoint.get("worktree"), dict) else {}
        worktree_path = Path(path or worktree.get("path") or worktree.get("worktree_path") or self.workspace_root).expanduser().resolve()
        if not worktree_path.exists():
            raise FileNotFoundError(f"worktree path does not exist: {worktree_path}")
        if not self._git(worktree_path, "rev-parse", "--is-inside-work-tree")[0]:
            raise ValueError(f"not a git worktree: {worktree_path}")

        status_text = self._git(worktree_path, "status", "--porcelain=v1", "--untracked-files=all")[1]
        files = self._parse_status(status_text)
        origins = self._origin_map(run_id)
        prohibited = tuple(checkpoint.get("prohibited_paths") or DEFAULT_PROHIBITED)
        needle = query.strip().lower()
        visible: list[dict[str, Any]] = []
        for item in files:
            item["originating_steps"] = origins.get(item["path"], [])
            item["prohibited"] = self._is_prohibited(item["path"], prohibited)
            item["diff"] = self._file_diff(worktree_path, item["path"], item["change_type"], max_diff_chars)
            item["diff_digest"] = _digest(item["diff"])
            item["reviewable"] = not item["prohibited"]
            if wanted and item["change_type"] != wanted:
                continue
            if needle and needle not in json.dumps(item, sort_keys=True, default=str).lower():
                continue
            visible.append(item)

        base_commit = str(worktree.get("base_commit") or checkpoint.get("base_commit") or "")
        primary_head = self._git(self.workspace_root, "rev-parse", "HEAD")[1].strip()
        worktree_head = self._git(worktree_path, "rev-parse", "HEAD")[1].strip()
        stale_base = bool(base_commit and primary_head and base_commit != primary_head)
        sourceplan = checkpoint.get("sourceplan") if isinstance(checkpoint.get("sourceplan"), dict) else {}
        prohibited_findings = [item["path"] for item in files if item["prohibited"]]
        diff_stat = self._git(worktree_path, "diff", "--stat", "HEAD")[1]
        result = {
            "version": VERSION,
            "beast_object_type": OBJECT_TYPE,
            "run_id": run_id,
            "run_state": str(run.get("state") or "unknown").lower(),
            "worktree": {
                "path": str(worktree_path), "branch": self._git(worktree_path, "branch", "--show-current")[1].strip(),
                "base_commit": base_commit, "primary_head": primary_head, "worktree_head": worktree_head,
                "dirty": bool(files), "stale_base": stale_base,
            },
            "summary": {
                "total_changed_files": len(files), "visible_changed_files": len(visible),
                "added": sum(1 for x in files if x["change_type"] in {"ADDED", "UNTRACKED"}),
                "modified": sum(1 for x in files if x["change_type"] == "MODIFIED"),
                "deleted": sum(1 for x in files if x["change_type"] == "DELETED"),
                "renamed": sum(1 for x in files if x["change_type"] == "RENAMED"),
                "prohibited_findings": len(prohibited_findings),
            },
            "filters": {"change_type": wanted, "query": query},
            "diff_stat": diff_stat,
            "files": visible,
            "prohibited_paths": prohibited_findings,
            "sourceplan": {
                "status": str(sourceplan.get("status") or ("not_created" if files else "not_required")),
                "sourceplan_id": str(sourceplan.get("sourceplan_id") or sourceplan.get("plan_id") or ""),
                "digest": str(sourceplan.get("digest") or sourceplan.get("sourceplan_digest") or ""),
                "promotion_ready": bool(sourceplan.get("promotion_ready")) and not stale_base and not prohibited_findings,
                "promotion_authorized": False,
                "blocked_reasons": (["base_changed"] if stale_base else []) + (["prohibited_paths"] if prohibited_findings else []),
            },
            "warnings": (["SourcePlan base is stale because the primary workspace HEAD changed."] if stale_base else []) + (["One or more changed paths are prohibited by policy."] if prohibited_findings else []),
            "authority": "worktree_diff_console_read_only",
            "grants_execution_authority": False,
            "grants_workspace_mutation": False,
            "grants_promotion_authority": False,
        }
        result["console_digest"] = _digest(result)
        return result

    def verify(self, console: dict[str, Any]) -> bool:
        if console.get("beast_object_type") != OBJECT_TYPE:
            return False
        claimed = str(console.get("console_digest") or "")
        semantic = dict(console); semantic.pop("console_digest", None)
        return claimed == _digest(semantic)

    def _origin_map(self, run_id: str) -> dict[str, list[dict[str, str]]]:
        page = self.events.page(run_id, limit=500, view="expanded")
        result: dict[str, list[dict[str, str]]] = {}
        for event in page.get("events", []):
            detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
            paths = detail.get("affected_files") or detail.get("changed_files") or []
            if isinstance(paths, str): paths = [paths]
            for path in paths:
                result.setdefault(str(path), []).append({
                    "step_id": str(event.get("step_id") or detail.get("step_id") or ""),
                    "tool_id": str(detail.get("tool_id") or ""),
                    "event_id": str(event.get("projection_event_id") or ""),
                    "evidence_digest": str(event.get("evidence_digest") or ""),
                })
        return result

    @staticmethod
    def _parse_status(text: str) -> list[dict[str, Any]]:
        out = []
        for line in text.splitlines():
            if len(line) < 3: continue
            code, raw = line[:2], line[3:]
            old_path = ""
            path = raw
            if " -> " in raw:
                old_path, path = raw.split(" -> ", 1)
            if code == "??": kind = "UNTRACKED"
            elif "U" in code: kind = "CONFLICTED"
            elif "R" in code: kind = "RENAMED"
            elif "C" in code: kind = "COPIED"
            elif "D" in code: kind = "DELETED"
            elif "A" in code: kind = "ADDED"
            else: kind = "MODIFIED"
            normalized = path.replace("\\", "/").lstrip("/")
            if normalized == ".beast" or normalized.startswith(".beast/"):
                continue
            out.append({"path": path, "old_path": old_path, "change_type": kind, "index_status": code[0], "worktree_status": code[1]})
        return out

    def _file_diff(self, root: Path, path: str, kind: str, max_chars: int) -> dict[str, Any]:
        if kind == "UNTRACKED":
            target = root / path
            content = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
            patch = "\n".join([f"diff --git a/{path} b/{path}", "new file mode 100644", "--- /dev/null", f"+++ b/{path}"] + [f"+{line}" for line in content.splitlines()])
        else:
            patch = self._git(root, "diff", "--no-ext-diff", "--", path)[1]
            if not patch:
                patch = self._git(root, "diff", "--cached", "--no-ext-diff", "--", path)[1]
        return {"patch": patch[:max_chars], "truncated": len(patch) > max_chars, "character_count": len(patch)}

    @staticmethod
    def _is_prohibited(path: str, patterns: tuple[str, ...]) -> bool:
        normalized = path.replace("\\", "/").lstrip("/")
        return any(normalized == p.rstrip("/") or normalized.startswith(p) for p in patterns)

    @staticmethod
    def _git(root: Path, *args: str) -> tuple[bool, str, str]:
        completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        return completed.returncode == 0, completed.stdout, completed.stderr
