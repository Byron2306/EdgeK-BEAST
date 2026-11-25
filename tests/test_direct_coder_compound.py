import pytest

from app.kernel.compute.direct_coder_compound import (
    CompoundFragmentError,
    MergeNode,
    compose_fragments,
    fragment_from_legacy_plan,
)


def test_independent_fragments_compose_into_multifile_plan():
    a = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 1\n"}},
        fragment_id="fragment-a",
        producer="crystal-a",
        provenance_lane="implementation",
    )
    b = fragment_from_legacy_plan(
        {
            "edits": [{
                "path": "pkg/b.py",
                "old": "B = 1",
                "new": "B = 2",
            }]
        },
        fragment_id="fragment-b",
        producer="crystal-b",
        provenance_lane="verification-repair",
        requires=("fragment-a",),
    )

    plan = compose_fragments([a, b])

    assert plan["legacy_plan"]["rewrite"] == {
        "pkg/a.py": "A = 1\n"
    }
    assert plan["legacy_plan"]["edits"][0]["path"] == "pkg/b.py"
    assert plan["paths"] == ["pkg/a.py", "pkg/b.py"]
    assert plan["provenance_lanes"] == [
        "implementation",
        "verification-repair",
    ]
    assert plan["dependency_edges"] == ["fragment-a->fragment-b"]
    assert plan["plan_digest"].startswith("sha256:")


def test_overlap_is_refused_without_explicit_merge():
    a = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 1\n"}},
        fragment_id="a",
        producer="producer-a",
        provenance_lane="lane-a",
    )
    b = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 2\n"}},
        fragment_id="b",
        producer="producer-b",
        provenance_lane="lane-b",
    )

    with pytest.raises(
        CompoundFragmentError,
        match="explicit merge node",
    ):
        compose_fragments([a, b])


def test_overlap_requires_exact_provenance_bound_merge():
    a = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 1\n"}},
        fragment_id="a",
        producer="producer-a",
        provenance_lane="lane-a",
    )
    b = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 2\n"}},
        fragment_id="b",
        producer="producer-b",
        provenance_lane="lane-b",
    )

    merged = compose_fragments(
        [a, b],
        merge_nodes=[
            MergeNode(
                path="pkg/a.py",
                input_fragment_ids=("a", "b"),
                rewrite="A = 3\n",
            )
        ],
    )

    assert merged["legacy_plan"]["rewrite"]["pkg/a.py"] == "A = 3\n"
    assert len(merged["merges"]) == 1
    assert merged["merges"][0]["merge_digest"].startswith("sha256:")


def test_merge_with_wrong_inputs_is_refused():
    a = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 1\n"}},
        fragment_id="a",
        producer="a",
        provenance_lane="one",
    )
    b = fragment_from_legacy_plan(
        {"rewrite": {"pkg/a.py": "A = 2\n"}},
        fragment_id="b",
        producer="b",
        provenance_lane="two",
    )

    with pytest.raises(
        CompoundFragmentError,
        match="merge provenance mismatch",
    ):
        compose_fragments(
            [a, b],
            merge_nodes=[
                MergeNode(
                    path="pkg/a.py",
                    input_fragment_ids=("a", "wrong"),
                    rewrite="A = 3\n",
                )
            ],
        )


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/tmp/escape.py",
        "",
    ],
)
def test_unsafe_paths_refused(path):
    with pytest.raises(CompoundFragmentError):
        fragment_from_legacy_plan(
            {"rewrite": {path: "bad"}},
            fragment_id="bad",
            producer="bad",
            provenance_lane="bad",
        )
