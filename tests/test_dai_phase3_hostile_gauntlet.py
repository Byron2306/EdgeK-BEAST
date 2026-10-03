from scripts.run_dai_phase3_hostile_gauntlet import run


def test_phase3_hostile_gauntlet_blocks_every_declared_attack(tmp_path):
    from tests.test_dai_phase3_composition import EVIDENCE

    receipt = run(root=EVIDENCE)

    assert receipt["green"] is True
    assert receipt["case_count"] == 10
    assert receipt["blocked_count"] == 10
    assert receipt["case_results"]["extra_text_claim_rejected"] is True
    assert receipt["case_results"]["extra_visual_claim_rejected"] is True
    assert receipt["case_results"]["semantic_digest_marker_tamper_rejected"] is True
    assert all(receipt["case_results"].values())
    assert receipt["provider_calls_used"] == 0
    assert receipt["production_authority_allowed"] is False
