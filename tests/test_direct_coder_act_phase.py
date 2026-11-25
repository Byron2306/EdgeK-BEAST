"""Edit runs must turn 'I already have the text' into an edit.

Regression for run agent-a615d0b5-5f90e8e56782 ("patch in your first 5"): after binding
and reading, the model asked 15 more times for lines it already had, re-bound the
worktree, and thought at length every turn without editing.
"""
import asyncio

from app.cli.coder_client import RuntimeEvent
from app.cli.coder_state import project_runtime_event
from app.kernel.agents import direct_coder_runtime as dcr
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from tests.test_direct_coder_runtime import Engine, Registry, Spec, tool

ANSWER = ("## 3 improvements\n\n### Improvement 1 \u2014 Add `--version` flag\nwhy...\n\n"
          "### Improvement 2 \u2014 Add `--quiet` flag\nwhy...\n\n### Improvement 3 \u2014 Add `--config`\n")
LINES = [f"def f{n}():" if n % 2 else f"    return {n}" for n in range(1, 61)]


class ReadFreeRegistry(Registry):
    def get(self, name):
        return Spec(name, requires_approval=name in {"worktree.bind", "worktree.replace_exact",
                                                     "worktree.write_file", "worktree.verify"})


class EditEngine(Engine):
    def __init__(self):
        super().__init__()
        self.tool_registry = ReadFreeRegistry()
        self.store.run["objective"] = "implement the first 2 of your suggestions"
        self.store.run["request"] = {"autonomy": "autopilot", "context_files": [],
                                     "conversation": [{"role": "user", "content": "suggest 3"},
                                                      {"role": "assistant", "content": ANSWER}]}

    async def execute_tool(self, run_id, tool_id, arguments, *, execution_target="local", approval_id=""):
        self.calls.append((tool_id, dict(arguments)))
        if tool_id == "worktree.bind":
            self.store.run["checkpoint"]["worktree_root"] = "/wt"
            return {"tool_id": tool_id, "status": "completed",
                    "result": {"worktree_root": "/wt", "workspace_prefix": "tester"}}
        if tool_id == "worktree.read_file":
            start = int(arguments.get("start_line") or 1)
            end = min(len(LINES), start + int(arguments.get("line_count") or 200) - 1)
            return {"tool_id": tool_id, "status": "completed",
                    "result": {"path": arguments["path"], "start_line": start, "end_line": end,
                               "total_lines": len(LINES), "sha256": "s",
                               "content": "\n".join(LINES[start - 1:end])}}
        if tool_id == "worktree.verify":
            return {"tool_id": tool_id, "status": "completed",
                    "result": {"ok": True, "returncode": 0, "command": arguments["command"]}}
        return {"tool_id": tool_id, "status": "completed", "result": {"ok": True}}


class Model:
    enable_thinking = True

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.prompts, self.thinking = [], []

    async def next_decision(self, prompt, *, run, turn):
        self.prompts.append(prompt)
        self.thinking.append(self.enable_thinking)
        return self.decisions.pop(0)


def edit(old, new, summary):
    return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                           arguments={"path": "tester/beast", "old_text": old, "new_text": new},
                           summary=summary)


def test_checklist_act_phase_fold_gutter_and_auto_verify():
    engine = EditEngine()
    read = tool("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 40})
    model = Model([
        tool("worktree.bind", {"objective": "x"}),
        read,
        read,                                   # repeat: served from memory, folded (same turn)
        read,                                   # repeat again: skipped -> act phase
        edit("    3| def f3():\n    4|     return 4", "def f3():\n    return 40", "DONE 1 added --version"),
        edit("def f5():", "def f5():  # quiet", "DONE 2 added --quiet"),
        PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="Implemented items 1 and 2."),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=16)

    async def go():
        snap = None
        for _ in range(10):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] == "completed":
                break
        return snap

    snap = asyncio.run(go())
    assert snap["state"] == "completed"
    names = [e for e, _ in engine.events]
    # Checklist from the earlier answer, both items ticked.
    lists = [p for e, p in engine.events if e == "agent.coder.checklist"]
    assert [i["title"] for i in lists[0]["items"]] == ["Add --version flag", "Add --quiet flag"]
    assert lists[-1]["done"] == 2
    assert "agent.coder.skip_folded" in names and "agent.coder.act_phase" in names
    # Act prompt carries the exact text with a gutter and demands an edit.
    act_prompt = next(p for p in model.prompts if "ACT NOW" in p)
    assert "EXACT TEXT beast lines 1-40" in act_prompt and "    3| def f3():" in act_prompt
    assert "CHECKLIST" in act_prompt and "NEXT: item 1" in act_prompt
    # Gutter stripped before the edit ran.
    edits = [a for t, a in engine.calls if t == "worktree.replace_exact"]
    assert edits[0]["old_text"] == "def f3():\n    return 4"
    # Runtime verified and completed without another model turn.
    verify = [a for t, a in engine.calls if t == "worktree.verify"]
    assert verify and verify[0]["command"][:2] == ["python", "-c"] and "py_compile" in verify[0]["command"][2]
    done = [p for e, p in engine.events if e == "agent.coder.completed"][0]["summary"]
    assert "Verified by the runtime" in done and "beast" in done and "2/2" in done
    # The harness bound the worktree itself (one bind), so every model turn is an act turn: no thinking.
    assert [t for t, _ in engine.calls].count("worktree.bind") == 1
    assert "agent.coder.auto_bind" in names and not any(model.thinking)
    # Turn count: the folded repeat did not consume a turn.
    assert int(engine.store.run["checkpoint"]["direct_coder"]["turn"]) <= 7


