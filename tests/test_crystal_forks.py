from app.kernel.crystal_forks import TemporalCrystalForkManager


def test_temporal_fork_channels_bound_traffic_and_persist(tmp_path):
    path = tmp_path / "forks.json"
    manager = TemporalCrystalForkManager(path)
    stable = manager.create_fork("cap:stable", "code", channel="stable", traffic_share=1.0, confidence=0.95)
    candidate = manager.create_fork("cap:candidate", "code", channel="candidate", traffic_share=0.9, confidence=0.7)
    experimental = manager.create_fork("cap:exp", "code", channel="experimental", traffic_share=0.9, confidence=0.5)

    assert stable.traffic_share == 1.0
    assert candidate.traffic_share == 0.25
    assert experimental.traffic_share == 0.05
    assert TemporalCrystalForkManager(path).state()["channels"]["experimental"] == 1


def test_experimental_failure_rolls_back_without_touching_stable(tmp_path):
    manager = TemporalCrystalForkManager(tmp_path / "forks.json")
    stable = manager.create_fork("cap:stable", "code", channel="stable", traffic_share=1.0, confidence=0.95)
    exp = manager.create_fork("cap:exp", "code", channel="experimental", traffic_share=0.05, confidence=0.4)

    rolled = manager.record_outcome(exp.fork_id, clean_completion=False, rollback_success=True, friction_score=0.8)
    stable_after = next(item for item in manager.state()["forks"] if item["fork_id"] == stable.fork_id)

    assert rolled.state == "rolled_back"
    assert rolled.traffic_share == 0.0
    assert stable_after["channel"] == "stable"
    assert stable_after["traffic_share"] == 1.0


def test_candidate_promotes_only_with_clean_friction_cost_and_rollback_evidence(tmp_path):
    manager = TemporalCrystalForkManager(tmp_path / "forks.json")
    candidate = manager.create_fork("cap:candidate", "code", channel="candidate", traffic_share=0.25)
    for _ in range(3):
        candidate = manager.record_outcome(
            candidate.fork_id,
            clean_completion=True,
            rollback_success=True,
            friction_score=0.05,
            cost_usd=0.001,
        )

    eligible, reason, details = manager.promotion_eligibility(candidate.fork_id)
    promoted = manager.promote(candidate.fork_id, approved_by="test")

    assert eligible is True
    assert reason == "eligible_for_stable_promotion"
    assert details["rollback_successes"] == 3
    assert promoted.channel == "stable"
    assert promoted.traffic_share == 1.0


def test_annealing_merges_duplicates_splits_multimodal_and_retires_stale(tmp_path):
    manager = TemporalCrystalForkManager(tmp_path / "forks.json")
    duplicate_a = manager.create_fork("cap:dup", "code", channel="candidate", confidence=0.8)
    duplicate_b = manager.create_fork("cap:dup", "code", channel="candidate", confidence=0.7)
    multimodal = manager.create_fork("cap:multi", "code", channel="candidate", confidence=0.8)
    stale = manager.create_fork("cap:stale", "code", channel="candidate", confidence=0.2)
    for _ in range(2):
        manager.record_outcome(multimodal.fork_id, clean_completion=True, friction_score=0.1)
        manager.record_outcome(multimodal.fork_id, clean_completion=False, friction_score=0.9)
    for _ in range(3):
        manager.record_outcome(stale.fork_id, clean_completion=False, friction_score=0.9)

    report = manager.anneal()
    state = manager.state()
    by_id = {item["fork_id"]: item for item in state["forks"]}

    assert report["merged_duplicates"] >= 1
    assert by_id[duplicate_b.fork_id]["state"] == "merged"
    assert report["split_multimodal"] >= 1
    assert report["retired_stale"] >= 1
    assert by_id[stale.fork_id]["state"] == "retired"
    assert by_id[duplicate_a.fork_id]["state"] == "active"
