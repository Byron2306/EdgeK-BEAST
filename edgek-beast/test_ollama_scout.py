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
    assert len(packet["tool_menu"]) <= 5
    assert packet["model"] == "llama3.2:3b"


def test_ollama_scout_falls_back_without_server(tmp_path):
    scout = OllamaScout(None, policies={"ollama_scout": {"base_url": "http://127.0.0.1:9"}})

    result = scout.scout(
        {"task": "Explain the auth module", "use_ollama": True},
        workspace_root=str(tmp_path),
    )

    assert result["mode"] == "ollama_scout_handoff"
    assert result["packet"]["local_analysis"]["source"] == "edgek_fallback"
    assert result["selected_tools"]


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
