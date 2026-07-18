"""Versioned, hash-stable contracts for the BEAST Sensorium.

These classes define identity and evidence objects only.  They deliberately do
not contain sensor attachment, process control, socket mutation, or crystal
execution behavior.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, List

from app.kernel.sensorium.artifact_taxonomy import ArtifactAuthority
from app.kernel.sensorium.contracts_hash import canonical_bytes, content_hash


SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
IDENTITY_RE = re.compile(r"^[a-z][a-z0-9_-]*:sha256:[a-f0-9]{64}$")
EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class ContractValidationError(ValueError):
    """Raised when a Sensorium contract violates an invariant."""


def typed_identity(prefix: str, value: Any) -> str:
    return f"{prefix}:{content_hash(value)}"


def _required(value: Any, field_name: str) -> None:
    if value is None or value == "" or value == [] or value == {}:
        raise ContractValidationError(f"{field_name} is required")


def _sha256(value: str, field_name: str) -> None:
    if not SHA256_RE.fullmatch(str(value or "")):
        raise ContractValidationError(f"{field_name} must be sha256:<64 lowercase hex chars>")


def _typed_identity(value: str, prefix: str, field_name: str) -> None:
    if not IDENTITY_RE.fullmatch(str(value or "")) or not str(value).startswith(f"{prefix}:sha256:"):
        raise ContractValidationError(f"{field_name} must be {prefix}:sha256:<64 lowercase hex chars>")


def _nonnegative(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractValidationError(f"{field_name} must be a nonnegative integer")


@dataclass(frozen=True)
class ProcessLease:
    boot_id: str
    pid_at_observation: int
    start_time_ticks: int
    executable_digest: str
    cgroup_id: str
    pid_namespace_inode: int
    mount_namespace_inode: int
    parent_identity_hash: str
    owner_scope: str
    acquired_at: str
    lease_id: str = ""
    exited_at: str = ""

    def identity_payload(self) -> Dict[str, Any]:
        return {
            "boot_id": self.boot_id,
            "pid_at_observation": self.pid_at_observation,
            "start_time_ticks": self.start_time_ticks,
            "executable_digest": self.executable_digest,
            "cgroup_id": self.cgroup_id,
            "pid_namespace_inode": self.pid_namespace_inode,
            "mount_namespace_inode": self.mount_namespace_inode,
            "parent_identity_hash": self.parent_identity_hash,
            "owner_scope": self.owner_scope,
        }

    def with_identity(self) -> "ProcessLease":
        return replace(self, lease_id=typed_identity("process", self.identity_payload()))

    def validate(self) -> None:
        _required(self.boot_id, "boot_id")
        _nonnegative(self.pid_at_observation, "pid_at_observation")
        if self.pid_at_observation == 0:
            raise ContractValidationError("pid_at_observation must be greater than zero")
        _nonnegative(self.start_time_ticks, "start_time_ticks")
        _sha256(self.executable_digest, "executable_digest")
        _required(self.cgroup_id, "cgroup_id")
        _nonnegative(self.pid_namespace_inode, "pid_namespace_inode")
        _nonnegative(self.mount_namespace_inode, "mount_namespace_inode")
        _sha256(self.parent_identity_hash, "parent_identity_hash")
        _required(self.owner_scope, "owner_scope")
        _required(self.acquired_at, "acquired_at")
        _typed_identity(self.lease_id, "process", "lease_id")
        if self.lease_id != typed_identity("process", self.identity_payload()):
            raise ContractValidationError("lease_id does not match process identity payload")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "beast_object_type": "process_lease",
            "version": "1.0",
            **asdict(self),
            "pidfd_serialized": False,
        }


@dataclass(frozen=True)
class SocketIdentity:
    family: str
    protocol: str
    local_address_class: str
    local_port: int
    remote_scope: str
    owning_process: str
    service_id: str
    workspace_id: str
    cgroup_id: str
    listener_generation: int
    opened_at_monotonic_ns: int
    policy_class: str
    network_namespace: str = "host"
    vrf: str = "production"
    identity: str = ""

    def identity_payload(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "identity"}

    def with_identity(self) -> "SocketIdentity":
        return replace(self, identity=typed_identity("socket", self.identity_payload()))

    def validate(self) -> None:
        if self.family not in {"AF_INET", "AF_INET6", "AF_UNIX"}:
            raise ContractValidationError("unsupported socket family")
        if self.protocol not in {"TCP", "UDP", "UNIX_SEQPACKET"}:
            raise ContractValidationError("unsupported socket protocol")
        if self.family == "AF_UNIX" and self.protocol != "UNIX_SEQPACKET":
            raise ContractValidationError("AF_UNIX v1 identities require UNIX_SEQPACKET")
        if self.family != "AF_UNIX" and not 1 <= self.local_port <= 65535:
            raise ContractValidationError("local_port must be between 1 and 65535")
        if self.family == "AF_UNIX" and self.local_port != 0:
            raise ContractValidationError("AF_UNIX local_port must be zero")
        _required(self.local_address_class, "local_address_class")
        _required(self.remote_scope, "remote_scope")
        _typed_identity(self.owning_process, "process", "owning_process")
        _required(self.service_id, "service_id")
        _required(self.workspace_id, "workspace_id")
        _required(self.cgroup_id, "cgroup_id")
        _nonnegative(self.listener_generation, "listener_generation")
        _nonnegative(self.opened_at_monotonic_ns, "opened_at_monotonic_ns")
        _required(self.policy_class, "policy_class")
        _typed_identity(self.identity, "socket", "identity")
        if self.identity != typed_identity("socket", self.identity_payload()):
            raise ContractValidationError("identity does not match socket identity payload")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {"beast_object_type": "socket_identity", "version": "1.0", **asdict(self)}


@dataclass(frozen=True)
class SensorEvent:
    event_type: str
    source: str
    source_instance: str
    boot_id: str
    source_sequence: int
    cpu_sequence: int
    monotonic_ns: int
    wall_time: str
    attribution: Dict[str, str]
    confidence: float
    confidence_method: str
    gaps_before: int
    loss_counter: int
    privacy: Dict[str, Any]
    payload_schema: str
    payload: Dict[str, Any]
    payload_sha256: str = ""
    event_id: str = ""

    def identity_payload(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "source_instance": self.source_instance,
            "boot_id": self.boot_id,
            "source_sequence": self.source_sequence,
            "monotonic_ns": self.monotonic_ns,
            "payload_sha256": self.payload_sha256,
        }

    def sealed(self) -> "SensorEvent":
        payload_digest = content_hash(self.payload)
        provisional = replace(self, payload_sha256=payload_digest)
        return replace(provisional, event_id=typed_identity("event", provisional.identity_payload()))

    def validate(self) -> None:
        if not EVENT_TYPE_RE.fullmatch(self.event_type):
            raise ContractValidationError("event_type must be a dotted lowercase identifier")
        _required(self.source, "source")
        _required(self.source_instance, "source_instance")
        _required(self.boot_id, "boot_id")
        _nonnegative(self.source_sequence, "source_sequence")
        _nonnegative(self.cpu_sequence, "cpu_sequence")
        _nonnegative(self.monotonic_ns, "monotonic_ns")
        _required(self.wall_time, "wall_time")
        if not isinstance(self.attribution, dict):
            raise ContractValidationError("attribution must be an object")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ContractValidationError("confidence must be between 0 and 1")
        _required(self.confidence_method, "confidence_method")
        _nonnegative(self.gaps_before, "gaps_before")
        _nonnegative(self.loss_counter, "loss_counter")
        if not isinstance(self.privacy, dict):
            raise ContractValidationError("privacy must be an object")
        for field_name in ("class", "raw_retention", "export_allowed", "redaction_status"):
            if field_name not in self.privacy:
                raise ContractValidationError(f"privacy.{field_name} is required")
        _required(self.payload_schema, "payload_schema")
        if not isinstance(self.payload, dict):
            raise ContractValidationError("payload must be an object")
        # Physical producers opt into a stronger evidence contract without
        # invalidating the existing generic SensorEvent payload surface.
        from app.kernel.sensorium.physical_effects import PhysicalEffect
        PhysicalEffect.from_payload(self.payload)
        _sha256(self.payload_sha256, "payload_sha256")
        if self.payload_sha256 != content_hash(self.payload):
            raise ContractValidationError("payload_sha256 does not match payload")
        _typed_identity(self.event_id, "event", "event_id")
        if self.event_id != typed_identity("event", self.identity_payload()):
            raise ContractValidationError("event_id does not match event identity payload")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "beast_object_type": "sensor_event",
            "version": "1.0",
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "source_instance": self.source_instance,
            "ordering": {
                "boot_id": self.boot_id,
                "source_sequence": self.source_sequence,
                "cpu_sequence": self.cpu_sequence,
                "monotonic_ns": self.monotonic_ns,
                "wall_time": self.wall_time,
            },
            "attribution": dict(self.attribution),
            "confidence": {
                "value": self.confidence,
                "method": self.confidence_method,
                "gaps_before": self.gaps_before,
                "loss_counter": self.loss_counter,
            },
            "privacy": dict(self.privacy),
            "payload_schema": self.payload_schema,
            "payload": dict(self.payload),
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True)
class RuntimeEpisode:
    mission_id: str
    objective_hash: str
    workspace_identity: str
    initial_state_hash: str
    event_ids: List[str]
    source_loss: Dict[str, int]
    causal_graph: Dict[str, Any]
    resources: Dict[str, float]
    outcome: Dict[str, Any]
    episode_hash: str = ""

    def content_payload(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "objective_hash": self.objective_hash,
            "workspace_identity": self.workspace_identity,
            "initial_state_hash": self.initial_state_hash,
            "event_ids": list(self.event_ids),
            "source_loss": dict(self.source_loss),
            "causal_graph": self.causal_graph,
            "resources": self.resources,
            "outcome": self.outcome,
        }

    def sealed(self) -> "RuntimeEpisode":
        return replace(self, episode_hash=content_hash(self.content_payload()))

    def validate(self) -> None:
        _required(self.mission_id, "mission_id")
        _sha256(self.objective_hash, "objective_hash")
        _required(self.workspace_identity, "workspace_identity")
        _sha256(self.initial_state_hash, "initial_state_hash")
        if not self.event_ids:
            raise ContractValidationError("event_ids must not be empty")
        for event_id in self.event_ids:
            _typed_identity(event_id, "event", "event_ids[]")
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ContractValidationError("event_ids must not contain duplicates")
        if any(not isinstance(value, int) or value < 0 for value in self.source_loss.values()):
            raise ContractValidationError("source_loss values must be nonnegative integers")
        if not isinstance(self.causal_graph, dict):
            raise ContractValidationError("causal_graph must be an object")
        if any(float(value) < 0 for value in self.resources.values()):
            raise ContractValidationError("resource values must be nonnegative")
        _required(self.outcome.get("status"), "outcome.status")
        _sha256(self.outcome.get("effect_hash", ""), "outcome.effect_hash")
        _sha256(self.episode_hash, "episode_hash")
        if self.episode_hash != content_hash(self.content_payload()):
            raise ContractValidationError("episode_hash does not match episode content")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "beast_object_type": "runtime_episode",
            "version": "1.0",
            **self.content_payload(),
            "event_range": {"first": self.event_ids[0], "last": self.event_ids[-1]},
            "episode_hash": self.episode_hash,
            "authority": "evidence_only",
        }


@dataclass(frozen=True)
class ComputeCrystal:
    identity: str
    task_family: List[str]
    authority: Dict[str, Any]
    applicability: Dict[str, Any]
    parameters: Dict[str, Dict[str, Any]]
    preconditions: List[Dict[str, Any]]
    execution_graph: Dict[str, Any]
    postconditions: List[str]
    topology: Dict[str, Any]
    evidence_requirements: List[str]
    economics: Dict[str, Any]
    decay: Dict[str, Any]
    signer: str
    artifact_digest: str = ""

    def content_payload(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "artifact_digest"}

    def sealed(self) -> "ComputeCrystal":
        return replace(self, artifact_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if not re.fullmatch(r"crystal:[a-z0-9][a-z0-9._-]*:v[1-9][0-9]*", self.identity):
            raise ContractValidationError("identity must be crystal:<name>:v<positive integer>")
        if not self.task_family or any(not str(item).strip() for item in self.task_family):
            raise ContractValidationError("task_family must contain nonempty values")
        maximum = str(self.authority.get("maximum") or "")
        try:
            ArtifactAuthority.from_label(maximum)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if maximum == "bounded_execute" and not self.authority.get("capability_lease"):
            raise ContractValidationError("bounded_execute crystals require capability_lease")
        if not self.applicability:
            raise ContractValidationError("applicability is required")
        if not self.parameters:
            raise ContractValidationError("parameters are required")
        allowed_types = {"string", "integer", "number", "boolean", "workspace_identity"}
        for name, schema in self.parameters.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                raise ContractValidationError(f"invalid parameter name: {name}")
            if schema.get("type") not in allowed_types:
                raise ContractValidationError(f"unsupported parameter type for {name}")
        if not self.preconditions:
            raise ContractValidationError("preconditions are required")
        if not self.postconditions:
            raise ContractValidationError("postconditions are required")
        if not self.evidence_requirements:
            raise ContractValidationError("evidence_requirements are required")
        self._validate_execution_graph()
        _required(self.signer, "signer")
        _sha256(self.artifact_digest, "artifact_digest")
        if self.artifact_digest != content_hash(self.content_payload()):
            raise ContractValidationError("artifact_digest does not match crystal content")

    def _validate_execution_graph(self) -> None:
        nodes = self.execution_graph.get("nodes")
        edges = self.execution_graph.get("edges")
        if not isinstance(nodes, list) or not nodes:
            raise ContractValidationError("execution_graph.nodes must not be empty")
        if not isinstance(edges, list):
            raise ContractValidationError("execution_graph.edges must be a list")
        node_ids = [str(item.get("id") or "") for item in nodes if isinstance(item, dict)]
        if len(node_ids) != len(nodes) or any(not item for item in node_ids):
            raise ContractValidationError("every execution node requires an id")
        if len(set(node_ids)) != len(node_ids):
            raise ContractValidationError("execution node ids must be unique")
        adjacency = {node_id: [] for node_id in node_ids}
        indegree = {node_id: 0 for node_id in node_ids}
        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 2 or edge[0] not in adjacency or edge[1] not in adjacency:
                raise ContractValidationError("execution graph edge references unknown node")
            adjacency[edge[0]].append(edge[1])
            indegree[edge[1]] += 1
        queue = [node_id for node_id, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for child in adjacency[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(node_ids):
            raise ContractValidationError("execution_graph must be acyclic in v1")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "beast_object_type": "compute_crystal_ir",
            "version": "1.0",
            **self.content_payload(),
            "artifact_digest": self.artifact_digest,
            "artifact_class": "compute_crystal_ir",
        }
