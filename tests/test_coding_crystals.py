from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.kernel.compute.coding_crystals import CODING_OPCODE_TOOLS, coding_opcode_registry, resolve_constant
from app.kernel.compute.typed_crystal_ir import default_opcode_registry

sys.path.insert(0, str(Path(__file__).resolve().parent))

UNITTEST_FAIL = (
    "F\n======================================================================\n"
    "FAIL: test_rate (test_calc.AssertionCase.test_rate)\n"
    "----------------------------------------------------------------------\n"
    "Traceback (most recent call last):\n  File \"test_calc.py\", line 9, in test_rate\n"
    "    self.assertEqual(calc.rate(), 4)\nAssertionError: 3 != 4\n\nFAILED (failures=1)\n"
)
TARGET = "RATE = 3\n\n\ndef rate():\n    return RATE\n"


# --- Task 1: reviewed coding opcodes and resolver ------------------------------------------------

def test_coding_catalog_validates_and_is_separate_from_physical_catalog():
    registry = coding_opcode_registry()
    catalog = registry.catalog()
    assert catalog["contains_executable_code"] is False
    assert catalog["catalog_digest"] != default_opcode_registry().catalog()["catalog_digest"]
    names = {entry["opcode"] for entry in catalog["entries"]}
    assert names == {"worktree.inspect", "worktree.bind", "worktree.verify", "repair.resolve_constant",
                     "worktree.replace_exact", "crystal.complete"}
    for entry in catalog["entries"]:
        if entry["authority"] == "bounded_execute":
            assert entry["rollback_key"]
    assert registry.resolve("repair.resolve_constant").authority == "proposal_only"
    assert registry.resolve("worktree.verify").authority == "verify_only"


def test_exactly_the_reviewed_tools_are_mapped():
    assert CODING_OPCODE_TOOLS == {
        "worktree.inspect": "workspace.read_range",
        "worktree.bind": "worktree.bind",
        "worktree.verify": "worktree.verify",
        "worktree.replace_exact": "worktree.replace_exact",
    }


def test_resolver_handles_unittest_and_pytest_failures():
    assert resolve_constant(UNITTEST_FAIL, TARGET) == {"old_text": "RATE = 3", "new_text": "RATE = 4", "name": "RATE"}
    pytest_out = "E       assert 3 == 4\nE        +  where 3 = rate()\nFAILED test_calc.py::test_rate"
    assert resolve_constant(pytest_out, TARGET)["new_text"] == "RATE = 4"
    assert resolve_constant("AssertionError: 'a' != 'b'", "MODE = 'a'\n") == {
        "old_text": "MODE = 'a'", "new_text": "MODE = 'b'", "name": "MODE"}


@pytest.mark.parametrize("output,target", [
    (UNITTEST_FAIL, "RATE = 3\nOTHER = 3\n"),                       # ambiguous assignment
    (UNITTEST_FAIL, "RATE = 5\n"),                                   # absent assignment
    ("OK\n", TARGET),                                                 # no failure
    (UNITTEST_FAIL + "AssertionError: 1 != 2\n", TARGET),            # several failures
    ("AssertionError: 3 != __import__('os')\n", TARGET),             # non-literal expectation
])
def test_resolver_refuses_ambiguous_absent_or_unsafe(output, target):
    assert resolve_constant(output, target) is None


# --- Task 2: extraction, negative evidence and registry ------------------------------------------

@pytest.fixture(scope="module")
def learned(tmp_path_factory):
    from crystal_fabric_support import run_learn

    base = tmp_path_factory.mktemp("learn")
    result = run_learn(base / "repo", base / "envelopes.sqlite3")
    assert result["final"]["state"] == "completed"
    return result


def _registry(tmp_path):
    from app.kernel.compute.coding_crystals import CodingCrystalRegistry

    return CodingCrystalRegistry(tmp_path / "coding_crystals.sqlite3")


