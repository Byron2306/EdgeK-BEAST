from __future__ import annotations

import os

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.routes.agent_runs import _ollama_base_url
from app.routes.ide_routes.agent_runs import _ollama_base_url as _ide_ollama_base_url


def test_provider_normalizes_openai_compatible_suffixes() -> None:
    assert OllamaPlannerProvider(base_url="http://127.0.0.1:11434/v1").base_url == "http://127.0.0.1:11434"
    assert (
        OllamaPlannerProvider(
            base_url="http://127.0.0.1:11434/v1/chat/completions"
        ).base_url
        == "http://127.0.0.1:11434"
    )


def test_provider_normalizes_native_endpoint_suffixes() -> None:
    assert OllamaPlannerProvider(base_url="127.0.0.1:11434/api/generate").base_url == "http://127.0.0.1:11434"
    assert OllamaPlannerProvider(base_url="http://127.0.0.1:11434/api").base_url == "http://127.0.0.1:11434"


def test_agent_run_prefers_request_scoped_ollama_url(monkeypatch) -> None:
    monkeypatch.setenv("BEAST_OLLAMA_BASE_URL", "http://environment.invalid:9999")
    run = {"request": {"ollama_base_url": "http://127.0.0.1:11434/v1"}}
    assert _ollama_base_url(run) == "http://127.0.0.1:11434/v1"


def test_ide_agent_run_prefers_request_scoped_ollama_url(monkeypatch) -> None:
    monkeypatch.setenv("BEAST_OLLAMA_BASE_URL", "http://environment.invalid:9999")
    run = {"request": {"ollama_base_url": "http://127.0.0.1:11434/v1"}}
    assert _ide_ollama_base_url(run) == "http://127.0.0.1:11434/v1"


def test_agent_run_uses_beast_specific_environment_before_ollama_host(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://nginx.invalid:8000/v1")
    monkeypatch.setenv("BEAST_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    assert _ollama_base_url({"request": {}}) == "http://127.0.0.1:11434"


def test_planner_uses_live_small_model_default(monkeypatch) -> None:
    monkeypatch.delenv("BEAST_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert OllamaPlannerProvider().model == "qwen2.5:0.5b"


def test_planner_preflight_has_missing_model_guidance() -> None:
    names = OllamaPlannerProvider._preflight.__code__.co_names
    constants = " ".join(str(item) for item in OllamaPlannerProvider._preflight.__code__.co_consts)
    assert "_request_json" in names
    assert "/api/tags" in constants
    assert "not installed" in constants
    assert "ollama pull" in constants
