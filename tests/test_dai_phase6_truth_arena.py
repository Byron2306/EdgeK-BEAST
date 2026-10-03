import json

import pytest

from app.kernel.dai.capability_ledger import build_phase6_capability_ledger
from app.kernel.dai.phase6_deterministic_arena import run_phase6_arena
from app.kernel.dai.phase6_sophia_transfer_arena import run_phase6_sophia_transfer_arena
from app.kernel.dai.phase6_truth_arena import generate_phase6_truth_cases, run_phase6_truth_arena


def _write_sophia_export(tmp_path):
    rows = [
        {
            "case_id": "semantic_human_agency",
            "passed": True,
            "top": {
                "support_label": "supports",
                "entailment_status": "entailed_by_visible_span",
                "exact_span": "Visible support span.",
                "page_locator": "p. 1",
                "page_status": "page/span marker visible",
                "semantic_overlap": ["human_agency"],
                "source_name": "Source A",
                "source_role": "fixture",
            },
        },
        {
            "case_id": "span_page_locator",
            "passed": True,
            "top": {
                "support_label": "supports",
                "entailment_status": "entailed_by_visible_span",
                "exact_span": "Visible support span two.",
                "page_locator": "p. 2",
                "page_status": "page/span marker visible",
                "semantic_overlap": ["academic_integrity_policy"],
                "source_name": "Source B",
                "source_role": "fixture",
            },
        },
        {
            "case_id": "contradiction_not_exported_as_support",
            "passed": True,
            "top": {
                "support_label": "contradicts",
                "entailment_status": "not_entailed",
                "exact_span": "This contradicts the claim.",
                "semantic_overlap": ["human_agency"],
                "source_name": "Negative control",
                "source_role": "negative control",
            },
        },
    ]
    path = tmp_path / "sophia_export.json"
    path.write_text(json.dumps({
        "summary": {
            "suite": "sophia_writing_desk_phase3_export_semantic",
            "total": len(rows),
            "passed": len(rows),
            "pass_rate": 1.0,
            "passes_phase3_export_semantic_gate": True,
        },
        "rows": rows,
    }, sort_keys=True), encoding="utf-8")
    return path


def _ledger(tmp_path):
    restart = run_phase6_arena(freeze_seed="phase6-truth-restart-fixture")
    sophia = run_phase6_sophia_transfer_arena(
        export_path=_write_sophia_export(tmp_path),
        freeze_seed="phase6-truth-sophia-fixture",
    )
    return build_phase6_capability_ledger(restart_arena_receipt=restart, sophia_transfer_receipt=sophia)


def test_phase6_truth_arena_composes_two_crystals_and_refuses_gaps(tmp_path):
    receipt = run_phase6_truth_arena(
        ledger=_ledger(tmp_path),
        freeze_seed="phase6-truth-test-freeze",
    )

    assert receipt["green"] is True
    assert receipt["case_count"] == 9
    assert receipt["mixed_capability_cases"] == 9
    assert receipt["answerable_case_count"] == 6
    assert receipt["refusal_case_count"] == 3
    assert receipt["semantic_correct_count"] == 9
    assert receipt["text_visual_joined_green_count"] == 9
    assert receipt["visual_proposition_coverage_count"] == 9
    assert receipt["provider_calls_after_ledger"] == 0
    assert receipt["baseline_report"]["beast_stronger_than_local_baselines"] is True


def test_phase6_truth_arena_records_optional_rds_rag_baseline_without_oracle(tmp_path):
    def fake_rag(request):
        return {
            "answer_text": f"{request['source']} and {request['target']} retrieved without proof.",
            "retrieved_chunks": [{"text": "retrieved"}],
            "current_claim_valid": True,
            "provider_calls_used": 0,
        }

    receipt = run_phase6_truth_arena(
        ledger=_ledger(tmp_path),
        freeze_seed="phase6-truth-test-freeze",
        rds_rag_runner=fake_rag,
    )

    assert receipt["green"] is True
    assert receipt["baseline_report"]["rds_rag_enabled"] is True
    assert len(receipt["baseline_report"]["rds_rag_outputs"]) == receipt["case_count"]
    assert receipt["baseline_report"]["rds_rag_semantic_correct"] < receipt["semantic_correct_count"]


def test_phase6_truth_cases_are_randomized_and_bound_to_ledger_digest(tmp_path):
    ledger = _ledger(tmp_path)
    first = generate_phase6_truth_cases(freeze_seed="truth-seed-a", ledger_digest=ledger.ledger_digest)
    second = generate_phase6_truth_cases(freeze_seed="truth-seed-a", ledger_digest=ledger.ledger_digest)
    other = generate_phase6_truth_cases(freeze_seed="truth-seed-b", ledger_digest=ledger.ledger_digest)

    assert first == second
    assert first != other
    assert all(ledger.ledger_digest[-12:] in case.case_id for case in first)
    assert all(case.generated_after_freeze for case in first)


def test_capability_ledger_rejects_non_green_source_receipt(tmp_path):
    restart = run_phase6_arena(freeze_seed="phase6-truth-restart-fixture")
    sophia = run_phase6_sophia_transfer_arena(
        export_path=_write_sophia_export(tmp_path),
        freeze_seed="phase6-truth-sophia-fixture",
    )
    bad_restart = dict(restart)
    bad_restart["green"] = False

    with pytest.raises(ValueError, match="restart arena receipt is not green"):
        build_phase6_capability_ledger(restart_arena_receipt=bad_restart, sophia_transfer_receipt=sophia)
