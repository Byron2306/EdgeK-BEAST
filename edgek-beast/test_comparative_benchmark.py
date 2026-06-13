from app.kernel.benchmark import ComparativeBenchmark, MegaGauntlet
from app.kernel.reason import BudgetLedger, Reasoner


def test_comparative_benchmark_reports_gated_vs_non_gated(tmp_path):
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": 100,
            "max_output_tokens_per_request": 50,
            "max_tool_calls_per_request": 2,
            "semantic_risk_governance_enabled": True,
            "context_compression_trigger_ratio": 0.5,
            "context_compression_ratio_target": 0.5,
        },
        "providers": {
            "openai": {
                "enabled": True,
                "rate_limit_rpm": 100,
                "rate_limit_tpm": 100000,
                "pricing": {"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002},
            }
        },
    }
    reasoner = Reasoner(
        policy_path=str(tmp_path / "missing.yaml"),
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
    )
    reasoner.policies = policies
    runner = ComparativeBenchmark(policies, reasoner=reasoner)

    report = runner.run(
        scenarios=[
            {
                "name": "output_cap",
                "provider": "openai",
                "request": {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 500,
                },
            },
            {
                "name": "tool_cap",
                "provider": "openai",
                "request": {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "tools"}],
                    "tools": [{"type": "function", "function": {"name": str(i)}} for i in range(3)],
                },
            },
        ],
        session_id="bench-test",
    )

    assert report["scenario_count"] == 2
    assert report["totals"]["non_gated_issue_count"] >= 2
    assert report["scenarios"][0]["gated"]["decision"] == "modify"
    assert report["scenarios"][1]["gated"]["decision"] == "deny"


def test_mega_gauntlet_runs_provider_profiles(tmp_path):
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": 1000,
            "max_output_tokens_per_request": 200,
            "max_tool_calls_per_request": 5,
            "semantic_risk_governance_enabled": True,
            "context_compression_trigger_ratio": 0.5,
            "context_compression_ratio_target": 0.5,
        },
        "providers": {
            name: {
                "enabled": True,
                "rate_limit_rpm": 1000,
                "rate_limit_tpm": 1000000,
                "pricing": {"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002},
            }
            for name in ["openai", "anthropic", "google"]
        },
    }
    reasoner = Reasoner(
        policy_path=str(tmp_path / "missing.yaml"),
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
    )
    reasoner.policies = policies
    gauntlet = MegaGauntlet(policies, reasoner=reasoner)

    report = gauntlet.run(
        providers=["openai", "anthropic", "google"],
        scenario_names=["baseline", "runaway_output", "tool_flood"],
        session_id="mega-test",
    )

    assert report["coverage"]["total_cases"] == 9
    assert set(report["scorecard"]["by_provider"]) == {"openai", "anthropic", "google"}
    assert report["totals"]["non_gated_issue_count"] >= 3


def test_mega_gauntlet_blocks_semantic_risks(tmp_path):
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": 1000,
            "max_output_tokens_per_request": 200,
            "max_tool_calls_per_request": 5,
            "semantic_risk_governance_enabled": True,
        },
        "providers": {
            "openai": {
                "enabled": True,
                "rate_limit_rpm": 1000,
                "rate_limit_tpm": 1000000,
                "pricing": {"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002},
            }
        },
    }
    reasoner = Reasoner(
        policy_path=str(tmp_path / "missing.yaml"),
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
    )
    reasoner.policies = policies
    gauntlet = MegaGauntlet(policies, reasoner=reasoner)

    report = gauntlet.run(
        providers=["openai"],
        scenario_names=["prompt_injection", "secret_exfil", "destructive_ops", "financial_high_stakes"],
        session_id="risk-test",
    )

    assert {case["gated"]["decision"] for case in report["cases"]} == {"deny"}
    assert report["totals"]["issues_prevented"] == 4


def test_mega_gauntlet_reports_cipc_pipeline_metrics(tmp_path):
    policies = {
        "meta_rules": {
            "context_economizer_enabled": True,
            "max_input_tokens_per_request": 1000,
            "max_output_tokens_per_request": 200,
            "max_tool_calls_per_request": 5,
            "semantic_risk_governance_enabled": True,
            "circuit_breaker_enabled": True,
            "circuit_breaker_failure_threshold": 5,
        },
        "providers": {
            "openai": {
                "enabled": True,
                "rate_limit_rpm": 1000,
                "rate_limit_tpm": 1000000,
                "pricing": {"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002},
            },
            "openrouter": {
                "enabled": True,
                "pricing": {"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002},
            },
        },
    }
    reasoner = Reasoner(
        policy_path=str(tmp_path / "missing.yaml"),
        budget_ledger=BudgetLedger(str(tmp_path / "budget.db")),
    )
    reasoner.policies = policies
    gauntlet = MegaGauntlet(policies, reasoner=reasoner)

    report = gauntlet.run(
        providers=["openai"],
        scenario_names=["baseline"],
        session_id="cipc-test",
    )

    metrics = report["cipc_metrics"]
    quality = metrics["context_quality_measurement"]
    cost = metrics["cost_benefit_analysis"]
    efficiency = metrics["context_efficiency_benchmark"]
    safety = metrics["stateful_safety"]
    rust = metrics["rust_speed_advantage"]

    assert quality["handoff_packet_tokens"] < quality["raw_context_tokens"]
    assert quality["handoff_packet_success_score"] >= quality["raw_context_success_score"]
    assert cost["handoff_estimated_big_api_cost_usd"] < cost["raw_estimated_big_api_cost_usd"]
    assert efficiency["gateway_tokens"] < efficiency["raw_copy_paste_tokens"]
    assert safety["circuit_opened"] is True
    assert safety["accepted_failures_before_interrupt"] == 5
    assert "rtk_available" in rust
    assert rust["python_latency_ms"] >= 0
