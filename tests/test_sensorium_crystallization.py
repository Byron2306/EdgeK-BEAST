from app.kernel.sensorium.runtime import SensoriumRuntime


def test_closed_sensorium_episode_can_crystallize(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path)
    runtime.observe_owned(event_type="socket.bound", source="test", payload_schema="test.v1", payload={}, mission_id="m1")
    runtime.observe_owned(event_type="health.verified", source="test", payload_schema="test.v1", payload={}, mission_id="m1")
    runtime.close_episode("m1", objective_hash="sha256:" + "a" * 64, workspace_identity="workspace:test", initial_state_hash="sha256:" + "b" * 64, outcome={"status": "verified_success", "effect_hash": "sha256:" + "c" * 64})
    crystal = runtime.crystallize_episode("m1", identity="crystal:test:v1", task_family=["test"], parameters=["port"], preconditions=["listener"], postconditions=["healthy"])
    assert crystal.identity == "crystal:test:v1"
    assert len(crystal.execution_graph) == 2
