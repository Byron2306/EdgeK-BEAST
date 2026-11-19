"""Local Ollama swarm specialist: D9 local_specialist_adapter proposal → governor ADMIT → runner → gates."""

from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

import httpx
import pytest

from app.kernel.agents.swarm_specialist import (
    OllamaSwarmRunner,
    SwarmSpecialistDispatch,
    resolve_runner_model,
)
from app.kernel.compute.adaptive_router import AdaptiveRouter
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog


def specialist_route():
    return AdaptiveRouter().route(similarity=0.87, specialist={"execution_mode": "local_specialist_adapter",
                                                               "model_ref": "ollama://beast-specialist-x",
                                                               "boundary_checks_passed": True}).to_dict()


def mock_ollama(text="def add(a, b):\n    return a + b", models=("qwen3:4b",), done_reason="stop", calls=None):
    calls = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, json.loads(request.content or b"{}")))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"response": text, "done_reason": done_reason,
                                             "prompt_eval_count": 7, "eval_count": 5})
        return httpx.Response(404)

    return OllamaSwarmRunner(base_url="http://ollama.test", transport=httpx.MockTransport(handler)), calls


def ir(**metadata):
    return SimpleNamespace(messages=[{"role": "system", "content": "be terse"},
                                     {"role": "user", "content": "write add"}],
                           max_tokens=64, metadata=metadata)


def passing_cascade(text, ir):
    return True, "quality_cascade_passed"


def run(dispatch, request, route):
    return asyncio.run(dispatch.dispatch(request, route, run_id="run-1"))


def gov(tmp_path, enforce=True):
    return ComputeGovernorSpine(receipts=GovernorReceiptLog(tmp_path / "r.jsonl"), enforce=enforce)


def test_route_selects_specialist_band():
    route = specialist_route()
    assert route["route"] == "local_specialist_adapter"
    assert route["execution_granted"] is False


def test_admitted_specialist_dispatches_to_runner_not_provider(tmp_path):
    runner, calls = mock_ollama()
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(), specialist_route())
    assert outcome.dispatched is True
    assert outcome.response["model"] == "qwen3:4b"
    assert outcome.receipt["model_resolution"] == "base_model_substitute"
    assert outcome.receipt["governor_outcome"] == "admit"
    generate = [body for path, body in calls if path == "/api/generate"][0]
    assert generate["think"] is False and generate["stream"] is False
    assert generate["system"] == "be terse" and "write add" in generate["prompt"]
    assert [g["gate"] for g in outcome.receipt["gates"]] == ["quality_cascade", "output_governor", "verifier"]


def test_exact_specialist_model_preferred():
    assert resolve_runner_model("ollama://beast-specialist-x", ["qwen3:4b", "beast-specialist-x:latest"]) == (
        "beast-specialist-x:latest", "exact_specialist")
    assert resolve_runner_model("ollama://missing", ["llama-other"], env={}) == ("", "no_installed_model")


def test_governor_refusal_never_reaches_runner(tmp_path):
    runner, calls = mock_ollama()
    route = {**specialist_route(), "digest": "forged"}
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(), route)
    assert outcome.dispatched is False and outcome.reason.startswith("governor_")
    assert calls == []


def test_shadow_mode_non_admit_is_not_dispatched(tmp_path):
    runner, calls = mock_ollama()
    route = {**specialist_route(), "digest": "forged"}
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path, enforce=False),
                                          quality_gate=passing_cascade), ir(), route)
    assert outcome.dispatched is False and calls == []


def test_unattested_cascade_discards_output_and_records_negative_evidence(tmp_path):
    runner, _ = mock_ollama()
    evidence = []
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), negative_evidence=evidence.append),
                  ir(quality_cascade={"beast_object_type": "quality_cascade_report", "status": "passed"}),
                  specialist_route())
    assert outcome.dispatched is False and outcome.response is None
    assert outcome.reason.startswith("quality_cascade_failed")
    assert evidence and evidence[0]["kind"] == "specialist_output_rejected"


