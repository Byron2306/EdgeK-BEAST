"""Direct Coder must not loop on reads: it keeps what it read, skips repeats,
and saves turns to write the answer (regression for run agent-a615d0b5-733d39d70329,
which spent all 32 turns cycling list -> read 1 -> read 200 -> read 400)."""
import asyncio

from app.cli.coder_client import RuntimeEvent
from app.cli.coder_state import project_runtime_event
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from tests.test_direct_coder_runtime import Engine, tool

TOTAL = 600


class ReadEngine(Engine):
    def __init__(self):
        super().__init__()
        self.store.run["objective"] = "read the beast file, suggest improvements and patch them"
        self.store.run["request"]["context_files"] = ["beast"]

    def list_tools(self):
        return [{"tool_id": t, "description": "t", "input_schema": {}}
                for t in ("workspace.list", "workspace.read_range")]

    async def execute_tool(self, run_id, tool_id, arguments, *, execution_target="local", approval_id=""):
        self.calls.append((tool_id, dict(arguments)))
        if tool_id == "workspace.list":
            return {"tool_id": tool_id, "status": "completed",
                    "result": {"entries": [{"path": "beast", "kind": "file"}], "count": 1}}
        start = int(arguments.get("start_line") or 1)
        end = min(TOTAL, start + int(arguments.get("line_count") or 200) - 1)
        content = "\n".join(f"line {n} MARK{n}" for n in range(start, end + 1))
        return {"tool_id": tool_id, "status": "completed",
                "result": {"path": "beast", "start_line": start, "end_line": end,
                           "total_lines": TOTAL, "sha256": "abc", "content": content}}


class PromptRecordingModel:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.prompts = []

    async def next_decision(self, prompt, *, run, turn):
        assert "DIRECT CODING AGENT" in prompt
        self.prompts.append(prompt)
        return self.decisions.pop(0) if self.decisions else tool("workspace.read_range", {"path": "beast", "start_line": 1})


def read(start):
    return tool("workspace.read_range", {"path": "beast", "start_line": start, "line_count": 200,
                                         "include_outline": True})


ANSWER = ("Findings: beast:12 swallows errors.\n"
          "--- a/beast\n+++ b/beast\n@@ -12 +12 @@\n-except Exception: pass\n+except OSError as exc: log(exc)\n")


def test_reads_kept_in_memory_repeats_skipped_then_written_answer():
    engine = ReadEngine()
    model = PromptRecordingModel([
        tool("workspace.list", {"path": ".", "limit": 50}), read(1), read(200), read(400),
        tool("workspace.list", {"path": ".", "limit": 50}), read(1),
        PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=ANSWER),
    ])
    coder = DirectCoderRuntime(engine, model, max_turns=32)

    async def go():
        snap = None
        for _ in range(7):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] == "completed":
                break
        return snap

    snap = asyncio.run(go())
    assert snap["state"] == "completed"
    executed = [c for c in engine.calls]
    assert [c[0] for c in executed].count("workspace.list") == 1
    assert sum(1 for c in executed if c[0] == "workspace.read_range" and c[1]["start_line"] == 1) == 1
    names = [e for e, _ in engine.events]
    assert names.count("agent.coder.duplicate_read_skipped") == 2
    assert "agent.coder.finishing" in names
    completed = [p for e, p in engine.events if e == "agent.coder.completed"]
    assert "+++ b/beast" in completed[0]["summary"]
    final_prompt = model.prompts[-1]
    # All three ranges stay verbatim in the prompt (the old renderer kept only the tail).
    for marker in ("MARK1\n", "MARK250", "MARK599"):
        assert marker in final_prompt
    assert "FINISH NOW" in final_prompt
    assert '"unread_lines": []' in final_prompt or "600" in final_prompt


