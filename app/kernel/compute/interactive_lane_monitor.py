from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Deque
import statistics
import time

from .residual_pressure_governor import InteractiveLaneState


@dataclass(frozen=True, slots=True)
class InteractiveSample:
    latency_ms: float
    active_missions: int
    queue_depth: int
    observed_at_ns: int


class InteractiveLaneMonitor:
    def __init__(self, *, latency_budget_ms: float = 250.0, window: int = 32) -> None:
        if latency_budget_ms <= 0 or window <= 0:
            raise ValueError("latency budget and window must be positive")
        self.latency_budget_ms = float(latency_budget_ms)
        self._samples: Deque[InteractiveSample] = deque(maxlen=int(window))
        self._lock = RLock()

    def observe(self, latency_ms: float, *, active_missions: int = 0, queue_depth: int = 0) -> None:
        with self._lock:
            self._samples.append(InteractiveSample(max(0.0, float(latency_ms)), max(0, active_missions),
                                                   max(0, queue_depth), time.time_ns()))

    def state(self) -> InteractiveLaneState:
        with self._lock:
            samples = tuple(self._samples)
        if not samples:
            return InteractiveLaneState(True, 0.0, self.latency_budget_ms, reason="no interactive samples")
        latencies = [item.latency_ms for item in samples]
        p95_index = max(0, min(len(latencies) - 1, int(round((len(latencies) - 1) * 0.95))))
        p95 = sorted(latencies)[p95_index]
        latest = samples[-1]
        healthy = p95 <= self.latency_budget_ms and latest.queue_depth < 8
        reason = "within latency budget" if healthy else "p95 latency or queue depth exceeded budget"
        return InteractiveLaneState(healthy, p95, self.latency_budget_ms, latest.active_missions, latest.queue_depth, reason)
