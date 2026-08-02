from app.kernel.agents.verification_repair_loop import VerificationRepairLoop


def test_repair_loop_corrects_wrong_first_response_within_scope():
    source = {"value": "old"}
    responses = iter(["wrong", "correct"])
    requests = []

    def solver(request):
        requests.append(request)
        return {"replacement_expression": next(responses)}

    def apply(value):
        source["value"] = value
        return {"path": "pricing.py", "symbol": "apply_discount"}

    def verify():
        return {"ok": source["value"] == "correct", "failure": "expected correct"}

    result = VerificationRepairLoop(solver=solver, apply=apply, verify=verify).run(
        path="pricing.py", symbol="apply_discount", old="old", failure="expected 170, got 185"
    )

    assert result["status"] == "passed"
    assert result["repair_rounds"] == 2
    assert requests[1]["verifier_failure"] == "expected correct"
    assert result["scope"] == {"max_files": 1, "max_symbols": 1}


def test_repair_loop_rejects_multiline_or_import_response():
    result = VerificationRepairLoop(
        solver=lambda _: {"replacement_expression": "import os\nreturn 1"},
        apply=lambda _: {"ok": True},
        verify=lambda: {"ok": True},
    ).run(path="pricing.py", symbol="apply_discount", old="old", failure="failed")

    assert result["status"] == "blocked"
    assert "one-expression" in result["rounds"][0]["reason"]


def test_repair_loop_feeds_failure_analysis_and_crystal_scaffold():
    seen = {}

    def solver(request):
        seen.update(request)
        return {"replacement_expression": "value + 1"}

    result = VerificationRepairLoop(
        solver=solver,
        apply=lambda value: {"value": value},
        verify=lambda: {"ok": True},
        crystalist=lambda request: [{"pattern": "value + 1", "evidence_id": "proof-1"}],
    ).run(path="pricing.py", symbol="apply_discount", old="value", failure="NameError: name 'value' is not defined")

    assert result["status"] == "passed"
    assert seen["failure_analysis"]["repair_required"] is True
    assert seen["crystal_scaffold"][0]["evidence_id"] == "proof-1"
