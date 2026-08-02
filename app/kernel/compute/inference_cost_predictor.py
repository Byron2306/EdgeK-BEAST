from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .residual_candidate import ResidualCandidate


@dataclass(frozen=True, slots=True)
class InferenceSelectionWeights:
    latency: float = 1.0
    cpu: float = 0.20
    memory_mib: float = 0.08
    energy: float = 0.05
    money: float = 1000.0
    quality_penalty: float = 1800.0
    failure_penalty: float = 1200.0
    pressure_penalty: float = 1.0
    restoration: float = 1.0


@dataclass(frozen=True, slots=True)
class CostPrediction:
    candidate_id: str
    score: float
    components: Mapping[str, float]


class InferenceCostPredictor:
    def __init__(self, weights: InferenceSelectionWeights | None = None) -> None:
        self.weights = weights or InferenceSelectionWeights()

    def predict(self, candidate: ResidualCandidate) -> CostPrediction:
        meta = dict(candidate.metadata or {})
        pressure = float(meta.get("pressure_penalty", 0.0))
        restoration = float(meta.get("restoration_cost_ms", 0.0))
        energy = float(candidate.predicted_energy_joules or 0.0)
        quality_penalty = (1.0 - candidate.expected_quality) * self.weights.quality_penalty
        failure_penalty = candidate.failure_probability * self.weights.failure_penalty
        components = {
            "latency": candidate.expected_latency_ms * self.weights.latency,
            "cpu": candidate.predicted_cpu_ms * self.weights.cpu,
            "memory": (candidate.predicted_memory_bytes / (1024 * 1024)) * self.weights.memory_mib,
            "energy": energy * self.weights.energy,
            "money": candidate.predicted_monetary_cost * self.weights.money,
            "quality_penalty": quality_penalty,
            "failure_penalty": failure_penalty,
            "pressure_penalty": pressure * self.weights.pressure_penalty,
            "restoration": restoration * self.weights.restoration,
        }
        return CostPrediction(candidate.candidate_id, sum(components.values()), components)
