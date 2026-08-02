from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .residual_candidate import ResidualCandidate
from .residual_contracts import ApplicabilityState, ResidualAuthority, ResidualRoute, VerificationState, sha256_digest
from .residual_refusal import ResidualRefusal, ResidualRefusalCode


@dataclass(frozen=True, slots=True)
class EngineObservation:
    candidate_id: str
    route: ResidualRoute
    configured: bool
    compatible: bool
    workspace_id: str
    privacy_domain: str
    predicted_latency_ms: float
    predicted_cpu_ms: float
    predicted_memory_bytes: int
    expected_quality: float
    confidence: float = 1.0
    failure_probability: float = 0.0
    monetary_cost: float = 0.0
    energy_joules: float | None = None
    restoration_cost_ms: float = 0.0
    pressure_penalty: float = 0.0
    evidence: Mapping[str, Any] | None = None


class EngineCandidateAdapter:
    _authorities = {
        ResidualRoute.NATIVE_CONTEXT: ResidualAuthority.CONTEXT_ONLY,
        ResidualRoute.PREFIX_REPLAY: ResidualAuthority.CONTEXT_ONLY,
        ResidualRoute.WARM_MODEL: ResidualAuthority.CONTEXT_ONLY,
        ResidualRoute.FRESH_OLLAMA: ResidualAuthority.INFERENCE_ONLY,
        ResidualRoute.FRESH_LLAMA_CPP: ResidualAuthority.INFERENCE_ONLY,
        ResidualRoute.PROVIDER: ResidualAuthority.PROVIDER_CALL,
    }

    def adapt(self, observation: EngineObservation) -> ResidualCandidate:
        if observation.route not in self._authorities:
            raise ValueError(f"unsupported inference route: {observation.route.value}")
        refusal = None
        state = ApplicabilityState.APPLICABLE
        verification = VerificationState.VERIFIED
        if not observation.configured:
            state = ApplicabilityState.INAPPLICABLE
            verification = VerificationState.UNVERIFIED
            refusal = ResidualRefusal(
                code=ResidualRefusalCode.ENGINE_UNAVAILABLE,
                message="engine or route is not configured",
                evidence_digest=sha256_digest({"candidate_id": observation.candidate_id, "configured": False}),
            )
        elif not observation.compatible:
            state = ApplicabilityState.INAPPLICABLE
            verification = VerificationState.UNVERIFIED
            refusal = ResidualRefusal(
                code=ResidualRefusalCode.INCOMPATIBLE,
                message="engine route is incompatible with the request identity",
                evidence_digest=sha256_digest({"candidate_id": observation.candidate_id, "compatible": False}),
            )
        metadata = {
            "restoration_cost_ms": observation.restoration_cost_ms,
            "pressure_penalty": observation.pressure_penalty,
            "engine_evidence": dict(observation.evidence or {}),
        }
        return ResidualCandidate(
            candidate_id=observation.candidate_id,
            route=observation.route,
            applicability=state,
            verification=verification,
            authority=self._authorities[observation.route],
            predicted_latency_ms=observation.predicted_latency_ms,
            predicted_cpu_ms=observation.predicted_cpu_ms,
            predicted_memory_bytes=observation.predicted_memory_bytes,
            predicted_monetary_cost=observation.monetary_cost,
            predicted_energy_joules=observation.energy_joules,
            confidence=observation.confidence,
            expected_quality=observation.expected_quality,
            failure_probability=observation.failure_probability,
            workspace_id=observation.workspace_id,
            privacy_domain=observation.privacy_domain,
            evidence_digest=sha256_digest({"observation": observation}),
            refusal=refusal,
            metadata=metadata,
        )
