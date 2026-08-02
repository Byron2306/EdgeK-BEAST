from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app.kernel.compute.forge_kv_coordinator import ForgeKVCoordinator, ForgeKVRequest
from app.kernel.local.ollama_kv_manager import OllamaKVManager


class Response:
    status_code = 200
    def __init__(self, body): self._body = body
    def raise_for_status(self): return None
    def json(self): return dict(self._body)


class ScriptedClient:
    def __init__(self, responses, delay=0.0):
        self.responses = list(responses)
        self.requests = []
        self.delay = delay
        self.lock = threading.Lock()
    def post(self, url, json, timeout):
        if self.delay: time.sleep(self.delay)
        with self.lock:
            self.requests.append((url, dict(json)))
            if not self.responses:
                raise AssertionError("unexpected request")
            return Response(self.responses.pop(0))
    def close(self): pass


def request(**overrides):
    values = dict(
        task_class="repo_summary", model="qwen2.5:0.5b", prompt="continue",
        prompt_prefix="stable repo map", system_prompt="BEAST governance",
        model_digest="sha256:" + "1" * 64, tokenizer_hint="qwen2.5",
        template="template-v1", options={"num_ctx": 4096, "temperature": 0},
        workspace_id="edgek-beast", privacy_domain="workspace:edgek-beast",
        mission_id="mission-1", max_tokens=32,
    )
    values.update(overrides)
    return ForgeKVRequest(**values)


def test_native_context_reuse_is_measured_and_context_only():
    client = ScriptedClient([
        {"context": [1, 2, 3], "prompt_eval_count": 10, "prompt_eval_duration": 2_000_000},
        {"response": "ok", "context": [1, 2, 3, 4], "prompt_eval_count": 1,
         "prompt_eval_duration": 100_000, "eval_count": 2, "eval_duration": 50_000},
    ])
    manager = OllamaKVManager(client=client, max_contexts=4)
    events = []
    coordinator = ForgeKVCoordinator(manager, workers=1, event_sink=lambda t, p, r: events.append((t, p)))
    try:
        result = coordinator.run(request())
    finally:
        coordinator.close(); manager.close()
    assert result["authority"] == "context_only"
    assert result["speculative_prefill"] is False
    assert result["inference"]["reuse_mode"] == "native_context"
    assert result["inference"]["native_context_supplied"] is True
    assert result["economics"]["prompt_eval_count"] == 1
    assert result["context"]["portable_raw_kv"] is False
    assert any(name == "forge.kv_inference_completed" for name, _ in events)
    assert "prompt" not in result["economics"]


def test_no_context_is_warm_model_not_fake_native_reuse():
    client = ScriptedClient([
        {"prompt_eval_count": 10, "prompt_eval_duration": 2_000_000},
        {"response": "ok", "prompt_eval_count": 10, "prompt_eval_duration": 2_100_000, "eval_count": 2},
    ])
    manager = OllamaKVManager(client=client)
    coordinator = ForgeKVCoordinator(manager, workers=1)
    try:
        result = coordinator.run(request())
    finally:
        coordinator.close(); manager.close()
    assert result["inference"]["reuse_mode"] == "warm_model"
    assert result["inference"]["native_context_supplied"] is False
    assert result["context"]["native_context_available"] is False


def test_compatibility_identity_separates_workspace_privacy_and_num_ctx():
    responses = []
    for token in (11, 12, 13):
        responses += [
            {"context": [token], "prompt_eval_count": 5},
            {"response": "ok", "context": [token, token], "prompt_eval_count": 1},
        ]
    client = ScriptedClient(responses)
    manager = OllamaKVManager(client=client)
    coordinator = ForgeKVCoordinator(manager, workers=1)
    try:
        first = coordinator.run(request())
        second = coordinator.run(request(workspace_id="other"))
        third = coordinator.run(request(options={"num_ctx": 8192, "temperature": 0}))
    finally:
        coordinator.close(); manager.close()
    identities = {first["cache_identity"], second["cache_identity"], third["cache_identity"]}
    assert len(identities) == 3


def test_bounded_queue_reports_rejection():
    client = ScriptedClient([
        {"context": [1]}, {"response": "a", "context": [1]},
        {"context": [2]}, {"response": "b", "context": [2]},
    ], delay=0.15)
    manager = OllamaKVManager(client=client)
    coordinator = ForgeKVCoordinator(manager, workers=1, queue_capacity=1)
    try:
        first = coordinator.submit(request(prompt="one"))
        # Wait until worker takes the first job, then occupy the one queue slot.
        deadline = time.time() + 2
        while coordinator.state()["queue_depth"] and time.time() < deadline:
            time.sleep(0.01)
        second = coordinator.submit(request(prompt="two", prompt_prefix="prefix-two"))
        third = coordinator.submit(request(prompt="three", prompt_prefix="prefix-three"))
        with pytest.raises(Exception):
            third.result(timeout=1)
        first.result(timeout=3); second.result(timeout=3)
        assert coordinator.state()["metrics"]["queue_rejected"] == 1
    finally:
        coordinator.close(); manager.close()


def test_two_workers_do_not_duplicate_same_prefill():
    client = ScriptedClient([
        {"context": [7], "prompt_eval_count": 8},
        {"response": "one", "context": [7, 8], "prompt_eval_count": 1},
        {"response": "two", "context": [7, 8, 9], "prompt_eval_count": 1},
    ], delay=0.05)
    manager = OllamaKVManager(client=client)
    coordinator = ForgeKVCoordinator(manager, workers=2)
    try:
        a = coordinator.submit(request(prompt="a"))
        b = coordinator.submit(request(prompt="b"))
        a.result(timeout=3); b.result(timeout=3)
    finally:
        coordinator.close(); manager.close()
    # One prefill plus two continuations, not two prefills plus two continuations.
    assert len(client.requests) == 3
    assert sum(1 for _, payload in client.requests if payload.get("options", {}).get("num_predict") == 1) == 1
