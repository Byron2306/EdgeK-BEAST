"""Paired, verifier-gated economics for promoted deterministic recurrence."""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Any, Mapping, Sequence

from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class WorkMeasurement:
    route: str
    provider_calls: int
    provider_tokens: int
    latency_ms: float
    repair_steps: int = 0
    cpu_ms: float = 0.0
    memory_byte_ms: float = 0.0
    io_bytes: int = 0
    energy_joules: float | None = None
    pressure_score: float | None = None
    sensing_ms: float = 0.0
    applicability_ms: float = 0.0
    authorization_ms: float = 0.0
    replay_ms: float = 0.0
    verification_ms: float = 0.0
    provider_cost_usd: float = 0.0
    postcondition_digest: str = ""
    verifier_digest: str = ""
    policy_generation: str = ""
    initial_state_digest: str = ""
    task_digest: str = ""

    @property
    def governance_overhead_ms(self) -> float:
        return sum((self.sensing_ms, self.applicability_ms, self.authorization_ms,
                    self.replay_ms, self.verification_ms))


@dataclass(frozen=True)
class PairedOccurrence:
    occurrence_id: str
    baseline: WorkMeasurement
    recurrence: WorkMeasurement
    mutation_invalidated: bool = False
    false_hit: bool = False
    demoted: bool = False
    negative_outcome: bool = False


