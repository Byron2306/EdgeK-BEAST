import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.ollama_scout import OllamaScout
from app.kernel.workspace_graph import WorkspaceGraph
from app.main import app


def test_ollama_scout_builds_handoff_packet(tmp_path):
    graph = WorkspaceGraph(str(tmp_path / "graph.db"))
    graph.upsert_node(
        "file:app/auth.py",
        "file",
        "app/auth.py",
        {"path": "app/auth.py"},
        "2026-06-12T00:00:00Z",
    )
    scout = OllamaScout(graph, policies={"ollama_scout": {"default_model": "llama3.2:3b"}})

    packet = scout.build_packet(
        task="Find why login token refresh test fails",
        workspace_root=str(tmp_path),
        include_postgres_schema=False,
        include_github_context=False,
    )

    assert packet["goal"] == "Find why login token refresh test fails"
    assert packet["handoff_hash"].startswith("sha256:")
    assert packet["local_analysis"]["task_type"] == "test_failure"
    assert packet["decision_contract"]["beast_object_type"] == "ollama_local_decision_contract"
    assert packet["decision_contract"]["packet_hash"] == packet["handoff_hash"]
    assert "verifier" in packet["decision_contract"]["role_hints"]
    assert len(packet["tool_menu"]) <= 5
    assert packet["model"] == "llama3.2:3b"
    assert "ranked_chunks" in packet
    assert "chronicle_summary" in packet
    assert "fallback_recommendations" in packet


def test_ollama_scout_falls_back_without_server(tmp_path):
    scout = OllamaScout(None, policies={"ollama_scout": {"base_url": "http://127.0.0.1:9"}})

    result = scout.scout(
        {"task": "Explain the auth module", "use_ollama": True},
        workspace_root=str(tmp_path),
    )

    assert result["mode"] == "ollama_scout_handoff"
    assert result["packet"]["local_analysis"]["source"] == "edgek_fallback"
    assert result["decision_contract"]["source"] == "edgek_fallback"
    assert result["decision_contract"]["recommended_profile"] in {"openclaw", "zeroclaw"}
    assert result["selected_tools"]


def test_ollama_scout_packet_includes_compact_forensic_context(tmp_path):
    class FakeForensicMemory:
        def query(self, query, event_kind=None, layer=None, provider=None, status=None, limit=10):
            return {
                "retrieval_mode": "lexical_fallback",
                "vector_available": False,
                "filters": {"event_kind": event_kind, "layer": layer, "provider": provider, "status": status},
                "result_count": 1,
                "results": [
                    {
                        "event_id": "for_1",
                        "event_kind": "packet_observation",
                        "layer": "L4",
                        "provider": "ollama",
                        "status": "failed",
                        "severity": "high",
                        "priority_score": 0.91,
                        "lexical_score": 2.0,
                        "source_uri": "intercept://packet/for_1",
                        "event": {"summary": "raw packet was too large"},
                        "evidence": {
                            "summary": "large packet retained as forensic signal",
                            "signals": ["intercept_packet_observation", "intercept_layer_l4"],
                            "recommended_actions": ["Compress packet before Ollama handoff."],
                        },
                    }
                ],
            }

    scout = OllamaScout(
        None,
        policies={"ollama_scout": {"base_url": "http://127.0.0.1:9"}},
        forensic_memory=FakeForensicMemory(),
    )

    packet = scout.build_packet(
        task="Diagnose large Ollama packet failure",
        workspace_root=str(tmp_path),
        include_postgres_schema=False,
        include_github_context=False,
        forensic_layer="L4",
        forensic_event_kind="packet_observation",
    )
    scout_view = scout._scout_view(packet)

    assert packet["forensic_context"]["available"] is True
    assert packet["forensic_context"]["results"][0]["layer"] == "L4"
    assert packet["packet_stats"]["forensic_results"] == 1
    assert scout_view["forensic_context"]["results"][0]["event_kind"] == "packet_observation"
    assert packet["fallback_recommendations"][0]["action"] == "inspect_forensic_l4"


