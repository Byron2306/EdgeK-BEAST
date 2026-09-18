from __future__ import annotations

from app.kernel.agents.planner_provider import ScriptedPlannerProvider, parse_planner_decision
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


def _runtime_state(tmp_path):
    engine = AgentRunEngine(tmp_path)
    created = engine.create_run(
        session_id="phase2-multifile-guard",
        objective="Change two explicitly scoped files and verify them",
        mode="agent",
        provider="simulated",
        model="phase2-scripted",
        request={"context_files": ["values.py", "consumer.py"]},
    )
    runtime = AgentPlannerRuntime(engine, ScriptedPlannerProvider([]))
    state = runtime._load_state(created["run_id"])
    state.observations = [
        {"tool_id": "workspace.index", "status": "completed", "result": {"ok": True}},
        {"tool_id": "worktree.bind", "status": "completed", "result": {"worktree_root": str(tmp_path / "wt")}},
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "values.py", "content": "VALUE = 1\n"}},
        {"tool_id": "workspace.read_range", "status": "completed", "result": {"path": "consumer.py", "content": "from values import VALUE\nRESULT = VALUE\n"}},
        {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "values.py"}},
    ]
    return runtime, engine.store.get_run(created["run_id"]), state


def test_required_phase_allows_second_bounded_inspected_scoped_mutation_before_verify(tmp_path):
    runtime, run, state = _runtime_state(tmp_path)
    decision = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "worktree.replace_exact",
        "arguments": {"path": "consumer.py", "old_text": "RESULT = VALUE", "new_text": "RESULT = VALUE + 1"},
    })
    assert runtime._required_phase_decision(run, state, decision) is None


def test_required_phase_still_forces_verify_for_out_of_scope_second_mutation(tmp_path):
    runtime, run, state = _runtime_state(tmp_path)
    decision = parse_planner_decision({
        "decision_type": "tool",
        "tool_id": "worktree.replace_exact",
        "arguments": {"path": "rogue.py", "old_text": "A", "new_text": "B"},
    })
    required = runtime._required_phase_decision(run, state, decision)
    assert required is not None
    assert required.tool_id == "worktree.verify"
    assert required.arguments["command"][:3] == ["python", "-m", "py_compile"]
    assert required.arguments["command"][-1] == "values.py"
