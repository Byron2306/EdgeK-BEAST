import asyncio

from scripts.proof.run_stage4d_ranked_routing import (
    MODELS, run_matrix, split_plan,
)


def test_4d_split_freezes_disjoint_cases_and_balanced_calibration():
    train, test = split_plan(4327, 3)
    assert len(train) == 8 and len(test) == 12
    assert {r["fixture"] for r in train}.isdisjoint(r["fixture"] for r in test)
    for row in test:
        other, = [r for r in test if r["fixture"] == row["fixture"] and r["arm"] != row["arm"]]
        assert other["provider_seed"] == row["provider_seed"]
    for fixture in {r["fixture"] for r in train}:
        assert {r["model"] for r in train if r["fixture"] == fixture} == set(MODELS)


def test_4d_scripted_routing_changes_only_order_and_saves_calls(tmp_path):
    report = asyncio.run(run_matrix(tmp_path, live=False, seed=4327, repeats=3, request_cap=32))
    assert report["abort"] is None
    assert report["calibration"]["requests"] == 8
    assert report["arms"]["fixed"]["verified"] == report["arms"]["ranked"]["verified"] == 6
    assert report["arms"]["fixed"]["requests"] == 9
    assert report["arms"]["ranked"]["requests"] == 6
    assert report["paired"]["different_first_choice"] == 3
    assert report["paired"]["request_delta_ranked_minus_fixed"] == -3
    assert report["paired"]["verified_delta_ranked_minus_fixed"] == 0


def test_4d_shared_model_requests_are_identical_across_arms(tmp_path):
    import json

    report = asyncio.run(run_matrix(tmp_path, live=False, seed=9, repeats=1, request_cap=16))
    assert report["abort"] is None
    rows = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text().splitlines()]
    for fid in {r["fixture"] for r in rows}:
        first, second = (r for r in rows if r["fixture"] == fid)
        left, right = ({q["model"]: q["request_sha256"] for q in r["requests"]} for r in (first, second))
        assert left.keys() & right.keys()
        assert all(left[m] == right[m] for m in left.keys() & right.keys())


def test_4d_protocol_rejection_seals_partial_calibration_without_dialect_retries(tmp_path, monkeypatch):
    import httpx
    from scripts.proof import run_stage4d_ranked_routing as runner

    monkeypatch.setattr(runner, "_mock_response", lambda *args: httpx.Response(400, json={"error": "unsupported"}))
    report = asyncio.run(run_matrix(tmp_path, live=False, seed=9, repeats=1, request_cap=16))
    assert report["abort"]["http_status"] == 400
    assert report["abort"]["reason"] == "provider_protocol_rejected"
    assert report["total_http_requests"] == 1
    assert report["paired"]["complete_pairs"] == 0
    assert not (tmp_path / "frozen_scorecard.json").exists()
    assert (tmp_path / "SHA256SUMS").is_file()
