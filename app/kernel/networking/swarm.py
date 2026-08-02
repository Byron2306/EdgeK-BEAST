"""
EdgeK BEAST Gateway - Swarm Kernel
Deterministic role-based state machine for governed agentic workflows.
"""

import json
import hashlib
import re
import sqlite3
import uuid
import threading
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.networking.swarm_services import SwarmKernelServices
from app.kernel.networking.swarm_contracts import role_result_from_details
from app.kernel.networking.swarm_lifecycle import HermesLifecycle
from app.kernel.agents.phase_e_learning import Archivist, Scribe


PROFILE_BINDINGS: Dict[str, Dict[str, Any]] = {
    "hermes": {
        "profile": "hermes",
        "role": "coordinator",
        "execution_capability": "swarm_plan_shape",
        "default_execution": "role_briefs_and_routing",
        "requires_approval": False,
        "description": "Coordinator/router for role briefs and swarm plan shape.",
    },
    "openclaw": {
        "profile": "openclaw",
        "role": "local_inspector",
        "execution_capability": "read_only_local_first",
        "default_execution": "planning_and_inspection",
        "requires_approval": False,
        "description": "Read-only/local-first planning and inspection.",
    },
    "nemoclaw": {
        "profile": "nemoclaw",
        "role": "gated_executor",
        "execution_capability": "high_risk_gated",
        "default_execution": "approval_required",
        "requires_approval": True,
        "description": "Gated high-risk execution profile.",
    },
    "zeroclaw": {
        "profile": "zeroclaw",
        "role": "planner",
        "execution_capability": "planning_only",
        "default_execution": "no_tool_execution",
        "requires_approval": False,
        "description": "Planning-only profile with no tool execution.",
    },
}


