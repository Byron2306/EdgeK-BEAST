"""SQLite ledger for BEAST compute-economy plans, receipts, and credits.

This module intentionally keeps a stable compatibility surface for the TUI,
MCP tools, Compute Governor, and rollout scripts.  The recent refactor moved
several compute modules under ``app.kernel.compute``; this ledger is the small
durable seam those layers share.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.compute.compute_ir import CounterfactualCrystal, ComputeEscrowRecord


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload(value: Any) -> Dict[str, Any]:
    if hasattr(value, "to_dict"):
        data = value.to_dict()
    elif is_dataclass(value):
        data = asdict(value)
    elif isinstance(value, dict):
        data = dict(value)
    else:
        data = {}
    return data if isinstance(data, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ComputeLedger:
    def __init__(self, db_path: Optional[str] = None):
        root = Path(__file__).resolve().parents[2]
        self.db_path = Path(db_path) if db_path else root / "data" / "compute_ledger.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_initialized = False

    def _connect_raw(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        if not self._db_initialized:
            self._init_db()
            self._db_initialized = True
        conn = self._connect_raw()
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect_raw() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS compute_plans (
                    plan_id TEXT PRIMARY KEY,
                    request_fingerprint TEXT,
                    provider TEXT,
                    model TEXT,
                    task_class TEXT,
                    mode TEXT,
                    estimated_input_tokens INTEGER DEFAULT 0,
                    requested_output_tokens INTEGER DEFAULT 0,
                    created_at TEXT,
                    payload TEXT
                );
                CREATE TABLE IF NOT EXISTS compute_gates (
                    gate_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    mode TEXT,
                    decision TEXT,
                    candidate_decision TEXT,
                    enforced INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 0,
                    selected_rung TEXT,
                    recommended_rung TEXT,
                    created_at TEXT,
                    payload TEXT
                );
                CREATE TABLE IF NOT EXISTS compute_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    gate_id TEXT,
                    runtime_attempt_id TEXT,
                    mode TEXT,
                    provider TEXT,
                    model TEXT,
                    status TEXT,
                    provider_execution_requested INTEGER DEFAULT 1,
                    selected_rung TEXT,
                    recommended_rung TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    latency_ms REAL DEFAULT 0,
                    cost_usd REAL,
                    early_stopped INTEGER DEFAULT 0,
                    stream_tokens_saved INTEGER DEFAULT 0,
                    predicted_savings_usd REAL,
                    avoided_tokens_estimate INTEGER DEFAULT 0,
                    cost_observation_available INTEGER DEFAULT 0,
                    gate_decision TEXT,
                    candidate_decision TEXT,
                    suppression_enforced INTEGER DEFAULT 0,
                    behavior_preserved INTEGER,
                    created_at TEXT,
                    payload TEXT
                );
                CREATE TABLE IF NOT EXISTS counterfactual_crystals (
                    crystal_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    task_class TEXT,
                    selected_provider TEXT,
                    alternative_provider TEXT,
                    state TEXT,
                    resolution_outcome TEXT,
                    resolution_receipt_id TEXT,
                    created_at TEXT,
                    resolved_at TEXT,
                    payload TEXT
                );
                CREATE TABLE IF NOT EXISTS compute_escrows (
                    escrow_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    task_class TEXT,
                    provider TEXT,
                    model TEXT,
                    status TEXT,
                    reserved_prec_phase TEXT,
                    settled_prec_phase TEXT,
                    reserved_input_tokens INTEGER DEFAULT 0,
                    reserved_output_tokens INTEGER DEFAULT 0,
                    reserved_latency_ms INTEGER DEFAULT 0,
                    reserved_cost_usd REAL,
                    actual_input_tokens INTEGER DEFAULT 0,
                    actual_output_tokens INTEGER DEFAULT 0,
                    actual_latency_ms REAL DEFAULT 0,
                    actual_cost_usd REAL,
                    refunded_input_tokens INTEGER DEFAULT 0,
                    refunded_output_tokens INTEGER DEFAULT 0,
                    refunded_latency_ms REAL DEFAULT 0,
                    refunded_cost_usd REAL,
                    recovery_overhead_tokens INTEGER DEFAULT 0,
                    recovery_overhead_cost_usd REAL,
                    verified_delivery INTEGER DEFAULT 0,
                    emergency_claim INTEGER DEFAULT 0,
                    approved_by TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    payload TEXT
                );
                """
            )
            for column, kind in {
                "payload": "TEXT",
                "payload_json": "TEXT DEFAULT '{}'",
                "request_fingerprint": "TEXT",
                "provider": "TEXT",
                "model": "TEXT",
                "task_class": "TEXT",
                "mode": "TEXT",
                "estimated_input_tokens": "INTEGER DEFAULT 0",
                "requested_output_tokens": "INTEGER DEFAULT 0",
            }.items():
                self._ensure_column(conn, "compute_plans", column, kind)
            for column, kind in {
                "payload": "TEXT",
                "payload_json": "TEXT DEFAULT '{}'",
                "mode": "TEXT",
                "decision": "TEXT",
                "candidate_decision": "TEXT",
                "enforced": "INTEGER DEFAULT 0",
                "confidence": "REAL DEFAULT 0",
                "selected_rung": "TEXT",
                "recommended_rung": "TEXT",
            }.items():
                self._ensure_column(conn, "compute_gates", column, kind)
            for column, kind in {
                "payload": "TEXT",
                "payload_json": "TEXT DEFAULT '{}'",
                "runtime_attempt_id": "TEXT",
                "mode": "TEXT",
                "provider": "TEXT",
                "model": "TEXT",
                "status": "TEXT",
                "provider_execution_requested": "INTEGER DEFAULT 1",
                "selected_rung": "TEXT",
                "recommended_rung": "TEXT",
                "input_tokens": "INTEGER DEFAULT 0",
                "output_tokens": "INTEGER DEFAULT 0",
                "total_tokens": "INTEGER DEFAULT 0",
                "latency_ms": "REAL DEFAULT 0",
                "cost_usd": "REAL",
                "early_stopped": "INTEGER DEFAULT 0",
                "stream_tokens_saved": "INTEGER DEFAULT 0",
                "predicted_savings_usd": "REAL",
                "avoided_tokens_estimate": "INTEGER DEFAULT 0",
                "cost_observation_available": "INTEGER DEFAULT 0",
                "gate_decision": "TEXT",
                "candidate_decision": "TEXT",
                "suppression_enforced": "INTEGER DEFAULT 0",
                "behavior_preserved": "INTEGER",
            }.items():
                self._ensure_column(conn, "compute_receipts", column, kind)
            for column, kind in {
                "payload": "TEXT",
                "payload_json": "TEXT DEFAULT '{}'",
                "task_class": "TEXT",
                "selected_provider": "TEXT",
                "alternative_provider": "TEXT",
                "resolution_outcome": "TEXT",
                "resolution_receipt_id": "TEXT",
                "resolved_at": "TEXT",
            }.items():
                self._ensure_column(conn, "counterfactual_crystals", column, kind)
            for column, kind in {
                "payload": "TEXT",
                "payload_json": "TEXT DEFAULT '{}'",
                "task_class": "TEXT",
                "provider": "TEXT",
                "model": "TEXT",
                "status": "TEXT",
                "reserved_prec_phase": "TEXT",
                "settled_prec_phase": "TEXT",
                "reserved_input_tokens": "INTEGER DEFAULT 0",
                "reserved_output_tokens": "INTEGER DEFAULT 0",
                "reserved_latency_ms": "INTEGER DEFAULT 0",
                "reserved_cost_usd": "REAL",
                "actual_input_tokens": "INTEGER DEFAULT 0",
                "actual_output_tokens": "INTEGER DEFAULT 0",
                "actual_latency_ms": "REAL DEFAULT 0",
                "actual_cost_usd": "REAL",
                "refunded_input_tokens": "INTEGER DEFAULT 0",
                "refunded_output_tokens": "INTEGER DEFAULT 0",
                "refunded_latency_ms": "REAL DEFAULT 0",
                "refunded_cost_usd": "REAL",
                "recovery_overhead_tokens": "INTEGER DEFAULT 0",
                "recovery_overhead_cost_usd": "REAL",
                "verified_delivery": "INTEGER DEFAULT 0",
                "emergency_claim": "INTEGER DEFAULT 0",
                "approved_by": "TEXT",
                "updated_at": "TEXT",
            }.items():
                self._ensure_column(conn, "compute_escrows", column, kind)
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, kind: str) -> None:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    def _table_count(self, conn: sqlite3.Connection, table: str) -> int:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.Error:
            return 0

    def _rows(self, table: str, limit: int = 500, order: str = "created_at") -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        with self._connect() as conn:
            try:
                rows = conn.execute(f"SELECT * FROM {table} ORDER BY {order} DESC LIMIT ?", (limit,)).fetchall()
            except sqlite3.Error:
                return []
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payload = item.pop("payload", None)
            if payload:
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        parsed.update({k: v for k, v in item.items() if k not in parsed and v is not None})
                        out.append(parsed)
                        continue
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            return {
                "beast_object_type": "compute_ledger_state",
                "version": "1.0",
                "db_path": str(self.db_path),
                "plans": self._table_count(conn, "compute_plans"),
                "gates": self._table_count(conn, "compute_gates"),
                "receipts": self._table_count(conn, "compute_receipts"),
                "counterfactuals": self._table_count(conn, "counterfactual_crystals"),
                "escrows": self._table_count(conn, "compute_escrows"),
                "initialized": True,
                "mode": "shadow",
                "modes": {"shadow": self._table_count(conn, "compute_plans")},
                "enforcing": False,
            }

    def get_state(self) -> Dict[str, Any]:
        return self.state()

    def record_plan(self, plan: Any) -> Dict[str, Any]:
        data = _payload(plan)
        plan_id = str(data.get("plan_id") or "cplan_" + uuid.uuid4().hex[:20])
        created_at = str(data.get("created_at") or _utcnow())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compute_plans (
                    plan_id, request_fingerprint, provider, model, task_class, mode,
                    estimated_input_tokens, requested_output_tokens, created_at, payload, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    data.get("request_fingerprint"),
                    data.get("provider"),
                    data.get("model"),
                    data.get("task_class"),
                    data.get("mode"),
                    int(data.get("estimated_input_tokens") or 0),
                    int(data.get("requested_output_tokens") or 0),
                    created_at,
                    _json(data),
                    _json(data),
                ),
            )
            conn.commit()
        return data

    def record_gate(self, gate: Any) -> Dict[str, Any]:
        data = _payload(gate)
        gate_id = str(data.get("gate_id") or "cgate_" + uuid.uuid4().hex[:20])
        created_at = str(data.get("created_at") or _utcnow())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compute_gates (
                    gate_id, plan_id, mode, decision, candidate_decision, enforced,
                    confidence, selected_rung, recommended_rung, created_at, payload, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gate_id,
                    data.get("plan_id"),
                    data.get("mode"),
                    data.get("decision"),
                    data.get("candidate_decision"),
                    int(bool(data.get("enforced"))),
                    float(data.get("confidence") or 0.0),
                    data.get("selected_rung"),
                    data.get("recommended_rung"),
                    created_at,
                    _json(data),
                    _json(data),
                ),
            )
            conn.commit()
        return data

    def record_receipt(self, receipt: Any) -> Dict[str, Any]:
        data = _payload(receipt)
        receipt_id = str(data.get("receipt_id") or "crec_" + uuid.uuid4().hex[:20])
        created_at = str(data.get("created_at") or _utcnow())
        behavior = data.get("behavior_preserved")
        behavior_value = None if behavior is None else int(bool(behavior))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compute_receipts (
                    receipt_id, plan_id, gate_id, runtime_attempt_id, mode, provider, model,
                    status, provider_execution_requested, selected_rung, recommended_rung,
                    input_tokens, output_tokens, total_tokens, latency_ms, cost_usd,
                    early_stopped, stream_tokens_saved, predicted_savings_usd,
                    avoided_tokens_estimate, cost_observation_available, gate_decision,
                    candidate_decision, suppression_enforced, behavior_preserved,
                    created_at, payload, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    data.get("plan_id"),
                    data.get("gate_id"),
                    data.get("runtime_attempt_id"),
                    data.get("mode"),
                    data.get("provider"),
                    data.get("model"),
                    data.get("status"),
                    int(bool(data.get("provider_execution_requested", True))),
                    data.get("selected_rung"),
                    data.get("recommended_rung"),
                    int(data.get("input_tokens") or 0),
                    int(data.get("output_tokens") or 0),
                    int(data.get("total_tokens") or 0),
                    float(data.get("latency_ms") or 0.0),
                    _optional_float(data.get("cost_usd")),
                    int(bool(data.get("early_stopped"))),
                    int(data.get("stream_tokens_saved") or 0),
                    _optional_float(data.get("predicted_savings_usd")),
                    int(data.get("avoided_tokens_estimate") or 0),
                    int(bool(data.get("cost_observation_available"))),
                    data.get("gate_decision"),
                    data.get("candidate_decision"),
                    int(bool(data.get("suppression_enforced"))),
                    behavior_value,
                    created_at,
                    _json(data),
                    _json(data),
                ),
            )
            conn.commit()
        return data

    def recent_plans(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self._rows("compute_plans", limit)

    def recent_receipts(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self._rows("compute_receipts", limit)

    def receipt(self, receipt_id: str) -> Dict[str, Any]:
        wanted = str(receipt_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM compute_receipts WHERE receipt_id = ?", (wanted,)).fetchone()
        if row is None:
            raise ValueError(f"receipt not found: {wanted}")
        item = dict(row)
        payload = item.get("payload")
        if payload:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    parsed.update({k: v for k, v in item.items() if k not in parsed and v is not None})
                    return parsed
            except json.JSONDecodeError:
                pass
        return item

    def metrics(self, limit: int = 500) -> Dict[str, Any]:
        receipts = self.recent_receipts(limit)
        plans = self.recent_plans(limit)
        sample_size = len(receipts)
        observed_total = sum(int(r.get("total_tokens") or 0) for r in receipts)
        avoidable_total = sum(int(r.get("avoided_tokens_estimate") or 0) for r in receipts)
        observed_cost_values = [_optional_float(r.get("cost_usd")) for r in receipts]
        observed_costs = [v for v in observed_cost_values if v is not None]
        predicted_savings_values = [_optional_float(r.get("predicted_savings_usd")) for r in receipts]
        predicted_savings = [v for v in predicted_savings_values if v is not None]
        enforced_suppression = [r for r in receipts if bool(r.get("suppression_enforced"))]
        false_suppression = [r for r in enforced_suppression if r.get("behavior_preserved") is False or r.get("behavior_preserved") == 0]
        stream_actions: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        for row in receipts:
            statuses[str(row.get("status") or "unknown")] = statuses.get(str(row.get("status") or "unknown"), 0) + 1
            action = str(row.get("stream_repair_action") or "")
            if action:
                stream_actions[action] = stream_actions.get(action, 0) + 1
        cost_coverage = len(observed_costs) / sample_size if sample_size else 0.0
        false_rate = len(false_suppression) / len(enforced_suppression) if enforced_suppression else 0.0
        calibration = [r for r in receipts if r.get("observed_avoidable_tokens") not in (None, "")]
        calibration_errors = [
            abs(int(r.get("avoidable_token_estimation_error") or 0))
            for r in calibration
            if r.get("avoidable_token_estimation_error") not in (None, "")
        ]
        deterministic_attempts = sum(int(r.get("deterministic_shadow_attempts") or 0) for r in receipts)
        deterministic_verified = sum(int(r.get("deterministic_shadow_verified") or 0) for r in receipts)
        deterministic_calibrated = sum(int(r.get("deterministic_shadow_calibrated") or 0) for r in receipts)
        deterministic_agreements = sum(int(r.get("deterministic_shadow_agreements") or 0) for r in receipts)
        return {
            "beast_object_type": "compute_ledger_metrics",
            "version": "1.0",
            "claim_boundary": "Shadow estimates and measured receipts describe local counterfactual compute; they are not production savings until cost and volume are observed.",
            "sample_size": sample_size,
            "plan_count": len(plans),
            "recent_plans": plans[:25],
            "observed_total_tokens": observed_total,
            "estimated_avoidable_total_tokens": avoidable_total,
            "observed_cost_usd": round(sum(observed_costs), 9) if observed_costs else None,
            "predicted_savings_usd": round(sum(predicted_savings), 9) if predicted_savings else None,
            "predicted_savings_usd_observed": round(sum(predicted_savings), 9) if predicted_savings else None,
            "cost_coverage_rate": round(cost_coverage, 6),
            "token_calibration_count": len(calibration),
            "token_calibration_coverage_rate": round(len(calibration) / sample_size, 6) if sample_size else 0.0,
            "avoidable_token_mean_absolute_error": round(sum(calibration_errors) / len(calibration_errors), 6) if calibration_errors else 0.0,
            "deterministic_shadow_attempts": deterministic_attempts,
            "deterministic_shadow_verified": deterministic_verified,
            "deterministic_shadow_calibrated": deterministic_calibrated,
            "deterministic_shadow_agreements": deterministic_agreements,
            "deterministic_shadow_verification_rate": round(deterministic_verified / deterministic_attempts, 6) if deterministic_attempts else 0.0,
            "deterministic_shadow_agreement_rate": round(deterministic_agreements / deterministic_calibrated, 6) if deterministic_calibrated else 0.0,
            "stream_tokens_saved": sum(int(r.get("stream_tokens_saved") or 0) for r in receipts),
            "stream_early_stop_count": sum(1 for r in receipts if bool(r.get("early_stopped"))),
            "stream_upstream_cancellation_count": sum(1 for r in receipts if bool(r.get("upstream_cancel_requested"))),
            "stream_repair_actions": stream_actions,
            "statuses": statuses,
            "enforced_suppression_count": len(enforced_suppression),
            "false_suppression_count": len(false_suppression),
            "false_suppression_rate": round(false_rate, 6),
            "false_suppression_redline": bool(false_suppression),
            "enforcement_pause_required": bool(false_suppression),
        }

    def savings_summary(self, limit: int = 2000, weekly_call_volume: Optional[int] = None) -> Dict[str, Any]:
        metrics = self.metrics(limit)
        sample = int(metrics.get("sample_size") or 0)
        weekly = int(weekly_call_volume) if weekly_call_volume is not None else sample
        avg_avoidable = int(metrics.get("estimated_avoidable_total_tokens") or 0) / max(1, sample)
        avg_savings = _optional_float(metrics.get("predicted_savings_usd"))
        avg_savings = avg_savings / sample if avg_savings is not None and sample else None
        potential_tokens = int(avg_avoidable * max(0, weekly))
        return {
            "beast_object_type": "compute_savings_summary",
            "version": "1.0",
            "sample_size": sample,
            "weekly_call_volume": max(0, weekly),
            "potential_weekly_avoided_tokens": potential_tokens,
            "potential_weekly_savings_usd": round(avg_savings * max(0, weekly), 9) if avg_savings is not None else None,
            "cost_coverage_rate": metrics.get("cost_coverage_rate", 0.0),
            "availability": "available" if avg_savings is not None else "first-party cost observations unavailable",
            "claim_boundary": "Savings are counterfactual unless first-party cost observations and production volume are present.",
        }

    def record_counterfactual_crystals(self, plan: Any, economist_decision: Any) -> List[CounterfactualCrystal]:
        plan_data = _payload(plan)
        if isinstance(economist_decision, dict):
            candidates = economist_decision.get("ranked") or economist_decision.get("ranked_candidates") or economist_decision.get("candidates") or []
            selected = economist_decision.get("selected") if isinstance(economist_decision.get("selected"), dict) else {}
            selected_score = float(selected.get("economist_score") or selected.get("score") or 0.0)
        else:
            candidates = getattr(economist_decision, "ranked_candidates", None) or getattr(economist_decision, "candidates", None) or []
            selected_score = float(getattr(economist_decision, "selected_score", 0.0) or 0.0)
        if isinstance(candidates, dict):
            candidates = list(candidates.values())
        crystals: List[CounterfactualCrystal] = []
        for index, candidate in enumerate(candidates[1:4], start=1):
            data = _payload(candidate)
            crystal = CounterfactualCrystal(
                crystal_id="cf_" + uuid.uuid4().hex[:20],
                plan_id=str(plan_data.get("plan_id") or ""),
                task_class=str(plan_data.get("task_class") or ""),
                selected_provider=str(plan_data.get("provider") or ""),
                selected_model=str(plan_data.get("model") or ""),
                alternative_provider=str(data.get("provider") or data.get("provider_id") or ""),
                alternative_model=str(data.get("model") or ""),
                alternative_rank=index,
                selected_score=selected_score,
                alternative_score=float(data.get("score") or data.get("fitness_score") or 0.0),
                predicted_failure_class=str(data.get("failure_class") or ""),
                predicted_cost_usd=_optional_float(data.get("cost_usd")),
                predicted_latency_ms=_optional_float(data.get("latency_ms")),
                predicted_confidence=float(data.get("confidence") or 0.0),
                rejection_reason=str(data.get("rejection_reason") or "ranked_below_selected"),
                state="advisory",
                created_at=_utcnow(),
            )
            crystals.append(crystal)
            self._record_counterfactual(crystal.to_dict())
        return crystals

    def _record_counterfactual(self, data: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO counterfactual_crystals (
                    crystal_id, plan_id, task_class, selected_provider,
                    alternative_provider, state, resolution_outcome,
                    resolution_receipt_id, created_at, resolved_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("crystal_id"),
                    data.get("plan_id"),
                    data.get("task_class"),
                    data.get("selected_provider"),
                    data.get("alternative_provider"),
                    data.get("state"),
                    data.get("resolution_outcome"),
                    data.get("resolution_receipt_id"),
                    data.get("created_at"),
                    data.get("resolved_at"),
                    _json(data),
                ),
            )
            conn.commit()

    def recent_counterfactuals(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self._rows("counterfactual_crystals", limit)

    def counterfactual_summary(self, limit: int = 2000) -> Dict[str, Any]:
        rows = self.recent_counterfactuals(limit)
        states: Dict[str, int] = {}
        for row in rows:
            state = str(row.get("state") or "unknown")
            states[state] = states.get(state, 0) + 1
        return {
            "beast_object_type": "counterfactual_crystal_summary",
            "version": "1.0",
            "total": len(rows),
            "resolved": sum(1 for row in rows if row.get("resolved_at")),
            "states": states,
        }

    def resolve_counterfactuals(
        self,
        *,
        task_class: str,
        provider: str,
        model: str = "",
        receipt_id: str,
        outcome: str,
    ) -> Dict[str, Any]:
        now = _utcnow()
        rows = self.recent_counterfactuals(5000)
        matched = [
            row for row in rows
            if str(row.get("task_class") or "") == str(task_class)
            and str(row.get("alternative_provider") or "") == str(provider)
            and not row.get("resolved_at")
        ]
        with self._connect() as conn:
            for row in matched:
                row["state"] = "resolved"
                row["resolution_outcome"] = str(outcome)
                row["resolution_receipt_id"] = str(receipt_id)
                row["resolved_at"] = now
                conn.execute(
                    """
                    UPDATE counterfactual_crystals
                    SET state = ?, resolution_outcome = ?, resolution_receipt_id = ?, resolved_at = ?, payload = ?
                    WHERE crystal_id = ?
                    """,
                    ("resolved", str(outcome), str(receipt_id), now, _json(row), row.get("crystal_id")),
                )
            conn.commit()
        return {"resolved": len(matched), "outcome": str(outcome)}

    def reserve_escrow(
        self,
        plan: Any,
        *,
        estimated_cost_usd: Optional[float] = None,
        emergency_claim: bool = False,
        approved_by: str = "",
        prec_phase: str = "execute",
    ) -> ComputeEscrowRecord:
        data = _payload(plan)
        now = _utcnow()
        escrow = ComputeEscrowRecord(
            escrow_id="cesc_" + uuid.uuid4().hex[:20],
            plan_id=str(data.get("plan_id") or ""),
            task_class=str(data.get("task_class") or ""),
            provider=str(data.get("provider") or ""),
            model=str(data.get("model") or ""),
            status="reserved",
            reserved_prec_phase=str(prec_phase or "execute"),
            reserved_input_tokens=int(data.get("estimated_input_tokens") or 0),
            reserved_output_tokens=int(data.get("requested_output_tokens") or 0),
            reserved_latency_ms=int((data.get("budgets") or {}).get("latency_ms") or 0) if isinstance(data.get("budgets"), dict) else 0,
            reserved_cost_usd=estimated_cost_usd,
            emergency_claim=bool(emergency_claim),
            approved_by=str(approved_by or ""),
            created_at=now,
            updated_at=now,
        )
        self._record_escrow(escrow.to_dict())
        return escrow

    def _record_escrow(self, data: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compute_escrows (
                    escrow_id, plan_id, task_class, provider, model, status,
                    reserved_prec_phase, settled_prec_phase, reserved_input_tokens,
                    reserved_output_tokens, reserved_latency_ms, reserved_cost_usd,
                    actual_input_tokens, actual_output_tokens, actual_latency_ms,
                    actual_cost_usd, refunded_input_tokens, refunded_output_tokens,
                    refunded_latency_ms, refunded_cost_usd, recovery_overhead_tokens,
                    recovery_overhead_cost_usd, verified_delivery, emergency_claim,
                    approved_by, created_at, updated_at, payload, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("escrow_id"),
                    data.get("plan_id"),
                    data.get("task_class"),
                    data.get("provider"),
                    data.get("model"),
                    data.get("status"),
                    data.get("reserved_prec_phase"),
                    data.get("settled_prec_phase"),
                    int(data.get("reserved_input_tokens") or 0),
                    int(data.get("reserved_output_tokens") or 0),
                    int(data.get("reserved_latency_ms") or 0),
                    _optional_float(data.get("reserved_cost_usd")),
                    int(data.get("actual_input_tokens") or 0),
                    int(data.get("actual_output_tokens") or 0),
                    float(data.get("actual_latency_ms") or 0.0),
                    _optional_float(data.get("actual_cost_usd")),
                    int(data.get("refunded_input_tokens") or 0),
                    int(data.get("refunded_output_tokens") or 0),
                    float(data.get("refunded_latency_ms") or 0.0),
                    _optional_float(data.get("refunded_cost_usd")),
                    int(data.get("recovery_overhead_tokens") or 0),
                    _optional_float(data.get("recovery_overhead_cost_usd")),
                    int(bool(data.get("verified_delivery"))),
                    int(bool(data.get("emergency_claim"))),
                    data.get("approved_by"),
                    data.get("created_at"),
                    data.get("updated_at"),
                    _json(data),
                    _json(data),
                ),
            )
            conn.commit()

    def settle_escrow(
        self,
        plan_id: str,
        receipt: Any,
        *,
        verified_delivery: bool,
        recovery_overhead_tokens: int = 0,
        recovery_overhead_cost_usd: Optional[float] = None,
        prec_phase: str = "execute",
    ) -> Dict[str, Any]:
        receipt_data = _payload(receipt)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM compute_escrows WHERE plan_id = ? ORDER BY created_at DESC LIMIT 1",
                (str(plan_id),),
            ).fetchone()
        if row is None:
            return {"settled": False, "reason": "escrow_not_found"}
        data = dict(row)
        payload = data.get("payload")
        if payload:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                pass
        reserved_cost = _optional_float(data.get("reserved_cost_usd"))
        actual_cost = _optional_float(receipt_data.get("cost_usd"))
        refunded_cost = None
        if reserved_cost is not None and actual_cost is not None:
            refunded_cost = round(max(0.0, reserved_cost - actual_cost), 9)
        data.update({
            "status": "settled_verified" if verified_delivery else "settled_unverified",
            "settled_prec_phase": str(prec_phase or "execute"),
            "actual_input_tokens": int(receipt_data.get("input_tokens") or 0),
            "actual_output_tokens": int(receipt_data.get("output_tokens") or 0),
            "actual_latency_ms": float(receipt_data.get("latency_ms") or 0.0),
            "actual_cost_usd": actual_cost,
            "refunded_input_tokens": max(0, int(data.get("reserved_input_tokens") or 0) - int(receipt_data.get("input_tokens") or 0)),
            "refunded_output_tokens": max(0, int(data.get("reserved_output_tokens") or 0) - int(receipt_data.get("output_tokens") or 0)),
            "refunded_cost_usd": refunded_cost,
            "recovery_overhead_tokens": int(recovery_overhead_tokens or 0),
            "recovery_overhead_cost_usd": recovery_overhead_cost_usd,
            "verified_delivery": bool(verified_delivery),
            "updated_at": _utcnow(),
        })
        self._record_escrow(data)
        return {"settled": True, "escrow_id": data.get("escrow_id")}

    def escrow_for_plan(self, plan_id: str) -> ComputeEscrowRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM compute_escrows WHERE plan_id = ? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                (str(plan_id),),
            ).fetchone()
        if row is None:
            raise ValueError(f"escrow not found for plan: {plan_id}")
        data = dict(row)
        payload = data.get("payload")
        if payload:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                pass
        fields = ComputeEscrowRecord.__dataclass_fields__.keys()
        return ComputeEscrowRecord(**{key: data.get(key) for key in fields})

    def recent_escrows(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self._rows("compute_escrows", limit, order="updated_at")

    def escrow_summary(self, limit: int = 2000) -> Dict[str, Any]:
        rows = self.recent_escrows(limit)
        settled = sum(1 for row in rows if str(row.get("status") or "").startswith("settled"))
        verified = sum(1 for row in rows if bool(row.get("verified_delivery")))
        settled_prec_phases: Dict[str, int] = {}
        for row in rows:
            if str(row.get("status") or "").startswith("settled"):
                phase = str(row.get("settled_prec_phase") or "unknown")
                settled_prec_phases[phase] = settled_prec_phases.get(phase, 0) + 1
        return {
            "beast_object_type": "compute_escrow_summary",
            "version": "1.0",
            "total": len(rows),
            "reserved": sum(1 for row in rows if row.get("status") == "reserved"),
            "settled": settled,
            "verified_delivery": verified,
            "verified_delivery_rate": round(verified / settled, 6) if settled else 0.0,
            "settled_prec_phases": settled_prec_phases,
            "refunded_input_tokens": sum(int(row.get("refunded_input_tokens") or 0) for row in rows),
            "refunded_output_tokens": sum(int(row.get("refunded_output_tokens") or 0) for row in rows),
            "recovery_overhead_tokens": sum(int(row.get("recovery_overhead_tokens") or 0) for row in rows),
        }
