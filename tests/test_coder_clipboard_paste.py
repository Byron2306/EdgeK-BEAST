"""Copy/paste ergonomics in bin/beast ui (Byron, t207u): OSC52 copies, mouse release, multi-line paste."""
from pathlib import Path

import pytest
from textual import events

from app.cli.coder import BeastCoderApp, PasteInput
from app.cli.coder_state import parse_slash_command
from tests.test_coder_tli import FakeRuntimeClient


@pytest.mark.asyncio
async def test_multiline_paste_is_one_message_not_line_by_line(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    submitted: list[str] = []

    async def fake_submit(value: str) -> None:
        submitted.append(value)

    async with app.run_test(size=(100, 30)) as pilot:
        app._submit_input = fake_submit
        box = app.query_one("#coder-input", PasteInput)
        box.focus()
        box.insert_text_at_cursor("Fix this: ")
        box.post_message(events.Paste("line one\nline two\r\nline three\n"))
        await pilot.pause()
        assert box.value == "Fix this: [Pasted #1: 3 lines]"
        await pilot.press("enter")
        await pilot.pause()
    assert submitted == ["Fix this: line one\nline two\nline three"]


@pytest.mark.asyncio
async def test_single_line_paste_is_inline(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        box = app.query_one("#coder-input", PasteInput)
        box.focus()
        box.post_message(events.Paste("just one line"))
        await pilot.pause()
        assert box.value == "just one line" and not box.pastes


@pytest.mark.asyncio
async def test_copy_answer_diff_selection_and_mouse_toggle(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(100, 30)):
        await app.submit_text("Explain README.md")
        await app.submit_text("/copy answer")
        assert app.clipboard.strip() and "Explain README.md" not in app.clipboard
        app.diff_bundle = {"diff": "--- a/x\n+++ b/x\n-old\n+new\n"}
        await app.submit_text("/copy diff")
        assert app.clipboard.endswith("+new\n")
        app._selected_text = lambda: "picked text"
        app.action_copy_smart()
        assert app.clipboard == "picked text"
        app._selected_text = lambda: ""
        app.action_copy_smart()  # no selection: falls back to the last run
        assert "Explain README.md" in app.clipboard
        await app.submit_text("/mouse off")
        assert app._mouse_captured is False
        await app.submit_text("/mouse on")
        assert app._mouse_captured is True
        await app.submit_text("/help")
        help_text = "\n".join(str(e.get("content") or "") for e in app.transcript_entries)
        assert "/mouse" in help_text and "OSC 52" in help_text and "/copy" in help_text


def test_new_commands_parse():
    assert parse_slash_command("/mouse off").argument == "off"
    assert parse_slash_command("/copy diff").name == "copy"
