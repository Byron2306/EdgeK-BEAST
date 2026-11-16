"""execute.py routes schema-carrying requests through the governed client only when the flag is on."""
from __future__ import annotations

import asyncio
import json
import types

import httpx

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.governed_client import Candidate, GovernedModelClient
from app.kernel.execution import execute as ex
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

SCHEMA = {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"]}


def _stub(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        assert body["format"] == SCHEMA and body["think"] is False
        return httpx.Response(200, content=(json.dumps({"message": {"content": '{"answer": 42}'}, "done": False}) + "\n"
                                            + json.dumps({"message": {"content": " trailing"}, "done": True,
                                                          "prompt_eval_count": 10, "eval_count": 5}) + "\n").encode())

    client = GovernedModelClient([Candidate(provider="ollama", model="qwen3:4b", kind="ollama", base_url="http://o.test",
                                            rung="local_specialist", placement="gpu_full")],
                                 scorecard=CapabilityScorecard(tmp_path / "sc.json"),
                                 governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(None), enforce=True),
                                 transport=httpx.MockTransport(handler), use_scorecard=False)
    executor = ex.Executor.__new__(ex.Executor)
    executor._governed_client = client
    return executor


def _ir(meta):
    return types.SimpleNamespace(metadata=meta, messages=[{"role": "user", "content": "6*7"}], model="m")


def _compute():
    return types.SimpleNamespace(plan=types.SimpleNamespace(plan_id="plan-1"))


def test_flag_off_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("BEAST_GOVERNED_INTERCEPTION", raising=False)
    out = asyncio.run(_stub(tmp_path)._try_governed_interception(_ir({"governed_schema": SCHEMA}), _compute()))
    assert out is None


def test_flag_on_routes_and_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_GOVERNED_INTERCEPTION", "1")
    completed = {}
    monkeypatch.setattr(ex.compute_interceptor, "complete", lambda compute, **kw: completed.update(kw) or {"ok": True})
    executor = _stub(tmp_path)
    monkeypatch.setattr(executor, "_compute_summary", lambda compute, receipt: {"receipt": receipt}, raising=False)
    out = asyncio.run(executor._try_governed_interception(_ir({"governed_schema": SCHEMA, "task_family": "math"}), _compute()))
    assert json.loads(out["choices"][0]["message"]["content"]) == {"answer": 42}
    gi = out["edgek_governed_interception"]
    assert gi["accepted"] and gi["calls"][0]["early_stop"] and gi["model_calls"] == 1
    assert completed["status"] == "governed_interception_succeeded"


def test_request_without_schema_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_GOVERNED_INTERCEPTION", "1")
    assert asyncio.run(_stub(tmp_path)._try_governed_interception(_ir({}), _compute())) is None