def test_verified_envelope_extracts_candidate_with_only_reviewed_opcodes(learned, tmp_path):
    from app.kernel.compute.coding_crystals import REVIEWED_TOOLS, CodingCrystalExtractor

    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    assert candidate is not None
    candidate.validate()
    assert candidate.task_family == "fix-failing-assertion"
    assert [step["opcode"] for step in candidate.steps] == [
        "worktree.inspect", "worktree.bind", "worktree.verify", "repair.resolve_constant",
        "worktree.replace_exact", "worktree.verify", "crystal.complete"]
    assert {step["tool_id"] for step in candidate.steps if step["tool_id"]} <= REVIEWED_TOOLS
    assert candidate.source_envelope_digest == learned["envelope"].envelope_digest
    assert candidate.learned_budget["model_turns"] == learned["final"]["budget"]["model_turns"]
    registry = _registry(tmp_path)
    registry.add_candidate(candidate)
    assert registry.get(candidate.crystal_id)["status"] == "candidate"
    assert registry.active_for_family("fix-failing-assertion") is None


def test_failed_envelope_records_negative_evidence_and_no_candidate(learned, tmp_path):
    import dataclasses

    from app.kernel.compute.coding_crystals import CodingCrystalExtractor

    failed = dataclasses.replace(
        learned["envelope"], verification={**learned["envelope"].verification, "passed": False}, envelope_digest="",
    ).sealed()
    registry = _registry(tmp_path)
    assert CodingCrystalExtractor().extract(failed, learned["observations"], registry=registry) is None
    negatives = registry.negatives("fix-failing-assertion")
    assert negatives and negatives[0]["kind"] == "unverified_episode"
    assert negatives[0]["evidence_digest"] == failed.envelope_digest


def test_unreproducible_edit_is_refused(learned, tmp_path):
    from app.kernel.compute.coding_crystals import CodingCrystalExtractor

    observations = [dict(item) for item in learned["observations"]]
    for item in observations:
        if item["tool_id"] == "worktree.replace_exact":
            item["arguments"] = {**item["arguments"], "new_text": "RATE = 99"}
    registry = _registry(tmp_path)
    assert CodingCrystalExtractor().extract(learned["envelope"], observations, registry=registry) is None
    assert registry.negatives("fix-failing-assertion")[0]["kind"] == "edit_not_reproducible"


def test_illegal_opcode_or_tool_is_refused_at_compile_time(learned, tmp_path):
    import dataclasses

    from app.kernel.compute.coding_crystals import CodingCrystalExtractor

    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    bad_tool = list(candidate.steps)
    bad_tool[4] = {**bad_tool[4], "tool_id": "workspace.write_file"}
    bad_opcode = list(candidate.steps)
    bad_opcode[1] = {"opcode": "shell.exec", "tool_id": "shell.exec", "expect": ""}
    no_postcondition = list(candidate.steps)[:5] + [candidate.steps[-1]]
    registry = _registry(tmp_path)
    for steps in (bad_tool, bad_opcode, no_postcondition):
        tampered = dataclasses.replace(candidate, steps=tuple(steps), digest="").sealed()
        with pytest.raises(ValueError):
            tampered.validate()
        with pytest.raises(ValueError):
            registry.add_candidate(tampered)


def test_tampered_registry_record_is_refused(learned, tmp_path):
    import sqlite3

    from app.kernel.compute.coding_crystals import CodingCrystalExtractor

    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    registry = _registry(tmp_path)
    registry.add_candidate(candidate)
    with sqlite3.connect(registry.path) as connection:
        connection.execute("UPDATE coding_crystals SET status='promoted'")
    with pytest.raises(ValueError):
        registry.get(candidate.crystal_id)
    assert registry.active_for_family("fix-failing-assertion") is None


def test_registry_lifecycle_promote_reuse_demote(learned, tmp_path):
    from app.kernel.compute.coding_crystals import CodingCrystalExtractor
    from app.kernel.compute.heldout_replay import ReplayReceipt

    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    registry = _registry(tmp_path)
    registry.add_candidate(candidate)
    with pytest.raises(PermissionError):
        registry.promote(candidate.crystal_id, ReplayReceipt(candidate.crystal_id, 2, 2, False, "held-out replay failed"))
    registry.promote(candidate.crystal_id, ReplayReceipt(candidate.crystal_id, 3, 3, True, "held-out replay passed"))
    assert registry.active_for_family("fix-failing-assertion").crystal_id == candidate.crystal_id
    registry.record_reuse(candidate.crystal_id, run_id="r1", outcome="verified")
    assert registry.get(candidate.crystal_id)["reuse_count"] == 1
    registry.demote(candidate.crystal_id, reason="postcondition_failed", evidence_digest="sha256:x")
    assert registry.get(candidate.crystal_id)["status"] == "demoted"
    assert registry.active_for_family("fix-failing-assertion") is None
    assert registry.negatives("fix-failing-assertion")[-1]["kind"] == "postcondition_failed"


