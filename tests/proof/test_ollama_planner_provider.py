from __future__ import annotations

import asyncio
import pytest

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_provider import PlannerDecisionError


class _Context:
    context_id = "ctx-test"
    native_context_available = True


class _Manager:
    def __init__(self):
        self.calls = []
        self.contexts = {"ctx-test": _Context()}

    def get_or_create_context(self, *args, **kwargs):
        self.calls.append(("prefill", args, kwargs))
        return self.contexts["ctx-test"]

    def generate_with_context(self, block, prompt, *args, **kwargs):
        self.calls.append(("suffix", prompt, args, kwargs))
        return {"response": '{"decision_type":"tool","tool_id":"workspace.list","arguments":{}}', "prompt_eval_count": 3, "eval_count": 4}


class _WarmOnlyManager(_Manager):
    class Warm:
        context_id = "warm"
        native_context_available = False
    def get_or_create_context(self, *args, **kwargs):
        return self.Warm()


class _InvalidNativeManager(_Manager):
    def generate_with_context(self, block, prompt, *args, **kwargs):
        self.calls.append(("suffix", prompt, args, kwargs))
        return {"response": "not json", "prompt_eval_count": 3, "eval_count": 4}



def test_ollama_planner_default_predict_budget_supports_structured_edits(monkeypatch):
    monkeypatch.delenv("BEAST_OLLAMA_NUM_PREDICT", raising=False)
    provider = OllamaPlannerProvider(model="test")
    assert provider._num_predict() == 512


def test_ollama_planner_predict_budget_preserves_env_override(monkeypatch):
    monkeypatch.setenv("BEAST_OLLAMA_NUM_PREDICT", "256")
    provider = OllamaPlannerProvider(model="test")
    assert provider._num_predict() == 256



def test_ollama_provider_injects_run_scoped_approval(monkeypatch):
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        lambda self, path, payload, timeout: {"models": [{"name": "test"}]},
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        lambda self, path, payload, timeout: {
            "response": '{"decision_type":"tool","tool_id":"worktree.bind","arguments":{"objective":"x"}}'
        },
    )
    provider = OllamaPlannerProvider(model="test", default_approval_id="approved-once")
    decision = asyncio.run(provider.next_decision("prompt", run={}, turn=1))
    assert decision.tool_id == "worktree.bind"
    assert decision.approval_id == "approved-once"


def test_native_prompt_split_keeps_contract_stable():
    stable, suffix = OllamaPlannerProvider._split_native_planner_prompt("CONTRACT\nOBJECTIVE: x\nTURN: 2/8\nOBSERVATIONS: []")
    assert stable == "CONTRACT\nOBJECTIVE: x"
    assert suffix == "TURN: 2/8\nOBSERVATIONS: []"


def test_native_planner_path_sends_only_turn_suffix():
    manager = _Manager()
    provider = OllamaPlannerProvider(model="test", forge_kv_manager=manager)
    provider._request_json = lambda path, payload, timeout: {"models": [{"name": "test"}]}
    decision = asyncio.run(provider.next_decision("CONTRACT\nOBJECTIVE: x\nTURN: 2/8\nOBSERVATIONS: []", run={}, turn=2))
    assert decision.tool_id == "workspace.list"
    assert manager.calls[1][0] == "suffix"
    assert manager.calls[1][1] == "TURN: 2/8\nOBSERVATIONS: []"
    assert provider.last_usage["forge_kv"]["suffix_only"] is True


def test_warm_model_does_not_receive_suffix_only():
    provider = OllamaPlannerProvider(model="test", forge_kv_manager=_WarmOnlyManager(), timeout_seconds=10, max_retries=0)
    provider._request_json = lambda path, payload, timeout: {"models": [{"name": "test"}]}
    provider._request_stream_json = lambda path, payload, timeout: {
        "response": '{"decision_type":"complete","summary":"fallback"}'
    }
    decision = asyncio.run(provider.next_decision("CONTRACT\nTURN: 2/8", run={}, turn=2))
    assert decision.summary == "fallback"


