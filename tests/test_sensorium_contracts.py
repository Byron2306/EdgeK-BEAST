from dataclasses import replace

import pytest

from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.sensorium import (
    ArtifactAuthority,
    ComputeCrystal,
    ContractValidationError,
    CrystalArtifactClass,
    CrystalArtifactDescriptor,
    ProcessLease,
    RuntimeEpisode,
    SensorEvent,
    SocketIdentity,
    authority_allows,
    describe_existing_artifact,
    sensorium_architecture_decision_register,
)
from app.kernel.sensorium.contracts import content_hash


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def process_lease() -> ProcessLease:
    return ProcessLease(
        boot_id="boot-test",
        pid_at_observation=4242,
        start_time_ticks=9001,
        executable_digest=HASH_A,
        cgroup_id="beast.slice/mission-test",
        pid_namespace_inode=101,
        mount_namespace_inode=202,
        parent_identity_hash=HASH_B,
        owner_scope="beast_mission",
        acquired_at="2026-07-14T00:00:00Z",
    ).with_identity()


def sensor_event(lease: ProcessLease) -> SensorEvent:
    return SensorEvent(
        event_type="process.exec",
        source="beast_owned_process_sensor",
        source_instance="sensor-test",
        boot_id=lease.boot_id,
        source_sequence=1,
        cpu_sequence=0,
        monotonic_ns=123456,
        wall_time="2026-07-14T00:00:01Z",
        attribution={"process_lease_id": lease.lease_id, "mission_id": "mission-test"},
        confidence=1.0,
        confidence_method="beast_owned_spawn",
        gaps_before=0,
        loss_counter=0,
        privacy={
            "class": "internal_sensitive",
            "raw_retention": "ephemeral",
            "export_allowed": False,
            "redaction_status": "passed",
        },
        payload_schema="beast.sensor.process.exec.v1",
        payload={"executable_digest": lease.executable_digest},
    ).sealed()


def compute_crystal() -> ComputeCrystal:
    return ComputeCrystal(
        identity="crystal:port-conflict-repair:v1",
        task_family=["address_already_in_use"],
        authority={"maximum": "bounded_execute", "capability_lease": "port_conflict_repair"},
        applicability={"operating_system": "linux", "minimum_sensor_confidence": 0.9},
        parameters={
            "desired_service": {"type": "string"},
            "requested_port": {"type": "integer", "minimum": 1, "maximum": 65535},
        },
        preconditions=[{"id": "listener_identified", "verifier": "socket_inventory_binding"}],
        execution_graph={
            "nodes": [
                {"id": "inventory", "op": "query_socket_inventory"},
                {"id": "verify", "op": "verify_listener"},
            ],
            "edges": [["inventory", "verify"]],
        },
        postconditions=["expected_service_listening"],
        topology={"required_socket_roles": ["target_listener"]},
        evidence_requirements=["sensor_episode_hash", "verification_receipt"],
        economics={"maximum_cpu_ms": 2000},
        decay={"expires_after_days": 90},
        signer="beast-local-test",
    ).sealed()


def test_artifact_taxonomy_refuses_authority_escalation():
    assert authority_allows(CrystalArtifactClass.COMPUTE_CRYSTAL_IR, "bounded_execute")
    assert not authority_allows(CrystalArtifactClass.SEMANTIC_CACHE_ENTRY, "proposal_only")
    descriptor = CrystalArtifactDescriptor(
        artifact_class=CrystalArtifactClass.SEMANTIC_CACHE_ENTRY,
        authority=ArtifactAuthority.BOUNDED_EXECUTE,
        verification_state="promoted",
        applicability_hash=HASH_A,
        policy_generation="policy-v1",
        expires_at="2026-08-01T00:00:00Z",
    )
    with pytest.raises(ValueError, match="maximum is context_only"):
        descriptor.validate()


def test_existing_artifact_adapter_labels_without_granting_unpromoted_authority():
    semantic = describe_existing_artifact(
        {"beast_object_type": "semantic_cache_entry", "state": "active", "task_family": "repair"},
        policy_generation="policy-v1",
        expires_at="2026-08-01T00:00:00Z",
    )
    assert semantic.artifact_class is CrystalArtifactClass.SEMANTIC_CACHE_ENTRY
    assert semantic.authority is ArtifactAuthority.CONTEXT_ONLY
    assert semantic.verification_state == "promoted"

    candidate = describe_existing_artifact(
        {"beast_object_type": "deterministic_displacement_proof", "state": "candidate", "task_class": "repair"},
        policy_generation="policy-v1",
        expires_at="2026-08-01T00:00:00Z",
    )
    assert candidate.authority is ArtifactAuthority.PROPOSAL_ONLY

    with pytest.raises(ValueError, match="unsupported crystal-like"):
        describe_existing_artifact(
            {"beast_object_type": "mystery_crystal"},
            policy_generation="policy-v1",
            expires_at="2026-08-01T00:00:00Z",
        )


