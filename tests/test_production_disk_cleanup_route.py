import json
from pathlib import Path

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.disk_pressure_cleanup import execute_cleanup
from app.kernel.compute.sensorium_disk_cleanup_experiment import SensoriumDiskCleanupExperiment
from app.kernel.sensorium.contracts_hash import content_hash


def test_promoted_disk_cleanup_uses_isolated_delegate_not_interpreter(tmp_path: Path):
    experiment = SensoriumDiskCleanupExperiment(tmp_path / "experiment")
    packet = experiment.run()
    delegated = []

    def delegate(**values):
        effect = execute_cleanup(values["workspace"], values["manifest"],
                                 approval_receipt=values["approval_receipt"])
        body = {
            "mission_id": values["mission_id"],
            "manifest_digest": values["manifest"].manifest_digest,
            "cgroup_path": "/sys/fs/cgroup/test-production-capsule",
            "worker_digest": "sha256:" + "1" * 64,
            "launch_receipt_digest": "sha256:" + "2" * 64,
            "files_removed": effect["files_removed"], "bytes_removed": effect["bytes_removed"],
            "targets_absent": effect["all_targets_absent"], "clone3_into_cgroup": True,
            "namespace_isolation": True, "filesystem_secret_isolation": True,
            "ambient_network_denied": True, "root_cleanup_confirmed": True, "verified": True,
        }
        delegated.append(body)
        return {**body, "receipt_digest": content_hash(body)}

    plane = ComputePlane(root=tmp_path / "state", isolated_disk_cleanup_delegate=delegate)
    crystal = plane._deserialize_crystal(packet["crystal"])
    replay = plane.submit_replay(crystal, [
        experiment._variant("route-alpha", b"a" * 31),
        experiment._variant("route-beta", b"b" * 37),
        experiment._variant("route-gamma", b"c" * 41),
        experiment._variant("route-negative", b"x", negative=True),
    ])
    plane.admit_promoted_crystal(crystal, replay, scientific_evidence={
        "heldout_ablation": {"receipt_id": replay.evidence_root + ":ablation", "verified": True, "held_out": True},
        "displacement": {"receipt_id": replay.evidence_root + ":displacement", "verified": True, "provider_calls_avoided": 1},
    }, policy_generation="policy:disk-production:v1", approver="arda-disk-operator",
        approval_receipt="approval:disk-production:v1")

    workspace = tmp_path / "user-workspace"; (workspace / "cache").mkdir(parents=True)
    (workspace / "cleanup-policy.json").write_text(json.dumps({
        "version": "beast.disk-cleanup.v1", "cache_roots": ["cache"], "min_age_seconds": 0,
        "max_files": 4, "max_bytes": 4096, "approval_threshold_bytes": 2048,
    }))
    (workspace / "cache" / "stale.bin").write_bytes(b"stale" * 20)
    # Removal of the in-process actuator proves this route cannot accidentally use it.
    plane.physical_interpreter.handlers.handlers.pop("disk.quarantine_and_purge")
    receipt = plane.execute_user_mission({
        "mission_id": "mission:disk-production-1",
        "task_family": "disk_pressure_diagnosis_and_governed_cleanup",
        "workspace_root": str(workspace), "approval_receipt": "approval:disk-standard:production-1",
    }, interface="cli")
    assert receipt.final_status == "verified_local_recurrence"
    assert receipt.provider_call_witness["during_execution"] == 0
    assert delegated and not (workspace / "cache" / "stale.bin").exists()
    node = plane.evidence_graph.query("production_isolated_disk_cleanup")[-1]
    assert node.receipt["applicability_proof_digest"] == receipt.applicability_proof_digest
    assert node.receipt["authorization_receipt_digest"] == receipt.authorization_receipt_digest
