import asyncio

import pytest

from scripts.proof.run_stage4c_preprovider import CASES, ARMS, make_plan, run_trial, summarize


@pytest.mark.parametrize("case", list(CASES))
def test_4c_only_admitted_complete_verified_routes_avoid_transport(tmp_path, case):
    rows = make_plan((case,), 1, 4350)
    outputs = {r["arm"]: asyncio.run(run_trial(tmp_path, r, live=False)) for r in rows}
    assert set(outputs) == set(ARMS)
    assert all(r["verified"] for r in outputs.values())
    assert outputs["pass_through"]["provider_requests"] == outputs["shadow"]["provider_requests"] == 1
    assert outputs["shadow"]["transform_results"]
    treated = outputs["verified_local"]
    matched = CASES[case].eligible
    assert treated["provider_requests"] == int(not matched)
    assert treated["selected_route"] == ("deterministic" if matched else "provider")
    assert treated["receipt"]["provider_execution_requested"] is (not matched)
    assert treated["observed_avoidance"] is matched
    assert summarize(rows, list(outputs.values()), live=False, abort=None)["paired_verified_provider_requests_avoided"] is None


def test_4c_simulated_provider_failure_does_not_earn_paired_credit(tmp_path):
    rows = make_plan(("valid",), 1, 7)
    outcomes = [asyncio.run(run_trial(tmp_path, r, live=False)) for r in rows]
    pass_row = next(r for r in outcomes if r["arm"] == "pass_through")
    pass_row["verified"] = False
    assert summarize(rows, outcomes, live=True, abort=None)["paired_verified_provider_requests_avoided"] == 0
