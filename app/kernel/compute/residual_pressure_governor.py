from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
import os
import time

from .residual_candidate import ResidualCandidate
from .residual_contracts import ResidualRoute, sha256_digest
from .residual_refusal import ResidualRefusal, ResidualRefusalCode


class PressureLevel(str, Enum):
    LOW = "low"
    RISING = "rising"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PSIWindow:
    avg10: float = 0.0
    avg60: float = 0.0
    avg300: float = 0.0
    total_us: int = 0


@dataclass(frozen=True, slots=True)
class PSIResource:
    some: PSIWindow = PSIWindow()
    full: PSIWindow | None = None


@dataclass(frozen=True, slots=True)
class PressureSnapshot:
    cpu: PSIResource
    memory: PSIResource
    io: PSIResource
    available_memory_bytes: int | None = None
    swap_free_bytes: int | None = None
    load1: float | None = None
    cpu_count: int = 1
    forge_queue_depth: int = 0
    forge_worker_saturation: float = 0.0
    ollama_resident_bytes: int = 0
    observed_at_ns: int = field(default_factory=time.time_ns)
    source: str = "linux_procfs"

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class PressureThresholds:
    rising_some_avg10: float = 5.0
    high_some_avg10: float = 20.0
    critical_some_avg10: float = 50.0
    high_full_avg10: float = 5.0
    critical_full_avg10: float = 20.0
    rising_worker_saturation: float = 0.70
    high_worker_saturation: float = 0.90
    critical_worker_saturation: float = 0.98
    low_memory_ratio_high: float = 0.08
    low_memory_ratio_critical: float = 0.03


class LinuxPSIReader:
    def __init__(self, proc_root: str | os.PathLike[str] = "/proc") -> None:
        self.proc_root = Path(proc_root)

    @staticmethod
    def _parse_psi(text: str) -> PSIResource:
        rows: dict[str, PSIWindow] = {}
        for raw in text.splitlines():
            parts = raw.strip().split()
            if not parts:
                continue
            kind = parts[0]
            values: dict[str, str] = {}
            for item in parts[1:]:
                if "=" in item:
                    key, value = item.split("=", 1)
                    values[key] = value
            rows[kind] = PSIWindow(
                avg10=float(values.get("avg10", 0.0)),
                avg60=float(values.get("avg60", 0.0)),
                avg300=float(values.get("avg300", 0.0)),
                total_us=int(values.get("total", 0)),
            )
        return PSIResource(some=rows.get("some", PSIWindow()), full=rows.get("full"))

    def _read_pressure(self, name: str) -> PSIResource:
        path = self.proc_root / "pressure" / name
        try:
            return self._parse_psi(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return PSIResource()

    def _read_meminfo(self) -> tuple[int | None, int | None]:
        try:
            values: dict[str, int] = {}
            for line in (self.proc_root / "meminfo").read_text(encoding="utf-8").splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0]) * 1024
            return values.get("MemAvailable"), values.get("SwapFree")
        except (OSError, ValueError, IndexError):
            return None, None

    def read(self, *, forge_queue_depth: int = 0, forge_worker_saturation: float = 0.0,
             ollama_resident_bytes: int = 0) -> PressureSnapshot:
        available, swap_free = self._read_meminfo()
        try:
            load1 = os.getloadavg()[0]
        except OSError:
            load1 = None
        return PressureSnapshot(
            cpu=self._read_pressure("cpu"),
            memory=self._read_pressure("memory"),
            io=self._read_pressure("io"),
            available_memory_bytes=available,
            swap_free_bytes=swap_free,
            load1=load1,
            cpu_count=os.cpu_count() or 1,
            forge_queue_depth=max(0, int(forge_queue_depth)),
            forge_worker_saturation=max(0.0, min(1.0, float(forge_worker_saturation))),
            ollama_resident_bytes=max(0, int(ollama_resident_bytes)),
        )


@dataclass(frozen=True, slots=True)
class InteractiveLaneState:
    healthy: bool
    latency_ms: float
    latency_budget_ms: float
    active_missions: int = 0
    queue_depth: int = 0
    reason: str = ""

    @property
    def overloaded(self) -> bool:
        return (not self.healthy) or self.latency_ms > self.latency_budget_ms


@dataclass(frozen=True, slots=True)
class PressureDecision:
    level: PressureLevel
    allow_speculative_prefill: bool
    allow_demand_context_creation: bool
    allow_context_reuse: bool
    recommended_workers: int
    cancel_speculative_jobs: bool
    evict_cold_contexts: bool
    prefer_smaller_local_models: bool
    consider_provider_fallback: bool
    retain_proof_critical: bool
    reasons: tuple[str, ...]
    snapshot_digest: str


