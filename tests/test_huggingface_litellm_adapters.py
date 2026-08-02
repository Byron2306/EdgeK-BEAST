import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.deployment.deployment import DeploymentManager
from app.kernel.execution.execute import Executor
from app.kernel.compute.perceive import EdgeKIR, ProviderType
from app.kernel.governance.runtime import runtime_governor
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


@pytest.mark.asyncio
async def test_registry_proxy_routes_litellm_managed_provider(monkeypatch):
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:9/v1")
    runtime_governor.reset_circuit("litellm")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/proxy/openrouter/v1/chat/completions",
            json={
                "model": "openrouter/auto",
                "messages": [{"role": "user", "content": "Say BEAST."}],
                "max_tokens": 8,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"]["provider"] == "litellm"


@pytest.mark.asyncio
async def test_proxy_v1_compatibility_lane_accepts_provider_header(monkeypatch):
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:9/v1")
    runtime_governor.reset_circuit("litellm")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/proxy/v1/chat/completions",
            headers={"X-EdgeK-Provider": "groq"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "Say BEAST."}],
                "max_tokens": 8,
            },
        )

    assert response.status_code == 200
    assert response.json()["error"]["provider"] == "litellm"


@pytest.mark.asyncio
async def test_registry_proxy_routes_openai_compatible_provider_without_litellm(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/proxy/nvidia-nim/v1/chat/completions",
            json={
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "messages": [{"role": "user", "content": "Say BEAST."}],
                "max_tokens": 8,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["edgek_provider"] == "nvidia_nim"
    assert "SIMULATED" in body["choices"][0]["message"]["content"]


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


def test_executor_honors_ollama_backend_marker_when_route_metadata_is_minimized():
    executor = Executor()
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "hi"}],
        model="qwen2.5-coder:1.5b",
        # This is the durable marker injected by the registry proxy before
        # policy transformations; no OpenAI fallback is allowed here.
        metadata={"edgek_provider_backend": "ollama", "provider": "openai"},
    )

    assert executor._determine_provider_type(ir) == ProviderType.OLLAMA


def test_pair_programmer_ollama_context_plan_reuses_only_stable_system_context(monkeypatch):
    monkeypatch.delenv("BEAST_OLLAMA_NATIVE_CONTEXT_REUSE", raising=False)
    executor = Executor()
    ir = EdgeKIR(
        messages=[
            {"role": "system", "content": "Selected source: def target(): pass"},
            {"role": "assistant", "content": "I am ready."},
            {"role": "user", "content": "Add a regression test."},
        ],
        model="qwen2.5-coder:1.5b",
        metadata={"edgek_surface": "beast_tui_live_session_stream"},
    )

    plan = executor._ollama_pair_context_plan(ir, ir.model)

    assert plan is not None
    assert plan["prefix"] == "Selected source: def target(): pass"
    assert "system:" not in plan["continuation"]
    assert "Add a regression test." in plan["continuation"]


@pytest.mark.asyncio
async def test_executor_routes_nvidia_nim_through_its_registry_lane(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = Executor()
    ir = EdgeKIR(
        messages=[{"role": "user", "content": "hi"}],
        model="meta/llama-3.1-70b-instruct",
        metadata={"provider": "nvidia_nim", "route_provider": "nvidia_nim"},
    )

    assert executor._determine_provider_type(ir) == ProviderType.OPENAI_COMPATIBLE
    response = await executor._route_to_provider(ProviderType.OPENAI_COMPATIBLE, ir)
    assert response["edgek_provider"] == "nvidia_nim"
    assert "OPENAI_API_KEY" not in response["choices"][0]["message"]["content"]


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
