from app.kernel.agents.phase12_gauntlet import REQUIRED_CASES, evaluate_agent_gauntlet


def good_case(case_id):
    value = {
        "case_id": case_id,
        "completed": True,
        "exact_source_grounded": True,
        "governed_mutation": True,
        "fresh_verification": True,
        "event_chain_valid": True,
        "unsupported_completion": False,
        "evidence": {"receipt": "sha256:test"},
    }
    if case_id == "repair":
        value.update(repair_observed=True, repair_bounded=True)
    if case_id == "remote_target":
        value.update(target_evidence_preserved=True, same_authority_model=True)
    if case_id == "cross_file_reasoning":
        value["relevant_files_used"] = 3
    if case_id == "large_repo_navigation":
        value.update(repository_discovery_used=True, manual_attachment_dependency=False)
    return value


def test_phase12_promotes_only_complete_integrated_gauntlet():
    result = evaluate_agent_gauntlet([good_case(case_id) for case_id in REQUIRED_CASES])
    assert result["promotion_decision"] == "PROMOTE"
    assert result["passed_cases"] == 5
    assert result["baseline"]["performance_claimed"] is False
    assert result["grants_promotion_authority"] is False


def test_phase12_refuses_missing_case():
    result = evaluate_agent_gauntlet([good_case(case_id) for case_id in REQUIRED_CASES[:-1]])
    assert result["promotion_decision"] == "REFUSE"


def test_phase12_refuses_stale_verification():
    cases = [good_case(case_id) for case_id in REQUIRED_CASES]
    cases[0]["fresh_verification"] = False
    result = evaluate_agent_gauntlet(cases)
    assert result["promotion_decision"] == "REFUSE"
    simple = next(item for item in result["results"] if item["case_id"] == "simple_mutation")
    assert simple["checks"]["fresh_verification"] is False


def test_phase12_refuses_unbounded_repair():
    cases = [good_case(case_id) for case_id in REQUIRED_CASES]
    repair = next(case for case in cases if case["case_id"] == "repair")
    repair["repair_bounded"] = False
    assert evaluate_agent_gauntlet(cases)["promotion_decision"] == "REFUSE"


def test_phase12_refuses_remote_authority_downgrade():
    cases = [good_case(case_id) for case_id in REQUIRED_CASES]
    remote = next(case for case in cases if case["case_id"] == "remote_target")
    remote["same_authority_model"] = False
    assert evaluate_agent_gauntlet(cases)["promotion_decision"] == "REFUSE"
