"""A wrong model tool packet may be repaired once, never silently executed."""
import asyncio
import subprocess

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


def _setup(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="schema-repair", objective="inspect calc.py", mode="agent")
    return engine, run


def _invalid():
    return PlannerDecision(
        decision_type=PlannerDecisionType.TOOL,
        tool_id="workspace.index",
        arguments={"path": "calc.py"},
    )


def _provider(tool_id="workspace.index", arguments=None):
    return ScriptedPlannerProvider([{
        "decision_type": "tool", "tool_id": tool_id,
        "arguments": arguments if arguments is not None else {"limit": 50, "include_symbols": True},
    }])


def test_one_model_schema_correction_recovers_same_tool(tmp_path):
    async def scenario():
        engine, run = _setup(tmp_path)
        planner = AgentPlannerRuntime(engine, _provider(), max_turns=1)
        repaired, reason = await planner._one_schema_correction(run, run["run_id"], _invalid(), 1)
        assert reason == ""
        assert repaired.tool_id == "workspace.index"
        assert repaired.arguments == {"limit": 50, "include_symbols": True}
        assert engine.store.approvals(run["run_id"]) == []
        kinds = [event["event_type"] for event in engine.store.events(run["run_id"], limit=50)]
        assert "agent.planner.tool_arguments_refused" in kinds
        assert "agent.provider.tool_schema_retry_recovered" in kinds
        assert engine.store.verify_chain(run["run_id"])["ok"] is True
    asyncio.run(scenario())


def test_second_invalid_schema_refuses_without_authority(tmp_path):
    async def scenario():
        engine, run = _setup(tmp_path)
        planner = AgentPlannerRuntime(engine, _provider(arguments={"path": "calc.py"}), max_turns=1)
        repaired, reason = await planner._one_schema_correction(run, run["run_id"], _invalid(), 1)
        assert repaired is None
        assert "REFUSE_INVALID_TOOL_ARGUMENTS:workspace.index" in reason
        assert engine.store.approvals(run["run_id"]) == []
        kinds = [event["event_type"] for event in engine.store.events(run["run_id"], limit=50)]
        assert "agent.provider.tool_schema_retry_refused" in kinds
    asyncio.run(scenario())


def test_schema_correction_cannot_switch_tools(tmp_path):
    async def scenario():
        engine, run = _setup(tmp_path)
        planner = AgentPlannerRuntime(engine, _provider("worktree.bind", {}), max_turns=1)
        repaired, reason = await planner._one_schema_correction(run, run["run_id"], _invalid(), 1)
        assert repaired is None and "changed the tool identity" in reason
        assert engine.store.approvals(run["run_id"]) == []
    asyncio.run(scenario())


def test_planner_records_terminal_refusal_instead_of_throwing(tmp_path):
    async def scenario():
        engine, run = _setup(tmp_path)
        # 1st model turn and its only schema correction both contain the invalid key.
        provider = ScriptedPlannerProvider([{
            "decision_type": "tool", "tool_id": "workspace.index", "arguments": {"path": "calc.py"}
        }, {
            "decision_type": "tool", "tool_id": "workspace.index", "arguments": {"path": "calc.py"}
        }])
        planner = AgentPlannerRuntime(engine, provider, max_turns=1)
        outcome = await planner.run(run["run_id"])
        assert str(outcome["state"]) == "policy_blocked"
        assert "REFUSE_INVALID_TOOL_ARGUMENTS" in str(outcome["error"])
        assert engine.store.approvals(run["run_id"]) == []
        assert engine.store.verify_chain(run["run_id"])["ok"] is True
    asyncio.run(scenario())
