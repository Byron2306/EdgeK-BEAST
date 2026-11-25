"""Regression for run agent-a615d0b5-c09297ce06db (8101 on 887334c6, Byron 21:03-21:15 SAST).

'proceed implementing your first 5 suggestions for patching.' got eight runtime progress lines
as its conversation, so no checklist was built. The model then rewrote tester/beast lines 1-140
eight times ('convert double-quoted strings to single quotes', a task it took from the act
prompt's JSON tip), re-reading the same lines to 'confirm' between edits, hit the duplicate
guard, and ended budget_exhausted with the worktree copy failing py_compile at line 347.
"""
import asyncio

from app.cli.coder_state import is_history_row, project_runtime_event
from app.cli.coder_client import RuntimeEvent
from app.kernel.agents import direct_coder_runtime as dcr
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from tests.test_direct_coder_act_phase import EditEngine, Model
from tests.test_direct_coder_runtime import tool

PROGRESS = ("Skipped repeat read: Lines 2363-2482 of beast were already read (they are in FILE MEMORY or "
            "summarised in NOTES). Do not re-read them.")
# The conversation 8101 actually received (request_json of the run).
A615_CONVERSATION = [{"role": "assistant", "content": PROGRESS}] * 4 + [
    {"role": "user", "content": "patch in your first 5 suggestions and test them."},
    {"role": "assistant", "content": "Skipped repeat read: worktree.list was already called with these "
                                     "arguments; its result is in PRIOR OBSERVATIONS/NOTES."},
    {"role": "assistant", "content": "Skipped repeat read: worktree.list was already called with these "
                                     "arguments; its result is in PRIOR OBSERVATIONS/NOTES."},
    {"role": "user", "content": "/agent proceed implementing your first 5 suggestions for patching."},
]
# The session's real suggestions answer (run agent-a615d0b5-f6328f73c9be, 18:10 SAST), inline-numbered.
A615_SUGGESTIONS = (
    "I have read the full beast file (2780 lines) across all ranges. Findings: the file is a large CLI "
    "governor. I identified several concrete improvement opportunities: (1) add a --version flag to the "
    "top-level parser; (2) add a --quiet flag to suppress non-JSON output; (3) add a --config flag to specify "
    "an alternate config file path; (4) add a --log-level flag for logging control; (5) add a --no-color flag "
    "to disable ANSI color output; (6) add a --dry-run flag to the up command.")


class Store:
    def __init__(self, runs):
        self.runs = runs

    def list_runs(self, session_id="", limit=8, state=""):
        return list(self.runs)[:limit]


def test_tui_does_not_send_progress_rows_as_history():
    assert not is_history_row({"role": "assistant", "content": PROGRESS})
    assert not is_history_row({"role": "assistant", "content": "anything",
                               "metadata": {"run_id": "r", "turn_complete": False}})
    assert not is_history_row({"role": "assistant", "content": "x", "metadata": {"streaming": True}})
    assert is_history_row({"role": "assistant", "content": A615_SUGGESTIONS,
                           "metadata": {"run_id": "r", "turn_complete": True}})
    assert is_history_row({"role": "user", "content": "patch in your first 5"})


def test_run_a615_conversation_now_yields_the_five_item_checklist():
    engine = EditEngine()
    coder = DirectCoderRuntime(engine, Model([]), max_turns=8)
    prior = {"run_id": "agent-a615d0b5-f6328f73c9be", "created_at": 1.0,
             "objective": "read the beast file in this folder, see if there are ways to improve it"}
    later = {"run_id": "agent-a615d0b5-c230388cc73c", "created_at": 2.0, "objective": "patch in your first 5"}
    engine.store.list_runs = Store([later, prior]).list_runs
    coder._final_answer = lambda r: A615_SUGGESTIONS if r["run_id"] == prior["run_id"] else PROGRESS
    run = {"run_id": "now", "session_id": "agent-a615d0b5", "created_at": 9.0,
           "request": {"conversation": A615_CONVERSATION}}
    history = coder._session_history(run)
    assert not any(m["content"].startswith("Skipped repeat read") for m in history)
    assert history[1]["content"] == A615_SUGGESTIONS
    checklist = dcr._build_checklist("proceed implementing your first 5 suggestions for patching.", history)
    assert [i["title"][:24] for i in checklist] == [
        "add a --version flag to ", "add a --quiet flag to su", "add a --config flag to s",
        "add a --log-level flag f", "add a --no-color flag to"]


