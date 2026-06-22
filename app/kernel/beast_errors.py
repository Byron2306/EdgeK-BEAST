"""Typed Error Hierarchy + Circuit Breaker for BEAST.

Never swallow exceptions. Never silently suppress.
All public methods should raise or return typed errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class BeastError(Exception):
    """Base class for all BEAST errors."""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()


class OllamaUnavailable(BeastError):
    """Ollama is not reachable or returned an error."""
    pass


class LedgerCorrupt(BeastError):
    """Compute ledger or scheduler state is corrupted."""
    pass


class AblationTimeout(BeastError):
    """Ablation run exceeded the configured timeout."""
    pass


class KVTransportError(BeastError):
    """Error during KV cache movement, compression, or lookup."""
    pass


class ForgeNodeError(BeastError):
    """Error reported by a Compute Forge Node."""
    pass


class SchedulerError(BeastError):
    """Error in the distributed forge scheduler."""
    pass


class ConfigurationError(BeastError):
    """Invalid or missing configuration."""
    pass


# --- Circuit Breaker ---

@dataclass
class CircuitBreakerState:
    """State for a simple circuit breaker."""
    failures: int = 0
    last_failure: Optional[str] = None
    open_until: Optional[str] = None


class CircuitBreaker:
    """Simple circuit breaker for external calls (Ollama, etc.)."""

    def __init__(self, threshold: int = 3, timeout_seconds: int = 30):
        self.threshold = threshold
        self.timeout_seconds = timeout_seconds
        self.state = CircuitBreakerState()

    def record_success(self) -> None:
        self.state.failures = 0
        self.state.open_until = None

    def record_failure(self) -> None:
        from datetime import datetime, timezone, timedelta
        self.state.failures += 1
        self.state.last_failure = datetime.now(timezone.utc).isoformat()
        if self.state.failures >= self.threshold:
            self.state.open_until = (datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds)).isoformat()

    def is_open(self) -> bool:
        if self.state.open_until is None:
            return False
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat() < self.state.open_until

    def call(self, func, *args, **kwargs):
        """Execute func if circuit is closed; raise if open."""
        if self.is_open():
            raise OllamaUnavailable(
                "Circuit breaker open",
                context={"open_until": self.state.open_until, "failures": self.state.failures}
            )
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise OllamaUnavailable(str(e), context={"original_error": str(e)}) from e