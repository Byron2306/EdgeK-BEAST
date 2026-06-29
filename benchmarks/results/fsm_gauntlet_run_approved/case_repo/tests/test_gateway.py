import pytest

from gateway.config import normalize_provider_id, provider_config
from gateway.redaction import redact_config
from gateway.router import resolve_model
from gateway.streaming import collect_stream


def test_provider_ids_normalize_hyphen_space_and_case():
    assert normalize_provider_id("NVIDIA-NIM") == "nvidia_nim"
    assert normalize_provider_id("Open AI") == "open_ai"


def test_provider_config_never_leaks_raw_api_key():
    env = {"NVIDIA_NIM_API_KEY": "super-secret"}
    config = provider_config("NVIDIA-NIM", env)
    assert config["provider"] == "nvidia_nim"
    assert config["api_key_present"] is True
    assert "api_key" not in config
    assert "super-secret" not in str(config)


def test_beast_auto_resolves_concrete_model_after_normalization():
    assert resolve_model("NVIDIA-NIM", "beast-auto") == "meta/llama-3.1-70b-instruct"


@pytest.mark.asyncio
async def test_empty_stream_chunks_do_not_terminate_collection():
    async def chunks():
        for item in ["alpha", "", "beta", None, "ignored"]:
            yield item
    assert await collect_stream(chunks()) == "alphabeta"


def test_redaction_is_recursive_for_sensitive_keys():
    config = {
        "provider": "nvidia_nim",
        "nested": {"token": "abc", "headers": {"Authorization": "Bearer nope"}},
        "safe": "ok",
    }
    redacted = redact_config(config)
    assert redacted["safe"] == "ok"
    assert redacted["nested"]["token"] == "***REDACTED***"
    assert redacted["nested"]["headers"]["Authorization"] == "***REDACTED***"
    assert "abc" not in str(redacted)
    assert "Bearer nope" not in str(redacted)