def test_invalid_native_context_falls_back_to_direct_generate():
    manager = _InvalidNativeManager()
    provider = OllamaPlannerProvider(model="test", forge_kv_manager=manager, timeout_seconds=10, max_retries=0)
    provider._request_json = lambda path, payload, timeout: {"models": [{"name": "test"}]}
    provider._request_stream_json = lambda path, payload, timeout: {
        "response": '{"decision_type":"complete","summary":"direct generate"}'
    }
    decision = asyncio.run(provider.next_decision("CONTRACT\nTURN: 2/8", run={}, turn=2))
    assert decision.summary == "direct generate"
    assert provider.last_route["route_kind"] == "direct_generate"


def test_direct_generate_uses_stream_transport_when_payload_streams(monkeypatch):
    calls = []

    def stream_json(self, path, payload, timeout):
        calls.append(("stream", path, payload.get("stream")))
        return {
            "response": (
                '{"decision_type":"tool",'
                '"tool_id":"worktree.replace_exact",'
                '"arguments":{'
                '"path":"calculator.py",'
                '"old_text":"return sum(values) / len(values)",'
                '"new_text":"return sum(values) / len(values) if values else 0.0"'
                '}}'
            ),
            "prompt_eval_count": 20,
            "eval_count": 30,
            "done": True,
        }

    def request_json(self, path, payload, timeout):
        if path == "/api/tags":
            return {
                "models": [
                    {"name": "test"}
                ]
            }
        raise AssertionError(
            "_request_json must not consume stream=True NDJSON"
        )

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        stream_json,
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        request_json,
    )

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=0,
        on_token=lambda token: None,
    )

    decision = asyncio.run(
        provider.next_decision(
            "CONTRACT\nTURN: 4/16",
            run={"mode": "agent"},
            turn=4,
        )
    )

    assert calls == [
        ("stream", "/api/generate", True),
    ]
    assert decision.tool_id == "worktree.replace_exact"
    assert decision.arguments["path"] == "calculator.py"
    assert provider.last_route["route_kind"] == "direct_generate"


def test_explicit_recovery_uses_single_attempt_and_recovery_timeout(monkeypatch):
    calls = []

    def request_json(self, path, payload, timeout):
        if path == "/api/tags":
            return {"models": [{"name": "test"}]}
        raise AssertionError(f"unexpected request: {path}")

    def stream_json(self, path, payload, timeout):
        calls.append((path, timeout))
        raise OSError("simulated provider failure")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        request_json,
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        stream_json,
    )
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=2,
    )

    with pytest.raises(PlannerDecisionError):
        asyncio.run(
            provider.next_decision(
                "CONTRACT\nTURN: 4/16",
                run={
                    "mode": "agent",
                    "_beast_recovery_timeout_seconds": 28.0,
                },
                turn=4,
            )
        )

    assert calls == [
        ("/api/generate", 28.0),
    ]


def test_normal_planner_mode_preserves_internal_retries(monkeypatch):
    calls = []

    def request_json(self, path, payload, timeout):
        if path == "/api/tags":
            return {"models": [{"name": "test"}]}
        raise AssertionError(f"unexpected request: {path}")

    def stream_json(self, path, payload, timeout):
        calls.append((path, timeout))
        raise OSError("simulated provider failure")

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        request_json,
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        stream_json,
    )
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=2,
    )

    with pytest.raises(PlannerDecisionError):
        asyncio.run(
            provider.next_decision(
                "CONTRACT\nTURN: 1/16",
                run={"mode": "agent"},
                turn=1,
            )
        )

    assert len(calls) == 3


def test_explicit_recovery_timeout_overrides_followup_timeout():
    timeout = OllamaPlannerProvider._request_timeout(
        "prompt",
        run={
            "mode": "agent",
            "_beast_recovery_timeout_seconds": 28.0,
            "checkpoint": {
                "planner": {
                    "observations": [
                        {
                            "tool_id": "workspace.read_range",
                            "status": "completed",
                        }
                    ]
                }
            },
        },
        turn=4,
    )

    assert timeout == 28.0


