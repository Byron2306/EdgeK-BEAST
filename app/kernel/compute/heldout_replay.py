"""Held-out replay gate for candidate crystal promotion.

Receipts carry an ``evidence_root`` binding the episode envelope digest, the per-variant results and the
reproduction record, so a promotion is auditable after the fact. ``structured`` is true only for typed (mapping)
held-out variants whose results are all recorded against a bound episode envelope.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                 default=str).encode()).hexdigest()


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
    episode_envelope_digest: str = ""
    variant_results_digest: str = ""
    reproduction_record_digest: str = ""


def replay_evidence(*, candidate_id: str, envelope_digest: str, variants: list[Any], results: list[bool],
                    reproduction: Mapping[str, Any] | None = None) -> dict[str, Any]:
    variant_results = [{"variant": dict(v) if isinstance(v, Mapping) else str(v), "passed": bool(r)}
                       for v, r in zip(variants, results, strict=True)]
    record = {"candidate_id": candidate_id, "variant_count": len(variants), **dict(reproduction or {})}
    components = {"episode_envelope_digest": str(envelope_digest or ""),
                  "variant_results_digest": _sha(variant_results),
                  "reproduction_record_digest": _sha(record)}
    structured = bool(variants) and bool(envelope_digest) and all(isinstance(v, Mapping) for v in variants)
    return {**components, "evidence_root": _sha(components), "structured": structured}


class HeldOutReplayGate:
    def evaluate(self, candidate_id: str, variants: Iterable[Any], replay: Callable[[Any], bool], *,
                 minimum_successes: int = 3, envelope_digest: str = "",
                 reproduction: Mapping[str, Any] | None = None) -> ReplayReceipt:
        variants = list(variants)
        results = [bool(replay(variant)) for variant in variants]
        successes = sum(results)
        promoted = len(results) > 0 and successes >= minimum_successes and successes == len(results)
        ids = tuple(str(variant) for variant in variants)
        evidence = replay_evidence(candidate_id=candidate_id, envelope_digest=envelope_digest, variants=variants,
                                   results=results, reproduction=reproduction)
        return ReplayReceipt(candidate_id, len(results), successes, promoted,
                             "held-out replay passed" if promoted else "held-out replay failed", ids, tuple(results),
                             **evidence)
