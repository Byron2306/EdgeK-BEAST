from app.kernel.tool_laziness import ToolLazinessLearner
from app.kernel.workspace_graph import WorkspaceGraph
import pytest


def test_tool_laziness_learns_skip_for_low_value_calls(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))

    learner.record("search", "repeat", True, False, tokens_spent=100, cost_usd=0.01, latency_ms=50)
    learner.record("search", "repeat", True, False, tokens_spent=110, cost_usd=0.011, latency_ms=55)
    recommendation = learner.record("search", "repeat", True, False, tokens_spent=90, cost_usd=0.009, latency_ms=45)

    assert recommendation["decision"] == "skip"
    assert recommendation["estimated_avoidance"]["tokens"] == 100


def test_tool_laziness_benchmark_projects_avoidance(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    report = learner.benchmark_learning()

    assert report["final_recommendation"]["decision"] == "skip"
    assert report["critical_final_recommendation"]["decision"] == "call"
    assert report["projected_100_redundant_calls"]["tokens_avoided"] > 0


def test_tool_laziness_calls_rare_high_value_tool(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))

    learner.record("provider", "rare-critical", True, False, tokens_spent=100, latency_ms=50)
    learner.record("provider", "rare-critical", True, False, tokens_spent=100, latency_ms=50)
    learner.record("provider", "rare-critical", True, True, tokens_spent=100, latency_ms=50, value_score=1.0)
    recommendation = learner.record("provider", "rare-critical", True, False, tokens_spent=100, latency_ms=50)

    assert recommendation["decision"] == "call"
    assert recommendation["reason"] == "rare critical success observed"


def test_tool_laziness_high_token_schema_benchmark(tmp_path):
    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))

    report = learner.benchmark_schema_laziness(tool_count=64, turns=24, relevant_tools_per_turn=4)

    assert report["static_total_tokens"] > report["lazy_total_tokens"]
    assert report["token_reduction_percent"] > 50
    assert report["skipped_calls"] > 0


def test_tool_laziness_semantic_recommend_uses_workspace_evidence(tmp_path):
    pytest.importorskip("sentence_transformers")
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "budget.py").write_text(
        "def enforce_budget(request):\n"
        "    return request.get('tokens', 0) < 1000\n",
        encoding="utf-8",
    )
    graph.semantic_index_repository(str(repo), max_files=5, max_chunks=5)

    learner = ToolLazinessLearner(db_path=str(tmp_path / "tools.db"))
    for _ in range(4):
        learner.record("read_file", "budget_lookup", True, False, tokens_spent=100, latency_ms=500)

    recommendation = learner.semantic_recommend(
        "read_file",
        "budget_lookup",
        "find token budget enforcement logic",
        graph,
        min_similarity=0.4,
    )

    assert recommendation["semantic"]["matches"]
    assert recommendation["decision"] == "call"
