from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Iterable
import time

from .residual_contracts import sha256_digest


@dataclass(frozen=True, slots=True)
class ProofCriticalPin:
    artifact_id: str
    workspace_id: str
    privacy_domain: str
    reason: str
    expires_at_ns: int
    created_at_ns: int
    evidence_digest: str

    @property
    def pin_digest(self) -> str:
        return sha256_digest(self)

    @property
    def expired(self) -> bool:
        return time.time_ns() >= self.expires_at_ns


class ProofCriticalPinRegistry:
    def __init__(self, *, max_pins: int = 128) -> None:
        self.max_pins = max(1, int(max_pins))
        self._lock = RLock()
        self._pins: dict[str, ProofCriticalPin] = {}

    def pin(self, *, artifact_id: str, workspace_id: str, privacy_domain: str, reason: str,
            ttl_seconds: float, evidence_digest: str) -> ProofCriticalPin:
        if ttl_seconds <= 0:
            raise ValueError("proof-critical pins require a positive bounded TTL")
        now = time.time_ns()
        pin = ProofCriticalPin(artifact_id, workspace_id, privacy_domain, reason,
                               now + int(ttl_seconds * 1_000_000_000), now, evidence_digest)
        with self._lock:
            self.prune()
            if artifact_id not in self._pins and len(self._pins) >= self.max_pins:
                raise OverflowError("proof-critical pin registry is full")
            self._pins[artifact_id] = pin
        return pin

    def unpin(self, artifact_id: str) -> bool:
        with self._lock:
            return self._pins.pop(artifact_id, None) is not None

    def prune(self) -> int:
        now = time.time_ns()
        with self._lock:
            stale = [key for key, pin in self._pins.items() if now >= pin.expires_at_ns]
            for key in stale:
                self._pins.pop(key, None)
            return len(stale)

    def is_pinned(self, artifact_id: str, *, workspace_id: str, privacy_domain: str) -> bool:
        with self._lock:
            pin = self._pins.get(artifact_id)
            if pin is None or pin.expired:
                self._pins.pop(artifact_id, None)
                return False
            return pin.workspace_id == workspace_id and pin.privacy_domain == privacy_domain

    def active(self) -> tuple[ProofCriticalPin, ...]:
        self.prune()
        with self._lock:
            return tuple(sorted(self._pins.values(), key=lambda item: item.artifact_id))
