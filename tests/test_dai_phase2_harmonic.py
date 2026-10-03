import json

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.phase2_harmonic import score_stale_listener_harmonic_transfer


def _payload():
    return {
        "schema": "dai.phase2.sophia_stale_listener_examples.v1",
        "examples": [
            {
                "case_id": "near_same_service_other_port",
                "transfer_class": "near",
                "domain": "api_listener_replacement",
                "outcome_label": "stale_listener_conflict",
                "evidence_terms": ["owned_process", "listener_socket", "stale_generation", "same_port_replacement"],
                "causal_sequence": [
                    "owned_process_verified",
                    "stale_listener_blocks_port",
                    "retire_exact_owner",
                    "rebind_same_port",
                    "verify_replacement_healthy",
                ],
                "required_boundaries": ["exact_process_identity_required", "replacement_health_required"],
            },
            {
                "case_id": "far_metrics_namespace_listener",
                "transfer_class": "far",
                "domain": "metrics_namespace_repair",
                "outcome_label": "stale_listener_conflict",
                "evidence_terms": ["owned_process", "listener_socket", "namespace_boundary", "stale_generation", "same_port_replacement"],
                "causal_sequence": [
                    "namespace_identity_verified",
                    "owned_process_verified",
                    "stale_listener_blocks_port",
                    "retire_exact_owner",
                    "rebind_same_port",
                    "verify_replacement_healthy",
                ],
                "required_boundaries": [
                    "namespace_identity_required",
                    "exact_process_identity_required",
                    "replacement_health_required",
                ],
            },
            {
                "case_id": "negative_unknown_owner_refusal",
                "transfer_class": "negative",
                "domain": "unknown_process_boundary",
                "outcome_label": "safe_refusal",
                "evidence_terms": ["listener_socket", "unknown_owner"],
                "causal_sequence": ["listener_socket_observed", "owner_unverified", "refuse_retirement"],
                "required_boundaries": ["must_not_retire_unknown_process"],
            },
            {
                "case_id": "negative_healthy_reuse",
                "transfer_class": "negative",
                "domain": "healthy_existing_service",
                "outcome_label": "reuse_existing_service",
                "evidence_terms": ["owned_process", "listener_socket", "current_generation", "healthy_service"],
                "causal_sequence": [
                    "owned_process_verified",
                    "current_generation_verified",
                    "healthy_service_verified",
                    "reuse_existing_service",
                ],
                "required_boundaries": ["must_not_retire_healthy_current_service"],
            },
        ],
    }


def _write(tmp_path, payload):
    path = tmp_path / "examples.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _score(path):
    return score_stale_listener_harmonic_transfer(
        path,
        candidate_digest=sha256_digest({"candidate": "stale_listener_conflict"}),
        source_receipt_digest=sha256_digest({"receipt": "sophia_examples"}),
        source_artifact_digest=sha256_digest({"artifact": "examples"}),
    )


def test_phase2_harmonic_scores_near_far_transfer_green(tmp_path):
    report = _score(_write(tmp_path, _payload()))

    assert report.passed is True
    assert report.maximum_authority.value == "harmonic_assessment_only"
    assert report.execution_authority_allowed is False
    assert report.provider_calls_used == 0
    assert report.near_case_ids == ("near_same_service_other_port",)
    assert report.far_case_ids == ("far_metrics_namespace_listener",)
    assert report.negative_case_ids == ("negative_healthy_reuse", "negative_unknown_owner_refusal")
    assert all(case.passed for case in report.cases)
    assert report.report_digest.startswith("sha256:")


def test_phase2_harmonic_catches_reversed_causal_chain(tmp_path):
    payload = _payload()
    payload["examples"][0]["causal_sequence"] = [
        "verify_replacement_healthy",
        "rebind_same_port",
        "retire_exact_owner",
        "stale_listener_blocks_port",
        "owned_process_verified",
    ]

    report = _score(_write(tmp_path, payload))

    near = next(case for case in report.cases if case.case_id == "near_same_service_other_port")
    assert report.passed is False
    assert near.passed is False
    assert near.refusal_reason == "causal_order_reversed_or_incomplete"


def test_phase2_harmonic_catches_far_transfer_without_namespace_boundary(tmp_path):
    payload = _payload()
    payload["examples"][1]["evidence_terms"] = ["owned_process", "listener_socket", "stale_generation", "same_port_replacement"]

    report = _score(_write(tmp_path, payload))

    far = next(case for case in report.cases if case.case_id == "far_metrics_namespace_listener")
    assert report.passed is False
    assert far.passed is False
    assert far.refusal_reason == "far_transfer_namespace_boundary_missing"


def test_phase2_harmonic_catches_negative_control_laundering(tmp_path):
    payload = _payload()
    payload["examples"][2]["outcome_label"] = "stale_listener_conflict"

    report = _score(_write(tmp_path, payload))

    negative = next(case for case in report.cases if case.case_id == "negative_unknown_owner_refusal")
    assert report.passed is False
    assert negative.passed is False
    assert negative.refusal_reason == "negative_control_laundered_as_positive_transfer"

