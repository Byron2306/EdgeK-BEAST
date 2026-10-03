from __future__ import annotations

from scripts.run_dai_phase4_commons_gauntlet import run


def test_phase4_commons_gauntlet_blocks_all_mixed_online_offline_attacks(tmp_path):
    receipt = run(out=tmp_path)

    assert receipt["green"] is True
    assert receipt["case_count"] == 11
    assert receipt["blocked_count"] == 11
    assert all(receipt["case_results"].values())
    assert receipt["provider_calls_used"] == 0
    assert receipt["execution_authority_allowed"] is False
    assert receipt["production_authority_allowed"] is False
    assert (tmp_path / "dio_phase4_commons_gauntlet_receipt.json").exists()
