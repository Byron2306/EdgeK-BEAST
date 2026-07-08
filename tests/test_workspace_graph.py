from app.kernel.data_processing.workspace_graph import WorkspaceGraph
from app.kernel.data_processing.workspace_graph_service import WorkspaceGraphService
from app.cli.api import BeastApiClient
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
                    "content": "Please inspect app.kernel.governance.reason.py and app/main.py",
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
    assert "app.kernel.governance.reason.py" in recent_labels
    assert "app/main.py" in recent_labels

    search_results = graph.search_nodes("reason.py", node_type="file")
    assert search_results[0]["id"] == "file:app.kernel.governance.reason.py"

    neighborhood = graph.neighborhood("file:app.kernel.governance.reason.py")
    assert neighborhood["center"]["type"] == "file"
    assert any(edge["relation"] == "mentioned_file" for edge in neighborhood["edges"])

    context = graph.context_for_ir({
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Use app.kernel.governance.reason.py"}],
    })
    assert context["matched_node_count"] >= 1
    assert context["matched_nodes"][0]["id"] == "file:app.kernel.governance.reason.py"

    exported = graph.export_graph(node_limit=10, edge_limit=20)
    integrity = graph.integrity_report()

    assert exported["stats"]["total_nodes"] == stats["total_nodes"]
    assert any(node["id"] == "file:app.kernel.governance.reason.py" for node in exported["nodes"])
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