def test_ollama_scout_ranks_chunks_and_summarizes_chronicle(tmp_path):
    data_dir = tmp_path / "data" / "evidence_chronicles"
    data_dir.mkdir(parents=True)
    (data_dir / "ev.json").write_text(
        '{"evidence":{"summary":"Provider circuit timeout repeated","provider":"groq","severity":"high","capability_family":"diagnostics","priority_score":0.9,"signals":["intercept_circuit"]}}',
        encoding="utf-8",
    )

    class FakeGraph:
        def stats(self):
            return {"total_nodes": 1, "total_edges": 0}

        def semantic_context(self, query, limit, include_content, max_chars_per_chunk):
            return {
                "results": [
                    {
                        "file": "app/provider.py",
                        "start_line": 10,
                        "end_line": 20,
                        "similarity": 0.7,
                        "content": "def diagnose_circuit_timeout(): pass",
                    },
                    {
                        "file": "docs/readme.md",
                        "start_line": 1,
                        "end_line": 2,
                        "similarity": 0.2,
                        "content": "general notes",
                    },
                ]
            }

    scout = OllamaScout(
        FakeGraph(),
        policies={"ollama_scout": {"base_url": "http://127.0.0.1:9"}},
        data_dir=str(tmp_path / "data"),
    )
    packet = scout.build_packet(
        task="diagnose provider circuit timeout",
        workspace_root=str(tmp_path),
        include_postgres_schema=False,
        include_github_context=False,
    )

    assert packet["ranked_chunks"][0]["file"] == "app/provider.py"
    assert packet["ranked_chunks"][0]["rank"] == 1
    assert packet["chronicle_summary"]["available"] is True
    assert packet["chronicle_summary"]["record_count"] == 1
    assert "run_provider_diagnostic" in {item["action"] for item in packet["fallback_recommendations"]}


def test_ollama_scout_uses_bounded_memory_view(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": (
                        '{"task_type":"bug_fix","risk":"medium","needs_cloud":true,'
                        '"privacy_level":"redacted_cloud_ok","confidence":0.8,'
                        '"relevant_files":["app/auth.py"],"needed_tools":["repo.semantic_context"],'
                        '"redaction_required":false,"summary":"bounded"}'
                    )
                }
            }

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    class FakeGraph:
        def stats(self):
            return {
                "total_nodes": 10,
                "total_edges": 4,
                "node_types": {"semantic_chunk": 3},
                "file_read_cache": {"l1_entries": 1, "l2_entries": 2},
                "semantic": {"available": True, "chunks": 3},
                "tree_sitter": {"available": True, "languages": ["python"]},
            }

        def semantic_context(self, query, limit, include_content, max_chars_per_chunk):
            return {
                "results": [
                    {
                        "file": "app/auth.py",
                        "start_line": 1,
                        "end_line": 200,
                        "similarity": 0.99,
                        "content": "refresh_token = True\n" + ("huge context " * 1000),
                    }
                ]
            }

    monkeypatch.setattr("app.kernel.ollama_scout.httpx.post", fake_post)
    scout = OllamaScout(
        FakeGraph(),
        policies={
            "ollama_scout": {
                "max_prompt_chars": 1800,
                "max_chunk_chars": 120,
                "max_exact_chars": 140,
                "num_ctx": 512,
                "timeout_seconds": 3,
            }
        },
    )
    packet = scout.build_packet(
        task="Debug refresh token loop",
        workspace_root=".",
        include_postgres_schema=False,
        include_github_context=False,
    )
    decision = scout._call_ollama(packet, model="qwen2.5:0.5b")

    prompt = captured["payload"]["messages"][0]["content"]
    assert decision["source"] == "ollama"
    assert "role_hints" in decision
    assert packet["memory_state"]["available"] is True
    assert packet["packet_stats"]["ollama_scout_view_chars"] < packet["packet_stats"]["full_packet_chars"]
    assert len(prompt) <= 1800
    assert captured["payload"]["options"]["num_ctx"] == 512
    assert "huge context " * 20 not in prompt
    assert "truncated" in prompt


@pytest.mark.asyncio
async def test_ollama_scout_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status = await client.get("/edgek/ollama/status")
        packet = await client.post("/edgek/ollama/packet", json={"task": "Debug login test failure"})
        scout = await client.post("/edgek/ollama/scout", json={"task": "Debug login test failure", "use_ollama": False})

    assert status.status_code == 200
    assert "installed" in status.json()
    assert packet.status_code == 200
    assert packet.json()["handoff_hash"].startswith("sha256:")
    assert scout.status_code == 200
    assert scout.json()["packet"]["local_analysis"]["source"] == "edgek_fallback"
    assert scout.json()["decision_contract"]["beast_object_type"] == "ollama_local_decision_contract"
