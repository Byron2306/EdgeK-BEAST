"""Structured edit contract shared by the Ollama specialist and the NIM fallback."""
from __future__ import annotations

from app.kernel.compute.structured_edit import (
    EDIT_SCHEMA,
    edit_messages,
    nim_request_extras,
    parse_edit,
    repair_message,
)


def test_schema_requires_both_fields():
    assert EDIT_SCHEMA["required"] == ["old_text", "new_text"]
    assert EDIT_SCHEMA["additionalProperties"] is False


def test_parse_edit_strict_json_fenced_and_think_stripped():
    assert parse_edit('{"old_text": "A = 1", "new_text": "A = 2"}') == {"old_text": "A = 1", "new_text": "A = 2"}
    assert parse_edit('```json\n{"old_text": "A = 1", "new_text": "A = 2"}\n```')["new_text"] == "A = 2"
    assert parse_edit('<think>{"old_text": "x", "new_text": "y"}</think>{"old_text": "A", "new_text": "B"}') == {
        "old_text": "A", "new_text": "B"}
    assert parse_edit('{"old_text": "A\\n  B", "new_text": "A\\n  C"}')["old_text"] == "A\n  B"


def test_parse_edit_rejects_prose_partial_and_noop():
    assert parse_edit("Okay, let's see. Change 0.14 to 0.15.") is None
    assert parse_edit('{"old_text": "A = 1"}') is None
    assert parse_edit('{"old_text": "A = 1", "new_text": "A = 1"}') is None
    assert parse_edit('{"old_text": "", "new_text": "A = 1"}') is None


def test_edit_messages_are_few_shot_and_carry_task():
    msgs = edit_messages("pkg/mod.py", "X = 1\n", "AssertionError: 1 != 2")
    assert msgs[0]["role"] == "system" and "JSON" in msgs[0]["content"]
    roles = [m["role"] for m in msgs]
    assert roles.count("assistant") >= 2  # few-shot examples
    assert "pkg/mod.py" in msgs[-1]["content"] and "AssertionError: 1 != 2" in msgs[-1]["content"]


def test_repair_message_quotes_reason_and_previous_reply():
    msg = repair_message("prose", "edit_not_exact_unique")
    assert msg["role"] == "user" and "edit_not_exact_unique" in msg["content"] and "prose" in msg["content"]


def test_nim_extras_turn_reasoning_off_only_when_asked():
    assert nim_request_extras(thinking=False) == {"chat_template_kwargs": {"enable_thinking": False}}
    assert nim_request_extras(thinking=True) == {}


def test_multi_file_edits_schema_and_parse():
    from app.kernel.compute.structured_edit import EDITS_SCHEMA, parse_edits

    assert EDITS_SCHEMA["required"] == ["edits"]
    item = EDITS_SCHEMA["properties"]["edits"]["items"]
    assert item["required"] == ["path", "old_text", "new_text"]
    text = '{"edits": [{"path": "a/b.py", "old_text": "x = 1", "new_text": "x = 2"}, {"path": "c.py", "old_text": "f()", "new_text": "g()"}]}'
    assert [e["path"] for e in parse_edits(text, default_path="t.py")] == ["a/b.py", "c.py"]
    assert parse_edits('{"old_text": "A", "new_text": "B"}', default_path="t.py") == [
        {"path": "t.py", "old_text": "A", "new_text": "B"}]
    assert parse_edits("prose", default_path="t.py") is None
    assert parse_edits('{"edits": []}', default_path="t.py") is None
    assert parse_edits('{"edits": [{"path": "../x.py", "old_text": "a", "new_text": "b"}]}', default_path="t.py") is None


def test_edits_messages_show_every_file_and_are_few_shot():
    from app.kernel.compute.structured_edit import edits_messages

    msgs = edits_messages({"pkg/a.py": "A = 1\n", "pkg/b.py": "B = 2\n"}, "AssertionError: 1 != 3", target="pkg/a.py")
    assert sum(m["role"] == "assistant" for m in msgs) >= 2
    assert '"edits"' in msgs[2]["content"]
    assert "pkg/a.py" in msgs[-1]["content"] and "pkg/b.py" in msgs[-1]["content"] and "B = 2" in msgs[-1]["content"]


