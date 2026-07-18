from app.kernel.compute.displacement import DisplacementEvaluator


def test_verified_local_crystal_displaces_provider_work():
    receipt = DisplacementEvaluator().run("crystal:port-conflict-repair:v1", lambda: {"verification_passed": True, "latency_ms": 22, "cpu_ms": 8, "memory_mb": 12}, provider_calls=1, repair_steps=6)
    assert receipt.displaced is True
    assert receipt.provider_calls_avoided == 1
    assert receipt.repair_steps_avoided == 6


def test_failed_verification_claims_no_displacement():
    receipt = DisplacementEvaluator().run("crystal:test", lambda: {"verification_passed": False}, provider_calls=1)
    assert receipt.displaced is False
    assert receipt.provider_calls_avoided == 0

