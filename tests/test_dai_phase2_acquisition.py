import json

import pytest

from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
from app.kernel.dai.phase2_acquisition import (
    Phase2SophiaAcquisitionError,
    phase2_acquisition_receipt,
    stale_listener_candidate_from_sophia_examples,
)


def _base_payload():
    return {
        "schema": "dai.phase2.sophia_stale_listener_examples.v1",
        "summary": {"passes_acquisition_gate": True},
        "examples": [
            {
                "case_id": "near_same_service_other_port",
                "transfer_class": "near",
                "domain": "api_listener_replacement",
                "outcome_label": "stale_listener_conflict",
                "source_span": "owned stale listener blocks the requested port and is replaced on the same port",
                "evidence_terms": [
                    "owned_process",
                    "listener_socket",
                    "stale_generation",
                    "failed_health_check",
                    "same_port_replacement",
                ],
                "required_boundaries": [
                    "exact_process_identity_required",
                    "replacement_health_required",
                ],
            },
            {
                "case_id": "far_metrics_namespace_listener",
                "transfer_class": "far",
                "domain": "metrics_namespace_repair",
                "outcome_label": "stale_listener_conflict",
                "source_span": "same causal structure in a different namespace and service class",
                "evidence_terms": [
                    "owned_process",
                    "listener_socket",
                    "namespace_boundary",
                    "stale_generation",
                    "same_port_replacement",
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
                "source_span": "unknown owner requires refusal",
                "evidence_terms": ["listener_socket", "unknown_owner"],
                "required_boundaries": ["must_not_retire_unknown_process"],
            },
            {
                "case_id": "negative_healthy_reuse",
                "transfer_class": "negative",
                "domain": "healthy_existing_service",
                "outcome_label": "reuse_existing_service",
                "source_span": "healthy current service should be reused",
                "evidence_terms": [
                    "owned_process",
                    "listener_socket",
                    "current_generation",
                    "healthy_service",
                ],
                "required_boundaries": ["must_not_retire_healthy_current_service"],
            },
        ],
    }


def _write_payload(tmp_path, payload):
    path = tmp_path / "phase2_sophia_examples.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _receipt(path):
    return ArtifactReceipt.from_file(path, organ=DAIOrgan.SOPHIA, artifact_schema="test.phase2.sophia")


def test_phase2_sophia_examples_compile_stale_listener_candidate(tmp_path):
    path = _write_payload(tmp_path, _base_payload())
    candidate, summary = stale_listener_candidate_from_sophia_examples(path, source_receipt=_receipt(path))
    receipt = phase2_acquisition_receipt(candidate, summary)

    assert candidate.candidate_id == "sophia:phase2:stale-listener-conflict:v1"
    assert candidate.maximum_authority.value == "candidate_only"
    assert candidate.promotion_state.value == "quarantined_candidate"
    assert summary.near_case_ids == ("near_same_service_other_port",)
    assert summary.far_case_ids == ("far_metrics_namespace_listener",)
    assert summary.refusal_case_ids == ("negative_unknown_owner_refusal",)
    assert len(summary.domains) == 4
    assert {spec.predicate for spec in candidate.candidate_predicates} >= {
        "stale_listener_conflict",
        "listener_owner_verified",
        "same_port_replacement_healthy",
        "unrelated_listener_unchanged",
    }
    assert receipt["execution_authority_allowed"] is False
    assert receipt["provider_calls_used"] == 0


def test_phase2_sophia_examples_require_far_transfer(tmp_path):
    payload = _base_payload()
    payload["examples"] = [example for example in payload["examples"] if example["transfer_class"] != "far"]
    path = _write_payload(tmp_path, payload)

    with pytest.raises(Phase2SophiaAcquisitionError, match="far-transfer"):
        stale_listener_candidate_from_sophia_examples(path, source_receipt=_receipt(path))


def test_phase2_sophia_examples_require_negative_refusal_boundaries(tmp_path):
    payload = _base_payload()
    for example in payload["examples"]:
        if example["case_id"] == "negative_unknown_owner_refusal":
            example["required_boundaries"] = ["operator_or_external_authority_required"]
    path = _write_payload(tmp_path, payload)

    with pytest.raises(Phase2SophiaAcquisitionError, match="negative boundaries"):
        stale_listener_candidate_from_sophia_examples(path, source_receipt=_receipt(path))


def test_phase2_sophia_examples_refuse_tampered_artifact_digest(tmp_path):
    path = _write_payload(tmp_path, _base_payload())
    receipt = _receipt(path)
    payload = _base_payload()
    payload["summary"]["passes_acquisition_gate"] = False
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(Phase2SophiaAcquisitionError, match="digest"):
        stale_listener_candidate_from_sophia_examples(path, source_receipt=receipt)

