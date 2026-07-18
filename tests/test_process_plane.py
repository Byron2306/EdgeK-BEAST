import os
import signal
import subprocess
import sys
import time
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.execution.cgroup_capsule import (
    CgroupAuthorization,
    CgroupMissionCapsule,
    CgroupV2Discovery,
)
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.process_plane import process_plane_capabilities
from app.kernel.execution.process_supervisor import (
    ProcessLeaseSupervisor,
    ProcessSignalAuthorization,
)
from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.main import app


def authorization(action: str, *, destructive: bool = False) -> CgroupAuthorization:
    return CgroupAuthorization(
        action=action,
        mission_id="mission-test",
        approved_by="test-operator",
        approval_receipt_id=f"approval-{action}",
        reason=f"test {action}",
        destructive=destructive,
    )


@pytest.mark.skipif(not hasattr(os, "pidfd_open"), reason="pidfd unavailable")
def test_process_identity_and_pidfd_exit_are_bound_to_owned_process(tmp_path):
    runtime = SensoriumRuntime(capacity=32, export_root=tmp_path, boot_id="boot-test")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    supervisor = ProcessLeaseSupervisor(sensorium=runtime)
    try:
        lease = supervisor.acquire(child.pid, mission_id="mission-process")
        assert lease.pid_at_observation == child.pid
        assert lease.lease_id.startswith("process:sha256:")
        assert supervisor.verify(lease.lease_id) is True
        state = supervisor.state()
        assert state["integer_pid_signal_used"] is False
        assert state["live_count"] == 1

        auth = ProcessSignalAuthorization(
            lease_id=lease.lease_id,
            signal_number=signal.SIGTERM,
            approved_by="test-operator",
            approval_receipt_id="approval-term",
            reason="finish owned test child",
        )
        receipt = supervisor.send_signal(
            lease.lease_id, signal.SIGTERM, auth, mission_id="mission-process"
        )
        assert receipt["targeted_via"] == "pidfd"
        assert receipt["integer_pid_signal_used"] is False
        child.wait(timeout=5)
        exited = []
        deadline = time.monotonic() + 3
        while not exited and time.monotonic() < deadline:
            exited = supervisor.poll(timeout=0.1)
        assert [item.lease_id for item in exited] == [lease.lease_id]
        assert supervisor.verify(lease.lease_id) is False
        assert {entry.event.event_type for entry in runtime.sequencer.latest(10)} >= {
            "process.lease_acquired", "process.signal_sent", "process.exit"
        }
    finally:
        supervisor.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.skipif(not hasattr(os, "pidfd_open"), reason="pidfd unavailable")
def test_process_signal_authorization_cannot_be_reused_for_another_lease():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    supervisor = ProcessLeaseSupervisor()
    try:
        lease = supervisor.acquire(child.pid)
        auth = ProcessSignalAuthorization(
            lease_id="process:sha256:" + "0" * 64,
            signal_number=signal.SIGTERM,
            approved_by="operator",
            approval_receipt_id="wrong-lease",
            reason="must fail",
        )
        with pytest.raises(PermissionError, match="lease mismatch"):
            supervisor.send_signal(lease.lease_id, signal.SIGTERM, auth)
        assert child.poll() is None
    finally:
        supervisor.close()
        child.terminate()
        child.wait(timeout=5)


def test_process_lease_tampering_fails_current_identity_check():
    collector = LinuxProcessIdentityCollector()
    lease = collector.collect(os.getpid(), owner_scope="beast_test")

    assert collector.still_matches(lease) is True
    assert collector.still_matches(replace(lease, start_time_ticks=lease.start_time_ticks + 1)) is False


def test_cgroup_discovery_is_read_only(tmp_path):
    (tmp_path / "cgroup.controllers").write_text("cpu memory io\n", encoding="utf-8")
    before = sorted(path.name for path in tmp_path.iterdir())
    state = CgroupV2Discovery(tmp_path).state()
    after = sorted(path.name for path in tmp_path.iterdir())

    assert state["available"] is True
    assert state["controllers"] == ["cpu", "io", "memory"]
    assert state["inspection_mutates_state"] is False
    assert before == after


