from app.kernel.compute.runtime_crystallizer import RuntimeCrystallizer


def test_runtime_episode_becomes_parameterized_crystal_ir():
    crystal = RuntimeCrystallizer().extract(
        {"episode_hash": "sha256:" + "a" * 64, "events": [{"type": "query_socket_inventory"}, {"type": "verify_health"}], "evidence": ["socket:1"]},
        identity="crystal:port-conflict-repair:v2", task_family=["service_startup_failure"], parameters=["requested_port"],
        preconditions=["listener_socket_identified"], postconditions=["expected_service_listening"],
    )
    assert crystal.execution_graph == ("query_socket_inventory", "verify_health")
    assert crystal.digest.startswith("sha256:")


def test_empty_episode_cannot_crystallize():
    import pytest
    with pytest.raises(ValueError, match="no causal events"):
        RuntimeCrystallizer().extract({}, identity="crystal:x", task_family=[], parameters=[], preconditions=[], postconditions=[])

