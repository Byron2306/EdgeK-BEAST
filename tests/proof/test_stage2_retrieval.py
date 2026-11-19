import json

from scripts.proof import run_coder_efficiency_matrix as matrix
from scripts.proof.retrieval_ablation import build_retrieval


def test_retrieval_arms_share_a_corpus_and_measure_first_turn_bytes(tmp_path):
    (tmp_path / "helper.py").write_text("def normalization(value):\n    return value.lower()\n")
    (tmp_path / "other.py").write_text("def calculate(price):\n    return price + 2\n")
    (tmp_path / "test_public.py").write_text("ORACLE_DO_NOT_DELIVER = 42\n")
    paths = ["helper.py", "other.py", "test_public.py"]
    results = [build_retrieval(tmp_path, paths, arm, "repair normalization")
               for arm in ("file_list", "lexical", "vector")]
    assert len({r["corpus_sha256"] for r in results}) == 1
    assert results[0]["chunks"] == []
    assert all(r["chunks"][0]["path"] == "helper.py" for r in results[1:])
    assert results[2]["backend"] == "local_lsa_tfidf_cosine"
    for r in results:
        payload = json.dumps(r["chunks"], ensure_ascii=False).encode()
        assert len(payload) <= 1800
        assert b"ORACLE_DO_NOT_DELIVER" not in payload


def test_stage2_plan_is_paired_and_has_no_graph_tool():
    rows = matrix.make_plan(("package_name",), 1, 4327, experiment="retrieval-ablation")
    assert {r["arm"] for r in rows} == {"file_list", "lexical", "vector"}
    assert all(r["prebind"] and r["closeout"] and r["graph_packet"] == "file_list" for r in rows)
    assert not any(r.get("graph_on_demand") for r in rows)


def test_memory_hull_recall_requires_current_scope_and_unmodified_body():
    from scripts.proof.retrieval_ablation import memory_controls

    report = memory_controls()
    assert report["passed"]
    assert report["checks"] == {
        "current_accepted": True, "stale_excluded": True,
        "other_repo_excluded": True, "tampered_not_returned": True,
    }