def _lines():
    return [f"LINE{n} = {n}" for n in range(1, 61)]


def test_confirm_read_and_rewrite_loop_of_run_a615_is_stopped():
    engine = EditEngine()
    engine.store.run["objective"] = "proceed implementing your first 5 suggestions for patching."
    engine.store.run["request"] = {"autonomy": "autopilot", "context_files": [],
                                   "conversation": A615_CONVERSATION}
    read = tool("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 40})

    def rewrite(k):
        new = "\n".join(f"LINE{n} = '{n}{'x' * k}'" for n in range(1, 11))
        return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                               arguments={"path": "tester/beast", "old_lines": "1-10", "new_text": new},
                               summary="Patch beast lines 1-10: convert double-quoted strings to single quotes")

    loop = [tool("worktree.bind", {"objective": "x"}), read]
    for k in range(1, 9):
        loop += [rewrite(k), read]
    model = Model(loop + [PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="done")])
    coder = DirectCoderRuntime(engine, model, max_turns=30)

    async def go():
        snap = None
        for _ in range(30):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] in {"completed", "paused", "budget_exhausted"}:
                break
        return snap

    snap = asyncio.run(go())
    edits = [a for t, a in engine.calls if t == "worktree.replace_exact"]
    names = [e for e, _ in engine.events]
    # Two rewrites of the region at most, then refused; the run ends with a summary, not the budget.
    assert len(edits) <= dcr.REGION_EDIT_LIMIT
    assert names.count("agent.coder.doom_loop") >= 1
    assert snap["state"] == "completed", snap
    summary = [p for e, p in engine.events if e == "agent.coder.completed"][-1]["summary"]
    assert "repeated-action loops" in summary or "Verified by the runtime" in summary
    assert int(engine.store.run["checkpoint"]["direct_coder"]["turn"]) < 20
    # The confirm read after an edit says the edit is applied instead of 'copy old_text now'.
    notes = [o.get("result", {}).get("note", "") for o in
             engine.store.run["checkpoint"]["direct_coder"].get("observations") or []
             if o.get("tool_id") == dcr.EXCERPT_TOOL]
    assert not notes or all("copy old_text" not in n.lower() for n in notes[-1:])
    refused = [p.get("message", "") for e, p in engine.events if e == "agent.coder.tool_rejected"]
    assert not any("found 0" in m for m in refused)


def test_act_prompt_has_no_quote_style_task_and_forbids_rewriting_edited_lines():
    state = {"file_memory": [{"path": "beast", "start": 1, "end": 5, "content": "a\nb\nc\nd\ne\n"}],
             "act_excerpts": [{"path": "beast", "start": 1, "end": 5}]}
    block = DirectCoderRuntime._render_act_block(state)
    assert "prefer single" not in block and "not a task" in block
    assert "never rewrite lines you already edited" in block


def test_duplicate_guard_names_the_exact_span_to_retry_with():
    content = "\n".join(_lines()) + "\n"
    state = {"file_memory": [{"path": "beast", "start": 1, "end": 60, "content": content}]}
    new_text = "\n".join(["LINE1 = 'one'"] + _lines()[1:14])     # rewrites 1-10 and repeats 11-14
    args, error = dcr._resolve_old_lines(state, {"path": "beast", "old_lines": "1-10", "new_text": new_text})
    assert "old_lines '1-14'" in error and "SAME edit" in error
    args, error = dcr._resolve_old_lines(state, {"path": "beast", "old_lines": "1-14", "new_text": new_text})
    assert error == "" and args["old_text"].endswith("LINE14 = 14")


