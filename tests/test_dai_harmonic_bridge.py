import json

import pytest

from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
from app.kernel.dai.harmonic_bridge import HarmonicBridgeError, harmonic_transfer_from_office_matrix


def _result(index, office, *, passed=True, document=True, office_match=True):
    active = office if office_match else f"{office}_other"
    return {
        "index": index,
        "office": office,
        "active_office": active,
        "document_evidence_used": document,
        "evaluation": {
            "passed": passed,
            "requested_office": office,
            "permitted_office": office,
            "active_office": active,
            "checks": {
                "document_evidence_used": document,
                "mandos_passed": passed,
                "office_active_match": office_match,
                "office_permitted_match": True,
                "office_requested": True,
                "has_learner_handback": True,
                "has_pitfall_or_uncertainty": True,
                "no_takeover_markers": True,
                "non_empty_response": True,
            },
        },
        "response_release_ledger": {
            "criterion_overall": "LAWFUL" if passed else "DENY",
            "claim_status": "source_grounded",
            "harmonic": {
                "resonance": 0.7 + (index * 0.01),
                "discord": 0.2,
                "confidence": 0.5,
                "mode": "normal_flow" if index > 1 else "observe_and_review",
            },
        },
    }


def _write_matrix(tmp_path, *, results=None, summary_overrides=None):
    results = results or [_result(1, "speculum"), _result(2, "custos"), _result(3, "constructor")]
    total = len(results)
    summary = {
        "total": total,
        "passed": total,
        "failed": 0,
        "document_grounded": total,
        "mandos_passes": total,
        "office_active_matches": total,
    }
    if summary_overrides:
        summary.update(summary_overrides)
    path = tmp_path / "office_response_matrix.json"
    path.write_text(json.dumps({"summary": summary, "results": results}, sort_keys=True), encoding="utf-8")
    return path


def _receipt(path):
    return ArtifactReceipt.from_file(path, organ=DAIOrgan.METATRON_HARMONIC, artifact_schema="test.harmonic")


def test_harmonic_matrix_compiles_to_transfer_assessment(tmp_path):
    path = _write_matrix(tmp_path)
    assessment, transfer = harmonic_transfer_from_office_matrix(path, source_receipt=_receipt(path))

    assert assessment.maximum_authority.value == "harmonic_assessment_only"
    assert assessment.result == "structured_transfer_assessment_available_not_truth_authority"
    assert assessment.drift_detected is True
    assert transfer.passed_cases == 3
    assert transfer.failed_cases == 0
    assert transfer.offices == ("speculum", "custos", "constructor")
    assert len(assessment.transfer_receipts) == 4


def test_harmonic_failed_transfer_row_is_refused(tmp_path):
    path = _write_matrix(
        tmp_path,
        results=[_result(1, "speculum"), _result(2, "custos", passed=False), _result(3, "constructor")],
        summary_overrides={"passed": 2, "failed": 1, "mandos_passes": 2},
    )

    with pytest.raises(HarmonicBridgeError, match="failed"):
        harmonic_transfer_from_office_matrix(path, source_receipt=_receipt(path))


def test_harmonic_office_mismatch_is_refused(tmp_path):
    path = _write_matrix(
        tmp_path,
        results=[_result(1, "speculum"), _result(2, "custos", office_match=False), _result(3, "constructor")],
        summary_overrides={"office_active_matches": 2},
    )

    with pytest.raises(HarmonicBridgeError, match="office routing"):
        harmonic_transfer_from_office_matrix(path, source_receipt=_receipt(path))


def test_harmonic_missing_document_grounding_is_refused(tmp_path):
    path = _write_matrix(
        tmp_path,
        results=[_result(1, "speculum"), _result(2, "custos", document=False), _result(3, "constructor")],
        summary_overrides={"document_grounded": 2},
    )

    with pytest.raises(HarmonicBridgeError, match="document grounded"):
        harmonic_transfer_from_office_matrix(path, source_receipt=_receipt(path))


def test_harmonic_tampered_artifact_digest_is_refused(tmp_path):
    path = _write_matrix(tmp_path)
    receipt = _receipt(path)
    path.write_text('{"summary":{},"results":[]}', encoding="utf-8")

    with pytest.raises(HarmonicBridgeError, match="digest"):
        harmonic_transfer_from_office_matrix(path, source_receipt=receipt)

