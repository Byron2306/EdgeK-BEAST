"""code.rename_symbol: scope-aware deterministic rename + governed action actuator."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from app.kernel.compute.governed_refactor import action_for_family, apply_action_to_copy, uses_rename_tool  # noqa: E402
from app.kernel.compute.symbol_rename import RenameError, plan_rename, rename_symbol  # noqa: E402


def _repo(tmp_path: Path) -> Path:
    files = {
        "users/__init__.py": 'from .core import fetch_user\n__all__ = ["fetch_user"]\n',
        "users/core.py": "def fetch_user(items):\n    return sum(items)\n\n\ndef other():\n    fetch_user = 3  # fetch_user local\n    return fetch_user\n",
        "users/report.py": ("from users.core import fetch_user as fu, fetch_user\nfrom users import core\nimport users.core\nimport users\n\n\n"
                            "def s(i, obj):\n    \"\"\"calls fetch_user\"\"\"\n    obj.fetch_user\n"
                            "    return fu(i) + fetch_user(i) + core.fetch_user(i) + users.core.fetch_user(i) + users.fetch_user(i)\n"),
        "users/rel.py": "from .core import fetch_user\n\n\ndef r(i):\n    return fetch_user(i)\n",
        "test_users.py": "from users.core import fetch_user\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


def test_resolves_every_reference_and_flags_strings(tmp_path):
    root = _repo(tmp_path)
    res = rename_symbol(root, "users/core.py", "fetch_user", "load_user", exclude=("test_*.py",))
    core = (root / "users/core.py").read_text()
    assert "def load_user(items)" in core and "    fetch_user = 3" in core and "return fetch_user" in core  # local untouched
    report = (root / "users/report.py").read_text()
    assert "load_user as fu, load_user" in report and "core.load_user(i)" in report and "users.load_user(i)" in report
    assert "users.core.load_user(i)" in report and '"""calls fetch_user"""' in report  # docstring flagged, not changed
    assert "obj.fetch_user" in report  # unresolvable attribute flagged only
    assert '__all__ = ["load_user"]' in (root / "users/__init__.py").read_text()
    assert "from .core import load_user" in (root / "users/rel.py").read_text()
    assert (root / "test_users.py").read_text() == "from users.core import fetch_user\n"  # excluded
    kinds = {f["kind"] for f in res["flagged"]}
    assert {"string", "unresolved_attribute", "comment"} <= kinds
    assert res["remaining_references"] == 0


def test_dry_run_writes_nothing_and_returns_diff(tmp_path):
    root = _repo(tmp_path)
    before = {p: p.read_text() for p in root.rglob("*.py")}
    res = rename_symbol(root, "users/core.py", "fetch_user", "load_user", dry_run=True)
    assert res["applied"] is False and "+def load_user" in res["diff"]
    assert {p: p.read_text() for p in root.rglob("*.py")} == before


@pytest.mark.parametrize("new", ["other", "class", "fetch_user", "9x"])
def test_refuses_conflicts_and_bad_names(tmp_path, new):
    root = _repo(tmp_path)
    with pytest.raises(RenameError):
        plan_rename(root, "users/core.py", "fetch_user", new)


def test_refuses_unknown_symbol_and_stale_plan(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(RenameError):
        plan_rename(root, "users/core.py", "nope", "x")
    plan = plan_rename(root, "users/core.py", "fetch_user", "load_user")
    (root / "users/rel.py").write_text("# edited meanwhile\n")
    from app.kernel.compute.symbol_rename import apply_rename

    with pytest.raises(RenameError):
        apply_rename(root, plan)
    assert "def fetch_user" in (root / "users/core.py").read_text()  # nothing written


def test_family_selection():
    assert uses_rename_tool("refactor-rename-symbol") and uses_rename_tool("composite-refguard")
    assert uses_rename_tool("fix-config-constant", "ImportError: cannot import name 'x' from 'a.b'")
    assert not uses_rename_tool("fix-config-constant", "AssertionError: 1 != 2")
    assert action_for_family("refactor-rename-symbol")["tool"] == "code.rename_symbol"


@pytest.mark.parametrize("name,old,new", [("ren-h1", "fetch_user", "load_user"), ("ren-h2", "make_report", "build_report"),
                                          ("ren-h3", "parse_cfg", "parse_config")])
def test_gauntlet_rename_tasks_pass_visible_and_hidden(tmp_path, name, old, new):
    import gauntlet_large as gl
    from app.kernel.compute.family_crystals import run_verify

    task = gl.TASKS[name]
    root = gl.make_repo(tmp_path, name)
    wt = tmp_path / "wt"
    out = apply_action_to_copy(root, {"renames": [{"symbol": old, "file": task["target"], "new_name": new}]}, wt)
    assert out["applied"], out
    assert run_verify(task["verify"], wt)["returncode"] == 0
    assert gl.hidden_check(wt, name)["passed"]


def test_refguard_rename_plus_guard_edit(tmp_path):
    import gauntlet_large as gl
    from app.kernel.compute.family_crystals import run_verify

    task = gl.TASKS["refguard-h1"]
    root = gl.make_repo(tmp_path, "refguard-h1")
    action = {"renames": [{"symbol": "calc_grade_mean", "file": "grades/core.py", "new_name": "compute_grade_mean"}],
              "edits": [{"path": "grades/core.py", "old_text": "    return sum(items) / len(items)",
                         "new_text": "    if not items:\n        return None\n    return sum(items) / len(items)"}]}
    out = apply_action_to_copy(root, action, tmp_path / "wt")
    assert out["applied"], out
    assert run_verify(task["verify"], tmp_path / "wt")["returncode"] == 0
    assert gl.hidden_check(tmp_path / "wt", "refguard-h1")["passed"]


def test_action_refuses_test_edits(tmp_path):
    root = _repo(tmp_path)
    out = apply_action_to_copy(root, {"renames": [], "edits": [{"path": "test_users.py", "old_text": "a", "new_text": "b"}]}, tmp_path / "wt")
    assert not out["applied"]


@pytest.mark.parametrize("old_text", ["def calc_grade_mean(items):\n    return sum(items) / len(items)",
                                      "def compute_grade_mean(items):\n    return sum(items) / len(items)"])
def test_edits_rebased_onto_renamed_tree_and_pure_rename_edits_dropped(tmp_path, old_text):
    import gauntlet_large as gl

    root = gl.make_repo(tmp_path, "refguard-h1")
    guard = old_text.replace("    return sum", "    if not items:\n        return None\n    return sum")
    action = {"renames": [{"symbol": "calc_grade_mean", "file": "grades/core.py", "new_name": "compute_grade_mean"}],
              "edits": [{"path": "grades/report.py", "old_text": "from grades.core import calc_grade_mean",
                         "new_text": "from grades.core import compute_grade_mean"},
                        {"path": "grades/core.py", "old_text": old_text, "new_text": guard}]}
    out = apply_action_to_copy(root, action, tmp_path / "wt")
    assert out["applied"], out
    assert gl.hidden_check(tmp_path / "wt", "refguard-h1")["passed"]
