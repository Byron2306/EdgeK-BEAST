"""Shared execution outcomes and expiring negative capability evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from functools import lru_cache
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


OUTCOMES = {"success", "failure", "recovered"}
SCOPE_KEYS = {"provider", "model", "tool", "route", "transform_type"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _safe_scope(scope: Optional[Dict[str, Any]]) -> Dict[str, str]:
    return {
        key: str(value)[:160]
        for key, value in (scope or {}).items()
        if key in SCOPE_KEYS and value not in (None, "")
    }


def failure_fingerprint(category: str, code: str = "", detail: str = "") -> str:
    """Create a privacy-safe fingerprint without persisting raw failure text."""
    normalized = re.sub(r"\b[0-9a-f]{8,}\b|\d+", "#", str(detail).lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()[:240]
    digest = hashlib.sha256(_canonical([category, code, normalized]).encode()).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class OutcomeEvidence:
    capability_id: str
    task_class: str
    outcome: str
    failure_category: str = ""
    failure_code: str = ""
    failure_fingerprint: str = ""
    scope: Dict[str, str] = field(default_factory=dict)
    retries: int = 0
    repair_depth: int = 0
    latency_ms: Optional[float] = None
    approval_pauses: int = 0
    approval_duration_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    confidence_before: Optional[float] = None
    confidence_after: Optional[float] = None
    selected_capabilities: tuple[str, ...] = ()
    rejected_capabilities: tuple[str, ...] = ()
    evidence_id: str = ""
    observed_at: str = ""

    @classmethod
    def create(cls, *, detail: str = "", **values: Any) -> "OutcomeEvidence":
        outcome = str(values.get("outcome") or "").lower()
        if outcome not in OUTCOMES:
            raise ValueError(f"unsupported outcome: {outcome}")
        capability_id = str(values.get("capability_id") or "").strip()
        task_class = str(values.get("task_class") or "general").strip()
        if not capability_id:
            raise ValueError("capability_id is required")
        observed_at = str(values.get("observed_at") or _iso(_now()))
        category = str(values.get("failure_category") or "")
        code = str(values.get("failure_code") or "")
        fingerprint = str(values.get("failure_fingerprint") or "")
        if outcome in {"failure", "recovered"} and not fingerprint:
            fingerprint = failure_fingerprint(category or "unknown_failure", code, detail)
        payload = {
            "capability_id": capability_id,
            "task_class": task_class,
            "outcome": outcome,
            "failure_category": category,
            "failure_code": code,
            "failure_fingerprint": fingerprint,
            "scope": _safe_scope(values.get("scope")),
            "retries": max(0, int(values.get("retries") or 0)),
            "repair_depth": max(0, int(values.get("repair_depth") or 0)),
            "latency_ms": values.get("latency_ms"),
            "approval_pauses": max(0, int(values.get("approval_pauses") or 0)),
            "approval_duration_ms": values.get("approval_duration_ms"),
            "cost_usd": values.get("cost_usd"),
            "input_tokens": max(0, int(values.get("input_tokens") or 0)),
            "output_tokens": max(0, int(values.get("output_tokens") or 0)),
            "confidence_before": values.get("confidence_before"),
            "confidence_after": values.get("confidence_after"),
            "selected_capabilities": tuple(str(item) for item in values.get("selected_capabilities") or ()),
            "rejected_capabilities": tuple(str(item) for item in values.get("rejected_capabilities") or ()),
            "observed_at": observed_at,
        }
        evidence_id = str(values.get("evidence_id") or "")
        if not evidence_id:
            evidence_id = "outcome_" + hashlib.sha256(_canonical(payload).encode()).hexdigest()[:24]
        return cls(**payload, evidence_id=evidence_id)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["selected_capabilities"] = list(self.selected_capabilities)
        payload["rejected_capabilities"] = list(self.rejected_capabilities)
        payload["beast_object_type"] = "outcome_evidence"
        payload["version"] = "1.0"
        return payload


@dataclass
class NegativeCapabilityRecord:
    record_id: str
    capability_id: str
    task_class: str
    failure_fingerprint: str
    scope: Dict[str, str]
    evidence_ids: List[str]
    failure_count: int
    clean_success_count: int
    recovered_count: int
    confidence: float
    state: str
    created_at: str
    updated_at: str
    expires_at: str
    operator_state: str = ""
    operator_reason: str = ""
    operator_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"beast_object_type": "negative_capability", "version": "1.0", **asdict(self)}


class NegativeCapabilityStore:
    """Durable, deduplicated observations that activate only after repetition."""

    ACTIVATION_FAILURES = 3

    def __init__(self, storage_path: Optional[Path] = None, ttl_days: int = 14):
        self.storage_path = Path(storage_path) if storage_path else None
        self.ttl_days = max(1, int(ttl_days))
        self.outcomes: Dict[str, Dict[str, Any]] = {}
        self.records: Dict[str, NegativeCapabilityRecord] = {}
        self._lock = threading.RLock()
        self._load()

    def record(self, evidence: OutcomeEvidence) -> Optional[NegativeCapabilityRecord]:
        with self._lock:
            if evidence.evidence_id in self.outcomes:
                return self._record_for_evidence(evidence)
            self.outcomes[evidence.evidence_id] = evidence.to_dict()
            record = self._upsert(evidence)
            self._persist()
            return record

    def _upsert(self, evidence: OutcomeEvidence) -> Optional[NegativeCapabilityRecord]:
        matching = self._matching_records(evidence.capability_id, evidence.task_class, evidence.scope)
        if evidence.outcome == "success":
            for record in matching:
                record.clean_success_count += 1
                record.updated_at = evidence.observed_at
                self._recalculate(record)
            return matching[0] if matching else None
        key_payload = [evidence.capability_id, evidence.task_class, evidence.failure_fingerprint, evidence.scope]
        record_id = "negative_" + hashlib.sha256(_canonical(key_payload).encode()).hexdigest()[:24]
        record = self.records.get(record_id)
        if record is None:
            record = NegativeCapabilityRecord(
                record_id=record_id,
                capability_id=evidence.capability_id,
                task_class=evidence.task_class,
                failure_fingerprint=evidence.failure_fingerprint,
                scope=dict(evidence.scope),
                evidence_ids=[],
                failure_count=0,
                clean_success_count=0,
                recovered_count=0,
                confidence=0.0,
                state="observing",
                created_at=evidence.observed_at,
                updated_at=evidence.observed_at,
                expires_at=_iso(_now() + timedelta(days=self.ttl_days)),
            )
            self.records[record_id] = record
        record.evidence_ids.append(evidence.evidence_id)
        record.failure_count += 1
        record.recovered_count += int(evidence.outcome == "recovered")
        record.updated_at = evidence.observed_at
        record.expires_at = _iso(_now() + timedelta(days=self.ttl_days))
        self._recalculate(record)
        return record

    def _recalculate(self, record: NegativeCapabilityRecord) -> None:
        observations = record.failure_count + record.clean_success_count
        failure_rate = record.failure_count / max(1, observations)
        sample_weight = min(1.0, observations / self.ACTIVATION_FAILURES)
        record.confidence = round(failure_rate * sample_weight, 6)
        if self._expired(record):
            record.state = "expired"
        elif record.operator_state:
            record.state = record.operator_state
        elif record.clean_success_count >= 2:
            record.state = "revalidation"
        elif record.failure_count >= self.ACTIVATION_FAILURES and record.confidence >= 0.55:
            record.state = "active"
        else:
            record.state = "observing"

    def active_matches(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        capability_id = str(context.get("capability_id") or context.get("provider") or "")
        task_class = str(context.get("task_class") or "general")
        scope = _safe_scope(context.get("scope") or context)
        with self._lock:
            matches = []
            for record in self._matching_records(capability_id, task_class, scope):
                self._recalculate(record)
                if record.state == "active":
                    matches.append(record.to_dict())
            return matches

    def list_records(self, include_expired: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            for record in self.records.values():
                self._recalculate(record)
            return [
                record.to_dict() for record in self.records.values()
                if include_expired or record.state != "expired"
            ]

    def override(self, record_id: str, *, state: str, reason: str, approved_by: str) -> Dict[str, Any]:
        """Apply an auditable local operator decision to one negative record."""
        if state not in {"active", "revalidation", "suppressed", "clear"}:
            raise ValueError("state must be active, revalidation, suppressed, or clear")
        if not reason.strip() or not approved_by.strip():
            raise ValueError("reason and approved_by are required")
        with self._lock:
            record = self.records.get(record_id)
            if record is None:
                raise ValueError("negative capability record not found")
            record.operator_state = "" if state == "clear" else state
            record.operator_reason = reason[:500]
            record.operator_by = approved_by[:120]
            record.updated_at = _iso(_now())
            self._recalculate(record)
            self._persist()
            return record.to_dict()

    def maintain(self, *, prune_expired: bool = False) -> Dict[str, Any]:
        """Expire records and optionally prune expired records and orphan failures."""
        with self._lock:
            before = len(self.records)
            expired_ids = []
            for record_id, record in self.records.items():
                self._recalculate(record)
                if record.state == "expired":
                    expired_ids.append(record_id)
            if prune_expired:
                for record_id in expired_ids:
                    self.records.pop(record_id, None)
                referenced = {item for record in self.records.values() for item in record.evidence_ids}
                self.outcomes = {
                    key: value for key, value in self.outcomes.items()
                    if key in referenced or value.get("outcome") == "success"
                }
            self._persist()
            return {
                "beast_object_type": "negative_capability_maintenance",
                "version": "1.0",
                "records_before": before,
                "expired": len(expired_ids),
                "pruned": len(expired_ids) if prune_expired else 0,
                "records_after": len(self.records),
                "outcomes_after": len(self.outcomes),
            }

    def friction_profiles(self) -> List[Dict[str, Any]]:
        """Aggregate privacy-safe Phase 2 friction signals by capability and scope."""
        groups: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            evidence_rows = list(self.outcomes.values())
        for evidence in evidence_rows:
            scope = _safe_scope(evidence.get("scope"))
            key_values = [evidence.get("capability_id"), evidence.get("task_class"), scope]
            key = hashlib.sha256(_canonical(key_values).encode()).hexdigest()[:20]
            row = groups.setdefault(key, {
                "profile_id": "friction_" + key,
                "capability_id": str(evidence.get("capability_id") or ""),
                "task_class": str(evidence.get("task_class") or "general"),
                "scope": scope,
                "samples": 0, "failures": 0, "recoveries": 0,
                "retries": 0, "repair_depth": 0,
                "latency_total": 0.0, "latency_square_total": 0.0, "latency_samples": 0,
                "approval_pauses": 0, "approval_duration_total": 0.0, "approval_duration_samples": 0,
                "cost_total": 0.0, "cost_samples": 0,
                "confidence_total": 0.0, "confidence_error_total": 0.0,
                "confidence_overstatement_total": 0.0, "confidence_samples": 0,
                "verified_completions": 0,
            })
            verified_completion = evidence.get("outcome") in {"success", "recovered"}
            row["samples"] += 1
            row["failures"] += int(evidence.get("outcome") == "failure")
            row["recoveries"] += int(evidence.get("outcome") == "recovered")
            row["verified_completions"] += int(verified_completion)
            row["retries"] += max(0, int(evidence.get("retries") or 0))
            row["repair_depth"] += max(0, int(evidence.get("repair_depth") or 0))
            if evidence.get("latency_ms") is not None:
                latency_ms = max(0.0, float(evidence["latency_ms"]))
                row["latency_total"] += latency_ms
                row["latency_square_total"] += latency_ms * latency_ms
                row["latency_samples"] += 1
            row["approval_pauses"] += max(0, int(evidence.get("approval_pauses") or 0))
            if evidence.get("approval_duration_ms") is not None:
                row["approval_duration_total"] += max(0.0, float(evidence["approval_duration_ms"]))
                row["approval_duration_samples"] += 1
            if evidence.get("cost_usd") is not None:
                row["cost_total"] += max(0.0, float(evidence["cost_usd"]))
                row["cost_samples"] += 1
            reported_confidence = evidence.get("confidence_after")
            if reported_confidence is None:
                reported_confidence = evidence.get("confidence_before")
            if reported_confidence is not None:
                confidence = min(1.0, max(0.0, float(reported_confidence)))
                target = 1.0 if verified_completion else 0.0
                row["confidence_total"] += confidence
                row["confidence_error_total"] += abs(confidence - target)
                row["confidence_overstatement_total"] += max(0.0, confidence - target)
                row["confidence_samples"] += 1
        profiles = []
        for row in groups.values():
            samples = max(1, row["samples"])
            failure_rate = row["failures"] / samples
            recovery_rate = row["recoveries"] / samples
            retry_pressure = min(1.0, row["retries"] / (samples * 3))
            repair_pressure = min(1.0, row["repair_depth"] / (samples * 3))
            avg_latency = row["latency_total"] / row["latency_samples"] if row["latency_samples"] else None
            latency_variance = None
            latency_stddev = None
            if row["latency_samples"]:
                mean_square = row["latency_square_total"] / row["latency_samples"]
                latency_variance = max(0.0, mean_square - ((avg_latency or 0.0) ** 2))
                latency_stddev = latency_variance ** 0.5
            latency_pressure = min(1.0, (avg_latency or 0.0) / 120_000.0)
            latency_variance_pressure = min(1.0, (latency_stddev or 0.0) / 60_000.0)
            approval_pause_rate = row["approval_pauses"] / samples
            avg_approval_duration = (
                row["approval_duration_total"] / row["approval_duration_samples"]
                if row["approval_duration_samples"] else None
            )
            approval_pressure = min(1.0, (approval_pause_rate / 2.0) + ((avg_approval_duration or 0.0) / 300_000.0))
            confidence_samples = row["confidence_samples"]
            avg_reported_confidence = row["confidence_total"] / confidence_samples if confidence_samples else None
            confidence_calibration_error = row["confidence_error_total"] / confidence_samples if confidence_samples else None
            confidence_overstatement = row["confidence_overstatement_total"] / confidence_samples if confidence_samples else None
            score = (
                0.30 * failure_rate
                + 0.15 * recovery_rate
                + 0.18 * retry_pressure
                + 0.14 * repair_pressure
                + 0.08 * latency_pressure
                + 0.07 * latency_variance_pressure
                + 0.08 * approval_pressure
            )
            profiles.append({
                "beast_object_type": "friction_profile", "version": "1.0",
                "profile_id": row["profile_id"], "capability_id": row["capability_id"],
                "task_class": row["task_class"], "scope": row["scope"],
                "samples": row["samples"], "failures": row["failures"], "recoveries": row["recoveries"],
                "failure_rate": round(failure_rate, 6), "recovery_rate": round(recovery_rate, 6),
                "avg_retries": round(row["retries"] / samples, 6),
                "avg_repair_depth": round(row["repair_depth"] / samples, 6),
                "avg_latency_ms": round(avg_latency, 3) if avg_latency is not None else None,
                "latency_variance_ms2": round(latency_variance, 3) if latency_variance is not None else None,
                "latency_stddev_ms": round(latency_stddev, 3) if latency_stddev is not None else None,
                "approval_pauses": row["approval_pauses"],
                "avg_approval_duration_ms": round(avg_approval_duration, 3) if avg_approval_duration is not None else None,
                "verified_completion_rate": round(row["verified_completions"] / samples, 6),
                "reported_confidence_avg": round(avg_reported_confidence, 6) if avg_reported_confidence is not None else None,
                "confidence_calibration_error": round(confidence_calibration_error, 6) if confidence_calibration_error is not None else None,
                "confidence_overstatement": round(confidence_overstatement, 6) if confidence_overstatement is not None else None,
                "observed_cost_usd": round(row["cost_total"], 9) if row["cost_samples"] else None,
                "friction_score": round(min(1.0, score), 6),
                "confidence": round(min(1.0, row["samples"] / 5), 6),
                "mode": "shadow",
            })
        return sorted(profiles, key=lambda item: (item["friction_score"], item["samples"]), reverse=True)

    def summary(self) -> Dict[str, Any]:
        records = self.list_records()
        return {
            "beast_object_type": "negative_capability_summary",
            "version": "1.0",
            "outcomes": len(self.outcomes),
            "records": len(records),
            "active": sum(item["state"] == "active" for item in records),
            "observing": sum(item["state"] == "observing" for item in records),
            "revalidation": sum(item["state"] == "revalidation" for item in records),
            "activation_failures": self.ACTIVATION_FAILURES,
        }

    def _matching_records(self, capability_id: str, task_class: str, scope: Dict[str, Any]) -> List[NegativeCapabilityRecord]:
        normalized = _safe_scope(scope)
        return [
            record for record in self.records.values()
            if record.capability_id == capability_id
            and record.task_class in {task_class, "general"}
            and all(normalized.get(key) == value for key, value in record.scope.items())
        ]

    def _record_for_evidence(self, evidence: OutcomeEvidence) -> Optional[NegativeCapabilityRecord]:
        for record in self.records.values():
            if evidence.evidence_id in record.evidence_ids:
                return record
        return None

    @staticmethod
    def _expired(record: NegativeCapabilityRecord) -> bool:
        try:
            return datetime.fromisoformat(record.expires_at) <= _now()
        except (TypeError, ValueError):
            return True

    def _persist(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "beast_object_type": "negative_capability_store",
            "version": "1.0",
            "outcomes": self.outcomes,
            "records": {key: asdict(value) for key, value in self.records.items()},
        }
        temp = self.storage_path.with_suffix(self.storage_path.suffix + f".{os.getpid()}.tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.storage_path)

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.is_file():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self.outcomes = dict(payload.get("outcomes") or {})
            self.records = {
                str(key): NegativeCapabilityRecord(**value)
                for key, value in (payload.get("records") or {}).items()
                if isinstance(value, dict)
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.outcomes = {}
            self.records = {}


@lru_cache(maxsize=1)
def default_outcome_store() -> NegativeCapabilityStore:
    root = Path(__file__).resolve().parents[2]
    return NegativeCapabilityStore(root / ".beast" / "crystal_compute_evidence.json")
