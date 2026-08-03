from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .residual_contracts import sha256_digest


class MeasurementRoute(str, Enum):
    RAW_LOCAL_MODEL = "raw_local_model"
    RAG_PLUS_MODEL = "rag_plus_model"
    BEAST_CACHE = "beast_cache"
    MEANING_CRYSTALS = "meaning_crystals"
    MEANING_CRYSTALS_WITH_BOUNDED_LEXICALIZATION = "meaning_crystals_with_bounded_lexicalization"


@dataclass(frozen=True, slots=True)
class MeasurementObservation:
    route: MeasurementRoute
    case_id: str
    resolved: bool
    correct: bool
    false_reuse: bool
    unsupported_assumptions: int
    stale_reuse_rejected: bool
    latency_ms: float
    cpu_ms: float
    memory_bytes: int
    tokens: int
    provider_calls: int

    def __post_init__(self) -> None:
        if not isinstance(self.route, MeasurementRoute):
            object.__setattr__(self, "route", MeasurementRoute(self.route))
        if not self.case_id.strip():
            raise ValueError("measurement observations require case_id")
        if min(self.unsupported_assumptions, self.memory_bytes, self.tokens, self.provider_calls) < 0:
            raise ValueError("measurement counters must be non-negative")
        if min(self.latency_ms, self.cpu_ms) < 0:
            raise ValueError("measurement timings must be non-negative")


@dataclass(frozen=True, slots=True)
class RouteMeasurement:
    route: MeasurementRoute
    case_count: int
    resolution_accuracy: float
    false_reuse: int
    unsupported_assumptions: int
    avg_latency_ms: float
    total_cpu_ms: float
    peak_memory_bytes: int
    total_tokens: int
    provider_calls: int
    cache_invalidation_correctness: float


@dataclass(frozen=True, slots=True)
class SynthesisMeasurementReport:
    route_measurements: tuple[RouteMeasurement, ...]
    passed: bool
    notes: tuple[str, ...]

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


REQUIRED_ROUTES = tuple(route for route in MeasurementRoute)


def run_synthesis_measurement_protocol(
    observations: tuple[MeasurementObservation, ...],
    *,
    minimum_cases_per_route: int = 1,
) -> SynthesisMeasurementReport:
    if minimum_cases_per_route <= 0:
        raise ValueError("minimum_cases_per_route must be positive")
    grouped: dict[MeasurementRoute, list[MeasurementObservation]] = {route: [] for route in REQUIRED_ROUTES}
    for item in observations:
        grouped[item.route].append(item)
    missing = [route.value for route, rows in grouped.items() if len(rows) < minimum_cases_per_route]
    measurements = tuple(_measure(route, tuple(grouped[route])) for route in REQUIRED_ROUTES if grouped[route])
    notes = []
    if missing:
        notes.append("missing minimum observations for routes: " + ", ".join(missing))
    if any(item.false_reuse for item in observations):
        notes.append("false reuse observed")
    if any(item.unsupported_assumptions for item in observations):
        notes.append("unsupported assumptions observed")
    return SynthesisMeasurementReport(
        route_measurements=measurements,
        passed=not notes,
        notes=tuple(notes),
    )


def _measure(route: MeasurementRoute, rows: tuple[MeasurementObservation, ...]) -> RouteMeasurement:
    case_count = len(rows)
    correct = sum(1 for item in rows if item.resolved and item.correct)
    stale_cases = [item for item in rows if item.stale_reuse_rejected or item.false_reuse]
    invalidation = (
        sum(1 for item in stale_cases if item.stale_reuse_rejected and not item.false_reuse) / len(stale_cases)
        if stale_cases else 1.0
    )
    return RouteMeasurement(
        route=route,
        case_count=case_count,
        resolution_accuracy=correct / case_count if case_count else 0.0,
        false_reuse=sum(1 for item in rows if item.false_reuse),
        unsupported_assumptions=sum(item.unsupported_assumptions for item in rows),
        avg_latency_ms=sum(item.latency_ms for item in rows) / case_count if case_count else 0.0,
        total_cpu_ms=sum(item.cpu_ms for item in rows),
        peak_memory_bytes=max((item.memory_bytes for item in rows), default=0),
        total_tokens=sum(item.tokens for item in rows),
        provider_calls=sum(item.provider_calls for item in rows),
        cache_invalidation_correctness=invalidation,
    )
