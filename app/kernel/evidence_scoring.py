"""
BEAST evidence scoring.

Small deterministic scorer for normalized evidence envelopes. It keeps ranking
explainable so promotion and handoff decisions can show their work.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict


SEVERITY_WEIGHT = {
    "info": 0.15,
    "low": 0.3,
    "medium": 0.55,
    "high": 0.78,
    "critical": 1.0,
}


@dataclass
class ScoreResult:
    expected_value: float
    priority_score: float
    failure_probability: float
    uncertainty: float
    promotion_candidate: bool
    learning_status: str
    breakdown: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceScorer:
    """Score evidence for ranking, prioritization, learning, and promotion."""

    EXPECTED_VALUE_WEIGHTS = {
        "relevance": 0.22,
        "confidence": 0.18,
        "severity": 0.18,
        "freshness": 0.10,
        "repetition": 0.14,
        "verification": 0.12,
        "blast_radius_inverse": 0.06,
    }

    PRIORITY_WEIGHTS = {
        "expected_value": 3.0,
        "confidence": 1.0,
        "relevance": 1.0,
        "verification": 1.0,
        "repeat_bonus": 1.0,
        "blast_radius_penalty": -1.0,
    }

    FAILURE_PROBABILITY_WEIGHTS = {
        "relevance": 0.25,
        "confidence": 0.25,
        "severity": 0.20,
        "repetition": 0.15,
        "verification": 0.10,
        "freshness": 0.05,
        "blast_radius_penalty": -0.05,
    }

    THRESHOLDS = {
        "promotion_repeat_count": 2,
        "promotion_expected_value": 0.55,
        "promotion_priority_score": 0.72,
        "promotion_verification_strength": 0.5,
        "prioritize_priority_score": 0.55,
    }

    def __init__(self, policies: Dict[str, Any] | None = None):
        config = (policies or {}).get("evidence_scoring", policies or {})
        self.expected_value_weights = self._merge_weights(
            self.EXPECTED_VALUE_WEIGHTS,
            config.get("expected_value_weights") or {},
        )
        self.priority_weights = self._merge_weights(
            self.PRIORITY_WEIGHTS,
            config.get("priority_weights") or {},
        )
        self.failure_probability_weights = self._merge_weights(
            self.FAILURE_PROBABILITY_WEIGHTS,
            config.get("failure_probability_weights") or {},
        )
        self.thresholds = self._merge_weights(
            self.THRESHOLDS,
            config.get("thresholds") or {},
        )

    def score(
        self,
        *,
        relevance: float,
        confidence: float,
        severity: str,
        freshness: float,
        repeat_count: int,
        verification_strength: float,
        blast_radius: float,
    ) -> ScoreResult:
        relevance = self._clamp(relevance)
        confidence = self._clamp(confidence)
        freshness = self._clamp(freshness)
        verification_strength = self._clamp(verification_strength)
        blast_radius = self._clamp(blast_radius)
        repeat_count = max(1, int(repeat_count or 1))
        severity_weight = SEVERITY_WEIGHT.get(str(severity or "info"), 0.3)
        repetition = self._clamp(math.log1p(max(0, repeat_count - 1)) / 2.2)
        expected_components = {
            "relevance": relevance * self.expected_value_weights["relevance"],
            "confidence": confidence * self.expected_value_weights["confidence"],
            "severity": severity_weight * self.expected_value_weights["severity"],
            "freshness": freshness * self.expected_value_weights["freshness"],
            "repetition": repetition * self.expected_value_weights["repetition"],
            "verification": verification_strength * self.expected_value_weights["verification"],
            "blast_radius_inverse": (1.0 - blast_radius) * self.expected_value_weights["blast_radius_inverse"],
        }
        expected_value = self._clamp(sum(expected_components.values()))
        failure_components = {
            "relevance": relevance * self.failure_probability_weights["relevance"],
            "confidence": confidence * self.failure_probability_weights["confidence"],
            "severity": severity_weight * self.failure_probability_weights["severity"],
            "repetition": repetition * self.failure_probability_weights["repetition"],
            "verification": verification_strength * self.failure_probability_weights["verification"],
            "freshness": freshness * self.failure_probability_weights["freshness"],
            "blast_radius_penalty": blast_radius * self.failure_probability_weights["blast_radius_penalty"],
        }
        failure_probability = self._clamp(sum(failure_components.values()))
        uncertainty = self._clamp(1.0 - ((confidence * 0.55) + (verification_strength * 0.3) + (relevance * 0.15)))
        repeat_bonus = min(repeat_count, 8) * 0.08
        priority_raw = (
            expected_value * self.priority_weights["expected_value"]
            + confidence * self.priority_weights["confidence"]
            + relevance * self.priority_weights["relevance"]
            + verification_strength * self.priority_weights["verification"]
            + repeat_bonus * self.priority_weights["repeat_bonus"]
            + blast_radius * 0.25 * self.priority_weights["blast_radius_penalty"]
        )
        priority_score = self._clamp(priority_raw / 5.0)
        promotion_candidate = self.promotion_candidate(
            expected_value=expected_value,
            priority_score=priority_score,
            repeat_count=repeat_count,
            verification_strength=verification_strength,
        )
        learning_status = self.learning_status(priority_score, promotion_candidate)
        return ScoreResult(
            expected_value=round(expected_value, 5),
            priority_score=round(priority_score, 5),
            failure_probability=round(failure_probability, 5),
            uncertainty=round(uncertainty, 5),
            promotion_candidate=promotion_candidate,
            learning_status=learning_status,
            breakdown={
                "score_schema_version": "1.0",
                "expected_value_weights": dict(self.expected_value_weights),
                "expected_value_components": {
                    key: round(value, 5)
                    for key, value in expected_components.items()
                },
                "expected_value_raw": round(sum(expected_components.values()), 5),
                "failure_probability_weights": dict(self.failure_probability_weights),
                "failure_probability_components": {
                    key: round(value, 5)
                    for key, value in failure_components.items()
                },
                "failure_probability_raw": round(sum(failure_components.values()), 5),
                "priority_weights": dict(self.priority_weights),
                "priority_components": {
                    "expected_value": round(expected_value * self.priority_weights["expected_value"], 5),
                    "confidence": round(confidence * self.priority_weights["confidence"], 5),
                    "relevance": round(relevance * self.priority_weights["relevance"], 5),
                    "verification": round(verification_strength * self.priority_weights["verification"], 5),
                    "repeat_bonus": round(repeat_bonus * self.priority_weights["repeat_bonus"], 5),
                    "blast_radius_penalty": round(blast_radius * 0.25 * self.priority_weights["blast_radius_penalty"], 5),
                },
                "priority_raw": round(priority_raw, 5),
                "local_scores": {
                    "relevance": relevance,
                    "confidence": confidence,
                    "severity": severity_weight,
                    "blast_radius": blast_radius,
                    "freshness": freshness,
                    "repetition": repetition,
                    "failure_probability": round(failure_probability, 5),
                    "expected_value": round(expected_value, 5),
                    "verification_strength": verification_strength,
                },
                "uncertainty": round(uncertainty, 5),
                "thresholds": dict(self.thresholds),
            },
        )

    def promotion_candidate(
        self,
        *,
        expected_value: float,
        priority_score: float,
        repeat_count: int,
        verification_strength: float,
    ) -> bool:
        if int(repeat_count or 1) >= int(self.thresholds["promotion_repeat_count"]) and float(expected_value or 0.0) >= float(self.thresholds["promotion_expected_value"]):
            return True
        if float(priority_score or 0.0) >= float(self.thresholds["promotion_priority_score"]) and float(verification_strength or 0.0) >= float(self.thresholds["promotion_verification_strength"]):
            return True
        return False

    def learning_status(self, priority_score: float, promotion_candidate: bool) -> str:
        if promotion_candidate:
            return "promotion_candidate"
        if float(priority_score or 0.0) >= float(self.thresholds["prioritize_priority_score"]):
            return "prioritize"
        return "observe"

    def _merge_weights(self, defaults: Dict[str, float], overrides: Dict[str, Any]) -> Dict[str, float]:
        merged = dict(defaults)
        for key, value in overrides.items():
            if key in merged:
                merged[key] = float(value)
        return merged

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
