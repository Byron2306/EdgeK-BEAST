import pytest

from app.kernel.sensorium import SocketIdentityReconciler, SocketReconciliationError


def observation():
    return {
        "family": "AF_INET", "protocol": "TCP", "local_address_class": "loopback",
        "local_port": 8005, "remote_scope": "loopback",
        "owning_process": "process:sha256:" + "a" * 64, "service_id": "beast-api",
        "workspace_id": "edgek-beast", "cgroup_id": "cgroup:mission-1",
        "listener_generation": 2, "opened_at_monotonic_ns": 12,
        "policy_class": "operator",
    }


def test_socket_observation_becomes_content_bound_identity():
    first = SocketIdentityReconciler().reconcile(observation())
    key = (
        first.identity.family, first.identity.protocol, first.identity.local_address_class,
        first.identity.local_port, first.identity.workspace_id, first.identity.service_id,
        first.identity.listener_generation, first.identity.network_namespace, first.identity.vrf,
    )
    result = SocketIdentityReconciler().reconcile(observation(), lease_index={key: "portlease:abc"})
    assert result.identity.identity.startswith("socket:")
    assert result.lease_match is True
    assert result.lease_id == "portlease:abc"


def test_port_only_lease_is_a_non_authoritative_compatibility_hint():
    result = SocketIdentityReconciler().reconcile(observation(), lease_index={8005: "portlease:legacy"})
    assert result.lease_match is False
    assert result.lease_id == ""
    assert result.compatibility_hint is True


def test_socket_reconciliation_fails_closed_on_missing_attribution():
    value = observation()
    del value["owning_process"]
    with pytest.raises(SocketReconciliationError, match="missing socket fields"):
        SocketIdentityReconciler().reconcile(value)
