from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any, Callable, Mapping


def _digest(value: Mapping[str, Any]) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()

@dataclass(frozen=True, slots=True)
class CapsuleEconomicsReceipt:
    capsule_id: str
    preparation_debt_ms: float
    avoided_recompile_ms: float
    residency_cost_ms: float
    verification_cost_ms: float
    net_value_ms: float
    break_even: bool
    credit_eligible: bool
    receipt_digest: str

class CapsuleEconomicsBridge:
    """Translate capsule use into an R6-style measured economics observation."""
    def __init__(self, sink: Callable[[Mapping[str, Any]], str] | None = None):
        self.sink = sink
    def record(self, *, capsule_id: str, preparation_debt_ms: float, avoided_recompile_ms: float,
               residency_cost_ms: float, verification_cost_ms: float, execution_succeeded: bool,
               reuse_count: int) -> CapsuleEconomicsReceipt:
        values = [preparation_debt_ms, avoided_recompile_ms, residency_cost_ms, verification_cost_ms]
        if any(v < 0 for v in values):
            raise ValueError('economics values must be non-negative')
        incurred = preparation_debt_ms + residency_cost_ms + verification_cost_ms
        gross = avoided_recompile_ms if execution_succeeded else 0.0
        net = gross - incurred
        break_even = execution_succeeded and reuse_count > 0 and net >= 0
        body = {
            'artifact_id': capsule_id,
            'artifact_type': 'sealed_crystal_capsule',
            'preparation_cost_ms': preparation_debt_ms,
            'avoided_fresh_compute_ms': gross,
            'memory_residency_cost_ms': residency_cost_ms,
            'verification_cost_ms': verification_cost_ms,
            'successful_reuse': bool(execution_succeeded),
            'reuse_count': int(reuse_count),
            'net_value_ms': net,
            'break_even': break_even,
            'authority': 'accounting_only',
        }
        digest = self.sink(body) if self.sink else _digest(body)
        return CapsuleEconomicsReceipt(capsule_id, preparation_debt_ms, gross, residency_cost_ms,
                                       verification_cost_ms, net, break_even, break_even, digest)
