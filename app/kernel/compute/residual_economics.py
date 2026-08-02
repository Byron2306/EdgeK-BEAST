from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .residual_contracts import ResidualRoute, sha256_digest, utc_now_iso, validate_non_negative_number


@dataclass(frozen=True, slots=True)
class ResidualCostObservation:
    route: ResidualRoute
    artifact_id: str
    workspace_id: str
    privacy_domain: str
    preparation_ms: float = 0.0
    lookup_ms: float = 0.0
    restoration_ms: float = 0.0
    execution_ms: float = 0.0
    verification_ms: float = 0.0
    memory_residency_byte_seconds: float = 0.0
    energy_joules: float = 0.0
    provider_cost: float = 0.0
    failure_retry_ms: float = 0.0
    avoided_fresh_compute_ms: float = 0.0
    avoided_provider_cost: float = 0.0
    prompt_tokens_avoided: int = 0
    provider_calls_avoided: int = 0
    successful_reuse: bool = False
    failed_reuse: bool = False
    evidence_digest: str = ""
    observed_at: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.workspace_id or not self.privacy_domain:
            raise ValueError("artifact_id, workspace_id and privacy_domain are required")
        for name in ("preparation_ms", "lookup_ms", "restoration_ms", "execution_ms", "verification_ms",
                     "memory_residency_byte_seconds", "energy_joules", "provider_cost", "failure_retry_ms",
                     "avoided_fresh_compute_ms", "avoided_provider_cost"):
            validate_non_negative_number(getattr(self, name), field_name=name)
        if self.prompt_tokens_avoided < 0 or self.provider_calls_avoided < 0:
            raise ValueError("avoided counters must be non-negative")
        if self.successful_reuse and self.failed_reuse:
            raise ValueError("reuse cannot be both successful and failed")
        if not self.observed_at:
            object.__setattr__(self, "observed_at", utc_now_iso())

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class EconomicsWeights:
    cpu_ms_value: float = 0.001
    memory_byte_second_cost: float = 1e-12
    energy_joule_cost: float = 0.00001
    failed_reuse_penalty: float = 0.05


@dataclass(frozen=True, slots=True)
class EconomicsDelta:
    artifact_id: str
    gross_avoided_value: float
    incurred_cost: float
    net_value: float
    preparation_debt_added: float
    realized_value: float
    observation_digest: str
    components: Mapping[str, float]


class ResidualEconomics:
    def __init__(self, weights: EconomicsWeights | None = None) -> None:
        self.weights = weights or EconomicsWeights()

    def evaluate(self, obs: ResidualCostObservation) -> EconomicsDelta:
        w = self.weights
        avoided_compute = obs.avoided_fresh_compute_ms * w.cpu_ms_value
        gross = avoided_compute + obs.avoided_provider_cost
        prep = obs.preparation_ms * w.cpu_ms_value
        runtime = (obs.lookup_ms + obs.restoration_ms + obs.execution_ms + obs.verification_ms + obs.failure_retry_ms) * w.cpu_ms_value
        residency = obs.memory_residency_byte_seconds * w.memory_byte_second_cost
        energy = obs.energy_joules * w.energy_joule_cost
        provider = obs.provider_cost
        failure = w.failed_reuse_penalty if obs.failed_reuse else 0.0
        incurred = prep + runtime + residency + energy + provider + failure
        net = gross - incurred
        components = {
            "avoided_compute": avoided_compute,
            "avoided_provider": obs.avoided_provider_cost,
            "preparation": prep,
            "runtime": runtime,
            "memory_residency": residency,
            "energy": energy,
            "provider": provider,
            "failed_reuse": failure,
        }
        return EconomicsDelta(obs.artifact_id, gross, incurred, net, prep, max(0.0, net), obs.digest, components)
