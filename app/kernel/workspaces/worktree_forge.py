"""Git worktree isolation for BEAST missions."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_slug(value: str, fallback: str = "mission") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return (slug or fallback)[:72]


def _now() -> float:
    return time.time()


@dataclass
class WorktreeCommandResult:
    ok: bool
    args: List[str]
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "args": list(self.args),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }


class WorktreeForge:
    """Create and track isolated git worktrees for risky BEAST missions."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "worktrees"
        self.registry_path = self.store_dir / "tasks.json"

    def list(self) -> Dict[str, Any]:
        registry = self._load()
        return {
            "beast_object_type": "beast_worktree_registry",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "count": len(registry.get("tasks") or []),
            "tasks": registry.get("tasks") or [],
        }

    def create(
        self,
        *,
        objective: str,
        risk: str = "medium",
        provider: str = "",
        mode: str = "implementer",
        base_ref: str = "HEAD",
        task_id: str = "",
    ) -> Dict[str, Any]:
        task_id = _safe_slug(task_id or objective or "mission")
        unique = hashlib.sha1(f"{task_id}:{_now()}".encode("utf-8")).hexdigest()[:8]
        task_id = f"{task_id}-{unique}"
        branch = f"beast/{task_id}"
        worktree_path = (self.store_dir / task_id).resolve()
        base_commit = self._git(["rev-parse", base_ref], cwd=self.workspace_root)
        record = {
            "beast_object_type": "beast_worktree_task",
            "version": "1.0",
            "task_id": task_id,
            "objective": objective,
            "risk": risk,
            "provider": provider,
            "active_mode": mode,
            "branch": branch,
            "base_ref": base_ref,
            "base_commit": base_commit.stdout if base_commit.ok else "",
            "workspace_root": str(self.workspace_root),
            "worktree_path": str(worktree_path),
            "status": "creating",
            "created_at": _now(),
            "updated_at": _now(),
            "evidence": [],
        }
        repo = self._git(["rev-parse", "--show-toplevel"], cwd=self.workspace_root)
        if not repo.ok:
            record.update({"status": "failed", "error": "workspace is not a git repository", "git": repo.to_dict()})
            record["receipt"] = self._receipt("create", record, False)
            self._upsert(record)
            self._register_receipt(record["receipt"])
            return {"ok": False, "task": record}
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        added = self._git(["worktree", "add", "-b", branch, str(worktree_path), base_ref], cwd=self.workspace_root, timeout=30.0)
        record["git"] = added.to_dict()
        if added.ok:
            record["status"] = "active"
            record["receipt"] = self._receipt("create", record, True)
        else:
            record["status"] = "failed"
            record["error"] = added.stderr or added.stdout or "git worktree add failed"
            record["receipt"] = self._receipt("create", record, False)
        record["updated_at"] = _now()
        self._upsert(record)
        self._register_receipt(record.get("receipt") if isinstance(record.get("receipt"), dict) else {})
        return {"ok": bool(added.ok), "task": record}

    def status(self, task_id: str) -> Dict[str, Any]:
        record = self._find(task_id)
        if not record:
            return {"ok": False, "error": f"unknown worktree task: {task_id}"}
        path = Path(str(record.get("worktree_path") or ""))
        git_status = self._git(["status", "--short"], cwd=path) if path.exists() else WorktreeCommandResult(False, [], stderr="worktree path missing", returncode=1)
        dirty_files = [line[3:] for line in git_status.stdout.splitlines() if len(line) >= 4]
        out = dict(record)
        out.update({
            "ok": git_status.ok,
            "dirty_count": len(dirty_files),
            "dirty_files": dirty_files[:100],
            "exists": path.exists(),
            "git_status": git_status.to_dict(),
            "updated_at": _now(),
        })
        return out

    def diff(self, task_id: str, max_chars: int = 40000) -> Dict[str, Any]:
        record = self._find(task_id)
        if not record:
            return {"ok": False, "error": f"unknown worktree task: {task_id}"}
        path = Path(str(record.get("worktree_path") or ""))
        result = self._git(["diff", "--stat"], cwd=path) if path.exists() else WorktreeCommandResult(False, [], stderr="worktree path missing", returncode=1)
        patch = self._git(["diff"], cwd=path) if path.exists() else result
        return {
            "ok": result.ok and patch.ok,
            "task_id": task_id,
            "branch": record.get("branch"),
            "stat": result.stdout,
            "diff": patch.stdout[:max_chars],
            "truncated": len(patch.stdout) > max_chars,
            "commands": [result.to_dict(), patch.to_dict()],
        }

    def sourceplan_draft_from_diff(self, task_id: str, max_chars: int = 60000) -> Dict[str, Any]:
        """Create an advisory SourcePlan draft from the worktree branch diff.

        This is deliberately not an apply operation. It gives IDE operators a
        governed promotion handoff that can be reviewed, translated into
        explicit operations, verified, and closed with evidence.
        """
        record = self._find(task_id)
        if not record:
            return {"ok": False, "error": f"unknown worktree task: {task_id}"}
        path = Path(str(record.get("worktree_path") or ""))
        if not path.exists():
            return {"ok": False, "error": "worktree path missing"}
        base_ref = str(record.get("base_commit") or record.get("base_ref") or "HEAD")
        branch = str(record.get("branch") or "")
        diff_range = f"{base_ref}...HEAD"
        stat = self._git(["diff", "--stat", diff_range], cwd=path)
        patch = self._git(["diff", diff_range], cwd=path)
        if not patch.stdout:
            stat = self._git(["diff", "--stat"], cwd=path)
            patch = self._git(["diff"], cwd=path)
            diff_range = "worktree"
        changed = self._git(["diff", "--name-only", diff_range], cwd=path) if diff_range != "worktree" else self._git(["diff", "--name-only"], cwd=path)
        files = [line.strip() for line in changed.stdout.splitlines() if line.strip()]
        operations, translation_notes = self._sourceplan_operations_for_files(path, base_ref, files)
        needs_translation = bool(translation_notes) or not operations
        plan_id = f"worktree-promotion-{task_id}"
        plan = {
            "beast_object_type": "sourceplan",
            "kind": "beast_source_patch_plan",
            "version": "1.0",
            "plan_id": plan_id,
            "objective": f"Promote verified worktree mission: {record.get('objective') or task_id}",
            "status": "draft",
            "source": "worktree_native_mission",
            "worktree_task_id": task_id,
            "worktree_path": str(path),
            "branch": branch,
            "base_ref": base_ref,
            "base_label": str(record.get("base_ref") or ""),
            "diff_range": diff_range,
            "files": files,
            "selected_files": files,
            "diff_stat": stat.stdout,
            "worktree_diff": patch.stdout[:max_chars],
            "diff_truncated": len(patch.stdout) > max_chars,
            "operations": operations,
            "selected_operations": [op["op_id"] for op in operations if op.get("selected", True)],
            "requires_operator_translation": needs_translation,
            "translation_notes": translation_notes,
            "governance_note": "Worktree promotion remains governed: preview, approve, verify, rollback, and evidence closure are required before any write.",
        }
        receipt = self._receipt("sourceplan_draft", record, True)
        receipt["plan_id"] = plan_id
        receipt["diff_range"] = diff_range
        record = dict(record)
        record["last_sourceplan_draft"] = receipt
        record["updated_at"] = _now()
        record.setdefault("evidence", []).append(receipt)
        self._upsert(record)
        self._register_receipt(receipt)
        return {"ok": True, "plan": plan, "receipt": receipt, "task": record}

    def _sourceplan_operations_for_files(self, cwd: Path, base_ref: str, files: List[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        operations: List[Dict[str, Any]] = []
        notes: List[Dict[str, Any]] = []
        for rel in files[:50]:
            if not rel or rel.startswith(".git/"):
                continue
            old = self._git(["show", f"{base_ref}:{rel}"], cwd=cwd, timeout=10.0)
            new = self._git(["show", f"HEAD:{rel}"], cwd=cwd, timeout=10.0)
            op_id = f"worktree_{len(operations) + 1:03d}"
            if old.ok and new.ok and old.stdout != new.stdout:
                if len(old.stdout) > 50000 or len(new.stdout) > 50000:
                    notes.append({"path": rel, "reason": "file too large for exact SourcePlan operation"})
                    continue
                operations.append({
                    "op_id": op_id,
                    "op": "replace_exact",
                    "path": rel,
                    "old_text": old.stdout + ("\n" if old.stdout and not old.stdout.endswith("\n") else ""),
                    "new_text": new.stdout + ("\n" if new.stdout and not new.stdout.endswith("\n") else ""),
                    "description": f"Promote worktree change for {rel}",
                    "source_edit": True,
                    "selected": True,
                    "worktree_promoted": True,
                })
            elif not old.ok and new.ok:
                if len(new.stdout) > 50000:
                    notes.append({"path": rel, "reason": "new file too large for SourcePlan operation"})
                    continue
                operations.append({
                    "op_id": op_id,
                    "op": "create_or_replace",
                    "path": rel,
                    "content": new.stdout + ("\n" if new.stdout and not new.stdout.endswith("\n") else ""),
                    "description": f"Promote new worktree file {rel}",
                    "source_edit": True,
                    "selected": True,
                    "worktree_promoted": True,
                })
            elif old.ok and not new.ok:
                notes.append({"path": rel, "reason": "deleted files require operator translation"})
            else:
                notes.append({"path": rel, "reason": "unable to resolve file content for SourcePlan operation"})
        if len(files) > 50:
            notes.append({"path": "*", "reason": f"{len(files) - 50} additional files require operator translation"})
        return operations, notes

    def test(self, task_id: str, command: Optional[List[str]] = None, timeout: float = 120.0) -> Dict[str, Any]:
        record = self._find(task_id)
        if not record:
            return {"ok": False, "error": f"unknown worktree task: {task_id}"}
        path = Path(str(record.get("worktree_path") or ""))
        if not path.exists():
            return {"ok": False, "error": "worktree path missing"}
        args = list(command or [sys.executable, "-m", "pytest", "-q"])
        started = _now()
        try:
            process = subprocess.run(
                args,
                cwd=str(path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            command_result = WorktreeCommandResult(process.returncode == 0, args, process.stdout[-4000:], process.stderr[-4000:], process.returncode)
        except Exception as exc:
            command_result = WorktreeCommandResult(False, args, stderr=str(exc), returncode=1)
        record = dict(record)
        record["last_test"] = {
            "beast_object_type": "beast_worktree_test_receipt",
            "version": "1.0",
            "task_id": task_id,
            "ok": command_result.ok,
            "command": args,
            "latency_ms": round((_now() - started) * 1000, 3),
            "result": command_result.to_dict(),
            "timestamp": _now(),
        }
        record["updated_at"] = _now()
        record.setdefault("evidence", []).append(record["last_test"])
        self._upsert(record)
        self._register_receipt(record["last_test"])
        return {"ok": command_result.ok, "task_id": task_id, "receipt": record["last_test"]}

    def promote(self, task_id: str, *, approved: bool = False, require_tests: bool = True) -> Dict[str, Any]:
        record = self._find(task_id)
        if not record:
            return {"ok": False, "error": f"unknown worktree task: {task_id}"}
        path = Path(str(record.get("worktree_path") or ""))
        if not approved:
            return {"ok": False, "decision": "blocked", "reason": "promotion requires explicit approval", "task": record}
        if require_tests and not bool((record.get("last_test") or {}).get("ok")):
            return {"ok": False, "decision": "blocked", "reason": "promotion requires passing worktree tests", "task": record}
        status = self.status(task_id)
        if int(status.get("dirty_count") or 0) > 0:
            return {"ok": False, "decision": "blocked", "reason": "worktree has uncommitted changes; commit inside worktree before promotion", "status": status}
        target_branch = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.workspace_root)
        branch = str(record.get("branch") or "")
        merge = self._git(["merge", "--ff-only", branch], cwd=self.workspace_root, timeout=30.0)
        record = dict(record)
        record["last_promotion"] = {
            "beast_object_type": "beast_worktree_promotion_receipt",
            "version": "1.0",
            "task_id": task_id,
            "ok": merge.ok,
            "approved": True,
            "target_branch": target_branch.stdout,
            "source_branch": branch,
            "git": merge.to_dict(),
            "timestamp": _now(),
        }
        record["status"] = "promoted" if merge.ok else "promotion_failed"
        record["updated_at"] = _now()
        record.setdefault("evidence", []).append(record["last_promotion"])
        self._upsert(record)
        self._register_receipt(record["last_promotion"])
        return {"ok": merge.ok, "task": record, "receipt": record["last_promotion"]}

    def archive(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        record = self._find(task_id)
        if not record:
            return {"ok": False, "error": f"unknown worktree task: {task_id}"}
        record = dict(record)
        record["status"] = "archived"
        record["archive_reason"] = reason
        record["archived_at"] = _now()
        record["updated_at"] = _now()
        record["receipt"] = self._receipt("archive", record, True)
        self._upsert(record)
        self._register_receipt(record["receipt"])
        return {"ok": True, "task": record}

    def _git(self, args: List[str], *, cwd: Path, timeout: float = 6.0) -> WorktreeCommandResult:
        command = ["git", *args]
        try:
            process = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return WorktreeCommandResult(process.returncode == 0, command, process.stdout.strip(), process.stderr.strip(), process.returncode)
        except Exception as exc:
            return WorktreeCommandResult(False, command, stderr=str(exc), returncode=1)

    def _load(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
        return {"beast_object_type": "beast_worktree_registry", "version": "1.0", "tasks": tasks}

    def _save(self, payload: Dict[str, Any]) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.registry_path)

    def _upsert(self, record: Dict[str, Any]) -> None:
        registry = self._load()
        tasks = [task for task in registry.get("tasks", []) if task.get("task_id") != record.get("task_id")]
        tasks.append(record)
        tasks.sort(key=lambda item: float(item.get("updated_at") or 0), reverse=True)
        registry["tasks"] = tasks
        self._save(registry)

    def _find(self, task_id: str) -> Optional[Dict[str, Any]]:
        for task in self._load().get("tasks", []):
            if str(task.get("task_id") or "") == str(task_id or ""):
                return task
        return None

    def _receipt(self, action: str, record: Dict[str, Any], ok: bool) -> Dict[str, Any]:
        return {
            "beast_object_type": "beast_worktree_forge_receipt",
            "version": "1.0",
            "action": action,
            "ok": bool(ok),
            "task_id": record.get("task_id"),
            "branch": record.get("branch"),
            "worktree_path": record.get("worktree_path"),
            "timestamp": _now(),
        }

    def _register_receipt(self, receipt: Dict[str, Any]) -> None:
        if not receipt:
            return
        try:
            from app.kernel.evidence.evidence_bus import EvidenceBus

            EvidenceBus(self.workspace_root).register_worktree_receipt(receipt, registry_path=self.registry_path)
        except Exception:
            pass
