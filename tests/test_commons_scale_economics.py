import json

from app.kernel.networking.commons_scale_economics import CommonsScaleEconomics, ScaleEconomicsAssumptions


class FakeRegistry:
    def list_spaces(self):
        return {
            "spaces": [
                {"space_id": "space_a", "valid": True},
                {"space_id": "space_b", "valid": True},
            ]
        }

    def get(self, space_id):
        return {
            "manifest": {
                "space_id": space_id,
                "manifest_hash": "sha256:abc",
                "artifacts": [
                    {"artifact_type": "orchestration_plan"},
                    {"artifact_type": "promotion_candidate"},
                    {"artifact_type": "verifier_result"},
                    {"artifact_type": "rollback_receipt"},
                ],
                "verifier_bundles": [{"bundle_id": "pytest"}],
                "privacy": {"contains_secrets": False},
            },
            "reduction_receipt": {
                "rollback_available": True,
                "local_seal": {
                    "crypto_profile": {"signature": "ML-DSA-65"},
                },
            },
            "adoptions": [
                {
                    "local_seal": {
                        "crypto_profile": {"signature": "ML-DSA-65"},
                    }
                }
            ],
            "reproductions": [
                {
                    "mode": "live_verifier",
                    "live_verifier_passed": space_id == "space_a",
                    "reproduced": True,
                    "local_seal": {
                        "crypto_profile": {"signature": "ML-DSA-65"},
                    },
                }
            ]
        }

    def registration_candidates(self, limit=500):
        return {
            "candidates": [
                {"source": "compute_forge", "candidate_kind": "fused_inference_crystal"},
                {"source": "compute_forge", "candidate_kind": "meta_tool"},
                {"source": "compute_forge", "candidate_kind": "skill"},
                {"source": "benchmarks/results", "candidate_kind": "benchmark_result_space"},
            ]
        }

    def public_registry(self):
        return {
            "spaces": [
                {
                    "space_id": "space_a",
                    "name": "Space A",
                    "task_class": "verified_reuse",
                    "manifest_hash": "sha256:abc",
                    "reproduction_status": {"successful": 3, "failed": 0},
                    "risk_approval": {"adoption_state": "adopted", "risk": "medium"},
                },
                {
                    "space_id": "space_b",
                    "name": "Space B",
                    "task_class": "unverified_reuse",
                    "manifest_hash": "sha256:def",
                    "reproduction_status": {"successful": 0, "failed": 1},
                    "risk_approval": {"adoption_state": "quarantined_hypothesis", "risk": "high"},
                },
            ]
        }


class FakeEconomy:
    def proof(self, space_id):
        return {"space_id": space_id, "eligible": space_id == "space_a"}

    def state(self):
        return {
            "credits": [
                {
                    "beast_object_type": "non_financial_compute_reduction_credit",
                    "space_id": "space_a",
                }
            ]
        }


def test_scale_economics_counts_proof_density_and_workload_receipts(tmp_path):
    receipt = {
        "beast_object_type": "live_commons_displacement_harness_receipt",
        "space_id": "space_a",
        "observed": {
            "repeated_matches": 3,
            "cloud_api_calls_avoided": 3,
        },
    }
    (tmp_path / "live_commons_displacement_harness_latest.json").write_text(json.dumps(receipt))

    report = CommonsScaleEconomics(FakeRegistry(), FakeEconomy(), result_root=tmp_path).report()

    density = report["proof_density"]
    assert density["spaces"]["valid"] == 2
    assert density["spaces"]["live_reproduced"] == 1
    assert density["spaces"]["eligible_for_credit"] == 1
    assert density["workload"]["total_repeated_matches"] == 3
    assert density["proof_gap_to_10x3"]["matches_needed"] == 27


def test_scale_ladder_uses_explicit_financial_assumptions(tmp_path):
    assumptions = ScaleEconomicsAssumptions(
        target_spaces=10,
        matches_per_space=3,
        tokens_per_match=3900,
        cloud_call_cost_usd=0.02,
        token_cost_per_1m_usd=5.0,
        setup_cost_usd=1.0,
        marketplace_take_rate=0.1,
        value_tier="fused_inference_crystal",
        tier_value_multiplier=3.0,
    )

    report = CommonsScaleEconomics(FakeRegistry(), FakeEconomy(), result_root=tmp_path).report(assumptions)
    primary = report["scale_ladder"]["primary_question"]
    scenario = report["scale_ladder"]["scenarios"][0]

    assert primary["total_displacements"] == 30
    assert primary["answer"] == "first_economic_signal_under_current_assumptions"
    assert scenario["gross_avoided_cost_usd"] > 0
    assert scenario["value_tier"] == "fused_inference_crystal"
    assert scenario["effective_tokens_per_match"] == 11700
    assert scenario["break_even_displacements_for_setup_cost"] is not None
    assert report["marketplace_readiness"]["public_claim_allowed_now"] is False
    assert report["proof_density"]["tier_inventory"]["forge_candidates"] == 3


def test_tiered_credit_pricing_uses_proof_based_caps(tmp_path):
    receipt = {
        "beast_object_type": "live_commons_displacement_harness_receipt",
        "space_id": "space_a",
        "observed": {"repeated_matches": 3, "cloud_api_calls_avoided": 3},
    }
    (tmp_path / "live_commons_displacement_harness_latest.json").write_text(json.dumps(receipt))

    report = CommonsScaleEconomics(FakeRegistry(), FakeEconomy(), result_root=tmp_path).report()
    pricing = report["tiered_credit_pricing"]
    observed = {item["space_id"]: item for item in pricing["observed_spaces"]}
    space_a = observed["space_a"]
    portfolio = pricing["tiered_10_space_portfolio_example"]

    assert space_a["tier"] == "tier_3_fused_crystal"
    assert space_a["multipliers"]["raw_total"] > 3.0
    assert space_a["multipliers"]["capped_total"] == 3.0
    assert space_a["per_displacement_value_usd"] == 0.06
    assert space_a["total_credit_value_usd"] == 0.18
    assert portfolio["tiered_credit_value_usd"] == 2.8215
    assert portfolio["flat_credit_value_usd"] == 0.76
    assert portfolio["marketplace_take_10pct_usd"] == 0.28215
    assert "omits that Space" in portfolio["source_spec_note"]


def test_marketplace_catalog_lists_only_eligible_spaces_and_stays_non_financial(tmp_path):
    receipt = {
        "beast_object_type": "live_commons_displacement_harness_receipt",
        "space_id": "space_a",
        "observed": {"repeated_matches": 3, "cloud_api_calls_avoided": 3},
    }
    (tmp_path / "live_commons_displacement_harness_latest.json").write_text(json.dumps(receipt))

    catalog = CommonsScaleEconomics(FakeRegistry(), FakeEconomy(), result_root=tmp_path).marketplace_catalog()

    assert catalog["mode"] == "governed_preview"
    assert catalog["listing_count"] == 1
    assert catalog["public_launch_ready"] is False
    assert catalog["financial_transactions_enabled"] is False
    listing = catalog["listings"][0]
    assert listing["space_id"] == "space_a"
    assert listing["primary_action"] == "import_as_quarantined_hypothesis"
    assert listing["scenario_credit"]["transferable"] is False
    assert listing["scenario_credit"]["redeemable"] is False
