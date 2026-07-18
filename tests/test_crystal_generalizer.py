import pytest

from app.kernel.compute.crystal_generalizer import CrystalGeneralizer
from app.kernel.sensorium.runtime import SensoriumRuntime


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _episode(runtime, mission, port, *, status="verified_success", subject=None, include_dependency=True):
    socket_id = "socket:sha256:" + f"{port:064x}"[-64:]
    state = f"socket_state:port:{port}"
    runtime.observe_physical(
        event_type="socket.inventoried", source="test_socket_sensor",
        payload_schema="beast.sensor.socket.inventoried.v1",
        operation="socket.inventory", phase="observation",
        subject=subject or f"port:{port}", result="observed",
        payload={
            "produces": [state], "descriptor_refs": [socket_id],
            "state_transition": {"resource": f"port:{port}", "from": "unknown", "to": "occupied"},
        }, mission_id=mission,
    )
    runtime.observe_physical(
        event_type="repair.branch_selected", source="test_planner",
        payload_schema="beast.sensor.repair.branch.v1",
        operation="repair.select_branch", phase="decision",
        subject=subject or f"port:{port}", result="selected",
        payload={
            "reads": [state] if include_dependency else [],
            "branch": "reuse_existing_service" if status == "verified_success" else "request_operator_approval",
            "descriptor_refs": [socket_id],
        }, mission_id=mission,
    )
    runtime.observe_physical(
        event_type="health.verified", source="test_health_verifier",
        payload_schema="beast.sensor.health.verified.v1",
        operation="service.verify_health", phase="verification",
        subject="service:beast-api",
        result="success" if status == "verified_success" else "refused",
        payload={"requires": [state], "descriptor_refs": [socket_id]},
        mission_id=mission,
    )
    return runtime.close_episode(
        mission, objective_hash=HASH_A, workspace_identity="workspace:test",
        initial_state_hash=HASH_B,
        outcome={"status": status, "effect_hash": HASH_A},
        resources={"cpu_time_ms": float(port % 10 + 1)},
    )


def test_natural_episode_family_infers_bounded_port_candidate(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    for index, port in enumerate((43001, 43002, 43003), start=1):
        _episode(runtime, f"positive-{index}", port)
    _episode(runtime, "negative-refusal", 43004, status="refused")

    crystal, receipt = runtime.generalize_episodes(
        ["positive-1", "positive-2", "positive-3", "negative-refusal"],
        identity="crystal:learned-port-reuse:v1",
        task_family=["address_already_in_use"],
    )

    assert crystal.parameters == ("requested_port",)
    assert crystal.parameter_schemas["requested_port"] == {
        "type": "integer", "minimum": 1, "maximum": 65535,
        "observed_min": 43001, "observed_max": 43003, "observed_count": 3,
    }
    assert crystal.execution_graph == ("socket.inventory", "repair.select_branch", "service.verify_health")
    assert "outcome_status:refused" in crystal.negative_conditions
    assert "branch:request_operator_approval" in crystal.negative_conditions
    assert "effect_result:service.verify_health:refused" in crystal.negative_conditions
    assert crystal.topology == ("descriptor_type:socket",)
    assert receipt.positive_episode_hashes == tuple(crystal.evidence[:3])
    assert receipt.family_hash == crystal.source_episode_hash
    assert crystal.resource_envelope["cpu_time_ms"] == 4.0


def test_generalizer_rejects_arbitrary_varying_causal_subject(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    for index, service in enumerate(("alpha", "beta", "gamma"), start=1):
        _episode(runtime, f"positive-{index}", 43001, subject=f"service:{service}")
    with pytest.raises(ValueError, match="unsafe varying causal value"):
        runtime.generalize_episodes(
            ["positive-1", "positive-2", "positive-3"],
            identity="crystal:unsafe:v1", task_family=["test"],
        )


def test_generalizer_requires_matching_evidence_backed_causal_topology(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    _episode(runtime, "positive-1", 43001)
    _episode(runtime, "positive-2", 43002)
    _episode(runtime, "positive-3", 43003, include_dependency=False)
    with pytest.raises(ValueError, match="causal topology"):
        runtime.generalize_episodes(
            ["positive-1", "positive-2", "positive-3"],
            identity="crystal:misaligned:v1", task_family=["test"],
        )


def test_generalizer_requires_multiple_natural_successes(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    _episode(runtime, "positive-1", 43001)
    _episode(runtime, "negative", 43002, status="refused")
    with pytest.raises(ValueError, match="at least 3"):
        runtime.generalize_episodes(
            ["positive-1", "negative"], identity="crystal:too-early:v1", task_family=["test"],
        )


def test_generalization_is_deterministic_across_episode_input_order(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    episodes = [_episode(runtime, f"positive-{index}", port) for index, port in enumerate((43001, 43002, 43003), 1)]
    generalizer = CrystalGeneralizer()
    first, first_receipt = generalizer.generalize(
        episodes, identity="crystal:deterministic:v1", task_family=["test"],
    )
    second, second_receipt = generalizer.generalize(
        reversed(episodes), identity="crystal:deterministic:v1", task_family=["test"],
    )
    assert first.digest == second.digest
    assert first_receipt == second_receipt


def test_generalizer_rejects_tampered_episode_mapping(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path, boot_id="boot-test")
    episodes = [_episode(runtime, f"positive-{index}", port) for index, port in enumerate((43001, 43002, 43003), 1)]
    tampered = episodes[0].to_dict()
    tampered["outcome"] = {"status": "verified_success", "effect_hash": HASH_B}
    with pytest.raises(ValueError, match="episode_hash does not match"):
        CrystalGeneralizer().generalize(
            [tampered, episodes[1], episodes[2]],
            identity="crystal:tampered:v1", task_family=["test"],
        )
