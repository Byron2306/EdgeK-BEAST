from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin


def test_tool_laziness_plugin_recommends_low_value_tools_not_to_call(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    for _ in range(4):
        learner.record("web_search", "fix_import", True, False, tokens_spent=120, cost_usd=0.002, latency_ms=400)
        learner.record("read_file", "fix_import", True, True, tokens_spent=20, latency_ms=5, value_score=0.8)
    plugin = ToolLazinessPlugin(learner)

    result = plugin.recommend_tools(["web_search", "read_file", "unknown_tool"], "fix_import")

    assert [item["name"] for item in result["tools_not_to_call"]] == ["web_search"]
    assert [item["name"] for item in result["tools_to_call"]] == ["read_file"]
    assert [item["name"] for item in result["tools_to_observe"]] == ["unknown_tool"]
    assert result["summary"]["estimated_tokens_avoided"] == 120


def test_tool_laziness_plugin_never_skips_required_workflow_tool(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    for _ in range(3):
        learner.record("pytest", "verify_patch", True, False, tokens_spent=50, latency_ms=100)
    plugin = ToolLazinessPlugin(learner)

    result = plugin.recommend_tools(["pytest"], "verify_patch", required_tools=["pytest"])

    assert not result["tools_not_to_call"]
    assert result["tools_to_call"][0]["reason"] == "required by active workflow"


def test_tool_laziness_plugin_deduplicates_tool_catalog_entries(tmp_path):
    plugin = ToolLazinessPlugin(ToolLazinessLearner(db_path=str(tmp_path / "tools.db")))

    result = plugin.recommend_tools(
        ["read_file", {"name": "read_file", "description": "duplicate"}, {"name": "search", "purpose": "lookup"}],
        "new_scenario",
    )

    assert result["summary"]["candidate_count"] == 2

