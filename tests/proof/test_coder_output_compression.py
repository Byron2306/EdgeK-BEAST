import json

from scripts.proof import run_coder_efficiency_matrix as matrix


def test_diagnostic_plan_uses_only_closeout_and_single_tiers():
    plan = matrix.make_plan(("retry", "shipping"), 2, 4319, experiment="diagnostic-compression")
    assert len(plan) == 12
    for i in range(0, len(plan), 3):
        block = plan[i:i + 3]
        assert len({(r["task"], r["repeat"]) for r in block}) == 1
        assert {r["compression"] for r in block} == {"none", "rtk", "sqz"}
        assert all(r["closeout"] and not r["reporelay"] for r in block)


def test_scripted_compression_controls_deliver_compact_real_verifier_output(tmp_path):
    report = tmp_path / "matrix"
    assert matrix.main([
        "--out", str(report), "--tasks", "retry",
        "--experiment", "diagnostic-compression",
    ]) == 0
    rows = {row["arm"]: row for row in map(json.loads, (report / "attempts.jsonl").read_text().splitlines())}
    assert set(rows) == {"closeout", "rtk", "sqz"}
    assert all(row["verified"] and row["diagnostic_preflight"] for row in rows.values())
    assert rows["closeout"]["compression_deliveries"] == 0
    for tier in ("rtk", "sqz"):
        assert rows[tier]["compression_deliveries"] > 0
        assert rows[tier]["compression_prompt_bytes_saved"] > 0
        stream = (report / "events" / f"retry-01-{tier}.jsonl").read_text()
        events = [json.loads(line) for line in stream.splitlines()]
        receipts = [e["payload"] for e in events if e["event_type"] == "agent.efficiency.compression_prompt"]
        assert any(r["sent_prompt_sha256"] != r["raw_prompt_sha256"] and r["bytes_saved"] > 0 for r in receipts)
        assert "ERROR CONTRACT_CHECK retry_policy alpha-02" in stream
    summary = json.loads((report / "summary.json").read_text())
    assert len(summary["paired_against_closeout"]) == 2


def test_rejected_compression_preserves_raw_diagnostic(monkeypatch):
    def broken(*args, **kwargs):
        return {"content": "healthy", "backend": "rtk_binary", "safe": True}
    monkeypatch.setattr(matrix, "compress_cascade_output", broken, raising=False)
    raw = "healthy\n" * 10 + "ERROR CONTRACT_CHECK shipping alpha-02\n"
    output, receipt = matrix.project_diagnostic(raw, "rtk", "native", {})
    assert output == raw
    assert receipt["reason"] == "fidelity_failed"


def test_metered_provider_matches_http_body_and_keeps_usage_unknown(monkeypatch):
    import io

    from app.kernel.agents import nim_planner_provider

    seen = []

    def capture(_client, request, **kwargs):
        seen.append(request.data)
        return io.BytesIO(b'{"choices": [{"message": {"content": "{}"}}]}')

    monkeypatch.setattr(nim_planner_provider._egress, "urlopen", capture)
    provider = matrix.MeasuredNIM(key="not-a-real-key", model="stub")
    payload = provider._request_payload("diagnostic: café", repair="", turn=1)
    provider._request_json(payload)
    receipt = provider.requests[0]
    assert json.loads(seen[0])["messages"][-1]["content"] == "diagnostic: café"
    assert receipt["request_body_bytes"] == len(seen[0])
    assert receipt["user_prompt_sha256"] == matrix.digest("diagnostic: café".encode())
    assert receipt["prompt_tokens"] is None
    assert receipt["completion_tokens"] is None