def test_output_governor_rejects_secret_material(tmp_path):
    runner, _ = mock_ollama(text="token = sk-" + "a" * 40)
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(), specialist_route())
    assert outcome.dispatched is False and "output_governor_failed" in outcome.reason


def test_output_governor_enforces_declared_json(tmp_path):
    runner, _ = mock_ollama(text="not json")
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(response_format={"type": "json_object"}), specialist_route())
    assert outcome.reason == "output_governor_failed:declared_json_format_invalid"


def test_truncated_generation_fails_verifier(tmp_path):
    runner, _ = mock_ollama(done_reason="length")
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(), specialist_route())
    assert outcome.reason == "verifier_failed:generation_not_complete:length"


def test_runner_unavailable_falls_back(tmp_path):
    def handler(request):
        raise httpx.ConnectError("down")

    runner = OllamaSwarmRunner(base_url="http://ollama.test", transport=httpx.MockTransport(handler))
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(), specialist_route())
    assert outcome.dispatched is False and outcome.reason == "runner_unavailable:ConnectError"


def test_crystal_route_is_not_a_specialist_proposal(tmp_path):
    runner, calls = mock_ollama()
    route = AdaptiveRouter().route(similarity=0.2).to_dict()
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path)), ir(), route)
    assert outcome.reason == "not_a_specialist_proposal" and calls == []


def test_swarm_services_bind_a_specialist_runner():
    from app.kernel.networking.swarm_services import SwarmKernelServices

    assert isinstance(SwarmKernelServices.from_runtime().specialist_runner, OllamaSwarmRunner)


def test_adaptive_dispatcher_reads_real_lattice_schema():
    from app.kernel.compute.adaptive_dispatcher import AdaptiveDispatcher

    node = AdaptiveDispatcher._normalize_node({"task_family": "coding", "capability_contract_digest": "d",
                                               "fingerprint_hashes": {"a": "b"}})
    assert node["task_class"] == "coding" and len(node["node_id"]) == 16


@pytest.mark.skipif(os.environ.get("BEAST_LIVE_OLLAMA") != "1", reason="set BEAST_LIVE_OLLAMA=1 for live smoke")
def test_live_ollama_smoke(tmp_path):
    runner = OllamaSwarmRunner(timeout=180)
    try:
        installed = asyncio.run(runner.installed_models())
    except httpx.HTTPError:
        pytest.skip("ollama not reachable")
    model, _ = resolve_runner_model("ollama://beast-specialist-none", installed)
    if not model:
        pytest.skip("no preferred model installed")
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  SimpleNamespace(messages=[{"role": "user", "content": "Reply with the single word OK."}],
                                  max_tokens=256, metadata={}), specialist_route())
    assert outcome.receipt.get("generated") is True
    assert outcome.dispatched is True, outcome.reason


# --- structured edits + bounded repair-retry (gauntlet 2026-11-16 crux fix) ----------------------------------

def scripted_ollama(texts, models=("qwen3:4b",), calls=None):
    calls = calls if calls is not None else []
    queue = list(texts)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        calls.append((request.url.path, body))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        return httpx.Response(200, json={"response": queue.pop(0), "done_reason": "stop",
                                         "prompt_eval_count": 10, "eval_count": 20})

    return OllamaSwarmRunner(base_url="http://ollama.test", transport=httpx.MockTransport(handler)), calls


SCHEMA = {"type": "object", "properties": {"old_text": {"type": "string"}, "new_text": {"type": "string"}},
          "required": ["old_text", "new_text"]}


def wants_json_edit(text, _ir):
    try:
        value = json.loads(text)
    except ValueError:
        return False, "not_json"
    return (value.get("new_text") == "B = 2"), ("ok" if value.get("new_text") == "B = 2" else "wrong_edit")


def test_response_schema_is_sent_as_ollama_format(tmp_path):
    runner, calls = scripted_ollama(['{"old_text": "B = 1", "new_text": "B = 2"}'])
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade,
                                          verifiers=[wants_json_edit]), ir(response_schema=SCHEMA), specialist_route())
    assert outcome.dispatched is True
    generate = [b for p, b in calls if p == "/api/generate"][0]
    assert generate["format"] == SCHEMA


