from pathlib import Path
import subprocess
import pytest
from app.kernel.agents.run_store import AgentRunStore
from app.kernel.operations_console.worktree_console import WorktreeChangesDiffConsole


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


def seed(tmp_path: Path):
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "BEAST Test")
    (tmp_path / "app.py").write_text("print('old')\n")
    git(tmp_path, "add", "app.py"); git(tmp_path, "commit", "-m", "base")
    store=AgentRunStore(tmp_path); store.create_run(session_id="s", objective="edit", run_id="run-59", mode="agent")
    base=git(tmp_path,"rev-parse","HEAD")
    store.checkpoint("run-59", {"worktree":{"path":str(tmp_path),"base_commit":base},"sourceplan":{"status":"ready","promotion_ready":True}})
    return "run-59"


def test_modified_file_and_exact_diff(tmp_path):
    rid=seed(tmp_path); (tmp_path/"app.py").write_text("print('new')\n")
    c=WorktreeChangesDiffConsole(tmp_path).build(rid)
    assert c["summary"]["modified"]==1
    assert "-print('old')" in c["files"][0]["diff"]["patch"]
    assert "+print('new')" in c["files"][0]["diff"]["patch"]


def test_untracked_file_is_reviewable(tmp_path):
    rid=seed(tmp_path); (tmp_path/"new.py").write_text("x=1\n")
    c=WorktreeChangesDiffConsole(tmp_path).build(rid)
    assert c["files"][0]["change_type"]=="UNTRACKED"
    assert "+x=1" in c["files"][0]["diff"]["patch"]


def test_prohibited_path_blocks_promotion_readiness(tmp_path):
    rid=seed(tmp_path); (tmp_path/".env").write_text("TOKEN=secret\n")
    c=WorktreeChangesDiffConsole(tmp_path).build(rid)
    assert c["files"][0]["prohibited"]
    assert not c["sourceplan"]["promotion_ready"]
    assert "prohibited_paths" in c["sourceplan"]["blocked_reasons"]


def test_stale_base_blocks_promotion(tmp_path):
    rid=seed(tmp_path); (tmp_path/"app.py").write_text("print('new')\n")
    git(tmp_path,"add","app.py"); git(tmp_path,"commit","-m","move head")
    (tmp_path/"app.py").write_text("print('newer')\n")
    c=WorktreeChangesDiffConsole(tmp_path).build(rid)
    assert c["worktree"]["stale_base"]
    assert not c["sourceplan"]["promotion_ready"]


def test_filter_by_change_type(tmp_path):
    rid=seed(tmp_path); (tmp_path/"app.py").write_text("print('new')\n"); (tmp_path/"new.py").write_text("x=1\n")
    c=WorktreeChangesDiffConsole(tmp_path).build(rid, change_type="MODIFIED")
    assert len(c["files"])==1 and c["files"][0]["path"]=="app.py"


def test_query_filter(tmp_path):
    rid=seed(tmp_path); (tmp_path/"app.py").write_text("print('new')\n"); (tmp_path/"other.py").write_text("x=1\n")
    c=WorktreeChangesDiffConsole(tmp_path).build(rid, query="other.py")
    assert [x["path"] for x in c["files"]]==["other.py"]


def test_invalid_change_type_denied(tmp_path):
    rid=seed(tmp_path)
    with pytest.raises(ValueError): WorktreeChangesDiffConsole(tmp_path).build(rid, change_type="BANANA")


def test_unknown_run_denied(tmp_path):
    git(tmp_path,"init")
    with pytest.raises(KeyError): WorktreeChangesDiffConsole(tmp_path).build("missing")


def test_tamper_detection_and_read_only_authority(tmp_path):
    rid=seed(tmp_path); c=WorktreeChangesDiffConsole(tmp_path).build(rid)
    assert c["authority"]=="worktree_diff_console_read_only"
    assert not c["grants_promotion_authority"]
    c["grants_promotion_authority"]=True
    assert not WorktreeChangesDiffConsole(tmp_path).verify(c)


def test_frontend_panel_present():
    html=Path("app/frontend/index.html").read_text()
    assert "PHASE5_9_WORKTREE_DIFF_CONSOLE" in html
    assert "worktreeDiffConsolePanel" in html
