"""Measure verified local crystal displacement of remote/probabilistic work."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class DisplacementReceipt:
    crystal_id: str
    provider_calls_avoided: int
    repair_steps_avoided: int
    latency_ms: float
    cpu_ms: float
    memory_mb: float
    verification_passed: bool
    displaced: bool


class DisplacementEvaluator:
    def run(self, crystal_id: str, execute_local: Callable[[], Mapping[str, Any]], *, provider_calls: int = 1, repair_steps: int = 0) -> DisplacementReceipt:
        result = dict(execute_local())
        verified = result.get("verification_passed") is True
        return DisplacementReceipt(
            crystal_id, provider_calls if verified else 0, repair_steps if verified else 0,
            float(result.get("latency_ms", 0.0)), float(result.get("cpu_ms", 0.0)),
            float(result.get("memory_mb", 0.0)), verified, verified,
        )