def test_stubborn_reader_is_forced_to_finish_with_report_within_budget():
    engine = ReadEngine()
    starts = iter([1, 201, 401, 1, 201, 401, 1, 201, 401, 1])
    model = PromptRecordingModel([read(next(starts)) for _ in range(10)])
    coder = DirectCoderRuntime(engine, model, max_turns=6)

    async def go():
        snap = None
        for _ in range(8):
            snap = await coder.run_one_turn("agent-test")
            if snap["state"] in {"completed", "budget_exhausted"}:
                break
        return snap

    snap = asyncio.run(go())
    assert snap["state"] == "budget_exhausted"
    reads = [c[1]["start_line"] for c in engine.calls if c[0] == "workspace.read_range"]
    assert sorted(reads) == [1, 201, 401]  # each range executed once
    reports = [p for e, p in engine.events if e == "agent.coder.final_report"]
    assert len(reports) == 1
    assert "1-600 of 600" in reports[0]["summary"]
    # The last turn asked the model for its answer a second time instead of reading.
    assert "final turn, answer now" in model.prompts[-1]


def test_changed_file_resets_coverage():
    state = {}
    DirectCoderRuntime._remember(state, "workspace.read_range", {"path": "beast", "start_line": 1},
                                 {"status": "completed", "result": {"path": "beast", "start_line": 1,
                                  "end_line": 200, "total_lines": 600, "sha256": "a", "content": "x"}})
    # Reads default to 2000 lines since 887334c6: ask for the same 200-line window explicitly.
    first = {"path": "beast", "start_line": 1, "line_count": 200}
    assert DirectCoderRuntime._duplicate_reason(state, "workspace.read_range", first)
    DirectCoderRuntime._remember(state, "workspace.read_range", {"path": "beast", "start_line": 300},
                                 {"status": "completed", "result": {"path": "beast", "start_line": 300,
                                  "end_line": 400, "total_lines": 600, "sha256": "b", "content": "y"}})
    assert not DirectCoderRuntime._duplicate_reason(state, "workspace.read_range", first)


def test_tli_shows_final_report_and_skips():
    report = project_runtime_event(RuntimeEvent(
        "agent.coder.final_report", {"sequence": 9, "payload": {"summary": "Read beast: lines 1-600"}}, "9"))
    assert report.kind == "advisory" and "1-600" in report.text
    skip = project_runtime_event(RuntimeEvent(
        "agent.coder.duplicate_read_skipped", {"sequence": 3, "payload": {"reason": "already read"}}, "3"))
    assert "already read" in skip.text


class ThinkingOverflowModel:
    """First call: reasoning ate the budget and content was empty."""

    def __init__(self):
        self.enable_thinking = True
        self.seen = []

    async def next_decision(self, prompt, *, run, turn):
        self.seen.append(self.enable_thinking)
        if self.enable_thinking:
            from app.kernel.agents.planner_provider import PlannerDecisionError
            raise PlannerDecisionError("planner response did not contain a JSON object")
        return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=ANSWER)


def test_thinking_overflow_retries_once_without_thinking_instead_of_pausing():
    engine = ReadEngine()
    model = ThinkingOverflowModel()
    coder = DirectCoderRuntime(engine, model, max_turns=8)
    snap = asyncio.run(coder.run_one_turn("agent-test"))
    assert snap["state"] == "completed"
    assert model.seen == [True, False]
    assert model.enable_thinking is True  # restored for later turns
    assert any(e == "agent.coder.thinking_overflow_retry" for e, _ in engine.events)


def test_full_coverage_tells_model_to_stop_reading():
    engine = ReadEngine()
    model = PromptRecordingModel([read(1), read(201), read(401),
                                  PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=ANSWER)])
    coder = DirectCoderRuntime(engine, model, max_turns=32)

    async def go():
        for _ in range(4):
            await coder.run_one_turn("agent-test")

    asyncio.run(go())
    assert "ALL EXPLICIT FILES ARE FULLY READ" in model.prompts[-1]
    assert "ALL EXPLICIT FILES ARE FULLY READ" not in model.prompts[-2]


class TruncatingModel:
    """Finishing answer is cut off at the default budget, fits at the bigger one."""

    def __init__(self):
        self.enable_thinking = True
        self.max_tokens_override = 0
        self.seen = []

    async def next_decision(self, prompt, *, run, turn):
        self.seen.append((self.enable_thinking, self.max_tokens_override))
        if self.max_tokens_override < 8000:
            from app.kernel.agents.planner_provider import PlannerDecisionError
            raise PlannerDecisionError("invalid planner JSON: Unterminated string")
        return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=ANSWER)


