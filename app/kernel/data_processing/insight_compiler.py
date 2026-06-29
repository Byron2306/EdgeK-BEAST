"""
BEAST Insight Compiler.

Turns local records into ranked evidence and requires current-task markup before
handoff packets are considered ready for cloud agents.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.storage.evidence_scoring import EvidenceScorer, SEVERITY_WEIGHT


@dataclass
class EvidenceRecord:
    evidence_schema_version: str
    evidence_id: str
    source_type: str
    source_uri: str
    scope: str
    artifact_type: str
    task_id: Optional[str]
    provider: Optional[str]
    severity: str
    confidence: float
    freshness: float
    relevance: float
    risk: float
    blast_radius: float
    repeat_count: int
    verification_strength: float
    expected_value: float
    failure_probability: float = 0.0
    uncertainty: float = 0.0
    signals: List[str] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    recommended_capability_id: Optional[str] = None
    capability_family: Optional[str] = None
    priority_score: float = 0.0
    promotion_candidate: bool = False
    learning_status: str = "observe"
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InsightCompiler:
    """Build ranked local insight packets from BEAST memory and task markup."""

    SEVERITY_WEIGHT = SEVERITY_WEIGHT

    CATEGORY_SEVERITY = {
        "auth_or_credentials": "high",
        "runtime_circuit_open": "high",
        "quota_or_rate_limit": "medium",
        "network_or_timeout": "medium",
        "upstream_server_error": "medium",
        "unknown": "low",
    }

    CAPABILITY_FAMILIES = {
        "workflow:provider_diagnostic": "diagnostics",
        "workflow:quality_cascade": "quality",
        "workflow:conductor_plan": "handoff",
        "workflow:handoff_prepare": "handoff",
        "workflow:test_failure_cascade": "debugging",
        "workflow:dashboard_widget_cascade": "quality",
        "workflow:mcp_install": "tool_bus",
        "workflow:provider_proxy_setup": "provider",
        "linter:py_compile": "lint_syntax",
        "linter:pytest_collect": "lint_syntax",
        "tool:compression_prune": "tool_bus",
        "tool:semantic_interceptor": "tool_bus",
        "tool:pytest_failure_parser": "debugging",
        "tool:stack_trace_classifier": "debugging",
        "tool:log_signature_matcher": "debugging",
    }

    def __init__(
        self,
        data_dir: Optional[str] = None,
        policies: Optional[Dict[str, Any]] = None,
        forensic_memory: Optional[Any] = None,
    ):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir = Path(data_dir)
        self.current_task_dir = self.data_dir / "current_tasks"
        self.scorer = EvidenceScorer(policies)
        self.forensic_memory = forensic_memory

    def compile(
        self,
        objective: str = "",
        provider: Optional[str] = None,
        task_class: Optional[str] = None,
        limit: int = 10,
        current_task: Optional[Dict[str, Any]] = None,
        evidence_records: Optional[List[Dict[str, Any]]] = None,
        include_forensic_context: bool = True,
        forensic_limit: int = 8,
        forensic_layer: Optional[str] = None,
        forensic_event_kind: Optional[str] = None,
        forensic_provider: Optional[str] = None,
        forensic_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compile ranked evidence from Chronicle/provider diagnostic memory."""
        objective = str(objective or "").strip()
        records = self._load_chronicles(provider=provider, task_class=task_class)
        repeat_counts = self._repeat_counts(records)
        evidence = [
            self._normalize_evidence(self._evidence_from_chronicle(record, objective, repeat_counts))
            for record in records
        ]
        live_records = list(evidence_records or [])
        forensic_records = self._forensic_evidence_records(
            objective,
            limit=forensic_limit,
            layer=forensic_layer,
            event_kind=forensic_event_kind,
            provider=forensic_provider or provider,
            status=forensic_status,
        ) if include_forensic_context else []
        live_records.extend(forensic_records)
        evidence.extend(self._coerce_live_evidence(live_records, objective))
        evidence.sort(key=self._rank_key, reverse=True)
        bounded = evidence[: max(1, min(int(limit), 100))]
        markup = self.current_task_markup(current_task or {"objective": objective}, persist=False)
        return {
            "beast_object_type": "insight_packet",
            "version": "1.0",
            "objective": objective,
            "provider": provider,
            "task_class": task_class,
            "current_task": markup,
            "evidence": [item.to_dict() for item in bounded],
            "summary": self._summary(bounded),
            "forensic_context": {
                "included": bool(include_forensic_context and self.forensic_memory),
                "evidence_count": len(forensic_records),
                "filters": {
                    "layer": forensic_layer,
                    "event_kind": forensic_event_kind,
                    "provider": forensic_provider or provider,
                    "status": forensic_status,
                },
            },
            "ranked": True,
            "local_first": True,
            "created_at": self._utc_now(),
        }

    def prepare_handoff(
        self,
        current_task: Dict[str, Any],
        objective: str = "",
        provider: Optional[str] = None,
        task_class: Optional[str] = None,
        limit: int = 8,
        persist_task: bool = True,
        evidence_records: Optional[List[Dict[str, Any]]] = None,
        include_forensic_context: bool = True,
        forensic_limit: int = 8,
        forensic_layer: Optional[str] = None,
        forensic_event_kind: Optional[str] = None,
        forensic_provider: Optional[str] = None,
        forensic_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare a cloud handoff packet only after current task markup exists."""
        markup = self.current_task_markup(current_task, persist=persist_task)
        if not markup["valid"]:
            return {
                "beast_object_type": "cloud_handoff_precheck",
                "version": "1.0",
                "ready": False,
                "reason": "current_task_markup_required",
                "current_task": markup,
                "insight_packet": None,
            }
        objective = objective or markup["record"].get("objective", "")
        insight = self.compile(
            objective=objective,
            provider=provider,
            task_class=task_class,
            limit=limit,
            current_task=markup["record"],
            evidence_records=evidence_records,
            include_forensic_context=include_forensic_context,
            forensic_limit=forensic_limit,
            forensic_layer=forensic_layer,
            forensic_event_kind=forensic_event_kind,
            forensic_provider=forensic_provider,
            forensic_status=forensic_status,
        )
        return {
            "beast_object_type": "cloud_handoff_precheck",
            "version": "1.0",
            "ready": True,
            "reason": "current_task_markup_present",
            "current_task": markup,
            "insight_packet": insight,
            "handoff_rules": [
                "send ranked evidence, not raw repository dumps",
                "include current task objective, scope, constraints, and success criteria",
                "preserve local policy/circuit/credential findings",
                "include exact source references and uncertainty",
            ],
        }

    def current_task_markup(self, current_task: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
        """Validate and optionally persist a current task record."""
        task = dict(current_task or {})
        missing = [
            key for key in ("objective", "scope", "success_criteria")
            if not task.get(key)
        ]
        if isinstance(task.get("success_criteria"), str):
            task["success_criteria"] = [task["success_criteria"]]
        if isinstance(task.get("constraints"), str):
            task["constraints"] = [task["constraints"]]
        task.setdefault("constraints", [])
        task.setdefault("created_at", self._utc_now())
        task.setdefault("source", "beast_current_task_markup")
        stable = json.dumps(task, sort_keys=True, default=str)
        digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()
        task.setdefault("task_markup_id", f"ctask_{digest[:16]}")
        task["task_markup_hash"] = f"sha256:{digest}"
        result = {
            "valid": not missing,
            "missing": missing,
            "record": task,
            "written": False,
            "path": None,
        }
        if persist and not missing:
            self.current_task_dir.mkdir(parents=True, exist_ok=True)
            path = self.current_task_dir / f"{task['task_markup_id']}.json"
            path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result.update({"written": True, "path": str(path)})
        return result

    def _load_chronicles(self, provider: Optional[str], task_class: Optional[str]) -> List[Dict[str, Any]]:
        chronicle_dir = self.data_dir / "chronicles"
        records = []
        for path in self._chronicle_paths(chronicle_dir):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
            if evidence:
                record = self._evidence_chronicle_to_record(record, evidence)
            if provider and record.get("provider") != provider:
                continue
            if task_class and record.get("task_class") != task_class:
                continue
            record["_source_uri"] = str(path)
            records.append(record)
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return records

    def _chronicle_paths(self, chronicle_dir: Path) -> List[Path]:
        paths: List[Path] = []
        if chronicle_dir.exists():
            paths.extend(chronicle_dir.glob("*.json"))
        evidence_dir = self.data_dir / "evidence_chronicles"
        if evidence_dir.exists():
            paths.extend(evidence_dir.glob("*.json"))
        return paths

    def _evidence_chronicle_to_record(self, record: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **record,
            "chronicle_type": record.get("chronicle_type") or "evidence_envelope",
            "task_id": evidence.get("task_id") or record.get("task_id"),
            "task_class": record.get("task_class") or "evidence_envelope",
            "provider": evidence.get("provider") or record.get("provider"),
            "category": evidence.get("capability_family") or record.get("category") or evidence.get("source_type"),
            "summary": evidence.get("summary") or record.get("summary") or "Scored evidence envelope",
            "root_cause": evidence.get("summary") or record.get("reason"),
            "confidence": evidence.get("confidence") or 0.55,
            "cloud_escalation_needed": False,
            "memory_candidate": True,
            "created_at": evidence.get("created_at") or record.get("created_at"),
            "verification": {"check_count": 1, "failed_checks": []},
            "recommendations": evidence.get("recommended_actions") or [],
            "recommended_capability_id": evidence.get("recommended_capability_id"),
            "capability_family": evidence.get("capability_family"),
            "expected_value": evidence.get("expected_value"),
            "priority_score": evidence.get("priority_score"),
            "_evidence_envelope": evidence,
        }

    def _repeat_counts(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in records:
            key = self._repeat_key(record)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _evidence_from_chronicle(
        self,
        record: Dict[str, Any],
        objective: str,
        repeat_counts: Dict[str, int],
    ) -> EvidenceRecord:
        category = str(record.get("category") or "unknown")
        provider = record.get("provider")
        severity = self.CATEGORY_SEVERITY.get(category, "low")
        confidence = self._clamp(float(record.get("confidence") or 0.55))
        freshness = self._freshness(record.get("created_at"))
        relevance = self._relevance(objective, record)
        repeat_count = repeat_counts.get(self._repeat_key(record), 1)
        verification_strength = self._verification_strength(record.get("verification") or {})
        risk = self.SEVERITY_WEIGHT.get(severity, 0.3)
        blast_radius = self._blast_radius(record)
        score = self.scorer.score(
            relevance=relevance,
            confidence=confidence,
            severity=severity,
            freshness=freshness,
            repeat_count=repeat_count,
            verification_strength=verification_strength,
            blast_radius=blast_radius,
        )
        expected_value = score.expected_value
        signals = self._signals(record, repeat_count)
        evidence_id = self._evidence_id(record)
        return EvidenceRecord(
            evidence_schema_version="1.0",
            evidence_id=evidence_id,
            source_type="chronicle",
            source_uri=record.get("_source_uri") or (record.get("artifacts") or {}).get("json_path") or "",
            scope="provider",
            artifact_type=str(record.get("chronicle_type") or "provider_diagnostic_summary"),
            task_id=record.get("task_id"),
            provider=provider,
            severity=severity,
            confidence=confidence,
            freshness=freshness,
            relevance=relevance,
            risk=risk,
            blast_radius=blast_radius,
            repeat_count=repeat_count,
            verification_strength=verification_strength,
            expected_value=expected_value,
            failure_probability=score.failure_probability,
            uncertainty=score.uncertainty,
            priority_score=self._clamp(float(record.get("priority_score") or score.priority_score)),
            promotion_candidate=score.promotion_candidate,
            learning_status=score.learning_status,
            score_breakdown=score.breakdown,
            signals=signals,
            relationships=[
                {"type": "provider", "id": provider},
                {"type": "category", "id": category},
            ],
            recommended_actions=[str(item) for item in record.get("recommendations", [])[:6]],
            recommended_capability_id=record.get("recommended_capability_id") or self._map_to_capability_id(objective, record),
            capability_family=record.get("capability_family"),
            summary=str(record.get("summary") or record.get("root_cause") or ""),
            created_at=record.get("created_at"),
        )

    def _coerce_live_evidence(self, records: List[Dict[str, Any]], objective: str) -> List[EvidenceRecord]:
        evidence: List[EvidenceRecord] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            source_type = str(record.get("source_type") or "")
            if source_type not in {"tool_interception", "quality_verifier", "capability_registry", "interception_event", "compression_pipeline", "forensic_l4"}:
                continue
            cloned = dict(record)
            cloned["freshness"] = self._freshness(cloned.get("created_at")) if cloned.get("created_at") else 1.0
            cloned["relevance"] = max(float(cloned.get("relevance") or 0.0), self._relevance(objective, cloned))
            score = self.scorer.score(
                relevance=float(cloned.get("relevance") or 0.4),
                confidence=float(cloned.get("confidence") or 0.5),
                severity=str(cloned.get("severity") or "info"),
                freshness=float(cloned.get("freshness") or 1.0),
                repeat_count=int(cloned.get("repeat_count") or 1),
                verification_strength=float(cloned.get("verification_strength") or 0.35),
                blast_radius=float(cloned.get("blast_radius") or 0.4),
            )
            cloned["expected_value"] = score.expected_value
            cloned["_score"] = score
            evidence.append(self._normalize_evidence(EvidenceRecord(
                evidence_schema_version=str(cloned.get("evidence_schema_version") or "1.0"),
                evidence_id=str(cloned.get("evidence_id") or self._generic_evidence_id(cloned)),
                source_type=source_type,
                source_uri=str(cloned.get("source_uri") or ""),
                scope=str(cloned.get("scope") or "tool_call"),
                artifact_type=str(cloned.get("artifact_type") or "live_evidence"),
                task_id=cloned.get("task_id"),
                provider=cloned.get("provider"),
                severity=str(cloned.get("severity") or "info"),
                confidence=self._clamp(float(cloned.get("confidence") or 0.5)),
                freshness=self._clamp(float(cloned.get("freshness") or 1.0)),
                relevance=self._clamp(float(cloned.get("relevance") or 0.4)),
                risk=self._clamp(float(cloned.get("risk") or 0.25)),
                blast_radius=self._clamp(float(cloned.get("blast_radius") or 0.4)),
                repeat_count=int(cloned.get("repeat_count") or 1),
                verification_strength=self._clamp(float(cloned.get("verification_strength") or 0.35)),
                expected_value=self._clamp(float(cloned.get("expected_value") or 0.35)),
                failure_probability=self._clamp(float(cloned.get("failure_probability") or score.failure_probability)),
                uncertainty=self._clamp(float(cloned.get("uncertainty") or score.uncertainty)),
                signals=[str(item) for item in cloned.get("signals", [])],
                relationships=cloned.get("relationships", []),
                recommended_actions=[str(item) for item in cloned.get("recommended_actions", [])[:6]],
                recommended_capability_id=cloned.get("recommended_capability_id") or self._map_to_capability_id(objective, cloned),
                capability_family=cloned.get("capability_family"),
                priority_score=self._clamp(float(cloned.get("priority_score") or score.priority_score)),
                promotion_candidate=bool(cloned.get("promotion_candidate", score.promotion_candidate)),
                learning_status=str(cloned.get("learning_status") or score.learning_status),
                score_breakdown=cloned.get("score_breakdown") or score.breakdown,
                summary=str(cloned.get("summary") or ""),
                created_at=cloned.get("created_at"),
            )))
        return evidence

    def _forensic_evidence_records(
        self,
        objective: str,
        *,
        limit: int,
        layer: Optional[str],
        event_kind: Optional[str],
        provider: Optional[str],
        status: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not self.forensic_memory:
            return []
        try:
            result = self.forensic_memory.query(
                query=objective,
                event_kind=event_kind,
                layer=layer,
                provider=provider,
                status=status,
                limit=max(1, min(int(limit), 50)),
            )
        except Exception:
            return []
        records: List[Dict[str, Any]] = []
        for item in result.get("results", []):
            evidence = dict(item.get("evidence") or {})
            event = item.get("event") or {}
            if evidence:
                evidence.setdefault("source_type", "interception_event")
                evidence.setdefault("source_uri", item.get("source_uri") or f"forensic://{item.get('event_id')}")
                evidence.setdefault("artifact_type", f"forensic_l4:{item.get('event_kind')}")
                evidence.setdefault("summary", event.get("summary") or event.get("message") or item.get("event_kind"))
            else:
                evidence = {
                    "source_type": "forensic_l4",
                    "source_uri": item.get("source_uri") or f"forensic://{item.get('event_id')}",
                    "scope": "forensic",
                    "artifact_type": f"forensic_l4:{item.get('event_kind')}",
                    "provider": item.get("provider"),
                    "severity": item.get("severity") or "info",
                    "confidence": 0.65,
                    "relevance": 0.45,
                    "risk": 0.35,
                    "blast_radius": 0.35,
                    "repeat_count": 1,
                    "verification_strength": 0.45,
                    "summary": event.get("summary") or event.get("message") or item.get("event_kind") or "Forensic L4 event",
                }
            evidence["evidence_id"] = evidence.get("evidence_id") or f"ev_forensic_{item.get('event_id')}"
            evidence["priority_score"] = max(float(evidence.get("priority_score") or 0.0), float(item.get("priority_score") or 0.0))
            evidence["relevance"] = max(float(evidence.get("relevance") or 0.0), min(1.0, 0.35 + float(item.get("lexical_score") or 0.0) * 0.1))
            evidence.setdefault("created_at", item.get("created_at"))
            evidence.setdefault("relationships", [])
            evidence["relationships"] = list(evidence.get("relationships") or []) + [
                {"type": "forensic_event", "id": item.get("event_id")},
                {"type": "forensic_layer", "id": item.get("layer")},
            ]
            evidence.setdefault("signals", [])
            evidence["signals"] = list(dict.fromkeys(list(evidence.get("signals") or []) + ["forensic_l4_retrieved"]))
            records.append(evidence)
        return records

    def _rank_key(self, evidence: EvidenceRecord) -> float:
        if evidence.priority_score:
            return evidence.priority_score
        return self._priority_score(evidence)

    def _priority_score(self, evidence: EvidenceRecord) -> float:
        return self.scorer.score(
            relevance=evidence.relevance,
            confidence=evidence.confidence,
            severity=evidence.severity,
            freshness=evidence.freshness,
            repeat_count=evidence.repeat_count,
            verification_strength=evidence.verification_strength,
            blast_radius=evidence.blast_radius,
        ).priority_score

    def _summary(self, evidence: List[EvidenceRecord]) -> Dict[str, Any]:
        if not evidence:
            return {
                "evidence_count": 0,
                "top_insight": None,
                "highest_expected_value": 0.0,
                "handoff_recommendation": "Current task markup is required; no local Chronicle evidence matched.",
            }
        top = evidence[0]
        family_counts: Dict[str, int] = {}
        capability_counts: Dict[str, int] = {}
        promotion_candidates = []
        for item in evidence:
            if item.capability_family:
                family_counts[item.capability_family] = family_counts.get(item.capability_family, 0) + 1
            if item.recommended_capability_id:
                capability_counts[item.recommended_capability_id] = capability_counts.get(item.recommended_capability_id, 0) + 1
            if item.promotion_candidate:
                promotion_candidates.append(item.evidence_id)
        return {
            "evidence_count": len(evidence),
            "top_insight": {
                "evidence_id": top.evidence_id,
                "provider": top.provider,
                "severity": top.severity,
                "confidence": top.confidence,
                "expected_value": top.expected_value,
                "failure_probability": top.failure_probability,
                "uncertainty": top.uncertainty,
                "priority_score": top.priority_score,
                "recommended_capability_id": top.recommended_capability_id,
                "capability_family": top.capability_family,
                "summary": top.summary,
            },
            "highest_expected_value": top.expected_value,
            "top_capability_family": top.capability_family,
            "family_counts": family_counts,
            "capability_counts": capability_counts,
            "promotion_candidates": promotion_candidates[:10],
            "handoff_recommendation": "Send top ranked evidence with current task markup and exact references.",
        }

    def _normalize_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        evidence.confidence = self._clamp(evidence.confidence)
        evidence.freshness = self._clamp(evidence.freshness)
        evidence.relevance = self._clamp(evidence.relevance)
        evidence.risk = self._clamp(evidence.risk)
        evidence.blast_radius = self._clamp(evidence.blast_radius)
        evidence.verification_strength = self._clamp(evidence.verification_strength)
        score = self.scorer.score(
            relevance=evidence.relevance,
            confidence=evidence.confidence,
            severity=evidence.severity,
            freshness=evidence.freshness,
            repeat_count=evidence.repeat_count,
            verification_strength=evidence.verification_strength,
            blast_radius=evidence.blast_radius,
        )
        evidence.expected_value = score.expected_value
        evidence.failure_probability = score.failure_probability
        evidence.uncertainty = score.uncertainty
        if evidence.recommended_capability_id and not evidence.capability_family:
            evidence.capability_family = self._capability_family(evidence.recommended_capability_id)
        if not evidence.capability_family:
            evidence.capability_family = self._infer_family(evidence)
        evidence.priority_score = score.priority_score
        evidence.promotion_candidate = score.promotion_candidate
        evidence.learning_status = score.learning_status
        evidence.score_breakdown = score.breakdown
        if evidence.recommended_capability_id:
            evidence.relationships.append({
                "type": "capability",
                "id": evidence.recommended_capability_id,
                "family": evidence.capability_family,
            })
        return evidence

    def _signals(self, record: Dict[str, Any], repeat_count: int) -> List[str]:
        signals = []
        if record.get("memory_candidate"):
            signals.append("memory_candidate")
        if record.get("cloud_escalation_needed"):
            signals.append("cloud_escalation_needed")
        if repeat_count > 1:
            signals.append("repeated_pattern")
        verification = record.get("verification") or {}
        if verification.get("failed_checks"):
            signals.append("failed_local_checks")
        return signals

    def _relevance(self, objective: str, record: Dict[str, Any]) -> float:
        if not objective:
            return 0.45
        haystack = " ".join([
            str(record.get("summary") or ""),
            str(record.get("root_cause") or ""),
            str(record.get("provider") or ""),
            str(record.get("category") or ""),
            " ".join(str(item) for item in record.get("recommendations", [])),
        ]).lower()
        tokens = [
            token.lower()
            for token in objective.replace("_", " ").split()
            if len(token.strip(".,:;")) >= 3
        ]
        if not tokens:
            return 0.45
        hits = sum(1 for token in tokens if token.strip(".,:;") in haystack)
        return self._clamp(0.25 + (hits / max(len(tokens), 1)) * 0.75)

    def _freshness(self, created_at: Optional[str]) -> float:
        if not created_at:
            return 0.35
        try:
            stamp = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0)
            return self._clamp(math.exp(-age_days / 30.0))
        except ValueError:
            return 0.35

    def _verification_strength(self, verification: Dict[str, Any]) -> float:
        check_count = int(verification.get("check_count") or 0)
        failed = len(verification.get("failed_checks") or [])
        if check_count <= 0:
            return 0.25
        return self._clamp(0.35 + min(check_count, 8) * 0.07 + min(failed, 4) * 0.08)

    def _blast_radius(self, record: Dict[str, Any]) -> float:
        if record.get("provider"):
            return 0.35
        if record.get("task_class") == "provider_debugging":
            return 0.3
        return 0.5

    def _expected_value(
        self,
        relevance: float,
        confidence: float,
        severity: str,
        freshness: float,
        repeat_count: int,
        verification_strength: float,
        blast_radius: float,
    ) -> float:
        return self.scorer.score(
            relevance=relevance,
            confidence=confidence,
            severity=severity,
            freshness=freshness,
            repeat_count=repeat_count,
            verification_strength=verification_strength,
            blast_radius=blast_radius,
        ).expected_value

    def _capability_family(self, capability_id: str) -> Optional[str]:
        if capability_id in self.CAPABILITY_FAMILIES:
            return self.CAPABILITY_FAMILIES[capability_id]
        if ":" in capability_id:
            prefix = capability_id.split(":", 1)[0]
            return {
                "provider": "provider",
                "parser": "parsing",
                "linter": "lint_syntax",
                "database": "database",
                "plugin": "plugin",
                "skill": "skill",
                "cli": "agentic_cli",
                "mcp_tool": "tool_bus",
                "route": "routing",
                "workflow": "workflow",
                "tool": "tool_bus",
            }.get(prefix)
        return None

    def _infer_family(self, evidence: EvidenceRecord) -> str:
        signals = " ".join(evidence.signals).lower()
        summary = evidence.summary.lower()
        if evidence.provider:
            return "provider"
        if "token" in signals or "compress" in summary:
            return "tool_bus"
        if "test" in signals or "lint" in summary or "traceback" in summary:
            return "debugging"
        if evidence.source_type == "quality_verifier":
            return "quality"
        if evidence.source_type == "tool_interception":
            return "tool_bus"
        return "general"

    def _promotion_candidate(self, evidence: EvidenceRecord) -> bool:
        return self.scorer.promotion_candidate(
            expected_value=evidence.expected_value,
            priority_score=evidence.priority_score,
            repeat_count=evidence.repeat_count,
            verification_strength=evidence.verification_strength,
        )

    def _learning_status(self, evidence: EvidenceRecord) -> str:
        return self.scorer.learning_status(evidence.priority_score, evidence.promotion_candidate)

    def _repeat_key(self, record: Dict[str, Any]) -> str:
        return f"{record.get('task_class')}::{record.get('provider')}::{record.get('category')}"

    def _evidence_id(self, record: Dict[str, Any]) -> str:
        raw = json.dumps({
            "task_id": record.get("task_id"),
            "provider": record.get("provider"),
            "category": record.get("category"),
            "source": record.get("_source_uri") or (record.get("artifacts") or {}).get("json_path"),
        }, sort_keys=True, default=str)
        return "ev_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _generic_evidence_id(self, record: Dict[str, Any]) -> str:
        return "ev_live_" + hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

    def _clamp(self, value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 5)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _map_to_capability_id(self, objective: str, record: Dict[str, Any]) -> Optional[str]:
        """Map objective and evidence signals to specific capability IDs."""
        objective_lower = objective.lower()
        summary = str(record.get("summary") or "").lower()
        root_cause = str(record.get("root_cause") or "").lower()
        provider = str(record.get("provider") or "").lower()
        category = str(record.get("category") or "").lower()
        recommendations = [str(item).lower() for item in record.get("recommendations", [])]
        
        # Combine all text for analysis
        haystack = " ".join([objective_lower, summary, root_cause, provider, category, " ".join(recommendations)])
        
        # Provider failure indicators -> workflow:provider_diagnostic
        if any(indicator in haystack for indicator in [
            "provider failure", "provider error", "api error", "upstream error", 
            "timeout", "rate limit", "quota exceeded", "unavailable", "down",
            "credential", "auth", "api key"
        ]) or category in ["auth_or_credentials", "network_or_timeout", "upstream_server_error", "quota_or_rate_limit"]:
            return "workflow:provider_diagnostic"
        
        # Python syntax/import errors -> linter:py_compile
        if any(indicator in haystack for indicator in [
            "syntax error", "import error", "indentation error", "python compile",
            "module not found", "invalid syntax", "python error"
        ]) or "python" in haystack and any(indicator in haystack for indicator in [
            "error", "exception", "traceback", "failed to import"
        ]):
            return "linter:py_compile"
        
        # Token-heavy intercepted payloads -> tool:compression_prune
        if any(indicator in haystack for indicator in [
            "token limit", "context length", "payload too large", "intercepted payload",
            "compression needed", "token heavy", "context overflow"
        ]) or ("token" in haystack and ("limit" in haystack or "exceed" in haystack)):
            return "tool:compression_prune"
        
        # Quality issues -> workflow:quality_cascade
        if any(indicator in haystack for indicator in [
            "quality issue", "test failure", "coverage low", "lint error",
            "quality cascade", "quality check"
        ]) or category == "quality_verifier":
            return "workflow:quality_cascade"
        
        # Conductor planning -> workflow:conductor_plan
        if any(indicator in haystack for indicator in [
            "workflow plan", "conductor", "orchestration", "task planning",
            "workflow execution", "plan workflow"
        ]):
            return "workflow:conductor_plan"
        
        # Handoff preparation -> workflow:handoff_prepare
        if any(indicator in haystack for indicator in [
            "handoff", "prepare handoff", "cloud handoff", "task markup",
            "current task", "task preparation"
        ]):
            return "workflow:handoff_prepare"
        
        # Tool interception -> tool:semantic_interceptor
        if any(indicator in haystack for indicator in [
            "semantic interception", "tool interception", "payload inspection",
            "intercepted", "semantic analysis"
        ]) or record.get("source_type") == "tool_interception":
            return "tool:semantic_interceptor"
        
        # Default fallback based on source_type
        source_type = str(record.get("source_type") or "")
        if source_type == "quality_verifier":
            return "workflow:quality_cascade"
        elif source_type == "tool_interception":
            return "tool:semantic_interceptor"
        elif source_type == "capability_registry":
            return "tool:compression_prune"  # Generic tool capability
        
        return None
