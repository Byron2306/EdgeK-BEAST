"""Build deterministic RuntimeEpisodes from ordered Sensorium entries."""

from __future__ import annotations

from collections import Counter, defaultdict
from threading import RLock
from typing import Any, Dict, List, Optional

from app.kernel.sensorium.contracts import RuntimeEpisode, content_hash
from app.kernel.sensorium.event_sequencer import SequencedEvent
from app.kernel.sensorium.physical_effects import PhysicalEffect


class RuntimeEpisodeBuilder:
    def __init__(self, *, closed_capacity: int = 100):
        if closed_capacity < 1:
            raise ValueError("closed_capacity must be positive")
        self.closed_capacity = int(closed_capacity)
        self._open: Dict[str, List[SequencedEvent]] = defaultdict(list)
        self._loss: Dict[str, Counter[str]] = defaultdict(Counter)
        self._closed: List[RuntimeEpisode] = []
        self._lock = RLock()

    def ingest(self, entry: SequencedEvent) -> bool:
        event = entry.event
        with self._lock:
            if event.event_type == "sensorium.loss":
                by_mission_source = event.payload.get("dropped_by_mission_source") or {}
                for mission_id, source_counts in by_mission_source.items():
                    if mission_id == "unattributed":
                        continue
                    if not isinstance(source_counts, dict):
                        continue
                    for source, source_count in source_counts.items():
                        self._loss[str(mission_id)][str(source)] += int(source_count)
            mission_id = str(event.attribution.get("mission_id") or "")
            if not mission_id:
                return False
            self._open[mission_id].append(entry)
            return True

    def close(
        self,
        mission_id: str,
        *,
        objective_hash: str,
        workspace_identity: str,
        initial_state_hash: str,
        outcome: Dict[str, Any],
        resources: Optional[Dict[str, float]] = None,
    ) -> RuntimeEpisode:
        with self._lock:
            entries = list(self._open.pop(mission_id, []))
            if not entries:
                raise ValueError(f"no Sensorium events for mission: {mission_id}")
            event_ids = [entry.event.event_id for entry in entries]
            graph = self._build_execution_graph(entries)
            aggregate = self._aggregate_resources(entries)
            for key, value in (resources or {}).items():
                aggregate[str(key)] = aggregate.get(str(key), 0.0) + float(value)
            episode = RuntimeEpisode(
                mission_id=mission_id,
                objective_hash=objective_hash,
                workspace_identity=workspace_identity,
                initial_state_hash=initial_state_hash,
                event_ids=event_ids,
                source_loss=dict(self._loss.pop(mission_id, Counter())),
                causal_graph=graph,
                resources=aggregate,
                outcome=dict(outcome),
            ).sealed()
            episode.validate()
            self._closed.append(episode)
            self._closed = self._closed[-self.closed_capacity :]
            return episode

    def state(self, *, include_closed: bool = False) -> Dict[str, Any]:
        with self._lock:
            payload: Dict[str, Any] = {
                "beast_object_type": "runtime_episode_builder_state",
                "version": "1.0",
                "open_missions": {
                    mission_id: {
                        "event_count": len(entries),
                        "first_offset": entries[0].offset,
                        "last_offset": entries[-1].offset,
                        "source_loss": dict(self._loss.get(mission_id, {})),
                    }
                    for mission_id, entries in sorted(self._open.items())
                },
                "closed_count": len(self._closed),
                "read_only": True,
            }
            if include_closed:
                payload["closed"] = [episode.to_dict() for episode in self._closed]
            return payload

    def latest_closed(self, limit: int = 25) -> List[RuntimeEpisode]:
        with self._lock:
            return list(self._closed[-max(0, limit) :])

    @staticmethod
    def _aggregate_resources(entries: List[SequencedEvent]) -> Dict[str, float]:
        aggregate: Dict[str, float] = {}
        for entry in entries:
            values = entry.event.payload.get("resource_delta")
            if not isinstance(values, dict):
                values = entry.event.payload.get("resources")
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                aggregate[str(key)] = aggregate.get(str(key), 0.0) + float(value)
        return aggregate

    @staticmethod
    def _build_execution_graph(entries: List[SequencedEvent]) -> Dict[str, Any]:
        event_ids = [entry.event.event_id for entry in entries]
        ordered_edges = [[event_ids[index - 1], event_ids[index]] for index in range(1, len(event_ids))]
        known_ids = set(event_ids)
        producers: Dict[str, str] = {}
        causal_edges: List[Dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str, str]] = set()
        event_facts: Dict[str, Dict[str, Any]] = {}

        def add(source: str, target: str, relation: str, evidence: str, confidence: float) -> None:
            key = (source, target, relation, evidence)
            if source in known_ids and target in known_ids and source != target and key not in seen_edges:
                seen_edges.add(key)
                causal_edges.append({
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "evidence": evidence,
                    "confidence": confidence,
                })

        for entry in entries:
            event = entry.event
            effect = PhysicalEffect.from_payload(event.payload)
            if effect is None:
                continue
            event_facts[event.event_id] = {
                "event_type": event.event_type,
                "payload_sha256": event.payload_sha256,
                **effect.fact_projection(),
            }
            for source in effect.caused_by_event_ids:
                add(source, event.event_id, "EXPLICIT_CAUSE", source, 1.0)
            for relation, resources in (("READS", effect.reads), ("REQUIRES", effect.requires)):
                for resource in resources:
                    source = producers.get(resource)
                    if source:
                        add(source, event.event_id, relation, resource, 0.95)
            if effect.state_transition is not None:
                resource, _before, _after = effect.state_transition
                source = producers.get(resource)
                if source and source != event.event_id:
                    add(source, event.event_id, "STATE_TRANSITION", resource, 0.98)
                producers[resource] = event.event_id
            for resource in (*effect.writes, *effect.produces):
                producers[resource] = event.event_id

        return {
            "nodes": event_ids,
            # Compatibility alias. These edges assert order only, never cause.
            "edges": ordered_edges,
            "edge_semantics": "order_only_compatibility_alias",
            "ordered_edges": ordered_edges,
            "ordering": "sequencer_offset",
            "causal_edges": causal_edges,
            "causality": "explicit_resource_descriptor_or_actuator_evidence_only",
            "event_facts": event_facts,
        }
