"""Idle-only, value-prioritized speculative prefill scheduler."""
from __future__ import annotations

import itertools
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PrefillCandidate:
    candidate_id: str
    value_score: float
    request: Any
    expires_at: float


class ForgeKVPrefillScheduler:
    def __init__(self, execute: Callable[[Any], Any], *, idle_probe: Callable[[], bool], pressure_probe: Callable[[], str], capacity: int = 128):
        self.execute = execute
        self.idle_probe = idle_probe
        self.pressure_probe = pressure_probe
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max(1, capacity))
        self._counter = itertools.count()
        self._closed = False
        self._metrics = {"submitted": 0, "completed": 0, "expired": 0, "deferred_busy": 0, "deferred_pressure": 0, "rejected": 0}
        self._thread = threading.Thread(target=self._run, name="beast-forge-kv-prefill", daemon=True)
        self._thread.start()

    def submit(self, candidate: PrefillCandidate) -> Future:
        future: Future = Future()
        try:
            self._queue.put_nowait((-float(candidate.value_score), next(self._counter), candidate, future))
            self._metrics["submitted"] += 1
        except queue.Full as exc:
            self._metrics["rejected"] += 1
            future.set_exception(exc)
        return future

    def _run(self) -> None:
        while not self._closed:
            try:
                priority, order, candidate, future = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if time.time() >= candidate.expires_at:
                    self._metrics["expired"] += 1
                    future.set_exception(TimeoutError("prefill candidate expired"))
                    continue
                pressure = self.pressure_probe()
                if pressure not in {"low", "unknown"}:
                    self._metrics["deferred_pressure"] += 1
                    self._queue.put((priority, order, candidate, future)); time.sleep(0.1); continue
                if not self.idle_probe():
                    self._metrics["deferred_busy"] += 1
                    self._queue.put((priority, order, candidate, future)); time.sleep(0.1); continue
                if future.set_running_or_notify_cancel():
                    future.set_result(self.execute(candidate.request))
                    self._metrics["completed"] += 1
            except Exception as exc:
                if not future.done(): future.set_exception(exc)
            finally:
                self._queue.task_done()

    def state(self) -> dict[str, Any]:
        return {"beast_object_type": "forge_kv_prefill_scheduler_state", "version": "1.0", "queue_depth": self._queue.qsize(), "metrics": dict(self._metrics), "authority": "speculative_context_preparation_only"}

    def close(self) -> None:
        self._closed = True
        self._thread.join(timeout=2.0)