def test_degenerate_edit_rejects_semantics_erasing_stubs():
    from app.kernel.compute.structured_edit import degenerate_edit

    assert degenerate_edit({"path": "f/core.py", "old_text": "return int(num) / int(den)", "new_text": "return None"})
    assert degenerate_edit({"path": "f/core.py", "old_text": "    x = a / b\n    return x", "new_text": "    pass"})
    assert degenerate_edit({"path": "f/core.py", "old_text": "return total", "new_text": "  return  "})
    # real fixes and guards that keep the computation are allowed
    assert degenerate_edit({"path": "f/core.py", "old_text": "return int(num) / int(den)",
                            "new_text": "try:\n    return int(num) / int(den)\nexcept ZeroDivisionError:\n    return None"}) is None
    assert degenerate_edit({"path": "f/core.py", "old_text": "LIMIT = 3", "new_text": "LIMIT = 5"}) is None
    assert degenerate_edit({"path": "f/core.py", "old_text": "return None", "new_text": "return None"}) is None



def test_schema_optional_disambiguators_are_optional():
    from app.kernel.compute.structured_edit import EDIT_ITEM_PROPERTIES, EDIT_SCHEMA, EDITS_SCHEMA
    from app.kernel.compute.symbol_rename import RENAME_ACTION_SCHEMA

    for key in ("anchor_line", "before_context", "after_context", "occurrence"):
        assert key in EDIT_SCHEMA["properties"]
        assert key in EDITS_SCHEMA["properties"]["edits"]["items"]["properties"]
        assert key in RENAME_ACTION_SCHEMA["properties"]["edits"]["items"]["properties"]
        assert key not in EDIT_SCHEMA["required"]
        assert key not in EDITS_SCHEMA["properties"]["edits"]["items"]["required"]
        assert key not in RENAME_ACTION_SCHEMA["properties"]["edits"]["items"]["required"]
    assert EDIT_ITEM_PROPERTIES["anchor_line"]["type"] == "integer"
    assert EDIT_SCHEMA["additionalProperties"] is False
    assert EDITS_SCHEMA["properties"]["edits"]["items"]["additionalProperties"] is False


def test_parse_preserves_optional_disambiguators():
    from app.kernel.compute.structured_edit import parse_edit, parse_edits

    got = parse_edit('{"old_text": "A", "new_text": "B", "anchor_line": 7, "occurrence": 2, '
                     '"before_context": "pre\\n", "after_context": "\\npost"}')
    assert got == {"old_text": "A", "new_text": "B", "anchor_line": 7, "occurrence": 2,
                   "before_context": "pre\n", "after_context": "\npost"}
    items = parse_edits('{"edits": [{"path": "a.py", "old_text": "A", "new_text": "B", "anchor_line": 3}]}',
                        default_path="t.py")
    assert items == [{"path": "a.py", "old_text": "A", "new_text": "B", "anchor_line": 3}]
    assert "anchor_line" in parse_edit('{"old_text": "A", "new_text": "B", "anchor_line": "4"}')
    assert "anchor_line" not in parse_edit('{"old_text": "A", "new_text": "B", "anchor_line": 0}')


def test_prompts_mention_anchor_and_context():
    from app.kernel.compute.structured_edit import SYSTEM, EDITS_SYSTEM, edit_messages, repair_message
    from app.kernel.compute.governed_refactor import ACTION_SYSTEM

    for text in (SYSTEM, EDITS_SYSTEM, ACTION_SYSTEM):
        assert "anchor_line" in text and "occurrence" in text and "before_context" in text
    assert "anchor_line" in edit_messages("a.py", "X = 1\n", "fail")[0]["content"]
    assert "occurrence" in repair_message("prose", "edit old_text is not unique in target")["content"]


def _sample_text() -> str:
    # 3 identical assignments on lines 1, 4, 7
    return "x = 1\n# first\nx = 1\n# second\nx = 1\n# tail\n"


def test_line_anchor_unique_match_is_backward_compatible(tmp_path):
    from app.kernel.compute.structured_edit import apply_one_edit, find_occurrences, resolve_occurrence

    text = "RETRY_LIMIT = 2\nTIMEOUT_S = 30\n"
    path = tmp_path / "limits.py"
    path.write_text(text, encoding="utf-8")
    assert len(find_occurrences(text, "RETRY_LIMIT = 2")) == 1
    occ = resolve_occurrence(text, {"old_text": "RETRY_LIMIT = 2", "new_text": "RETRY_LIMIT = 4"})
    assert occ.line == 1 and occ.index == 1
    apply_one_edit(path, {"old_text": "RETRY_LIMIT = 2", "new_text": "RETRY_LIMIT = 4"})
    assert path.read_text(encoding="utf-8") == "RETRY_LIMIT = 4\nTIMEOUT_S = 30\n"
    leftover = list(tmp_path.glob(".beast-edit-*"))
    assert leftover == []