def test_syntax_breaking_edit_is_reverted_and_rollback_is_named(tmp_path):
    (tmp_path / "tester").mkdir()
    target = tmp_path / "tester" / "beast"
    good = "#!/usr/bin/env python3\nimport os\n\n\ndef main():\n    return os.getcwd()\n"
    target.write_text(good)
    target.chmod(0o755)
    engine = EditEngine()
    engine.store.run["checkpoint"]["worktree_root"] = str(tmp_path)
    coder = DirectCoderRuntime(engine, Model([]), max_turns=8)
    state = {"path_prefix": "tester"}
    pre = coder._parseable_source("agent-test", state, "beast")
    assert pre and pre[1] == good
    target.write_text(good.replace("return os.getcwd()", "return os.getcwd(\n"))   # what the edit did
    decision = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                               arguments={"path": "beast", "old_text": "x", "new_text": "y"})
    error = coder._revert_if_syntax_broken("agent-test", state, pre, decision)
    assert error.startswith("Edit reverted") and "line" in error
    assert target.read_text() == good
    assert target.stat().st_mode & 0o777 == 0o755          # the revert keeps the exec bit
    assert "agent.coder.edit_reverted" in [e for e, _ in engine.events]
    # A clean edit is left alone.
    target.write_text(good.replace("getcwd()", "getcwd()  # ok"))
    assert coder._revert_if_syntax_broken("agent-test", state, pre, decision) == ""
    # Unverified edits name the rollback command in the stop summary.
    state.update(edit_count=2, verified_after_edit=False,
                 rollback_hint=f"git -C {tmp_path} checkout -- tester/beast")
    assert f"git -C {tmp_path} checkout -- tester/beast" in coder._step_limit_summary(state)
    assert "To discard" in coder._fallback_report(state, "turn budget exhausted")
    shown = project_runtime_event(RuntimeEvent("agent.coder.edit_reverted", {"sequence": 4, "payload": {
        "path": "beast", "line": 6, "message": "'(' was never closed"}}, "4"))
    assert "Edit reverted" in shown.text and "restored" in shown.text


def test_identical_reads_interleaved_with_edits_still_count_as_a_doom_loop():
    engine = EditEngine()
    read = tool("worktree.read_file", {"path": "tester/beast", "start_line": 41, "line_count": 10})
    other = tool("worktree.search_text", {"query": "LINE5"})
    model = Model([tool("worktree.bind", {"objective": "x"}), read, other, read, other, read,
                   PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="ok")] + [other] * 6)
    coder = DirectCoderRuntime(engine, model, max_turns=20)

    async def go():
        for _ in range(12):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] in {"completed", "paused"}:
                break

    asyncio.run(go())
    assert "agent.coder.doom_loop" in [e for e, _ in engine.events]


def test_region_rewrite_count_restarts_when_a_checklist_item_is_done():
    content = "\n".join(_lines()) + "\n"
    state = {"file_memory": [{"path": "beast", "start": 1, "end": 60, "content": content}],
             "checklist": [{"n": 1, "title": "a", "done": False}, {"n": 2, "title": "b", "done": False}]}
    DirectCoderRuntime._record_edited_region(state, "beast", "LINE3 = 3\nLINE4 = 4", 1)
    DirectCoderRuntime._record_edited_region(state, "beast", "LINE3 = 3\nLINE4 = 4", 2)
    assert state["edited_regions"][0]["count"] == 2
    state["checklist"][0]["done"] = True          # item 1 done: item 2 may edit the same block
    DirectCoderRuntime._record_edited_region(state, "beast", "LINE3 = 3\nLINE4 = 4", 3)
    region = state["edited_regions"][0]
    assert region["count"] == 1 and region["epoch"] == 1


def test_whitespace_only_edit_is_refused_and_does_not_tick_the_item():
    engine = EditEngine()
    read = tool("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 40})
    noop = PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                           arguments={"path": "tester/beast", "old_text": "def f3():\n    return 4",
                                      "new_text": "def f3():\n    return 4 "}, summary="DONE 1 added --version")
    model = Model([tool("worktree.bind", {"objective": "x"}), read, noop,
                   PlannerDecision(decision_type=PlannerDecisionType.BLOCKED, blocker="stop")])
    coder = DirectCoderRuntime(engine, model, max_turns=10)

    async def go():
        for _ in range(6):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] in {"completed", "paused"}:
                break

    asyncio.run(go())
    assert not [a for t, a in engine.calls if t == "worktree.replace_exact"]
    rejected = [p for e, p in engine.events if e == "agent.coder.tool_rejected"]
    assert any(p.get("reason") == "no_op_edit" for p in rejected)
    lists = [p for e, p in engine.events if e == "agent.coder.checklist"]
    assert lists and lists[-1]["done"] == 0
