"""Append-only PREC lifecycle state for BEAST operator work."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.storage.base_store import BaseStore

PHASES = ("perceive", "reason", "economize", "crystallize")


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PRECLifecycleStore(BaseStore):
    """Persist task, route, tool, handoff, and API PREC phase snapshots."""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__(db_path, default_db_name="prec_lifecycle.db")

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prec_lifecycles (
                    lifecycle_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_phase TEXT NOT NULL,
                    task_id TEXT,
                    provider TEXT,
                    summary TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    artifact_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prec_kind_status ON prec_lifecycles(kind, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prec_task ON prec_lifecycles(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prec_updated ON prec_lifecycles(updated_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prec_phase_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lifecycle_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    signals_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prec_events_lifecycle ON prec_phase_events(lifecycle_id, id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prec_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    lifecycle_id TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    token_estimate INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prec_snapshots_lifecycle ON prec_snapshots(lifecycle_id, created_at)")

    def start(
        self,
        *,
        kind: str,
        objective: str,
        scope: str = "",
        task_id: Optional[str] = None,
        provider: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        lifecycle_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        created_at = _utc_now()
        lifecycle_id = lifecycle_id or self._id(kind, objective, task_id, provider, created_at)
        metadata = _json_safe(metadata or {})
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO prec_lifecycles
                (lifecycle_id, kind, objective, scope, status, current_phase, task_id, provider,
                 summary, metadata_json, artifact_refs_json, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lifecycle_id,
                kind,
                objective,
                scope,
                "started",
                "perceive",
                task_id,
                provider,
                "PREC lifecycle started",
                json.dumps(metadata, sort_keys=True),
                "{}",
                created_at,
                created_at,
                None,
            ))
        return self.get(lifecycle_id) or {}

    def record_phase(
        self,
        lifecycle_id: str,
        phase: str,
        *,
        status: str = "completed",
        summary: str = "",
        artifacts: Optional[Dict[str, Any]] = None,
        signals: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if phase not in PHASES:
            raise ValueError(f"Unsupported PREC phase: {phase}")
        created_at = _utc_now()
        artifacts = _json_safe(artifacts or {})
        signals = [str(item) for item in (signals or [])]
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO prec_phase_events
                (lifecycle_id, phase, status, summary, artifacts_json, signals_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                lifecycle_id,
                phase,
                status,
                summary or f"{phase} phase {status}",
                json.dumps(artifacts, sort_keys=True),
                json.dumps(signals, sort_keys=True),
                created_at,
            ))
            current = conn.execute(
                "SELECT artifact_refs_json FROM prec_lifecycles WHERE lifecycle_id = ?",
                (lifecycle_id,),
            ).fetchone()
            refs = json.loads(current[0]) if current and current[0] else {}
            refs[phase] = self._artifact_refs(artifacts)
            conn.execute("""
                UPDATE prec_lifecycles
                SET status = ?, current_phase = ?, summary = ?, artifact_refs_json = ?, updated_at = ?
                WHERE lifecycle_id = ?
            """, (
                "running" if phase != "crystallize" else "completed",
                phase,
                summary or f"{phase} phase {status}",
                json.dumps(refs, sort_keys=True),
                created_at,
                lifecycle_id,
            ))
        return self.get(lifecycle_id) or {}

    def complete(self, lifecycle_id: str, *, summary: str = "PREC lifecycle completed") -> Dict[str, Any]:
        completed_at = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                UPDATE prec_lifecycles
                SET status = 'completed', current_phase = 'crystallize', summary = ?,
                    updated_at = ?, completed_at = ?
                WHERE lifecycle_id = ?
            """, (summary, completed_at, completed_at, lifecycle_id))
        return self.get(lifecycle_id) or {}

    def fail(self, lifecycle_id: str, *, summary: str) -> Dict[str, Any]:
        updated_at = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                UPDATE prec_lifecycles
                SET status = 'failed', summary = ?, updated_at = ?
                WHERE lifecycle_id = ?
            """, (summary, updated_at, lifecycle_id))
        return self.get(lifecycle_id) or {}

    def record_artifact_lifecycle(
        self,
        *,
        kind: str,
        payload: Optional[Dict[str, Any]] = None,
        artifacts: Optional[Dict[str, Any]] = None,
        objective: Optional[str] = None,
        scope: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        artifacts = artifacts or {}
        envelope = artifacts.get("envelope") or payload.get("envelope") or {}
        task_id = self._first(
            payload.get("task_id"),
            envelope.get("task_id"),
            (artifacts.get("diagnostic") or {}).get("task_id"),
            (artifacts.get("context_packet") or {}).get("task_id"),
            (artifacts.get("workflow") or {}).get("task_id"),
        )
        provider = provider or self._first(
            payload.get("provider"),
            (envelope.get("inputs") or {}).get("provider"),
            (artifacts.get("diagnostic") or {}).get("provider"),
        )
        objective = objective or self._objective(payload, envelope, task_id)
        scope = scope or self._first(payload.get("scope"), envelope.get("task_class"), kind) or kind
        lifecycle = self.start(
            kind=kind,
            objective=str(objective),
            scope=str(scope),
            task_id=task_id,
            provider=provider,
            metadata={"source": "artifact_lifecycle", "payload_keys": sorted(payload.keys())},
        )
        lifecycle_id = lifecycle["lifecycle_id"]

        self.record_phase(
            lifecycle_id,
            "perceive",
            summary="Perceived task shape, local signals, provider policy, and incoming artifacts.",
            artifacts={
                "envelope": self._compact_envelope(envelope),
                "provider_policy": artifacts.get("provider_policy") or {"provider": provider},
                "interception": artifacts.get("interception") or payload.get("interception"),
                "evidence_envelopes": artifacts.get("evidence_records") or payload.get("evidence_records") or [],
            },
            signals=self._signals("perceive", artifacts),
        )
        self.record_phase(
            lifecycle_id,
            "reason",
            summary="Reasoned over ranked insight, root cause, uncertainty, and safe next action.",
            artifacts={
                "insight_packet": self._compact_insight(artifacts.get("insight_packet") or payload.get("insight_packet")),
                "quality_report": self._compact_quality(artifacts.get("quality_report")),
                "forge_scorecard": self._compact_scorecard(artifacts.get("forge_scorecard")),
            },
            signals=self._signals("reason", artifacts),
        )
        self.record_phase(
            lifecycle_id,
            "economize",
            summary="Economized context into compact packets, selected chunks, route constraints, and tool sequence.",
            artifacts={
                "context_packet": self._compact_context_packet(artifacts.get("context_packet")),
                "route_card": self._compact_route(artifacts.get("route_card")),
                "recommended_tool_sequence": self._tool_sequence(artifacts),
            },
            signals=self._signals("economize", artifacts),
        )
        self.record_phase(
            lifecycle_id,
            "crystallize",
            summary="Crystallized Chronicle, route-card, capability, promotion, skill, and workflow memory.",
            artifacts={
                "chronicle": self._compact_chronicle(artifacts.get("chronicle")),
                "route_card": self._compact_route(artifacts.get("route_card")),
                "workflow": self._compact_workflow(artifacts.get("workflow")),
                "promotion_candidates": artifacts.get("promotion_candidates") or [],
                "capability_signals": artifacts.get("capability_signals") or [],
            },
            signals=self._signals("crystallize", artifacts),
        )
        return self.complete(lifecycle_id)

    def record_api_trace(
        self,
        *,
        provider_type: str,
        ir: Any,
        governance_result: Any,
        crystallize_result: Dict[str, Any],
        provider_response: Optional[Dict[str, Any]] = None,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        ir_dict = _json_safe(ir)
        governance = _json_safe(governance_result)
        trace_id = crystallize_result.get("trace_id")
        lifecycle = self.start(
            kind="api_request",
            objective=f"{provider_type} model request",
            scope="provider_api",
            task_id=trace_id,
            provider=provider_type,
            metadata={"session_id": session_id, "trace_id": trace_id},
        )
        lifecycle_id = lifecycle["lifecycle_id"]
        self.record_phase(
            lifecycle_id,
            "perceive",
            summary="Normalized provider request into EdgeK IR.",
            artifacts={"ir": self._compact_ir(ir_dict)},
            signals=["provider_request_normalized", f"provider:{provider_type}"],
        )
        self.record_phase(
            lifecycle_id,
            "reason",
            summary=f"Governance decision: {governance.get('decision', 'unknown')}.",
            artifacts={"governance_result": governance},
            signals=[f"governance:{governance.get('decision', 'unknown')}"],
        )
        self.record_phase(
            lifecycle_id,
            "economize",
            summary="Applied context economy metadata from the effective request.",
            artifacts={"context_economy": (ir_dict.get("metadata") or {}).get("context_economy", {})},
            signals=["context_economy:" + str(bool((ir_dict.get("metadata") or {}).get("context_economy", {}).get("changed", False))).lower()],
        )
        self.record_phase(
            lifecycle_id,
            "crystallize",
            summary="Crystallized provider trace, telemetry, skill, and workspace memory.",
            artifacts={
                "crystallize_result": crystallize_result,
                "provider_response_keys": sorted((provider_response or {}).keys()),
            },
            signals=["trace_archived", "telemetry_emitted"],
        )
        return self.complete(lifecycle_id)

    def list(self, *, kind: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        clauses = []
        params: List[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 200)))
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT lifecycle_id, kind, objective, scope, status, current_phase, task_id, provider,
                       summary, metadata_json, artifact_refs_json, created_at, updated_at, completed_at
                FROM prec_lifecycles
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
            """, params).fetchall()
        records = [self._row_to_record(row, include_events=False) for row in rows]
        return {
            "beast_object_type": "prec_lifecycle_index",
            "version": "1.0",
            "count": len(records),
            "lifecycles": records,
        }

    def compact_snapshot(
        self,
        lifecycle_id: str,
        *,
        max_chars: int = 6000,
        persist: bool = True,
    ) -> Dict[str, Any]:
        detail = self.get(lifecycle_id)
        if not detail:
            raise ValueError("PREC lifecycle not found")
        max_chars = max(1200, min(int(max_chars or 6000), 40000))
        phase_events = detail.get("phase_events") or []
        phase_summaries = [
            {
                "phase": event["phase"],
                "status": event["status"],
                "summary": event["summary"],
                "signals": event.get("signals", [])[:12],
                "artifact_refs": self._artifact_refs(event.get("artifacts") or {}),
            }
            for event in phase_events
        ]
        merged_artifacts = {
            event["phase"]: self._compact_for_snapshot(event.get("artifacts") or {}, max_chars=max(800, max_chars // 5))
            for event in phase_events
        }
        economize = merged_artifacts.get("economize") or {}
        reason = merged_artifacts.get("reason") or {}
        crystallize = merged_artifacts.get("crystallize") or {}
        route_card = economize.get("route_card") or crystallize.get("route_card") or {}
        context_packet = economize.get("context_packet") or {}
        insight_packet = reason.get("insight_packet") or {}
        phase_status = detail.get("phase_status") or {}
        ready_for_handoff = (
            phase_status.get("perceive") == "completed"
            and phase_status.get("reason") == "completed"
            and phase_status.get("economize") == "completed"
            and phase_status.get("crystallize") in {"completed", "planned"}
        )
        snapshot = {
            "beast_object_type": "prec_lifecycle_snapshot",
            "version": "1.0",
            "snapshot_id": "",
            "lifecycle_id": lifecycle_id,
            "kind": detail.get("kind"),
            "task_id": detail.get("task_id"),
            "provider": detail.get("provider"),
            "objective": detail.get("objective"),
            "scope": detail.get("scope"),
            "status": detail.get("status"),
            "current_phase": detail.get("current_phase"),
            "ready_for_handoff": ready_for_handoff,
            "phase_status": phase_status,
            "phase_summaries": phase_summaries,
            "ranked_insight": {
                "likely_root_cause": insight_packet.get("likely_root_cause"),
                "confidence": insight_packet.get("confidence"),
                "uncertainty": insight_packet.get("uncertainty"),
                "safest_local_next_action": insight_packet.get("safest_local_next_action"),
                "evidence_count": insight_packet.get("evidence_count"),
            },
            "context_budget": context_packet.get("context_budget") or {},
            "packet_stats": context_packet.get("packet_stats") or {},
            "route_constraints": {
                "route_id": route_card.get("route_id"),
                "preferred_order": route_card.get("preferred_order") or [],
                "avoid": route_card.get("avoid") or [],
                "promotion_status": route_card.get("promotion_status"),
            },
            "recommended_tool_sequence": economize.get("recommended_tool_sequence") or [],
            "crystallized_memory": {
                "chronicle": crystallize.get("chronicle") or {},
                "workflow": crystallize.get("workflow") or {},
                "promotion_candidates": crystallize.get("promotion_candidates") or [],
                "capability_signals": crystallize.get("capability_signals") or [],
            },
            "artifact_refs": detail.get("artifact_refs") or {},
            "compact_artifacts": merged_artifacts,
            "created_at": _utc_now(),
        }
        snapshot_payload = json.dumps(snapshot, sort_keys=True, default=str)
        snapshot_hash = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
        snapshot_id = "prec_snap_" + snapshot_hash[:18]
        snapshot["snapshot_id"] = snapshot_id
        snapshot["snapshot_hash"] = snapshot_hash
        snapshot["token_estimate"] = max(1, len(json.dumps(snapshot, sort_keys=True, default=str)) // 4)
        snapshot["compaction"] = {
            "source": "prec_phase_events",
            "max_chars": max_chars,
            "phase_event_count": len(phase_events),
            "omits_raw_payloads": True,
        }
        if persist:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO prec_snapshots
                    (snapshot_id, lifecycle_id, snapshot_hash, token_estimate, snapshot_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    snapshot_id,
                    lifecycle_id,
                    snapshot_hash,
                    snapshot["token_estimate"],
                    json.dumps(snapshot, sort_keys=True),
                    snapshot["created_at"],
                ))
        snapshot["persisted"] = bool(persist)
        return snapshot

    def list_snapshots(self, lifecycle_id: str, *, limit: int = 20) -> Dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT snapshot_id, lifecycle_id, snapshot_hash, token_estimate, snapshot_json, created_at
                FROM prec_snapshots
                WHERE lifecycle_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (lifecycle_id, max(1, min(int(limit), 100)))).fetchall()
        return {
            "beast_object_type": "prec_snapshot_index",
            "version": "1.0",
            "lifecycle_id": lifecycle_id,
            "count": len(rows),
            "snapshots": [
                {
                    "snapshot_id": row[0],
                    "lifecycle_id": row[1],
                    "snapshot_hash": row[2],
                    "token_estimate": row[3],
                    "created_at": row[5],
                    "summary": {
                        "objective": (json.loads(row[4] or "{}")).get("objective"),
                        "ready_for_handoff": (json.loads(row[4] or "{}")).get("ready_for_handoff"),
                    },
                }
                for row in rows
            ],
        }

    def get(self, lifecycle_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT lifecycle_id, kind, objective, scope, status, current_phase, task_id, provider,
                       summary, metadata_json, artifact_refs_json, created_at, updated_at, completed_at
                FROM prec_lifecycles
                WHERE lifecycle_id = ?
            """, (lifecycle_id,)).fetchone()
            if not row:
                return None
            events = conn.execute("""
                SELECT phase, status, summary, artifacts_json, signals_json, created_at
                FROM prec_phase_events
                WHERE lifecycle_id = ?
                ORDER BY id ASC
            """, (lifecycle_id,)).fetchall()
        record = self._row_to_record(row, include_events=False)
        record["phase_events"] = [
            {
                "phase": event[0],
                "status": event[1],
                "summary": event[2],
                "artifacts": json.loads(event[3] or "{}"),
                "signals": json.loads(event[4] or "[]"),
                "created_at": event[5],
            }
            for event in events
        ]
        record["phase_status"] = {
            phase: next((event["status"] for event in reversed(record["phase_events"]) if event["phase"] == phase), "missing")
            for phase in PHASES
        }
        return record

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT kind, status, COUNT(*) FROM prec_lifecycles GROUP BY kind, status").fetchall()
            recent = conn.execute("""
                SELECT lifecycle_id, kind, objective, status, current_phase, updated_at
                FROM prec_lifecycles
                ORDER BY updated_at DESC
                LIMIT 5
            """).fetchall()
        return {
            "beast_object_type": "prec_lifecycle_state",
            "version": "1.0",
            "db_path": str(self.db_path),
            "phases": list(PHASES),
            "counts": [{"kind": row[0], "status": row[1], "count": row[2]} for row in rows],
            "recent": [
                {
                    "lifecycle_id": row[0],
                    "kind": row[1],
                    "objective": row[2],
                    "status": row[3],
                    "current_phase": row[4],
                    "updated_at": row[5],
                }
                for row in recent
            ],
        }

    def _row_to_record(self, row: Any, *, include_events: bool) -> Dict[str, Any]:
        return {
            "beast_object_type": "prec_lifecycle",
            "version": "1.0",
            "lifecycle_id": row[0],
            "kind": row[1],
            "objective": row[2],
            "scope": row[3],
            "status": row[4],
            "current_phase": row[5],
            "task_id": row[6],
            "provider": row[7],
            "summary": row[8],
            "metadata": json.loads(row[9] or "{}"),
            "artifact_refs": json.loads(row[10] or "{}"),
            "created_at": row[11],
            "updated_at": row[12],
            "completed_at": row[13],
        }

    def _id(self, kind: str, objective: str, task_id: Optional[str], provider: Optional[str], created_at: str) -> str:
        stable = json.dumps({
            "kind": kind,
            "objective": objective,
            "task_id": task_id,
            "provider": provider,
            "created_at": created_at,
            "time": time.time_ns(),
        }, sort_keys=True)
        return "prec_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:18]

    def _artifact_refs(self, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        refs: Dict[str, Any] = {}
        for key, value in artifacts.items():
            if not value:
                continue
            if isinstance(value, dict):
                refs[key] = {
                    item: value.get(item)
                    for item in (
                        "task_id", "route_id", "packet_id", "workflow_id", "trace_id",
                        "scorecard_id", "evidence_id", "handoff_hash", "beast_object_type"
                    )
                    if value.get(item) is not None
                } or {"present": True}
            elif isinstance(value, list):
                refs[key] = {"count": len(value)}
            else:
                refs[key] = {"value": str(value)[:160]}
        return refs

    def _compact_envelope(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        if not envelope:
            return {}
        return {
            "beast_object_type": envelope.get("beast_object_type"),
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "inputs": envelope.get("inputs", {}),
            "constraints": envelope.get("constraints", []),
            "success_criteria": envelope.get("success_criteria", []),
            "allowed_actions": envelope.get("allowed_actions", []),
        }

    def _compact_insight(self, packet: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not packet:
            return {}
        summary = packet.get("summary") or {}
        top = summary.get("top_insight") or {}
        return {
            "beast_object_type": packet.get("beast_object_type"),
            "ready": packet.get("ready"),
            "likely_root_cause": summary.get("likely_root_cause") or top.get("summary"),
            "confidence": summary.get("confidence"),
            "uncertainty": summary.get("uncertainty"),
            "safest_local_next_action": summary.get("safest_local_next_action"),
            "evidence_count": len(packet.get("evidence") or []),
        }

    def _compact_quality(self, report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not report:
            return {}
        return {
            "beast_object_type": report.get("beast_object_type"),
            "route_id": report.get("route_id"),
            "summary": report.get("summary", {}),
            "status": report.get("status"),
        }

    def _compact_scorecard(self, scorecard: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not scorecard:
            return {}
        return {
            "beast_object_type": scorecard.get("beast_object_type"),
            "scorecard_id": scorecard.get("scorecard_id"),
            "decision": scorecard.get("decision"),
            "score": scorecard.get("score"),
            "risk": scorecard.get("risk"),
        }

    def _compact_context_packet(self, packet: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not packet:
            return {}
        return {
            "beast_object_type": packet.get("beast_object_type"),
            "packet_id": packet.get("packet_id"),
            "task_id": packet.get("task_id"),
            "handoff_hash": packet.get("handoff_hash"),
            "context_budget": packet.get("context_budget", {}),
            "packet_stats": packet.get("packet_stats", {}),
            "included_evidence_count": len(packet.get("included_evidence") or []),
            "excluded_evidence_count": len(packet.get("excluded_evidence") or []),
        }

    def _compact_route(self, route: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not route:
            return {}
        return {
            "beast_object_type": route.get("beast_object_type"),
            "route_id": route.get("route_id"),
            "task_class": route.get("task_class"),
            "preferred_order": route.get("preferred_order", []),
            "avoid": route.get("avoid", []),
            "promotion_status": route.get("promotion_status"),
        }

    def _compact_chronicle(self, chronicle: Any) -> Dict[str, Any]:
        if not chronicle:
            return {}
        if isinstance(chronicle, dict) and "record" in chronicle:
            record = chronicle.get("record") or {}
            return {
                "written": chronicle.get("written"),
                "task_id": record.get("task_id"),
                "category": record.get("category"),
                "memory_candidate": record.get("memory_candidate"),
                "json_path": chronicle.get("json_path"),
            }
        if isinstance(chronicle, dict):
            return {
                "task_id": chronicle.get("task_id"),
                "category": chronicle.get("category"),
                "memory_candidate": chronicle.get("memory_candidate"),
            }
        return {"present": True}

    def _compact_workflow(self, workflow: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not workflow:
            return {}
        return {
            "beast_object_type": workflow.get("beast_object_type"),
            "workflow_id": workflow.get("workflow_id"),
            "task_id": workflow.get("task_id"),
            "roles": workflow.get("roles", []),
            "promotion_candidate": workflow.get("promotion_candidate"),
        }

    def _compact_ir(self, ir: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "model": ir.get("model"),
            "message_count": len(ir.get("messages") or []),
            "max_tokens": ir.get("max_tokens"),
            "stream": ir.get("stream"),
            "tool_count": len(ir.get("tools") or []),
            "metadata": {
                key: value
                for key, value in (ir.get("metadata") or {}).items()
                if key != "original_request"
            },
        }

    def _tool_sequence(self, artifacts: Dict[str, Any]) -> List[str]:
        route = artifacts.get("route_card") or {}
        if route.get("preferred_order"):
            return list(route["preferred_order"])
        quality = artifacts.get("quality_report") or {}
        route_execution = quality.get("route_execution") or {}
        return list(route_execution.get("executed_order") or [])

    def _compact_for_snapshot(self, value: Any, *, max_chars: int) -> Any:
        value = _json_safe(value)
        if isinstance(value, dict):
            compacted: Dict[str, Any] = {}
            remaining = max_chars
            priority = [
                "beast_object_type", "task_id", "provider", "route_id", "packet_id",
                "workflow_id", "trace_id", "summary", "status", "decision", "confidence",
                "uncertainty", "likely_root_cause", "safest_local_next_action",
                "context_budget", "packet_stats", "preferred_order", "avoid",
                "chronicle", "workflow", "promotion_candidates", "capability_signals",
                "recommended_tool_sequence", "evidence_count", "ready",
            ]
            ordered_keys = [key for key in priority if key in value] + [key for key in sorted(value) if key not in priority]
            for key in ordered_keys:
                if remaining <= 0:
                    compacted["_truncated"] = True
                    break
                item = self._compact_for_snapshot(value[key], max_chars=max(80, remaining // 2))
                encoded = json.dumps(item, sort_keys=True, default=str)
                if len(encoded) > remaining:
                    compacted[key] = self._truncate(encoded, remaining)
                    compacted["_truncated"] = True
                    break
                compacted[key] = item
                remaining -= len(encoded)
            return compacted
        if isinstance(value, list):
            compacted_list = []
            remaining = max_chars
            for item in value[:40]:
                if remaining <= 0:
                    break
                compacted = self._compact_for_snapshot(item, max_chars=max(80, remaining // 2))
                encoded = json.dumps(compacted, sort_keys=True, default=str)
                if len(encoded) > remaining:
                    break
                compacted_list.append(compacted)
                remaining -= len(encoded)
            if len(compacted_list) < len(value):
                compacted_list.append({"_omitted_count": len(value) - len(compacted_list)})
            return compacted_list
        if isinstance(value, str):
            return self._truncate(value, max_chars)
        return value

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars <= 32:
            return text[:max_chars]
        keep = max_chars - 32
        return text[:keep] + f"...[truncated {len(text) - keep} chars]"

    def _signals(self, phase: str, artifacts: Dict[str, Any]) -> List[str]:
        signals = [f"prec:{phase}"]
        for key in ("envelope", "route_card", "quality_report", "context_packet", "forge_scorecard", "workflow", "chronicle"):
            if artifacts.get(key):
                signals.append(f"artifact:{key}")
        return signals

    def _objective(self, payload: Dict[str, Any], envelope: Dict[str, Any], task_id: Optional[str]) -> str:
        return str(self._first(
            payload.get("objective"),
            payload.get("user_request"),
            payload.get("task"),
            payload.get("goal"),
            envelope.get("objective"),
            task_id,
            "BEAST operator task",
        ))

    def _first(self, *values: Any) -> Optional[Any]:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return None


prec_lifecycle_store = PRECLifecycleStore()
