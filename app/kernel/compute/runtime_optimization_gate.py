"""Evidence gate for latency optimizations around local inference."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class RuntimeLaneMeasurement:
    lane: str
    prompt_eval_ms: float
    total_latency_ms: float
    verification_passed: bool
    measured: bool = True

    @classmethod
    def from_usage(cls, lane: str, usage: Mapping[str, Any], *, verification_passed: bool) -> "RuntimeLaneMeasurement":
        prompt_ns = usage.get("prompt_eval_duration_ns") or usage.get("prompt_eval_duration") or 0
        total_ns = usage.get("total_duration_ns") or usage.get("total_duration") or 0
        return cls(lane, float(prompt_ns) / 1_000_000, float(total_ns) / 1_000_000,
                   bool(verification_passed), bool(usage.get("measured", True)))


def summarize_lane(lane: str, samples: Iterable[RuntimeLaneMeasurement]) -> dict[str, Any]:
    rows = [item for item in samples if item.measured and item.lane == lane]
    if not rows:
        return {"lane": lane, "measured_samples": 0, "verification_rate": 0.0}
    return {
        "lane": lane, "measured_samples": len(rows),
        "median_prompt_eval_ms": round(statistics.median(item.prompt_eval_ms for item in rows), 3),
        "median_total_latency_ms": round(statistics.median(item.total_latency_ms for item in rows), 3),
        "verification_rate": round(sum(item.verification_passed for item in rows) / len(rows), 4),
    }


def evaluate_optimization(*, baseline: Iterable[RuntimeLaneMeasurement], candidate: Iterable[RuntimeLaneMeasurement], candidate_lane: str = "candidate", minimum_prefill_saving: float = 0.05) -> dict[str, Any]:
    base = summarize_lane("baseline", baseline)
    optimized = summarize_lane(candidate_lane, candidate)
    blockers: list[str] = []
    if not base.get("measured_samples"):
        blockers.append("baseline_not_measured")
    if not optimized.get("measured_samples"):
        blockers.append("candidate_not_measured")
    if not blockers:
        base_prefill = float(base["median_prompt_eval_ms"])
        candidate_prefill = float(optimized["median_prompt_eval_ms"])
        saving = (base_prefill - candidate_prefill) / max(base_prefill, 0.001)
        optimized["prefill_saving"] = round(saving, 4)
        if saving < float(minimum_prefill_saving):
            blockers.append("no_measurable_prefill_improvement")
        if float(optimized["verification_rate"]) < float(base["verification_rate"]):
            blockers.append("verification_regression")
    return {
        "status": "promote_runtime_route" if not blockers else "experimental_only",
        "baseline": base, "candidate": optimized, "blockers": blockers,
        "vector_or_kv_injection_authorized": False if blockers else True,
        "authority": "measurement_gate_only",
    }

