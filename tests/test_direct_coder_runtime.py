"""Focused direct-coder acceptance contracts; no network and no planner agent."""
import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType


def tool(name, args=None):
    return PlannerDecision(
        decision_type=PlannerDecisionType.TOOL,
        tool_id=name,
        arguments=args or {},
    )


class ScriptedCodingModel:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls = 0

    async def next_decision(self, prompt, *, run, turn):
        assert "DIRECT CODING AGENT" in prompt
        self.calls += 1
        item = next(self.decisions)
        if isinstance(item, BaseException):
            raise item
        return item


@dataclass
class Spec:
    tool_id: str
    requires_approval: bool = False
    risk: object = None


class Registry:
    def get(self, name):
        return Spec(name, requires_approval=name.startswith("worktree."))

    def validate_arguments(self, spec, args):
        return dict(args)


class Store:
    def __init__(self, run):
        self.run = run
        self.approvals = {}

    def get_run(self, run_id):
        assert run_id == self.run["run_id"]
        return self.run

    def transition(self, run_id, state, *, error=""):
        self.run["state"] = getattr(state, "value", str(state))
        self.run["error"] = error

    def create_approval(self, run_id, request):
        self.approvals[request["request_id"]] = {
            "approval_id": request["request_id"], "status": "pending",
        }

    def resolve_approval(self, run_id, approval_id, payload):
        approval = self.approvals[approval_id]
        approval["status"] = "approved" if payload["approved"] else "rejected"
        return approval

    def get_approval(self, run_id, approval_id):
        return self.approvals.get(approval_id)


class Engine:
    def __init__(self, *, autonomy="autopilot"):
        self.store = Store({
            "run_id": "agent-test", "state": "created",
            "objective": "Make a bounded change and verify it",
            "provider": "nvidia_nim", "model": "nvidia/test",
            "request": {"autonomy": autonomy, "context_files": ["a.py"]},
            "checkpoint": {},
        })
        self.tool_registry = Registry()
        self.events = []
        self.calls = []

    def emit(self, run_id, event, payload):
        self.events.append((event, payload))
        return {"event_type": event}

    def merge_checkpoint(self, run_id, payload):
        self.store.run["checkpoint"].update(payload)
        return self.store.run

    def list_tools(self):
        return [
            {"tool_id": name, "description": "test tool",
             "input_schema": {"type": "object", "properties": {}}}
            for name in ("workspace.read_range", "worktree.bind",
                         "worktree.write_file", "worktree.verify")
        ]

    async def execute_tool(self, run_id, tool_id, arguments, *,
                           execution_target="local", approval_id=""):
        self.calls.append((tool_id, approval_id))
        return {"tool_id": tool_id, "status": "completed", "result": {"ok": True}}


def test_direct_coder_timeout_pauses_then_recovers_without_planner_subagent():
    engine = Engine()
    model = ScriptedCodingModel([
        tool("workspace.read_range", {"path": "a.py"}),
        tool("worktree.bind"),
        TimeoutError("injected provider timeout"),
        tool("worktree.write_file", {"path": "a.py", "content": "x"}),
        tool("worktree.verify", {"command": "pytest -q"}),
        PlannerDecision(decision_type=PlannerDecisionType.COMPLETE,
                        summary="verified"),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=12)

    async def check():
        for _ in range(2):
            await coder.run_one_turn("agent-test")
        assert [x[0] for x in engine.calls].count("worktree.bind") == 1
        paused = await coder.run_one_turn("agent-test")
        assert paused["state"] == "paused"
        assert paused["state"] != "policy_blocked"
        for _ in range(3):
            result = await coder.run_one_turn("agent-test")
        assert result["state"] == "completed"
        assert [x[0] for x in engine.calls].count("worktree.bind") == 1
        assert [x[0] for x in engine.calls].count("worktree.verify") == 1
        assert any(event == "agent.coder.started" for event, _ in engine.events)
        assert not any(event.startswith("agent.planner.") for event, _ in engine.events)

    asyncio.run(check())


def test_manual_approval_resumes_exact_tool_once():
    engine = Engine(autonomy="manual")
    model = ScriptedCodingModel([tool("worktree.bind")])
    coder = DirectCoderRuntime(engine, model)
    async def check():
        first = await coder.run_one_turn("agent-test")
        assert first["state"] == "waiting_for_approval"
        assert engine.calls == []
        assert model.calls == 1
        approval_id = next(iter(engine.store.approvals))
        engine.store.resolve_approval("agent-test", approval_id, {"approved": True})
        second = await coder.run_one_turn("agent-test")
        assert second["state"] == "observing"
        assert engine.calls == [("worktree.bind", approval_id)]
        assert model.calls == 1
    asyncio.run(check())


def test_cannot_complete_mutation_without_verification():
    engine = Engine()
    model = ScriptedCodingModel([
        tool("worktree.bind"),
        tool("worktree.write_file", {"path": "a.py", "content": "x"}),
        PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="done"),
        tool("worktree.verify", {"command": "pytest -q"}),
        PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="verified"),
    ])
    coder = DirectCoderRuntime(engine, model)
    async def check():
        for _ in range(3):
            await coder.run_one_turn("agent-test")
        assert engine.store.run["state"] != "completed"
        await coder.run_one_turn("agent-test")
        done = await coder.run_one_turn("agent-test")
        assert done["state"] == "completed"
        assert any(e == "agent.coder.completion_refused" for e, _ in engine.events)
    asyncio.run(check())
