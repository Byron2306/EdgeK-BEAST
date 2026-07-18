"""Deterministic, bounded e-graph support for Crystal alternatives.

The legacy alternative API remains useful for externally verified crystals.
``EGraph`` adds actual congruence closure and bounded rewrite saturation for
declarative terms.  It intentionally never executes a rewrite: rules are data
and extraction only returns a term that still needs normal crystal verification.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

@dataclass(frozen=True)
class EquivalentAlternative:
    expression_id: str
    equivalence_key: str
    cost: float
    verified: bool = False
    payload: Any = None


@dataclass(frozen=True)
class ENode:
    """A hashable declarative expression node (operator plus child e-classes)."""
    operator: str
    children: tuple[int, ...] = ()
    value: str = ""


@dataclass(frozen=True)
class RewriteRule:
    """A first-order rewrite expressed as pattern dictionaries.

    Variables use ``?name`` strings.  A pattern is either such a variable,
    a scalar leaf, or ``{"op": str, "args": [patterns...]}``.
    """
    name: str
    lhs: Any
    rhs: Any

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


class EGraph:
    """A small e-graph with congruence closure and resource-bounded rewrites.

    It is deliberately dependency-free so it can run in the trusted local
    crystallization path.  Saturation stops at explicit iteration/node limits,
    making an over-broad rule set fail closed rather than consuming a runtime.
    """
    def __init__(self) -> None:
        self._parent: list[int] = []
        self._nodes: dict[ENode, int] = {}
        self._terms: dict[int, Any] = {}

    def _new_class(self, term: Any) -> int:
        index = len(self._parent)
        self._parent.append(index); self._terms[index] = term
        return index

    def find(self, value: int) -> int:
        if self._parent[value] != value:
            self._parent[value] = self.find(self._parent[value])
        return self._parent[value]

    def union(self, left: int, right: int) -> int:
        left, right = self.find(left), self.find(right)
        if left == right:
            return left
        winner, loser = min(left, right), max(left, right)
        self._parent[loser] = winner
        if winner not in self._terms:
            self._terms[winner] = self._terms[loser]
        return winner

    def rebuild(self) -> int:
        """Restore congruence after unions; return e-class merges performed."""
        merges = 0
        canonical: dict[ENode, int] = {}
        for node, class_id in list(self._nodes.items()):
            normalized = ENode(node.operator, tuple(self.find(child) for child in node.children), node.value)
            existing = canonical.get(normalized)
            if existing is None:
                canonical[normalized] = self.find(class_id)
            elif self.find(existing) != self.find(class_id):
                self.union(existing, class_id); merges += 1
        self._nodes = canonical
        return merges

    def add(self, term: Any) -> int:
        if isinstance(term, Mapping) and "op" in term:
            operator = str(term["op"])
            children = tuple(self.find(self.add(item)) for item in term.get("args", ()))
            node = ENode(operator, children)
        else:
            node = ENode("$leaf", (), repr(term))
        present = self._nodes.get(node)
        if present is not None:
            return self.find(present)
        result = self._new_class(term)
        self._nodes[node] = result
        return result

    def equivalent(self, left: Any, right: Any) -> bool:
        return self.find(self.add(left)) == self.find(self.add(right))

    @staticmethod
    def _match(pattern: Any, term: Any, bindings: dict[str, Any]) -> bool:
        if isinstance(pattern, str) and pattern.startswith("?"):
            bound = bindings.get(pattern)
            if bound is None:
                bindings[pattern] = term; return True
            return bound == term
        if isinstance(pattern, Mapping):
            return (isinstance(term, Mapping) and pattern.get("op") == term.get("op")
                    and len(pattern.get("args", ())) == len(term.get("args", ()))
                    and all(EGraph._match(a, b, bindings) for a, b in zip(pattern.get("args", ()), term.get("args", ()))) )
        return pattern == term

    @staticmethod
    def _instantiate(pattern: Any, bindings: Mapping[str, Any]) -> Any:
        if isinstance(pattern, str) and pattern.startswith("?"):
            return bindings[pattern]
        if isinstance(pattern, Mapping):
            return {"op": pattern["op"], "args": [EGraph._instantiate(v, bindings) for v in pattern.get("args", ())]}
        return pattern

    def saturate(self, rules: Iterable[RewriteRule], *, max_iterations: int = 8, max_nodes: int = 4096) -> dict[str, int | bool]:
        if max_iterations < 1 or max_nodes < 1:
            raise ValueError("saturation limits must be positive")
        rules = tuple(rules); rewrites = 0
        for iteration in range(max_iterations):
            changed = False
            for class_id, term in list(self._terms.items()):
                root = self.find(class_id)
                for rule in rules:
                    bindings: dict[str, Any] = {}
                    if not self._match(rule.lhs, term, bindings):
                        continue
                    rhs = self._instantiate(rule.rhs, bindings)
                    if len(self._parent) >= max_nodes and rhs not in self._terms.values():
                        return {"iterations": iteration + 1, "rewrites": rewrites, "saturated": False, "node_limit_hit": True}
                    before = self.find(self.add(rhs))
                    if root != before:
                        self.union(root, before)
                        changed = True; rewrites += 1
            if self.rebuild():
                changed = True
            if not changed:
                return {"iterations": iteration + 1, "rewrites": rewrites, "saturated": True, "node_limit_hit": False}
        return {"iterations": max_iterations, "rewrites": rewrites, "saturated": False, "node_limit_hit": False}

    def extract(self, term: Any, *, cost: Callable[[Any], float] | None = None) -> Any:
        root = self.find(self.add(term)); scorer = cost or (lambda value: 1.0)
        candidates = [value for key, value in self._terms.items() if self.find(key) == root]
        if not candidates:
            raise LookupError("e-class has no extractable term")
        return min(candidates, key=scorer)

    def summary(self) -> dict[str, int]:
        return {"eclasses": len({self.find(i) for i in range(len(self._parent))}), "enodes": len(self._nodes)}
