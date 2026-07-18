import pytest

from app.kernel.compute.port_conflict_crystal import PortConflictRepairCrystal
from app.kernel.sensorium.contracts import ProcessLease


LEASE = ProcessLease(
    boot_id="boot-test", pid_at_observation=123, start_time_ticks=456,
    executable_digest="sha256:" + "a" * 64, cgroup_id="/beast/test",
    pid_namespace_inode=1, mount_namespace_inode=2,
    parent_identity_hash="sha256:" + "b" * 64, owner_scope="test",
    acquired_at="2026-01-01T00:00:00Z",
).with_identity()
LISTENER = {"owning_process": LEASE.lease_id, "executable_digest": LEASE.executable_digest}


@pytest.mark.parametrize(
    ("listener", "lease", "started", "healthy", "approved", "identity", "action"),
    [
        (None, False, False, False, False, None, "bind_requested_port"),
        (LISTENER, True, True, True, False, LEASE, "reuse_existing_service"),
        (LISTENER, True, True, False, False, LEASE, "request_operator_approval"),
        ({**LISTENER, "executable_digest": "sha256:" + "b" * 64}, True, True, True, False, LEASE, "request_operator_approval"),
        (LISTENER, False, False, False, False, LEASE, "request_operator_approval"),
        (LISTENER, False, True, False, True, LEASE, "retire_stale_process_and_rebind"),
    ],
)
def test_heldout_port_conflict_matrix(listener, lease, started, healthy, approved, identity, action):
    result = PortConflictRepairCrystal().plan(requested_port=8005, listener=listener, lease_match=lease, process_start_verified=started, health_ok=healthy, operator_approved=approved, process_lease=identity)
    assert result.action == action
