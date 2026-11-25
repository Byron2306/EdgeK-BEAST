"""OpenCode wins (Byron t211u): arg repair, invalid tool, doom loop, pinned history + step-limit
summary, todowrite, scope diagnostics, output trimming, flat tool names, plan vs build."""
import asyncio
import subprocess
import sys

from app.kernel.agents import direct_coder_runtime as dcr
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from tests.test_direct_coder_act_phase import EditEngine, Model
from tests.test_direct_coder_runtime import tool

BUGGY = '''#!/usr/bin/env python3
import os
from pathlib import Path

ROOT = Path(".")


def _is_safe_path(target: Path) -> bool:
    try:
        target.resolve().relative_to(workspace)
        return True
    except ValueError:
        return False


def command_reinstall_surfaces(args):
    workspace = Path(args.workspace or os.environ.get("BEAST_WORKSPACE") or ROOT).resolve()
    return _is_safe_path(workspace / "x")
'''


def schemas():
    return [{"tool_id": t, "input_schema": {"type": "object", "additionalProperties": False, "properties": p}}
            for t, p in {
                "worktree.read_file": {"path": {"type": "string"}, "start_line": {"type": "integer"},
                                       "line_count": {"type": "integer"}},
                "workspace.read_range": {"path": {"type": "string"}, "start_line": {"type": "integer"},
                                         "line_count": {"type": "integer"}},
                "worktree.search_text": {"path": {"type": "string"}, "query": {"type": "string"},
                                         "limit": {"type": "integer"}},
                "workspace.list": {"path": {"type": "string"}},
                "worktree.replace_exact": {"path": {"type": "string"}, "old_text": {"type": "string"},
                                           "new_text": {"type": "string"}},
                "worktree.verify": {"command": {"type": "array"}, "timeout_seconds": {"type": "integer"}},
                "worktree.bind": {"objective": {"type": "string"}},
            }.items()]


def run_turns(coder, n):
    async def go():
        snap = None
        for _ in range(n):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] in {"completed", "paused"}:
                break
        return snap
    return asyncio.run(go())


# (a) schema repair for every tool
def test_schema_repair_renames_coerces_drops_and_notes():
    schema = {"additionalProperties": False, "properties": {
        "path": {"type": "string"}, "start_line": {"type": "integer"}, "line_count": {"type": "integer"},
        "command": {"type": "array"}, "case_sensitive": {"type": "boolean"}}}
    args, notes = dcr._repair_arguments("x", {"filePath": "a.py", "offset": "10", "limit": 5.0,
                                              "command": "python -m pytest -q", "case_sensitive": "False",
                                              "bogus": 1}, schema)
    assert args == {"path": "a.py", "start_line": 10, "line_count": 5,
                    "command": ["python", "-m", "pytest", "-q"], "case_sensitive": False}
    assert "dropped unknown argument bogus" in notes and "renamed argument filePath -> path" in notes


