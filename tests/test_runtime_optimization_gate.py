from app.kernel.compute.runtime_optimization_gate import RuntimeLaneMeasurement, evaluate_optimization


def test_runtime_gate_requires_prefill_gain_and_no_verification_regression():
    baseline = [RuntimeLaneMeasurement("baseline", 100, 130, True), RuntimeLaneMeasurement("baseline", 110, 140, True)]
    candidate = [RuntimeLaneMeasurement("forge_kv", 60, 90, True), RuntimeLaneMeasurement("forge_kv", 70, 100, True)]
    result = evaluate_optimization(baseline=baseline, candidate=candidate, candidate_lane="forge_kv")
    assert result["status"] == "promote_runtime_route"
    assert result["candidate"]["prefill_saving"] >= 0.05


def test_runtime_gate_refuses_unmeasured_or_regressed_route():
    baseline = [RuntimeLaneMeasurement("baseline", 100, 120, True)]
    candidate = [RuntimeLaneMeasurement("forge_kv", 50, 80, False)]
    result = evaluate_optimization(baseline=baseline, candidate=candidate, candidate_lane="forge_kv")
    assert result["status"] == "experimental_only"
    assert "verification_regression" in result["blockers"]