class ResidualPressureGovernor:
    def __init__(self, thresholds: PressureThresholds | None = None, *, max_workers: int = 2) -> None:
        self.thresholds = thresholds or PressureThresholds()
        self.max_workers = max(1, int(max_workers))

    @staticmethod
    def _max_some(snapshot: PressureSnapshot) -> float:
        return max(snapshot.cpu.some.avg10, snapshot.memory.some.avg10, snapshot.io.some.avg10)

    @staticmethod
    def _max_full(snapshot: PressureSnapshot) -> float:
        values = [r.full.avg10 for r in (snapshot.cpu, snapshot.memory, snapshot.io) if r.full is not None]
        return max(values, default=0.0)

    def classify(self, snapshot: PressureSnapshot, *, total_memory_bytes: int | None = None,
                 interactive: InteractiveLaneState | None = None) -> PressureDecision:
        t = self.thresholds
        some = self._max_some(snapshot)
        full = self._max_full(snapshot)
        memory_ratio = None
        if total_memory_bytes and snapshot.available_memory_bytes is not None and total_memory_bytes > 0:
            memory_ratio = snapshot.available_memory_bytes / total_memory_bytes
        reasons: list[str] = []
        level = PressureLevel.LOW
        if some >= t.critical_some_avg10 or full >= t.critical_full_avg10 or snapshot.forge_worker_saturation >= t.critical_worker_saturation:
            level = PressureLevel.CRITICAL
            reasons.append("critical PSI or worker saturation")
        elif memory_ratio is not None and memory_ratio <= t.low_memory_ratio_critical:
            level = PressureLevel.CRITICAL
            reasons.append("critically low available memory")
        elif some >= t.high_some_avg10 or full >= t.high_full_avg10 or snapshot.forge_worker_saturation >= t.high_worker_saturation:
            level = PressureLevel.HIGH
            reasons.append("high PSI or worker saturation")
        elif memory_ratio is not None and memory_ratio <= t.low_memory_ratio_high:
            level = PressureLevel.HIGH
            reasons.append("low available memory")
        elif some >= t.rising_some_avg10 or snapshot.forge_worker_saturation >= t.rising_worker_saturation:
            level = PressureLevel.RISING
            reasons.append("rising PSI or worker saturation")
        if interactive and interactive.overloaded:
            if level in (PressureLevel.LOW, PressureLevel.RISING):
                level = PressureLevel.HIGH
            reasons.append("interactive lane is outside latency budget")
        if not reasons:
            reasons.append("pressure within low operating envelope")

        if level is PressureLevel.LOW:
            return PressureDecision(level, True, True, True, self.max_workers, False, False, False, False, True, tuple(reasons), snapshot.digest)
        if level is PressureLevel.RISING:
            return PressureDecision(level, False, True, True, max(1, self.max_workers // 2), False, False, False, False, True, tuple(reasons), snapshot.digest)
        if level is PressureLevel.HIGH:
            return PressureDecision(level, False, False, True, 1, True, True, True, False, True, tuple(reasons), snapshot.digest)
        return PressureDecision(level, False, False, True, 0, True, True, True, True, True, tuple(reasons), snapshot.digest)

    def shape_candidate(self, candidate: ResidualCandidate, decision: PressureDecision) -> ResidualCandidate:
        metadata = dict(candidate.metadata or {})
        base_penalty = float(metadata.get("pressure_penalty", 0.0))
        multiplier = {
            PressureLevel.LOW: 0.0,
            PressureLevel.RISING: 150.0,
            PressureLevel.HIGH: 650.0,
            PressureLevel.CRITICAL: 1800.0,
            PressureLevel.UNKNOWN: 100.0,
        }[decision.level]
        memory_mib = candidate.predicted_memory_bytes / (1024 * 1024)
        route_factor = {
            ResidualRoute.NATIVE_CONTEXT: 0.45,
            ResidualRoute.PREFIX_REPLAY: 0.65,
            ResidualRoute.WARM_MODEL: 0.80,
            ResidualRoute.FRESH_OLLAMA: 1.25,
            ResidualRoute.FRESH_LLAMA_CPP: 1.0,
            ResidualRoute.PROVIDER: 0.05,
        }.get(candidate.route, 1.0)
        metadata.update({
            "pressure_level": decision.level.value,
            "pressure_snapshot_digest": decision.snapshot_digest,
            "pressure_penalty": base_penalty + multiplier * route_factor + memory_mib * route_factor,
            "recommended_workers": decision.recommended_workers,
        })
        if decision.level in (PressureLevel.HIGH, PressureLevel.CRITICAL) and candidate.route in {
            ResidualRoute.PREFIX_REPLAY, ResidualRoute.WARM_MODEL
        } and bool(metadata.get("requires_new_context", False)):
            return candidate.refuse(ResidualRefusal(
                code=ResidualRefusalCode.PRESSURE_REJECTED,
                message="new reusable context creation refused under pressure",
                evidence_digest=sha256_digest({"candidate": candidate.candidate_id, "decision": decision}),
            ))
        if decision.level is PressureLevel.CRITICAL and candidate.route is ResidualRoute.FRESH_OLLAMA and candidate.predicted_memory_bytes > 0:
            return candidate.refuse(ResidualRefusal(
                code=ResidualRefusalCode.PRESSURE_REJECTED,
                message="fresh Ollama inference refused under critical pressure",
                evidence_digest=sha256_digest({"candidate": candidate.candidate_id, "decision": decision}),
            ))
        return replace(candidate, metadata=metadata)
