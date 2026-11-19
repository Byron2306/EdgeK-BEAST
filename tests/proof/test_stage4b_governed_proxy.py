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
    assert r["verifier"]["reason"] == "fixture_behavior_failed"
    assert r["verifier"]["anchor_valid"] and r["verifier"]["behavior_executed"]


@pytest.mark.parametrize("taskname,replacement", [
    ("shipping", "def shipping_fee(total):\n    if total >= 50:\n        return 0\n    return 4\n"),
    ("retry", "def retry_delay(attempt, base=2, cap=30):\n    return min(base * 2 ** max(attempt, 0), cap)\n"),
    ("normalize", 'import re\n\ndef normalize_provider(label):\n    return re.sub(r"[-\\s]+", "_", label.strip().lower())\n'),
])
def test_4b_accepts_noncanonical_whole_file_edit(taskname, replacement):
    from scripts.proof.run_stage4b_governed_proxy import TASKS, check_repair

    task = TASKS[taskname]
    r = check_repair(task, {"edits": [{"path": task.path, "old_text": task.source, "new_text": replacement}]})
    assert r["anchor_valid"] and r["behavior_executed"] and r["passed"]
    assert not r["canonical_exact_match"]
    assert r["before_returncodes"] == (1, 1) and r["after_returncodes"] == (0, 0)


@pytest.mark.parametrize("path,old,new,reason", [
    ("../shipping.py", "total > 50", "total >= 50", "disallowed_path"),
    ("shipping.py", "total", "amount", "ambiguous_anchor"),
    ("shipping.py", "", "total >= 50", "empty_anchor"),
    ("shipping.py", "total >= 50", "total > 50", "missing_anchor"),
    ("shipping.py", "total > 50", "open('/tmp/never-write', 'w')", "outside_fixture_subset"),
    ("shipping.py", "total > 50", "total > 50", "no_change"),
])
def test_4b_refuses_invalid_anchor_or_code_outside_fixture_subset(path, old, new, reason, monkeypatch):
    from scripts.proof.run_stage4b_governed_proxy import TASKS, check_repair

    def must_not_run(*args, **kwargs):
        pytest.fail("refused proposals must not start a verifier")

    monkeypatch.setattr("scripts.proof.run_stage4b_governed_proxy.subprocess.run", must_not_run)
    result = check_repair(TASKS["shipping"], {"edits": [{"path": path, "old_text": old, "new_text": new}]})
    assert result["reason"] == reason and not result["passed"] and not result["behavior_executed"]