def test_helpers_parse_counts_items_and_gutter():
    assert dcr._requested_count("implement the first five of your suggestions") == 5
    assert dcr._requested_count("patch in the first 3") == 3
    assert dcr._requested_count("fix it") == 0
    items = dcr._extract_suggestions("1. **Add --version** flag\n2) Quiet mode\n3 - Config file\n1. dup")
    assert items == ["Add --version flag", "Quiet mode", "Config file"]
    assert dcr._strip_gutter("   12| a\n   13|     b") == ("a\n    b", True)
    assert dcr._strip_gutter("a = 1 | 2") == ("a = 1 | 2", False)


def test_tui_projects_checklist_progress():
    event = RuntimeEvent(event="agent.coder.checklist", data={"sequence": 3, "payload": {
        "items": [{"n": 1, "title": "Add --version", "done": True}, {"n": 2, "title": "Quiet", "done": False}],
        "done": 1, "total": 2}})
    projected = project_runtime_event(event)
    assert "Checklist 1/2" in projected.text and "✓1" in projected.text and "next: 2. Quiet" in projected.text


def test_done_needs_a_successful_edit_and_skip_records_reason():
    engine = EditEngine()
    coder = DirectCoderRuntime(engine, Model([]), max_turns=8)
    state = {"checklist": [{"n": 1, "title": "a", "done": False}, {"n": 2, "title": "b", "done": False},
                           {"n": 3, "title": "c", "done": False}]}
    # Claimed on an edit that failed: not credited (run agent-680b3463-4384429de2df).
    coder._update_checklist("agent-test", state, "DONE 2 added max_output", edit_succeeded=False, is_edit=True)
    assert not state["checklist"][1]["done"]
    # Claimed on a read with no edit since: not credited.
    coder._update_checklist("agent-test", state, "DONE 1")
    assert not state["checklist"][0]["done"]
    coder._update_checklist("agent-test", state, "DONE 1 version flag", edit_succeeded=True, is_edit=True)
    assert state["checklist"][0]["done"]
    coder._update_checklist("agent-test", state, "SKIP 2: _run_command does not exist in beast")
    assert state["checklist"][1]["skipped"] and "does not exist" in state["checklist"][1]["skip_reason"]
    text = dcr._render_checklist(state["checklist"])
    assert "[x] 1." in text and "[-] 2." in text and "NEXT: item 3" in text


def test_old_lines_fills_old_text_from_memory_and_rejects_unread_spans():
    state = {"path_prefix": "tester",
             "file_memory": [{"path": "beast", "start": 10, "end": 13,
                              "content": 'def f():\n    x = "a"\n    return x\n\n'}]}
    args, err = dcr._resolve_old_lines(state, {"path": "tester/beast", "old_lines": "10-12",
                                               "new_text": "def f():\n    return 'a'"})
    assert err == "" and "old_lines" not in args
    assert args["old_text"] == 'def f():\n    x = "a"\n    return x'
    _, err = dcr._resolve_old_lines(state, {"path": "beast", "old_lines": "40-45", "new_text": "x"})
    assert "not in FILE MEMORY" in err
    same, err = dcr._resolve_old_lines(state, {"path": "beast", "old_text": "a", "new_text": "b"})
    assert err == "" and same == {"path": "beast", "old_text": "a", "new_text": "b"}


