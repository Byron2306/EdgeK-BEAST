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


def test_missing_effect_runner_pauses_before_spending_model_turn(tmp_path):
    from app.kernel.agents.effect_ts_bridge import EffectTSBridge

    engine = Engine()
    bridge = EffectTSBridge(runner=tmp_path / "absent.mjs")
    engine.tool_runtime = SimpleNamespace(effect_executor=SimpleNamespace(bridge=bridge))
    model = ScriptedCodingModel([tool("worktree.bind")])
    coder = DirectCoderRuntime(engine, model)

    result = asyncio.run(coder.run_one_turn("agent-test"))
    assert result["state"] == "paused"
    assert "effect runtime script missing" in result["error"]
    assert model.calls == 0


def test_swarm_is_explicit_and_failure_proposal_does_not_execute(tmp_path, monkeypatch):
    from app.kernel.agents import direct_coder_hooks as hooks

    engine = Engine()
    engine.workspace_root = tmp_path
    engine.store.run["request"]["swarm"] = True
    engine.store.claim_swarm_recovery = lambda run_id: True
    engine.store.run["checkpoint"]["worktree_root"] = str(tmp_path / "bound")
    monkeypatch.setattr(hooks, "local_binding_identity", lambda run: (str(tmp_path / "bound"), "task", "branch", "base"))
    monkeypatch.setattr(hooks, "local_binding_error", lambda *_: "")
    monkeypatch.setattr(hooks, "specialist_enabled", lambda: True)
    calls = []
    async def recovery(**kwargs):
        calls.append(kwargs["target"])
        return {"path": "a.py", "old_text": "old", "new_text": "new"}, "candidate_grounded", {"generated": True, "model": "local"}
    monkeypatch.setattr(hooks, "recover", recovery)
    model = ScriptedCodingModel([tool("worktree.replace_exact", {"path": "a.py"})])
    async def fail(*args, **kwargs):
        raise ValueError("missing old_text")
    engine.execute_tool = fail
    coder = DirectCoderRuntime(engine, model)
    asyncio.run(coder.run_one_turn("agent-test"))

    assert calls == ["a.py"]
    assert engine.calls == []
    assert any(e == "agent.integration.fired" and p["capability"] == "swarm_roles" and p["roles"]
               for e, p in engine.events)
    assert engine.store.run["checkpoint"]["direct_coder"]["observations"][-1]["result"]["candidate"]["old_text"] == "old"
    assert not any(e.startswith("agent.planner.") for e, _ in engine.events)


def test_opt_in_integrations_mark_only_admitted_navigation_as_used(tmp_path, monkeypatch):
    from app.kernel.agents import direct_coder_hooks as hooks

    engine = Engine()
    engine.workspace_root = tmp_path
    profile = engine.store.run
    monkeypatch.delenv("BEAST_DIRECT_CODER_INTEGRATIONS", raising=False)
    assert asyncio.run(hooks.prepare(engine, "agent-test", profile)) == []
    assert engine.events == []

    monkeypatch.setenv("BEAST_DIRECT_CODER_INTEGRATIONS", "1")
    monkeypatch.setattr(hooks, "_prepare_integrations", lambda *_: {
        "repo_map": "a.py contains the target.",
        "events": [
            {"event_type": "agent.integration.fired",
             "payload": {"capability": "compression.reporelay", "status": "fired"}},
            {"event_type": "agent.integration.skipped",
             "payload": {"capability": "kv_transport", "status": "skipped"}},
        ],
    })
    model = ScriptedCodingModel([PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="Done")])
    coder = DirectCoderRuntime(engine, model)
    asyncio.run(coder.run_one_turn("agent-test"))
    saved = engine.store.run["checkpoint"]["direct_coder"]
    assert "a.py contains the target." in coder._prompt(profile, saved)
    assert [event["used_in_prompt"] for _, event in engine.events if "used_in_prompt" in event] == [True, False]


def test_swarm_recovery_accepts_only_matching_bound_file_read(tmp_path):
    from app.kernel.agents.swarm_recovery import _source_evidence

    (tmp_path / "a.py").write_text("VALUE = 1\n")
    observation = {"tool_id": "worktree.read_file", "status": "completed", "result": {
        "path": "a.py", "content": "VALUE = 1", "worktree_root": str(tmp_path / "other"),
    }}
    assert not _source_evidence(tmp_path, [observation], "a.py")
    observation["result"]["worktree_root"] = str(tmp_path)
    assert _source_evidence(tmp_path, [observation], "a.py")


def test_direct_trial_records_bound_failure_before_edit_and_pass_before_completion():
    from app.kernel.compute.coder_crystal_feedback import trial_request

    engine = Engine()
    engine.store.run["request"].update(trial_request("agent", ("a.py", "test_a.py"), enabled=True))
    called, completed = [], []
    stack = SimpleNamespace(
        decision=lambda *_: None,
        budget=SimpleNamespace(start=lambda *_: None, mark_wall=lambda *_: None, record_tool_call=lambda *_, **__: None,
                               record_model_turn=lambda *_, **__: None),
    )

    async def complete(run_id, objective, verified):
        completed.append(verified)

    stack.complete = complete
    async def execute(run_id, tool_id, arguments, **kwargs):
        called.append(tool_id)
        if tool_id == "worktree.bind":
            engine.store.run["checkpoint"]["worktree_root"] = "/isolated/test"
        edited = "worktree.replace_exact" in called
        if tool_id == "worktree.verify":
            assert arguments["command"] == ["python3", "-m", "unittest", "discover", "-p", "test_a.py", "-q"]
            return {"tool_id": tool_id, "arguments": arguments,
                    "status": "completed" if edited else "failed",
                    "result": {"returncode": 0 if edited else 1, "ok": edited,
                               "stderr": "Ran 2 tests\n" + ("OK" if edited else "FAILED (failures=1)")}}
        return {"tool_id": tool_id, "arguments": arguments, "status": "completed", "result": {}}
    engine.execute_tool = execute
    done = PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="Verified")
    model = ScriptedCodingModel([
        tool("worktree.replace_exact", {"path": "a.py"}), done, done,
    ])
    coder = DirectCoderRuntime(engine, model, crystal_stack=stack)

    async def run():
        for _ in range(6):
            await coder.run_one_turn("agent-test")
    asyncio.run(run())
    assert called == ["worktree.bind", "worktree.verify", "workspace.read_range",
                      "worktree.replace_exact", "worktree.verify"]
    assert model.calls == 3 and completed == [True]
    assert engine.store.run["state"] == "completed"
