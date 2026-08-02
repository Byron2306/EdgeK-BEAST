from __future__ import annotations

import asyncio

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider


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


def test_ollama_provider_injects_run_scoped_approval(monkeypatch):
    monkeypatch.setattr(
        OllamaPlannerProvider,
        "_request_json",
        lambda self, path, payload, timeout: {"response": '{"decision_type":"tool","tool_id":"worktree.bind","arguments":{"objective":"x"}}'},
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
    decision = asyncio.run(provider.next_decision("CONTRACT\nOBJECTIVE: x\nTURN: 2/8\nOBSERVATIONS: []", run={}, turn=2))
    assert decision.tool_id == "workspace.list"
    assert manager.calls[1][0] == "suffix"
    assert manager.calls[1][1] == "TURN: 2/8\nOBSERVATIONS: []"
    assert provider.last_usage["forge_kv"]["suffix_only"] is True


def test_warm_model_does_not_receive_suffix_only():
    provider = OllamaPlannerProvider(model="test", forge_kv_manager=_WarmOnlyManager(), timeout_seconds=10, max_retries=0)
    provider._request_json = lambda path, payload, timeout: {"response": '{"decision_type":"complete","summary":"fallback"}'}
    decision = asyncio.run(provider.next_decision("CONTRACT\nTURN: 2/8", run={}, turn=2))
    assert decision.summary == "fallback"


def test_invalid_native_context_falls_back_to_direct_generate():
    manager = _InvalidNativeManager()
    provider = OllamaPlannerProvider(model="test", forge_kv_manager=manager, timeout_seconds=10, max_retries=0)
    provider._request_json = lambda path, payload, timeout: {"response": '{"decision_type":"complete","summary":"direct generate"}'}
    decision = asyncio.run(provider.next_decision("CONTRACT\nTURN: 2/8", run={}, turn=2))
    assert decision.summary == "direct generate"
    assert provider.last_route["route_kind"] == "direct_generate"
