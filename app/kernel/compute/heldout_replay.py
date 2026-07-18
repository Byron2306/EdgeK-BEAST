"""Held-out replay gate for candidate crystal promotion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Any


@dataclass(frozen=True)
class ReplayReceipt:
    candidate_id: str
    attempts: int
    successes: int
    promoted: bool
    reason: str
    variant_ids: tuple[str, ...] = ()
    variant_results: tuple[bool, ...] = ()
    evidence_root: str = ""
    structured: bool = False


class HeldOutReplayGate:
    def evaluate(self, candidate_id: str, variants: Iterable[Any], replay: Callable[[Any], bool], *, minimum_successes: int = 3) -> ReplayReceipt:
        variants = list(variants)
        results = [bool(replay(variant)) for variant in variants]
        successes = sum(results)
        promoted = len(results) > 0 and successes >= minimum_successes and successes == len(results)
        ids = tuple(str(variant) for variant in variants)
        return ReplayReceipt(candidate_id, len(results), successes, promoted,
                             "held-out replay passed" if promoted else "held-out replay failed", ids, tuple(results))
