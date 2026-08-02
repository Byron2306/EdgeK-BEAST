from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Any
import hashlib, json
from .bpf_event_contracts import KernelObservation
from .bpf_loss_receipts import LossLedger

class ProcessLeaseResolver(Protocol):
    def __call__(self, *, pid: int, tgid: int, cgroup_id: int) -> Mapping[str, Any] | None: ...

@dataclass(frozen=True, slots=True)
class SensoriumProjection:
    event_type: str
    mission_id: str | None
    workspace_id: str | None
    process_lease_id: str | None
    observation_digest: str
    body: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"event_type": self.event_type, "mission_id": self.mission_id,
                "workspace_id": self.workspace_id, "process_lease_id": self.process_lease_id,
                "observation_digest": self.observation_digest, "body": dict(self.body),
                "authority": "observation_only", "raw_payload_retained": False}

class BPFSensoriumAdapter:
    def __init__(self, *, sink: Callable[[Mapping[str, Any]], None], lease_resolver: ProcessLeaseResolver,
                 ledger: LossLedger | None = None) -> None:
        if not callable(sink) or not callable(lease_resolver):
            raise TypeError("sink and lease_resolver must be callable")
        self.sink, self.lease_resolver = sink, lease_resolver
        self.ledger = ledger or LossLedger()
        self._observations = 0
        self._correlated = 0

    def accept(self, observation: KernelObservation) -> SensoriumProjection:
        self.ledger.observe_sequence(observation.cpu, observation.sequence)
        lease = self.lease_resolver(pid=observation.pid, tgid=observation.tgid, cgroup_id=observation.cgroup_id)
        self._observations += 1
        if lease:
            self._correlated += 1
        body = observation.to_dict()
        body.pop("fields", None)
        body["attributes"] = dict(observation.fields)
        body["correlated"] = bool(lease)
        if lease and lease.get("correlation_method") is not None:
            body["correlation_method"] = str(lease["correlation_method"])
        projection = SensoriumProjection(
            event_type=f"kernel.bpf.{observation.kind.name.lower()}",
            mission_id=str(lease.get("mission_id")) if lease and lease.get("mission_id") is not None else None,
            workspace_id=str(lease.get("workspace_id")) if lease and lease.get("workspace_id") is not None else None,
            process_lease_id=str(lease.get("process_lease_id")) if lease and lease.get("process_lease_id") is not None else None,
            observation_digest=observation.digest,
            body=body,
        )
        self.sink(projection.to_dict())
        self.ledger.emitted()
        return projection

    def correlation_receipt(self) -> dict[str, int | bool]:
        """Return only aggregate custody facts; individual leases stay in the event sink."""
        return {
            "observations_consumed": self._observations,
            "process_lease_correlations": self._correlated,
            "process_lease_correlation_performed": self._correlated > 0,
        }
