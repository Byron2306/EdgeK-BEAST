"""
Common BEAST evidence envelope factory.

Emitters use this at the source so InsightCompiler receives already-scored,
schema-compatible evidence instead of cleaning up every subsystem after the fact.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.kernel.evidence_scoring import EvidenceScorer


class EvidenceEnvelopeFactory:
    """Build normalized, scored evidence envelopes from local emitter signals."""

    def __init__(self, policies: Optional[Dict[str, Any]] = None):
        self.scorer = EvidenceScorer(policies)

    def build(
        self,
        *,
        source_type: str,
        source_uri: str,
        scope: str,
        artifact_type: str,
        severity: str,
        confidence: float,
        relevance: float,
        risk: float,
        blast_radius: float,
        repeat_count: int = 1,
        verification_strength: float = 0.35,
        freshness: float = 1.0,
        task_id: Optional[str] = None,
        provider: Optional[str] = None,
        expected_value: Optional[float] = None,
        signals: Optional[List[str]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        recommended_actions: Optional[List[str]] = None,
        recommended_capability_id: Optional[str] = None,
        capability_family: Optional[str] = None,
        summary: str = "",
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        score = self.scorer.score(
            relevance=relevance,
            confidence=confidence,
            severity=severity,
            freshness=freshness,
            repeat_count=repeat_count,
            verification_strength=verification_strength,
            blast_radius=blast_radius,
        )
        stable = json.dumps({
            "source_type": source_type,
            "source_uri": source_uri,
            "scope": scope,
            "artifact_type": artifact_type,
            "summary": summary,
            "signals": signals or [],
            "created_at": created_at,
        }, sort_keys=True, default=str)
        return {
            "evidence_schema_version": "1.0",
            "evidence_id": "ev_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16],
            "source_type": source_type,
            "source_uri": source_uri,
            "scope": scope,
            "artifact_type": artifact_type,
            "task_id": task_id,
            "provider": provider,
            "severity": severity,
            "confidence": self._clamp(confidence),
            "freshness": self._clamp(freshness),
            "relevance": self._clamp(relevance),
            "risk": self._clamp(risk),
            "blast_radius": self._clamp(blast_radius),
            "repeat_count": max(1, int(repeat_count or 1)),
            "verification_strength": self._clamp(verification_strength),
            "failure_probability": score.failure_probability,
            "uncertainty": score.uncertainty,
            "expected_value": self._clamp(expected_value) if expected_value is not None else score.expected_value,
            "priority_score": score.priority_score,
            "capability_family": capability_family,
            "recommended_capability_id": recommended_capability_id,
            "promotion_candidate": score.promotion_candidate,
            "learning_status": score.learning_status,
            "score_breakdown": score.breakdown,
            "signals": signals or [],
            "relationships": relationships or [],
            "recommended_actions": recommended_actions or [],
            "summary": summary,
            "created_at": created_at,
        }

    def _clamp(self, value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 5)