def test_old_lines_edit_runs_through_runtime_and_memory_is_patched_after_edit():
    engine = EditEngine()
    read = tool("worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 40})
    model = Model([
        tool("worktree.bind", {"objective": "x"}),
        read,
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                        arguments={"path": "tester/beast", "old_lines": "3-4",
                                   "new_text": "def f3():\n    return 'forty'"},
                        summary="DONE 1"),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=8)

    async def go():
        for _ in range(3):
            await coder.run_one_turn("agent-test")

    asyncio.run(go())
    edits = [a for t, a in engine.calls if t == "worktree.replace_exact"]
    assert edits == [{"path": "tester/beast", "old_text": "def f3():\n    return 4",
                      "new_text": "def f3():\n    return 'forty'"}]
    st = engine.store.run["checkpoint"]["direct_coder"]
    mem = [m for m in st["file_memory"] if m["path"] == "beast"]
    assert mem and "return 'forty'" in mem[-1]["content"] and "return 4\n" not in mem[-1]["content"]
    assert dcr._memory_slice(st, "beast", 3, 4) == "def f3():\n    return 'forty'\n"
    assert st["checklist"][0]["done"] is True


def test_memory_patch_shifts_later_chunks_and_drops_overlaps():
    state = {"file_memory": [
        {"path": "beast", "start": 1, "end": 4, "content": "a\nb\nc\nd"},
        {"path": "beast", "start": 3, "end": 5, "content": "c\nd\ne"},
        {"path": "beast", "start": 10, "end": 11, "content": "j\nk"},
        {"path": "other", "start": 10, "end": 11, "content": "x\ny"},
    ], "reads": {"beast": {"sha256": "old", "total_lines": 20, "ranges": [[1, 5], [10, 11]]}}}
    # newest chunk containing old_text once is patched: "d\ne" (lines 4-5) -> three lines
    assert dcr._apply_edit_to_memory(state, "beast", "d\ne", "d\nE1\nE2")
    mem = {(m["path"], m["start"]): m for m in state["file_memory"]}
    assert mem[("beast", 3)]["end"] == 6 and mem[("beast", 3)]["content"] == "c\nd\nE1\nE2"
    assert ("beast", 1) not in mem  # overlapped the edit: stale
    assert mem[("beast", 11)]["end"] == 12 and mem[("other", 10)]["end"] == 11
    assert state["reads"]["beast"]["sha256"] == "" and state["reads"]["beast"]["total_lines"] == 21
    assert not dcr._apply_edit_to_memory(state, "beast", "zzz", "q")


def test_chunk_by_chunk_scan_of_large_file_is_refused_with_search_hint():
    engine = EditEngine()
    model = Model([tool("worktree.bind", {"objective": "x"})])
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    state = {"bound": True, "path_prefix": "tester",
             "reads": {"beast": {"total_lines": 2781}},
             "scan": {"path": "beast", "streak": 3, "end": 360}}
    reason = coder._edit_read_budget_reason(
        state, "worktree.read_file", {"path": "tester/beast", "start_line": 361, "line_count": 120})
    assert "search_text" in reason and "small chunks" in reason and "line_count 2000" in reason
    state["scan"]["streak"] = 2
    assert coder._edit_read_budget_reason(
        state, "worktree.read_file", {"path": "tester/beast", "start_line": 361, "line_count": 120}) == ""
    state["scan"]["streak"] = 3
    assert coder._edit_read_budget_reason(
        state, "worktree.read_file", {"path": "tester/beast", "start_line": 1500, "line_count": 60}) == ""


SYM_ANSWER = ("1. **Speed up `func_three`**\nIt is slow.\n\n2. **Harden `func_seven`** loop\nbody\n\n"
              "3. Something else\n")


class SiteEngine(EditEngine):
    def __init__(self):
        super().__init__()
        self.store.run["request"]["conversation"][-1]["content"] = SYM_ANSWER

    async def execute_tool(self, run_id, tool_id, arguments, *, execution_target="local", approval_id=""):
        if tool_id == "worktree.search_text":
            self.calls.append((tool_id, dict(arguments)))
            line = 3 if "three" in arguments["query"] else 7
            return {"tool_id": tool_id, "status": "completed",
                    "result": {"matches": [{"path": "tester/beast", "line": line, "preview": "def"}]}}
        return await super().execute_tool(run_id, tool_id, arguments,
                                          execution_target=execution_target, approval_id=approval_id)


def test_prelocate_batch_edits_and_runtime_finish_use_two_model_turns():
    engine = SiteEngine()
    model = Model([
        tool("worktree.bind", {"objective": "x"}),
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                        arguments={"path": "tester/beast", "edits": [
                            {"item": 1, "old_lines": "3-4", "new_text": "def f3():\n    return 'three'"},
                            {"item": 2, "old_lines": "7-8", "new_text": "def f7():\n    return 'seven'"}]},
                        summary="both"),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=10)

    async def go():
        result = None
        for _ in range(6):
            result = await coder.run_one_turn("agent-test")
            if result["state"] == "completed":
                break
        return result

    result = asyncio.run(go())
    assert len(model.prompts) == 2  # bind + one batched edit decision; no verify/finish turns
    st = engine.store.run["checkpoint"]["direct_coder"]
    assert [i["done"] for i in st["checklist"]] == [True, True]
    assert st["checklist"][0]["site"] == "beast:3"
    assert "EXACT TEXT beast" in model.prompts[1]  # located code shown on the first edit turn
    edits = [a for t, a in engine.calls if t == "worktree.replace_exact"]
    assert [e["old_text"] for e in edits] == ["def f3():\n    return 4", "def f7():\n    return 8"]
    verifies = [a for t, a in engine.calls if t == "worktree.verify"]
    assert verifies and "py_compile" in " ".join(verifies[-1]["command"])
    assert result["state"] == "completed"


def test_unbound_worktree_calls_map_to_workspace_or_bind_once():
    engine = EditEngine()
    engine.store.run["objective"] = "fix it"
    engine.store.run["request"]["conversation"] = []
    model = Model([
        tool("worktree.list", {"path": "."}),
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.replace_exact",
                        arguments={"path": "tester/beast", "old_text": "a", "new_text": "b"}, summary="x"),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=6)

    async def go():
        await coder.run_one_turn("agent-test")
        await coder.run_one_turn("agent-test")

    asyncio.run(go())
    ids = [t for t, _ in engine.calls]
    assert ids[0] == "workspace.list"
    assert "worktree.bind" in ids and "worktree.replace_exact" not in ids
    assert "worktree.list" not in ids


def test_edit_without_done_credits_next_pending_item():
    engine = EditEngine()
    coder = DirectCoderRuntime(engine, Model([]), max_turns=6)
    state = {"checklist": [{"n": 1, "title": "a", "done": False}, {"n": 2, "title": "b", "done": False}]}
    coder._update_checklist("agent-test", state, "edited the thing", edit_succeeded=True, is_edit=True)
    assert [i["done"] for i in state["checklist"]] == [True, False]
    coder._update_checklist("agent-test", state, "SKIP 2: missing", edit_succeeded=True, is_edit=True)
    assert state["checklist"][1].get("skipped") and not state["checklist"][1]["done"]


def test_tui_projects_turnaround_events():
    for name, payload, needle in [
        ("agent.coder.prelocate", {"item": 1, "path": "beast", "line": 40, "start": 36, "end": 125}, "Located item 1"),
        ("agent.coder.batch_edit", {"item": 2, "path": "beast", "remaining": 1}, "1 more queued"),
        ("agent.coder.runtime_finish", {"edits": 3}, "without another model turn"),
        ("agent.coder.auto_bind", {"requested_tool": "worktree.replace_exact"}, "binding it once"),
    ]:
        projected = project_runtime_event(RuntimeEvent(event=name, data={"sequence": 3, "payload": payload}))
        assert needle in projected.text


def test_old_lines_rejects_new_text_that_duplicates_following_lines():
    lines = [f"line{n}" for n in range(1, 21)]
    state = {"file_memory": [{"path": "beast", "start": 1, "end": 20, "content": "\n".join(lines)}]}
    _, error = dcr._resolve_old_lines(state, {"path": "beast", "old_lines": "3-4",
                                              "new_text": "new3\nline5\nline6\nline7\nline8"})
    assert "duplicate" in error
    resolved, error = dcr._resolve_old_lines(state, {"path": "beast", "old_lines": "3-8",
                                                     "new_text": "new3\nline5\nline6\nline7\nline8"})
    assert error == "" and resolved["old_text"].startswith("line3")


def test_auto_verify_flags_undefined_helpers_used_by_edits(tmp_path):
    import subprocess, sys
    script = tmp_path / "tool"
    script.write_text("#!/usr/bin/env python3\nimport sys\ndef main():\n    if not _is_safe(sys.argv):\n"
                      "        return 1\n    return helper()\ndef helper():\n    return 0\n"
                      "if __name__ == '__main__' and '--help' not in sys.argv:\n    main()\n")
    cmd = dcr._auto_verify_command([str(script)], ["_is_safe", "helper", "print"])
    r = subprocess.run([sys.executable] + cmd[1:], capture_output=True, text=True)
    assert r.returncode == 1 and "UNDEFINED" in r.stdout and "_is_safe" in r.stdout and "helper," not in r.stdout
    cmd = dcr._auto_verify_command([str(script)], ["helper"])
    assert subprocess.run([sys.executable] + cmd[1:], capture_output=True, text=True).returncode == 0


def test_loose_match_and_closest_lines():
    state = {"file_memory": [{"path": "beast", "start": 10, "end": 13,
                              "content": "def f():\n    x = 1\n    return x\n\n"}]}
    assert dcr._loose_match(state, "beast", "def f():\n  x = 1  \n return x") == "def f():\n    x = 1\n    return x"
    assert dcr._loose_match(state, "beast", "nope") == ""
    near = dcr._closest_lines(state, "beast", "    x = 2")
    assert "  11| " in near or "11|" in near


def test_big_numbered_reads_and_next_offset(tmp_path):
    from app.kernel.agents import worktree_tools as wt
    assert wt.READ_DEFAULT_LINES == 2000 and wt.READ_MAX_BYTES == 50_000
    assert dcr.DEFAULT_READ_LINES == 2000
    assert dcr._requested_range({"path": "x"}) == ("x", 1, 2000)
    state = {"file_memory": [{"path": "beast", "start": 7, "end": 8, "content": "a\nb"}]}
    rendered = DirectCoderRuntime._render_file_memory(state)
    assert "    7| a" in rendered and "    8| b" in rendered


def test_worktree_read_file_defaults_to_2000_lines_with_byte_cap(tmp_path, monkeypatch):
    from app.kernel.agents import worktree_tools as wt
    target = tmp_path / "big.py"
    target.write_text("\n".join("x" * 40 for _ in range(3000)), encoding="utf-8")
    monkeypatch.setattr(wt, "_is_remote_target", lambda context: False)
    monkeypatch.setattr(wt, "_worktree_relative", lambda context, path: str(path))
    monkeypatch.setattr(wt, "_safe_worktree_path", lambda context, rel: tmp_path / rel)
    monkeypatch.setattr(wt, "_worktree_result", lambda context: {})
    result = asyncio.run(wt._worktree_read_file({"path": "big.py"}, None))
    assert result["start_line"] == 1 and result["truncated"] is True
    assert len(result["content"]) <= 50_000 and result["next_start_line"] == result["end_line"] + 1
    assert 1000 < result["end_line"] < 2000  # byte cap (41 bytes/line) hit before the 2000-line cap


class ParallelEngine(SiteEngine):
    async def execute_tool(self, run_id, tool_id, arguments, *, execution_target="local", approval_id=""):
        if tool_id in {"worktree.read_file", "worktree.search_text"}:
            self.inflight = getattr(self, "inflight", 0) + 1
            self.peak = max(getattr(self, "peak", 0), self.inflight)
            await asyncio.sleep(0.01)
            try:
                return await super().execute_tool(run_id, tool_id, arguments,
                                                  execution_target=execution_target, approval_id=approval_id)
            finally:
                self.inflight -= 1
        return await super().execute_tool(run_id, tool_id, arguments,
                                          execution_target=execution_target, approval_id=approval_id)


def test_parallel_decision_runs_reads_concurrently_and_queues_edits_in_order():
    engine = ParallelEngine()
    engine.store.run["request"]["conversation"] = [{"role": "user", "content": "hi"},
                                                   {"role": "assistant", "content": "ok"}]
    engine.store.run["objective"] = "fix the two functions"
    model = Model([
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="parallel", arguments={"calls": [
            {"tool_id": "worktree.read_file", "arguments": {"path": "tester/beast", "start_line": 1, "line_count": "20"}},
            {"tool_id": "Worktree.Search_Text", "arguments": {"query": "def f7"}},
            {"tool_id": "worktree.read_file", "arguments": {"path": "tester/beast", "start_line": 21, "line_count": 20}},
        ]}, summary="look"),
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="parallel", arguments={"calls": [
            {"tool_id": "worktree.replace_exact", "arguments": {"path": "tester/beast", "old_lines": "3-4",
                                                                "new_text": "def f3():\n    return 'a'"}},
            {"tool_id": "worktree.replace_exact", "arguments": {"path": "tester/beast", "old_lines": "7-8",
                                                                "new_text": "def f7():\n    return 'b'"}},
        ]}, summary="edit both"),
        PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="done"),
    ])
    engine.tool_registry.list = lambda: [
        {"tool_id": t, "input_schema": {"type": "object", "properties": {
            "path": {"type": "string"}, "start_line": {"type": "integer"}, "line_count": {"type": "integer"},
            "query": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}}}
        for t in ("worktree.read_file", "worktree.search_text", "worktree.replace_exact", "worktree.bind",
                  "worktree.verify", "workspace.list")]
    coder = DirectCoderRuntime(engine, model, max_turns=12)

    async def go():
        snap = None
        for _ in range(8):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] == "completed":
                break
        return snap

    snap = asyncio.run(go())
    reads = [a for t, a in engine.calls if t == "worktree.read_file"]
    assert engine.peak >= 2  # reads overlapped
    assert {"path": "tester/beast", "start_line": 1, "line_count": 20} in reads  # "20" coerced to int
    assert ("worktree.search_text", {"query": "def f7"}) in engine.calls  # lowercased tool id
    edits = [a["old_text"] for t, a in engine.calls if t == "worktree.replace_exact"]
    assert edits == ["def f3():\n    return 4", "def f7():\n    return 8"]
    assert snap["state"] == "completed"


