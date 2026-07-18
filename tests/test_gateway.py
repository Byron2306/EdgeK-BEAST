import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from benchmarks import public_economic_thesis_harness as harness


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint():
    async with _client() as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint():
    async with _client() as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "BEAST Commons" in response.text
    assert "/beast-assets/idle/frame_00.png" in response.text
    assert "/commons-media/beast-logo.png" in response.text
    assert "/commons-media/inference-economy.mp4" in response.text
    assert "/commons-media/inference-inversion.pptx" in response.text
    assert "TUI Web Surface" in response.text
    assert "Raw status" not in response.text
    assert 'href="/edgek/federated-commons"' not in response.text


@pytest.mark.asyncio
async def test_root_info_endpoint():
    async with _client() as client:
        response = await client.get("/edgek/root-info")

    assert response.status_code == 200
    assert response.json()["service"] == "EdgeK BEAST Gateway"


@pytest.mark.asyncio
async def test_commons_media_assets():
    async with _client() as client:
        logo = await client.head("/commons-media/beast-logo.png")
        video = await client.head("/commons-media/inference-economy.mp4")
        deck = await client.head("/commons-media/inference-inversion.pptx")

    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert video.status_code == 200
    assert "video" in video.headers["content-type"]
    assert deck.status_code == 200


@pytest.mark.asyncio
async def test_public_benchmark_grading_daemon_route(tmp_path):
    rows = [
        {
            "source_path": "demo_governed.json",
            "task": "task_a",
            "lane_class": "governed",
            "lane": "live_full_beast",
            "provider": "demo",
            "model": "demo-model",
            "completed": True,
            "latency_ms": 50.0,
            "prompt": "task a",
            "output_text": '{"kind":"beast.action_intent.v1","actions":[{"id":"a1","type":"replace_anchor","target":{"path":"app/a.py","anchor_ref":"A1"},"intent":"fix task a","new":"return 2"}],"verify":["python -m pytest tests -q"]}',
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cost_usd": 0.03,
            "verification": {},
            "output_evidence": {},
        },
        {
            "source_path": "demo_baseline.json",
            "task": "task_b",
            "lane_class": "baseline",
            "lane": "live_raw",
            "provider": "demo",
            "model": "demo-model",
            "completed": False,
            "latency_ms": 70.0,
            "prompt": "task b",
            "output_text": "try changing the function maybe",
            "prompt_tokens": 9,
            "completion_tokens": 11,
            "total_tokens": 20,
            "cost_usd": 0.02,
            "verification": {},
            "output_evidence": {},
        },
    ]
    packet = {
        "generated_at": harness.utc_now(),
        "claim_status": "open_research_question",
        "claim_scope": "test",
        "row_count": len(rows),
        "rows": rows,
    }
    blind_info = harness.write_blind_grading(rows, tmp_path, seed=7)
    harness.write_grader_template(tmp_path)
    cost_info = harness.write_cost_accounting(rows, tmp_path)
    harness.write_summary(packet, blind_info, cost_info, tmp_path)
    harness.write_manifest(packet, blind_info, cost_info, tmp_path, [])

    async with _client() as client:
        response = await client.post("/edgek/benchmarks/public-grading-daemon", json={"packet_dir": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["claim_status"] == "supported"
    assert body["structural_claim_status"] == "supported"


@pytest.mark.asyncio
async def test_openai_models():
    async with _client() as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert "data" in response.json()


@pytest.mark.asyncio
async def test_crystal_reuse_gateway_endpoints():
    async with _client() as client:
        inventory = await client.get("/edgek/crystal-reuse")
        integrations = await client.get("/edgek/crystal-reuse/integrations")
        decision = await client.post(
            "/edgek/crystal-reuse/decide",
            json={"prompt": "hello reusable compute", "model": "local-test", "parameters": {"temperature": 0}},
        )
        export = await client.post(
            "/edgek/crystal-reuse/export",
            json={"prompt": "hello reusable compute", "model": "local-test", "parameters": {"temperature": 0}},
        )
        memory = await client.get("/edgek/memory-security")

    assert inventory.status_code == 200
    assert inventory.json()["beast_object_type"] == "crystal_reuse_gateway_inventory"
    assert integrations.status_code == 200
    assert integrations.json()["beast_object_type"] == "beast_local_capability_health"
    assert decision.status_code == 200
    assert decision.json()["action"] in {"execute_local_cpu", "reuse_answer", "reuse_semantic_credit", "reuse_kv_prefill"}
    assert export.status_code == 200
    assert export.json()["beast_object_type"] == "beast_local_capability_export_bundle"
    assert memory.status_code == 200
    assert memory.json()["beast_object_type"] == "beast_memory_security_state"


@pytest.mark.asyncio
async def test_openai_chat_completion():
    async with _client() as client:
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello, EdgeK BEAST!"}
            ],
            "max_tokens": 50,
        }
        response = await client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert "choices" in response.json()


@pytest.mark.asyncio
async def test_anthropic_message():
    async with _client() as client:
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": "Hello, EdgeK BEAST!"}
            ],
        }
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    assert "content" in response.json() or "error" in response.json()
