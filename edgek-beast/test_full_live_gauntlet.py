from benchmarks import full_live_gauntlet
from benchmarks import provider_edge_compare


def test_full_gauntlet_dry_run_combines_suites(monkeypatch):
    monkeypatch.setattr(full_live_gauntlet.edge_metrics_benchmark, "benchmark_latency", lambda: {
        "median_latency_reduction_percent": 12.5,
    })
    monkeypatch.setattr(full_live_gauntlet.edge_metrics_benchmark, "benchmark_bandwidth", lambda: {
        "industrial_telemetry": {"schema_rows_reduction_percent": 33.0},
    })
    monkeypatch.setattr(full_live_gauntlet.edge_metrics_benchmark, "benchmark_loop_protection", lambda: {})
    monkeypatch.setattr(full_live_gauntlet.edge_metrics_benchmark, "benchmark_cost_efficiency", lambda: {
        "combined_token_reduction_percent": 44.0,
    })
    monkeypatch.setattr(full_live_gauntlet.edge_metrics_benchmark, "benchmark_tool_laziness", lambda: {})
    monkeypatch.setattr(full_live_gauntlet.edge_metrics_benchmark, "benchmark_swarm", lambda: {})

    class FakeMegaGauntlet:
        def run(self, session_id=None):
            return {
                "session_id": session_id,
                "cipc_metrics": {
                    "context_quality_measurement": {"token_reduction_percent": 55.0},
                    "stateful_safety": {"circuit_opened": True},
                },
            }

    monkeypatch.setattr(full_live_gauntlet, "MegaGauntlet", FakeMegaGauntlet)
    monkeypatch.setattr(full_live_gauntlet.provider_edge_compare, "run_compare", lambda timeout, repeats, dry_run: {
        "configured_providers": [],
        "summary": {"note": "No provider calls executed."},
        "runs": [],
    })
    monkeypatch.setattr(full_live_gauntlet, "ollama_scout_benchmark", lambda live: {
        "mode": "bounded_local_scout",
        "live_ollama_calls": live,
        "runs": [{"used_ollama": False, "packet_stats": {"ollama_prompt_char_limit": 7000}}],
    })

    report = full_live_gauntlet.run_full_gauntlet(live=False, repeats=1, timeout=1.0)

    assert report["live_api_calls"] is False
    assert report["summary"]["edge_latency_reduction_percent"] == 12.5
    assert report["summary"]["cipc_handoff_token_reduction_percent"] == 55.0
    assert report["summary"]["cipc_postgres_circuit_opened"] is True
    assert report["summary"]["ollama_scout_prompt_limits"] == [7000]
    assert report["enterprise"]["sealed_trace"]["round_trip_ok"] is True


def test_provider_compare_scenario_sizing_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_COMPARE_TELEMETRY_COUNT", "24")
    monkeypatch.setenv("PROVIDER_COMPARE_CONTEXT_REPEATS", "24")
    monkeypatch.setenv("PROVIDER_COMPARE_TOOL_COUNT", "24")

    scenarios = provider_edge_compare.build_scenarios()

    assert len(scenarios) == 3
    assert len(scenarios[0]["telemetry"]) == 24
    assert scenarios[1]["context"].count("historical diagnostic context") == 24
    assert scenarios[2]["source"].count("def tool_") == 24


def test_provider_compare_can_keep_local_nim_scout_only(monkeypatch):
    monkeypatch.setenv("LOCAL_NIM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LOCAL_NIM_SCOUT_ONLY", "1")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    providers = provider_edge_compare.configured_providers()

    assert providers == []
