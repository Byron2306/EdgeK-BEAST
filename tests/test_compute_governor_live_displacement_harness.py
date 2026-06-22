from benchmarks.compute_governor_phase2_live_displacement import run


def test_phase2_live_displacement_harness_supports_injected_provider_call(monkeypatch):
    def fake_provider_call(provider, prompt, max_tokens, timeout):
        return {
            "text": '{"ok": true}',
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(
        "benchmarks.compute_governor_phase2_live_displacement._provider_call",
        fake_provider_call,
    )

    report = run(provider_name="groq", max_tokens=16, timeout=1.0)

    assert report["phase2_live_displacement_passed"] is True
    assert report["shadow_live_provider_calls"] == 1
    assert report["shadow_transform_verified"] is True
    assert report["shadow_transform_agreement"] is True
    assert report["impact_reusable_at_enforcement"] is True
    assert report["enforced_provider_execution_requested"] is False
    assert report["enforced_gate_decision"] == "deterministic"
    assert report["displaced_live_calls"] == 1
