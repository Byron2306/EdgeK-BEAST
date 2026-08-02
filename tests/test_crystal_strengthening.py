from app.kernel.compute.crystal_strengthening import VerifiedCrystalStrengthener


def _episode():
    return {
        "task_family": "percentage_arithmetic_repair",
        "failure_signature": "pytest:percentage_discount:subtracts_percent_as_value",
        "symbol_shape": "apply_discount:function",
        "operation_family": "replace_exact",
        "resolved_residual": {"replacement_pattern": "amount * (1 - percent / 100)"},
        "verifier_contract": "pytest suite digest",
        "visible_pass": True,
        "verification_status": "passed",
        "authority": ["worktree_mutation", "worktree_verification"],
    }


def test_verified_episodes_strengthen_without_authorizing_promotion(tmp_path):
    strengthener = VerifiedCrystalStrengthener(tmp_path)
    first = strengthener.strengthen(_episode())
    second = strengthener.strengthen(_episode())
    third = strengthener.strengthen(_episode())
    lookup = strengthener.lookup(_episode())

    assert first["assistance_mode"] == "advisory"
    assert second["assistance_mode"] == "scaffolded"
    assert third["assistance_mode"] == "deterministic_reuse_candidate"
    assert lookup["execution_allowed"] is True
    assert third["promotion_authorized"] is False


def test_failed_episode_does_not_strengthen(tmp_path):
    result = VerifiedCrystalStrengthener(tmp_path).strengthen({"visible_pass": False, "verification_status": "failed"})
    assert result["status"] == "not_strengthened"
