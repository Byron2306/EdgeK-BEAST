"""Canonical, declarative Crystal IR and reviewed opcode registry.

This module maps learned operation names to local handler *identifiers*.  It
never serializes callables, commands, Python source, or ambient authority.
Execution is a later boundary that resolves these identifiers locally.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping

from app.kernel.sensorium.artifact_taxonomy import ArtifactAuthority
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.contracts import ComputeCrystal


OPCODE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
PARAMETER_RE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
DESCRIPTOR_KINDS = {"process", "socket", "port_lease", "workspace"}
# Additive catalog evolution must not revoke already promoted artifacts whose
# referenced opcode contracts remain byte-for-byte identical. Contract changes
# still fail above; only catalog generations previously emitted by BEAST are
# accepted here.
COMPATIBLE_OPCODE_CATALOG_DIGESTS = frozenset({
    "sha256:2ad4c2b56c9acd96b98178a83eb87f5c3d1f00bd30cf86c90ef70a64cf14e2ff",
})


@dataclass(frozen=True)
class OpcodeSpec:
    opcode: str
    version: int
    phase: str
    authority: str
    handler_key: str
    input_schema: Mapping[str, str]
    output_schema: Mapping[str, str]
    allowed_parameters: tuple[str, ...]
    required_descriptors: tuple[str, ...]
    resource_limits: Mapping[str, float]
    verifier_key: str
    rollback_key: str = ""
    refusal_key: str = "fail_closed"

    def validate(self) -> None:
        if not OPCODE_RE.fullmatch(self.opcode) or self.version < 1:
            raise ValueError("opcode requires a dotted identifier and positive version")
        authority = ArtifactAuthority.from_label(self.authority)
        if self.phase not in {"observation", "decision", "actuation", "verification", "refusal", "rollback"}:
            raise ValueError("invalid opcode phase")
        if not self.handler_key or not self.refusal_key or not self.verifier_key:
            raise ValueError("opcode requires local handler, verifier, and refusal keys")
        if any(item not in DESCRIPTOR_KINDS for item in self.required_descriptors):
            raise ValueError("opcode declares an unsupported descriptor kind")
        if any(float(value) <= 0 for value in self.resource_limits.values()):
            raise ValueError("opcode resource limits must be positive")
        if authority is ArtifactAuthority.BOUNDED_EXECUTE and not self.rollback_key:
            raise ValueError("bounded execution opcode requires rollback behavior")

    @property
    def identity(self) -> str:
        self.validate()
        return f"{self.opcode}:v{self.version}"

    def public_contract(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


class OpcodeRegistry:
    def __init__(self, specs: Iterable[OpcodeSpec] = ()):
        self._specs: dict[tuple[str, int], OpcodeSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: OpcodeSpec) -> None:
        spec.validate()
        key = (spec.opcode, spec.version)
        if key in self._specs:
            raise ValueError(f"duplicate opcode registration: {spec.identity}")
        self._specs[key] = spec

    def resolve(self, opcode: str, version: int = 1) -> OpcodeSpec:
        try:
            return self._specs[(str(opcode), int(version))]
        except KeyError as exc:
            raise ValueError(f"unreviewed crystal opcode: {opcode}:v{version}") from exc

    def catalog(self) -> dict[str, Any]:
        entries = [spec.public_contract() for _, spec in sorted(self._specs.items())]
        return {
            "beast_object_type": "crystal_opcode_catalog",
            "version": "1.0",
            "entries": entries,
            "catalog_digest": content_hash(entries),
            "contains_executable_code": False,
        }


@dataclass(frozen=True)
class TypedCrystalNode:
    node_id: str
    opcode: str
    opcode_version: int
    phase: str
    authority: str
    handler_key: str
    parameter_bindings: Mapping[str, str]
    descriptor_requirements: tuple[str, ...]
    descriptor_constraints: tuple[str, ...]
    input_schema: Mapping[str, str]
    output_schema: Mapping[str, str]
    resource_limits: Mapping[str, float]
    verifier_key: str
    rollback_key: str
    refusal_key: str
    evidence_template_hash: str


@dataclass(frozen=True)
class ExecutableCrystalIR:
    identity: str
    task_family: tuple[str, ...]
    parameters: Mapping[str, Any]
    preconditions: tuple[str, ...]
    nodes: tuple[TypedCrystalNode, ...]
    edges: tuple[tuple[str, str, str], ...]
    postconditions: tuple[str, ...]
    negative_conditions: tuple[str, ...]
    evidence: tuple[str, ...]
    source_family_hash: str
    maximum_authority: str
    capability_lease: str
    resource_envelope: Mapping[str, Any]
    opcode_catalog_digest: str
    artifact_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("artifact_digest", None)
        return value

    def sealed(self) -> "ExecutableCrystalIR":
        return replace(self, artifact_digest=content_hash(self.content_payload()))

    def validate(self, registry: OpcodeRegistry) -> None:
        if not self.nodes:
            raise ValueError("typed crystal requires at least one node")
        if self.artifact_digest != content_hash(self.content_payload()):
            raise ValueError("typed crystal artifact digest mismatch")
        authority = ArtifactAuthority.from_label(self.maximum_authority)
        if authority is ArtifactAuthority.BOUNDED_EXECUTE and not self.capability_lease:
            raise ValueError("bounded executable crystal requires a capability lease")
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("typed crystal node ids must be unique")
        observed_maximum = ArtifactAuthority.CONTEXT_ONLY
        for node in self.nodes:
            spec = registry.resolve(node.opcode, node.opcode_version)
            observed_maximum = max(observed_maximum, ArtifactAuthority.from_label(spec.authority))
            if (
                node.phase != spec.phase
                or node.authority != spec.authority
                or node.handler_key != spec.handler_key
                or tuple(node.descriptor_requirements) != tuple(spec.required_descriptors)
                or dict(node.input_schema) != dict(spec.input_schema)
                or dict(node.output_schema) != dict(spec.output_schema)
                or dict(node.resource_limits) != dict(spec.resource_limits)
                or node.verifier_key != spec.verifier_key
                or node.rollback_key != spec.rollback_key
                or node.refusal_key != spec.refusal_key
            ):
                raise ValueError("typed crystal node differs from reviewed opcode contract")
            if set(node.parameter_bindings) - set(self.parameters):
                raise ValueError("typed crystal node binds undeclared parameters")
            if set(node.parameter_bindings) - set(spec.allowed_parameters):
                raise ValueError("typed crystal node exceeds opcode parameter contract")
            if set(node.descriptor_requirements) - set(DESCRIPTOR_KINDS):
                raise ValueError("typed crystal node requires unsupported descriptor kinds")
        if observed_maximum.label != self.maximum_authority:
            raise ValueError("typed crystal maximum authority does not match its nodes")
        adjacency = {node_id: [] for node_id in node_ids}
        indegree = {node_id: 0 for node_id in node_ids}
        seen_edges = set()
        for source, target, _relation in self.edges:
            if source not in node_ids or target not in node_ids or source == target:
                raise ValueError("typed crystal edge references an invalid node")
            if not _relation or (source, target, _relation) in seen_edges:
                raise ValueError("typed crystal edges require unique nonempty relations")
            seen_edges.add((source, target, _relation))
            adjacency[source].append(target)
            indegree[target] += 1
        queue = [node_id for node_id, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for target in adjacency[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if visited != len(node_ids):
            raise ValueError("typed crystal execution graph must be acyclic")
        if self.opcode_catalog_digest not in {registry.catalog()["catalog_digest"], *COMPATIBLE_OPCODE_CATALOG_DIGESTS}:
            raise ValueError("typed crystal opcode catalog has drifted")

    def to_dict(self, registry: OpcodeRegistry) -> dict[str, Any]:
        self.validate(registry)
        return {
            "beast_object_type": "typed_compute_crystal_ir",
            "version": "1.0",
            **self.content_payload(),
            "artifact_digest": self.artifact_digest,
            "contains_executable_code": False,
        }

    def to_compute_crystal(
        self,
        registry: OpcodeRegistry,
        *,
        signer: str,
        policy_generation: str,
        expires_after_days: int = 30,
    ) -> ComputeCrystal:
        """Materialize typed nodes inside the established proof envelope."""
        self.validate(registry)
        if not signer or not policy_generation or expires_after_days < 1:
            raise ValueError("signer, policy generation, and positive decay are required")
        nodes = []
        for node in self.nodes:
            nodes.append({
                "id": node.node_id,
                "opcode": node.opcode,
                "opcode_version": node.opcode_version,
                "phase": node.phase,
                "authority": node.authority,
                "handler_key": node.handler_key,
                "parameter_bindings": dict(node.parameter_bindings),
                "descriptor_requirements": list(node.descriptor_requirements),
                "input_schema": dict(node.input_schema),
                "output_schema": dict(node.output_schema),
                "resource_limits": dict(node.resource_limits),
                "verifier_key": node.verifier_key,
                "rollback_key": node.rollback_key,
                "refusal_key": node.refusal_key,
                "evidence_template_hash": node.evidence_template_hash,
            })
        authority = {"maximum": self.maximum_authority}
        if self.capability_lease:
            authority["capability_lease"] = self.capability_lease
        return ComputeCrystal(
            identity=self.identity,
            task_family=list(self.task_family),
            authority=authority,
            applicability={
                "source_family_hash": self.source_family_hash,
                "policy_generation": policy_generation,
                "negative_conditions": list(self.negative_conditions),
                "opcode_catalog_digest": self.opcode_catalog_digest,
            },
            parameters={name: dict(schema) for name, schema in self.parameters.items()},
            preconditions=[{"id": f"precondition_{index}", "expression": value, "verifier": "runtime_applicability_revalidation"} for index, value in enumerate(self.preconditions)],
            execution_graph={
                "nodes": nodes,
                "edges": [[source, target] for source, target, _relation in self.edges],
                "edge_evidence": [{"source": source, "target": target, "relation": relation} for source, target, relation in self.edges],
            },
            postconditions=list(self.postconditions),
            topology={
                "descriptor_requirements": sorted({kind for node in self.nodes for kind in node.descriptor_requirements}),
                "descriptor_constraints": sorted({value for node in self.nodes for value in node.descriptor_constraints}),
            },
            evidence_requirements=["source_episode_hashes", "opcode_receipts", "postcondition_receipts", "control_evidence_root"],
            economics={"resource_envelope": dict(self.resource_envelope)},
            decay={"expires_after_days": int(expires_after_days), "policy_generation": policy_generation},
            signer=signer,
        ).sealed()


def default_opcode_registry() -> OpcodeRegistry:
    # Full /proc fd-to-inode attribution can legitimately exceed 100 ms on a
    # busy workstation; the bound remains finite and replay-enforced.
    common_observe = {"cpu_time_ms": 1000.0, "wall_time_ms": 3000.0}
    return OpcodeRegistry((
        OpcodeSpec(
            "socket.inventory", 1, "observation", "context_only", "sensorium.socket_inventory",
            {"network_namespace": "string"}, {"socket_state": "object"}, ("requested_port",), (),
            common_observe, "verifier.socket_inventory_complete",
        ),
        OpcodeSpec(
            "socket.reconcile", 1, "observation", "context_only", "sensorium.socket_reconcile",
            {"socket_observation": "object"}, {"socket_identity": "socket_descriptor"}, (), (),
            common_observe, "verifier.socket_identity_content_bound",
        ),
        OpcodeSpec(
            "repair.select_branch", 1, "decision", "proposal_only", "planner.port_conflict_branch",
            {"socket_state": "object"}, {"selected_branch": "string"}, ("requested_port",), ("socket",),
            {"cpu_time_ms": 50.0, "wall_time_ms": 500.0}, "verifier.branch_within_allowlist",
        ),
        OpcodeSpec(
            "service.verify_health", 1, "verification", "verify_only", "verifier.service_health",
            {"service_identity": "string"}, {"healthy": "boolean"}, ("requested_port",), ("socket",),
            {"cpu_time_ms": 100.0, "wall_time_ms": 3000.0}, "verifier.health_probe_receipt",
        ),
        OpcodeSpec(
            "process_lease.revalidate", 1, "verification", "verify_only", "process_supervisor.revalidate",
            {"process_lease": "process_descriptor"}, {"identity_current": "boolean"}, (), ("process",),
            {"cpu_time_ms": 50.0, "wall_time_ms": 500.0}, "verifier.process_lease_current",
        ),
        OpcodeSpec(
            "port_lease.recover_descriptor", 1, "actuation", "bounded_execute", "port_lease.recover_descriptor",
            {"port_lease": "port_lease_descriptor"}, {"socket": "socket_descriptor"}, ("requested_port",), ("port_lease",),
            {"cpu_time_ms": 100.0, "wall_time_ms": 2000.0}, "verifier.recovered_socket_matches_lease",
            "rollback.close_duplicate_descriptor", "refuse.on_lease_or_generation_drift",
        ),
        OpcodeSpec(
            "file.inspect_source", 1, "observation", "context_only", "sensorium.file_source",
            {"workspace": "workspace_descriptor"}, {"source_state": "object"}, ("workspace_identity",), ("workspace",),
            {"cpu_time_ms": 100.0, "wall_time_ms": 500.0}, "verifier.file_source_bounded",
        ),
        OpcodeSpec(
            "build.select_branch", 1, "decision", "proposal_only", "planner.build_repair_branch",
            {"source_state": "object"}, {"selected_branch": "string"}, ("workspace_identity",), ("workspace",),
            {"cpu_time_ms": 50.0, "wall_time_ms": 500.0}, "verifier.build_branch_allowlisted",
        ),
        OpcodeSpec(
            "build.render_artifact", 1, "actuation", "bounded_execute", "builder.render_canonical_artifact",
            {"source_state": "object"}, {"artifact_state": "object"}, ("workspace_identity",), ("workspace",),
            {"cpu_time_ms": 200.0, "wall_time_ms": 1000.0}, "verifier.artifact_write_bounded",
            "rollback.restore_generated_artifact", "refuse.on_invalid_source_or_workspace",
        ),
        OpcodeSpec(
            "artifact.verify_build", 1, "verification", "verify_only", "verifier.canonical_build_artifact",
            {"artifact_state": "object"}, {"verified": "boolean"}, ("workspace_identity",), ("workspace",),
            {"cpu_time_ms": 100.0, "wall_time_ms": 500.0}, "verifier.canonical_build_receipt",
        ),
        OpcodeSpec(
            "disk.inspect_pressure", 1, "observation", "context_only", "sensorium.disk_pressure",
            {"workspace": "workspace_descriptor"}, {"manifest": "cleanup_manifest", "pressure": "object"},
            ("workspace_identity", "cleanup_manifest_digest", "approval_receipt_digest"), ("workspace",),
            {"cpu_time_ms": 500.0, "wall_time_ms": 3000.0}, "verifier.disk_manifest_bound",
        ),
        OpcodeSpec(
            "disk.plan_cleanup", 1, "decision", "proposal_only", "planner.disk_cleanup",
            {"manifest": "cleanup_manifest"}, {"selected_branch": "string"},
            ("workspace_identity", "cleanup_manifest_digest", "approval_receipt_digest"), ("workspace",),
            {"cpu_time_ms": 100.0, "wall_time_ms": 500.0}, "verifier.disk_cleanup_branch_allowlisted",
        ),
        OpcodeSpec(
            "disk.quarantine_cleanup", 1, "actuation", "bounded_execute", "disk.quarantine_and_purge",
            {"manifest": "cleanup_manifest"}, {"cleanup_effect": "object"},
            ("workspace_identity", "cleanup_manifest_digest", "approval_receipt_digest"), ("workspace",),
            {"cpu_time_ms": 1000.0, "wall_time_ms": 5000.0}, "verifier.disk_cleanup_bounded",
            "rollback.restore_quarantined_files", "refuse.on_manifest_or_approval_drift",
        ),
        OpcodeSpec(
            "disk.verify_cleanup", 1, "verification", "verify_only", "verifier.disk_cleanup",
            {"cleanup_effect": "object"}, {"verified": "boolean"},
            ("workspace_identity", "cleanup_manifest_digest", "approval_receipt_digest"), ("workspace",),
            {"cpu_time_ms": 200.0, "wall_time_ms": 1000.0}, "verifier.disk_cleanup_receipt",
        ),
    ))


class TypedCrystalCompiler:
    def __init__(self, registry: OpcodeRegistry | None = None):
        self.registry = registry or default_opcode_registry()

    def compile(self, candidate: Any, *, capability_lease: str = "") -> ExecutableCrystalIR:
        invariants = candidate.invariants or {}
        templates = list(invariants.get("step_templates") or ())
        if len(templates) != len(candidate.execution_graph):
            raise ValueError("candidate lacks aligned step templates")
        nodes = []
        maximum = ArtifactAuthority.CONTEXT_ONLY
        for index, (opcode, template) in enumerate(zip(candidate.execution_graph, templates)):
            spec = self.registry.resolve(opcode, 1)
            authority = ArtifactAuthority.from_label(spec.authority)
            maximum = max(maximum, authority)
            placeholders = set(PARAMETER_RE.findall(str(template)))
            if placeholders - set(candidate.parameters):
                raise ValueError(f"opcode template references undeclared parameters: {sorted(placeholders - set(candidate.parameters))}")
            if placeholders - set(spec.allowed_parameters):
                raise ValueError(f"opcode does not allow parameters: {sorted(placeholders - set(spec.allowed_parameters))}")
            constraints = tuple(dict.fromkeys(str(item) for item in template.get("descriptor_refs") or ()))
            observed_kinds = tuple(item.split(":", 1)[1] for item in constraints if item.startswith("descriptor_type:"))
            if set(spec.required_descriptors) - set(observed_kinds):
                raise ValueError(f"opcode {opcode} lacks required descriptor evidence")
            nodes.append(TypedCrystalNode(
                node_id=f"step:{index}", opcode=opcode, opcode_version=1,
                phase=spec.phase, authority=spec.authority, handler_key=spec.handler_key,
                parameter_bindings={name: f"{{{{{name}}}}}" for name in sorted(placeholders)},
                descriptor_requirements=spec.required_descriptors,
                descriptor_constraints=constraints,
                input_schema=dict(spec.input_schema), output_schema=dict(spec.output_schema),
                resource_limits=dict(spec.resource_limits), verifier_key=spec.verifier_key,
                rollback_key=spec.rollback_key, refusal_key=spec.refusal_key,
                evidence_template_hash=content_hash(template),
            ))
        if maximum is ArtifactAuthority.BOUNDED_EXECUTE and not capability_lease:
            raise ValueError("bounded executable candidate requires a capability lease")
        edge_values = [
            (f"step:{source}", f"step:{target}", relation)
            for source, target, relation, _confidence in invariants.get("causal_topology") or ()
        ]
        edge_values.extend((f"step:{index - 1}", f"step:{index}", "SEQUENCE") for index in range(1, len(nodes)))
        edges = tuple(dict.fromkeys(edge_values))
        result = ExecutableCrystalIR(
            identity=candidate.identity, task_family=tuple(candidate.task_family),
            parameters=dict(candidate.parameter_schemas or {}), preconditions=tuple(candidate.preconditions),
            nodes=tuple(nodes), edges=edges, postconditions=tuple(candidate.postconditions),
            negative_conditions=tuple(candidate.negative_conditions), evidence=tuple(candidate.evidence),
            source_family_hash=candidate.source_episode_hash, maximum_authority=maximum.label,
            capability_lease=capability_lease, resource_envelope=dict(candidate.resource_envelope or {}),
            opcode_catalog_digest=self.registry.catalog()["catalog_digest"],
        ).sealed()
        result.validate(self.registry)
        return result
