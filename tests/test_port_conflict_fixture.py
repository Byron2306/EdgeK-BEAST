from app.kernel.compute.port_conflict_fixture import start_listener
from app.kernel.compute.port_conflict_crystal import PortConflictRepairCrystal
from app.kernel.compute.socket_inventory import tcp_listeners, inode_owners
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector


def test_real_process_socket_evidence_drives_safe_reuse():
    proc, evidence = start_listener()
    try:
        lease = LinuxProcessIdentityCollector().collect(evidence.pid, owner_scope="port-conflict-fixture")
        listener = {"owning_process": lease.lease_id, "service_id": "fixture", "pid": evidence.pid, "start_time_ticks": evidence.start_time_ticks, "executable_digest": evidence.executable_digest}
        kernel = next(item for item in tcp_listeners() if item.port == evidence.port)
        assert evidence.pid in inode_owners(kernel.inode)
        plan = PortConflictRepairCrystal().plan(requested_port=evidence.port, listener=listener, lease_match=True, process_start_verified=True, health_ok=evidence.health_probe_passed, process_lease=lease)
        assert plan.action == "reuse_existing_service"
        assert proc.poll() is None
    finally:
        proc.terminate(); proc.wait(timeout=3)
