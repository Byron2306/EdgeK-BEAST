from dataclasses import replace

import pytest

from app.kernel.execution.mission_isolation_proof import MissionIsolationProof
from app.kernel.execution.race_free_cgroup_launcher import NativeCgroupLauncherCompiler, RaceFreeCgroupLauncher


def complete_proof():
    return MissionIsolationProof(
        mission_id="heldout-1", cgroup_path="/sys/fs/cgroup/heldout-1",
        limits_requested={"cpu.max": "50000 100000"},
        limits_observed={"cpu.max": "50000 100000"},
        controllers=("cpu", "memory", "pids", "io"),
        pressure={"cpu": "some", "memory": "some", "io": "some"},
        resource_stats={"cpu.stat": {"usage_usec": 1}, "memory.events": {"oom_kill": 1}},
        initial_events={"populated": 0}, final_events={"populated": 0},
        namespace_receipt_digest="sha256:namespaces", freeze_observed=True,
        clone3_supported=True, placement_boundary="clone3_into_cgroup",
        fault_receipts={name: {"receipt_digest": f"sha256:{name}"} for name in ("timeout", "oom", "bus_peer_death", "rollback", "descendant")},
        descendant_containment=True, descriptor_cleanup=True, timeout_observed=True,
        oom_observed=True, bus_peer_death_observed=True, rollback_observed=True,
        populated_zero_observed=True, no_orphans=True, cleanup_confirmed=True,
        full_isolation_proven=True,
    ).sealed()


def test_complete_mission_isolation_proof_is_tamper_evident():
    proof = complete_proof()
    proof.validate()
    with pytest.raises(ValueError, match="tampered"):
        replace(proof, no_orphans=False).validate()


def test_complete_claim_rejects_missing_io_or_fault_evidence():
    proof = complete_proof()
    with pytest.raises(ValueError, match="missing physical evidence"):
        replace(proof, controllers=("cpu", "memory", "pids"), receipt_digest="").sealed().validate()


def test_clone3_fallback_is_explicit_and_refuses_destructive_execution():
    fallback = RaceFreeCgroupLauncher.refused_fallback("heldout-1", "clone3 returned ENOSYS")
    fallback.validate()
    assert fallback.destructive_execution_allowed is False
    assert fallback.fallback_method == "stopped_child_then_cgroup_procs"


def test_reviewed_fault_workers_compile(tmp_path):
    compiler = NativeCgroupLauncherCompiler()
    for mode in range(1, 6):
        assert compiler.compile_fault_worker(tmp_path / f"worker-{mode}", mode).is_file()
