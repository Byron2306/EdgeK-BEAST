"""The cgroup probe must describe the kernel, not the root-cgroup artifact.

``cgroup.kill``, ``cgroup.freeze`` and ``cgroup.events`` do not exist on the
cgroup v2 root.  Probing only the root therefore reports "no actuator" on a
kernel that supports one.  These tests pin the corrected resolution order:
effective cgroup, then root, then a bounded non-root sweep, with the source
of every control reported alongside it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.kernel.execution.cgroup_capsule import (
    CgroupAuthorization,
    CgroupMissionCapsule,
    CgroupV2Discovery,
)


def _write(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "cgroup"
    _write(root / "cgroup.controllers", "cpu memory io pids\n")
    _write(root / "cgroup.procs", "")
    _write(root / "cgroup.subtree_control", "")
    return root


def _child_with_controls(root: Path, name: str = "user.slice") -> Path:
    child = root / name
    for control in ("cgroup.events", "cgroup.freeze", "cgroup.kill", "cgroup.pressure"):
        _write(child / control, "")
    return child


def test_probe_reports_non_root_controls_as_available(tmp_path):
    root = _root(tmp_path)
    child = _child_with_controls(root)
    proc = tmp_path / "self.cgroup"
    _write(proc, "0::/user.slice/session.scope\n")

    state = CgroupV2Discovery(root, proc_self_cgroup=proc).state()

    assert state["controls"] == {"events": True, "freeze": True, "kill": True, "pressure": True}
    assert state["control_sources"]["kill"] == str(child)
    assert state["inspection_mutates_state"] is False


def test_effective_cgroup_controls_are_reported_separately(tmp_path):
    root = _root(tmp_path)
    child = _child_with_controls(root, "user.slice/scoped.scope")
    proc = tmp_path / "self.cgroup"
    _write(proc, "0::/user.slice/scoped.scope\n")

    state = CgroupV2Discovery(root, proc_self_cgroup=proc).state()

    assert state["effective_cgroup"] == str(child)
    assert state["effective_cgroup_exists"] is True
    assert state["effective_controls"]["kill"] is True
    assert state["effective_cgroup_writable"] is True
    assert state["actuation_proven"] is True


def test_root_only_hierarchy_still_reports_no_controls(tmp_path):
    root = _root(tmp_path)
    proc = tmp_path / "self.cgroup"
    _write(proc, "0::/\n")

    state = CgroupV2Discovery(root, proc_self_cgroup=proc).state()

    assert state["controls"] == {"events": False, "freeze": False, "kill": False, "pressure": False}
    assert state["effective_controls"]["kill"] is False
    assert state["actuation_proven"] is False


def test_probe_is_read_only(tmp_path):
    root = _root(tmp_path)
    _child_with_controls(root)
    proc = tmp_path / "self.cgroup"
    _write(proc, "0::/user.slice\n")

    before = sorted(str(path) for path in tmp_path.rglob("*"))
    CgroupV2Discovery(root, proc_self_cgroup=proc).state()
    after = sorted(str(path) for path in tmp_path.rglob("*"))

    assert before == after


def _authorization(action: str, *, destructive: bool = False) -> CgroupAuthorization:
    return CgroupAuthorization(
        action=action,
        mission_id="mission-reclaim",
        approved_by="test-operator",
        approval_receipt_id=f"approval-{action}",
        reason=f"test {action}",
        destructive=destructive,
    )


def _capsule(tmp_path: Path) -> CgroupMissionCapsule:
    capsule = CgroupMissionCapsule(tmp_path / "cgroup", "mission-reclaim", synthetic=True)
    capsule.create(_authorization("create"))
    _write(capsule.path / "cgroup.procs", "")
    _write(capsule.path / "cgroup.events", "populated 0\nfrozen 0\n")
    _write(capsule.path / "memory.current", "1048576\n")
    _write(capsule.path / "memory.reclaim", "")
    return capsule


def test_reclaim_requires_scoped_authority(tmp_path):
    capsule = _capsule(tmp_path)
    with pytest.raises(PermissionError):
        capsule.reclaim_memory(4096, _authorization("cleanup"))


def test_reclaim_is_bounded(tmp_path):
    capsule = _capsule(tmp_path)
    with pytest.raises(ValueError):
        capsule.reclaim_memory(0, _authorization("reclaim"))
    with pytest.raises(ValueError):
        capsule.reclaim_memory(1 << 41, _authorization("reclaim"))


def test_reclaim_emits_a_receipt_with_observed_delta(tmp_path):
    capsule = _capsule(tmp_path)

    receipt = capsule.reclaim_memory(4096, _authorization("reclaim"))

    assert receipt["action"] == "reclaim"
    assert receipt["confirmed"] is True
    details = receipt["details"]
    assert details["kernel_interface"] == "memory.reclaim"
    assert details["requested_bytes"] == 4096
    assert details["memory_current_before"] == 1048576
    assert details["reclaimed_bytes"] == 0  # synthetic file does not reclaim


def test_capsule_state_exposes_reclaim_controls(tmp_path):
    capsule = _capsule(tmp_path)
    state = capsule.state()

    assert state["controls"]["memory.reclaim"] is True
    assert state["controls"]["memory.current"] is True
