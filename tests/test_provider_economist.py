from app.kernel.provider_economist import EconomistPolicy, ProviderEconomist


def test_provider_economist_chooses_hidden_clean_economic_route():
    candidates = [
        {
            "provider": "qwen_coder", "recommended_role": "clean_patch_candidate",
            "sample_size": 10, "hidden_clean_completed": 2, "hidden_clean_rate": 0.2,
            "hidden_clean_usd_per_fix": 0.0016, "rescued_completed": 8,
            "avg_latency_ms": 4000, "auth_confidence": 1.0,
        },
        {
            "provider": "gptoss", "recommended_role": "cheap_clean_candidate_slow",
            "sample_size": 10, "hidden_clean_completed": 2, "hidden_clean_rate": 0.2,
            "hidden_clean_usd_per_fix": 0.0005, "rescued_completed": 8,
            "avg_latency_ms": 9000, "auth_confidence": 1.0,
        },
    ]

    decision = ProviderEconomist().select(candidates, EconomistPolicy())

    assert decision["decision"] == "route_selected"
    assert decision["selected"]["provider"] == "gptoss"
    assert decision["selected"]["hidden_clean_per_usd"] == 2000.0


def test_provider_economist_excludes_invalid_auth_latency_and_cost_routes():
    candidates = [
        {"provider": "fal", "recommended_role": "do_not_use_until_auth_fixed", "auth_confidence": 0.0},
        {
            "provider": "slow", "recommended_role": "candidate_patch_provider",
            "auth_confidence": 1.0, "avg_latency_ms": 50000,
            "hidden_clean_usd_per_fix": 0.01,
        },
        {
            "provider": "eligible", "recommended_role": "candidate_patch_provider",
            "auth_confidence": 0.95, "avg_latency_ms": 1000,
            "hidden_clean_usd_per_fix": 0.0008, "hidden_clean_rate": 0.2,
        },
    ]
    policy = EconomistPolicy(max_latency_ms=10000, max_usd_per_fix=0.002, min_auth_confidence=0.8)

    decision = ProviderEconomist().select(candidates, policy)

    assert decision["selected"]["provider"] == "eligible"
    excluded = {item["provider"]: item["exclusion_reasons"] for item in decision["excluded"]}
    assert "role do_not_use_until_auth_fixed is not routable" in excluded["fal"]
    assert "latency exceeds envelope" in excluded["slow"]
    assert "hidden-clean USD/fix exceeds envelope" in excluded["slow"]


def test_provider_economist_can_require_first_party_cost_observation():
    decision = ProviderEconomist().select(
        [{"provider": "xai", "recommended_role": "clean_candidate_cost_incomplete", "auth_confidence": 1.0}],
        EconomistPolicy(require_cost_observation=True),
    )

    assert decision["decision"] == "no_eligible_route"
    assert decision["excluded"][0]["exclusion_reasons"] == ["cost observation required"]


def test_verified_cost_does_not_claim_hidden_clean_economics_without_hidden_success():
    decision = ProviderEconomist().select([{
        "provider": "rescue_only", "recommended_role": "fast_rescue_backed_action_ir",
        "first_party_usd_per_verified_fix": 0.0005, "hidden_clean_completed": 0,
        "route_confidence": "high", "rescued_completed": 10, "sample_size": 10,
    }], EconomistPolicy(requested_role="rescued_patch_provider"))

    selected = decision["selected"]
    assert selected["hidden_clean_per_usd"] is None
    assert selected["verified_fixes_per_usd"] == 2000.0
    assert selected["auth_confidence"] == 0.9


def test_provider_economist_excludes_only_active_matching_negative_capability():
    candidates = [
        {"provider": "nvidia_nim", "model": "nemotron", "auth_confidence": 1.0},
        {"provider": "groq", "model": "llama", "auth_confidence": 1.0},
    ]
    negative = {
        "record_id": "negative_nim_stream",
        "capability_id": "provider:nvidia_nim",
        "task_class": "code_generation",
        "scope": {"provider": "nvidia_nim", "model": "nemotron"},
        "state": "active",
        "failure_count": 3,
    }

    decision = ProviderEconomist().select(
        candidates,
        EconomistPolicy(task_class="code_generation"),
        negative_capabilities=[negative],
    )

    assert decision["selected"]["provider"] == "groq"
    excluded = {item["provider"]: item for item in decision["excluded"]}
    assert "negative_nim_stream" in excluded["nvidia_nim"]["exclusion_reasons"][0]


def test_phase2_friction_shadow_score_does_not_change_default_selection():
    candidates = [
        {"provider": "nim", "model": "m", "auth_confidence": 1.0, "hidden_clean_per_usd": 100},
        {"provider": "groq", "model": "g", "auth_confidence": 1.0, "hidden_clean_per_usd": 90},
    ]
    friction = [{
        "profile_id": "friction_nim", "capability_id": "provider:nim", "task_class": "code_generation",
        "scope": {"provider": "nim", "model": "m"}, "friction_score": 1.0, "confidence": 1.0, "samples": 5,
    }]

    shadow = ProviderEconomist().select(
        candidates, EconomistPolicy(task_class="code_generation"), friction_profiles=friction,
    )
    enforced = ProviderEconomist().select(
        candidates, EconomistPolicy(task_class="code_generation", friction_mode="enforce"), friction_profiles=friction,
    )

    assert shadow["selected"]["provider"] == "nim"
    assert shadow["selected"]["friction_shadow_score"] < shadow["selected"]["base_economist_score"]
    assert shadow["phase2_friction"]["base_selected_provider"] == "nim"
    assert shadow["phase2_friction"]["friction_selected_provider"] == "groq"
    assert shadow["phase2_friction"]["selection_would_change"] is True
    assert shadow["phase2_friction"]["selection_changed"] is False
    assert enforced["selected"]["provider"] == "groq"
    assert enforced["phase2_friction"]["selection_changed"] is True


def test_provider_economist_emits_bounded_counterfactual_crystals():
    candidates = [
        {"provider": "nim", "model": "m", "auth_confidence": 1.0, "hidden_clean_per_usd": 100},
        {"provider": "slow", "model": "s", "auth_confidence": 0.9, "hidden_clean_per_usd": 80, "avg_latency_ms": 45_000},
        {"provider": "unknown_cost", "model": "u", "auth_confidence": 0.9},
        {"provider": "blocked", "recommended_role": "do_not_use_until_auth_fixed", "auth_confidence": 0.0},
    ]

    decision = ProviderEconomist().select(candidates, EconomistPolicy(task_class="code_generation"))
    crystals = decision["counterfactual_crystals"]

    assert 1 <= len(crystals) <= 3
    assert crystals[0]["selected_provider"] == decision["selected"]["provider"]
    assert crystals[0]["alternative_provider"] != decision["selected"]["provider"]
    assert crystals[0]["predicted_failure_class"] in {"latency_risk", "cost_unknown", "auth_or_route_confidence", "lower_expected_value"}
    assert "rejection_reason" in crystals[0]
