from app.kernel.dai.phase6_deterministic_arena import generate_phase6_cases, run_phase6_arena


def test_phase6_arena_proves_provider_displacement_and_semantic_correctness():
    receipt = run_phase6_arena(freeze_seed="phase6-test-freeze")

    assert receipt["green"] is True
    assert receipt["case_count"] == 9
    assert receipt["family_count"] == 3
    assert receipt["post_freeze_randomized_cases"] is True
    assert receipt["provider_calls_before_promotion"] == 3
    assert receipt["provider_calls_after_promotion"] == 0
    assert receipt["provider_call_displacement"] == 3
    assert receipt["semantic_correct_count"] == 9
    assert receipt["text_visual_joined_green_count"] == 9
    assert receipt["production_authority_allowed"] is False
    assert receipt["execution_authority_allowed"] is False


def test_phase6_arena_contains_refusal_holdouts_and_zero_provider_reuse():
    receipt = run_phase6_arena(freeze_seed="phase6-test-freeze")

    heldout = [case for case in receipt["case_receipts"] if not case["first_exposure"]]
    refusals = [case for case in receipt["case_receipts"] if case["expected_action"] == "refuse"]

    assert heldout
    assert all(case["provider_calls_used"] == 0 for case in heldout)
    assert refusals
    assert all(case["action"] == "refuse" and case["refusal_artifact_only"] for case in refusals)
    assert all(case["semantic_correct"] for case in receipt["case_receipts"])


def test_phase6_case_generation_is_randomized_but_deterministic_from_freeze_seed():
    first = generate_phase6_cases(freeze_seed="phase6-seed-a")
    second = generate_phase6_cases(freeze_seed="phase6-seed-a")
    other = generate_phase6_cases(freeze_seed="phase6-seed-b")

    assert first == second
    assert first != other
    assert len({case.case_digest for case in first}) == len(first)
    assert all(case.generated_after_freeze for case in first)
