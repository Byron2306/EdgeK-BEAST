import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.context_packet import ContextPacketBuilder
from app.kernel.workspace_graph import WorkspaceGraph
from app.main import app


def test_context_packet_includes_bounded_files_and_excludes_sensitive_paths(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "app" / "main.py").write_text("def hello():\n    return 'beast'\n", encoding="utf-8")
    (repo / "config" / ".env").write_text("SECRET_TOKEN=do-not-read\n", encoding="utf-8")

    graph = WorkspaceGraph(db_path=str(tmp_path / "graph.db"))
    graph.index_repository(str(repo), max_files=20)
    builder = ContextPacketBuilder(workspace_graph=graph, max_file_chars=120)
    envelope = {
        "beast_object_type": "task_envelope",
        "version": "1.0",
        "task_id": "tsk_context_test",
        "intent": "Inspect app/main.py and config/.env for a diagnostic.",
        "task_class": "small_patch",
        "privacy_class": "internal",
        "inputs": {
            "user_request": "Inspect app/main.py and config/.env for a diagnostic.",
            "provider": "huggingface",
        },
        "context_budget": {"max_tokens": 8000, "max_files": 8, "allow_full_files": False},
    }

    packet = builder.build(envelope, workspace_root=str(repo), include_content=True)

    assert packet["beast_object_type"] == "context_packet"
    assert packet["packet_id"].startswith("pkt_")
    assert packet["handoff_hash"].startswith("sha256:")
    assert packet["packet_stats"]["estimated_tokens"] > 0
    sources = {item["source"] for item in packet["included_evidence"]}
    assert "app/main.py" in sources
    snippet = next(item for item in packet["included_evidence"] if item["source"] == "app/main.py")
    assert "def hello" in snippet["content"]
    assert "SECRET_TOKEN" not in str(packet)
    assert {"source": "config/.env", "reason": "sensitive_or_blocked"} in packet["excluded_evidence"]


def test_context_packet_hash_is_stable_for_identical_evidence(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.py").write_text("print('stable')\n", encoding="utf-8")
    builder = ContextPacketBuilder(max_file_chars=120)
    envelope = {
        "task_id": "tsk_stable",
        "intent": "Read app/main.py",
        "task_class": "small_patch",
        "privacy_class": "internal",
        "inputs": {"user_request": "Read app/main.py"},
        "context_budget": {"max_tokens": 4000, "max_files": 4, "allow_full_files": False},
    }

    first = builder.build(envelope, workspace_root=str(repo))
    second = builder.build(envelope, workspace_root=str(repo))

    assert first["handoff_hash"] == second["handoff_hash"]
    assert first["packet_id"] == second["packet_id"]


def test_context_packet_includes_beast_artifact_memory(tmp_path):
    data = tmp_path / "data"
    chronicles = data / "chronicles"
    chronicles.mkdir(parents=True)
    (chronicles / "tsk_auth_huggingface_diagnostic.json").write_text(
        '{"task_id":"tsk_auth","task_class":"provider_debugging","provider":"huggingface",'
        '"category":"auth_or_credentials","summary":"Provider diagnostic completed",'
        '"root_cause":"credential missing","recommendations":["Set HF_TOKEN"]}',
        encoding="utf-8",
    )
    graph = WorkspaceGraph(db_path=str(tmp_path / "graph.db"))
    graph.index_beast_artifacts(str(data), include_embeddings=False)
    builder = ContextPacketBuilder(workspace_graph=graph)
    envelope = {
        "task_id": "tsk_new",
        "intent": "Diagnose Hugging Face auth credential failure",
        "task_class": "provider_debugging",
        "privacy_class": "internal",
        "inputs": {"user_request": "Diagnose Hugging Face auth credential failure", "provider": "huggingface"},
        "context_budget": {"max_tokens": 4000, "max_files": 4, "allow_full_files": False},
    }

    packet = builder.build(envelope, workspace_root=str(tmp_path), semantic_limit=3)

    artifacts = [item for item in packet["included_evidence"] if item["kind"] == "artifact_memory"]
    assert artifacts
    assert "credential missing" in artifacts[0]["content"]
    assert packet["workspace_context"]["artifact_match_count"] >= 1


@pytest.mark.asyncio
async def test_context_packet_endpoint_builds_from_raw_request():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/edgek/context/packet",
            json={
                "provider": "huggingface",
                "user_request": "Inspect app/main.py for provider diagnostic routing",
                "run_quality": False,
            },
        )

    assert response.status_code == 200
    packet = response.json()
    assert packet["beast_object_type"] == "context_packet"
    assert packet["route_id"] == "route_provider_diagnostic_huggingface"
    assert packet["handoff_hash"].startswith("sha256:")