def test_anchor_line_picks_nearest_and_ties_fall_through():
    from app.kernel.compute.structured_edit import EditApplyError, resolve_occurrence

    text = _sample_text()
    # lines: 1:x=1  2:# first  3:x=1  4:# second  5:x=1  6:# tail
    picked = resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 2", "anchor_line": 5})
    assert picked.line == 5 and picked.index == 3
    picked = resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 2", "anchor_line": 3})
    assert picked.line == 3 and picked.index == 2
    try:
        resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 2", "anchor_line": 2})
        raise AssertionError("tie at line 2 should not uniquely resolve")
    except EditApplyError as exc:
        assert "not unique" in str(exc)
        assert {c.line for c in exc.candidates} == {1, 3}


def test_context_and_occurrence_disambiguate():
    from app.kernel.compute.structured_edit import EditApplyError, apply_one_edit, resolve_occurrence

    text = _sample_text()
    by_before = resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 9",
                                          "before_context": "# first\n"})
    assert by_before.line == 3
    by_after = resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 9",
                                         "after_context": "\n# tail"})
    assert by_after.line == 5
    by_occ = resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 9", "occurrence": 2})
    assert by_occ.index == 2 and by_occ.line == 3
    try:
        resolve_occurrence(text, {"old_text": "x = 1", "new_text": "x = 9"})
        raise AssertionError("ambiguous without hints")
    except EditApplyError as exc:
        msg = str(exc)
        assert msg.startswith("edit old_text is not unique in target")
        assert "occurrence=1, line 1:" in msg
        assert "occurrence=2, line 3:" in msg
        assert "occurrence=3, line 5:" in msg
        assert "# first" in msg and "# second" in msg
        assert "Supply anchor_line" in msg
        assert len(exc.candidates) == 3


def test_apply_one_edit_uses_hints_and_is_atomic(tmp_path):
    from app.kernel.compute.family_crystals import apply_plan
    from app.kernel.compute.structured_edit import EditApplyError, apply_one_edit

    path = tmp_path / "mod.py"
    path.write_text(_sample_text(), encoding="utf-8")
    apply_one_edit(path, {"path": "mod.py", "old_text": "x = 1", "new_text": "x = 7", "anchor_line": 3})
    assert path.read_text(encoding="utf-8").splitlines()[2] == "x = 7"
    # apply_plan with occurrence on a worktree of .py files
    wt = tmp_path / "wt"
    wt.mkdir()
    target = wt / "pkg.py"
    target.write_text(_sample_text(), encoding="utf-8")
    changed = apply_plan(wt, {"edits": [{"path": "pkg.py", "old_text": "x = 1", "new_text": "x = 8", "occurrence": 1}]})
    assert changed == ["pkg.py"]
    assert target.read_text(encoding="utf-8").startswith("x = 8\n")
    try:
        apply_plan(wt, {"edits": [{"path": "pkg.py", "old_text": "x = 1", "new_text": "x = 0"}]})
        raise AssertionError("should still reject remaining ambiguous matches")
    except EditApplyError as exc:
        assert "occurrence=" in str(exc)
        assert "line " in str(exc)


def test_edits_actuator_forwards_disambiguators(tmp_path):
    from app.kernel.compute.governed_refactor import apply_action_to_copy

    root = tmp_path / "repo"
    root.mkdir()
    (root / "core.py").write_text(_sample_text(), encoding="utf-8")
    out = apply_action_to_copy(root, {"renames": [], "edits": [
        {"path": "core.py", "old_text": "x = 1", "new_text": "x = 4", "before_context": "# second\n"}
    ]}, tmp_path / "wt")
    assert out["applied"] is True
    assert (tmp_path / "wt" / "core.py").read_text(encoding="utf-8").splitlines()[4] == "x = 4"
    refused = apply_action_to_copy(root, {"renames": [], "edits": [
        {"path": "core.py", "old_text": "x = 1", "new_text": "x = 4"}
    ]}, tmp_path / "wt2")
    assert refused["applied"] is False
    assert "not unique" in refused["reason"]
    assert "occurrence=1, line 1:" in (refused.get("output_tail") or "")
    assert "# first" in refused["output_tail"]


def test_zero_matches_still_uses_stable_prefix():
    from app.kernel.compute.structured_edit import EditApplyError, resolve_occurrence

    try:
        resolve_occurrence("a = 1\n", {"old_text": "b = 2", "new_text": "b = 3"}, path="z.py")
        raise AssertionError("missing")
    except EditApplyError as exc:
        assert str(exc).startswith("edit old_text is not unique in target (0 matches in z.py)")
