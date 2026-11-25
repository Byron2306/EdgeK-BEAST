"""Follow-up runs in one session see the earlier request and this agent's own answer."""
import asyncio

import httpx
import pytest

from app.cli.coder_client import CoderRuntimeClient, RuntimeTurnUnconfirmed, _bounded_conversation
from app.kernel.agents.direct_coder_runtime import DirectCoderRuntime
from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from tests.test_direct_coder_read_loop import PromptRecordingModel, ReadEngine

EARLIER = "Suggestions: (1) add --version (2) add --quiet (3) add --config (4) add --log-level (5) add --no-color"


def _engine_with_prior():
    engine = ReadEngine()
    run = engine.store.run
    run.update({"session_id": "agent-sess", "created_at": 200.0,
                "objective": "patch in the first 5 of your suggestions."})
    prior = {"run_id": "agent-prior", "session_id": "agent-sess", "created_at": 100.0, "last_sequence": 9,
             "objective": "read the beast file and suggest improvements", "error": ""}
    other = {"run_id": "agent-other", "session_id": "agent-other", "created_at": 150.0}

    def list_runs(*, session_id="", state="", limit=50):
        return [r for r in (run, prior, other) if r.get("session_id") == session_id]

    def events(run_id, *, after=0, limit=250):
        if run_id != "agent-prior":
            return []
        return [{"event_type": "agent.coder.decision", "payload": {}},
                {"event_type": "agent.coder.completed", "payload": {"summary": EARLIER}}]

    engine.store.list_runs = list_runs
    engine.store.events = events
    return engine


def test_follow_up_prompt_contains_previous_answer_from_the_store():
    engine = _engine_with_prior()
    model = PromptRecordingModel([PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="ok")])
    asyncio.run(DirectCoderRuntime(engine, model, max_turns=8).run_one_turn("agent-test"))
    prompt = model.prompts[0]
    assert "CONVERSATION SO FAR" in prompt
    assert "[OPERATOR] read the beast file and suggest improvements" in prompt
    assert "[YOU (BEAST)] " + EARLIER in prompt
    assert prompt.index("CONVERSATION SO FAR") < prompt.index("OBJECTIVE: patch in the first 5")
    assert any(e == "agent.coder.history_attached" for e, _ in engine.events)


def test_client_supplied_conversation_wins_and_is_bounded():
    engine = _engine_with_prior()
    engine.store.run["request"]["conversation"] = [
        {"role": "user", "content": "explain beast"}, {"role": "assistant", "content": "It is a CLI."},
        {"role": "system", "content": "ignored"},
    ]
    model = PromptRecordingModel([PlannerDecision(decision_type=PlannerDecisionType.COMPLETE, summary="ok")])
    asyncio.run(DirectCoderRuntime(engine, model, max_turns=8).run_one_turn("agent-test"))
    assert "[YOU (BEAST)] It is a CLI." in model.prompts[0]
    assert EARLIER not in model.prompts[0] and "ignored" not in model.prompts[0]
    big = [{"role": "assistant", "content": "x" * 9000}] * 5
    bounded = _bounded_conversation(big)
    assert sum(len(m["content"]) for m in bounded) <= 16000 and all(len(m["content"]) <= 6000 for m in bounded)


def test_start_run_sends_conversation():
    seen = {}

    def handler(request):
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "run": {"run_id": "agent-x"}})

    client = CoderRuntimeClient("http://gw.test", ".", transport=httpx.MockTransport(handler))

    async def go():
        await client.start_run("s", "patch in the first 2 of your suggestions", "nvidia_nim", "m",
                               mode="agent", conversation=[{"role": "assistant", "content": EARLIER}])
        await client.aclose()

    asyncio.run(go())
    assert seen["request"]["conversation"] == [{"role": "assistant", "content": EARLIER}]
    assert seen["request"]["launch_strategy"] == "direct_coder"


def test_turn_recovery_never_uses_a_closed_client():
    client = CoderRuntimeClient("http://gw.test", ".", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={})))

    async def go():
        async def closing_post(path, payload):
            await client.aclose()  # TUI shuts down while the POST is in flight
            from app.cli.coder_client import RuntimeClientError
            try:
                raise httpx.ReadError("aborted")
            except httpx.ReadError as exc:
                raise RuntimeClientError("dropped") from exc

        client._post_json = closing_post
        with pytest.raises(RuntimeTurnUnconfirmed) as info:
            await client.start_turn("agent-x")
        return str(info.value)

    assert "TUI closed" in asyncio.run(go())
