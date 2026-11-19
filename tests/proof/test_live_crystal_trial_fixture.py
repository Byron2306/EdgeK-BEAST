"""The live orchestration can be tested without paying for model calls."""
import json

from scripts.proof.run_live_crystal_trial import HOLDOUTS, TRAIN, capture, compare
from tests.crystal_fabric_support import CountingProvider, learn_script


class FixtureProvider(CountingProvider):
    def __init__(self, _governor):
        super().__init__()

    async def next_decision(self, prompt, *, run, turn):
        if self.calls == 0:
            module = run["request"]["implementation_target"].removesuffix(".py")
            variant = next(row for row in (TRAIN, *HOLDOUTS) if row["module"] == module)
            self.inner._decisions = learn_script(module, variant["constant"], variant["actual"], variant["expected"])
        return await super().next_decision(prompt, run=run, turn=turn)


def test_capture_then_comparison_runs_without_network(tmp_path):
    root = tmp_path / "trial"
    assert capture(root, FixtureProvider) == 0
    report = json.loads((root / "capture.json").read_text())
    assert report["status"] == "verified_awaiting_operator_promotion"
    assert report["source"]["independent_pass"]
    assert compare(root, "local test reviewer", FixtureProvider) == 0
    result = json.loads((root / "comparison" / "comparison.json").read_text())
    assert result["negative_pass"]
    assert all(row["off"]["observed_provider_attempts"] > row["on"]["observed_provider_attempts"]
               for row in result["rows"])


def test_trial_refuses_executable_replacement_and_unrelated_verifier():
    import asyncio

    import pytest

    from app.kernel.agents.planner_provider import parse_planner_decision
    from scripts.proof.run_live_crystal_trial import TrialRuntime

    runtime = TrialRuntime.__new__(TrialRuntime)
    runtime.module, runtime.constant, runtime.actual = "calc", "RATE", 3
    attempts = (
        ("worktree.replace_exact", {"path": "calc.py", "old_text": "RATE = 3", "new_text": "RATE = call()"}),
        ("worktree.replace_exact", {"path": "calc.py", "old_text": "RATE = 3", "new_text": "RATE = 4\nimport os"}),
        ("worktree.verify", {"command": ["python3", "-c", "print(1)"]}),
    )
    for tool, arguments in attempts:
        decision = parse_planner_decision({"decision_type": "tool", "tool_id": tool, "arguments": arguments})
        with pytest.raises(ValueError):
            asyncio.run(runtime._authorize_tool({}, "fixture", decision))


def test_full_context_reduces_to_model_literal_without_fixing_its_value():
    from scripts.proof.run_live_crystal_trial import TrialRuntime

    runtime = TrialRuntime.__new__(TrialRuntime)
    runtime.module, runtime.constant, runtime.actual = "calc", "RATE", 3
    runtime.fixture_source = "RATE = 3\n\n\ndef rate():\n    return RATE"
    args = {"path": "calc.py", "old_text": runtime.fixture_source,
            "new_text": "RATE = 5\n\n\ndef rate():\n    return RATE"}
    assert runtime._canonical_edit(args) == {"path": "calc.py", "old_text": "RATE = 3", "new_text": "RATE = 5"}


def test_full_context_refuses_a_second_change():
    import pytest

    from scripts.proof.run_live_crystal_trial import TrialRuntime

    runtime = TrialRuntime.__new__(TrialRuntime)
    runtime.module, runtime.constant, runtime.actual = "calc", "RATE", 3
    runtime.fixture_source = "RATE = 3\n\n\ndef rate():\n    return RATE"
    with pytest.raises(ValueError):
        runtime._canonical_edit({"path": "calc.py", "old_text": runtime.fixture_source,
                                 "new_text": "RATE = 4\n\n\ndef rate():\n    return 99"})