def test_workspace_graph_indexes_richer_file_import_and_test_metadata(tmp_path):
    repo = tmp_path / "repo"
    package = repo / "app"
    tests = repo / "tests"
    package.mkdir(parents=True)
    tests.mkdir(parents=True)
    (package / "service.py").write_text(
        "import json\n"
        "from pathlib import Path\n\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return Path(json.dumps({'ok': True}))\n",
        encoding="utf-8",
    )
    (tests / "test_service.py").write_text(
        "from app.service import Service\n\n"
        "def test_service_runs():\n"
        "    assert Service().run()\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.index_repository(str(repo), max_files=10)
    service_node = graph.search_nodes("app/service.py", node_type="file")[0]
    test_node = graph.search_nodes("tests/test_service.py", node_type="file")[0]
    imports = graph.search_nodes("pathlib", node_type="import")
    tests_nodes = graph.search_nodes("test_service.py", node_type="test")

    assert result["indexed_files"] == 2
    assert result["indexed_imports"] >= 3
    assert result["indexed_tests"] == 1
    assert service_node["properties"]["language"] == "python"
    assert service_node["properties"]["line_count"] >= 5
    assert service_node["properties"]["content_hash"]
    assert test_node["properties"]["is_test"] is True
    assert test_node["properties"]["test_runner"] == "pytest"
    assert imports
    assert tests_nodes


def test_workspace_graph_indexes_routes_and_local_dependency_edges(tmp_path):
    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "service.py").write_text(
        "def get_value():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    (app / "api.py").write_text(
        "from app.service import get_value\n\n"
        "@router.get('/health')\n"
        "def health():\n"
        "    return {'value': get_value()}\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.index_repository(str(repo), max_files=10)
    api_node = graph.search_nodes("app/api.py", node_type="file")[0]
    service_node = graph.search_nodes("app/service.py", node_type="file")[0]
    api_neighborhood = graph.neighborhood(api_node["id"])
    service_neighborhood = graph.neighborhood(service_node["id"])

    assert result["indexed_routes"] == 1
    assert result["indexed_dependencies"] == 1
    assert graph.search_nodes("/health", node_type="route")
    assert any(edge["relation"] == "depends_on" for edge in api_neighborhood["edges"])
    assert any(edge["relation"] == "used_by" for edge in service_neighborhood["edges"])


def test_workspace_graph_file_status_and_changed_since_detect_drift(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    graph.index_repository(str(repo), max_files=10)
    before = graph.file_status(str(repo), "module.py")

    target.write_text("def value():\n    return 2\n", encoding="utf-8")
    after = graph.file_status(str(repo), "module.py")
    changed = graph.changed_since(str(repo), timestamp_ns=before["indexed_mtime_ns"])

    assert before["indexed"] is True
    assert before["changed"] is False
    assert after["changed"] is True
    assert after["indexed_hash"] != after["current_hash"]
    assert changed["changed_count"] >= 1
    assert changed["changed"][0]["path"] == "module.py"


def test_workspace_graph_records_consumed_context_and_stale_events(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    graph.index_repository(str(repo), max_files=10)
    recorded = graph.record_context_consumption("session-a", str(repo), ["module.py"], objective="inspect value")

    target.write_text("def value():\n    return 2\n", encoding="utf-8")
    status = graph.file_status(str(repo), "module.py")
    stale = graph.stale_context_events(str(repo), session_id="session-a")

    assert recorded["recorded"] == 1
    assert status["changed"] is True
    assert status["stale_context_warning"] is True
    assert stale["event_count"] == 1
    assert stale["events"][0]["path"] == "module.py"


def test_workspace_graph_service_indexes_polls_and_serves_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    service = WorkspaceGraphService(graph, default_root=repo)

    indexed = service.index(max_files=10)
    files = service.files(limit=20)
    file_payload = service.file(None, "module.py")
    symbols = service.symbols(q="value", limit=10)

    target.write_text("def value():\n    return 2\n", encoding="utf-8")
    poll = service.poll(reindex=True, max_files=10)
    status = service.status()

    assert indexed["indexed_files"] == 1
    assert files["count"] >= 1
    assert file_payload["ok"] is True
    assert "return 1" in file_payload["content"]
    assert symbols["count"] >= 1
    assert poll["event_count"] >= 1
    assert poll["reindexed"] is True
    assert status["state"]["poll_count"] == 1


def test_workspace_graph_service_emits_stale_context_events(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    service = WorkspaceGraphService(graph, default_root=repo)
    service.index(max_files=10)
    graph.record_context_consumption("session-a", str(repo), ["module.py"], objective="inspect value")

    target.write_text("def value():\n    return 2\n", encoding="utf-8")
    poll = service.poll(reindex=False, max_files=10)

    assert any(event["event"] == "stale_context_warning" for event in poll["events"])




def test_workspace_graph_task_context_packs_selected_and_ranked_nodes(tmp_path):
    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "router.py").write_text(
        "def route_request(provider):\n"
        "    return {'provider': provider, 'route': 'local'}\n",
        encoding="utf-8",
    )
    (app / "budget.py").write_text(
        "def enforce_budget(tokens):\n"
        "    return tokens < 1000\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    graph.index_repository(str(repo), max_files=10)
    context = graph.graph_context_for_task(
        "repair provider route budget handling",
        selected_files=["app/router.py"],
        token_budget=600,
        limit=5,
    )

    reasons = {item["reason"] for item in context["results"]}
    labels = {item["label"] for item in context["results"]}
    assert context["beast_object_type"] == "workspace_graph_task_context"
    assert context["result_count"] >= 1
    assert "selected_file" in reasons
    assert "app/router.py" in labels
    assert context["estimated_tokens"] <= 600


def test_workspace_graph_task_context_can_record_session_consumption(tmp_path):
    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "router.py").write_text(
        "def route_request(provider):\n"
        "    return {'provider': provider, 'route': 'local'}\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    graph.index_repository(str(repo), max_files=10)
    context = graph.graph_context_for_task(
        "route provider",
        selected_files=["app/router.py"],
        token_budget=600,
        limit=3,
        session_id="session-ctx",
    )

    assert context["context_consumption"]["recorded"] >= 1


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


def test_workspace_graph_tree_sitter_helper_extracts_symbols_or_falls_back(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    symbols = graph._extract_symbols_tree_sitter(
        "class Helper:\n"
        "    def run(self):\n"
        "        return True\n\n"
        "def build_helper():\n"
        "    return Helper()\n",
        "python",
        "helpers.py",
    )

    names = {symbol["name"] for symbol in symbols}
    assert {"Helper", "run", "build_helper"}.issubset(names)
    assert all(symbol["file"] == "helpers.py" for symbol in symbols)


def test_sourceplan_apply_and_rollback_refresh_workspace_graph(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    graph.index_repository(str(repo), max_files=10)
    client = BeastApiClient("http://offline", workspace=repo, workspace_graph=graph)
    plan = {
        "plan_id": "plan_graph_refresh",
        "objective": "update value",
        "provider": "local",
        "files_allowed": ["module.py"],
        "operations": [
            {
                "op_id": "op_001",
                "op": "create_or_replace",
                "path": "module.py",
                "content": "def value():\n    return 2\n",
                "selected": True,
            }
        ],
    }

    monkeypatch.delenv("BEAST_PATCH_RUN_TESTS", raising=False)
    applied = client.apply_patch_plan(plan, approved=True)
    rollback = client.rollback_last_patch()
    sourceplans = graph.search_nodes("plan_graph_refresh", node_type="sourceplan")
    rollbacks = graph.search_nodes("plan_graph_refresh", node_type="rollback")
    file_node = graph.search_nodes("module.py", node_type="file")[0]
    neighborhood = graph.neighborhood(file_node["id"])

    assert applied.ok is True
    assert applied.data["workspace_graph_refresh"]["ok"] is True
    assert rollback.ok is True
    assert rollback.data["workspace_graph_refresh"]["ok"] is True
    assert sourceplans
    assert rollbacks
    assert any(edge["relation"] == "changed_by" for edge in neighborhood["edges"])
    assert any(edge["relation"] == "verified_by" for edge in neighborhood["edges"])


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


def test_workspace_graph_indexes_lexical_chunks_without_embedding_model(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "memory_pipeline.py").write_text(
        "class MemoryCompiler:\n"
        "    def contextual_chunk(self):\n"
        "        return 'chronicle route envelope vector rag'\n\n"
        "def lint_gate():\n"
        "    return 'syntax checking and debugging workflow'\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    monkeypatch.setattr(graph, "semantic_available", lambda load_model=False: False)

    result = graph.semantic_index_repository(str(repo), max_files=10, max_chunks=10)
    context = graph.semantic_context(
        "chronicle envelope vector rag MemoryCompiler",
        limit=3,
        include_content=True,
    )

    assert result["semantic_available"] is False
    assert result["indexed_chunks"] >= 1
    assert result["embedded_chunks"] == 0
    assert context["retrieval_mode"] == "lexical_bm25_fallback"
    assert context["result_count"] >= 1
    assert context["results"][0]["chunk_kind"] in {"code_unit", "code_window"}
    assert "MemoryCompiler" in context["results"][0]["content"]


def test_workspace_graph_markdown_chunks_include_context_headers(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ROADMAP.md").write_text(
        "# Memory Layer\n\n"
        "Chronicle records should become retrievable task memory.\n\n"
        "# Tooling Layer\n\n"
        "Plugins skills workflows linting syntax checking and parser routes.\n",
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    monkeypatch.setattr(graph, "semantic_available", lambda load_model=False: False)

    graph.semantic_index_repository(str(repo), max_files=10, max_chunks=10)
    context = graph.semantic_context("plugins skills workflows syntax parser", limit=2)

    assert context["result_count"] >= 1
    assert context["results"][0]["context_header"]
    assert context["results"][0]["chunk_kind"] == "markdown_section"
    assert "Tooling Layer" in context["results"][0]["context_header"] or "Tooling Layer" in context["results"][0]["content"]


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


def test_workspace_graph_indexes_beast_artifacts_for_memory(tmp_path):
    data = tmp_path / "data"
    chronicles = data / "chronicles"
    routes = data / "route_cards"
    chronicles.mkdir(parents=True)
    routes.mkdir(parents=True)
    (chronicles / "tsk_1_huggingface_diagnostic.json").write_text(
        '{"task_id":"tsk_1","task_class":"provider_debugging","provider":"huggingface",'
        '"category":"auth_or_credentials","summary":"Provider diagnostic completed",'
        '"root_cause":"credential missing","recommendations":["Set HF_TOKEN"],'
        '"envelope":{"task_id":"tsk_1","task_class":"provider_debugging",'
        '"intent":"Diagnose Hugging Face","inputs":{"provider":"huggingface"}}}',
        encoding="utf-8",
    )
    (routes / "route_provider_diagnostic_huggingface.json").write_text(
        '{"route_id":"route_provider_diagnostic_huggingface","task_class":"provider_debugging",'
        '"provider":"huggingface","context":"Diagnose provider calls",'
        '"preferred_order":["provider_policy","credentials"],"avoid":["secret_value_capture"]}',
        encoding="utf-8",
    )

    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    result = graph.index_beast_artifacts(str(data), include_embeddings=False)
    stats = graph.stats()

    assert result["indexed_artifacts"] >= 3
    assert stats["node_types"]["beast_artifact"] >= 3
    assert graph.search_nodes("huggingface", node_type="provider")
    artifact_nodes = graph.search_nodes("tsk_1", node_type="beast_artifact")
    assert artifact_nodes
    assert "HF_TOKEN" in artifact_nodes[0]["properties"]["preview"]


def test_workspace_graph_integrity_reports_orphan_edges(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "workspace_graph.db"))
    timestamp = "2026-06-11T00:00:00Z"
    graph.upsert_node("file:app/main.py", "file", "app/main.py", {}, timestamp)
    graph.upsert_edge("missing:source", "file:app/main.py", "mentions", {}, timestamp)

    report = graph.integrity_report()

    assert report["ok"] is False
    assert report["orphan_edge_count"] == 1
    assert report["orphan_edges"][0]["source"] == "missing:source"
