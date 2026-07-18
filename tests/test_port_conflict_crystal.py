from app.kernel.compute.port_conflict_crystal import PortConflictRepairCrystal
from app.kernel.sensorium.contracts import ProcessLease


def process_lease():
    return ProcessLease(
        boot_id="boot-test", pid_at_observation=123, start_time_ticks=456,
        executable_digest="sha256:" + "a" * 64, cgroup_id="/beast/test",
        pid_namespace_inode=1, mount_namespace_inode=2,
        parent_identity_hash="sha256:" + "b" * 64, owner_scope="test",
        acquired_at="2026-01-01T00:00:00Z",
    ).with_identity()


def listener(lease=None):
    lease = lease or process_lease()
    return {"owning_process": lease.lease_id, "executable_digest": lease.executable_digest, "service_id": "beast-api"}


def test_crystal_reuses_verified_healthy_leased_service():
    lease = process_lease()
    plan = PortConflictRepairCrystal().plan(requested_port=8005, listener=listener(lease), lease_match=True, process_start_verified=True, health_ok=True, process_lease=lease)
    assert plan.action == "reuse_existing_service"
    assert plan.approval_required is False
    assert plan.evidence_digest.startswith("sha256:")


def test_crystal_never_retire_unknown_process_without_approval():
    plan = PortConflictRepairCrystal().plan(requested_port=8005, listener=listener(), lease_match=False, process_start_verified=False, health_ok=False)
    assert plan.action == "request_operator_approval"
    assert plan.approval_required is True


def test_executable_digest_is_not_accepted_as_process_identity():
    value = {"owning_process": "process:" + "sha256:" + "a" * 64, "executable_digest": "sha256:" + "a" * 64}
    plan = PortConflictRepairCrystal().plan(
        requested_port=8005, listener=value, lease_match=True,
        process_start_verified=True, health_ok=True,
    )
    assert plan.action == "request_operator_approval"


def test_crystal_handles_free_port():
    plan = PortConflictRepairCrystal().plan(requested_port=8005, listener=None, lease_match=False, process_start_verified=False, health_ok=False)
    assert plan.action == "bind_requested_port"


def test_concrete_bind_requires_independent_probes_and_retains_lease():
    from tests.test_port_lease_broker import broker
    plan = PortConflictRepairCrystal().plan(
        requested_port=43000, listener=None, lease_match=False,
        process_start_verified=False, health_ok=False,
    )
    leases = broker()
    with __import__("pytest").raises(ValueError, match="probes"):
        PortConflictRepairCrystal().execute_with_socket_probe(plan, broker=leases)
    result = PortConflictRepairCrystal().execute_with_socket_probe(
        plan, broker=leases, service_id="beast-api", workspace_id="workspace-1",
        service_handoff=lambda _plan, lease, _sock: {"lease_id": lease.lease_id},
        listener_probe=lambda _plan, effect: bool(effect["lease_id"]),
        registry_probe=lambda _plan, effect: effect["listener_generation"] == 1,
        health_probe=lambda _plan, effect: effect["service_handoff"]["lease_id"] == effect["lease_id"],
    )
    assert result["status"] == "verified_success"
    assert leases.snapshot()[0].lifecycle_state == "handed_off"
    leases.release(result["effect"]["lease_id"])
