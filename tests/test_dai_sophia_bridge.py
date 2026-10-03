import json

import pytest

from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
from app.kernel.dai.sophia_bridge import SophiaBridgeError, concept_candidate_from_sophia_export


def _write_export(tmp_path, *, rows, passes=True):
    path = tmp_path / "sophia_export.json"
    payload = {
        "summary": {
            "suite": "sophia_writing_desk_phase3_export_semantic",
            "total": len(rows),
            "passed": len(rows) if passes else max(0, len(rows) - 1),
            "pass_rate": 1.0 if passes else 0.5,
            "passes_phase3_export_semantic_gate": passes,
        },
        "rows": rows,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _support(case_id, family, *, span="Visible support span.", page="p. 1", page_status="page/span marker visible"):
    return {
        "case_id": case_id,
        "passed": True,
        "top": {
            "support_label": "supports",
            "entailment_status": "entailed_by_visible_span",
            "exact_span": span,
            "page_locator": page,
            "page_status": page_status,
            "semantic_overlap": [family],
            "source_name": f"Source {case_id}",
            "source_role": "theory/construct definition",
        },
    }


def _contradiction(case_id="contradiction_not_exported_as_support"):
    return {
        "case_id": case_id,
        "passed": True,
        "top": {
            "support_label": "contradicts",
            "entailment_status": "not_entailed",
            "exact_span": "This contradicts the draft claim.",
            "semantic_overlap": ["human_agency"],
            "source_name": "Contradictory source",
            "source_role": "negative control",
        },
    }


def _receipt(path):
    return ArtifactReceipt.from_file(path, organ=DAIOrgan.SOPHIA, artifact_schema="test.sophia")


def test_sophia_export_compiles_to_candidate_from_actual_rows(tmp_path):
    path = _write_export(
        tmp_path,
        rows=[
            _support("semantic_human_agency", "human_agency"),
            _support("span_page_locator", "academic_integrity_policy"),
            _contradiction(),
        ],
    )
    candidate, summary = concept_candidate_from_sophia_export(path, source_receipt=_receipt(path))

    assert candidate.source_organ is DAIOrgan.SOPHIA
    assert candidate.maximum_authority.value == "candidate_only"
    assert candidate.promotion_state.value == "quarantined_candidate"
    assert summary.support_rows == 2
    assert summary.contradiction_rows == 1
    assert summary.distinct_support_families == ("academic_integrity_policy", "human_agency")
    assert candidate.transfer_evidence.near_transfer_case_ids == ("semantic_human_agency",)
    assert candidate.transfer_evidence.far_transfer_case_ids == ("span_page_locator",)
    assert candidate.transfer_evidence.negative_case_ids == ("contradiction_not_exported_as_support",)
    assert len(candidate.transfer_evidence.source_span_receipts) >= 3


def test_sophia_export_without_negative_control_is_refused(tmp_path):
    path = _write_export(
        tmp_path,
        rows=[
            _support("semantic_human_agency", "human_agency"),
            _support("span_page_locator", "academic_integrity_policy"),
        ],
    )

    with pytest.raises(SophiaBridgeError, match="contradiction"):
        concept_candidate_from_sophia_export(path, source_receipt=_receipt(path))


def test_sophia_export_without_distinct_support_families_is_refused(tmp_path):
    path = _write_export(
        tmp_path,
        rows=[
            _support("semantic_human_agency", "human_agency"),
            _support("span_page_locator", "human_agency"),
            _contradiction(),
        ],
    )

    with pytest.raises(SophiaBridgeError, match="semantic families"):
        concept_candidate_from_sophia_export(path, source_receipt=_receipt(path))


def test_sophia_export_with_invisible_support_span_is_refused(tmp_path):
    path = _write_export(
        tmp_path,
        rows=[
            _support("semantic_human_agency", "human_agency", page="", page_status=""),
            _support("span_page_locator", "academic_integrity_policy"),
            _contradiction(),
        ],
    )

    with pytest.raises(SophiaBridgeError, match="page/span visibility"):
        concept_candidate_from_sophia_export(path, source_receipt=_receipt(path))


def test_sophia_export_failed_gate_is_refused(tmp_path):
    path = _write_export(
        tmp_path,
        rows=[
            _support("semantic_human_agency", "human_agency"),
            _support("span_page_locator", "academic_integrity_policy"),
            _contradiction(),
        ],
        passes=False,
    )

    with pytest.raises(SophiaBridgeError, match="semantic gate"):
        concept_candidate_from_sophia_export(path, source_receipt=_receipt(path))
