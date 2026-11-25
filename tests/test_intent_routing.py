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
    # Still read-only analysis, but it needs a whole-file written proposal, so it stays on
    # Direct Coder (agent) instead of the explain fast path (run agent-ff6b2e53-9e5ef24547f4).
    assert route_composer_mode("agent", prompt) == "agent"
    assert route_composer_mode("agent", "read the beast file and suggest 3 concrete improvements, numbered") == "agent"
    assert route_composer_mode("agent", "explain the beast file") == "ask"
    assert route_composer_mode("agent", "what does beast do") == "ask"
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


def test_suggest_weak_spots_that_require_patching_is_analysis():
    prompt = "read through the beast file and suggest any weak spots that require patching."
    assert is_analysis_prompt(prompt)
    assert is_review_prompt(prompt)
    assert route_composer_mode("agent", prompt) == "review"
    assert route_composer_mode("agent", "/agent " + prompt) == "review"


def test_explicit_apply_or_edit_stays_on_the_agent_path():
    assert route_composer_mode("agent", "apply those fixes to the beast file") == "agent"
    assert route_composer_mode("agent", "edit the beast file and patch the typo") == "agent"
    assert route_composer_mode("agent", "make the change to beast") == "agent"
