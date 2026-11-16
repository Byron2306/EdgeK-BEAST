import asyncio
import threading

from app.kernel.agents.nim_planner_provider import NIMPlannerProvider


def test_late_request_completion_after_cancel_does_not_corrupt_loop():
    async def scenario():
        released = threading.Event()
        errors = []
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, context: errors.append(context))
        def request(_payload):
            released.wait(1)
            return {"content": "late result"}
        task = asyncio.create_task(NIMPlannerProvider._call_request(request, {}))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        released.set()
        await asyncio.sleep(0.05)
        assert not errors
    asyncio.run(scenario())


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


def test_nim_unwraps_structured_required_optional_argument_groups():
    raw = '{"decision_type":"tool","tool_id":"worktree.replace_exact","arguments":{"required":{"path":"a.py","old_text":"x","new_text":"y"},"optional":{"expected_occurrences":1}}}'
    normalized = NIMPlannerProvider._unwrap_argument_groups(raw)
    assert '"required"' not in normalized
    assert '"path":"a.py"' in normalized
    assert '"expected_occurrences":1' in normalized


def test_nim_planner_provider_can_add_legacy_guided_json(monkeypatch):
    monkeypatch.setenv("BEAST_NIM_GUIDED_JSON", "1")
    provider = NIMPlannerProvider(model="test", api_key="nvapi-test")
    payload = provider._request_payload("prompt", repair="", turn=1)
    assert payload["structured_outputs"]["json"] == provider.ACTION_SCHEMA
    assert payload["nvext"]["guided_json"] == provider.ACTION_SCHEMA
