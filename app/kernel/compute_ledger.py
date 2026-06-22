"""SQLite ledger for shadow compute plans, gates, and receipts."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.compute_ir import (
    ComputeEscrowRecord,
    ComputeGateDecision,
    ComputePlan,
    ComputeReceipt,
    CounterfactualCrystal,
)


class ComputeLedger:
    def __init__(self, db_path: Optional[str] = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.db_path = Path(db_path) if db_path else root / "data" / "compute_ledger.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS compute_plans (
                    plan_id TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL, provider TEXT NOT NULL,
                    model TEXT NOT NULL, task_class TEXT NOT NULL, mode TEXT NOT NULL,
                    estimated_input_tokens INTEGER NOT NULL, requested_output_tokens INTEGER NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS compute_gates (
                    gate_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, decision TEXT NOT NULL,
                    selected_rung TEXT NOT NULL, recommended_rung TEXT NOT NULL, enforced INTEGER NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS compute_receipts (
                    receipt_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    runtime_attempt_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
                    status TEXT NOT NULL, total_tokens INTEGER NOT NULL, latency_ms REAL NOT NULL,
                    cost_usd REAL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS counterfactual_crystals (
                    crystal_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, task_class TEXT NOT NULL,
                    selected_provider TEXT NOT NULL, alternative_provider TEXT NOT NULL,
                    state TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS compute_escrows (
                    escrow_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, task_class TEXT NOT NULL,
                    provider TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_compute_plans_fingerprint ON compute_plans(request_fingerprint);
                CREATE INDEX IF NOT EXISTS idx_compute_receipts_provider ON compute_receipts(provider);
                CREATE INDEX IF NOT EXISTS idx_compute_receipts_plan ON compute_receipts(plan_id);
                CREATE INDEX IF NOT EXISTS idx_counterfactual_route ON counterfactual_crystals(task_class, alternative_provider, state);
                CREATE INDEX IF NOT EXISTS idx_compute_escrows_plan ON compute_escrows(plan_id);
            """)

    def record_plan(self, plan: ComputePlan) -> None:
        payload = plan.to_dict()
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO compute_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                plan.plan_id, plan.request_fingerprint, plan.provider, plan.model, plan.task_class, plan.mode,
                plan.estimated_input_tokens, plan.requested_output_tokens,
                json.dumps(payload, sort_keys=True), plan.created_at,
            ))

    def record_gate(self, gate: ComputeGateDecision) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO compute_gates VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                gate.gate_id, gate.plan_id, gate.decision, gate.selected_rung, gate.recommended_rung,
                int(gate.enforced), json.dumps(gate.to_dict(), sort_keys=True), gate.created_at,
            ))

    def record_receipt(self, receipt: ComputeReceipt) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO compute_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                receipt.receipt_id, receipt.plan_id, receipt.gate_id, receipt.runtime_attempt_id,
                receipt.provider, receipt.model, receipt.status, receipt.total_tokens,
                receipt.latency_ms, receipt.cost_usd, json.dumps(receipt.to_dict(), sort_keys=True), receipt.created_at,
            ))

    def record_counterfactual_crystals(
        self,
        plan: ComputePlan,
        decision: Optional[Dict[str, Any]],
        *,
        limit: int = 3,
    ) -> List[CounterfactualCrystal]:
        if not isinstance(decision, dict):
            return []
        selected = decision.get("selected") if isinstance(decision.get("selected"), dict) else {}
        selected_provider = str(selected.get("provider") or plan.provider)
        selected_model = str(selected.get("model") or plan.model)
        created_at = self._now()
        raw = decision.get("counterfactual_crystals")
        if not isinstance(raw, list):
            raw = []
        crystals: List[CounterfactualCrystal] = []
        for index, item in enumerate(raw[: max(0, int(limit))], start=1):
            if not isinstance(item, dict):
                continue
            alternative_provider = str(item.get("alternative_provider") or item.get("provider") or "")
            if not alternative_provider:
                continue
            payload = CounterfactualCrystal(
                crystal_id=str(item.get("crystal_id") or f"cf_{uuid.uuid4().hex[:20]}"),
                plan_id=plan.plan_id,
                task_class=str(item.get("task_class") or plan.task_class),
                selected_provider=str(item.get("selected_provider") or selected_provider),
                selected_model=str(item.get("selected_model") or selected_model),
                alternative_provider=alternative_provider,
                alternative_model=str(item.get("alternative_model") or item.get("model") or ""),
                alternative_rank=int(item.get("alternative_rank") or index),
                selected_score=float(item.get("selected_score") or selected.get("economist_score") or 0.0),
                alternative_score=float(item.get("alternative_score") or item.get("economist_score") or 0.0),
                predicted_failure_class=str(item.get("predicted_failure_class") or "unknown"),
                predicted_cost_usd=self._optional_float(item.get("predicted_cost_usd")),
                predicted_latency_ms=self._optional_float(item.get("predicted_latency_ms")),
                predicted_confidence=float(item.get("predicted_confidence") or 0.0),
                rejection_reason=str(item.get("rejection_reason") or ""),
                state=str(item.get("state") or "speculative"),
                created_at=str(item.get("created_at") or created_at),
            )
            crystals.append(payload)
        with self._connect() as conn:
            for crystal in crystals:
                conn.execute(
                    "INSERT OR REPLACE INTO counterfactual_crystals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        crystal.crystal_id,
                        crystal.plan_id,
                        crystal.task_class,
                        crystal.selected_provider,
                        crystal.alternative_provider,
                        crystal.state,
                        json.dumps(crystal.to_dict(), sort_keys=True),
                        crystal.created_at,
                        crystal.resolved_at or None,
                    ),
                )
        return crystals

    def resolve_counterfactuals(
        self,
        *,
        task_class: str,
        provider: str,
        model: str = "",
        outcome: str,
        receipt_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        now = self._now()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM counterfactual_crystals
                WHERE task_class = ? AND alternative_provider = ? AND state IN ('speculative', 'advisory')
                ORDER BY created_at DESC LIMIT ?
                """,
                (task_class, provider, max(1, min(int(limit), 100))),
            ).fetchall()
            resolved = []
            for row in rows:
                payload = json.loads(row[0])
                payload["state"] = "resolved"
                payload["resolution_outcome"] = outcome
                payload["resolution_receipt_id"] = receipt_id
                payload["resolved_at"] = now
                conn.execute(
                    """
                    UPDATE counterfactual_crystals
                    SET state = ?, payload_json = ?, resolved_at = ?
                    WHERE crystal_id = ?
                    """,
                    ("resolved", json.dumps(payload, sort_keys=True), now, payload["crystal_id"]),
                )
                resolved.append(payload)
        return resolved

    def recent_counterfactuals(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._recent("counterfactual_crystals", "payload_json", limit)

    def counterfactual_summary(self, limit: int = 500) -> Dict[str, Any]:
        rows = self.recent_counterfactuals(limit)
        states: Dict[str, int] = {}
        failure_classes: Dict[str, int] = {}
        for row in rows:
            states[str(row.get("state") or "unknown")] = states.get(str(row.get("state") or "unknown"), 0) + 1
            failure = str(row.get("predicted_failure_class") or "unknown")
            failure_classes[failure] = failure_classes.get(failure, 0) + 1
        resolved = [row for row in rows if row.get("state") == "resolved"]
        correct = [
            row for row in resolved
            if self._resolution_matches_prediction(
                str(row.get("predicted_failure_class") or ""),
                str(row.get("resolution_outcome") or ""),
            )
        ]
        return {
            "beast_object_type": "counterfactual_crystal_summary",
            "version": "1.0",
            "sample_size": len(rows),
            "states": states,
            "predicted_failure_classes": failure_classes,
            "resolved": len(resolved),
            "calibrated_match_rate": round(len(correct) / len(resolved), 6) if resolved else None,
            "promotion_eligible": bool(len(resolved) >= 5 and len(correct) / len(resolved) >= 0.8) if resolved else False,
            "claim_boundary": "Counterfactual crystals are advisory until later traffic resolves the rejected route.",
        }

    def reserve_escrow(
        self,
        plan: ComputePlan,
        *,
        estimated_cost_usd: Optional[float] = None,
        emergency_claim: bool = False,
        approved_by: str = "",
        prec_phase: str = "execute",
    ) -> ComputeEscrowRecord:
        now = self._now()
        status = "emergency_claim" if emergency_claim else "reserved"
        reserved_cost = estimated_cost_usd if estimated_cost_usd is not None else plan.budgets.cost_usd
        record = ComputeEscrowRecord(
            escrow_id="escrow_" + uuid.uuid4().hex[:20],
            plan_id=plan.plan_id,
            task_class=plan.task_class,
            provider=plan.provider,
            model=plan.model,
            status=status,
            reserved_prec_phase=str(prec_phase or "execute")[:80],
            reserved_cloud_calls=max(0, int(plan.budgets.cloud_calls or 0)),
            reserved_input_tokens=max(0, int(plan.estimated_input_tokens or plan.budgets.input_tokens or 0)),
            reserved_output_tokens=max(0, int(plan.requested_output_tokens or plan.budgets.output_tokens or 0)),
            reserved_latency_ms=max(0, int(plan.budgets.latency_ms or 0)),
            reserved_cost_usd=reserved_cost,
            emergency_claim=emergency_claim,
            approved_by=approved_by[:120],
            created_at=now,
            updated_at=now,
        )
        self._record_escrow(record)
        return record

    def settle_escrow(
        self,
        plan_id: str,
        receipt: ComputeReceipt,
        *,
        verified_delivery: bool,
        recovery_overhead_tokens: int = 0,
        recovery_overhead_cost_usd: Optional[float] = None,
        prec_phase: str = "crystallize",
    ) -> Optional[ComputeEscrowRecord]:
        current = self.escrow_for_plan(plan_id)
        if not current:
            return None
        now = self._now()
        reserved_cost = current.reserved_cost_usd
        actual_cost = receipt.cost_usd
        refunded_cost = None
        if reserved_cost is not None and actual_cost is not None:
            refunded_cost = max(0.0, reserved_cost - actual_cost)
        status = "settled_verified" if verified_delivery else "settled_unverified"
        settled = replace(
            current,
            status=status,
            settled_prec_phase=str(prec_phase or "crystallize")[:80],
            actual_cloud_calls=1 if receipt.provider_execution_requested else 0,
            actual_input_tokens=receipt.input_tokens,
            actual_output_tokens=receipt.output_tokens,
            actual_latency_ms=receipt.latency_ms,
            actual_cost_usd=actual_cost,
            refunded_input_tokens=max(0, current.reserved_input_tokens - receipt.input_tokens),
            refunded_output_tokens=max(0, current.reserved_output_tokens - receipt.output_tokens),
            refunded_latency_ms=max(0.0, float(current.reserved_latency_ms) - receipt.latency_ms),
            refunded_cost_usd=round(refunded_cost, 9) if refunded_cost is not None else None,
            recovery_overhead_tokens=max(0, int(recovery_overhead_tokens)),
            recovery_overhead_cost_usd=recovery_overhead_cost_usd,
            verified_delivery=verified_delivery,
            updated_at=now,
        )
        self._record_escrow(settled)
        return settled

    def escrow_for_plan(self, plan_id: str) -> Optional[ComputeEscrowRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM compute_escrows WHERE plan_id = ? ORDER BY created_at DESC LIMIT 1",
                (plan_id,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        allowed = {field: payload.get(field) for field in ComputeEscrowRecord.__dataclass_fields__}
        return ComputeEscrowRecord(**allowed)

    def recent_escrows(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._recent("compute_escrows", "payload_json", limit)

    def escrow_summary(self, limit: int = 500) -> Dict[str, Any]:
        rows = self.recent_escrows(limit)
        statuses: Dict[str, int] = {}
        settled_prec_phases: Dict[str, int] = {}
        for row in rows:
            statuses[str(row.get("status") or "unknown")] = statuses.get(str(row.get("status") or "unknown"), 0) + 1
            phase = str(row.get("settled_prec_phase") or "")
            if phase:
                settled_prec_phases[phase] = settled_prec_phases.get(phase, 0) + 1
        settled = [row for row in rows if str(row.get("status") or "").startswith("settled")]
        verified = [row for row in settled if row.get("verified_delivery") is True]
        reserved_costs = [float(row["reserved_cost_usd"]) for row in rows if row.get("reserved_cost_usd") is not None]
        actual_costs = [float(row["actual_cost_usd"]) for row in settled if row.get("actual_cost_usd") is not None]
        refunds = [float(row["refunded_cost_usd"]) for row in settled if row.get("refunded_cost_usd") is not None]
        return {
            "beast_object_type": "compute_escrow_summary",
            "version": "1.0",
            "sample_size": len(rows),
            "statuses": statuses,
            "settled_prec_phases": settled_prec_phases,
            "settled": len(settled),
            "verified_delivery_rate": round(len(verified) / len(settled), 6) if settled else None,
            "reserved_cost_usd": round(sum(reserved_costs), 9) if reserved_costs else None,
            "actual_cost_usd": round(sum(actual_costs), 9) if actual_costs else None,
            "refunded_cost_usd": round(sum(refunds), 9) if refunds else None,
            "claim_boundary": "Escrow charges verified delivery; unverified settlements remain audit evidence.",
        }

    def recent_plans(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._recent("compute_plans", "payload_json", limit)

    def recent_receipts(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._recent("compute_receipts", "payload_json", limit)

    def receipt(self, receipt_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM compute_receipts WHERE receipt_id = ?", (receipt_id,)).fetchone()
        if not row:
            raise ValueError(f"compute receipt not found: {receipt_id}")
        return json.loads(row[0])

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            counts = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("compute_plans", "compute_gates", "compute_receipts", "counterfactual_crystals", "compute_escrows")
            }
            # Derive mode distribution from recent plans
            mode_rows = conn.execute(
                "SELECT mode, COUNT(*) as cnt FROM compute_plans GROUP BY mode"
            ).fetchall()
            mode_distribution = {row["mode"]: row["cnt"] for row in mode_rows}
        enforcing = any(m in ("phase2_enforce",) for m in mode_distribution.keys())
        return {
            "beast_object_type": "compute_governor_state", "version": "1.0",
            "modes": mode_distribution or {"shadow": 0},
            "enforcing": enforcing,
            "plans": counts["compute_plans"], "gates": counts["compute_gates"],
            "receipts": counts["compute_receipts"],
            "counterfactual_crystals": counts["counterfactual_crystals"],
            "escrows": counts["compute_escrows"],
            "db_path": str(self.db_path),
        }

    def metrics(self, limit: int = 500) -> Dict[str, Any]:
        rows = self.recent_receipts(limit)
        sample_size = len(rows)
        if sample_size == 0:
            return {
                "beast_object_type": "compute_governor_metrics", "version": "1.0",
                "mode": "shadow", "sample_size": 0, "statuses": {}, "recommended_rungs": {},
                "observed_total_tokens": 0, "estimated_avoidable_input_tokens": 0,
                "estimated_avoidable_output_tokens": 0, "estimated_avoidable_total_tokens": 0,
                "predicted_savings_usd_observed": None, "observed_cost_usd": None,
                "cost_observation_count": 0, "cost_coverage_rate": 0.0,
                "enforced_suppression_count": 0, "false_suppression_count": 0,
                "false_suppression_rate": 0.0, "false_suppression_redline": False,
                "enforcement_pause_required": False, "average_latency_ms": 0.0,
                "deterministic_shadow_attempts": 0, "deterministic_shadow_verified": 0,
                "deterministic_shadow_calibrated": 0, "deterministic_shadow_agreements": 0,
                "deterministic_shadow_verification_rate": 0.0,
                "deterministic_shadow_agreement_rate": None,
                "stream_early_stop_count": 0, "stream_tokens_saved": 0,
                "stream_upstream_cancellation_count": 0, "stream_repair_actions": {},
                "token_calibration_count": 0, "token_calibration_coverage_rate": 0.0,
                "avoidable_token_mean_absolute_error": None,
                "claim_boundary": "Shadow estimates are hypotheses until verified by a behavior-preserving ablation.",
            }
        total_tokens = sum(int(item.get("total_tokens") or 0) for item in rows)
        avoidable_input = sum(int(item.get("estimated_avoidable_input_tokens") or 0) for item in rows)
        avoidable_output = sum(int(item.get("estimated_avoidable_output_tokens") or 0) for item in rows)
        savings = [float(item["predicted_savings_usd"]) for item in rows if item.get("predicted_savings_usd") is not None]
        observed_costs = [float(item["cost_usd"]) for item in rows if item.get("cost_usd") is not None]
        latencies = [float(item.get("latency_ms") or 0) for item in rows]
        statuses: Dict[str, int] = {}
        recommended: Dict[str, int] = {}
        for item in rows:
            statuses[str(item.get("status") or "unknown")] = statuses.get(str(item.get("status") or "unknown"), 0) + 1
            rung = str(item.get("recommended_rung") or "unknown")
            recommended[rung] = recommended.get(rung, 0) + 1
        suppressions = [item for item in rows if item.get("suppression_enforced") is True]
        false_suppressions = [item for item in suppressions if item.get("behavior_preserved") is False]
        false_suppression_rate = len(false_suppressions) / len(suppressions) if suppressions else 0.0
        # Cost coverage uses cost_usd presence, not predicted_savings_usd
        cost_observation_count = sum(1 for r in rows if r.get("cost_usd") is not None)
        cost_coverage_rate = cost_observation_count / sample_size if sample_size > 0 else 0.0
        shadow_attempts = sum(int(item.get("deterministic_shadow_attempts") or 0) for item in rows)
        shadow_verified = sum(int(item.get("deterministic_shadow_verified") or 0) for item in rows)
        shadow_calibrated = sum(int(item.get("deterministic_shadow_calibrated") or 0) for item in rows)
        shadow_agreements = sum(int(item.get("deterministic_shadow_agreements") or 0) for item in rows)
        calibration_errors = [
            abs(int(item["avoidable_token_estimation_error"]))
            for item in rows if item.get("avoidable_token_estimation_error") is not None
        ]
        stream_early_stops = [item for item in rows if item.get("early_stopped") is True]
        stream_repairs: Dict[str, int] = {}
        for item in rows:
            action = str(item.get("stream_repair_action") or "")
            if action:
                stream_repairs[action] = stream_repairs.get(action, 0) + 1
        return {
            "beast_object_type": "compute_governor_metrics", "version": "1.0",
            "mode": "shadow", "sample_size": len(rows), "statuses": statuses,
            "recommended_rungs": recommended, "observed_total_tokens": total_tokens,
            "estimated_avoidable_input_tokens": avoidable_input,
            "estimated_avoidable_output_tokens": avoidable_output,
            "estimated_avoidable_total_tokens": avoidable_input + avoidable_output,
            "predicted_savings_usd_observed": round(sum(savings), 9) if savings else None,
            "observed_cost_usd": round(sum(observed_costs), 9) if observed_costs else None,
            "cost_observation_count": cost_observation_count,
            "cost_coverage_rate": round(cost_coverage_rate, 6),
            "enforced_suppression_count": len(suppressions),
            "false_suppression_count": len(false_suppressions),
            "false_suppression_rate": round(false_suppression_rate, 6),
            "false_suppression_redline": bool(false_suppressions),
            "enforcement_pause_required": bool(false_suppressions),
            "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "deterministic_shadow_attempts": shadow_attempts,
            "deterministic_shadow_verified": shadow_verified,
            "deterministic_shadow_calibrated": shadow_calibrated,
            "deterministic_shadow_agreements": shadow_agreements,
            "deterministic_shadow_verification_rate": round(shadow_verified / shadow_attempts, 6) if shadow_attempts else 0.0,
            "deterministic_shadow_agreement_rate": round(shadow_agreements / shadow_calibrated, 6) if shadow_calibrated else None,
            "stream_early_stop_count": len(stream_early_stops),
            "stream_tokens_saved": sum(int(item.get("stream_tokens_saved") or 0) for item in rows),
            "stream_upstream_cancellation_count": sum(1 for item in rows if item.get("upstream_cancel_requested") is True),
            "stream_repair_actions": stream_repairs,
            "token_calibration_count": len(calibration_errors),
            "token_calibration_coverage_rate": round(len(calibration_errors) / sample_size, 6),
            "avoidable_token_mean_absolute_error": round(sum(calibration_errors) / len(calibration_errors), 3) if calibration_errors else None,
            "claim_boundary": "Shadow estimates are hypotheses until verified by a behavior-preserving ablation.",
        }

    def savings_summary(self, limit: int = 2000, weekly_call_volume: Optional[int] = None) -> Dict[str, Any]:
        rows = self.recent_receipts(limit)
        volume = weekly_call_volume
        if volume is None:
            raw = __import__("os").environ.get("BEAST_COMPUTE_WEEKLY_CALL_VOLUME", "")
            try:
                volume = int(raw) if raw else None
            except ValueError:
                volume = None
        estimates = [int(item.get("avoided_tokens_estimate") or 0) for item in rows]
        usd = [float(item["predicted_savings_usd"]) for item in rows if item.get("predicted_savings_usd") is not None]
        avg_tokens = (sum(estimates) / len(estimates)) if estimates else 0.0
        avg_usd = (sum(usd) / len(usd)) if usd else None
        weekly_tokens = round(avg_tokens * volume) if volume is not None else None
        weekly_usd = round(avg_usd * volume, 6) if avg_usd is not None and volume is not None else None
        reason = "available"
        if not rows:
            reason = "no compute receipts observed"
        elif not usd:
            reason = "first-party cost observations unavailable"
        elif volume is None:
            reason = "set BEAST_COMPUTE_WEEKLY_CALL_VOLUME or pass weekly_call_volume"
        return {
            "beast_object_type": "compute_savings_shadow_summary", "version": "1.0",
            "mode": "shadow", "sample_size": len(rows), "weekly_call_volume": volume,
            "average_avoided_tokens_estimate": round(avg_tokens, 3),
            "average_predicted_savings_usd": round(avg_usd, 9) if avg_usd is not None else None,
            "potential_weekly_avoided_tokens": weekly_tokens,
            "potential_weekly_savings_usd": weekly_usd,
            "cost_coverage_rate": round(len(usd) / len(rows), 6) if rows else 0.0,
            "availability": reason,
            "claim_boundary": "Projected values remain counterfactual until behavior-preserving ablation.",
        }

    def _recent(self, table: str, column: str, limit: int) -> List[Dict[str, Any]]:
        bounded = max(1, min(int(limit), 2000))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {column} FROM {table} ORDER BY created_at DESC LIMIT ?", (bounded,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _record_escrow(self, record: ComputeEscrowRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO compute_escrows VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.escrow_id,
                    record.plan_id,
                    record.task_class,
                    record.provider,
                    record.status,
                    json.dumps(record.to_dict(), sort_keys=True),
                    record.created_at,
                    record.updated_at,
                ),
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolution_matches_prediction(predicted: str, outcome: str) -> bool:
        predicted = predicted.lower()
        outcome = outcome.lower()
        if predicted in {"none", "clean", "low_risk"}:
            return outcome in {"success", "recovered", "completed", "succeeded"}
        if "cost" in predicted:
            return "cost" in outcome or "budget" in outcome
        if "latency" in predicted:
            return "latency" in outcome or "timeout" in outcome
        if "friction" in predicted or "repair" in predicted:
            return outcome in {"recovered", "repair", "failed", "failure"} or "repair" in outcome
        if "negative" in predicted or "failure" in predicted:
            return outcome in {"failed", "failure", "provider_error"} or "fail" in outcome
        return False
