from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from .cache_aware_engine_selector import CacheAwareEngineSelector, EngineSelection
from .residual_candidate import ResidualCandidate
from .residual_contracts import sha256_digest
from .residual_pressure_governor import InteractiveLaneState, PressureDecision, PressureSnapshot, ResidualPressureGovernor


class ConcurrencyController(Protocol):
    def set_limit(self, workers: int) -> None: ...


class SpeculativeController(Protocol):
    def cancel_speculative(self, reason: str) -> int: ...


class EvictionController(Protocol):
    def evict_cold(self, *, preserve_ids: set[str], maximum: int) -> int: ...


@dataclass(frozen=True, slots=True)
class WorkloadGovernanceReceipt:
    pressure: PressureDecision
    workers_before: int | None
    workers_after: int
    speculative_cancelled: int
    cold_contexts_evicted: int
    protected_artifacts: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class GovernedEngineSelection:
    selection: EngineSelection
    governance: WorkloadGovernanceReceipt


class PRISMR5WorkloadGovernor:
    def __init__(self, *, pressure_governor: ResidualPressureGovernor | None = None,
                 selector: CacheAwareEngineSelector | None = None,
                 concurrency: ConcurrencyController | None = None,
                 speculative: SpeculativeController | None = None,
                 eviction: EvictionController | None = None) -> None:
        self.pressure_governor = pressure_governor or ResidualPressureGovernor()
        self.selector = selector or CacheAwareEngineSelector()
        self.concurrency = concurrency
        self.speculative = speculative
        self.eviction = eviction

    def select(self, *, request_digest: str, workspace_id: str, privacy_domain: str,
               candidates: Iterable[ResidualCandidate], snapshot: PressureSnapshot,
               interactive: InteractiveLaneState | None = None,
               total_memory_bytes: int | None = None,
               protected_artifact_ids: Iterable[str] = (),
               minimum_quality: float = 0.0,
               maximum_monetary_cost: float | None = None,
               provider_allowed: bool = True) -> GovernedEngineSelection:
        pressure = self.pressure_governor.classify(snapshot, total_memory_bytes=total_memory_bytes, interactive=interactive)
        workers_before = getattr(self.concurrency, "limit", None) if self.concurrency is not None else None
        if self.concurrency is not None:
            self.concurrency.set_limit(pressure.recommended_workers)
        cancelled = 0
        if pressure.cancel_speculative_jobs and self.speculative is not None:
            cancelled = int(self.speculative.cancel_speculative("prism_r5_pressure:" + pressure.level.value))
        protected = set(protected_artifact_ids)
        evicted = 0
        if pressure.evict_cold_contexts and self.eviction is not None:
            evicted = int(self.eviction.evict_cold(preserve_ids=protected, maximum=16))
        shaped = [self.pressure_governor.shape_candidate(item, pressure) for item in candidates]
        selection = self.selector.select(
            request_digest=request_digest,
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            candidates=shaped,
            minimum_quality=minimum_quality,
            maximum_monetary_cost=maximum_monetary_cost,
            provider_allowed=provider_allowed,
        )
        core = {
            "pressure": pressure,
            "workers_before": workers_before,
            "workers_after": pressure.recommended_workers,
            "speculative_cancelled": cancelled,
            "cold_contexts_evicted": evicted,
            "protected_artifacts": sorted(protected),
            "decision_digest": selection.receipt.decision_digest,
        }
        receipt = WorkloadGovernanceReceipt(pressure, workers_before, pressure.recommended_workers,
                                             cancelled, evicted, tuple(sorted(protected)), sha256_digest(core))
        return GovernedEngineSelection(selection, receipt)
