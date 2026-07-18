import pytest

from app.kernel.compute.inference_engine_fabric import InferenceEngineFabric


def test_cpu_selector_uses_configured_low_latency_default(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llama.test")
    fabric = InferenceEngineFabric()
    assert fabric.select_cpu_engine("code_completion", "llama-3", 900, 16_000) == "ollama"


def test_cpu_selector_prefers_llama_cpp_for_long_context_llama_work(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llama.test")
    fabric = InferenceEngineFabric()
    assert fabric.select_cpu_engine("code_completion", "llama-3", 5_000, 16_000) == "llama_cpp"


def test_cpu_selector_fails_closed_without_configured_candidate(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
    # Ollama has a deliberate local default, so override the catalogue endpoint
    # mapping for this isolated no-engine policy test.
    monkeypatch.setattr(InferenceEngineFabric, "ENV_ENDPOINTS", {**InferenceEngineFabric.ENV_ENDPOINTS, "ollama": ("OLLAMA_BASE_URL", "")})
    with pytest.raises(ValueError, match="no configured CPU"):
        InferenceEngineFabric().select_cpu_engine("general", "", 5_000, 1)
