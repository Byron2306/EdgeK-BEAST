from types import SimpleNamespace

from app.kernel.agents.repair_learning_runtime import learning_episode, repair_projection


def test_environment_failure_retries_without_code_mutation():
    packet = repair_projection(
        {"error": "Connection refused while running verifier", "result": {"returncode": 1}},
        repair_cycle=1,
        max_repair_cycles=3,
    )
    assert packet["failure_analysis"]["failure_class"] == "environment_issue"
    assert packet["next_mode"] == "retry_verification"
    assert packet["requires_exact_source_before_mutation"] is False
    assert packet["mutation_authority"] == "none"


def test_logic_failure_requires_bounded_source_grounded_repair():
    packet = repair_projection(
        {"result": {"stderr": "AssertionError: expected 2 actual 3", "returncode": 1}},
        repair_cycle=1,
        max_repair_cycles=3,
    )
    assert packet["failure_analysis"]["failure_class"] == "logic_regression"
    assert packet["next_mode"] == "bounded_code_repair"
    assert packet["requires_exact_source_before_mutation"] is True
    assert packet["requires_fresh_verification_after_mutation"] is True


def test_learning_episode_never_authorizes_mutation_or_promotion():
    episode = learning_episode(
        run={"run_id": "r9"},
        state=SimpleNamespace(run_id="r9"),
        observation={"tool_id": "worktree.verify", "evidence_digest": "proof", "result": {"returncode": 0}},
        passed=True,
    )
    assert episode["episode_status"] == "verified"
    assert episode["promotion_authorized"] is False
    assert episode["authority"] == "learning_evidence_never_mutation_authority"