# --- Task 3: held-out replay, promotion and planning-time reuse ----------------------------------

def _promoted_stack(learned, base):
    from crystal_fabric_support import crystal_stack

    from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalPlanner
    from app.kernel.compute.heldout_replay import ReplayReceipt

    stack = crystal_stack(base)
    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    stack["registry"].add_candidate(candidate)
    stack["registry"].promote(candidate.crystal_id, ReplayReceipt(candidate.crystal_id, 3, 3, True, "held-out replay passed"))
    stack["candidate"] = candidate
    stack["planner"] = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"])
    return stack


def _events(result, event_type):
    return [e["payload"] for e in result["events"] if e["event_type"] == event_type]


def test_promoted_crystal_is_reused_without_consulting_the_model(learned, tmp_path):
    from crystal_fabric_support import HELD_OUT_VARIANTS, run_with_planner

    stack = _promoted_stack(learned, tmp_path / "stack")
    result = run_with_planner(tmp_path / "repo", stack["planner"], variant=HELD_OUT_VARIANTS[0])
    assert result["final"]["state"] == "completed"
    assert result["provider"].calls == 0
    budget = result["final"]["budget"]
    assert budget.get("model_turns", 0) == 0
    assert budget["tool_calls_crystal"] >= 4  # the runtime itself enforces the final verify and sourceplan closure
    assert budget["tool_calls"] <= 6
    assert _events(result, "agent.crystal.completed")
    assert result["envelope"].verification["passed"] is True
    assert _events(result, "agent.crystal.activated")[0]["crystal_id"] == stack["candidate"].crystal_id
    assert stack["registry"].get(stack["candidate"].crystal_id)["reuse_count"] == 1
    tools = {o["tool_id"] for o in result["observations"]}
    assert tools <= {"workspace.read_range", "worktree.bind", "worktree.verify", "worktree.replace_exact",
                     "worktree.sourceplan_draft"}


@pytest.mark.parametrize("overrides,reason", [
    ({"implementation_target": ""}, "implementation_target_missing"),
    ({"implementation_target": "missing.py"}, "implementation_target_absent"),
    ({"implementation_target": "../escape.py"}, "implementation_target_unsafe"),
])
def test_applicability_gate_refuses_before_any_tool(learned, tmp_path, overrides, reason):
    from crystal_fabric_support import HELD_OUT_VARIANTS, run_with_planner

    stack = _promoted_stack(learned, tmp_path / "stack")
    result = run_with_planner(tmp_path / "repo", stack["planner"], variant=HELD_OUT_VARIANTS[1],
                              request_overrides=overrides)
    refused = _events(result, "agent.crystal.refused")
    assert refused and refused[0]["reason"] == reason
    assert not _events(result, "agent.crystal.activated")
    assert result["provider"].calls >= 1  # planning fell back to the model


def test_other_task_family_never_activates(learned, tmp_path):
    from crystal_fabric_support import HELD_OUT_VARIANTS, run_with_planner

    stack = _promoted_stack(learned, tmp_path / "stack")
    result = run_with_planner(tmp_path / "repo", stack["planner"], variant=HELD_OUT_VARIANTS[1],
                              request_overrides={"task_family": "rename-symbol"})
    assert not _events(result, "agent.crystal.activated")
    assert result["provider"].calls >= 1


def test_misfit_already_green_is_refused_before_mutation(learned, tmp_path):
    from crystal_fabric_support import MISFIT_ALREADY_GREEN, run_with_planner

    stack = _promoted_stack(learned, tmp_path / "stack")
    result = run_with_planner(tmp_path / "repo", stack["planner"], variant=MISFIT_ALREADY_GREEN)
    aborted = _events(result, "agent.crystal.aborted")
    assert aborted and aborted[0]["reason"] == "precondition_not_failing"
    assert "worktree.replace_exact" not in {o["tool_id"] for o in result["observations"]}
    assert stack["registry"].get(stack["candidate"].crystal_id)["status"] == "promoted"  # a misfit is not a defect
    assert result["provider"].calls >= 1


