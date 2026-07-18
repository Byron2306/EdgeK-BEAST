"""Explicit transactional orchestration for governed crystal effects."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping

@dataclass(frozen=True)
class RollbackReceipt:
    status: str
    effect: Mapping[str, Any]
    snapshot_ref: str
    verification: Mapping[str, Any]
    error: str = ""

class RollbackOrchestrator:
    def run(self, operation: Any, *, snapshot: Callable[[Any], str], apply: Callable[[Any], Mapping[str, Any]], verify: Callable[[Any, Mapping[str, Any]], Mapping[str, Any]], rollback: Callable[[Any, str, Mapping[str, Any]], None]) -> RollbackReceipt:
        snapshot_ref=snapshot(operation)
        effect={}
        try:
            effect=dict(apply(operation))
            verification=dict(verify(operation,effect))
        except Exception as exc:
            rollback(operation,snapshot_ref,effect)
            return RollbackReceipt("rolled_back",effect,snapshot_ref,{"exception":False},str(exc))
        if all(bool(value) for value in verification.values()):
            return RollbackReceipt("verified",effect,snapshot_ref,verification)
        rollback(operation,snapshot_ref,effect)
        return RollbackReceipt("rolled_back",effect,snapshot_ref,verification)
