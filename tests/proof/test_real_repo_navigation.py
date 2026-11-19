import json

import pytest

from scripts.proof import run_coder_efficiency_matrix as matrix


def test_real_repo_plan_is_paired_and_prebound():
    plan = matrix.make_plan(("package_name",), 4, 4325, experiment="real-repo-navigation")
    assert len(plan) == 8
    assert {row["repeat"] for row in plan} == {1, 2, 3, 4}
    for i in range(0, len(plan), 2):
        assert {row["arm"] for row in plan[i:i+2]} == {"file_list", "graph"}
        assert plan[i]["repeat"] == plan[i+1]["repeat"]
        assert all(row["prebind"] and row["closeout"] and not row["reporelay"] for row in plan[i:i+2])


def test_graph_warm_lookup_uses_same_index_and_exposes_edges(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "a.py").write_text("from b import foo\n\ndef bar():\n    return foo()\n")
    (root / "b.py").write_text("def foo():\n    return 1\n")
    db = tmp_path / "index.sqlite3"
    packet = matrix.build_graph_packet(root, ["a.py", "b.py"], "graph", db, real_repo=True, objective="foo")
    assert json.loads(packet["sent"])["edges"] == [{"from": "a.py", "to": "b.py"}]
    assert packet["navigation"]["cold_index_seconds"] is not None
    assert packet["navigation"]["indexed_snapshot_lookup_seconds"] is not None
    with pytest.raises(FileExistsError):
        matrix.build_graph_packet(root, ["a.py", "b.py"], "graph", db, real_repo=True, objective="foo")


def test_warm_replay_summary_counts_one_file_list_graph_pair():
    rows = [
        {"task": "package_name", "repeat": 1, "arm": arm, "state": "completed", "verified": True,
         "provider_attempts": n, "wall_seconds": float(n)}
        for arm, n in (("file_list", 3), ("graph", 2))
    ]
    summary = matrix.summarize(rows, "nim", experiment="real-repo-navigation")
    pair, = summary["paired_against_file_list"]
    assert pair["arm"] == "graph"
    assert pair["deltas"]["provider_attempts"] == -1
    assert pair["deltas"]["prompt_tokens_observed"] is None
