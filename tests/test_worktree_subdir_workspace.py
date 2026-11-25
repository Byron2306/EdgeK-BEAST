"""A TLI workspace that is a subfolder with untracked files must be editable in a worktree.

Regression for run agent-a615d0b5-f6328f73c9be: workspace .../EdgeK-BEAST/tester,
file `beast` untracked, worktree.read_file('beast') -> "worktree file not found".
"""
import asyncio
import subprocess
from pathlib import Path

from app.kernel.agents.tool_models import ToolExecutionContext
from app.kernel.agents import worktree_tools as wt


class Store:
    def __init__(self):
        self.run = {"run_id": "agent-sub", "checkpoint": {}}

    def get_run(self, run_id):
        return self.run


class Engine:
    def __init__(self):
        self.store = Store()

    def merge_checkpoint(self, run_id, payload):
        self.store.run["checkpoint"].update(payload)
        return self.store.run

    def emit(self, *a, **k):
        return {}


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_untracked_subdir_file_is_seeded_and_paths_map(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "tester").mkdir(parents=True)
    (repo / "README").write_text("x\n")
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "README")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    (repo / "tester" / "beast").write_text("def main():\n    return 1\n")
    (repo / "tester" / ".beast").mkdir()
    (repo / "tester" / ".beast" / "secret.env").write_text("NOPE=1\n")

    engine = Engine()
    ctx = ToolExecutionContext(run_id="agent-sub", workspace_root=str(repo / "tester"), engine=engine)
    bound = asyncio.run(wt._worktree_bind({"objective": "edit beast", "task_id": "agent-sub"}, ctx))
    assert bound["workspace_prefix"] == "tester"
    assert bound["seeded_untracked_files"] == ["tester/beast"]
    root = Path(bound["worktree_root"])
    assert (root / "tester" / "beast").is_file()
    assert not (root / "tester" / ".beast").exists()

    ctx2 = ToolExecutionContext(run_id="agent-sub", workspace_root=str(repo / "tester"),
                                worktree_root=str(root), engine=engine)
    read = asyncio.run(wt._worktree_read_file({"path": "beast", "start_line": 1}, ctx2))
    assert "def main" in read["content"]
    edited = asyncio.run(wt._worktree_replace_exact(
        {"path": "beast", "old_text": "return 1", "new_text": "return 2"}, ctx2))
    assert edited["path"] == "tester/beast"
    # Only the agent's edit shows in the diff, not the whole seeded file.
    assert "-    return 1" in edited["diff"] and "+    return 2" in edited["diff"]
    assert "+def main" not in edited["diff"]
    # The operator's real file is untouched.
    assert "return 1" in (repo / "tester" / "beast").read_text()
