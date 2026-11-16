"""Governed interception: constrained bodies, stream gate, scorecard, governed client, placement."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.constrained_output import constrain_body, dialects_for, output_budget
from app.kernel.compute.governed_client import Candidate, CircuitBreaker, GovernedModelClient, redact
from app.kernel.compute.json_stream_gate import JsonStreamGate
from app.kernel.compute.placement import plan
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

SCHEMA = {"type": "object", "properties": {"edits": {"type": "array", "minItems": 1, "items": {
    "type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
    "required": ["path", "old_text", "new_text"], "additionalProperties": False}}}, "required": ["edits"], "additionalProperties": False}
ACTION = {"edits": [{"path": "a.py", "old_text": "x = 1", "new_text": "x = 2"}]}
SECRET = "nvapi-TESTSECRETVALUE1234567890"


# -- 1. schema-constrained request bodies per provider ------------------------------------------------
def test_ollama_body_forces_schema_and_disables_thinking():
    body = constrain_body("ollama", {"model": "qwen3:4b", "messages": []}, SCHEMA, max_tokens=512)
    assert body["format"] == SCHEMA and body["think"] is False
    assert body["options"]["num_predict"] == 512 and body["stream"] is True


def test_nim_body_json_schema_then_guided_json_dialect():
    assert dialects_for("nim")[:2] == ["openai_json_schema", "nim_guided_json"]
    a = constrain_body("nim", {"model": "nvidia/nemotron-3.5-lightning-30b-a3b", "messages": []}, SCHEMA, max_tokens=2048)
    assert a["response_format"]["type"] == "json_schema" and a["response_format"]["json_schema"]["schema"] == SCHEMA
    assert a["chat_template_kwargs"] == {"enable_thinking": False} and a["max_tokens"] == 2048
    assert a["stream"] is True and a["stream_options"] == {"include_usage": True}
    b = constrain_body("nim", {"model": "deepseek-ai/deepseek-v4.1-flash", "messages": []}, SCHEMA, dialect="nim_guided_json")
    assert b["nvext"]["guided_json"] == SCHEMA and "response_format" not in b
    assert b["chat_template_kwargs"] == {"thinking": False}
    c = constrain_body("nim", {"model": "openai/gpt-oss-20b", "messages": []}, SCHEMA)
    assert c["reasoning_effort"] == "low"


def test_hf_router_tgi_and_vllm_dialects():
    hf = constrain_body("hf_router", {"model": "Qwen/Qwen2.5-Coder-32B-Instruct:nebius", "messages": []}, SCHEMA)
    assert hf["response_format"]["json_schema"]["strict"] is True
    tgi = constrain_body("tgi", {"model": "tgi", "messages": []}, SCHEMA)
    assert tgi["response_format"] == {"type": "json_object", "value": SCHEMA}
    gen = constrain_body("tgi_generate", {"inputs": "x"}, SCHEMA, max_tokens=300)
    assert gen["parameters"]["grammar"] == {"type": "json", "value": SCHEMA} and gen["parameters"]["max_new_tokens"] == 300
    vl = constrain_body("vllm", {"model": "m", "messages": []}, SCHEMA)
    assert vl["guided_json"] == SCHEMA


def test_output_budget_sized_for_reasoning_models():
    assert output_budget("qwen2.5-coder:7b") == 1024
    assert output_budget("deepseek-r1:7b", thinking_disabled=False) == 4096
    assert output_budget("nemotron-x") >= 2048


# -- 2. stream gate / interceptor early stop -----------------------------------------------------------
def test_gate_stops_on_first_complete_valid_action_and_ignores_think():
    gate = JsonStreamGate(schema=SCHEMA)
    text = "<think>{not json}</think>Sure! " + json.dumps(ACTION) + "\nHere is why: blah blah"
    verdicts = [gate.feed(text[i:i + 7]) for i in range(0, len(text), 7)]
    assert "stop" in verdicts
    stop_at = verdicts.index("stop")
    assert stop_at < len(verdicts) - 1  # stopped before the trailing prose was consumed
    assert gate.value == ACTION and gate.stop_reason == "schema_valid_action"


def test_gate_skips_schema_invalid_object_then_accepts_valid_one():
    gate = JsonStreamGate(schema=SCHEMA)
    assert gate.feed('{"edits": []} ') == "continue"
    assert gate.feed(json.dumps(ACTION)) == "stop"


def test_gate_flags_runaway_prose_and_repetition():
    gate = JsonStreamGate(schema=SCHEMA, prose_budget_chars=100)
    assert gate.feed("I think we should " * 10) == "runaway"
    rep = JsonStreamGate(schema=SCHEMA, prose_budget_chars=10**6)
    assert rep.feed("lorem ipsum dolor sit amet consectetur adipiscing elit sed do " * 40) == "runaway"


def test_gate_handles_braces_inside_strings_and_fenced_finish():
    gate = JsonStreamGate(schema=SCHEMA)
    tricky = {"edits": [{"path": "a.py", "old_text": "d = {'}': 1}", "new_text": "d = {\"{\": 2}"}]}
    assert gate.feed(json.dumps(tricky)) == "stop" and gate.value == tricky
    fenced = JsonStreamGate(schema=SCHEMA, prose_budget_chars=10**6)
    fenced.buffer = "```json\n" + json.dumps(ACTION) + "\n```"
    assert fenced.finish()["valid"]


# -- 3. capability scorecard ---------------------------------------------------------------------------
def _cands():
    return [{"provider": "ollama", "model": "qwen3:4b", "placement": "gpu_full"},
            {"provider": "nim", "model": "nemotron", "placement": "cloud"},
            {"provider": "nim", "model": "deepseek", "placement": "cloud"}]


def test_scorecard_ranks_by_family_evidence_and_persists(tmp_path):
    path = tmp_path / "sc.json"
    sc = CapabilityScorecard(path)
    for _ in range(4):
        sc.record(provider="nim", model="nemotron", family="rename", passed=True, json_valid=True, tokens=700, latency_ms=1200)
        sc.record(provider="ollama", model="qwen3:4b", family="rename", placement="gpu_full", passed=False, json_valid=False)
    ranked = sc.rank(_cands(), "rename", consume_cooldown=False)
    assert ranked[0]["model"] == "nemotron"
    assert ranked[-1]["model"] == "qwen3:4b"  # demoted after consecutive failures
    again = CapabilityScorecard(path)
    assert again.rank(_cands(), "rename", consume_cooldown=False)[0]["model"] == "nemotron"
    snap = again.snapshot()["cells"]
    assert any(c["family"] == "*" for c in snap) and all("prompt" not in json.dumps(c) for c in snap)


def test_scorecard_shift_on_failure_then_cooldown_expires(tmp_path):
    sc = CapabilityScorecard(tmp_path / "s.json", demote_after=2, cooldown=2)
    for _ in range(3):
        sc.record(provider="ollama", model="qwen3:4b", family="obo", placement="gpu_full", passed=True, json_valid=True, tokens=600)
    assert sc.rank(_cands(), "obo", consume_cooldown=False)[0]["model"] == "qwen3:4b"
    sc.record(provider="ollama", model="qwen3:4b", family="obo", placement="gpu_full", passed=False, json_valid=False)
    sc.record(provider="ollama", model="qwen3:4b", family="obo", placement="gpu_full", passed=False, json_valid=False)
    first = sc.rank(_cands(), "obo")
    assert first[0]["model"] != "qwen3:4b" and any(r["score"]["demoted"] for r in first)
    sc.rank(_cands(), "obo")
    third = sc.rank(_cands(), "obo")
    assert not any(r["score"]["demoted"] for r in third)  # cooldown consumed: eligible again (exploration)


def test_scorecard_is_deterministic_and_explores_unseen(tmp_path):
    a = CapabilityScorecard(tmp_path / "a.json")
    b = CapabilityScorecard(tmp_path / "b.json")
    for sc in (a, b):
        sc.record(provider="nim", model="nemotron", family="x", passed=False, json_valid=True)
    ra = [r["model"] for r in a.rank(_cands(), "x", consume_cooldown=False)]
    rb = [r["model"] for r in b.rank(_cands(), "x", consume_cooldown=False)]
    assert ra == rb and ra[0] != "nemotron"  # unseen candidates win the exploration bonus


def test_scorecard_placement_dimension_is_separate(tmp_path):
    sc = CapabilityScorecard(tmp_path / "p.json")
    sc.record(provider="ollama", model="qwen2.5-coder:7b", family="f", placement="hybrid:6", passed=True, json_valid=True, latency_ms=70000)
    sc.record(provider="ollama", model="qwen2.5-coder:7b", family="f", placement="cpu", passed=False, json_valid=False)
    keys = {c["placement"] for c in sc.snapshot()["cells"]}
    assert {"hybrid:6", "cpu"} <= keys


# -- 4. governed client (mock transport) -----------------------------------------------------------------
def _sse(chunks, usage=None):
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks]
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _governor():
    return ComputeGovernorSpine(receipts=GovernorReceiptLog(None), enforce=True)


def _client(handler, cands, tmp_path, **kw):
    return GovernedModelClient(cands, scorecard=CapabilityScorecard(tmp_path / "sc.json"), governor=kw.pop("governor", _governor()),
                               transport=httpx.MockTransport(handler), use_scorecard=kw.pop("use_scorecard", False), **kw)


NIM = Candidate(provider="nim", model="nvidia/nemotron", kind="nim", base_url="https://nim.test/v1", key_env="TEST_NIM_KEY", max_tokens=2048)
DS = Candidate(provider="nim", model="deepseek-ai/deepseek-v4.1-flash", kind="nim", base_url="https://nim.test/v1", key_env="TEST_NIM_KEY")
OLL = Candidate(provider="ollama", model="qwen3:4b", kind="ollama", base_url="http://ollama.test", placement="gpu_full",
                rung="local_specialist", stall_timeout_s=0.3, ttft_timeout_s=0.3)


def _ok(_):
    return {"passed": True, "reason": "tests_pass"}


def test_streaming_early_stop_saves_tail_and_emits_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)
    sent = {}

    def handler(request):
        sent["body"] = json.loads(request.content)
        payload = json.dumps(ACTION)
        return httpx.Response(200, content=_sse([payload[:20], payload[20:], " and now a long explanation" * 50]))

    gc = _client(handler, [NIM], tmp_path)
    res = asyncio.run(gc.complete(family="fix-config-constant", messages=[{"role": "user", "content": "fix"}], schema=SCHEMA,
                                  verify=_ok, run_id="t1"))
    assert res.accepted and res.value == ACTION
    call = res.calls[0]
    assert call.early_stop and call.stop_reason == "schema_valid_action" and call.budget_headroom_tokens > 1500
    assert sent["body"]["response_format"]["type"] == "json_schema" and sent["body"]["stream"] is True
    records = gc.governor.receipts.records()
    assert any(r.get("type") == "model_call" and r.get("passed") for r in records)
    assert any(r.get("type") == "decision" and r.get("outcome") == "admit" for r in records)
    assert gc.governor.receipts.verify()["valid"]
    assert SECRET not in json.dumps(records)


def test_dialect_fallback_on_400(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format unsupported"})
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    res = asyncio.run(_client(handler, [NIM], tmp_path).complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="t2"))
    assert res.accepted and seen == [True, False] and res.calls[0].dialect == "nim_guided_json"


def test_fallback_when_circuit_open_and_no_secret_in_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)

    def handler(request):
        body = json.loads(request.content)
        if "deepseek" in body["model"]:
            return httpx.Response(503, text=f"upstream down; key={SECRET}")
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    breaker = CircuitBreaker(open_after=2, cooldown_s=999)
    gc = _client(handler, [DS, NIM], tmp_path, breaker=breaker)
    r1 = asyncio.run(gc.complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="a"))
    assert r1.accepted and r1.calls[0].status == "http_error" and r1.accepted_by.startswith("nim:nvidia/nemotron")
    asyncio.run(gc.complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="b"))
    assert breaker.state(DS.ident)["state"] == "open"
    r3 = asyncio.run(gc.complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="c"))
    assert r3.calls[0].status == "skipped_circuit_open" and r3.accepted
    blob = json.dumps(gc.governor.receipts.records()) + json.dumps([c.public() for c in r1.calls])
    assert SECRET not in blob and "[REDACTED]" in blob


def test_scorecard_routing_shifts_after_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)

    def handler(request):
        body = json.loads(request.content)
        if "deepseek" in body["model"]:
            return httpx.Response(200, content=_sse(["I'd be happy to help! " * 3]))  # prose, no JSON
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    gc = _client(handler, [DS, NIM], tmp_path, use_scorecard=True)
    order = []
    for i in range(4):
        res = asyncio.run(gc.complete(family="rename", messages=[], schema=SCHEMA, verify=_ok, run_id=f"s{i}"))
        order.append(res.calls[0].candidate.model)
        assert res.accepted
    assert order[-1] == "nvidia/nemotron"  # learned: deepseek no longer tried first for this family


def test_verifier_reject_falls_through_to_next_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)
    handler = lambda request: httpx.Response(200, content=_sse([json.dumps(ACTION)]))  # noqa: E731
    verdicts = iter([{"passed": False, "reason": "tests_still_failing"}, {"passed": True}])
    res = asyncio.run(_client(handler, [DS, NIM], tmp_path).complete(family="f", messages=[], schema=SCHEMA,
                                                                       verify=lambda v: next(verdicts), run_id="v"))
    assert [c.status for c in res.calls] == ["verifier_reject", "ok"] and res.accepted


def test_stream_stall_detected_and_ollama_model_unloaded(tmp_path):
    unloads = []

    async def handler(request):
        body = json.loads(request.content)
        if request.url.path == "/api/generate" and body.get("keep_alive") == 0:
            unloads.append(body["model"])
            return httpx.Response(200, json={"done": True})

        async def stalled():
            yield (json.dumps({"message": {"content": '{"edits": ['}, "done": False}) + "\n").encode()
            await asyncio.sleep(5)
            yield b""

        assert body["format"] == SCHEMA and body["think"] is False
        return httpx.Response(200, content=stalled())

    res = asyncio.run(_client(handler, [OLL], tmp_path).complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="st"))
    assert res.calls[0].status == "stream_stall" and res.calls[0].stop_reason == "inter_chunk_stall"
    assert unloads == ["qwen3:4b"] and res.calls[0].teardown["mode"] == "ollama_unload"


def test_governor_budget_exhaustion_defers(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)
    handler = lambda request: httpx.Response(200, content=_sse(["no json"], usage={"prompt_tokens": 900, "completion_tokens": 200}))  # noqa: E731
    gc = _client(handler, [NIM, DS], tmp_path, episode_token_limit=2100)
    res = asyncio.run(gc.complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="budget"))
    assert not res.accepted and res.reason == "governor_budget_exhausted"
    assert res.calls[-1].status == "refused_governor" and "budget_exhausted" in res.calls[-1].error


def test_avoid_hook_short_circuits_with_zero_calls(tmp_path):
    gc = _client(lambda r: pytest.fail("no model call expected"), [NIM], tmp_path,
                 avoid=lambda fam, msgs: {"by": "crystal:family-crystal:abc", "value": ACTION})
    res = asyncio.run(gc.complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="av"))
    assert res.avoided and res.accepted and res.public()["model_calls"] == 0
    assert gc.governor.receipts.records()[-1]["status"] == "avoided"


def test_redact_patterns():
    s = redact(f"Authorization: Bearer abcdefghijklmnop hf_ABCDEFGHIJKLMNOP {SECRET}", [SECRET])
    assert "hf_ABCDEFGH" not in s and SECRET not in s and "abcdefghijkl" not in s


# -- 5. placement ---------------------------------------------------------------------------------------
def test_placement_hybrid_cpu_and_cloud_under_pressure():
    roomy = plan("qwen2.5-coder:7b", pressure={"vram_free_mib": 6000, "ram_available_mib": 8000})
    assert roomy["placement"] == "gpu_full"
    tight = plan("qwen2.5-coder:7b", pressure={"vram_free_mib": 1980, "ram_available_mib": 9000})
    assert tight["placement"].startswith("hybrid:") and 1 <= tight["num_gpu"] <= 8
    thrash = plan("qwen2.5-coder:7b", pressure={"vram_free_mib": 1980, "ram_available_mib": 1000})
    assert thrash["placement"] == "cloud" and "ram_pressure" in thrash["reason"] and thrash["options"] == {}
    q8 = plan("qwen3:4b", num_ctx=8192, kv_quant="q8_0", pressure={"vram_free_mib": 6000, "ram_available_mib": 8000})
    f16 = plan("qwen3:4b", num_ctx=8192, pressure={"vram_free_mib": 6000, "ram_available_mib": 8000})
    assert q8["kv_cache_mib"] == pytest.approx(f16["kv_cache_mib"] / 2)


def test_verifier_feedback_turn_reaches_next_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["messages"])
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    verdicts = iter([{"passed": False, "reason": "tests_still_failing", "feedback": "ImportError: load_user"}, {"passed": True}])
    gc = _client(handler, [DS, NIM], tmp_path)
    res = asyncio.run(gc.complete(family="rename", messages=[{"role": "user", "content": "task"}], schema=SCHEMA,
                                  verify=lambda v: next(verdicts), run_id="fb"))
    assert res.accepted and len(seen[0]) == 1 and len(seen[1]) == 3
    assert "ImportError: load_user" in seen[1][-1]["content"]
    assert "ImportError" not in json.dumps(gc.governor.receipts.records())  # feedback text never lands in receipts


def test_tgi_is_optional_and_probed(monkeypatch, tmp_path):
    from app.kernel.compute.governed_client import default_candidates

    up = httpx.MockTransport(lambda r: httpx.Response(200 if r.url.path == "/health" else 404))
    down = httpx.MockTransport(lambda r: httpx.Response(503))
    with_tgi = default_candidates({}, tgi_transport=up)
    without = default_candidates({}, tgi_transport=down)
    assert [c.provider for c in with_tgi].count("tgi") == 1 and with_tgi[2].provider == "tgi"
    assert all(c.provider != "tgi" for c in without)
    hf = [c for c in without if c.provider == "hf"][0]
    assert hf.key_env == "HF_TOKEN" and hf.key_file == "~/.cache/huggingface/token"


def test_hf_token_read_from_file_never_recorded(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("hf_FILETOKENVALUE123456789\n")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(401, text="bad token hf_FILETOKENVALUE123456789")

    cand = Candidate(provider="hf", model="m:prov", kind="hf_router", base_url="https://hf.test/v1", key_env="HF_TOKEN",
                     key_file=str(token_file))
    gc = _client(handler, [cand], tmp_path)
    res = asyncio.run(gc.complete(family="f", messages=[], schema=SCHEMA, verify=_ok, run_id="hf"))
    assert seen["auth"] == "Bearer hf_FILETOKENVALUE123456789"
    blob = json.dumps(gc.governor.receipts.records()) + json.dumps(res.public())
    assert "FILETOKENVALUE" not in blob


# -- 6. HF-router lanes + Gemini adapter -------------------------------------------------------------------
def test_hf_router_lanes_one_candidate_per_model_provider(tmp_path):
    from app.kernel.compute.governed_client import hf_router_candidates, default_candidates
    lanes = hf_router_candidates({})
    idents = {c.model for c in lanes}
    assert len(lanes) == 15 and len(idents) == 15
    assert "moonshotai/Kimi-K2.7-Code:featherless-ai" in idents and "openai/gpt-oss-120b:groq" in idents
    assert "deepseek-ai/DeepSeek-V4.1-Flash:baseten" in idents and "zai-org/GLM-5.3-Flash:zai-org" in idents
    for c in lanes:
        assert c.base_url == "https://router.huggingface.co/v1" and c.kind == "hf_router"
        assert c.key_env == "HF_TOKEN" and c.key_file.endswith("huggingface/token") and c.usd_per_mtok_out > 0
    only = hf_router_candidates({"BEAST_HF_ROUTER_MODELS": "Qwen/Qwen3.8-27B"})
    assert [c.model.split(":")[1] for c in only] == ["cerebras", "deepinfra", "nscale"]
    dc = default_candidates({}, probe_tgi=False)
    assert sum(c.provider == "hf" for c in dc) == 15
    # scorecard keeps a separate cell per (model, provider)
    from app.kernel.compute.capability_scorecard import CapabilityScorecard
    sc = CapabilityScorecard(tmp_path / "sc.json")
    sc.record(provider="hf", model="openai/gpt-oss-120b:groq", family="f", passed=True, json_valid=True)
    sc.record(provider="hf", model="openai/gpt-oss-120b:cerebras", family="f", passed=False, json_valid=False)
    models = {c["model"] for c in sc.snapshot()["cells"]}
    assert {"openai/gpt-oss-120b:groq", "openai/gpt-oss-120b:cerebras"} <= models


def test_gemini_candidate_only_with_key_and_body_is_schema_forced_stream(tmp_path, monkeypatch):
    from app.kernel.compute.governed_client import gemini_candidate
    from app.kernel.compute.constrained_output import constrain_body
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    empty = tmp_path / "empty.env"; empty.write_text("OTHER=1\n")
    assert gemini_candidate({}, dotenv=str(empty)) is None
    dot = tmp_path / "secrets.env"; dot.write_text("GEMINI_API_KEY=AIzaTESTGEMINIKEY0000000000000000000\n")
    cand = gemini_candidate({}, dotenv=str(dot))
    assert cand and cand.kind == "gemini" and cand.key_env == "GEMINI_API_KEY"
    assert cand.base_url.startswith("https://generativelanguage.googleapis.com/v1beta/openai")
    body = constrain_body("gemini", {"model": cand.model, "messages": []}, SCHEMA, max_tokens=64)
    assert body["response_format"]["type"] == "json_schema" and body["stream"] is True
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA


def test_gemini_key_from_dotenv_used_at_call_time_and_never_recorded(tmp_path, monkeypatch):
    from app.kernel.compute.governed_client import gemini_candidate
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    dot = tmp_path / "secrets.env"; dot.write_text("GEMINI_API_KEY=AIzaTESTGEMINIKEY0000000000000000000\n")
    cand = gemini_candidate({}, dotenv=str(dot))
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    client = _client(handler, [cand], tmp_path)
    res = asyncio.run(client.complete(family="f", messages=[{"role": "user", "content": "x"}], schema=SCHEMA,
                                      verify=lambda v: {"passed": True}, run_id="t-gemini"))
    assert res.accepted and seen["auth"] == "Bearer AIzaTESTGEMINIKEY0000000000000000000"
    assert seen["url"].endswith("/v1beta/openai/chat/completions")
    for p in tmp_path.rglob("*.jsonl"):
        assert "AIzaTESTGEMINIKEY" not in p.read_text()


def test_rejected_optional_knob_is_stripped_and_same_dialect_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_NIM_KEY", SECRET)
    qwen = Candidate(provider="hf", model="Qwen/Qwen3.8-27B:cerebras", kind="hf_router", base_url="https://hf.test/v1",
                     key_env="TEST_NIM_KEY")
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "chat_template_kwargs" in body:
            return httpx.Response(400, json={"message": "chat_template_kwargs: property 'chat_template_kwargs' is unsupported"})
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    res = asyncio.run(_client(handler, [qwen], tmp_path).complete(family="f", messages=[{"role": "user", "content": "x"}],
                                                                  schema=SCHEMA, verify=_ok, run_id="t-strip"))
    assert res.accepted and len(bodies) == 2
    assert bodies[1]["response_format"]["type"] == "json_schema" and "chat_template_kwargs" not in bodies[1]
    assert res.calls[-1].dialect == "openai_json_schema"


# -- 7. direct-provider lanes (Fireworks / SambaNova / Hyperbolic / Replicate / fal) -------------------------
def test_provider_lanes_activate_only_with_key(tmp_path, monkeypatch):
    from app.kernel.compute.governed_client import provider_lane_candidates
    for k in ("FIREWORKS_API_KEY", "HYPERBOLIC_API_KEY", "REPLICATE_API_TOKEN", "SAMBANOVA_API_KEY", "FAL_KEY"):
        monkeypatch.delenv(k, raising=False)
    none = tmp_path / "none.env"; none.write_text("")
    assert provider_lane_candidates({}, dotenv=str(none)) == []
    dot = tmp_path / "s.env"; dot.write_text("FIREWORKS_API_KEY=fw_TESTKEY000000000000\nFAL_KEY=fal-TEST:000000\n")
    c = provider_lane_candidates({}, dotenv=str(dot))
    provs = {x.provider for x in c}
    assert provs == {"fireworks", "fal_llm"}
    assert all(x.base_url.startswith("https://") and x.key_env and x.usd_per_mtok_out > 0 for x in c)
    assert [x.provider for x in c][-1] == "fal_llm"  # proxy lane is ranked last
    fal = [x for x in c if x.provider == "fal_llm"][0]
    assert fal.auth_scheme == "Key" and fal.base_url == "https://fal.run/openrouter/router/openai/v1"
    sn = provider_lane_candidates({"SAMBANOVA_API_KEY": "x" * 20}, dotenv=str(none))
    assert {x.model for x in sn} == {"gpt-oss-120b", "MiniMax-M3.1-Flash", "Meta-Llama-3.3-70B-Instruct"}


def test_fal_llm_uses_key_auth_scheme(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_FAL", "fal-TESTKEYVALUE-123456")
    cand = Candidate(provider="fal_llm", model="openai/gpt-oss-120b", kind="openai", base_url="https://fal.test/v1",
                     key_env="TEST_FAL", auth_scheme="Key")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=_sse([json.dumps(ACTION)]))

    res = asyncio.run(_client(handler, [cand], tmp_path).complete(family="f", messages=[{"role": "user", "content": "x"}],
                                                                  schema=SCHEMA, verify=_ok, run_id="t-fal"))
    assert res.accepted and seen["auth"] == "Key fal-TESTKEYVALUE-123456"


def test_thinking_only_rejection_strips_thinking_knobs():
    from app.kernel.compute.constrained_output import strip_unsupported
    body = {"model": "glm", "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_schema"}}
    out = strip_unsupported(body, "400: GLM-5.3 is a thinking-only model; disabling thinking (reasoning_effort='none') is not supported.")
    assert "chat_template_kwargs" not in out and out["response_format"]["type"] == "json_schema"


def _replicate_cand():
    return Candidate(provider="replicate", model="openai/gpt-oss-120b", kind="replicate", base_url="https://rep.test/v1",
                     key_env="TEST_REP", options={"input_map": {"system": ""}}, usd_per_mtok_in=0.18, usd_per_mtok_out=0.72)


def test_replicate_prompt_validate_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_REP", "r8_TESTREPLICATETOKEN0000000")
    posts = []

    def handler(request):
        if request.method == "POST":
            body = json.loads(request.content)
            posts.append(body)
            assert request.url.path == "/v1/models/openai/gpt-oss-120b/predictions"
            assert request.headers["prefer"].startswith("wait") and "JSON Schema" in body["input"]["prompt"]
            if len(posts) == 1:
                return httpx.Response(201, json={"status": "succeeded", "output": ["Sure! here you go: {not json"],
                                                 "metrics": {"input_token_count": 100, "output_token_count": 10}})
            return httpx.Response(201, json={"status": "processing", "urls": {"get": "https://rep.test/v1/predictions/p2"}})
        return httpx.Response(200, json={"status": "succeeded", "output": [json.dumps(ACTION)[:15], json.dumps(ACTION)[15:]],
                                         "metrics": {"input_token_count": 120, "output_token_count": 20}})

    res = asyncio.run(_client(handler, [_replicate_cand()], tmp_path).complete(
        family="f", messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "x"}], schema=SCHEMA, verify=_ok,
        run_id="t-rep"))
    call = res.calls[0]
    assert res.accepted and len(posts) == 2 and call.dialect == "prompt_validate_retry:attempts=2"
    assert call.tokens_prompt == 220 and call.tokens_completion == 30 and call.spend_usd > 0
    for p in tmp_path.rglob("*.jsonl"):
        assert "r8_TESTREPLICATE" not in p.read_text()


def test_replicate_402_costs_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_REP", "r8_TESTREPLICATETOKEN0000000")
    res = asyncio.run(_client(lambda r: httpx.Response(402, json={"detail": "Insufficient credit"}), [_replicate_cand()],
                              tmp_path).complete(family="f", messages=[{"role": "user", "content": "x"}], schema=SCHEMA,
                                                 verify=_ok, run_id="t-rep402"))
    c = res.calls[0]
    assert not res.accepted and c.status == "http_error" and c.spend_usd == 0 and c.tokens_prompt == 0


def test_fal_media_lane_queue_flow_and_off_by_default(tmp_path, monkeypatch):
    from app.kernel.compute.media_lanes import FalMediaLane
    monkeypatch.delenv("BEAST_MEDIA_LANES", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    dot = tmp_path / "s.env"; dot.write_text("FAL_KEY=fal-TESTMEDIAKEY:0000\n")
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "r1", "status": "IN_QUEUE",
                                             "status_url": "https://q.test/fal-ai/flux/requests/r1/status",
                                             "response_url": "https://q.test/fal-ai/flux/requests/r1"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        return httpx.Response(200, json={"images": [{"url": "https://cdn.test/a.png", "width": 512, "height": 512}]})

    lane = FalMediaLane(dotenv=str(dot), base="https://q.test", transport=httpx.MockTransport(handler), poll_s=0)
    assert lane.generate("fal-ai/flux/schnell", {"prompt": "x"}).status == "disabled"
    res = lane.generate("fal-ai/flux/schnell", {"prompt": "x"}, force=True).public()
    assert res["ok"] and res["counts_in_coding_scorecard"] is False and abs(res["est_cost_usd"] - 0.000786) < 1e-5
    assert seen[0] == ("POST", "/fal-ai/flux/schnell", "Key fal-TESTMEDIAKEY:0000")
    assert "TESTMEDIAKEY" not in json.dumps(res)


def test_smoke_family_does_not_feed_aggregate(tmp_path):
    sc = CapabilityScorecard(tmp_path / "sc.json")
    sc.record(provider="p", model="m", family="smoke-tiny", passed=True, json_valid=True)
    keys = {(c["family"]) for c in sc.snapshot()["cells"]}
    assert keys == {"smoke-tiny"}
    assert sc.score("p", "m", "refactor-rename-symbol")["source"] == "prior"


def test_exploration_bonus_capped_so_evidence_beats_unseen_lanes(tmp_path):
    sc = CapabilityScorecard(tmp_path / "sc.json")
    for _ in range(4):
        sc.record(provider="fireworks", model="ds", family="rename", passed=True, json_valid=True, tokens=900, latency_ms=2000)
    cands = [{"provider": "hf", "model": f"unseen{i}", "placement": "cloud"} for i in range(30)]
    cands.append({"provider": "fireworks", "model": "ds", "placement": "cloud"})
    ranked = sc.rank(cands, "rename", consume_cooldown=False)
    assert ranked[0]["model"] == "ds"
    assert all(r["score"]["explore_bonus"] <= sc.explore_c + 1e-9 for r in ranked)
