"""Small deterministic equality-saturation core for Crystal alternatives.

This is deliberately an engine for verified alternatives, not a theorem
prover: callers supply an equivalence key and a measurable extraction cost.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class EquivalentAlternative:
    expression_id: str
    equivalence_key: str
    cost: float
    verified: bool = False
    payload: Any = None

class EqualitySaturation:
    def __init__(self): self._groups: dict[str, list[EquivalentAlternative]] = {}
    def add(self, alternative: EquivalentAlternative) -> None:
        if not alternative.expression_id or not alternative.equivalence_key or alternative.cost < 0: raise ValueError("invalid equivalent alternative")
        if any(item.expression_id==alternative.expression_id for item in self._groups.get(alternative.equivalence_key,())): raise ValueError("duplicate equivalent expression")
        self._groups.setdefault(alternative.equivalence_key, []).append(alternative)
    def extract(self, key: str, *, cost: Callable[[EquivalentAlternative], float] | None = None) -> EquivalentAlternative:
        choices=[item for item in self._groups.get(key, ()) if item.verified]
        if not choices: raise LookupError(f"no verified equivalent for {key}")
        return min(choices, key=cost or (lambda item: item.cost))
    def alternatives(self, key: str) -> tuple[EquivalentAlternative, ...]:
        return tuple(self._groups.get(key, ()))
    def summary(self) -> dict:
        return {"groups":len(self._groups),"alternatives":sum(len(items) for items in self._groups.values()),"verified":sum(item.verified for items in self._groups.values() for item in items)}
