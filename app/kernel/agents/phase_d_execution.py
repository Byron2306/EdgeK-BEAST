"""Phase D isolated execution, verification, and critique contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, Iterable, Optional


class GovernedForgeExecutor:
    """Authorize one compiled Action IR operation inside one worktree."""

    ALLOWED_ACTIONS = {"replace_anchor", "replace_exact", "write_file", "run_verifier"}

    def __init__(self, mutation_runner: Optional[Callable[..., Dict[str, Any]]] = None) -> None:
        self.mutation_runner = mutation_runner

    def execute(
        self,
        action_ir: Dict[str, Any],
        *,
        approval_id: str,
        worktree_task_id: str,
        worktree_root: str,
        approved: bool = False,
    ) -> Dict[str, Any]:
        if not approved or not approval_id:
            return self._blocked("explicit approval is required")
        if not worktree_task_id or not worktree_root:
            return self._blocked("isolated worktree binding is required")
        actions = action_ir.get("actions") if isinstance(action_ir.get("actions"), list) else []
        if len(actions) != 1:
            return self._blocked("exactly one Action IR operation is required")
        action = actions[0] if isinstance(actions[0], dict) else {}
        action_type = str(action.get("type") or action.get("op") or "")
        if action_type not in self.ALLOWED_ACTIONS:
            return self._blocked(f"action type is not allowed: {action_type or 'missing'}")
        target = action.get("target") if isinstance(action.get("target"), dict) else {}
        path = str(target.get("path") or "")
        if not path or path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/"):
            return self._blocked("Action IR target must be one safe relative path")
        if "<RESIDUAL>" in str(action.get("new") or ""):
            return self._blocked("residual fields must be solved before Forge execution")
        authority = {
            "approval_id": approval_id,
            "worktree_task_id": worktree_task_id,
            "worktree_root": worktree_root,
            "path": path,
            "action_type": action_type,
            "one_use": True,
        }
        if self.mutation_runner is None:
            return self._blocked("no governed worktree mutation runner is bound")
        result = self.mutation_runner(action_ir, authority)
        return {
            "status": "succeeded",
            "mutation_applied": True,
            "authority": authority,
            "result": result,
            "receipt_digest": self._digest({"action_ir": action_ir, "authority": authority, "result": result}),
        }

    @staticmethod
    def _blocked(reason: str) -> Dict[str, Any]:
        return {"status": "blocked", "mutation_applied": False, "reason": reason}

    @staticmethod
    def _digest(value: Any) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class PhaseDVerifier:
    """Require a fresh passing verification result for the latest mutation."""

    def verify(self, checks: Iterable[Dict[str, Any]], *, mutation_epoch: int, verified_epoch: Optional[int] = None) -> Dict[str, Any]:
        rows = [dict(item) for item in checks if isinstance(item, dict)]
        failed = [item for item in rows if item.get("passed") is False or item.get("ok") is False or item.get("status") == "failed"]
        fresh = verified_epoch is None or int(verified_epoch) == int(mutation_epoch)
        passed = bool(rows) and not failed and fresh
        return {
            "status": "passed" if passed else "failed",
            "passed": passed,
            "fresh": fresh,
            "mutation_epoch": int(mutation_epoch),
            "verified_epoch": verified_epoch,
            "checks": rows,
            "failure_count": len(failed),
            "reason": "fresh checks passed" if passed else ("verification receipt is stale" if not fresh else "one or more checks failed"),
        }


class PhaseDCritic:
    """Check scope, provenance, and risk after isolated execution."""

    def review(self, execution: Dict[str, Any], verification: Dict[str, Any], *, allowed_paths: Iterable[str]) -> Dict[str, Any]:
        authority = execution.get("authority") if isinstance(execution.get("authority"), dict) else {}
        path = str(authority.get("path") or "")
        allowed = {str(item) for item in allowed_paths}
        findings = []
        if execution.get("mutation_applied") and path not in allowed:
            findings.append("changed path is outside the approved scope")
        if execution.get("mutation_applied") and not authority.get("approval_id"):
            findings.append("mutation has no approval provenance")
        if verification.get("status") != "passed":
            findings.append("fresh verification did not pass")
        return {
            "status": "passed" if not findings else "blocked",
            "passed": not findings,
            "findings": findings,
            "blast_radius": {"paths_changed": [path] if execution.get("mutation_applied") else [], "outside_scope": path not in allowed if path else False},
            "read_only": True,
        }