ROLE_LANES: Dict[str, Dict[str, Any]] = {
    "failure_analyst": {
        "lane": "failure_analyst",
        "purpose": "failure signatures, historical evidence, operation family",
        "default_risk": "read_only",
    },
    "crystalist": {
        "lane": "crystalist",
        "purpose": "reuse, staleness, compatibility, and interception decisions",
        "default_risk": "read_only",
    },
    "cartographer": {
        "lane": "cartographer",
        "purpose": "context, graph, memory, schema, exact files",
        "default_risk": "read_only",
    },
    "compressor": {
        "lane": "compressor",
        "purpose": "chunk/reduce/package context",
        "default_risk": "read_only",
    },
    "sentinel": {
        "lane": "sentinel",
        "purpose": "policy, credentials, circuits, approvals, secrets",
        "default_risk": "governance",
    },
    "verifier": {
        "lane": "verifier",
        "purpose": "tests, lint, syntax, static checks",
        "default_risk": "read_only",
    },
    "scribe": {
        "lane": "scribe",
        "purpose": "Chronicle and promotion candidate records",
        "default_risk": "write_safe_record",
    },
    "critic": {
        "lane": "critic",
        "purpose": "targeted review when risk or failure warrants it",
        "default_risk": "advisory",
    },
}


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
        services: Optional[SwarmKernelServices] = None,
    ):
        self.policies = policies or {}
        self.workspace_graph = workspace_graph
        self.services = services or SwarmKernelServices.from_runtime(
            policies=self.policies,
            workspace_graph=workspace_graph,
        )
        self.lifecycle = HermesLifecycle()
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "swarm.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = threading.Lock()
        self._db_initialized = False

    def _connect(self):
        from app.kernel.compute.container import container
        if not self._db_initialized:
            with self._init_lock:
                if not self._db_initialized:
                    self._init_db_immediate()
                    self._db_initialized = True
        
        # Diagnostic: print where we are trying to connect
        print(f"DEBUG: SwarmKernel._connect connecting to: {self.db_path}")
        return sqlite3.connect(self.db_path)

    def _init_db_immediate(self):
        print(f"DEBUG: Initializing swarm database at {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        try:
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
            print("DEBUG: swarm_runs table created")
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
            conn.commit()
            print("DEBUG: Initialization complete")
        finally:
            conn.close()

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
        profile = self._execution_profile(payload)
        metadata = dict(payload.get("metadata") or {})
        metadata["execution_profile"] = profile
        metadata["role_lanes"] = self._lane_briefs()
        metadata["service_inventory"] = self.services.inventory()
        lifecycle = self.lifecycle.decide(payload)
        metadata["hermes_lifecycle"] = lifecycle.to_dict()
        state = SwarmState.RECEIVED
        events: List[RoleEvent] = []

        plan = self._conductor_plan(objective, task_type, risk_level, payload, profile)
        state = SwarmState.PLANNED
        route_decision = self._hermes_route(payload, task_type, risk_level)
        events.append(self._event(run_id, "hermes", state, "role_briefs_routed", {
            "profile": profile,
            "role_lanes": self._lane_briefs(),
            "plan_shape": plan,
            "route_decision": route_decision,
            "lifecycle": lifecycle.to_dict(),
        }))
        events.append(self._event(run_id, "conductor", state, "plan_selected", {
            "task_type": task_type,
            "steps": plan,
        }))

        gates = self._sentinel_gates(objective, risk_level, payload, profile)
        blocked_gate = next((gate for gate in gates if gate["decision"] == "block"), None)
        approval_gate = next((gate for gate in gates if gate["decision"] == "approval_required"), None)
        state = SwarmState.GATED
        events.append(self._event(run_id, "sentinel", state, "gates_evaluated", {
            "risk_level": risk_level,
            "profile": profile["profile"],
            "gates": gates,
        }))

        if blocked_gate or approval_gate:
            status = "blocked"
            if approval_gate:
                status = "approval_required"
            value = self._value_metrics(payload, plan, gates, status)
            run = SwarmRun(run_id, objective, SwarmState.BLOCKED.value, status, task_type, risk_level,
                           plan, gates, value, now, now, metadata)
            events.append(self._event(run_id, "supervisor", SwarmState.BLOCKED, status, {
                "blocked_gate": blocked_gate,
                "approval_gate": approval_gate,
            }))
            self._store_run(run, events)
            return self.get_run(run_id)

        context_plan = self._cartographer_context(payload)
        state = SwarmState.CONTEXT_MAPPED
        events.append(self._event(run_id, "cartographer", state, "context_selected", context_plan))

        failure_analysis = self._failure_analysis(payload, objective, task_type, context_plan)
        events.append(self._event(run_id, "failure_analyst", state, "failure_signature_normalized", failure_analysis))

        compression = self._compressor_plan(payload, context_plan)
        state = SwarmState.COMPRESSED
        events.append(self._event(run_id, "compressor", state, "context_budgeted", compression))

        crystal_decision = self._crystalist_decision(
            payload,
            context_plan=context_plan,
            failure_analysis=failure_analysis,
        )
        events.append(self._event(run_id, "crystalist", state, "reuse_classified", crystal_decision))

        verifier = self._verifier_checks(payload, task_type)
        if verifier["checks"]:
            events.append(self._event(run_id, "verifier", state, verifier["decision"], verifier))

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
        learning = (self.services.scribe or Scribe()).compile_episode(
            task_class=task_type,
            events=[_json_safe(event) for event in events],
            execution=payload.get("execution_result"),
            verification={"status": "passed" if status in ("ready", "succeeded") else "failed"},
            critic=critic,
        )
        archive = (self.services.archivist or Archivist()).archive(
            learning,
            execution=payload.get("execution_result"),
            verification={"status": "passed" if status in ("ready", "succeeded") else "failed"},
            critic=critic,
        )
        events.append(self._event(run_id, "scribe", SwarmState.ARCHIVED, "chronicle_trace_prepared", {
            "value": value,
            "promotion_candidate": learning["promotion_candidate"],
            "classifications": learning["classifications"],
            "promotion_authorized": learning["promotion_authorized"],
            "event_count": len(events) + 2,
        }))
        events.append(self._event(run_id, "archivist", SwarmState.ARCHIVED, "run_archived", {
            "value": value,
            "packet_hash": archive["packet"]["packet_hash"],
            "promotion_authorized": archive["promotion_authorized"],
            "event_count": len(events) + 1,
        }))

        final_state = SwarmState.COMPLETED if status in ("ready", "succeeded") else SwarmState.BLOCKED
        run = SwarmRun(run_id, objective, final_state.value, status, task_type, risk_level,
                       plan, gates, value, now, _utc_now(), metadata)
        self._store_run(run, events)
        return self.get_run(run_id)

    def governed_roles(self, profile: Optional[str] = None) -> Dict[str, Any]:
        profiles = PROFILE_BINDINGS
        if profile:
            selected = self._execution_profile({"profile": profile})["profile"]
            profiles = {selected: PROFILE_BINDINGS[selected]}
        return {
            "beast_object_type": "swarm_governance_profile",
            "version": "1.0",
            "profiles": profiles,
            "role_lanes": ROLE_LANES,
            "routing": {
                "default_profile": "hermes",
                "planning_only_profiles": ["zeroclaw"],
                "approval_gated_profiles": ["nemoclaw"],
                "local_first_profiles": ["openclaw", "hermes", "zeroclaw"],
            },
        }

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
            "profiles": PROFILE_BINDINGS,
            "role_lanes": ROLE_LANES,
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

    def _conductor_plan(
        self,
        objective: str,
        task_type: str,
        risk_level: str,
        payload: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        base = [
            {"role": "hermes", "action": "route_role_briefs", "profile": profile["profile"]},
            {"role": "cartographer", "action": "select_relevant_context"},
            {"role": "failure_analyst", "action": "normalize_failure_signature"},
            {"role": "compressor", "action": "fit_context_budget"},
            {"role": "crystalist", "action": "classify_reuse_without_authority"},
            {"role": "supervisor", "action": "check_success_criteria"},
            {"role": "scribe", "action": "record_chronicle_and_promotion_signal"},
        ]
        if task_type in ("code_change", "test_repair"):
            base.insert(3, {"role": "verifier", "action": "plan_tests_lint_syntax_static_checks"})
        if risk_level in ("high", "critical"):
            base.insert(0, {"role": "sentinel", "action": "require_gate_before_execution"})
            base.append({"role": "critic", "action": "review_high_risk_strategy"})
        if profile["profile"] == "zeroclaw":
            base.append({"role": "sentinel", "action": "enforce_no_tool_execution"})
        if profile["profile"] == "nemoclaw":
            base.insert(0, {"role": "sentinel", "action": "require_nemoclaw_approval_gate"})
        if payload.get("model_based_critic"):
            base.append({"role": "critic", "action": "optional_model_based_review"})
        return base

    def _sentinel_gates(
        self,
        objective: str,
        risk_level: str,
        payload: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        gates = []
        text = objective.lower()
        approved = bool(payload.get("approved", False))
        if profile["profile"] == "zeroclaw":
            gates.append({
                "name": "zeroclaw_planning_only",
                "decision": "allow",
                "reason": "ZeroClaw may plan but never execute tools",
            })
        if profile["profile"] == "nemoclaw" and not approved:
            gates.append({
                "name": "nemoclaw_explicit_approval",
                "decision": "approval_required",
                "reason": "Nemoclaw high-risk execution profile requires explicit approval",
            })
        if profile["profile"] == "openclaw" and risk_level in ("medium", "high") and not approved:
            gates.append({
                "name": "openclaw_read_only_boundary",
                "decision": "approval_required",
                "reason": "Openclaw is read-only/local-first; write or shell work needs approval",
            })
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
            "selection_evidence": [
                "caller_supplied_context" if files or graph_nodes else "no_caller_files",
                "semantic_workspace_match" if semantic.get("result_count") else "no_semantic_match",
            ],
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
            "read_only": True,
        }

    def _hermes_route(self, payload: Dict[str, Any], task_type: str, risk_level: str) -> Dict[str, Any]:
        """Return a read-only economic route recommendation for this mission."""
        candidates = payload.get("provider_candidates") or payload.get("routes") or []
        if candidates and self.services.economist is not None:
            from app.kernel.adapters.provider_economist import EconomistPolicy

            selected = self.services.economist.select(
                candidates,
                EconomistPolicy(
                    requested_role=str(payload.get("requested_role") or "primary_patch_provider"),
                    task_class=task_type,
                    max_latency_ms=payload.get("max_latency_ms"),
                    max_usd_per_fix=payload.get("max_usd_per_fix"),
                    friction_mode=str(payload.get("friction_mode") or "shadow"),
                ),
                negative_capabilities=payload.get("negative_capabilities") or [],
                friction_profiles=payload.get("friction_profiles") or [],
            )
            route = selected.get("selected") or {}
            return {
                "route": route.get("provider") or route.get("route") or "refusal",
                "reason": selected.get("reason") or "ProviderEconomist returned no eligible route",
                "predicted_cost": payload.get("predicted_cost") or {},
                "selected": route,
                "alternatives_rejected": selected.get("excluded") or [],
                "read_only": True,
            }
        if payload.get("deterministic_crystal") or payload.get("crystal_solution"):
            route, reason = "deterministic_crystal", "caller supplied a deterministic candidate for inspection"
        elif payload.get("use_ollama") is not False:
            route, reason = "ollama_residual", "no complete deterministic route was supplied; residual local reasoning remains bounded"
        else:
            route, reason = "local_first_inspection", "provider inference disabled for this read-only mission"
        return {
            "route": route,
            "reason": reason,
            "predicted_cost": payload.get("predicted_cost") or {"cloud_cost": 0, "latency_class": "unmeasured"},
            "alternatives_rejected": [],
            "read_only": True,
            "risk_level": risk_level,
        }

    def _failure_analysis(
        self,
        payload: Dict[str, Any],
        objective: str,
        task_type: str,
        context_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = payload.get("execution_result") or {}
        failure = str(
            payload.get("failure")
            or payload.get("baseline_failure")
            or result.get("error")
            or result.get("stderr")
            or objective
        ).strip()
        tokens = sorted(set(re.findall(r"[a-zA-Z][a-zA-Z0-9_.:-]{2,}", failure.lower())))[:40]
        signature_input = {"task_type": task_type, "failure": failure, "files": context_plan.get("files", [])[:20]}
        signature = str(payload.get("failure_signature") or "").strip()
        if not signature:
            signature = "sha256:" + hashlib.sha256(json.dumps(signature_input, sort_keys=True).encode()).hexdigest()
        operation_family = "replace_exact" if any(word in objective.lower() for word in ("fix", "replace", "repair")) else "inspect"
        historical = payload.get("historical_evidence") or payload.get("evidence_matches") or []
        return {
            "task_family": task_type,
            "failure_signature": signature,
            "failure_terms": tokens,
            "historical_matches": len(historical) if isinstance(historical, list) else 0,
            "strongest_prior_evidence": (historical[0] if isinstance(historical, list) and historical else None),
            "likely_target": payload.get("target") or (context_plan.get("files") or [None])[0],
            "likely_operation_family": operation_family,
            "confidence": 0.5 if failure else 0.0,
            "read_only": True,
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
        exact_payload = {
            "objective": str(payload.get("objective") or payload.get("task") or ""),
            "target": payload.get("target") or {"path": (context_plan.get("files") or [None])[0]},
            "current_code": payload.get("current_code") or "",
            "failure": payload.get("failure") or payload.get("baseline_failure") or "",
            "crystal_guidance": payload.get("crystal_guidance") or [],
            "allowed_output": payload.get("allowed_output") or {"kind": "bounded_action_ir_field"},
        }
        discarded_tools = max(0, len(payload.get("tools") or []) - 4)
        return {
            "original_tokens": original_tokens,
            "target_tokens": target_tokens,
            "final_tokens": final_tokens,
            "estimated_tokens_saved": max(0, original_tokens - final_tokens),
            "retrieval_mode": context_plan["retrieval_mode"],
            "semantic_chunks_shared": semantic_chunks,
            "exact_model_payload": exact_payload,
            "discarded_tool_schemas": discarded_tools,
            "reduction_ratio": round(max(0, original_tokens - final_tokens) / max(1, original_tokens), 4),
            "read_only": True,
        }

    def _crystalist_decision(
        self,
        payload: Dict[str, Any],
        *,
        context_plan: Dict[str, Any],
        failure_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        advisory = list(payload.get("advisory_matches") or payload.get("crystal_matches") or [])
        scaffold = list(payload.get("scaffold_matches") or [])
        exact = list(payload.get("execution_matches") or [])
        target_fingerprint = payload.get("target_fingerprint")
        compatible = bool(payload.get("compatibility_verified"))
        execution_matches = exact if target_fingerprint and compatible else []
        refusal = []
        if exact and not execution_matches:
            refusal.append("target fingerprint or compatibility proof missing")
        if not advisory and not scaffold and not execution_matches:
            refusal.append("no verified reuse candidate supplied")
        return {
            "assistance_mode": "execution_candidate" if execution_matches else ("scaffolded" if scaffold else "advisory" if advisory else "none"),
            "advisory_matches": advisory[:8],
            "scaffold_matches": scaffold[:8],
            "execution_matches": execution_matches[:8],
            "execution_refused_because": refusal,
            "failure_signature": failure_analysis["failure_signature"],
            "retrieval_mode": context_plan.get("retrieval_mode"),
            "mutation_authorized": False,
            "read_only": True,
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

    def _verifier_checks(self, payload: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        checks: List[str] = []
        explicit = payload.get("verification_plan") or payload.get("checks") or []
        if isinstance(explicit, dict):
            explicit = explicit.get("checks") or explicit.get("commands") or []
        checks.extend([str(item) for item in explicit if item])
        if task_type == "test_repair":
            checks.extend(["pytest_targeted", "py_compile"])
        elif task_type == "code_change":
            checks.extend(["py_compile", "targeted_tests_if_available"])
        unique_checks = list(dict.fromkeys(checks))
        return {
            "decision": "checks_planned" if unique_checks else "no_checks_required",
            "checks": unique_checks,
            "read_only": True,
            "model_call_executed": False,
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
        """Persist legacy event fields plus the validated shared role contract."""
        payload = dict(details or {})
        status = "blocked" if decision in {"blocked", "approval_required", "refused"} else "failed" if decision in {"failed", "error"} else "completed"
        next_role = {
            "hermes": "sentinel",
            "sentinel": "cartographer",
            "cartographer": "failure_analyst",
            "failure_analyst": "compressor",
            "compressor": "crystalist",
            "crystalist": "verifier",
            "verifier": "supervisor",
            "supervisor": "critic",
            "critic": "scribe",
            "scribe": "archivist",
            "archivist": None,
        }.get(role)
        typed = role_result_from_details(role, payload, next_role=next_role, status=status)
        payload["role_result"] = typed.to_dict()
        return RoleEvent(run_id, role, state.value, decision, payload, _utc_now())

    def _execution_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested = str(
            payload.get("profile")
            or payload.get("mode")
            or payload.get("execution_profile")
            or "hermes"
        ).lower()
        if requested not in PROFILE_BINDINGS:
            requested = "hermes"
        return dict(PROFILE_BINDINGS[requested])

    def _lane_briefs(self) -> List[Dict[str, Any]]:
        return [dict(ROLE_LANES[key]) for key in ("cartographer", "failure_analyst", "compressor", "crystalist", "sentinel", "verifier", "scribe", "critic")]

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
