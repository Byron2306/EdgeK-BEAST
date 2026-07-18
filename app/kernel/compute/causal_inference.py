"""Evidence-bounded causal graph extraction for runtime episodes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping

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
