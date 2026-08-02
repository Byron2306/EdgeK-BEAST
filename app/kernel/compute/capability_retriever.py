"""Local-first retrieval of verified capability patterns for small models."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping


_WORD = re.compile(r"[a-zA-Z0-9_:.#-]+")
_FORBIDDEN = ("complete replacement source", "replacement code here", "insert code", "your code", "todo")


def _tokens(value: Any) -> set[str]:
    return {item.casefold() for item in _WORD.findall(str(value or "")) if len(item) > 1}


@dataclass(frozen=True)
class VerifiedCapabilityPattern:
    pattern_id: str
    task_family: str
    slot_type: str
    failure_signature: str
    pattern: str
    verifier: str
    evidence_id: str
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"pattern_id": self.pattern_id, "task_family": self.task_family,
                "slot_type": self.slot_type, "failure_signature": self.failure_signature,
                "pattern": self.pattern, "verifier": self.verifier,
                "evidence_id": self.evidence_id, "confidence": self.confidence,
                "authority": "verified_guidance_only"}


class VerifiedCapabilityRetriever:
    """Bounded lexical retrieval; semantic backends may be layered above it."""

    def __init__(self, *, max_patterns: int = 2048) -> None:
        self.max_patterns = max(1, int(max_patterns))
        self._patterns: dict[str, VerifiedCapabilityPattern] = {}
        self._lock = RLock()

    def add_verified(self, pattern: VerifiedCapabilityPattern | Mapping[str, Any]) -> str:
        if not isinstance(pattern, VerifiedCapabilityPattern):
            pattern = VerifiedCapabilityPattern(
                pattern_id=str(pattern.get("pattern_id") or ""),
                task_family=str(pattern.get("task_family") or ""),
                slot_type=str(pattern.get("slot_type") or "unknown"),
                failure_signature=str(pattern.get("failure_signature") or ""),
                pattern=str(pattern.get("pattern") or pattern.get("text") or ""),
                verifier=str(pattern.get("verifier") or ""),
                evidence_id=str(pattern.get("evidence_id") or ""),
                confidence=float(pattern.get("confidence") or 0.0),
            )
        if not pattern.pattern_id:
            pattern = VerifiedCapabilityPattern(
                "cap_" + hashlib.sha256(pattern.pattern.encode()).hexdigest()[:20],
                pattern.task_family, pattern.slot_type, pattern.failure_signature,
                pattern.pattern, pattern.verifier, pattern.evidence_id, pattern.confidence,
            )
        if not pattern.pattern.strip() or not pattern.evidence_id or pattern.confidence < 0.8:
            raise ValueError("capability pattern requires non-empty verified evidence and confidence >= 0.8")
        lowered = pattern.pattern.casefold()
        if any(item in lowered for item in _FORBIDDEN):
            raise ValueError("placeholder-like capability pattern rejected")
        with self._lock:
            if len(self._patterns) >= self.max_patterns and pattern.pattern_id not in self._patterns:
                oldest = next(iter(self._patterns))
                self._patterns.pop(oldest)
            self._patterns[pattern.pattern_id] = pattern
        return pattern.pattern_id

    def retrieve(self, request: Mapping[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
        task = str(request.get("task_family") or request.get("task") or "")
        contract = request.get("residual_contract") if isinstance(request.get("residual_contract"), Mapping) else {}
        slot = str(contract.get("scope") or request.get("slot_type") or "")
        failure = str(request.get("failure_summary") or request.get("failure") or "")
        query = _tokens(" ".join((task, slot, failure, str(request.get("symbol") or ""))))
        with self._lock:
            candidates = list(self._patterns.values())
        ranked: list[tuple[float, VerifiedCapabilityPattern]] = []
        for item in candidates:
            candidate = _tokens(" ".join((item.task_family, item.slot_type, item.failure_signature, item.pattern)))
            overlap = len(query & candidate) / max(1, len(query | candidate))
            exact_task = 0.35 if task and task.casefold() == item.task_family.casefold() else 0.0
            exact_slot = 0.2 if slot and slot.casefold() == item.slot_type.casefold() else 0.0
            score = min(1.0, overlap + exact_task + exact_slot) * min(1.0, item.confidence)
            if score >= 0.12:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].pattern_id))
        return [{**item.to_dict(), "retrieval_score": round(score, 4)} for score, item in ranked[:max(0, int(limit))]]

    def patterns_for_model(self, request: Mapping[str, Any], *, limit: int = 3) -> list[str]:
        return [str(item["pattern"])[:400] for item in self.retrieve(request, limit=limit)]

