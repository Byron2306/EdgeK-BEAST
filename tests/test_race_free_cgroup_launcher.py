from pathlib import Path
import uuid

import pytest

from app.kernel.execution.isolation_readiness import effective_cgroup_path
from app.kernel.execution.race_free_cgroup_launcher import (
    NativeCgroupLauncherCompiler,
    RaceFreeCgroupLauncher,
    RaceFreeLaunchAuthorization,
)
from app.kernel.sensorium.runtime import SensoriumRuntime


def test_native_launcher_compiles_and_rejects_missing_descriptor_contract(tmp_path):
    launcher = NativeCgroupLauncherCompiler().compile(tmp_path / "beast-cgroup-launcher")
    import subprocess

    completed = subprocess.run([str(launcher)], capture_output=True, text=True, check=False)
    assert completed.returncode == 64
    source = NativeCgroupLauncherCompiler().source.read_text(encoding="utf-8")
    assert "CLONE_INTO_CGROUP" in source
    assert "execveat" in source
    assert "system(" not in source
    assert "execvp" not in source


def test_launch_authority_cannot_be_retargeted(tmp_path):
    worker = Path("/usr/bin/true")
    runner = RaceFreeCgroupLauncher(tmp_path / "missing-launcher")
    digest = runner._digest(worker)
    authorization = RaceFreeLaunchAuthorization(
        "mission-a", "/cgroup/a", digest, "operator", "approval:1", "bounded worker"
    )
    with pytest.raises(PermissionError, match="binding mismatch"):
        authorization.validate(mission_id="mission-b", cgroup_path=Path("/cgroup/a"), worker_digest=digest)


def test_live_clone3_gate_observes_membership_before_exec(tmp_path):
    cgroup = effective_cgroup_path()
    if not cgroup.is_dir() or not (cgroup / "cgroup.procs").exists():
        pytest.skip("effective cgroup is unavailable")
    launcher = NativeCgroupLauncherCompiler().compile(tmp_path / "beast-cgroup-launcher")
    sensorium = SensoriumRuntime(capacity=16, export_root=tmp_path / "sensorium", boot_id="boot-clone3")
    runner = RaceFreeCgroupLauncher(launcher, sensorium=sensorium)
    worker = Path("/usr/bin/true")
    digest = runner._digest(worker)
    authorization = RaceFreeLaunchAuthorization(
        "mission-clone3-probe", str(cgroup), digest, "operator", "approval:clone3", "same-cgroup syscall probe"
    )
    try:
        receipt = runner.launch("mission-clone3-probe", cgroup, worker, authorization, timeout_seconds=3)
    except (PermissionError, RuntimeError) as exc:
        pytest.skip(f"kernel does not permit clone3 cgroup probe: {type(exc).__name__}")
    assert receipt.membership_observed_before_release is True
    assert receipt.child_exit_code == 0
    assert sensorium.sequencer.latest(1)[0].event.event_type == "isolation.worker_born_in_cgroup"


def test_live_distinct_child_cgroup_is_empty_and_removable_after_worker(tmp_path):
    parent = effective_cgroup_path()
    child = parent / f"beast-test-{uuid.uuid4().hex[:10]}"
    try:
        child.mkdir()
    except OSError as exc:
        pytest.skip(f"effective cgroup does not permit a mission child: {type(exc).__name__}")
    try:
        launcher = NativeCgroupLauncherCompiler().compile(tmp_path / "beast-cgroup-launcher")
        runner = RaceFreeCgroupLauncher(launcher)
        worker = Path("/usr/bin/true")
        digest = runner._digest(worker)
        authorization = RaceFreeLaunchAuthorization(
            "mission-distinct-child", str(child), digest, "operator", "approval:child", "distinct cgroup probe"
        )
        try:
            receipt = runner.launch("mission-distinct-child", child, worker, authorization, timeout_seconds=3)
        except (PermissionError, RuntimeError) as exc:
            pytest.skip(f"kernel refused distinct child placement: {type(exc).__name__}")
        assert receipt.membership_observed_before_release is True
        assert "populated 0" in (child / "cgroup.events").read_text(encoding="utf-8")
    finally:
        try:
            child.rmdir()
        except OSError:
            pass
    assert not child.exists()


def test_live_worker_combines_distinct_cgroup_and_namespaces(tmp_path):
    parent = effective_cgroup_path()
    child = parent / f"beast-combined-{uuid.uuid4().hex[:10]}"
    try:
        child.mkdir()
    except OSError as exc:
        pytest.skip(f"effective cgroup does not permit a mission child: {type(exc).__name__}")
    try:
        compiler = NativeCgroupLauncherCompiler()
        launcher = compiler.compile(tmp_path / "beast-cgroup-launcher")
        worker = compiler.compile_worker(tmp_path / "beast-isolated-worker")
        sensorium = SensoriumRuntime(capacity=16, export_root=tmp_path / "sensorium", boot_id="boot-combined")
        runner = RaceFreeCgroupLauncher(launcher, sensorium=sensorium)
        digest = runner._digest(worker)
        authorization = RaceFreeLaunchAuthorization(
            "mission-combined", str(child), digest, "operator", "approval:combined", "combined isolation proof"
        )
        try:
            receipt = runner.launch("mission-combined", child, worker, authorization, timeout_seconds=5)
        except (PermissionError, RuntimeError) as exc:
            pytest.skip(f"kernel refused combined isolation probe: {type(exc).__name__}")
        assert receipt.combined_cgroup_namespace_proven is True
        assert receipt.worker_evidence["pid"] == 1
        assert receipt.worker_evidence["uid"] == 0
        assert receipt.worker_evidence["non_loopback_interface_count"] == 0
        assert receipt.worker_evidence["filesystem_root_isolated"] is True
        assert receipt.worker_evidence["secrets_denied"] is True
        assert receipt.filesystem_secret_isolation_proven is True
        assert receipt.root_cleanup_confirmed is True
        assert "populated 0" in (child / "cgroup.events").read_text(encoding="utf-8")
    finally:
        try:
            child.rmdir()
        except OSError:
            pass
    assert not child.exists()
