"""Phase 5.4 durable objective, success-criteria, and plan workspace."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import TERMINAL_STATES, normalize_state
from app.kernel.approvals.digests import canonicalize, semantic_payload, sha256_digest, verify_digest

VERSION = "5.4"
WORKSPACE_TYPE = "beast_objective_plan_workspace"
REVISION_TYPE = "beast_objective_plan_revision"


def _criteria(values: Sequence[Any] | None) -> list[str]:
    result = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _steps(values: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(values or [], start=1):
        item = dict(raw)
        step_id = str(item.get("step_id") or f"step-{index}").strip()
        if not step_id or step_id in seen:
            raise ValueError("plan step IDs must be unique and non-empty")
        title = str(item.get("title") or item.get("objective") or "").strip()
        if not title:
            raise ValueError(f"plan step {step_id} requires a title")
        status = str(item.get("status") or "pending").strip().lower()
        if status not in {"pending", "active", "completed", "blocked", "skipped"}:
            raise ValueError(f"unsupported plan step status: {status}")
        result.append({
            "step_id": step_id,
            "title": title,
            "status": status,
            "success_criteria": _criteria(item.get("success_criteria")),
            "blocked_reason": str(item.get("blocked_reason") or ""),
            "telemetry": dict(item.get("telemetry")) if isinstance(item.get("telemetry"), Mapping) else {},
        })
        seen.add(step_id)
    return result


class ObjectivePlanWorkspace:
    """Durable, versioned mission intent without executable authority."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.engine = AgentRunEngine(self.workspace_root)
        self.db_path = self.workspace_root / ".beast" / "operations_console" / "objective_plan.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS objective_plan_revisions(
              revision_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, version INTEGER NOT NULL,
              objective TEXT NOT NULL, success_criteria_json TEXT NOT NULL, plan_json TEXT NOT NULL,
              active_step_id TEXT NOT NULL, operator_id TEXT NOT NULL, reason TEXT NOT NULL,
              expansion_confirmed INTEGER NOT NULL, previous_revision_digest TEXT NOT NULL,
              revision_digest TEXT NOT NULL, created_at REAL NOT NULL,
              UNIQUE(run_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_objective_plan_run
              ON objective_plan_revisions(run_id, version);
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.db_path), isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def current(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM objective_plan_revisions WHERE run_id=? ORDER BY version DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row:
            return self._row(row)
        request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
        return {
            "version": VERSION,
            "beast_object_type": WORKSPACE_TYPE,
            "run_id": run_id,
            "revision_id": "",
            "plan_version": 0,
            "objective": str(run.get("objective") or ""),
            "success_criteria": _criteria(request.get("success_criteria")),
            "plan": {"status": "not_created", "steps": [], "active_step_id": ""},
            "history_available": False,
            "authority": "objective_plan_record_only",
            "grants_execution_authority": False,
            "grants_objective_expansion": False,
        }

    def revise(
        self,
        run_id: str,
        *,
        objective: str,
        success_criteria: Sequence[Any],
        steps: Sequence[Mapping[str, Any]],
        active_step_id: str = "",
        operator_id: str,
        reason: str,
        expansion_confirmed: bool = False,
    ) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        operator = str(operator_id or "").strip()
        why = str(reason or "").strip()
        new_objective = str(objective or "").strip()
        criteria = _criteria(success_criteria)
        normalized_steps = _steps(steps)
        if not operator or not why:
            raise ValueError("operator_id and reason are required")
        if normalize_state(str(run.get("state") or "")) in TERMINAL_STATES and not operator.startswith("beast.phase"):
            raise ValueError("terminal runs cannot revise mission intent")
        if not new_objective:
            raise ValueError("objective is required")
        if not criteria:
            raise ValueError("at least one measurable success criterion is required")
        if not normalized_steps:
            raise ValueError("at least one plan step is required")
        step_ids = {step["step_id"] for step in normalized_steps}
        active = str(active_step_id or "").strip()
        active_marked = [step["step_id"] for step in normalized_steps if step["status"] == "active"]
        if not active and active_marked:
            active = active_marked[0]
        if active and active not in step_ids:
            raise ValueError("active_step_id must reference a plan step")
        if len(active_marked) > 1:
            raise ValueError("only one plan step may be active")
        for step in normalized_steps:
            if active:
                if step["step_id"] == active and step["status"] == "pending":
                    step["status"] = "active"
                elif step["step_id"] != active and step["status"] == "active":
                    step["status"] = "pending"
        previous = self.current(run_id)
        old_objective = str(previous.get("objective") or run.get("objective") or "").strip()
        expanded = self._is_expansion(old_objective, new_objective, previous.get("success_criteria", []), criteria)
        if expanded and not expansion_confirmed:
            raise ValueError("material objective expansion requires explicit confirmation")
        created = time.time()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT version, revision_digest FROM objective_plan_revisions WHERE run_id=? ORDER BY version DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            version = (int(row["version"]) + 1) if row else 1
            previous_digest = str(row["revision_digest"]) if row else ""
            semantic = {
                "version": VERSION,
                "beast_object_type": REVISION_TYPE,
                "revision_id": f"planrev_{uuid4().hex}",
                "run_id": run_id,
                "plan_version": version,
                "objective": new_objective,
                "success_criteria": criteria,
                "plan": {"status": "active", "steps": normalized_steps, "active_step_id": active},
                "operator_id": operator,
                "reason": why,
                "objective_expanded": expanded,
                "expansion_confirmed": bool(expansion_confirmed),
                "previous_revision_digest": previous_digest,
                "created_at": created,
                "authority": "objective_plan_record_only",
                "grants_execution_authority": False,
                "grants_objective_expansion": False,
            }
            digest = sha256_digest(semantic)
            import json
            db.execute(
                "INSERT INTO objective_plan_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (semantic["revision_id"], run_id, version, new_objective,
                 json.dumps(criteria, separators=(",", ":")),
                 json.dumps(semantic["plan"], separators=(",", ":")), active, operator, why,
                 int(bool(expansion_confirmed)), previous_digest, digest, created),
            )
            db.execute("COMMIT")
        receipt = {**semantic, "revision_digest": digest}
        self.engine.merge_checkpoint(run_id, {
            "objective_plan": receipt,
            "plan": {**semantic["plan"], "version": version, "revision_reason": why},
            "success_criteria": criteria,
        })
        self.engine.emit(run_id, "agent.plan.revised", {
            "summary": f"Plan revised to version {version}",
            "plan_version": version,
            "objective": new_objective,
            "success_criteria": criteria,
            "active_step_id": active,
            "reason": why,
            "revision_digest": digest,
        })
        return receipt

    def advance(self, run_id: str, *, completed_step_id: str, next_step_id: str = "", operator_id: str, reason: str) -> dict[str, Any]:
        current = self.current(run_id)
        if not current.get("revision_id"):
            raise ValueError("a durable plan must exist before advancing")
        plan = dict(current["plan"])
        steps = [dict(step) for step in plan.get("steps", [])]
        found = False
        for step in steps:
            if step["step_id"] == completed_step_id:
                step["status"] = "completed"
                found = True
            elif next_step_id and step["step_id"] == next_step_id:
                step["status"] = "active"
            elif step["status"] == "active":
                step["status"] = "pending"
        if not found:
            raise ValueError("completed_step_id must reference a plan step")
        if next_step_id and next_step_id not in {step["step_id"] for step in steps}:
            raise ValueError("next_step_id must reference a plan step")
        return self.revise(
            run_id, objective=current["objective"], success_criteria=current["success_criteria"],
            steps=steps, active_step_id=next_step_id, operator_id=operator_id, reason=reason,
            expansion_confirmed=False,
        )

    def history(self, run_id: str) -> list[dict[str, Any]]:
        if not self.engine.store.get_run(run_id):
            raise KeyError(f"unknown agent run: {run_id}")
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM objective_plan_revisions WHERE run_id=? ORDER BY version", (run_id,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def verify(self, receipt: Mapping[str, Any]) -> bool:
        return (
            receipt.get("beast_object_type") == REVISION_TYPE
            and str(receipt.get("version")) == VERSION
            and verify_digest(semantic_payload(receipt, exclude={"revision_digest"}), str(receipt.get("revision_digest") or ""))
            and receipt.get("authority") == "objective_plan_record_only"
            and receipt.get("grants_execution_authority") is False
            and receipt.get("grants_objective_expansion") is False
        )

    @staticmethod
    def _is_expansion(old: str, new: str, old_criteria: Sequence[Any], new_criteria: Sequence[Any]) -> bool:
        if not old:
            return False
        old_words = {word.lower() for word in old.split() if len(word) > 3}
        new_words = {word.lower() for word in new.split() if len(word) > 3}
        objective_widened = bool(new_words - old_words) and not new_words.issubset(old_words)
        criteria_widened = not set(_criteria(new_criteria)).issubset(set(_criteria(old_criteria))) if old_criteria else False
        return objective_widened or criteria_widened

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        import json
        return {
            "version": VERSION,
            "beast_object_type": REVISION_TYPE,
            "revision_id": row["revision_id"], "run_id": row["run_id"],
            "plan_version": row["version"], "objective": row["objective"],
            "success_criteria": json.loads(row["success_criteria_json"]),
            "plan": json.loads(row["plan_json"]),
            "operator_id": row["operator_id"], "reason": row["reason"],
            "expansion_confirmed": bool(row["expansion_confirmed"]),
            "previous_revision_digest": row["previous_revision_digest"],
            "created_at": row["created_at"], "authority": "objective_plan_record_only",
            "grants_execution_authority": False, "grants_objective_expansion": False,
            "revision_digest": row["revision_digest"], "history_available": True,
        }