class DisplacementEconomics:
    """Accept displacement only when paired work is equivalent and net-positive."""

    REQUIRED_BINDINGS = ("task_digest", "initial_state_digest", "verifier_digest", "policy_generation")

    @classmethod
    def evaluate(cls, occurrences: Sequence[PairedOccurrence], *, setup_cost_usd: float = 0.0,
                 setup_latency_ms: float = 0.0, confidence: float = 0.95,
                 measurement_scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if len(occurrences) < 2:
            raise ValueError("paired displacement requires repeated occurrences")
        if not 0.5 <= confidence < 1:
            raise ValueError("confidence must be in [0.5, 1)")
        valid: list[PairedOccurrence] = []
        rejected: list[dict[str, str]] = []
        for item in occurrences:
            reason = cls._equivalence_failure(item)
            if reason:
                rejected.append({"occurrence_id": item.occurrence_id, "reason": reason})
            else:
                valid.append(item)
        if not valid:
            raise PermissionError("no behaviorally equivalent paired occurrences")
        call_delta = [x.baseline.provider_calls - x.recurrence.provider_calls for x in valid]
        token_delta = [x.baseline.provider_tokens - x.recurrence.provider_tokens for x in valid]
        latency_delta = [x.baseline.latency_ms - x.recurrence.latency_ms for x in valid]
        cost_delta = [x.baseline.provider_cost_usd - x.recurrence.provider_cost_usd for x in valid]
        overhead = [x.recurrence.governance_overhead_ms for x in valid]
        net_latency = [saved - moved for saved, moved in zip(latency_delta, overhead)]
        mean_cost = statistics.fmean(cost_delta)
        mean_net_latency = statistics.fmean(net_latency)
        break_even_occurrences = math.ceil(setup_cost_usd / mean_cost) if mean_cost > 0 else None
        latency_break_even = math.ceil(setup_latency_ms / mean_net_latency) if mean_net_latency > 0 else None
        payload: dict[str, Any] = {
            "beast_object_type": "verified_displacement_economics_receipt",
            "version": "1.0", "paired_occurrences": len(occurrences), "equivalent_occurrences": len(valid),
            "measurement_scope": dict(measurement_scope or {}),
            "rejected_occurrences": rejected,
            "provider_calls_avoided": sum(call_delta), "provider_tokens_avoided": sum(token_delta),
            "provider_cost_avoided_usd": round(sum(cost_delta), 9),
            "latency_avoided_ms_gross": round(sum(latency_delta), 6),
            "work_moved_locally": {
                "cpu_ms": round(sum(x.recurrence.cpu_ms for x in valid), 6),
                "memory_byte_ms": round(sum(x.recurrence.memory_byte_ms for x in valid), 3),
                "io_bytes": sum(x.recurrence.io_bytes for x in valid),
                "energy_joules": cls._optional_sum(x.recurrence.energy_joules for x in valid),
                "pressure_score": cls._optional_sum(x.recurrence.pressure_score for x in valid),
                "governance_and_verification_ms": round(sum(overhead), 6),
            },
            "net_latency_displacement_ms": round(sum(net_latency) - setup_latency_ms, 6),
            "setup_cost_usd": setup_cost_usd, "setup_latency_ms": setup_latency_ms,
            "break_even_occurrences_cost": break_even_occurrences,
            "break_even_occurrences_latency": latency_break_even,
            "confidence_intervals": {
                "confidence": confidence,
                "calls_per_occurrence": cls._mean_ci(call_delta, confidence),
                "tokens_per_occurrence": cls._mean_ci(token_delta, confidence),
                "net_latency_ms_per_occurrence": cls._mean_ci(net_latency, confidence),
                "cost_usd_per_occurrence": cls._mean_ci(cost_delta, confidence),
            },
            "mutation_invalidation": {
                "tested": any(x.mutation_invalidated for x in occurrences),
                "invalidations": sum(x.mutation_invalidated for x in occurrences),
            },
            "impact_feedback": {
                "verified_displacements": len(valid), "false_hits": sum(x.false_hit for x in occurrences),
                "demotions": sum(x.demoted for x in occurrences),
                "negative_outcomes": sum(x.negative_outcome for x in occurrences),
            },
        }
        payload["net_positive"] = bool(sum(call_delta) > 0 and sum(token_delta) >= 0 and
                                       sum(cost_delta) - setup_cost_usd >= 0 and
                                       payload["mutation_invalidation"]["tested"])
        payload["receipt_digest"] = content_hash(payload)
        return payload

    @classmethod
    def validate(cls, receipt: Mapping[str, Any]) -> None:
        body = dict(receipt); supplied = str(body.pop("receipt_digest", ""))
        if supplied != content_hash(body):
            raise ValueError("displacement receipt is tampered")
        if receipt.get("net_positive") is not True or int(receipt.get("provider_calls_avoided") or 0) < 1:
            raise PermissionError("displacement receipt does not prove net avoided work")
        if not (receipt.get("mutation_invalidation") or {}).get("tested"):
            raise PermissionError("mutation invalidation was not tested")

    @classmethod
    def _equivalence_failure(cls, item: PairedOccurrence) -> str:
        for field in cls.REQUIRED_BINDINGS:
            if not getattr(item.baseline, field) or getattr(item.baseline, field) != getattr(item.recurrence, field):
                return "binding_mismatch:" + field
        if not item.baseline.postcondition_digest or item.baseline.postcondition_digest != item.recurrence.postcondition_digest:
            return "behavioral_postcondition_mismatch"
        if item.false_hit or item.demoted or item.negative_outcome:
            return "negative_routing_outcome"
        return ""

    @staticmethod
    def _optional_sum(values: Any) -> float | None:
        present = [float(value) for value in values if value is not None]
        return round(sum(present), 6) if present else None

    @staticmethod
    def _mean_ci(values: Sequence[float | int], confidence: float) -> dict[str, float]:
        mean = statistics.fmean(values)
        if len(values) < 2:
            return {"mean": mean, "low": mean, "high": mean}
        # Conservative normal approximation; receipt names the method explicitly.
        z = 1.959963984540054 if confidence >= 0.95 else 1.6448536269514722
        margin = z * statistics.stdev(values) / math.sqrt(len(values))
        return {"mean": round(mean, 9), "low": round(mean - margin, 9),
                "high": round(mean + margin, 9), "method": "normal_mean"}
