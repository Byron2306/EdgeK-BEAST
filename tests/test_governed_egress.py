"""Egress shims: byte-identical passthrough with flags off; admit headers + redacted receipts with flags on."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.kernel.compute import governed_egress as eg


class Recorder:
    def __init__(self):
        self.calls = []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return httpx.Response(200, json={"usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}})


def test_flags_off_is_exact_passthrough(monkeypatch):
    monkeypatch.delenv("BEAST_GOVERNED_INTERCEPTION", raising=False)
    rec = Recorder()
    kw = {"json": {"a": 1}, "headers": {"Authorization": "Bearer x"}, "timeout": 5}
    eg.post(rec, "nim", "https://integrate.api.nvidia.com/v1/chat/completions", **kw)
    assert rec.calls == [("https://integrate.api.nvidia.com/v1/chat/completions", kw)]


def test_flags_on_adds_admit_headers_and_receipts_without_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_GOVERNED_INTERCEPTION", "1")
    monkeypatch.setenv("BEAST_GOVERNED_EGRESS_RECEIPTS", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(eg, "_STATE", {})
    rec = Recorder()
    eg.post(rec, "nim", "https://integrate.api.nvidia.com/v1/chat/completions", json={"prompt": "SECRET-PROMPT"},
            headers={"Authorization": "Bearer nvapi-abcdefghijklmnop"})
    url, kw = rec.calls[0]
    assert kw["headers"]["Authorization"] == "Bearer nvapi-abcdefghijklmnop" and len(kw["headers"]["X-BEAST-Admit"]) == 32
    text = (tmp_path / "r.jsonl").read_text()
    assert "SECRET-PROMPT" not in text and "nvapi-" not in text
    rows = [json.loads(line) for line in text.splitlines()]
    egress = [r for r in rows if r.get("type") == "model_egress"]
    assert egress and egress[-1]["usage"]["total_tokens"] == 3 and egress[-1]["host"] == "integrate.api.nvidia.com"


def test_async_post_and_stream_passthrough(monkeypatch):
    monkeypatch.delenv("BEAST_GOVERNED_INTERCEPTION", raising=False)
    seen = []

    def handler(req):
        seen.append((req.method, str(req.url), dict(req.headers)))
        return httpx.Response(200, text='{"ok":true}')

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434") as c:
            r = await eg.apost(c, "swarm", "/api/generate", json={"m": 1})
            async with eg.astream(c, "providers", "POST", "/api/chat", json={"m": 2}) as s:
                body = await s.aread()
            return r.status_code, body

    status, body = asyncio.run(run())
    assert status == 200 and body == b'{"ok":true}'
    assert [s[0] for s in seen] == ["POST", "POST"] and not any(k.startswith("x-beast") for s in seen for k in s[2])


def test_refusal_enforced_only_when_asked(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_GOVERNED_INTERCEPTION", "1")
    monkeypatch.setenv("BEAST_GOVERNED_EGRESS_RECEIPTS", str(tmp_path / "r.jsonl"))

    class Deny:
        receipt_hash, reasons = "sha256:" + "0" * 64, ("budget_exhausted:test",)

        def permits(self):
            return False

    class Gov:
        class receipts:
            @staticmethod
            def _append(body):
                return body

        def admit(self, *a, **k):
            return Deny()

    monkeypatch.setattr(eg, "_STATE", {"governor": Gov()})
    rec = Recorder()
    eg.post(rec, "x", "http://127.0.0.1:11434/api/generate")  # receipted, proceeds
    monkeypatch.setenv("BEAST_GOVERNED_EGRESS_ENFORCE", "1")
    with pytest.raises(eg.EgressRefused):
        eg.post(rec, "x", "http://127.0.0.1:11434/api/generate")
    assert len(rec.calls) == 1


def test_arda_admit_queue(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_GOVERNED_INTERCEPTION", "1")
    monkeypatch.setenv("BEAST_ARDA_EGRESS_ADMIT", "1")
    monkeypatch.setenv("BEAST_GOVERNED_EGRESS_RECEIPTS", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(eg, "_STATE", {})
    monkeypatch.setattr(eg, "ADMIT_QUEUE", tmp_path / "q.jsonl")
    eg.post(Recorder(), "x", "https://router.huggingface.co/v1/chat/completions")
    row = json.loads((tmp_path / "q.jsonl").read_text().splitlines()[0])
    assert row["host"] == "router.huggingface.co" and len(row["receipt_prefix"]) == 16 and row["ttl_ms"] == 30000


def test_no_direct_model_calls_left_in_converted_sites():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    files = ["app/kernel/agents/swarm_specialist.py", "app/kernel/agents/nim_planner_provider.py",
             "app/kernel/agents/ollama_planner_provider.py", "app/kernel/adapters/providers.py",
             "app/kernel/compute/inference_engine_fabric.py", "app/kernel/local/ollama_scout.py",
             "app/kernel/local/ollama_kv_manager.py", "app/kernel/compute/nim_live_probe.py"]
    for f in files:
        text = (root / f).read_text()
        assert not re.search(r"(?<!_egress)\b(?:client|self\.client|self\._session|httpx)\.post\(", text), f
        assert "urllib.request.urlopen(" not in text or "_egress.urlopen" in text, f