def test_cgroup_capsule_requires_scoped_authority_and_destructive_approval(tmp_path):
    runtime = SensoriumRuntime(capacity=32, export_root=tmp_path / "outbox", boot_id="boot-test")
    capsule = CgroupMissionCapsule(
        tmp_path / "cgroup", "mission-test", sensorium=runtime, synthetic=True
    )
    with pytest.raises(PermissionError):
        capsule.create(authorization("attach"))
    capsule.create(authorization("create"))
    (capsule.path / "cgroup.procs").write_text("", encoding="utf-8")
    (capsule.path / "cgroup.events").write_text("populated 0\nfrozen 0\n", encoding="utf-8")
    (capsule.path / "cgroup.freeze").write_text("0\n", encoding="utf-8")
    (capsule.path / "cgroup.kill").write_text("", encoding="utf-8")
    (capsule.path / "cpu.pressure").write_text("some avg10=0.00 total=0\n", encoding="utf-8")

    lease = LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="beast_test")

    class StableSupervisor:
        @staticmethod
        def verify(lease_id):
            return lease_id == lease.lease_id

    attach = capsule.attach_process(lease, StableSupervisor(), authorization("attach"))
    assert attach["confirmed"] is True
    assert attach["details"]["identity_verified_after_write"] is True
    assert (capsule.path / "cgroup.procs").read_text(encoding="utf-8") == f"{os.getpid()}\n"
    freeze = capsule.freeze(True, authorization("freeze"))
    assert freeze["confirmed"] is False
    assert (capsule.path / "cgroup.freeze").read_text(encoding="utf-8") == "1\n"

    with pytest.raises(PermissionError, match="destructive"):
        capsule.kill(authorization("kill", destructive=False))
    kill = capsule.kill(authorization("kill", destructive=True))
    assert kill["details"]["confirmation_requires_populated_zero"] is True
    assert (capsule.path / "cgroup.kill").read_text(encoding="utf-8") == "1\n"
    assert capsule.empty() is True
    assert capsule.pressure()["cpu"].startswith("some")
    (capsule.path / "cgroup.procs").write_text(f"{os.getpid()}\n4321\n", encoding="utf-8")
    orphan = capsule.orphan_state([os.getpid()])
    assert orphan["unexpected_members"] == [4321]
    assert orphan["orphaned"] is True
    (capsule.path / "cgroup.procs").write_text("", encoding="utf-8")
    cleanup = capsule.cleanup(authorization("cleanup"))
    assert cleanup["confirmed"] is True
    assert not capsule.path.exists()
    assert {entry.event.event_type for entry in runtime.sequencer.latest(20)} >= {
        "cgroup.create", "cgroup.attach", "cgroup.freeze", "cgroup.kill", "cgroup.cleanup"
    }


def test_cgroup_attach_fails_closed_when_lease_changes_during_write(tmp_path):
    capsule = CgroupMissionCapsule(tmp_path, "mission-test", synthetic=True)
    capsule.create(authorization("create"))
    (capsule.path / "cgroup.procs").write_text("", encoding="utf-8")
    lease = LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="beast_test")

    class DriftingSupervisor:
        calls = 0

        def verify(self, lease_id):
            self.calls += 1
            return self.calls == 1 and lease_id == lease.lease_id

    with pytest.raises(ProcessLookupError, match="changed during cgroup attachment"):
        capsule.attach_process(lease, DriftingSupervisor(), authorization("attach"))


def test_cgroup_cleanup_is_graceful_first_and_does_not_escalate_when_empty(tmp_path):
    capsule = CgroupMissionCapsule(tmp_path, "mission-test", synthetic=True)
    capsule.create(authorization("create"))
    (capsule.path / "cgroup.procs").write_text("5555\n", encoding="utf-8")
    (capsule.path / "cgroup.events").write_text("populated 1\nfrozen 0\n", encoding="utf-8")
    (capsule.path / "cgroup.kill").write_text("", encoding="utf-8")

    class FakeSupervisor:
        def send_signal(self, lease_id, signal_number, selected_authorization, mission_id):
            assert signal_number == signal.SIGTERM
            (capsule.path / "cgroup.procs").write_text("", encoding="utf-8")
            (capsule.path / "cgroup.events").write_text("populated 0\nfrozen 0\n", encoding="utf-8")
            return {"lease_id": lease_id, "targeted_via": "pidfd"}

        def poll(self, timeout=0):
            return []

    lease_id = "process:sha256:" + "1" * 64
    process_auth = ProcessSignalAuthorization(
        lease_id=lease_id,
        signal_number=signal.SIGTERM,
        approved_by="operator",
        approval_receipt_id="approval-term",
        reason="graceful cleanup",
    )
    receipt = capsule.graceful_cleanup(
        FakeSupervisor(),
        [lease_id],
        {lease_id: process_auth},
        timeout_seconds=0.2,
        kill_authorization=authorization("kill", destructive=True),
    )

    assert receipt["empty_after_graceful_wait"] is True
    assert receipt["escalated_to_cgroup_kill"] is False
    assert (capsule.path / "cgroup.kill").read_text(encoding="utf-8") == ""


def test_process_plane_capability_projection_has_no_actuator(tmp_path):
    (tmp_path / "cgroup.controllers").write_text("cpu memory\n", encoding="utf-8")
    state = process_plane_capabilities(tmp_path)

    assert state["authority"] == "read_only"
    assert state["actuator_available"] is False
    assert state["platform"]["pidfd_open"] is hasattr(os, "pidfd_open")


@pytest.mark.asyncio
async def test_process_plane_http_capabilities_are_read_only():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/edgek/process-plane/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "beast_process_plane_capabilities"
    assert payload["authority"] == "read_only"
    assert payload["actuator_available"] is False


def test_process_plane_s2_objects_are_registered_with_canon(tmp_path):
    (tmp_path / "cgroup.controllers").write_text("cpu memory\n", encoding="utf-8")
    canon = CanonRegistry()
    capability = process_plane_capabilities(tmp_path)
    orphan = {
        "beast_object_type": "cgroup_capsule_orphan_state",
        "version": "1.0",
        "mission_id": "mission-test",
        "members": [],
        "expected": [],
        "unexpected_members": [],
        "missing_expected_members": [],
        "orphaned": False,
        "populated": 0,
        "read_only": True,
    }

    assert canon.validate_object(capability)["valid"] is True
    assert canon.validate_object(orphan)["valid"] is True
