from app.kernel.skill_tree import SkillTree


def test_skill_tree_mines_generates_validates_and_promotes_candidate(tmp_path):
    tree = SkillTree(data_dir=str(tmp_path))
    sequences = [
        ["read_file", "edit_file", "pytest"],
        ["read_file", "edit_file", "pytest"],
        ["read_file", "edit_file", "pytest"],
    ]

    mining = tree.mine(
        sequences=sequences,
        min_length=2,
        min_frequency=3,
        use_approximate=False,
    )
    generated = tree.generate_candidates(min_frequency=3, min_confidence=0.1)

    assert mining["status"] == "success"
    assert mining["patterns_detected"] >= 1
    assert generated["generated"] >= 1

    candidate = generated["candidates"][0]
    validation = tree.validate_candidate(candidate["candidate_id"])
    promotion = tree.promote_candidate(candidate["candidate_id"], approved_by="tester")

    assert validation["status"] in ("passed", "passed_with_warnings")
    assert promotion["promoted"] is True
    assert promotion["skill"]["category"] == "meta_tool"
    assert tree.list_skills(category="meta_tool")[0]["id"] == promotion["skill"]["id"]


def test_skill_tree_requires_validation_before_promotion(tmp_path):
    tree = SkillTree(data_dir=str(tmp_path))
    tree.mine(
        sequences=[
            ["grep", "read_file"],
            ["grep", "read_file"],
        ],
        min_frequency=2,
        use_approximate=False,
    )
    generated = tree.generate_candidates(min_frequency=2, min_confidence=0.1)
    candidate_id = generated["candidates"][0]["candidate_id"]

    try:
        tree.promote_candidate(candidate_id, approved_by="tester")
    except ValueError as exc:
        assert "sandbox validation" in str(exc)
    else:
        raise AssertionError("Expected validation gate to block promotion")
