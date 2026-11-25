from __future__ import annotations

from pathlib import Path

from app.kernel.agents.intent_routing import (
    is_analysis_prompt,
    is_review_prompt,
    resolve_context_files,
    route_composer_mode,
)


def test_byron_summarize_prompt_is_analysis_not_a_patch():
    prompt = "proceed reading this file, summarize all functions and list any weaknesses"
    assert is_analysis_prompt(prompt)
    assert is_review_prompt(prompt)
    assert route_composer_mode("agent", prompt) == "review"
    assert route_composer_mode("edit", prompt) == "edit"
    assert route_composer_mode("ask", prompt) == "ask"


def test_byron_suggest_fixes_prompt_is_analysis():
    prompt = "read the beast file and suggest any fixes to improve it"
    assert is_analysis_prompt(prompt)
    assert route_composer_mode("agent", prompt) == "ask"
    assert route_composer_mode("agent", "Fix the typo in beast") == "agent"
    assert route_composer_mode("agent", "Add tests for the planner") == "agent"


def test_swarm_prefix_does_not_hide_an_analysis_prompt():
    prompt = (
        "Decompose this request into independent subtasks, then complete every "
        "subtask in this workspace and verify the combined result: proceed reading "
        "this file, summarize all functions and list any weaknesses"
    )
    assert is_analysis_prompt(prompt)


def test_resolve_context_files_finds_extensionless_and_this_file(tmp_path: Path):
    (tmp_path / "beast").write_text("#!/usr/bin/env python3\n")
    (tmp_path / "coder.py").write_text("pass\n")
    assert resolve_context_files(tmp_path, "read the beast file") == ("beast",)
    assert resolve_context_files(tmp_path, "Explain coder.py. Ignore missing.bak.") == ("coder.py",)
    # Two visible files, so "this file" is not guessed.
    assert "beast" not in resolve_context_files(tmp_path, "proceed reading this file")

    only = tmp_path / "only-ws"
    only.mkdir()
    (only / "beast").write_text("print('hi')\n")
    assert resolve_context_files(only, "proceed reading this file, summarize all functions") == ("beast",)
