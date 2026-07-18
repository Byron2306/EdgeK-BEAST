"""Evidence-bounded causal graph extraction for runtime episodes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

@dataclass(frozen=True)
class CausalEdge:
    source: str
    target: str
    reason: str
    confidence: float

def infer_edges(events: list[Mapping[str, Any]]) -> tuple[CausalEdge, ...]:
    edges=[]; previous=None; producers={}; seen=set()
    def add(source,target,reason,confidence):
        key=(source,target,reason)
        if source and target and source!=target and key not in seen: seen.add(key); edges.append(CausalEdge(source,target,reason,confidence))
    for index,event in enumerate(events):
        current=str(event.get("id") or event.get("event_id") or event.get("type") or f"event-{index}")
        if previous and event.get("happened_after", True):
            add(previous,current,"ordered_episode",0.6)
        # Trace/span and explicit causation are stronger than ordering.  These
        # identifiers are evidence references, never guessed semantic links.
        for key in ("parent_event_id", "caused_by", "follows", "span_parent"):
            parent = event.get(key)
            if parent:
                add(str(parent), current, key, 1.0)
        for key in ("reads","depends_on","input_from","requires"):
            values=event.get(key) or []
            if isinstance(values,str): values=[values]
            for value in values:
                source=producers.get(str(value),str(value))
                add(source,current,key,0.9)
        for key in ("writes","produces","outputs"):
            values=event.get(key) or []
            if isinstance(values,str): values=[values]
            for value in values: producers[str(value)]=current
        previous=current
    return tuple(edges)


def infer_consensus_edges(
    episodes: Sequence[Sequence[Mapping[str, Any]]], *, minimum_support: int = 2
) -> tuple[CausalEdge, ...]:
    """Return only repeatable edges across independent observed episodes.

    This is evidence-bounded causal discovery: it discovers stable *observed*
    relations, but deliberately does not claim counterfactual causality.
    """
    if minimum_support < 1:
        raise ValueError("minimum_support must be positive")
    support: dict[tuple[str, str, str], list[float]] = {}
    for episode in episodes:
        # An edge contributes once per episode, preventing one noisy trace from
        # manufacturing apparent support.
        observed: dict[tuple[str, str, str], float] = {}
        for edge in infer_edges(list(episode)):
            if edge.reason == "ordered_episode":
                continue
            key = (edge.source, edge.target, edge.reason)
            observed[key] = max(observed.get(key, 0.0), edge.confidence)
        for key, confidence in observed.items():
            support.setdefault(key, []).append(confidence)
    return tuple(
        CausalEdge(source, target, reason, round(sum(confidences) / len(confidences), 6))
        for (source, target, reason), confidences in sorted(support.items())
        if len(confidences) >= minimum_support
    )
