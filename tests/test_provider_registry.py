import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.registry.provider_registry import ProviderRegistry
from app.kernel.adapters.provider_adapters import ProviderAdapterRegistry
from app.cli.api import BeastApiClient
from app.main import app


def test_provider_registry_inventory_defines_gateway_lanes():
    inventory = ProviderRegistry().inventory()

    assert inventory["beast_object_type"] == "provider_registry"
    assert inventory["governance"]["beast_in_front_of_litellm"] is True
    assert "native_anthropic" in inventory["backend_classes"]
    assert "native_replicate" in inventory["backend_classes"]
    assert "openai_compatible" in inventory["backend_classes"]
    assert "litellm" in inventory["backend_classes"]
    assert "ollama" in inventory["backend_classes"]
    assert inventory["governance"]["provider_explicit_lane"].startswith("/proxy/<provider>")


def test_provider_registry_policy_overrides_defaults():
    registry = ProviderRegistry(
        {
            "providers": {
                "openrouter": {
                    "enabled": True,
                    "backend": "litellm",
                    "env": "OPENROUTER_TOKEN",
                    "default_model": "openrouter/meta-llama/llama-3.1-8b-instruct",
                    "risk_level": "high",
                },
                "custom_openai_lane": {
                    "enabled": True,
                    "backend": "openai",
                    "env": ["CUSTOM_OPENAI_KEY"],
                    "base_url": "https://example.invalid/v1",
                    "proxy_path": "/proxy/custom-openai",
                },
            }
        }
    )

    records = {record.provider_id: record for record in registry.records()}

    assert records["openrouter"].backend == "litellm"
    assert records["openrouter"].env == ["OPENROUTER_TOKEN"]
    assert records["openrouter"].proxy_path == "/proxy/openrouter"
    assert records["openrouter"].risk_level == "high"
    assert records["custom_openai_lane"].backend == "openai_compatible"
    assert records["custom_openai_lane"].openai_compatible is True
    assert records["custom_openai_lane"].proxy_path == "/proxy/custom-openai"


def test_provider_adapter_registry_assigns_dedicated_adapter_classes():
    inventory = ProviderAdapterRegistry({
        "providers": {
            "openrouter": {"enabled": True, "backend": "litellm", "default_model": "openrouter/auto"},
            "nvidia_nim": {
                "enabled": True,
                "backend": "openai_compatible",
                "base_url": "https://integrate.api.nvidia.com/v1",
                "default_model": "meta/llama",
            },
            "ollama": {"enabled": True, "backend": "ollama", "default_model": "llama3.2:3b"},
        }
    }).inventory()
    adapters = {item["provider_id"]: item for item in inventory["adapters"]}

    assert adapters["openrouter"]["adapter_class"] == "litellm"
    assert adapters["openrouter"]["route_provider"] == "litellm"
    assert ProviderAdapterRegistry({
        "providers": {
            "litellm": {
                "enabled": True,
                "backend": "litellm",
                "litellm_model_prefix": "openai/",
                "default_model": "gpt-3.5-turbo",
            }
        }
    }).adapter_for("litellm").plan_chat("ollama").model == "litellm/ollama"
    assert adapters["nvidia_nim"]["adapter_class"] == "openai_compatible"
    assert adapters["nvidia_nim"]["route_provider"] == "openai_compatible"
    assert ProviderAdapterRegistry({
        "providers": {
            "nvidia_nim": {
                "enabled": True,
                "backend": "openai_compatible",
                "base_url": "https://integrate.api.nvidia.com/v1",
                "default_model": "nvidia/nemotron-3-super-120b-a12b",
            }
        }
    }).adapter_for("nvidia_nim").plan_chat("beast-auto").model == "nvidia/nemotron-3-super-120b-a12b"
    assert adapters["ollama"]["adapter_class"] == "ollama"


def test_xai_and_replicate_have_distinct_route_contracts():
    records = {record.provider_id: record for record in ProviderRegistry().records()}

    assert records["xai"].backend == "openai_compatible"
    assert records["xai"].base_url == "https://api.x.ai/v1"
    assert records["xai"].default_model == "grok-build-0.1"
    assert records["replicate"].backend == "native_replicate"
    assert records["replicate"].openai_compatible is False

    adapters = ProviderAdapterRegistry()
    xai = adapters.adapter_for("xai").plan_chat("beast-auto")
    replicate = adapters.adapter_for("replicate").plan_chat("beast-auto")
    assert xai.route_provider == "openai_compatible"
    assert replicate.adapter_class == "native_replicate"
    assert replicate.route_provider == "replicate_prediction"


def test_codex_and_beast_auto_have_concrete_provider_contracts():
    records = {record.provider_id: record for record in ProviderRegistry().records()}

    assert records["codex"].backend == "openai_compatible"
    assert records["codex"].default_model == "gpt-5-codex"
    assert records["codex"].env == ["OPENAI_API_KEY"]

    adapters = ProviderAdapterRegistry()
    expected_models = {
        "codex": "gpt-5-codex",
        "openai": "gpt-4o-mini",
        "litellm": "litellm/ollama",
        "openrouter": "litellm/openrouter/auto",
        "nvidia_nim": "nvidia/nemotron-3-super-120b-a12b",
        "local_nim": "local-nim-model",
        "ollama": "llama3.2:3b",
    }
    for provider_id, expected_model in expected_models.items():
        plan = adapters.adapter_for(provider_id).plan_chat("beast-auto")
        assert plan.model == expected_model
        assert plan.provider_id == provider_id
        assert plan.governed_by_beast is True


def test_tui_chat_model_mapper_uses_provider_contracts():
    api = BeastApiClient()

    assert api._chat_model_for_provider("", "beast-auto") == "nvidia/nemotron-3-super-120b-a12b"
    assert api._chat_model_for_provider("auto", "beast-auto") == "nvidia/nemotron-3-super-120b-a12b"
    assert api._chat_model_for_provider("codex", "beast-auto") == "gpt-5-codex"
    assert api._chat_model_for_provider("openai", "beast-auto") == "gpt-4o-mini"
    assert api._chat_model_for_provider("openrouter", "beast-auto") == "litellm/openrouter/auto"
    assert api._chat_model_for_provider("nvidia-nim", "beast-auto") == "nvidia/nemotron-3-super-120b-a12b"
    assert api._chat_model_for_provider("local-nim", "beast-auto") == "local-nim-model"
    assert api._chat_model_for_provider("litellm", "beast-auto") == "litellm/ollama"


@pytest.mark.asyncio
async def test_provider_registry_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/edgek/providers/registry")
        adapters = await client.get("/edgek/providers/adapters")
        telemetry = await client.get("/edgek/telemetry/http")
        runtime_metrics = await client.get("/edgek/runtime/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["beast_object_type"] == "provider_registry"
    assert body["governance"]["litellm_role"] == "managed_backend_lane"
    assert any(provider["provider_id"] == "ollama" for provider in body["providers"])
    assert adapters.status_code == 200
    assert adapters.json()["beast_object_type"] == "provider_adapter_inventory"
    assert telemetry.status_code == 200
    assert "latency_ms" in telemetry.json()
    assert runtime_metrics.status_code == 200
    assert "provider_counts" in runtime_metrics.json()
