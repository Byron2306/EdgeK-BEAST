from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.compute.distributed_forge_scheduler import DistributedForgeScheduler
from app.kernel.compute.forge_isolation import ForgeIsolationAttestation, forge_work_isolation_admitted


def _attestation(node_id="forge-a", controllers=("cpu", "memory", "pids")):
    return ForgeIsolationAttestation(
        node_id=node_id,
        worker_digest="sha256:worker",
        launch_receipt_digest="sha256:launch",
        delegation_receipt_digest="sha256:delegation",
        race_free_cgroup_birth=True,
        namespace_isolation=True,
        filesystem_secret_isolation=True,
        cleanup_confirmed=True,
        enabled_controllers=controllers,
        missing_controllers=tuple(sorted({"cpu", "memory", "pids", "io"} - set(controllers))),
        authority_mode="isolated_execute",
    ).sealed()


def test_compute_forge_profile_carries_validated_isolation_attestation(tmp_path):
    node = ComputeForgeNode("forge-a")
    value = node.bind_isolation_attestation(_attestation())
    assert value["authority_mode"] == "isolated_execute"
    assert value["missing_controllers"] == ("io",)
    assert node.profile.to_dict()["isolation_attestation"]["attestation_digest"]


def test_scheduler_withholds_isolated_work_without_attestation(tmp_path):
    scheduler = DistributedForgeScheduler(tmp_path / "scheduler")
    scheduler.register_node("plain", ["verify_deterministic"])
    scheduler.submit_work(
        "verify_deterministic", ".", metadata={"requires_isolation": True, "required_controllers": ["memory", "pids"]}
    )
    assert scheduler.assign_work("plain") == []
    assert scheduler.get_system_status()["work"]["queued"] == 1


def test_scheduler_admits_supported_controllers_and_rejects_missing_io(tmp_path):
    scheduler = DistributedForgeScheduler(tmp_path / "scheduler")
    attestation = _attestation().to_dict()
    scheduler.register_node("forge-a", ["verify_deterministic"], isolation_attestation=attestation)
    admitted = scheduler.submit_work(
        "verify_deterministic", ".", priority=1,
        metadata={"requires_isolation": True, "required_controllers": ["memory", "pids"]},
    )
    blocked = scheduler.submit_work(
        "verify_deterministic", ".", priority=2,
        metadata={"requires_isolation": True, "required_controllers": ["io"]},
    )
    assigned = scheduler.assign_work("forge-a", max_items=2)
    assert [item.work_item.work_id for item in assigned] == [admitted.work_id]
    assert scheduler.work_queue[0].work_id == blocked.work_id
    assert forge_work_isolation_admitted(blocked.metadata, attestation) is False
