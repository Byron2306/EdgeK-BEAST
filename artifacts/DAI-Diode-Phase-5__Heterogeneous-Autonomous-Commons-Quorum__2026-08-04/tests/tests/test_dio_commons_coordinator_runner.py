from scripts.run_dai_phase4_commons_coordinator import run


def test_phase4_commons_coordinator_runner_produces_green_bounded_quorum(tmp_path):
    summary = run(out=tmp_path)

    assert summary["green"] is True
    assert summary["decision"] == "approve"
    assert summary["quorum_class"] == "heterogeneous_distributed_quorum"
    assert summary["admitted_node_count"] == 5
    assert summary["valid_vote_count"] == 5
    assert summary["red_gates"] == ()
    assert summary["adapter_votes_simulated"] is True
    assert summary["provider_calls_used"] == 0
    assert summary["production_authority_allowed"] is False
    assert summary["execution_authority_allowed"] is False
    assert (tmp_path / "dio_phase4_commons_coordinator_run.json").is_file()
