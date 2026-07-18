from app.kernel.execution.cgroup_capsule import CgroupAuthorization, CgroupMissionCapsule
from app.kernel.execution.isolation_readiness import IsolationReadinessProbe
from app.kernel.execution.namespace_isolation import NamespaceIsolationAuthorization, NamespaceIsolationRunner
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.execution.cgroup_delegation import CgroupDelegationManager
import shutil
import pytest


def test_delegation_readiness_is_read_only_and_never_overclaims_clone3(tmp_path):
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "cgroup.controllers").write_text("cpu memory pids io\n", encoding="utf-8")
    (cgroup / "cgroup.subtree_control").write_text("cpu memory pids io\n", encoding="utf-8")
    (cgroup / "cgroup.procs").write_text("", encoding="utf-8")
    before = {item.name: item.read_text(encoding="utf-8") for item in cgroup.iterdir()}
    state = IsolationReadinessProbe(cgroup_root=cgroup).state()
    after = {item.name: item.read_text(encoding="utf-8") for item in cgroup.iterdir()}
    assert state["cgroup"]["delegation_proven"] is True
    assert state["clone3_into_cgroup_available"] is False
    assert state["full_isolation_claim_allowed"] is False
    assert before == after


def test_mission_capsule_resource_limits_are_written_and_read_back(tmp_path):
    capsule = CgroupMissionCapsule(tmp_path, "mission-isolated", synthetic=True)
    capsule.path.mkdir(parents=True)
    for name in ("cpu.max", "memory.max", "pids.max", "io.max"):
        (capsule.path / name).write_text("", encoding="utf-8")
    authorization = CgroupAuthorization(
        action="configure",
        mission_id="mission-isolated",
        approved_by="operator",
        approval_receipt_id="approval:configure",
        reason="bounded replay resources",
    )
    receipt = capsule.configure_resources(
        {"cpu.max": "50000 100000", "memory.max": "268435456", "pids.max": "32"},
        authorization,
    )
    assert receipt["confirmed"] is True
    assert receipt["details"]["observed_limits"]["pids.max"] == "32"


@pytest.mark.skipif(shutil.which("unshare") is None, reason="unshare is unavailable")
def test_live_user_mount_pid_and_network_namespaces_are_kernel_distinct(tmp_path):
    sensorium = SensoriumRuntime(capacity=16, export_root=tmp_path / "sensorium", boot_id="boot-isolation")
    receipt = NamespaceIsolationRunner(sensorium=sensorium).run(
        "mission-isolated",
        NamespaceIsolationAuthorization(
            mission_id="mission-isolated",
            approved_by="test-operator",
            approval_receipt_id="approval:namespace",
            reason="held-out destructive replay",
        ),
    )
    assert receipt.full_namespace_isolation_proven is True
    assert set(receipt.separated_namespaces) == {"mnt", "pid", "net", "user"}
    assert receipt.non_loopback_route_count == 0
    assert sensorium.sequencer.latest(1)[0].event.event_type == "isolation.namespace_verified"


def test_namespace_failure_is_evidenced_as_reduced_authority(tmp_path):
    sensorium = SensoriumRuntime(capacity=16, export_root=tmp_path / "sensorium", boot_id="boot-isolation")
    receipt = NamespaceIsolationRunner(sensorium=sensorium, unshare_binary="/bin/false").run(
        "mission-reduced",
        NamespaceIsolationAuthorization(
            mission_id="mission-reduced",
            approved_by="test-operator",
            approval_receipt_id="approval:namespace",
            reason="negative control",
        ),
    )
    assert receipt.full_namespace_isolation_proven is False
    assert sensorium.sequencer.latest(1)[0].event.event_type == "isolation.namespace_reduced"


def test_populated_parent_refuses_controller_enablement_without_mutation(tmp_path):
    parent = tmp_path / "delegated"
    parent.mkdir()
    (parent / "cgroup.controllers").write_text("memory pids\n", encoding="utf-8")
    (parent / "cgroup.subtree_control").write_text("", encoding="utf-8")
    (parent / "cgroup.procs").write_text("123\n", encoding="utf-8")
    sensorium = SensoriumRuntime(capacity=16, export_root=tmp_path / "sensorium", boot_id="boot-cgroup")
    capsule, receipt = CgroupDelegationManager(parent, sensorium=sensorium, synthetic=True).prepare(
        "mission-delegated",
        ("memory", "pids"),
        CgroupAuthorization(
            action="delegate", mission_id="mission-delegated", approved_by="operator",
            approval_receipt_id="approval:delegate", reason="bounded replay",
        ),
    )
    assert capsule is None
    assert receipt.reason == "populated_parent_blocks_domain_controller_enablement"
    assert (parent / "cgroup.subtree_control").read_text(encoding="utf-8") == ""
    assert sensorium.sequencer.latest(1)[0].event.event_type == "isolation.cgroup_reduced"


def test_empty_delegated_parent_enables_controllers_and_creates_capsule(tmp_path):
    parent = tmp_path / "delegated"
    parent.mkdir()
    (parent / "cgroup.controllers").write_text("cpu memory pids io\n", encoding="utf-8")
    (parent / "cgroup.subtree_control").write_text("", encoding="utf-8")
    (parent / "cgroup.procs").write_text("", encoding="utf-8")
    capsule, receipt = CgroupDelegationManager(parent, synthetic=True).prepare(
        "mission-delegated",
        ("cpu", "memory", "pids", "io"),
        CgroupAuthorization(
            action="delegate", mission_id="mission-delegated", approved_by="operator",
            approval_receipt_id="approval:delegate", reason="bounded replay",
        ),
    )
    assert capsule is not None and capsule.path.is_dir()
    assert receipt.full_controller_delegation is True


def test_exact_owned_anchor_is_evacuated_before_controller_enablement(tmp_path):
    from app.kernel.sensorium.contracts import ProcessLease
    from datetime import datetime, timezone

    parent = tmp_path / "delegated"
    parent.mkdir()
    (parent / "cgroup.controllers").write_text("cpu memory pids\n", encoding="utf-8")
    (parent / "cgroup.subtree_control").write_text("", encoding="utf-8")
    (parent / "cgroup.procs").write_text("4321\n", encoding="utf-8")
    lease = ProcessLease(
        boot_id="boot", pid_at_observation=4321, start_time_ticks=10,
        executable_digest="sha256:" + "1" * 64, cgroup_id="/delegated",
        pid_namespace_inode=1, mount_namespace_inode=2,
        parent_identity_hash="sha256:" + "2" * 64, owner_scope="beast_service",
        acquired_at=datetime.now(timezone.utc).isoformat(),
    ).with_identity()

    class Supervisor:
        def verify(self, lease_id):
            return lease_id == lease.lease_id

    capsule, receipt = CgroupDelegationManager(parent, synthetic=True).prepare_with_owned_anchor(
        "mission-delegated", ("cpu", "memory", "pids"), lease, Supervisor(),
        CgroupAuthorization(
            action="delegate", mission_id="mission-delegated", approved_by="operator",
            approval_receipt_id="approval:delegate", reason="owned transient anchor",
        ),
    )
    assert capsule is not None
    assert receipt.full_controller_delegation is True
    assert (parent / "cgroup.procs").read_text(encoding="utf-8") == ""
    assert (parent / "beast-anchor" / "cgroup.procs").read_text(encoding="utf-8") == "4321\n"
