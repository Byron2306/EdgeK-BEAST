"""Run agent-a615d0b5-e4e194547191: the model asked for worktree.read_range (not a tool)
and put 'summary' inside worktree.replace_exact arguments, so both edits were rejected."""
from app.kernel.agents.direct_coder_runtime import _normalize_tool_call, _unknown_tool_message

SCHEMAS = {
    "workspace.read_range": {"properties": {"path": {}, "start_line": {}, "line_count": {},
                                            "include_outline": {}, "outline_symbols": {}},
                             "additionalProperties": False},
    "worktree.read_file": {"properties": {"path": {}, "start_line": {}, "line_count": {}},
                           "additionalProperties": False},
    "worktree.replace_exact": {"properties": {"path": {}, "old_text": {}, "new_text": {},
                                              "expected_occurrences": {}},
                               "required": ["path", "old_text", "new_text"], "additionalProperties": False},
    "worktree.search_text": {"properties": {"path": {}, "query": {}, "limit": {}}, "additionalProperties": False},
}


def test_worktree_read_range_maps_to_read_file_and_drops_foreign_args():
    tool, args, changes = _normalize_tool_call(
        "worktree.read_range",
        {"path": "tester/beast", "start_line": 2363, "line_count": 120, "include_outline": True}, SCHEMAS)
    assert tool == "worktree.read_file"
    assert args == {"path": "tester/beast", "start_line": 2363, "line_count": 120}
    assert any("worktree.read_range -> worktree.read_file" in c for c in changes)


def test_summary_inside_arguments_is_dropped_not_rejected():
    tool, args, changes = _normalize_tool_call(
        "worktree.replace_exact",
        {"path": "tester/beast", "old_text": "a", "new_text": "b", "expected_occurrences": 1,
         "summary": "add --version"}, SCHEMAS)
    assert tool == "worktree.replace_exact" and "summary" not in args and args["old_text"] == "a"
    assert changes == ["dropped argument summary"]


def test_registered_tool_and_real_typos_are_left_alone():
    tool, args, changes = _normalize_tool_call("worktree.read_file", {"path": "x"}, SCHEMAS)
    assert (tool, args, changes) == ("worktree.read_file", {"path": "x"}, [])
    # OpenCode-style schema repair (t211u): unknown keys on closed schemas are dropped with a note.
    _, args, changes = _normalize_tool_call("worktree.replace_exact", {"path": "x", "old": "a"}, SCHEMAS)
    assert "old" not in args and changes == ["dropped unknown argument old"]


def test_unknown_tool_message_lists_valid_ids_and_suggestion():
    msg = _unknown_tool_message("worktree.readfile", SCHEMAS)
    assert "worktree.read_file" in msg and "Did you mean" in msg
    assert "workspace.read_range" in msg
