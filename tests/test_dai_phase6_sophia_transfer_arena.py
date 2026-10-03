import json

from app.kernel.dai.phase6_sophia_transfer_arena import (
    generate_phase6_sophia_cases,
    run_phase6_sophia_transfer_arena,
)


def _write_export(tmp_path):
    rows = []
    for index in range(2):
        family = "human_agency" if index == 0 else "academic_integrity_policy"
        rows.append({
            "case_id": "semantic_human_agency" if index == 0 else "span_page_locator",
            "passed": True,
            "top": {
                "support_label": "supports",
                "entailment_status": "entailed_by_visible_span",
                "exact_span": f"Visible support span {index}.",
                "page_locator": f"p. {index + 1}",
                "page_status": "page/span marker visible",
                "semantic_overlap": [family],
                "source_name": f"Source {index}",
                "source_role": "semantic fixture",
            },
        })
    rows.append({
        "case_id": "contradiction_not_exported_as_support",
        "passed": True,
        "top": {
            "support_label": "contradicts",
            "entailment_status": "not_entailed",
            "exact_span": "This contradicts the draft claim.",
            "semantic_overlap": ["human_agency"],
            "source_name": "Negative control",
            "source_role": "negative control",
        },
    })
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


def test_phase6_sophia_transfer_ingests_export_and_solves_heldout_cases(tmp_path):
    receipt = run_phase6_sophia_transfer_arena(
        export_path=_write_export(tmp_path),
        freeze_seed="phase6-sophia-test-freeze",
    )

    assert receipt["green"] is True
    assert receipt["sophia_support_rows"] == 2
    assert receipt["sophia_contradiction_rows"] == 1
    assert receipt["candidate_predicate_count"] == 3
    assert receipt["case_count"] == 12
    assert receipt["answerable_case_count"] == 6
    assert receipt["refusal_case_count"] == 6
    assert receipt["bounded_acquisition_calls_before_promotion"] == 1
    assert receipt["provider_calls_after_promotion"] == 0
    assert receipt["semantic_correct_count"] == 12
    assert receipt["text_visual_joined_green_count"] == 12
    assert receipt["production_authority_allowed"] is False
    assert receipt["execution_authority_allowed"] is False


def test_phase6_sophia_transfer_refuses_contradiction_and_missing_span(tmp_path):
    receipt = run_phase6_sophia_transfer_arena(
        export_path=_write_export(tmp_path),
        freeze_seed="phase6-sophia-test-freeze",
    )

    refusals = [case for case in receipt["case_receipts"] if case["expected_action"] == "refuse"]

    assert refusals
    assert all(case["action"] == "refuse" for case in refusals)
    assert all(case["refusal_artifact_only"] for case in refusals)
    assert any(case["source_contradicts_claim"] for case in refusals)
    assert any(not case["visible_span_bound"] for case in refusals)


def test_phase6_sophia_cases_are_post_freeze_randomized_but_stable():
    first = generate_phase6_sophia_cases(
        freeze_seed="sophia-seed-a",
        capability_family_digest="sha256:" + "a" * 64,
    )
    second = generate_phase6_sophia_cases(
        freeze_seed="sophia-seed-a",
        capability_family_digest="sha256:" + "a" * 64,
    )
    other = generate_phase6_sophia_cases(
        freeze_seed="sophia-seed-b",
        capability_family_digest="sha256:" + "a" * 64,
    )

    assert first == second
    assert first != other
    assert all(case.generated_after_freeze for case in first)
    assert len({case.case_digest for case in first}) == len(first)
