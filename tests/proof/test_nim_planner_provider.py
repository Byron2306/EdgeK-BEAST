import asyncio

from app.kernel.agents.nim_planner_provider import NIMPlannerProvider


def test_nim_planner_provider_parses_streamed_action(monkeypatch):
    tokens = []
    monkeypatch.setenv("BEAST_NIM_PLANNER_STREAM", "1")
    provider = NIMPlannerProvider(model="test", api_key="nvapi-test", on_token=tokens.append)
    monkeypatch.setattr(
        provider,
        "_request_stream",
        lambda payload: {
            "content": '{"decision_type":"tool","tool_id":"workspace.list","arguments":{}}',
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
            "finish_reason": "stop",
        },
    )
    decision = asyncio.run(provider.next_decision("prompt", run={}, turn=1))
    assert decision.tool_id == "workspace.list"
    assert provider.last_usage["engine"] == "nvidia_nim"


def test_nim_planner_provider_requires_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    provider = NIMPlannerProvider(model="test", api_key="")
    try:
        asyncio.run(provider.next_decision("prompt", run={}, turn=1))
    except RuntimeError as exc:
        assert "NVIDIA_API_KEY" in str(exc)
    else:
        raise AssertionError("NIM planner accepted a request without an API key")


def test_control_plane_defaults_to_fast_instruct_model(monkeypatch):
    monkeypatch.delenv("BEAST_NIM_MODEL", raising=False)
    provider = NIMPlannerProvider(api_key="nvapi-test")
    assert provider.model == "meta/llama-3.2-1b-instruct"


def test_nim_planner_provider_requests_structured_outputs_by_default(monkeypatch):
    monkeypatch.delenv("BEAST_NIM_STRUCTURED_OUTPUTS", raising=False)
    monkeypatch.delenv("BEAST_NIM_GUIDED_JSON", raising=False)
    provider = NIMPlannerProvider(model="test", api_key="nvapi-test")
    payload = provider._request_payload("prompt", repair="", turn=1)
    assert payload["structured_outputs"]["json"] == provider.ACTION_SCHEMA
    assert "nvext" not in payload


def test_nim_planner_provider_can_add_legacy_guided_json(monkeypatch):
    monkeypatch.setenv("BEAST_NIM_GUIDED_JSON", "1")
    provider = NIMPlannerProvider(model="test", api_key="nvapi-test")
    payload = provider._request_payload("prompt", repair="", turn=1)
    assert payload["structured_outputs"]["json"] == provider.ACTION_SCHEMA
    assert payload["nvext"]["guided_json"] == provider.ACTION_SCHEMA
