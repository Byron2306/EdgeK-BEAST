import json

import pytest

from app.kernel.sensorium import ContractValidationError, SensoriumEventSequencer
from app.kernel.sensorium.adapters import BeastOwnedEventFactory
from app.kernel.sensorium.episode_builder import RuntimeEpisodeBuilder


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _publish(sequencer, builder, event):
    receipt = sequencer.publish(event)
    builder.ingest(receipt.admitted)
    return receipt.admitted.event


def _close(builder):
    return builder.close(
        "mission-physical",
        objective_hash=HASH_A,
        workspace_identity="workspace:test",
        initial_state_hash=HASH_B,
        outcome={"status": "verified_success", "effect_hash": HASH_A},
    )


def test_physical_effect_contract_rejects_ambiguous_effects():
    factory = BeastOwnedEventFactory(boot_id="boot-test")
    with pytest.raises(ContractValidationError, match="operation"):
        factory.physical_event(
            event_type="socket.bound",
            source="test",
            payload_schema="beast.sensor.socket.bound.v1",
            operation="bind",
            phase="actuation",
            subject="socket:target",
            result="success",
            mission_id="mission-physical",
        )
    with pytest.raises(ContractValidationError, match="distinct from/to"):
        factory.physical_event(
            event_type="socket.bound",
            source="test",
            payload_schema="beast.sensor.socket.bound.v1",
            operation="socket.bind",
            phase="actuation",
            subject="socket:target",
            result="success",
            payload={"state_transition": {"resource": "port:8101", "from": "free", "to": "free"}},
            mission_id="mission-physical",
        )


def test_temporal_adjacency_is_not_reported_as_causality():
    factory = BeastOwnedEventFactory(boot_id="boot-test")
    sequencer = SensoriumEventSequencer(capacity=8)
    builder = RuntimeEpisodeBuilder()
    for operation, subject in (("pressure.sample", "host:local"), ("socket.observe", "socket:target")):
        _publish(sequencer, builder, factory.physical_event(
            event_type=operation,
            source="test",
            payload_schema=f"test.{operation}.v1",
            operation=operation,
            phase="observation",
            subject=subject,
            result="observed",
            mission_id="mission-physical",
        ))

    episode = _close(builder)
    assert len(episode.causal_graph["ordered_edges"]) == 1
    assert episode.causal_graph["edges"] == episode.causal_graph["ordered_edges"]
    assert episode.causal_graph["edge_semantics"] == "order_only_compatibility_alias"
    assert episode.causal_graph["causal_edges"] == []


def test_resource_and_explicit_evidence_create_reconstructable_causal_graph():
    factory = BeastOwnedEventFactory(boot_id="boot-test")
    sequencer = SensoriumEventSequencer(capacity=8)
    builder = RuntimeEpisodeBuilder()
    inventory = _publish(sequencer, builder, factory.physical_event(
        event_type="socket.inventoried",
        source="test_socket_sensor",
        payload_schema="beast.sensor.socket.inventoried.v1",
        operation="socket.inventory",
        phase="observation",
        subject="port:8101",
        result="observed",
        payload={
            "produces": ["socket_state:port:8101"],
            "descriptor_refs": ["socket:sha256:" + "c" * 64],
            "state_transition": {"resource": "port:8101", "from": "unknown", "to": "occupied"},
        },
        mission_id="mission-physical",
    ))
    decision = _publish(sequencer, builder, factory.physical_event(
        event_type="repair.branch_selected",
        source="test_planner",
        payload_schema="beast.sensor.repair.branch.v1",
        operation="repair.select_branch",
        phase="decision",
        subject="port:8101",
        result="selected",
        payload={
            "reads": ["socket_state:port:8101"],
            "branch": "reuse_existing_service",
            "descriptor_refs": ["socket:sha256:" + "c" * 64],
        },
        mission_id="mission-physical",
    ))
    verified = _publish(sequencer, builder, factory.physical_event(
        event_type="health.verified",
        source="test_health_verifier",
        payload_schema="beast.sensor.health.verified.v1",
        operation="service.verify_health",
        phase="verification",
        subject="service:beast-api",
        result="success",
        payload={
            "caused_by_event_ids": [decision.event_id],
            "requires": ["socket_state:port:8101"],
            "descriptor_refs": ["socket:sha256:" + "c" * 64],
        },
        mission_id="mission-physical",
    ))

    episode = _close(builder)
    edges = episode.causal_graph["causal_edges"]
    assert any(edge["source"] == inventory.event_id and edge["target"] == decision.event_id and edge["relation"] == "READS" for edge in edges)
    assert any(edge["source"] == decision.event_id and edge["target"] == verified.event_id and edge["relation"] == "EXPLICIT_CAUSE" for edge in edges)
    assert any(edge["source"] == inventory.event_id and edge["target"] == verified.event_id and edge["relation"] == "REQUIRES" for edge in edges)
    facts = episode.causal_graph["event_facts"]
    assert facts[decision.event_id]["branch"] == "reuse_existing_service"
    assert facts[verified.event_id]["phase"] == "verification"
    encoded = json.dumps(episode.to_dict(), sort_keys=True)
    assert "physical_effect" not in encoded
    assert "payload_sha256" in encoded
