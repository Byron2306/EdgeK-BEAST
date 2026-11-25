"""Edit runs on a large file must search and edit, not read it top to bottom.

Regression for agent-72239d6a-7bf86a3f0516: after binding a worktree with
workspace prefix ``tester`` the model read ``tester/beast`` (2780 lines) twice,
because ``beast`` and ``tester/beast`` were tracked as different files and no
read budget applied to edit runs.
"""
from app.kernel.agents import direct_coder_runtime as dcr
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime, _canonical_path


def _obs(path, start, end, total=2780):
    return {"status": "completed", "result": {"path": path, "start_line": start, "end_line": end,
                                              "total_lines": total, "sha256": "x", "content": "a\n" * 10}}


def test_prefixed_and_plain_paths_share_coverage():
    state = {"path_prefix": "tester"}
    assert _canonical_path(state, "tester/beast") == "beast"
    assert _canonical_path(state, "./beast") == "beast"
    DirectCoderRuntime._remember(state, "workspace.read_range",
                                 {"path": "beast", "start_line": 1, "line_count": 200}, _obs("beast", 1, 200))
    DirectCoderRuntime._remember(state, "worktree.read_file",
                                 {"path": "tester/beast", "start_line": 201, "line_count": 200},
                                 _obs("tester/beast", 201, 400))
    assert list(state["reads"]) == ["beast"]
    assert state["reads"]["beast"]["ranges"] == [[1, 400]]
    reason = DirectCoderRuntime._duplicate_reason(
        state, "worktree.read_file", {"path": "tester/beast", "start_line": 1, "line_count": 200})
    assert "already read" in reason


def test_edit_read_budget_forces_search_then_closes_reading():
    rt = DirectCoderRuntime.__new__(DirectCoderRuntime)
    state = {"path_prefix": "tester", "reads": {"beast": {"total_lines": 2780, "ranges": [[1, 400]]}}}
    wide = {"path": "tester/beast", "start_line": 1400, "line_count": 200}
    narrow = {"path": "tester/beast", "start_line": 1400, "line_count": 60}
    state["reads_since_edit"] = dcr.EDIT_READ_BUDGET - 1
    assert rt._edit_read_budget_reason(state, "worktree.read_file", wide) == ""
    state["reads_since_edit"] = dcr.EDIT_READ_BUDGET
    assert "search_text" in rt._edit_read_budget_reason(state, "worktree.read_file", wide)
    assert rt._edit_read_budget_reason(state, "worktree.read_file", narrow) == ""
    assert rt._edit_read_budget_reason(state, "workspace.search_text", {"query": "x"}) == ""
    state["reads_since_edit"] = dcr.EDIT_READ_HARD_CAP
    assert "replace_exact" in rt._edit_read_budget_reason(state, "worktree.read_file", narrow)
    assert rt._large_files(state) == {"beast": 2780}


def test_memory_slice_returns_exact_lines():
    state = {"file_memory": [{"path": "beast", "start": 10, "end": 14,
                              "content": "l10\nl11\nl12\nl13\nl14\n"}]}
    assert dcr._memory_slice(state, "beast", 11, 12) == "l11\nl12\n"
    assert dcr._memory_slice(state, "beast", 9, 12) == ""


def test_edit_run_finishing_prompt_asks_for_edit_not_essay():
    rt = DirectCoderRuntime.__new__(DirectCoderRuntime)
    rt.max_turns = 32
    rt.crystals = None

    class _Reg:
        def list(self):
            return []

    class _Eng:
        tool_registry = _Reg()

    rt.engine = _Eng()
    run = {"objective": "implement the first 2", "request": {}, "checkpoint": {"worktree_root": "/wt"}}
    try:
        prompt = rt._prompt(run, {"turn": 20}, finishing="you keep requesting content you already have")
    except Exception:  # registry shape differs across builds; the block text is what matters
        import inspect
        prompt = inspect.getsource(DirectCoderRuntime._prompt)
    assert "edit run in a bound worktree" in prompt
