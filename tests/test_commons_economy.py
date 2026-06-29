from pathlib import Path

import pytest

from app.kernel.networking.commons_economy import ComputeReductionEconomy
from app.kernel.networking.commons_prototype import CommonsCrystalPromoter, FirstPrototypeRunner
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.networking.commons_spaces import package_tiny_llama_case


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"
SPACE_ID = "tiny_llama_opus_gateway_repair"


def test_proof_requires_reproduction_and_excludes_counterfactual_tokens(tmp_path):
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    package_tiny_llama_case(SOURCE, registry.root / SPACE_ID)
    economy = ComputeReductionEconomy(registry)

    proof = economy.proof(SPACE_ID)

    assert proof["eligible"] is False
    assert proof["components"]["observed_tokens_credited"] == 0
    assert proof["anti_gaming"]["local_live_reproduction_required"] is False
    assert economy.simulate(SPACE_ID)["total_simulated_units"] == 0


def test_first_prototype_promotes_advisory_crystal_and_issues_one_credit(tmp_path):
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    packaged = package_tiny_llama_case(SOURCE, registry.root / SPACE_ID)
    economy = ComputeReductionEconomy(registry)
    promoter = CommonsCrystalPromoter(registry, economy, tmp_path / "crystals")
    runner = FirstPrototypeRunner(registry, economy, promoter)

    result = runner.complete(
        space_id=SPACE_ID,
        target=SOURCE / "case_repo",
        approved=True,
        approved_by="pytest",
        reason="verified local prototype",
    )
    duplicate = economy.issue_credit(
        SPACE_ID,
        approved=True,
        approved_by="pytest",
        reason="same evidence must not mint again",
    )
    crystal = promoter.state()["crystals"][0]

    assert packaged["manifest"]["artifact_count"] == 9
    assert result["completed"] is True
    assert result["checklist"]["live_reproductions"] == 3
    assert crystal["approved_for_enforcement"] is False
    assert duplicate["duplicate_issuance"] is True
    assert economy.state()["credit_count"] == 1
    assert economy.state()["credits"][0]["financial_value"] is None


def test_credit_and_promotion_require_explicit_approval(tmp_path):
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    package_tiny_llama_case(SOURCE, registry.root / SPACE_ID)
    economy = ComputeReductionEconomy(registry)
    promoter = CommonsCrystalPromoter(registry, economy, tmp_path / "crystals")

    with pytest.raises(ValueError, match="explicit approval"):
        economy.issue_credit(SPACE_ID, approved=False, approved_by="pytest", reason="denied")
    with pytest.raises(ValueError, match="explicit approval"):
        promoter.promote(SPACE_ID, approved=False, approved_by="pytest", reason="denied")
