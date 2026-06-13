from app.kernel.workspace_graph import WorkspaceGraph
import pytest


def test_workspace_graph_observes_trace_nodes_and_edges(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    trace = {
        "trace_id": "trace-1",
        "timestamp": "2026-06-11T00:00:00Z",
        "session_id": "session-a",
        "provider_type": "openai",
        "edgek_ir": {
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "user",
                    "content": "Please inspect app/kernel/reason.py and app/main.py",
                }
            ],
            "metadata": {
                "context_economy": {
                    "changed": True,
                    "strategy": "deterministic_trim",
                    "within_input_budget": True,
                    "original_tokens": 100,
                    "final_tokens": 60,
                }
            },
        },
        "governance_result": {
            "decision": "allow",
            "policies_applied": ["max_input_tokens_per_request"],
            "budget_impact": {"estimated_cost_usd": 0.001},
        },
    }

    result = graph.observe_trace(trace)
    stats = graph.stats()
    recent_labels = {node["label"] for node in graph.recent_nodes()}

    assert result["node_count"] >= 6
    assert stats["node_types"]["trace"] == 1
    assert stats["node_types"]["file"] == 2
    assert "app/kernel/reason.py" in recent_labels
    assert "app/main.py" in recent_labels

    search_results = graph.search_nodes("reason.py", node_type="file")
    assert search_results[0]["id"] == "file:app/kernel/reason.py"

    neighborhood = graph.neighborhood("file:app/kernel/reason.py")
    assert neighborhood["center"]["type"] == "file"
    assert any(edge["relation"] == "mentioned_file" for edge in neighborhood["edges"])

    context = graph.context_for_ir({
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Use app/kernel/reason.py"}],
    })
    assert context["matched_node_count"] >= 1
    assert context["matched_nodes"][0]["id"] == "file:app/kernel/reason.py"

    exported = graph.export_graph(node_limit=10, edge_limit=20)
    integrity = graph.integrity_report()

    assert exported["stats"]["total_nodes"] == stats["total_nodes"]
    assert any(node["id"] == "file:app/kernel/reason.py" for node in exported["nodes"])
    assert any(edge["relation"] == "mentioned_file" for edge in exported["edges"])
    assert integrity["ok"] is True
    assert integrity["orphan_edge_count"] == 0


def test_workspace_graph_indexes_repository_files_and_symbols(tmp_path):
    repo = tmp_path / "repo"
    package = repo / "app" / "kernel"
    package.mkdir(parents=True)
    (package / "sample.py").write_text(
        "class Sample:\n"
        "    pass\n\n"
        "def run_sample():\n"
        "    return Sample()\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.index_repository(str(repo), max_files=10)
    stats = graph.stats()

    assert result["indexed_files"] == 1
    assert result["indexed_symbols"] == 2
    assert stats["node_types"]["repository"] == 1
    assert stats["node_types"]["directory"] >= 1
    assert stats["node_types"]["symbol"] == 2
    assert graph.search_nodes("run_sample", node_type="symbol")[0]["label"] == "run_sample"


def test_workspace_graph_indexes_javascript_symbols_with_multilanguage_parser(tmp_path):
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    (src / "widget.js").write_text(
        "class Widget {\n"
        "  render() { return true; }\n"
        "}\n\n"
        "function buildWidget() {\n"
        "  return new Widget();\n"
        "}\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.index_repository(str(repo), max_files=10)

    assert result["indexed_files"] == 1
    assert result["indexed_symbols"] >= 2
    assert graph.search_nodes("Widget", node_type="symbol")
    assert graph.search_nodes("buildWidget", node_type="symbol")
    assert "tree_sitter" in graph.stats()


def test_workspace_graph_semantic_index_context_and_dedupe(tmp_path):
    pytest.importorskip("sentence_transformers")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "budget.py").write_text(
        "def enforce_budget(request):\n"
        "    tokens = request.get('tokens', 0)\n"
        "    return tokens < 1000\n\n"
        "def cache_file_read(path):\n"
        "    return path\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.semantic_index_repository(str(repo), max_files=10, max_chunks=10)
    context = graph.semantic_context("token budget enforcement", limit=3, include_content=True)
    dedupe = graph.semantic_dedupe_payloads([
        "read app/main.py and inspect token budget enforcement",
        "read app/main.py and inspect token budget enforcement",
        "unrelated deployment nginx config",
    ])

    assert result["semantic_available"] is True
    assert result["indexed_chunks"] >= 1
    assert context["result_count"] >= 1
    assert "enforce_budget" in context["results"][0]["content"]
    assert dedupe["duplicates"] >= 1
    assert graph.stats()["semantic"]["embeddings"] >= 1


def test_workspace_graph_rebuilds_from_trace_archive(tmp_path):
    trace_path = tmp_path / "traces.jsonl"
    trace_path.write_text(
        '{"trace_id":"trace-1","timestamp":"2026-06-11T00:00:00Z",'
        '"session_id":"session-a","provider_type":"openai",'
        '"edgek_ir":{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Use app/main.py"}]},'
        '"governance_result":{"decision":"allow","policies_applied":["max_input_tokens_per_request"],'
        '"budget_impact":{"estimated_cost_usd":0.001}}}\n',
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.rebuild_from_traces(str(trace_path), clear_existing=True)
    stats = graph.stats()

    assert result["processed_traces"] == 1
    assert result["errors"] == 0
    assert stats["node_types"]["trace"] == 1
    assert graph.get_node("file:app/main.py") is not None


def test_workspace_graph_integrity_reports_orphan_edges(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    timestamp = "2026-06-11T00:00:00Z"
    graph.upsert_node("file:app/main.py", "file", "app/main.py", {}, timestamp)
    graph.upsert_edge("missing:source", "file:app/main.py", "mentions", {}, timestamp)

    report = graph.integrity_report()

    assert report["ok"] is False
    assert report["orphan_edge_count"] == 1
    assert report["orphan_edges"][0]["source"] == "missing:source"
