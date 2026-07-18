"""Extract proof-carrying Crystal IR from a verified runtime episode."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any, Iterable, Mapping
from app.kernel.compute.causal_inference import infer_edges


@dataclass(frozen=True)
class CrystalIR:
    identity: str
    task_family: tuple[str, ...]
    parameters: tuple[str, ...]
    preconditions: tuple[str, ...]
    execution_graph: tuple[str, ...]
    postconditions: tuple[str, ...]
    evidence: tuple[str, ...]
    source_episode_hash: str
    topology: tuple[str, ...] = ()
    resource_envelope: Mapping[str, Any] = None
    negative_conditions: tuple[str, ...] = ()
    causal_edges: tuple[tuple[str, str, str, float], ...] = ()
    parameter_schemas: Mapping[str, Any] = None
    invariants: Mapping[str, Any] = None
    generalization_receipt: Mapping[str, Any] = None

    @property
    def digest(self) -> str:
        body = asdict(self)
        # Preserve legacy CrystalIR identities until a generalized candidate
        # actually opts into the new evidence fields.
        for optional in ("parameter_schemas", "invariants", "generalization_receipt"):
            if body.get(optional) is None:
                body.pop(optional, None)
        return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RuntimeCrystallizer:
    def extract(self, episode: Mapping[str, Any], *, identity: str, task_family: Iterable[str], parameters: Iterable[str], preconditions: Iterable[str], postconditions: Iterable[str]) -> CrystalIR:
        events = episode.get("events") or ()
        graph = tuple(str(event.get("type") or event.get("event_type")) for event in events if isinstance(event, Mapping))
        if not graph:
            raise ValueError("episode has no causal events")
        source = episode.get("episode_hash") or ("sha256:" + hashlib.sha256(json.dumps(episode, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        evidence = tuple(str(item) for item in episode.get("evidence", ()))
        topology = tuple(str(item) for item in episode.get("socket_topology", episode.get("topology", ())))
        resources = dict(episode.get("resources") or episode.get("resource_envelope") or {})
        negatives = tuple(str(item) for item in episode.get("negative_conditions", ()))
        causal = tuple((edge.source, edge.target, edge.reason, edge.confidence) for edge in infer_edges(list(events)))
        return CrystalIR(identity, tuple(task_family), tuple(parameters), tuple(preconditions), graph, tuple(postconditions), evidence, source, topology, resources, negatives, causal)