def test_explicit_recovery_bypasses_native_context_and_execution_gateway(monkeypatch):
    class ExplodingKV:
        def get_or_create_context(self, *args, **kwargs):
            raise AssertionError("recovery must not use Forge-KV")

    class ExplodingGateway:
        def complete(self, request):
            raise AssertionError("recovery must not use execution gateway")

    def request_json(self, path, payload, timeout):
        if path == "/api/tags":
            return {"models": [{"name": "test"}]}
        raise AssertionError(f"unexpected request: {path}")

    def stream_json(self, path, payload, timeout):
        assert path == "/api/generate"
        assert timeout == 28.0
        return {
            "response": (
                '{"decision_type":"tool",'
                '"tool_id":"worktree.replace_exact",'
                '"arguments":{"path":"calculator.py",'
                '"old_text":"return sum(values) / len(values)",'
                '"new_text":"return sum(values) / len(values) if values else 0.0"}}'
            ),
            "done": True,
        }

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        request_json,
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        stream_json,
    )

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=2,
        forge_kv_manager=ExplodingKV(),
        execution_gateway=ExplodingGateway(),
    )

    decision = asyncio.run(
        provider.next_decision(
            "CONTRACT\nTURN: 4/16",
            run={
                "mode": "agent",
                "_beast_recovery_timeout_seconds": 28.0,
            },
            turn=4,
        )
    )

    assert decision.tool_id == "worktree.replace_exact"


def test_first_mutation_recovery_salvages_triple_quoted_residual(monkeypatch):
    raw = r'''```json
{
  "decision_type": "tool",
  "tool_id": "worktree.replace_exact",
  "arguments": {
    "new_text": """
def safe_average(values):
    \"\"\"Return the arithmetic mean, or 0.0 for an empty iterable.\"\"\"
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
"""
  }
}
```'''

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        lambda self, path, payload, timeout: {
            "models": [{"name": "test"}]
        },
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        lambda self, path, payload, timeout: {
            "response": raw
        },
    )

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=0,
    )

    decision = asyncio.run(
        provider.next_decision(
            "FIRST MUTATION REQUIRED: residual only",
            run={
                "mode": "agent",
                "_beast_recovery_timeout_seconds": 28.0,
            },
            turn=4,
        )
    )

    assert decision.tool_id == "worktree.replace_exact"
    assert set(decision.arguments) == {"new_text"}
    assert "if not values:" in decision.arguments["new_text"]
    assert provider.last_usage["residual_salvage"]["kind"] == \
        "triple_quoted_new_text"


def test_triple_quoted_residual_salvage_is_scoped_to_mutation_recovery(monkeypatch):
    raw = r'''```json
{
  "decision_type": "tool",
  "tool_id": "worktree.replace_exact",
  "arguments": {
    "new_text": """
VALUE = 2
"""
  }
}
```'''

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        lambda self, path, payload, timeout: {
            "models": [{"name": "test"}]
        },
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        lambda self, path, payload, timeout: {
            "response": raw
        },
    )

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=0,
    )

    with pytest.raises(PlannerDecisionError):
        asyncio.run(
            provider.next_decision(
                "CONTRACT\nTURN: 2/8",
                run={
                    "mode": "agent",
                    "_beast_recovery_timeout_seconds": 28.0,
                },
                turn=2,
            )
        )


def test_first_mutation_salvage_decodes_json_style_escapes(monkeypatch):
    raw = r'''```json
{
  "decision_type": "tool",
  "tool_id": "worktree.replace_exact",
  "arguments": {
    "new_text": """
def safe_average(values):
    \"\"\"Return the arithmetic mean, or 0.0 for an empty iterable.\"\"\"\n    values = list(values)
    return sum(values) / len(values)
"""
  }
}
```'''

    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        lambda self, path, payload, timeout: {
            "models": [{"name": "test"}]
        },
    )
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_stream_json",
        lambda self, path, payload, timeout: {
            "response": raw
        },
    )

    provider = OllamaPlannerProvider(
        model="test",
        max_retries=0,
    )

    decision = asyncio.run(
        provider.next_decision(
            "FIRST MUTATION REQUIRED: residual only",
            run={
                "mode": "agent",
                "_beast_recovery_timeout_seconds": 28.0,
            },
            turn=4,
        )
    )

    text = decision.arguments["new_text"]

    assert '\\"' not in text
    assert "\\n" not in text
    assert '"""Return the arithmetic mean' in text
    assert "\n    values = list(values)" in text