def test_finishing_answer_gets_bigger_output_budget_and_one_retry():
    engine = ReadEngine()
    model = TruncatingModel()
    coder = DirectCoderRuntime(engine, model, max_turns=2)  # first turn is already a finishing turn
    snap = asyncio.run(coder.run_one_turn("agent-test"))
    assert snap["state"] == "completed"
    assert model.seen == [(False, 6144), (False, 12288)]
    assert (model.enable_thinking, model.max_tokens_override) == (True, 0)


def test_worktree_reads_share_coverage_and_reset_after_an_edit():
    state = {}
    res = {"status": "completed", "result": {"path": "beast", "start_line": 1, "end_line": 200,
                                             "total_lines": 600, "sha256": "a", "content": "x"}}
    DirectCoderRuntime._remember(state, "workspace.read_range", {"path": "beast", "start_line": 1}, res)
    assert DirectCoderRuntime._duplicate_reason(state, "worktree.read_file", {"path": "beast", "line_count": 120})
    DirectCoderRuntime._remember(state, "worktree.list", {"path": ".", "limit": 50},
                                 {"status": "completed", "result": {"entries": []}})
    assert DirectCoderRuntime._duplicate_reason(state, "worktree.list", {"path": ".", "limit": 50})


def test_thinking_stays_off_after_first_overflow():
    engine = ReadEngine()
    model = ThinkingOverflowModel()
    model_decisions = [read(1), PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary=ANSWER)]

    async def next_decision(prompt, *, run, turn):
        model.seen.append(model.enable_thinking)
        if model.enable_thinking:
            from app.kernel.agents.planner_provider import PlannerDecisionError
            raise PlannerDecisionError("planner response did not contain a JSON object")
        return model_decisions.pop(0)

    model.next_decision = next_decision
    coder = DirectCoderRuntime(engine, model, max_turns=8)

    async def go():
        await coder.run_one_turn("agent-test")
        return await coder.run_one_turn("agent-test")

    assert asyncio.run(go())["state"] == "completed"
    assert model.seen == [True, False, False]  # one overflow, then thinking stays off
    assert model.enable_thinking is True


def test_evicted_range_may_be_reread_once_then_is_a_loop():
    state = {"reads": {"beast": {"ranges": [[1, 200]], "total_lines": 600, "sha256": "a"}}, "file_memory": []}
    args = {"path": "beast", "start_line": 1, "line_count": 200}
    assert DirectCoderRuntime._duplicate_reason(state, "worktree.read_file", args) == ""
    assert DirectCoderRuntime._duplicate_reason(state, "worktree.read_file", args)


def test_rebind_is_refused_and_worktree_target_is_normalised():
    engine = ReadEngine()
    engine.store.run["checkpoint"]["worktree_root"] = "/tmp/wt-1"
    model = PromptRecordingModel([
        tool("worktree.bind", {"objective": "again"}),
        PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id="worktree.read_file",
                        arguments={"path": "beast", "start_line": 1}, execution_target="isolated_worktree"),
    ])
    targets = []
    original = engine.execute_tool

    async def execute_tool(run_id, tool_id, arguments, *, execution_target="local", approval_id=""):
        targets.append((tool_id, execution_target))
        return await original(run_id, tool_id, arguments, execution_target=execution_target,
                              approval_id=approval_id)

    engine.execute_tool = execute_tool
    from tests.test_direct_coder_runtime import Spec
    engine.tool_registry.get = lambda name: Spec(name, requires_approval=name == "worktree.bind")
    coder = DirectCoderRuntime(engine, model, max_turns=8)

    async def go():
        await coder.run_one_turn("agent-test")
        await coder.run_one_turn("agent-test")

    asyncio.run(go())
    assert ("worktree.bind", "local") not in targets
    # The refused re-bind is folded (no turn spent), so the second turn is a fresh decision.
    assert targets[0] == ("worktree.read_file", "local")
    skips = [p for e, p in engine.events if e == "agent.coder.duplicate_read_skipped"]
    assert "already bound" in skips[0]["reason"]
