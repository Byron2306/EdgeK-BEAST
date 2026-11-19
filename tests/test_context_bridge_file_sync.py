"""Phase 5: context bridge (selection -> model) and real-time file sync."""

from __future__ import annotations

import time

import pytest

from app.kernel.agents.context_bridge import ContextBridge, SelectedFile, build_context
from app.kernel.agents.file_sync import FileSyncWatcher, WorkspaceSync, scan_workspace


def test_selection_becomes_bounded_model_messages(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")

    bridge = ContextBridge(tmp_path, max_chars_each=1000, max_total_chars=5000)
    result = bridge.build([SelectedFile("src/app.py"), "notes.md"], "Summarize the app")

    assert result["stats"]["included"] == 2
    assert result["stats"]["excluded"] == 0
    assert "line2" in result["context_block"]
    assert "## src/app.py" in result["context_block"]
    assert result["messages"][0]["role"] == "system"
    assert result["messages"][1] == {"role": "user", "content": "Summarize the app"}
    assert result["files"][0]["content_hash"].startswith("sha256:")


def test_line_ranges_are_honoured(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = ContextBridge(tmp_path).build([SelectedFile("app.py", 2, 2)])

    assert result["files"][0]["content"] == "two"
    assert result["files"][0]["start_line"] == 2
    assert result["files"][0]["end_line"] == 2


def test_sensitive_and_binary_files_are_excluded(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "image.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "ok.txt").write_text("public", encoding="utf-8")

    result = ContextBridge(tmp_path).build([".env", "image.bin", "ok.txt"])

    reasons = {item["path"]: item["reason"] for item in result["excluded"]}
    assert reasons == {".env": "sensitive_file", "image.bin": "binary"}
    assert {item["path"] for item in result["files"]} == {"ok.txt"}


def test_selection_outside_the_workspace_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes the workspace"):
        ContextBridge(tmp_path).build([str(outside)])


def test_per_file_and_total_budgets_are_enforced(tmp_path):
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text("x" * 100, encoding="utf-8")

    per_file = ContextBridge(tmp_path, max_chars_each=10).build(["a.txt"])
    assert per_file["files"][0]["truncated"] is True
    assert per_file["files"][0]["content"].endswith("[truncated]")

    limited = ContextBridge(tmp_path, max_files=2).build(["a.txt", "b.txt", "c.txt"])
    assert limited["stats"]["included"] == 2
    assert {"path": "c.txt", "reason": "max_files"} in limited["excluded"]

    tight = ContextBridge(tmp_path, max_total_chars=50).build(["a.txt", "b.txt"])
    assert tight["stats"]["included"] == 1
    assert tight["excluded"][0]["reason"] == "max_total_chars"


def test_build_context_helper_applies_budget(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")

    result = build_context(tmp_path, ["a.txt"], "Explain", max_chars_each=100)

    assert result["objective"] == "Explain"
    assert result["files"][0]["content"] == "hello"


def test_scan_and_diff_report_added_changed_removed(tmp_path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("module.exports = 1", encoding="utf-8")

    sync = WorkspaceSync(tmp_path)
    first = sync.snapshot()

    assert "a.txt" in first.files
    assert ".env" not in first.files
    assert "node_modules/dep.js" not in first.files
    assert first.files["a.txt"].sha256.startswith("sha256:")

    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    (tmp_path / "b.txt").write_text("new", encoding="utf-8")
    second = sync.snapshot()
    diff = second.diff(first)

    assert diff["changed"] == ["a.txt"]
    assert diff["added"] == ["b.txt"]
    assert diff["removed"] == []

    (tmp_path / "b.txt").unlink()
    assert sync.snapshot().diff(second)["removed"] == ["b.txt"]


def test_scan_workspace_helper_returns_file_states(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    states = scan_workspace(tmp_path)
    assert list(states) == ["a.txt"]


def test_watcher_emits_changes_on_a_background_thread(tmp_path):
    events: list[dict[str, list[str]]] = []
    sync = WorkspaceSync(tmp_path)
    watcher = FileSyncWatcher(sync, interval_s=0.05, on_change=events.append)

    watcher.start()
    try:
        deadline = time.monotonic() + 3.0
        (tmp_path / "watched.txt").write_text("v1", encoding="utf-8")
        while not events and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        watcher.stop()

    assert events, "watcher did not emit a diff"
    assert "watched.txt" in events[0]["added"]
    assert watcher.running is False
