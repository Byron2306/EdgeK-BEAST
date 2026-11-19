import json

from scripts.proof import run_coder_efficiency_matrix as matrix


def test_matrix_balances_and_randomizes_complete_blocks():
    plan = matrix.make_plan(("shipping", "normalize"), 2, 4317)
    assert plan == matrix.make_plan(("shipping", "normalize"), 2, 4317)
    assert len(plan) == 16
    for i in range(0, 16, 4):
        block = plan[i:i + 4]
        assert len({(row["task"], row["repeat"]) for row in block}) == 1
        assert {row["arm"] for row in block} == set(matrix.ARMS)


def test_real_worktree_matrix_scripted_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_DIRECT_CODER_INTEGRATIONS", "0")
    out = tmp_path / "report"
    assert matrix.main(["--out", str(out), "--tasks", "shipping"]) == 0
    rows = [json.loads(line) for line in (out / "attempts.jsonl").read_text().splitlines()]
    assert len(rows) == 4
    assert all(row["verified"] and row["independent_exit"] == 0 for row in rows)
    for row in rows:
        assert row["provider_attempts"] == 0
        assert row["decisions"] == (3 if row["closeout"] else 5)
        assert row["repo_hint_delivered"] == row["reporelay"]
        assert row["deterministic_closeout"] == row["closeout"]
        assert row["original_unchanged"]
        assert row["event_chain_valid"]


def test_public_success_does_not_hide_heldout_failure(tmp_path):
    import subprocess
    import sys

    task = matrix.TASKS["shipping"]
    root = tmp_path / "fixture"
    matrix.create_fixture(root, task)
    (root / task.path).write_text("def shipping_fee(total):\n    return 0 if total == 50 else 4\n")
    assert subprocess.run([sys.executable, *matrix.PUBLIC[1:]], cwd=root, capture_output=True).returncode == 0
    assert matrix.heldout(root, task)["exit"] == 1
