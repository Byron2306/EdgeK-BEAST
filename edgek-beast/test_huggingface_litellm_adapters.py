import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.deployment import DeploymentManager
from app.kernel.execute import Executor
from app.kernel.perceive import EdgeKIR, ProviderType
from app.kernel.runtime import runtime_governor
from app.main import app


def test_provider_type_supports_huggingface_tgi_and_litellm():
    assert ProviderType.HUGGINGFACE.value == "huggingface"
    assert ProviderType.TGI.value == "tgi"
    assert ProviderType.LITELLM.value == "litellm"


@pytest.mark.asyncio
async def test_huggingface_adapter_simulates_without_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/hf/v1/chat/completions",
            json={
                "model": "hf/openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "Say BEAST."}],
                "max_tokens": 8,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["edgek_provider"] == "huggingface"
    assert "SIMULATED" in body["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_litellm_adapter_simulates_when_upstream_missing(monkeypatch):
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:9/v1")
    runtime_governor.reset_circuit("litellm")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/litellm/v1/chat/completions",
            json={
                "model": "litellm/test-model",
                "messages": [{"role": "user", "content": "Say BEAST."}],
                "max_tokens": 8,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"]["provider"] == "litellm"


def test_executor_routes_provider_prefixes():
    executor = Executor()
    cases = {
        "hf/openai/gpt-oss-120b": ProviderType.HUGGINGFACE,
        "tgi/Qwen/Qwen2.5-3B-Instruct": ProviderType.TGI,
        "llamacpp/Qwen/Qwen2.5-3B-Instruct": ProviderType.TGI,
        "litellm/gpt-4o-mini": ProviderType.LITELLM,
        "gemini-2.5-flash": ProviderType.GEMINI,
    }
    for model, expected in cases.items():
        ir = EdgeKIR(messages=[{"role": "user", "content": "hi"}], model=model)
        assert executor._determine_provider_type(ir) == expected


def test_litellm_config_includes_hf_tgi_and_google():
    manager = DeploymentManager({
        "providers": {
            "google": {"enabled": True, "default_model": "gemini-2.5-flash"},
            "huggingface": {
                "enabled": True,
                "default_model": "openai/gpt-oss-120b",
                "base_url": "https://router.huggingface.co/v1",
            },
            "tgi": {
                "enabled": True,
                "default_model": "Qwen/Qwen2.5-3B-Instruct",
                "base_url": "http://127.0.0.1:3000",
            },
        },
        "meta_rules": {"runtime_provider_timeout_seconds": 120},
    })

    config = manager.generate_litellm_config(beast_base_url="http://127.0.0.1:8000")
    models = {entry["model_name"]: entry["litellm_params"] for entry in config["model_list"]}

    assert models["gemini-flash"]["model"] == "gemini/gemini-2.5-flash"
    assert models["huggingface"]["model"] == "huggingface/openai/gpt-oss-120b"
    assert models["tgi-llamacpp"]["api_base"] == "http://127.0.0.1:3000"
    assert "callbacks" not in config["litellm_settings"]
