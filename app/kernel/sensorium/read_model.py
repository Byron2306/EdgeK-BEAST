"""Payload-free read projection for the Runtime Observatory and local API."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict
from threading import RLock

from app.kernel.sensorium.episode_builder import RuntimeEpisodeBuilder
from app.kernel.sensorium.event_sequencer import SensoriumEventSequencer


class SensoriumReadModel:
    def __init__(self, sequencer: SensoriumEventSequencer, episodes: RuntimeEpisodeBuilder):
        self.sequencer = sequencer
        self.episodes = episodes
        self._sockets = {}
        self._lock = RLock()

    def register_socket(self, reconciled) -> None:
        """Register a reconciled identity; payloads and descriptors stay out."""
        identity = reconciled.identity
        with self._lock:
            self._sockets[identity.identity] = {
                "identity": identity.identity,
                "family": identity.family,
                "protocol": identity.protocol,
                "local_address_class": identity.local_address_class,
                "local_port": identity.local_port,
                "service_id": identity.service_id,
                "workspace_id": identity.workspace_id,
                "policy_class": identity.policy_class,
                "network_namespace": identity.network_namespace,
                "vrf": identity.vrf,
                "listener_generation": identity.listener_generation,
                "lease_id": reconciled.lease_id,
                "lease_match": reconciled.lease_match,
                "compatibility_hint": reconciled.compatibility_hint,
            }

    def remove_socket(self, identity: str) -> bool:
        with self._lock:
            return self._sockets.pop(identity, None) is not None

    def state(self, *, event_limit: int = 25, episode_limit: int = 10) -> Dict[str, Any]:
        entries = self.sequencer.latest(event_limit)
        closed = self.episodes.latest_closed(episode_limit)
        sources = Counter(entry.event.source for entry in entries)
        event_types = Counter(entry.event.event_type for entry in entries)
        with self._lock:
            sockets = tuple(dict(value) for value in self._sockets.values())
        return {
            "beast_object_type": "sensorium_read_model",
            "version": "1.0",
            "authority": "read_only",
            "actuator_available": False,
            "socket_topology": sockets,
            "sequencer": self.sequencer.metrics(),
            "episodes": self.episodes.state(include_closed=False),
            "recent_sources": dict(sorted(sources.items())),
            "recent_event_types": dict(sorted(event_types.items())),
            "recent_events": [
                {
                    "offset": entry.offset,
                    "event_id": entry.event.event_id,
                    "event_type": entry.event.event_type,
                    "source": entry.event.source,
                    "mission_id": entry.event.attribution.get("mission_id", ""),
                    "workspace_id": entry.event.attribution.get("workspace_id", ""),
                    "confidence": entry.event.confidence,
                    "privacy_class": entry.event.privacy.get("class"),
                    "payload_schema": entry.event.payload_schema,
                    "payload_included": False,
                }
                for entry in entries
            ],
            "recent_closed_episodes": [
                {
                    "mission_id": episode.mission_id,
                    "episode_hash": episode.episode_hash,
                    "event_count": len(episode.event_ids),
                    "outcome_status": episode.outcome.get("status"),
                    "source_loss": dict(episode.source_loss),
                }
                for episode in closed
            ],
        }
