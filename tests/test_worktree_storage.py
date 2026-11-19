import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.kernel.agents.tool_runtime import local_binding_error
from app.kernel.workspaces.worktree_forge import WorktreeForge


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.delenv("BEAST_WORKTREE_ROOT", raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(root, "add", "app.py")
    git(root, "-c", "user.email=test@example.test", "-c", "user.name=Test", "commit", "-qm", "fixture")
    return root


def identity(task):
    return tuple(task[key] for key in ("worktree_path", "task_id", "branch", "base_commit"))


def test_external_checkout_and_existing_registry_survive_config_changes(repo, tmp_path, monkeypatch):
    legacy = WorktreeForge(repo).create(objective="legacy")["task"]
    outside = tmp_path / "external"
    monkeypatch.setenv("BEAST_WORKTREE_ROOT", str(outside))
    result = WorktreeForge(repo).create(objective="external")
    assert result["ok"], result["task"].get("error")
    task = result["task"]
    path = Path(task["worktree_path"])
    assert path.is_relative_to(outside)
    assert (path / "app.py").read_text() == "value = 1\n"
    assert {row["task_id"] for row in WorktreeForge(path).list()["tasks"]} == {
        task["task_id"], legacy["task_id"],
    }
    assert (repo / ".beast/worktrees/tasks.json").is_file()
    assert local_binding_error(repo, identity(legacy)) == ""
    assert local_binding_error(repo, identity(task)) == ""

    monkeypatch.delenv("BEAST_WORKTREE_ROOT")
    assert local_binding_error(repo, identity(task)) == ""


def test_external_binding_cannot_point_to_an_unregistered_copy(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_WORKTREE_ROOT", str(tmp_path / "external"))
    forge = WorktreeForge(repo)
    task = forge.create(objective="external")["task"]
    assert local_binding_error(repo, identity(task)) == ""
    path = Path(task["worktree_path"])
    moved = tmp_path / "unregistered" / path.name
    moved.parent.mkdir()
    shutil.copytree(path, moved)

    # Even a matching registry/checkpoint pair cannot use an unregistered path.
    task["worktree_path"] = str(moved)
    forge.registry_path.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    assert local_binding_error(repo, identity(task)).startswith("STALE_WORKTREE_BINDING")


def test_low_space_on_destination_creates_no_checkout_or_branch(repo, tmp_path, monkeypatch):
    outside = tmp_path / "external"
    monkeypatch.setenv("BEAST_WORKTREE_ROOT", str(outside))
    real_usage = shutil.disk_usage

    def disk_usage(path):
        if Path(path).resolve().is_relative_to(outside):
            return type(real_usage(repo))(10 << 30, (10 << 30) - (100 << 20), 100 << 20)
        return real_usage(path)

    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    before = git(repo, "worktree", "list", "--porcelain")
    forge = WorktreeForge(repo)
    real_git = forge._git

    def git_without_checkout(args, **kwargs):
        assert args[:2] != ["worktree", "add"], "low space must not launch checkout"
        return real_git(args, **kwargs)

    monkeypatch.setattr(forge, "_git", git_without_checkout)
    result = forge.create(objective="no space")
    assert not result["ok"]
    task = result["task"]
    assert "insufficient free space" in task["error"]
    assert str(outside) in task["error"]
    assert not Path(task["worktree_path"]).exists()
    assert git(repo, "worktree", "list", "--porcelain") == before
    assert git(repo, "branch", "--list", "beast/*") == ""
