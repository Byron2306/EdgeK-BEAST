import json
from datetime import datetime, timedelta, timezone

from app.kernel.compute.distributed_forge_scheduler import DistributedForgeScheduler


def test_scheduler_reconstructs_queue_nodes_and_claims_after_restart(tmp_path):
    root = tmp_path / "scheduler"
    scheduler = DistributedForgeScheduler(root, lease_seconds=60)
    scheduler.register_node("node-a", ["fingerprint"])
    scheduler.submit_work("fingerprint", "/repo", priority=1)
    assigned = scheduler.assign_work("node-a", 1)[0]
    assert scheduler.claim_work(assigned.schedule_id, "node-a") is True

    restored = DistributedForgeScheduler(root, lease_seconds=60)

    assert restored.nodes["node-a"].current_load == 1
    assert restored.scheduled_work[assigned.schedule_id].status == "running"
    assert restored.get_pending_work_for_node("node-a")[0]["schedule_id"] == assigned.schedule_id
    assert json.loads((root / "scheduler_state.json").read_text())["version"] == "2.0"
    assert not list(root.glob(".*.tmp"))


def test_expired_claim_is_requeued_once_and_can_be_reassigned(tmp_path):
    root = tmp_path / "scheduler"
    scheduler = DistributedForgeScheduler(root, lease_seconds=60)
    scheduler.register_node("node-a", ["fingerprint"])
    scheduler.submit_work("fingerprint", "/repo")
    assigned = scheduler.assign_work("node-a", 1)[0]
    assigned.lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    scheduler._persist_state()

    restored = DistributedForgeScheduler(root, lease_seconds=60)

    assert restored.scheduled_work[assigned.schedule_id].status == "expired"
    assert len(restored.work_queue) == 1
    assert restored.nodes["node-a"].current_load == 0
    reassigned = restored.assign_work("node-a", 1)
    assert len(reassigned) == 1
    assert reassigned[0].work_item.work_id == assigned.work_item.work_id


def test_result_reporting_is_idempotent_but_rejects_conflicting_replay(tmp_path):
    scheduler = DistributedForgeScheduler(tmp_path / "scheduler")
    scheduler.register_node("node-a")
    scheduler.submit_work("fingerprint", "/repo")
    assigned = scheduler.assign_work("node-a", 1)[0]
    result = {"fingerprint": "sha256:abc"}

    assert scheduler.report_work_result(assigned.schedule_id, "node-a", True, result) is True
    assert scheduler.report_work_result(assigned.schedule_id, "node-a", True, result) is True
    assert scheduler.report_work_result(assigned.schedule_id, "node-a", True, {"fingerprint": "different"}) is False
    assert scheduler.nodes["node-a"].total_work_completed == 1

    restored = DistributedForgeScheduler(tmp_path / "scheduler")
    assert restored.report_work_result(assigned.schedule_id, "node-a", True, result) is True
    assert restored.nodes["node-a"].total_work_completed == 1


def test_multiple_scheduler_instances_merge_through_locked_snapshot_reload(tmp_path):
    root = tmp_path / "scheduler"
    first = DistributedForgeScheduler(root)
    second = DistributedForgeScheduler(root)

    first.register_node("node-a")
    second.register_node("node-b")
    first.submit_work("fingerprint", "/a")
    second.submit_work("secret_scan", "/b")

    restored = DistributedForgeScheduler(root)
    assert set(restored.nodes) == {"node-a", "node-b"}
    assert {item.repo_path for item in restored.work_queue} == {"/a", "/b"}
