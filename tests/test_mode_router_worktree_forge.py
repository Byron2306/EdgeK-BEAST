import subprocess

from app.cli.api import BeastApiClient
from app.kernel.agents.mode_router import ModeRouter
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.workspaces.worktree_forge import WorktreeForge
from app.mcp.runtime import BeastToolRuntime


def test_mode_router_selects_bounded_modes_and_tool_decisions():
    router = ModeRouter()

    route = router.select(phase="implement", risk="medium", provider="demo")
    scout_decision = router.tool_allowed("scout", "beast_sourceplan_apply_selected", "sourceplan")
    implementer_decision = router.tool_allowed("implementer", "beast_symbol_surgeon_plan", "sourceplan")

    assert route["selected_mode"] == "implementer"
    assert route["definition"]["tool_profile"] == "edit"
    assert scout_decision["allowed"] is False
    assert scout_decision["policy_gate"]["decision"] == "block"
    assert implementer_decision["allowed"] is True
    assert implementer_decision["policy_gate"]["decision"] == "allow"
    assert "implementer" in route["transition_path"]


def test_sourceplan_scorecard_includes_mode_and_worktree_recommendation(tmp_path):
    for name in ["a.py", "b.py", "c.py", "d.py"]:
        (tmp_path / name).write_text("value = 'old'\n", encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "kind": "beast_source_patch_plan",
        "operations": [
            {
                "id": f"op_{name}",
                "path": name,
                "op": "replace_exact",
                "old_text": "old",
                "new_text": "new",
                "selected": True,
            }
            for name in ["a.py", "b.py", "c.py", "d.py"]
        ],
    }

    scorecard = client.sourceplan_scorecard(plan).data

    assert scorecard["mode_route"]["selected_mode"] in {"architect", "implementer", "reviewer"}
    assert scorecard["worktree_recommendation"]["recommended"] is True
    assert scorecard["policy_gate_result"]["worktree_required"] is True
    assert "multi-file edit" in scorecard["worktree_recommendation"]["reasons"]


def test_worktree_forge_create_status_and_archive(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "beast@example.local"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    forge = WorktreeForge(tmp_path)

    created = forge.create(objective="isolate edit", risk="high", task_id="isolate-edit")
    task_id = created["task"]["task_id"]
    listed = forge.list()
    status = forge.status(task_id)
    tested = forge.test(task_id, command=["python3", "-c", "print('ok')"])
    worktree_path = created["task"]["worktree_path"]
    (tmp_path / ".beast" / "worktrees").mkdir(parents=True, exist_ok=True)
    with open(f"{worktree_path}/app.py", "w", encoding="utf-8") as handle:
        handle.write("value = 2\n")
    subprocess.run(["git", "add", "app.py"], cwd=worktree_path, check=True)
    subprocess.run(["git", "commit", "-m", "change value"], cwd=worktree_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    draft = forge.sourceplan_draft_from_diff(task_id)
    promote_blocked = forge.promote(task_id, approved=False, require_tests=False)
    archived = forge.archive(task_id, reason="test done")
    evidence = EvidenceBus(tmp_path).summary()

    assert created["ok"] is True
    assert listed["count"] == 1
    assert status["exists"] is True
    assert tested["ok"] is True
    assert draft["ok"] is True
    assert draft["plan"]["source"] == "worktree_native_mission"
    assert draft["plan"]["requires_operator_translation"] is False
    assert "app.py" in draft["plan"]["files"]
    assert "value = 2" in draft["plan"]["worktree_diff"]
    assert draft["plan"]["operations"][0]["op"] == "replace_exact"
    assert draft["plan"]["operations"][0]["old_text"] == "value = 1\n"
    assert draft["plan"]["operations"][0]["new_text"] == "value = 2\n"
    assert draft["plan"]["selected_operations"] == [draft["plan"]["operations"][0]["op_id"]]
    assert promote_blocked["decision"] == "blocked"
    assert "approval" in promote_blocked["reason"]
    assert archived["task"]["status"] == "archived"
    assert evidence["by_type"]["beast_worktree_forge_receipt"] == 3
    assert evidence["by_type"]["beast_worktree_test_receipt"] == 1


def test_mcp_mode_and_worktree_tools_respect_profiles(monkeypatch):
    monkeypatch.setenv("BEAST_MCP_TOOLS", "readonly")
    readonly = {tool["name"] for tool in BeastToolRuntime().tool_definitions()}
    monkeypatch.setenv("BEAST_MCP_TOOLS", "edit")
    edit = {tool["name"] for tool in BeastToolRuntime().tool_definitions()}

    assert "beast_mode_router_select" in readonly
    assert "beast_worktree_list" in readonly
    assert "beast_worktree_create" not in readonly
    assert "beast_worktree_promote" not in readonly
    assert "beast_worktree_create" in edit
    assert "beast_worktree_promote" in edit
