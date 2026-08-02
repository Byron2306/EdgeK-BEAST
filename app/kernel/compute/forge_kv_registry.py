"""Thread-safe Forge KV state and in-flight reservation registry."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, RLock
from typing import Any, Dict, Optional


@dataclass
class ForgeKVReservation:
    cache_id: str
    state: str = "preparing"
    waiters: int = 0
    error: str = ""


class ForgeKVRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._reservations: Dict[str, ForgeKVReservation] = {}

    def reserve(self, cache_id: str) -> bool:
        """Return True only for the caller that owns ABSENT -> PREPARING."""
        with self._condition:
            current = self._reservations.get(cache_id)
            if current and current.state == "preparing":
                current.waiters += 1
                return False
            self._reservations[cache_id] = ForgeKVReservation(cache_id=cache_id)
            return True

    def complete(self, cache_id: str, *, error: str = "") -> None:
        with self._condition:
            current = self._reservations.setdefault(cache_id, ForgeKVReservation(cache_id))
            current.state = "failed" if error else "ready"
            current.error = error
            self._condition.notify_all()

    def wait(self, cache_id: str, timeout: float = 60.0) -> Optional[ForgeKVReservation]:
        with self._condition:
            self._condition.wait_for(
                lambda: cache_id not in self._reservations or self._reservations[cache_id].state != "preparing",
                timeout=max(0.0, timeout),
            )
            return self._reservations.get(cache_id)

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "beast_object_type": "forge_kv_registry_state",
                "version": "1.0",
                "reservations": {
                    key: {"state": value.state, "waiters": value.waiters, "error": value.error}
                    for key, value in self._reservations.items()
                },
                "authority": "context_coordination_only",
            }
