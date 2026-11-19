import asyncio
import json

import httpx
import pytest

from scripts.proof.run_stage4b_governed_proxy import (
    ARMS, SCHEMA, make_plan, messages_for, run_trial,
)


def test_4b_pairs_three_arms_and_seed():
    rows = make_plan(("retry", "shipping"), 2, 5)
    assert len(rows) == 12
    for index in range(0, len(rows), 3):
        block = rows[index:index + 3]
        assert {r["arm"] for r in block} == set(ARMS)
        assert len({(r["task"], r["repeat"], r["provider_seed"]) for r in block}) == 1


def test_4b_keeps_same_candidate_and_changes_only_constraint_and_close(tmp_path):
    rows = make_plan(("shipping",), 1, 17)
    bodies = {}
    results = {}

    for row in rows:
        results[row["arm"]] = asyncio.run(run_trial(tmp_path, row, model="fixture",
            dialect="openai_json_schema", controls=True, body_observer=lambda body: bodies.update({row["arm"]: body})))

    assert all(r["verified"] and r["invalid_candidates"] == 1 and r["requests"] == 1 for r in results.values())
    assert "response_format" not in bodies["unconstrained_drain"]
    assert bodies["constrained_drain"] == bodies["constrained_gate"]
    assert bodies["constrained_drain"]["response_format"]["json_schema"]["schema"] == SCHEMA
    assert {k: v for k, v in bodies["constrained_drain"].items() if k != "response_format"} == bodies["unconstrained_drain"]
    assert all(b["messages"] == messages_for("shipping") for b in bodies.values())
    assert results["constrained_gate"]["early_stop"] is True
    assert results["constrained_gate"]["done_seen"] is False
    assert results["constrained_gate"]["prompt_tokens"] is None
    assert all(results[k]["done_seen"] and results[k]["prompt_tokens"] == 24 for k in
               ("constrained_drain", "unconstrained_drain"))
    assert results["constrained_gate"]["content_bytes"] < results["constrained_drain"]["content_bytes"]


def test_4b_bad_request_never_changes_dialect_or_retries(tmp_path):
    row = next(r for r in make_plan(("retry",), 1, 1) if r["arm"] == "constrained_gate")
    calls = []

    def rejected(request):
        calls.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "stream_options unsupported"}})

    r = asyncio.run(run_trial(tmp_path, row, model="fixture", dialect="openai_json_schema",
                              transport=httpx.MockTransport(rejected)))
    assert len(calls) == r["requests"] == 1
    assert not r["verified"] and r["http_status"] == 400
    assert r["dialect"] == "openai_json_schema"
    assert "stream_options" in calls[0] and "response_format" in calls[0]


def test_4b_well_formed_wrong_edit_does_not_count_as_verified(tmp_path):
    from scripts.proof.run_stage4b_governed_proxy import ScriptedSSE

    row = next(r for r in make_plan(("shipping",), 1, 1) if r["arm"] == "constrained_gate")
    wrong = {"edits": [{"path": "shipping.py", "old_text": "total > 50", "new_text": "True"}]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=ScriptedSSE(wrong)))
    r = asyncio.run(run_trial(tmp_path, row, model="fixture", dialect="openai_json_schema", transport=transport))
    assert r["json_valid"] and not r["verified"]
    assert r["status"] == "verifier_reject"
    assert r["verifier"]["reason"] == "not_the_canonical_fixture_edit"