def test_default_schema_always_used_for_specialists(tmp_path):
    """Specialists always use structured output (default schema) even when no response_schema provided."""
    runner, calls = scripted_ollama(['{"result": "def add(a, b): return a + b"}'])
    # Use a verifier that matches the default schema
    def wants_default_schema(text, _ir):
        try:
            value = json.loads(text)
        except ValueError:
            return False, "not_json"
        return ("result" in value), ("ok" if "result" in value else "missing_result")
    
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade,
                                          verifiers=[wants_default_schema]), ir(), specialist_route())
    assert outcome.dispatched is True
    generates = [b for p, b in calls if p == "/api/generate"]
    assert len(generates) == 1
    # Default schema is always sent
    assert "format" in generates[0]
    assert generates[0]["format"]["properties"]["result"]["type"] == "string"


def test_repair_retry_feeds_back_reason_and_succeeds(tmp_path):
    runner, calls = scripted_ollama(['{"old_text": "B = 1", "new_text": "B = 3"}',
                                     '{"old_text": "B = 1", "new_text": "B = 2"}'])
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade,
                                          verifiers=[wants_json_edit]),
                  ir(response_schema=SCHEMA, repair_retries=1), specialist_route())
    assert outcome.dispatched is True
    generates = [b for p, b in calls if p == "/api/generate"]
    assert len(generates) == 2 and "wrong_edit" in generates[1]["prompt"]
    assert [a["reason"] for a in outcome.receipt["attempts"]] == ["verifier_failed:wrong_edit", "specialist_output_accepted"]
    assert outcome.receipt["usage"] == {"prompt_tokens": 20, "completion_tokens": 40}


def test_repair_retries_are_capped_and_budgeted(tmp_path):
    runner, calls = scripted_ollama(["{}"] * 10)
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade,
                                          verifiers=[wants_json_edit]),
                  ir(response_schema=SCHEMA, repair_retries=9), specialist_route())
    assert outcome.dispatched is False
    assert len([1 for p, _ in calls if p == "/api/generate"]) == 3  # 1 + hard cap of 2 repairs
    runner, calls = scripted_ollama(["{}"] * 10)
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade,
                                          verifiers=[wants_json_edit]),
                  ir(response_schema=SCHEMA, repair_retries=2, token_budget=70), specialist_route())
    assert len([1 for p, _ in calls if p == "/api/generate"]) == 2  # 30 tokens/attempt: a third would exceed 70
    assert outcome.receipt["budget_exhausted"] is True


def test_retry_never_bypasses_governor_refusal(tmp_path):
    runner, calls = scripted_ollama(["{}"] * 3)
    governor = gov(tmp_path)
    route = dict(specialist_route(), digest="sha256:tampered")
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=governor, quality_gate=passing_cascade,
                                          verifiers=[wants_json_edit]), ir(response_schema=SCHEMA, repair_retries=2), route)
    assert outcome.dispatched is False
    assert not [1 for p, _ in calls if p == "/api/generate"]


def test_operational_route_uses_strict_admission_and_local_model_inventory(tmp_path):
    from app.kernel.agents.swarm_specialist import operational_specialist_route

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": "qwen3:4b", "remote_host": "https://example.test"},
                {"name": "remote:cloud"}, {"name": "granite3.3:2b"},
            ]})
        payload = json.loads(request.content)
        assert payload["model"] == "granite3.3:2b"
        return httpx.Response(200, json={"response": "proposal", "done_reason": "stop"})

    runner = OllamaSwarmRunner(transport=httpx.MockTransport(handler), local_models_only=True)
    route = operational_specialist_route("route_dampened", "qwen3:4b")
    assert route["band"] == "operational"
    assert route["similarity"] == 0
    outcome = run(SwarmSpecialistDispatch(runner=runner, governor=gov(tmp_path), quality_gate=passing_cascade),
                  ir(), route)
    assert outcome.dispatched
    assert outcome.receipt["governor_outcome"] == "admit"
    assert outcome.receipt["execution_granted"] is False
    assert outcome.receipt["installed_models"] == ["granite3.3:2b"]
