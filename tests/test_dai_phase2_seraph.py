from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase2_seraph import (
    run_stale_listener_seraph_injections,
    stale_listener_seraph_injection_cases,
)


def test_phase2_seraph_generates_named_stale_listener_injections():
    candidate_digest = sha256_digest({"candidate": "stale_listener_conflict"})
    source_digest = sha256_digest({"source": "sophia_acquisition"})

    cases = stale_listener_seraph_injection_cases(
        candidate_digest=candidate_digest,
        source_receipt_digest=source_digest,
    )

    assert len(cases) == 7
    assert {case.attack_family for case in cases} == {
        "fake_process_owner",
        "decoy_service",
        "misleading_health_response",
        "stale_pid",
        "copied_evidence_digest",
        "delayed_sensor_event",
        "contradictory_socket_observation",
    }
    assert all(case.maximum_authority.value == "adversarial_challenge_only" for case in cases)
    assert all(case.challenge_digest.startswith("sha256:") for case in cases)


def test_phase2_seraph_injections_are_refused_with_zero_effect():
    candidate_digest = sha256_digest({"candidate": "stale_listener_conflict"})
    source_digest = sha256_digest({"source": "sophia_acquisition"})

    report = run_stale_listener_seraph_injections(
        candidate_digest=candidate_digest,
        source_receipt_digest=source_digest,
    )

    assert report.passed is True
    assert report.provider_calls_used == 0
    assert report.execution_authority_allowed is False
    assert len(report.probe_results) == 7
    assert all(result.refused for result in report.probe_results)
    assert all(result.zero_effect for result in report.probe_results)
    assert all(result.passed for result in report.probe_results)
    assert report.report_digest.startswith("sha256:")

