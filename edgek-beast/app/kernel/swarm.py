"""
EdgeK BEAST Gateway - Swarm Kernel
Deterministic role-based state machine for governed agentic workflows.
"""

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SwarmState(Enum):
    RECEIVED = "received"
    PLANNED = "planned"
    GATED = "gated"
    CONTEXT_MAPPED = "context_mapped"
    COMPRESSED = "compressed"
    SUPERVISED = "supervised"
    CRITIQUED = "critiqued"
    ARCHIVED = "archived"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class RoleEvent:
    run_id: str
    role: str
    state: str
    decision: str
    details: Dict[str, Any]
    created_at: str


@dataclass
class SwarmRun:
    run_id: str
    objective: str
    state: str
    status: str
    task_type: str
    risk_level: str
    plan: List[Dict[str, Any]]
    gates: List[Dict[str, Any]]
    value: Dict[str, Any]
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class SwarmKernel:
    """Coordinates deterministic internal roles without multiplying model calls."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        db_path: Optional[str] = None,
        workspace_graph: Optional[Any] = None,
    ):
        self.policies = policies or {}
        self.workspace_graph = workspace_graph
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "swarm.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_runs (
                    run_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    state TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    gates TEXT NOT NULL,
                    value TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_status ON swarm_runs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_updated ON swarm_runs(updated_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_role_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    state TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_events_run ON swarm_role_events(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_events_role ON swarm_role_events(role)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_value_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    expected_value REAL NOT NULL,
                    actual_value REAL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_value_run ON swarm_value_logs(run_id)")

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run one deterministic swarm planning/supervision cycle."""
        payload = payload or {}
        run_id = str(payload.get("run_id") or uuid.uuid4())
        objective = str(payload.get("objective") or payload.get("task") or "").strip()
        if not objective:
            raise ValueError("Swarm objective is required")

        now = _utc_now()
        task_type = self._classify_task(objective, payload)
        risk_level = self._risk_level(objective, payload)
        state = SwarmState.RECEIVED
        events: List[RoleEvent] = []

        plan = self._conductor_plan(objective, task_type, risk_level, payload)
        state = SwarmState.PLANNED
        events.append(self._event(run_id, "conductor", state, "plan_selected", {
            "task_type": task_type,
            "steps": plan,
        }))

        gates = self._sentinel_gates(objective, risk_level, payload)
        blocked_gate = next((gate for gate in gates if gate["decision"] == "block"), None)
        approval_gate = next((gate for gate in gates if gate["decision"] == "approval_required"), None)
        state = SwarmState.GATED
        events.append(self._event(run_id, "sentinel", state, "gates_evaluated", {
            "risk_level": risk_level,
            "gates": gates,
        }))

        if blocked_gate or approval_gate:
            status = "blocked"
            if approval_gate:
                status = "approval_required"
            value = self._value_metrics(payload, plan, gates, status)
            run = SwarmRun(run_id, objective, SwarmState.BLOCKED.value, status, task_type, risk_level,
                           plan, gates, value, now, now, payload.get("metadata") or {})
            events.append(self._event(run_id, "supervisor", SwarmState.BLOCKED, status, {
                "blocked_gate": blocked_gate,
                "approval_gate": approval_gate,
            }))
            self._store_run(run, events)
            return self.get_run(run_id)

        context_plan = self._cartographer_context(payload)
        state = SwarmState.CONTEXT_MAPPED
        events.append(self._event(run_id, "cartographer", state, "context_selected", context_plan))

        compression = self._compressor_plan(payload, context_plan)
        state = SwarmState.COMPRESSED
        events.append(self._event(run_id, "compressor", state, "context_budgeted", compression))

        supervision = self._supervisor_check(payload, plan, gates)
        state = SwarmState.SUPERVISED
        events.append(self._event(run_id, "supervisor", state, supervision["decision"], supervision))

        critic = None
        if supervision["decision"] != "pass" or risk_level in ("high", "critical") or payload.get("model_based_critic"):
            critic = self._critic_review(payload, supervision, risk_level)
            state = SwarmState.CRITIQUED
            events.append(self._event(run_id, "critic", state, critic["decision"], critic))

        status = self._final_status(supervision, critic)
        value = self._value_metrics(payload, plan, gates, status, compression=compression, critic=critic)
        events.append(self._event(run_id, "archivist", SwarmState.ARCHIVED, "run_archived", {
            "value": value,
            "event_count": len(events) + 1,
        }))

        final_state = SwarmState.COMPLETED if status in ("ready", "succeeded") else SwarmState.BLOCKED
        run = SwarmRun(run_id, objective, final_state.value, status, task_type, risk_level,
                       plan, gates, value, now, _utc_now(), payload.get("metadata") or {})
        self._store_run(run, events)
        return self.get_run(run_id)

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM swarm_runs").fetchone()[0]
            statuses = conn.execute("SELECT status, COUNT(*) FROM swarm_runs GROUP BY status").fetchall()
            roles = conn.execute("SELECT role, COUNT(*) FROM swarm_role_events GROUP BY role").fetchall()
            value = conn.execute("""
                SELECT metric, COUNT(*), COALESCE(SUM(expected_value), 0.0), COALESCE(SUM(actual_value), 0.0)
                FROM swarm_value_logs
                GROUP BY metric
            """).fetchall()
        return {
            "enabled": bool(self.policies.get("swarm", {}).get("enabled", False)),
            "runs": total,
            "statuses": {row[0]: row[1] for row in statuses},
            "role_events": {row[0]: row[1] for row in roles},
            "value": {
                row[0]: {
                    "count": row[1],
                    "expected_total": row[2],
                    "actual_total": row[3],
                }
                for row in value
            },
            "db": str(self.db_path),
        }

    def recent_runs(self, limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if status:
            where = "WHERE status = ?"
            params.append(status)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT run_id, objective, state, status, task_type, risk_level,
                       plan, gates, value, metadata, created_at, updated_at
                FROM swarm_runs
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
            """, params).fetchall()
        return [self._run_row_to_dict(row, include_events=False) for row in rows]

    def get_run(self, run_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT run_id, objective, state, status, task_type, risk_level,
                       plan, gates, value, metadata, created_at, updated_at
                FROM swarm_runs
                WHERE run_id = ?
            """, (run_id,)).fetchone()
            if not row:
                raise ValueError(f"Swarm run not found: {run_id}")
            events = conn.execute("""
                SELECT role, state, decision, details, created_at
                FROM swarm_role_events
                WHERE run_id = ?
                ORDER BY id ASC
            """, (run_id,)).fetchall()
            values = conn.execute("""
                SELECT metric, expected_value, actual_value, details, created_at
                FROM swarm_value_logs
                WHERE run_id = ?
                ORDER BY id ASC
            """, (run_id,)).fetchall()
        result = self._run_row_to_dict(row, include_events=False)
        result["events"] = [
            {
                "role": event[0],
                "state": event[1],
                "decision": event[2],
                "details": json.loads(event[3] or "{}"),
                "created_at": event[4],
            }
            for event in events
        ]
        result["value_logs"] = [
            {
                "metric": item[0],
                "expected_value": item[1],
                "actual_value": item[2],
                "details": json.loads(item[3] or "{}"),
                "created_at": item[4],
            }
            for item in values
        ]
        return result

    def value_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT run_id, metric, expected_value, actual_value, details, created_at
                FROM swarm_value_logs
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [
            {
                "run_id": row[0],
                "metric": row[1],
                "expected_value": row[2],
                "actual_value": row[3],
                "details": json.loads(row[4] or "{}"),
                "created_at": row[5],
            }
            for row in rows
        ]

    def _classify_task(self, objective: str, payload: Dict[str, Any]) -> str:
        explicit = payload.get("task_type")
        if explicit:
            return str(explicit)
        text = objective.lower()
        if any(word in text for word in ["test", "pytest", "failing", "failure"]):
            return "test_repair"
        if any(word in text for word in ["security", "secret", "credential", "permission"]):
            return "security_review"
        if any(word in text for word in ["readme", "docs", "documentation"]):
            return "documentation"
        if any(word in text for word in ["implement", "fix", "refactor", "bug"]):
            return "code_change"
        return "general"

    def _risk_level(self, objective: str, payload: Dict[str, Any]) -> str:
        explicit = payload.get("risk_level")
        if explicit:
            return str(explicit)
        text = " ".join([
            objective.lower(),
            json.dumps(payload.get("tools") or []),
            json.dumps(payload.get("commands") or []),
        ])
        if any(word in text for word in ["secret", "credential", "private key", ".env"]):
            return "critical"
        if any(word in text for word in ["rm -rf", "delete", "drop table", "deploy", "production"]):
            return "high"
        if any(word in text for word in ["write", "edit", "shell", "migration"]):
            return "medium"
        return "low"

    def _conductor_plan(self, objective: str, task_type: str, risk_level: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        base = [
            {"role": "cartographer", "action": "select_relevant_context"},
            {"role": "compressor", "action": "fit_context_budget"},
            {"role": "supervisor", "action": "check_success_criteria"},
            {"role": "archivist", "action": "record_trace_and_value"},
        ]
        if task_type in ("code_change", "test_repair"):
            base.insert(2, {"role": "conductor", "action": "prefer_targeted_edit_and_test"})
        if risk_level in ("high", "critical"):
            base.insert(0, {"role": "sentinel", "action": "require_gate_before_execution"})
            base.append({"role": "critic", "action": "review_high_risk_strategy"})
        if payload.get("model_based_critic"):
            base.append({"role": "critic", "action": "optional_model_based_review"})
        return base

    def _sentinel_gates(self, objective: str, risk_level: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        gates = []
        text = objective.lower()
        approved = bool(payload.get("approved", False))
        if risk_level == "critical":
            gates.append({
                "name": "critical_secret_or_credential_gate",
                "decision": "block",
                "reason": "Critical-risk workflows require explicit redesign before execution",
            })
        elif risk_level == "high" and not approved:
            gates.append({
                "name": "high_risk_user_approval",
                "decision": "approval_required",
                "reason": "High-risk workflow requires user approval",
            })
        if any(word in text for word in ["delete", "drop table", "rm -rf"]) and not approved:
            gates.append({
                "name": "destructive_action_gate",
                "decision": "approval_required",
                "reason": "Destructive action requires approval",
            })
        if not gates:
            gates.append({
                "name": "deterministic_policy_gate",
                "decision": "allow",
                "reason": "No blocking deterministic gate matched",
            })
        return gates

    def _cartographer_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        files = payload.get("files") or payload.get("context_files") or []
        graph_nodes = payload.get("workspace_nodes") or []
        objective = str(payload.get("objective") or payload.get("task") or "")
        semantic = {"results": [], "result_count": 0}
        if self.workspace_graph is not None and objective:
            semantic = self.workspace_graph.semantic_context(
                objective,
                limit=int(payload.get("semantic_context_limit", 6)),
                include_content=True,
                max_chars_per_chunk=int(payload.get("semantic_chunk_chars", 700)),
            )
        return {
            "files": files[:20],
            "workspace_nodes": graph_nodes[:20],
            "semantic_context": semantic,
            "compact_context": [
                {
                    "file": item.get("file"),
                    "lines": [item.get("start_line"), item.get("end_line")],
                    "similarity": item.get("similarity"),
                    "content": item.get("content"),
                }
                for item in semantic.get("results", [])
            ],
            "retrieval_mode": "semantic_rag" if semantic.get("result_count") else ("targeted" if files or graph_nodes else "none_supplied"),
        }

    def _compressor_plan(self, payload: Dict[str, Any], context_plan: Dict[str, Any]) -> Dict[str, Any]:
        context = payload.get("context") or ""
        original_tokens = int(payload.get("estimated_context_tokens") or max(0, len(str(context)) // 4))
        target_tokens = int(payload.get("target_context_tokens") or 8000)
        final_tokens = min(original_tokens, target_tokens)
        semantic_chunks = len(context_plan.get("compact_context") or [])
        if semantic_chunks and original_tokens == 0:
            original_tokens = semantic_chunks * 1000
            final_tokens = min(target_tokens, semantic_chunks * 180)
        return {
            "original_tokens": original_tokens,
            "target_tokens": target_tokens,
            "final_tokens": final_tokens,
            "estimated_tokens_saved": max(0, original_tokens - final_tokens),
            "retrieval_mode": context_plan["retrieval_mode"],
            "semantic_chunks_shared": semantic_chunks,
        }

    def _supervisor_check(self, payload: Dict[str, Any], plan: List[Dict[str, Any]], gates: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = payload.get("execution_result")
        success_criteria = payload.get("success_criteria") or []
        if result is None:
            return {
                "decision": "ready",
                "reason": "Plan and deterministic gates are ready for execution",
                "success_criteria": success_criteria,
            }
        if bool(result.get("success")):
            return {
                "decision": "pass",
                "reason": "Reported execution result satisfied supervisor",
                "success_criteria": success_criteria,
                "execution_result": result,
            }
        return {
            "decision": "fail",
            "reason": result.get("error") or "Reported execution result failed",
            "success_criteria": success_criteria,
            "execution_result": result,
        }

    def _critic_review(self, payload: Dict[str, Any], supervision: Dict[str, Any], risk_level: str) -> Dict[str, Any]:
        model_based = bool(payload.get("model_based_critic"))
        if supervision["decision"] == "fail":
            decision = "revise_plan"
            recommendation = "Change strategy before retrying; inspect failure signature and narrow the next action."
        elif risk_level in ("high", "critical"):
            decision = "risk_review"
            recommendation = "Keep human approval and reduce blast radius before execution."
        else:
            decision = "advisory"
            recommendation = "No deterministic critique required."
        return {
            "decision": decision,
            "recommendation": recommendation,
            "model_based_requested": model_based,
            "model_call_executed": False,
            "expected_value_logged": model_based,
        }

    def _final_status(self, supervision: Dict[str, Any], critic: Optional[Dict[str, Any]]) -> str:
        if supervision["decision"] == "pass":
            return "succeeded"
        if supervision["decision"] == "fail":
            return "needs_revision"
        return "ready"

    def _value_metrics(
        self,
        payload: Dict[str, Any],
        plan: List[Dict[str, Any]],
        gates: List[Dict[str, Any]],
        status: str,
        compression: Optional[Dict[str, Any]] = None,
        critic: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        saved = float((compression or {}).get("estimated_tokens_saved", 0))
        avoided_model_calls = 1.0 if critic and critic.get("model_based_requested") and not critic.get("model_call_executed") else 0.0
        blocked_risk = 1.0 if status in ("blocked", "approval_required") else 0.0
        expected_score = min(1.0, (saved / 20000.0) + (avoided_model_calls * 0.25) + (blocked_risk * 0.5))
        return {
            "estimated_tokens_saved": saved,
            "avoided_model_calls": avoided_model_calls,
            "blocked_risk_events": blocked_risk,
            "expected_value_score": expected_score,
            "extra_model_calls": 0,
        }

    def _event(self, run_id: str, role: str, state: SwarmState, decision: str, details: Dict[str, Any]) -> RoleEvent:
        return RoleEvent(run_id, role, state.value, decision, details, _utc_now())

    def _store_run(self, run: SwarmRun, events: List[RoleEvent]):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO swarm_runs
                (run_id, objective, state, status, task_type, risk_level, plan, gates,
                 value, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.run_id,
                run.objective,
                run.state,
                run.status,
                run.task_type,
                run.risk_level,
                json.dumps(_json_safe(run.plan), sort_keys=True),
                json.dumps(_json_safe(run.gates), sort_keys=True),
                json.dumps(_json_safe(run.value), sort_keys=True),
                json.dumps(_json_safe(run.metadata), sort_keys=True),
                run.created_at,
                run.updated_at,
            ))
            for event in events:
                conn.execute("""
                    INSERT INTO swarm_role_events
                    (run_id, role, state, decision, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    event.run_id,
                    event.role,
                    event.state,
                    event.decision,
                    json.dumps(_json_safe(event.details), sort_keys=True),
                    event.created_at,
                ))
            for metric, value in run.value.items():
                if isinstance(value, (int, float)):
                    conn.execute("""
                        INSERT INTO swarm_value_logs
                        (run_id, metric, expected_value, actual_value, details, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        run.run_id,
                        metric,
                        float(value),
                        None,
                        json.dumps({"status": run.status}, sort_keys=True),
                        _utc_now(),
                    ))

    def _run_row_to_dict(self, row: Any, include_events: bool = False) -> Dict[str, Any]:
        return {
            "run_id": row[0],
            "objective": row[1],
            "state": row[2],
            "status": row[3],
            "task_type": row[4],
            "risk_level": row[5],
            "plan": json.loads(row[6] or "[]"),
            "gates": json.loads(row[7] or "[]"),
            "value": json.loads(row[8] or "{}"),
            "metadata": json.loads(row[9] or "{}"),
            "created_at": row[10],
            "updated_at": row[11],
        }


swarm_kernel = SwarmKernel()