def test_arg_repair_note_is_attached_to_the_tool_result():
    engine = EditEngine()
    engine.tool_registry.list = schemas
    model = Model([tool("worktree.bind", {"objective": "x"}),
                   tool("worktree.read_file", {"path": "tester/beast", "offset": "1", "limit": "10", "why": "x"})])
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    run_turns(coder, 2)
    obs = engine.store.run["checkpoint"]["direct_coder"]["observations"]
    repaired = [o for o in obs if o.get("arg_repair")]
    assert repaired and any("start_line" in n for n in repaired[-1]["arg_repair"])
    assert ("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 10}) in engine.calls


# (b) invalid tool fallback
def test_unknown_tool_is_a_folded_invalid_result_not_a_rejection():
    engine = EditEngine()
    engine.tool_registry.list = schemas
    model = Model([tool("frobnicate", {"x": 1}),
                   tool("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 5})])
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    run_turns(coder, 2)  # turn 1: harness bind; turn 2: invalid tool folded, then the read
    st = engine.store.run["checkpoint"]["direct_coder"]
    invalid = [o for o in st["observations"] if o.get("tool_id") == "invalid"]
    assert invalid and "worktree.read_file" in invalid[0]["result"]["error"]
    assert "read" in invalid[0]["result"]["flat_tools"]
    assert "agent.coder.tool_rejected" not in [e for e, _ in engine.events]
    assert len(model.prompts) == 2 and engine.calls[-1][0] == "worktree.read_file"
    assert int(st["turn"]) == 2  # the invalid call was folded: the read ran in the same turn


# (c) doom loop, beyond reads
def test_three_identical_calls_trigger_doom_loop_for_any_tool():
    engine = EditEngine()
    engine.tool_registry.list = schemas
    verify = tool("worktree.verify", {"command": ["python", "-c", "print(1)"]})
    model = Model([tool("worktree.bind", {"objective": "x"}), verify, verify, verify,
                   PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="done")])
    coder = DirectCoderRuntime(engine, model, max_turns=12)
    run_turns(coder, 6)
    assert [t for t, _ in engine.calls].count("worktree.verify") == 2
    assert "agent.coder.doom_loop" in [e for e, _ in engine.events]


# (d) pinned suggestions + step-limit summary
class Store:
    def __init__(self, runs):
        self.runs = runs

    def list_runs(self, session_id="", limit=8, state=""):
        return list(self.runs)[:limit]


def test_session_history_pins_the_detailed_suggestions_beyond_the_window():
    engine = EditEngine()
    detailed = "1. Fix `command_x` lines 10-20\n2. Guard `load_y`\n3. Add `--z`\n"
    runs = [{"run_id": "r0", "created_at": 0, "objective": "suggest 3"}]
    runs += [{"run_id": f"r{i}", "created_at": i, "objective": f"follow-up {i}"} for i in range(1, 7)]
    answers = {"r0": detailed}
    coder = DirectCoderRuntime(engine, Model([]), max_turns=8)
    coder._final_answer = lambda prior: answers.get(prior["run_id"], f"answer {prior['run_id']}")
    engine.store.list_runs = Store(runs).list_runs
    history = coder._session_history({"run_id": "now", "session_id": "s", "created_at": 99, "request": {}})
    assert history[1]["content"] == detailed and history[0]["content"] == "suggest 3"
    assert history[-1]["content"] == "answer r6"


def test_step_limit_switches_tools_off_and_summarises_done_and_left():
    engine = EditEngine()
    read = lambda n: tool("worktree.read_file", {"path": "tester/beast", "start_line": n, "line_count": 3})
    model = Model([tool("worktree.bind", {"objective": "x"}), read(1), read(10), read(20), read(30)])
    coder = DirectCoderRuntime(engine, model, max_turns=4)
    snap = run_turns(coder, 6)
    done = [p for e, p in engine.events if e == "agent.coder.completed"]
    assert snap["state"] == "completed" and "step limit" in done[-1]["summary"]
    assert "Left: 1." in done[-1]["summary"] and "continue" in done[-1]["summary"]


# (e) todowrite + continue
def test_todowrite_rewrites_checklist_and_continue_resumes_it():
    engine = EditEngine()
    model = Model([
        tool("worktree.bind", {"objective": "x"}),
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="todowrite", arguments={"todos": [
            {"content": "Add --version flag", "status": "completed"},
            {"content": "Add --quiet flag", "status": "cancelled"},
            {"content": "Write tests", "status": "pending"}]}, summary="plan"),
        tool("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 5}),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    run_turns(coder, 2)
    st = engine.store.run["checkpoint"]["direct_coder"]
    assert [(i["title"], i.get("done"), bool(i.get("skipped"))) for i in st["checklist"]] == [
        ("Add --version flag", True, False), ("Add --quiet flag", False, True), ("Write tests", False, False)]
    prior = {"run_id": "p", "created_at": 1, "checkpoint": {"direct_coder": {"checklist": st["checklist"]}}}
    engine2 = EditEngine()
    engine2.store.list_runs = Store([prior]).list_runs
    coder2 = DirectCoderRuntime(engine2, Model([]), max_turns=8)
    resumed = coder2._previous_checklist({"run_id": "now", "session_id": "s"})
    assert dcr._render_checklist(resumed).count("NEXT: item 3") == 1


# (f) scope diagnostics
def test_scope_check_flags_a_helper_using_another_functions_local():
    messages, checked = dcr._scope_diagnostics(BUGGY, (8, 13))
    assert checked == {"_is_safe_path"} and len(messages) == 1
    assert "undefined name 'workspace' in _is_safe_path()" in messages[0] and messages[0].startswith("line 10")
    fixed = BUGGY.replace("relative_to(workspace)", "relative_to(ROOT)")
    assert dcr._scope_diagnostics(fixed, (8, 13))[0] == []
    assert dcr._scope_diagnostics(BUGGY, (16, 18))[0] == []  # the caller is fine


def test_edit_result_carries_diagnostics_and_auto_verify_fails_on_scope_errors(tmp_path):
    (tmp_path / "tester").mkdir()
    target = tmp_path / "tester" / "beast"
    target.write_text(BUGGY.replace("relative_to(workspace)", "relative_to(ROOT)"))
    engine = EditEngine()
    engine.store.run["checkpoint"]["worktree_root"] = str(tmp_path)
    coder = DirectCoderRuntime(engine, Model([]), max_turns=8)
    target.write_text(BUGGY)
    state = {"path_prefix": "tester"}
    new_text = "        target.resolve().relative_to(workspace)\n"
    diags = coder._edit_diagnostics("agent-test", state, "beast", new_text)
    assert diags and "workspace" in diags[0] and state["edited_funcs"]["beast"] == ["_is_safe_path"]
    cmd = dcr._auto_verify_command([str(target)], [], {str(target): ["_is_safe_path"]})
    r = subprocess.run([sys.executable] + cmd[1:], capture_output=True, text=True)
    assert r.returncode == 1 and "SCOPE" in r.stdout and "workspace" in r.stdout


# (g) trimming
def test_file_memory_budget_shrinks_when_tool_output_is_large():
    content = "\n".join("x" * 60 for _ in range(3000))
    state = {"file_memory": [{"path": "beast", "start": 1, "end": 3000, "content": content}]}
    small = DirectCoderRuntime._render_file_memory(state, budget=30000)
    assert len(small) < 31000 and "not shown" in small
    assert dcr.PROMPT_TOOL_OUTPUT_CHARS == 160_000


# (h) flat names
def test_flat_tool_names_map_by_binding():
    assert dcr._flat_tool_id("read", True) == "worktree.read_file"
    assert dcr._flat_tool_id("read", False) == "workspace.read_range"
    assert dcr._flat_tool_id("grep", True) == "worktree.search_text"
    assert dcr._flat_tool_id("edit", False) == "worktree.replace_exact"
    assert dcr._flat_tool_id("shell", True) == "worktree.verify"
    assert dcr._flat_tool_id("worktree.read_file", False) == "worktree.read_file"


def test_flat_edit_call_runs_as_replace_exact():
    engine = EditEngine()
    engine.tool_registry.list = schemas
    model = Model([tool("worktree.bind", {"objective": "x"}),
                   tool("read", {"path": "tester/beast", "start_line": 1, "line_count": 10}),
                   tool("edit", {"filePath": "tester/beast", "oldString": "def f3():", "newString": "def f3():  # x"})])
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    run_turns(coder, 3)
    assert ("worktree.replace_exact", {"path": "tester/beast", "old_text": "def f3():",
                                       "new_text": "def f3():  # x"}) in engine.calls


# (i) plan vs build
def test_suggest_run_cannot_edit_and_gets_concrete_suggestion_rules():
    engine = EditEngine()
    engine.store.run["objective"] = "read the beast file and suggest 3 concrete improvements, numbered"
    engine.store.run["request"]["conversation"] = []
    model = Model([tool("worktree.bind", {"objective": "x"}),
                   PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="1. Fix `f`")])
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    run_turns(coder, 2)
    assert "worktree.bind" not in [t for t, _ in engine.calls]
    assert "SUGGESTION RULES" in model.prompts[0] and "line range" in model.prompts[0]
    assert engine.store.run["checkpoint"]["direct_coder"]["plan_run"] is True


def test_tui_projects_new_events():
    from app.cli.coder_client import RuntimeEvent
    from app.cli.coder_state import project_runtime_event
    for name, payload, needle in [
        ("agent.coder.invalid_tool", {"tool_id": "frob"}, "Unknown tool frob"),
        ("agent.coder.doom_loop", {"tool_id": "worktree.verify", "repeats": 3}, "3x"),
        ("agent.coder.diagnostics", {"path": "beast", "messages": ["line 9: undefined name 'w'"]}, "undefined name"),
        ("agent.coder.step_limit_summary", {}, "Step limit"),
    ]:
        assert needle in project_runtime_event(RuntimeEvent(event=name, data={"sequence": 1, "payload": payload})).text
