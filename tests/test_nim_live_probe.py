import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe
from app.main import app


class NoopVault:
    def load(self, override=False):
        return {"loaded": 0, "skipped_existing": 0}


def test_nim_live_probe_reports_missing_secret(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    receipt = NvidiaNIMLiveProbe(secret_vault=NoopVault()).run(discover_models=False)

    assert receipt["status"] == "missing_secret"
    assert receipt["secret"]["present"] is False


def test_nim_live_probe_discovers_model_and_completes(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-value")

    def handler(request):
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "nvidia/embed-qa"},
                        {"id": "meta/llama-3.1-8b-instruct"},
                    ]
                },
            )
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "BEAST_NIM_LIVE_OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    receipt = NvidiaNIMLiveProbe(secret_vault=NoopVault(), client=client).run(
        requested_model="meta/llama-3.1-8b-instruct",
        discover_models=True,
    )

    assert receipt["status"] == "ok"
    assert receipt["model"] == "meta/llama-3.1-8b-instruct"
    assert receipt["response_preview"] == "BEAST_NIM_LIVE_OK"
    assert receipt["secret"]["fingerprint"]
    assert "nvapi-test-key-value" not in str(receipt)


def test_nim_live_probe_stops_on_auth_failure(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-value")

    def handler(request):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    receipt = NvidiaNIMLiveProbe(secret_vault=NoopVault(), client=client).run(discover_models=False)

    assert receipt["status"] == "auth_failed"
    assert receipt["attempted_models"][0]["status_code"] == 401


@pytest.mark.asyncio
async def test_nim_live_smoke_endpoint_can_crystallize(monkeypatch):
    def fake_run(**kwargs):
        return {
            "beast_object_type": "nvidia_nim_live_probe_receipt",
            "status": "ok",
            "model": "meta/llama-3.1-8b-instruct",
            "response_preview": "BEAST_NIM_LIVE_OK",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            "latency_ms": 9.5,
            "receipt_hash": "sha256:test-nim-crystal",
        }

    monkeypatch.setattr("app.main.nim_live_probe.run", fake_run)
    prompt = "Return exactly: BEAST_NIM_LIVE_OK endpoint crystal regression"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/providers/nvidia-nim/live-smoke",
            json={
                "confirm_live": True,
                "crystallize": True,
                "prompt": prompt,
                "task_class": "nim_endpoint_crystallize_test",
                "repo_fingerprint": "repo-nim-endpoint-test",
                "max_tokens": 8,
            },
        )
        decision = await client.post(
            "/edgek/crystal-reuse/decide",
            json={
                "prompt": prompt,
                "model": "meta/llama-3.1-8b-instruct",
                "task_class": "nim_endpoint_crystallize_test",
                "repo_fingerprint": "repo-nim-endpoint-test",
                "parameters": {"max_tokens": 8},
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["crystal_record"]["semantic_credit_id"].startswith("scc_")
    assert payload["crystal_record"]["local_route_optimizer"]["engine_id"] == "meta/llama-3.1-8b-instruct"
    assert decision.json()["action"] in {"reuse_answer", "reuse_semantic_credit"}
