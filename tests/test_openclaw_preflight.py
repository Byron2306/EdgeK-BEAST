from app.kernel.beast_cli_executor import BeastCLIExecutor
from app.kernel.provider_economist import ProviderEconomist
from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.tool_laziness_plugin import ToolLazinessPlugin


def test_openclaw_preflight_consumes_laziness_and_provider_economics(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    for _ in range(3):
        learner.record("read_file", "fix_import", True, False, tokens_spent=100, latency_ms=50)
    executor = BeastCLIExecutor(
        tool_laziness_learner=learner,
        tool_laziness_plugin=ToolLazinessPlugin(learner),
        provider_economist=ProviderEconomist(),
    )
    plan = executor.plan(
        objective="fix import",
        workflow={"required_gates": []},
        context_packet={"included_evidence": [{"kind": "file_snippet", "source": "app/main.py"}]},
        candidate_tools=["read_file", "pytest"],
        provider_candidates=[
            {
                "provider": "expensive", "recommended_role": "clean_patch_candidate",
                "hidden_clean_usd_per_fix": 0.01, "hidden_clean_rate": 0.2,
                "avg_latency_ms": 1000, "auth_confidence": 1.0,
            },
            {
                "provider": "efficient", "recommended_role": "clean_patch_candidate",
                "hidden_clean_usd_per_fix": 0.001, "hidden_clean_rate": 0.2,
                "avg_latency_ms": 1200, "auth_confidence": 1.0,
            },
        ],
        use_ollama=False,
        preflight_budget_ms=500,
        scout_budget_ms=100,
    )

    assert plan["session_handshake"]["beast_object_type"] == "beast_session_handshake"
    assert plan["preflight"]["selected_provider"] == "efficient"
    assert plan["preflight"]["tool_laziness"]["tools_not_to_call"][0]["name"] == "read_file"
    assert plan["suppressed_actions"][0]["request"]["tool_name"] == "read_file"
    assert not any((item.get("request") or {}).get("tool_name") == "read_file" for item in plan["actions"])


def test_required_tool_overrides_laziness_skip(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    for _ in range(3):
        learner.record("read_file", "inspect", True, False, tokens_spent=100)
    executor = BeastCLIExecutor(tool_laziness_plugin=ToolLazinessPlugin(learner))

    plan = executor.plan(
        objective="inspect",
        workflow={"required_gates": []},
        context_packet={"included_evidence": [{"kind": "file_snippet", "source": "README.md"}]},
        candidate_tools=["read_file"],
        required_tools=["read_file"],
        use_ollama=False,
    )

    assert not plan["suppressed_actions"]
    assert plan["actions"][0]["request"]["tool_name"] == "read_file"


def test_preflight_skips_scout_when_scout_budget_is_zero():
    executor = BeastCLIExecutor()

    plan = executor.plan(
        objective="fast local decision",
        workflow={"required_gates": []},
        context_packet={},
        use_ollama=True,
        preflight_budget_ms=50,
        scout_budget_ms=0,
    )

    assert plan["preflight"]["scout"]["budget_skipped"] is True
    assert any(item["phase"] == "ollama_scout" for item in plan["preflight"]["skipped_phases"])
    assert plan["preflight"]["elapsed_ms"] < 50

