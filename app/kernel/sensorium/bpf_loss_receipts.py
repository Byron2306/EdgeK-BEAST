from __future__ import annotations
from dataclasses import dataclass
from threading import Lock
from .bpf_event_contracts import BPFHealthReceipt
import time

@dataclass
class _Counters:
    observed: int = 0
    emitted: int = 0
    kernel_reserve_failures: int = 0
    userspace_decode_failures: int = 0
    sequence_gaps: int = 0
    ring_poll_errors: int = 0

class LossLedger:
    """Monotonic, thread-safe accounting. Loss is evidence, never a log-only warning."""
    def __init__(self) -> None:
        self.started_ns = time.monotonic_ns()
        self._c = _Counters()
        self._lock = Lock()
        self._last_sequence: dict[int, int] = {}

    def observe_sequence(self, cpu: int, sequence: int) -> None:
        with self._lock:
            self._c.observed += 1
            previous = self._last_sequence.get(cpu)
            if previous is not None and sequence > previous + 1:
                self._c.sequence_gaps += sequence - previous - 1
            if previous is None or sequence > previous:
                self._last_sequence[cpu] = sequence

    def emitted(self) -> None:
        with self._lock: self._c.emitted += 1
    def kernel_loss(self, count: int = 1) -> None:
        with self._lock: self._c.kernel_reserve_failures += max(0, count)
    def decode_failure(self) -> None:
        with self._lock: self._c.userspace_decode_failures += 1
    def poll_error(self) -> None:
        with self._lock: self._c.ring_poll_errors += 1

    def receipt(self) -> BPFHealthReceipt:
        with self._lock:
            return BPFHealthReceipt(self.started_ns, **vars(self._c))
