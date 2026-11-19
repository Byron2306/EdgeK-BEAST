
import pytest

from scripts.proof import run_coder_efficiency_matrix as matrix
from scripts.proof.bounded_worktree_graph import BoundedWorktreeGraph


def test_lookup_is_lazy_and_scope_bound(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.py").write_text("from b import nice\n\ndef entry():\n    return nice()\n")
    (root / "b.py").write_text("def nice():\n    return 1\n")
    db = tmp_path / "graph.sqlite3"
    helper = BoundedWorktreeGraph(root, {"a.py", "b.py"}, db)
    assert helper.stats()["graph_index_builds"] == 0
    assert not db.exists()
    with pytest.raises(ValueError):
        helper.lookup("../private.py")
    assert not db.exists()
    hit = helper.lookup("a.py")
    assert {"from": "a.py", "to": "b.py"} in hit["edges"]
    assert len(matrix.canonical(hit)) <= 1200
    hit = helper.lookup("nice")
    assert hit["files"] == ["b.py"]
    assert helper.stats()["graph_index_builds"] == 1
    assert helper.stats()["graph_lookup_requests"] == 3
    with pytest.raises(ValueError, match="lookup limit"):
        helper.lookup("b.py")


def test_plan_first_packets_are_both_file_lists():
    rows = matrix.make_plan(("package_name", "compatible_identity"), 2, 4326,
                            experiment="graph-on-demand")
    assert len(rows) == 8
    for start in range(0, len(rows), 2):
        pair = rows[start:start + 2]
        assert {row["arm"] for row in pair} == {"file_list", "on_demand"}
        assert all(row["prebind"] and row["graph_packet"] == "file_list" and row["closeout"] for row in pair)
        assert sum(row["arm"] == "on_demand" and row["graph_on_demand"] for row in pair) == 1


def test_lookup_refuses_mutated_worktree_without_building(tmp_path):
    (tmp_path / "a.py").write_text("value = 1\n")
    db = tmp_path / "index.sqlite3"
    helper = BoundedWorktreeGraph(tmp_path, {"a.py"}, db)
    with pytest.raises(ValueError, match="initial worktree revision"):
        helper.lookup("a.py", pristine=False)
    assert not db.exists()
    assert helper.stats()["graph_index_builds"] == 0