def test_sensorium_architecture_decisions_record_claim_boundaries():
    register = sensorium_architecture_decision_register()
    assert register["decision_count"] == 5
    assert {item["adr_id"] for item in register["decisions"]} == {
        "SADR-001", "SADR-002", "SADR-003", "SADR-004", "SADR-005"
    }
    assert register["claim_boundary"]["capsule"] == "immutable_transport_not_authority_or_secrecy"


def test_process_and_socket_identities_are_content_bound():
    lease = process_lease()
    lease.validate()
    assert lease.to_dict()["pidfd_serialized"] is False
    with pytest.raises(ContractValidationError, match="does not match"):
        replace(lease, pid_at_observation=4243).validate()

    socket_identity = SocketIdentity(
        family="AF_INET",
        protocol="TCP",
        local_address_class="loopback",
        local_port=8005,
        remote_scope="none",
        owning_process=lease.lease_id,
        service_id="beast-api",
        workspace_id="edgek-beast",
        cgroup_id=lease.cgroup_id,
        listener_generation=14,
        opened_at_monotonic_ns=123500,
        policy_class="operator",
    ).with_identity()
    socket_identity.validate()
    with pytest.raises(ContractValidationError, match="does not match"):
        replace(socket_identity, listener_generation=15).validate()


def test_sensor_event_and_episode_are_hash_stable_and_tamper_evident():
    lease = process_lease()
    event = sensor_event(lease)
    event.validate()
    assert event.payload_sha256 == content_hash(event.payload)
    with pytest.raises(ContractValidationError, match="payload_sha256"):
        replace(event, payload={"executable_digest": HASH_B}).validate()

    episode = RuntimeEpisode(
        mission_id="mission-test",
        objective_hash=HASH_A,
        workspace_identity="edgek-beast",
        initial_state_hash=HASH_B,
        event_ids=[event.event_id],
        source_loss={event.source: 0},
        causal_graph={"nodes": [event.event_id], "edges": []},
        resources={"cpu_time_ms": 2.5, "memory_peak_bytes": 4096},
        outcome={"status": "verified_success", "effect_hash": HASH_A, "rollback_tested": True},
    ).sealed()
    episode.validate()
    assert episode.to_dict()["authority"] == "evidence_only"
    with pytest.raises(ContractValidationError, match="episode_hash"):
        replace(episode, mission_id="mission-tampered").validate()


def test_compute_crystal_requires_acyclic_content_bound_graph_and_lease():
    crystal = compute_crystal()
    crystal.validate()
    assert crystal.to_dict()["artifact_class"] == "compute_crystal_ir"

    cyclic = replace(
        crystal,
        execution_graph={
            "nodes": [{"id": "a", "op": "one"}, {"id": "b", "op": "two"}],
            "edges": [["a", "b"], ["b", "a"]],
        },
    ).sealed()
    with pytest.raises(ContractValidationError, match="acyclic"):
        cyclic.validate()

    unleased = replace(crystal, authority={"maximum": "bounded_execute"}).sealed()
    with pytest.raises(ContractValidationError, match="capability_lease"):
        unleased.validate()


def test_canon_catalog_accepts_all_sensorium_contracts():
    registry = CanonRegistry()
    lease = process_lease()
    event = sensor_event(lease)
    episode = RuntimeEpisode(
        mission_id="mission-test",
        objective_hash=HASH_A,
        workspace_identity="edgek-beast",
        initial_state_hash=HASH_B,
        event_ids=[event.event_id],
        source_loss={event.source: 0},
        causal_graph={"nodes": [event.event_id], "edges": []},
        resources={"cpu_time_ms": 1.0},
        outcome={"status": "verified_success", "effect_hash": HASH_A},
    ).sealed()
    socket_identity = SocketIdentity(
        family="AF_INET6",
        protocol="TCP",
        local_address_class="loopback",
        local_port=8005,
        remote_scope="none",
        owning_process=lease.lease_id,
        service_id="beast-api",
        workspace_id="edgek-beast",
        cgroup_id=lease.cgroup_id,
        listener_generation=1,
        opened_at_monotonic_ns=123500,
        policy_class="operator",
    ).with_identity()
    objects = [lease.to_dict(), event.to_dict(), episode.to_dict(), socket_identity.to_dict(), compute_crystal().to_dict()]

    assert all(registry.validate_object(obj)["valid"] for obj in objects)
    assert {obj["beast_object_type"] for obj in objects} <= set(registry.schema_catalog()["schemas"])


def test_canon_fails_closed_on_unknown_sensorium_contract_version():
    payload = compute_crystal().to_dict()
    payload["version"] = "2.0"

    report = CanonRegistry().validate_object(payload)

    assert report["valid"] is False
    assert any(error["path"] == "version" for error in report["errors"])