def test_used_capability_cannot_be_replayed(learned, tmp_path):
    from crystal_fabric_support import HELD_OUT_VARIANTS, create_assertion_run, make_assertion_repo

    stack = _promoted_stack(learned, tmp_path / "stack")
    root = make_assertion_repo(tmp_path / "repo", **HELD_OUT_VARIANTS[0])
    engine, run_id = create_assertion_run(root, module=HELD_OUT_VARIANTS[0]["module"])
    run = engine.store.get_run(run_id)
    first = stack["planner"].activate(run, run_id, engine=engine)
    assert first is not None and first.capability["capability_id"]
    assert stack["planner"].activate(run, run_id, engine=engine, capability=first.capability) is None
    refused = [e["payload"] for e in engine.store.events(run_id, limit=200) if e["event_type"] == "agent.crystal.refused"]
    assert refused[-1]["reason"].startswith("capability_refused") and "already consumed" in refused[-1]["reason"]
    forged = dict(first.capability, request_digest="sha256:" + "0" * 64)
    assert stack["planner"].activate(run, run_id, engine=engine, capability=forged) is None


def test_failing_postcondition_demotes_and_falls_back(learned, tmp_path):
    from crystal_fabric_support import SECOND_BUG_VARIANT, run_with_planner

    stack = _promoted_stack(learned, tmp_path / "stack")
    result = run_with_planner(tmp_path / "repo", stack["planner"], variant=SECOND_BUG_VARIANT)
    crystal_id = stack["candidate"].crystal_id
    assert stack["registry"].get(crystal_id)["status"] == "demoted"
    assert stack["registry"].negatives("fix-failing-assertion")[-1]["kind"] == "postcondition_failed"
    assert _events(result, "agent.crystal.aborted")[-1]["reason"] == "postcondition_failed"
    assert result["provider"].calls >= 1
    assert stack["registry"].active_for_family("fix-failing-assertion") is None


def test_runtime_refuses_crystal_tools_outside_reviewed_ops(tmp_path):
    from crystal_fabric_support import HELD_OUT_VARIANTS, run_with_planner

    from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

    class RogueSession:
        aborted = ""

        def next_decision(self, run, state):
            return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="workspace.write_file",
                                   arguments={"path": "pricing.py", "content": "TAX = 9\n"})

        def abort(self, reason):
            self.aborted = reason

    session = RogueSession()

    class RoguePlanner:
        def activate(self, run, run_id, *, engine, capability=None):
            return session

    result = run_with_planner(tmp_path / "repo", RoguePlanner(), variant=HELD_OUT_VARIANTS[0])
    refused = _events(result, "agent.crystal.refused")
    assert refused and refused[0]["reason"] == "unreviewed_tool" and refused[0]["tool_id"] == "workspace.write_file"
    assert session.aborted == "unreviewed_tool"
    assert "workspace.write_file" not in {o["tool_id"] for o in result["observations"]}
    assert (tmp_path / "repo" / "pricing.py").read_text().startswith("TAX = 7")


def test_heldout_replay_promotes_only_when_all_variants_pass(learned, tmp_path):
    from crystal_fabric_support import crystal_stack

    from app.kernel.compute.coding_crystals import CodingCrystalExtractor, replay_candidate

    stack = crystal_stack(tmp_path / "stack")
    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    stack["registry"].add_candidate(candidate)
    failing = replay_candidate(stack["registry"], candidate, ["a", "b", "c"], lambda v: v != "b")
    assert failing.promoted is False
    assert stack["registry"].get(candidate.crystal_id)["status"] == "candidate"
    assert stack["registry"].negatives("fix-failing-assertion")[-1]["kind"] == "heldout_replay_failed"
    too_few = replay_candidate(stack["registry"], candidate, ["a", "b"], lambda v: True)
    assert too_few.promoted is False
    passing = replay_candidate(stack["registry"], candidate, ["a", "b", "c"], lambda v: True)
    assert passing.promoted is True
    assert stack["registry"].active_for_family("fix-failing-assertion").crystal_id == candidate.crystal_id
