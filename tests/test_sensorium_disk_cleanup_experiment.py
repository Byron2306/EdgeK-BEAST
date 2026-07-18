from app.kernel.compute.sensorium_disk_cleanup_experiment import SensoriumDiskCleanupExperiment


def test_disk_cleanup_is_learned_and_replay_passes_but_production_fails_closed(tmp_path):
    packet = SensoriumDiskCleanupExperiment(tmp_path).run()
    assert packet["generalization"]["inferred_parameters"] == [
        "approval_receipt_digest", "cleanup_manifest_digest", "workspace_identity"]
    assert packet["replay"]["promotion_eligible"] is True
    assert packet["safety"]["quarantine_before_purge"] is True
    assert packet["production_promotion_allowed"] is False
    assert "delegated cgroup+namespace" in packet["promotion_blocker"]
