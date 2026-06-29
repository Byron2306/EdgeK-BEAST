from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.kernel.storage.outcome_evidence import NegativeCapabilityStore, OutcomeEvidence


def failure(provider: str = "nvidia_nim", model: str = "nemotron") -> OutcomeEvidence:
    return OutcomeEvidence.create(
        capability_id=f"provider:{provider}",
        task_class="code_generation",
        outcome="failure",
        failure_category="stream_incomplete",
        failure_code="premature_eof",
        detail="upstream disconnected after request 934812",
        scope={"provider": provider, "model": model},
        retries=1,
        repair_depth=1,
    )


def test_failure_fingerprint_is_stable_and_does_not_store_raw_detail():
    first = failure()
    second = OutcomeEvidence.create(
        **{
            **first.to_dict(),
            "evidence_id": "different",
            "failure_fingerprint": "",
            "detail": "upstream disconnected after request 127777",
        }
    )

    assert first.failure_fingerprint == second.failure_fingerprint
    assert "934812" not in str(first.to_dict())


def test_negative_capability_requires_three_matching_failures_and_persists(tmp_path):
    path = tmp_path / "negative.json"
    store = NegativeCapabilityStore(path)

    for index in range(3):
        store.record(replace(failure(), evidence_id=f"evidence-{index}"))

    assert store.summary()["active"] == 1
    matches = store.active_matches({
        "capability_id": "provider:nvidia_nim",
        "task_class": "code_generation",
        "provider": "nvidia_nim",
        "model": "nemotron",
    })
    assert len(matches) == 1
    assert matches[0]["failure_count"] == 3
    assert NegativeCapabilityStore(path).summary()["active"] == 1


def test_negative_capability_is_exactly_scoped_and_clean_success_weakens_it(tmp_path):
    store = NegativeCapabilityStore(tmp_path / "negative.json")
    for index in range(3):
        store.record(replace(failure(), evidence_id=f"failure-{index}"))

    assert not store.active_matches({
        "capability_id": "provider:nvidia_nim",
        "task_class": "code_generation",
        "provider": "nvidia_nim",
        "model": "different-model",
    })
    for index in range(2):
        store.record(OutcomeEvidence.create(
            capability_id="provider:nvidia_nim",
            task_class="code_generation",
            outcome="success",
            evidence_id=f"success-{index}",
            scope={"provider": "nvidia_nim", "model": "nemotron"},
        ))

    assert store.summary()["active"] == 0
    assert store.summary()["revalidation"] == 1


def test_expired_negative_capability_does_not_match(tmp_path):
    store = NegativeCapabilityStore(tmp_path / "negative.json")
    for index in range(3):
        store.record(replace(failure(), evidence_id=f"failure-{index}"))
    record = next(iter(store.records.values()))
    record.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

    assert store.active_matches({
        "capability_id": "provider:nvidia_nim",
        "task_class": "code_generation",
        "provider": "nvidia_nim",
        "model": "nemotron",
    }) == []


def test_operator_override_and_maintenance_are_auditable(tmp_path):
    store = NegativeCapabilityStore(tmp_path / "negative.json")
    record = store.record(failure())

    overridden = store.override(
        record.record_id, state="suppressed", reason="provider incident resolved", approved_by="operator",
    )
    maintenance = store.maintain(prune_expired=False)

    assert overridden["state"] == "suppressed"
    assert overridden["operator_by"] == "operator"
    assert maintenance["records_after"] == 1


def test_friction_profiles_aggregate_failure_repair_latency_and_cost(tmp_path):
    store = NegativeCapabilityStore(tmp_path / "negative.json")
    store.record(replace(
        failure(),
        latency_ms=30_000,
        confidence_after=0.8,
        approval_pauses=1,
        approval_duration_ms=90_000,
    ))
    store.record(OutcomeEvidence.create(
        capability_id="provider:nvidia_nim", task_class="code_generation", outcome="recovered",
        failure_category="timeout", scope={"provider": "nvidia_nim", "model": "nemotron"},
        retries=2, repair_depth=1, latency_ms=60_000, cost_usd=0.02, confidence_after=0.7,
    ))

    profile = store.friction_profiles()[0]
    assert profile["samples"] == 2
    assert profile["failures"] == 1
    assert profile["recoveries"] == 1
    assert profile["friction_score"] > 0.4
    assert profile["latency_variance_ms2"] == 225000000.0
    assert profile["latency_stddev_ms"] == 15000.0
    assert profile["approval_pauses"] == 1
    assert profile["avg_approval_duration_ms"] == 90000.0
    assert profile["verified_completion_rate"] == 0.5
    assert profile["reported_confidence_avg"] == 0.75
    assert profile["confidence_calibration_error"] == 0.55
    assert profile["confidence_overstatement"] == 0.4
    assert profile["mode"] == "shadow"