def test_follow_up_run_reuses_session_worktree_without_bind(tmp_path):
    engine = EditEngine()
    engine.store.run["session_id"] = "agent-s"
    prior = {"run_id": "agent-s-1", "created_at": 1.0, "checkpoint": {
        "worktree_root": str(tmp_path), "worktree_task_id": "t1", "worktree_prefix": "tester"}}
    engine.store.list_runs = lambda session_id="", limit=8, state="": [prior, {"run_id": "agent-test"}]

    def merge(run_id, payload):
        engine.store.run.setdefault("checkpoint", {}).update(payload)
    engine.merge_checkpoint = merge
    model = Model([PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.read_file",
                                   arguments={"path": "tester/beast", "start_line": 1, "line_count": 10})])
    coder = DirectCoderRuntime(engine, model, max_turns=6)
    asyncio.run(coder.run_one_turn("agent-test"))
    ids = [t for t, _ in engine.calls]
    assert "worktree.bind" not in ids and ids[-1] == "worktree.read_file"
    assert engine.store.run["checkpoint"]["worktree_root"] == str(tmp_path)
    assert "agent.coder.worktree_reused" in [e for e, _ in engine.events]


def test_inline_numbered_suggestions_build_a_checklist():
    answer = ("Reviewed the file. Three improvements: (1) Split `command_main` into modules. "
              "(2) Add validation to `parse_args_safe`. (3) Add docstrings.")
    checklist = dcr._build_checklist("implement the first 3 of your suggestions",
                                     [{"role": "assistant", "content": answer}])
    assert [i["n"] for i in checklist] == [1, 2, 3]
    assert checklist[0]["title"].startswith("Split command_main")
    assert checklist[1]["symbols"] == ["parse_args_safe"]


def test_big_memory_chunk_is_partially_rendered_not_dropped():
    content = "\n".join(f"line {n}" for n in range(1, 20001))
    state = {"file_memory": [{"path": "beast", "start": 1, "end": 20000, "content": content}]}
    rendered = DirectCoderRuntime._render_file_memory(state)
    assert "    1| line 1" in rendered and "not shown" in rendered
    assert len(rendered) <= dcr.FILE_MEMORY_PROMPT_CHARS + 500


def test_checklist_takes_symbols_from_the_detailed_earlier_answer():
    detailed = "1. **Fix `command_reinstall_surfaces`**\nIt writes to `target_path`.\n2. Speed up `load_all`\n"
    summary = "Implemented:\n1. Fix command_reinstall_surfaces - done\n2. Speed up load_all - done\n"
    checklist = dcr._build_checklist("implement the first 2", [
        {"role": "assistant", "content": detailed}, {"role": "assistant", "content": summary}])
    assert "target_path" in checklist[0]["symbols"]


def test_summary_status_suffix_is_not_part_of_the_title():
    items = dcr._extract_suggestions("1. Fix thing - done\n2. Other thing - skipped (n/a)\n")
    assert items == ["Fix thing", "Other thing"]
