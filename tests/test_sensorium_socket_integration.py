from app.kernel.sensorium.runtime import SensoriumRuntime


def test_socket_reconciliation_is_visible_as_read_only_topology(tmp_path):
    runtime = SensoriumRuntime(export_root=tmp_path)
    observation = {
        "family": "AF_INET", "protocol": "TCP", "local_address_class": "loopback",
        "local_port": 8005, "remote_scope": "loopback",
        "owning_process": "process:sha256:" + "a" * 64, "service_id": "beast-api",
        "workspace_id": "edgek-beast", "cgroup_id": "cgroup:mission-1",
        "listener_generation": 1, "opened_at_monotonic_ns": 1, "policy_class": "operator",
    }
    initial = runtime.socket_reconciler.reconcile(observation)
    identity = initial.identity
    key = (
        identity.family, identity.protocol, identity.local_address_class,
        identity.local_port, identity.workspace_id, identity.service_id,
        identity.listener_generation, identity.network_namespace, identity.vrf,
    )
    runtime.observe_socket(observation, lease_index={key: "portlease:test"})
    state = runtime.state()
    assert state["actuator_available"] is False
    assert state["socket_topology"][0]["lease_match"] is True
    assert state["recent_event_types"]["socket.reconciled"] == 1
