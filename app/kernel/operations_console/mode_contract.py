"""Phase 5.3 enforceable workbench mode contracts and transitions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import TERMINAL_STATES, normalize_state
from app.kernel.approvals.digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from app.kernel.approvals.models import PermissionMode

MODE_CONTRACT_VERSION = "5.3"
PROFILE_TYPE = "beast_workbench_mode_contract"
TRANSITION_TYPE = "beast_workbench_mode_transition_receipt"


class WorkbenchMode(str, Enum):
    ASK = "ASK"
    EDIT = "EDIT"
    AGENT = "AGENT"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class WorkbenchModeContract:
    mode: WorkbenchMode
    permission_mode: PermissionMode
    read_only: bool
    worktree_allowed: bool
    worktree_required: bool
    sourceplan_allowed: bool
    sourceplan_required: bool
    mutation_allowed: bool
    model_directed_tools: bool
    durable_run_required: bool
    repair_turn_limit: int | None
    repeated_repair_allowed: bool
    promotion_boundary_required: bool
    critic_role: bool
    verifier_role: bool
    conversion_required_for_mutation: bool
    version: str = MODE_CONTRACT_VERSION
    beast_object_type: str = PROFILE_TYPE
    contract_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["contract_digest"] = self.contract_digest or sha256_digest(
            semantic_payload(payload, exclude={"contract_digest"})
        )
        return payload


class WorkbenchModeEngine:
    """Persist and enforce conversation-first workbench mode transitions."""

    CONTRACTS = {
        WorkbenchMode.ASK: WorkbenchModeContract(
            WorkbenchMode.ASK, PermissionMode.OBSERVE_ONLY, True, False, False,
            False, False, False, False, False, 0, False, False, False, False, False,
        ),
        WorkbenchMode.EDIT: WorkbenchModeContract(
            WorkbenchMode.EDIT, PermissionMode.GUIDED, False, False, False,
            True, True, True, False, True, 1, False, True, False, False, False,
        ),
        WorkbenchMode.AGENT: WorkbenchModeContract(
            WorkbenchMode.AGENT, PermissionMode.BOUNDED_AUTONOMY, False, True, True,
            True, True, True, True, True, None, True, True, False, False, False,
        ),
        WorkbenchMode.REVIEW: WorkbenchModeContract(
            WorkbenchMode.REVIEW, PermissionMode.REVIEW, True, False, False,
            False, False, False, False, True, 0, False, False, True, True, True,
        ),
    }
    LEGAL = {
        WorkbenchMode.ASK: {WorkbenchMode.EDIT, WorkbenchMode.AGENT, WorkbenchMode.REVIEW},
        WorkbenchMode.EDIT: {WorkbenchMode.ASK, WorkbenchMode.AGENT, WorkbenchMode.REVIEW},
        WorkbenchMode.AGENT: {WorkbenchMode.ASK, WorkbenchMode.REVIEW},
        WorkbenchMode.REVIEW: {WorkbenchMode.ASK, WorkbenchMode.AGENT},
    }

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.engine = AgentRunEngine(self.workspace_root)
        self.db_path = self.workspace_root / ".beast" / "operations_console" / "mode_transitions.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS mode_transitions(
              transition_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, from_mode TEXT NOT NULL,
              to_mode TEXT NOT NULL, operator_id TEXT NOT NULL, reason TEXT NOT NULL,
              contract_digest TEXT NOT NULL, previous_digest TEXT NOT NULL,
              transition_digest TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mode_transitions_run ON mode_transitions(run_id, created_at);
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.db_path), isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def normalize(value: WorkbenchMode | str) -> WorkbenchMode:
        text = str(value.value if isinstance(value, WorkbenchMode) else value).strip().upper()
        return WorkbenchMode(text)

    def contract(self, mode: WorkbenchMode | str) -> dict[str, Any]:
        return self.CONTRACTS[self.normalize(mode)].to_dict()

    def verify_contract(self, contract: Mapping[str, Any]) -> bool:
        return (
            contract.get("beast_object_type") == PROFILE_TYPE
            and str(contract.get("version")) == MODE_CONTRACT_VERSION
            and verify_digest(semantic_payload(contract, exclude={"contract_digest"}), str(contract.get("contract_digest") or ""))
        )

    def transition(self, run_id: str, to_mode: WorkbenchMode | str, *, operator_id: str, reason: str,
                   conversion_confirmed: bool = False) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        if normalize_state(str(run.get("state") or "")) in TERMINAL_STATES:
            raise ValueError("terminal runs cannot change workbench mode")
        operator = str(operator_id or "").strip()
        why = str(reason or "").strip()
        if not operator or not why:
            raise ValueError("operator_id and reason are required")
        current = self.normalize(str(run.get("mode") or "AGENT"))
        target = self.normalize(to_mode)
        if current == target:
            raise ValueError("mode transition must change mode")
        if target not in self.LEGAL[current]:
            raise ValueError(f"illegal mode transition: {current.value} -> {target.value}")
        if current == WorkbenchMode.REVIEW and target == WorkbenchMode.AGENT and not conversion_confirmed:
            raise ValueError("REVIEW to AGENT requires explicit conversion confirmation")
        self._enforce_exit(run, current, target)
        contract = self.contract(target)
        created = time.time()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT transition_digest FROM mode_transitions WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
            previous = str(row[0]) if row else ""
            semantic = {
                "version": MODE_CONTRACT_VERSION, "beast_object_type": TRANSITION_TYPE,
                "transition_id": f"mode_{uuid4().hex}", "run_id": run_id,
                "from_mode": current.value, "to_mode": target.value,
                "operator_id": operator, "reason": why,
                "contract_digest": contract["contract_digest"], "previous_transition_digest": previous,
                "created_at": created, "authority": "workbench_mode_transition_only",
                "grants_execution_authority": False, "grants_promotion_authority": False,
            }
            digest = sha256_digest(semantic)
            db.execute("INSERT INTO mode_transitions VALUES(?,?,?,?,?,?,?,?,?,?)", (
                semantic["transition_id"], run_id, current.value, target.value, operator, why,
                contract["contract_digest"], previous, digest, created,
            ))
            db.execute("COMMIT")
        self._set_run_mode(run_id, target)
        self.engine.merge_checkpoint(run_id, {"workbench_mode": target.value, "workbench_mode_contract": contract})
        self.engine.emit(run_id, "agent.mode.changed", {
            "from_mode": current.value, "to_mode": target.value, "operator_id": operator,
            "reason": why, "contract_digest": contract["contract_digest"], "transition_digest": digest,
        })
        return {**semantic, "transition_digest": digest, "contract": contract}

    def _set_run_mode(self, run_id: str, mode: WorkbenchMode) -> None:
        with self.engine.store._lock, self.engine.store._connect() as db:  # durable same-store update
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE agent_runs SET mode=?,updated_at=? WHERE run_id=?", (mode.value.lower(), time.time(), run_id))
            db.execute("COMMIT")

    @staticmethod
    def _enforce_exit(run: Mapping[str, Any], current: WorkbenchMode, target: WorkbenchMode) -> None:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), Mapping) else {}
        if target in {WorkbenchMode.ASK, WorkbenchMode.REVIEW}:
            active_tool = checkpoint.get("active_tool") or checkpoint.get("tool_execution")
            if active_tool and str(active_tool).lower() not in {"none", "idle", "completed", "failed"}:
                raise ValueError("cannot enter a read-only mode while a tool is active")
        if target == WorkbenchMode.ASK and checkpoint.get("worktree", {}).get("dirty") if isinstance(checkpoint.get("worktree"), Mapping) else False:
            raise ValueError("cannot enter ASK with a dirty worktree")
        if current == WorkbenchMode.AGENT and target == WorkbenchMode.REVIEW:
            sourceplan = checkpoint.get("sourceplan") if isinstance(checkpoint.get("sourceplan"), Mapping) else {}
            if checkpoint.get("worktree", {}).get("dirty") and not sourceplan.get("status") in {"ready", "created", "validated"}:
                raise ValueError("AGENT to REVIEW requires a reviewable SourcePlan for dirty worktree changes")

    def history(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM mode_transitions WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
        return [dict(row) for row in rows]
