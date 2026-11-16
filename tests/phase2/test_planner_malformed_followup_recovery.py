"""Fail-closed handling and bounded token budgets after a model-generated edit."""
import asyncio
import subprocess

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_provider import PlannerDecisionError
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


def _run(*observations):
    return {"mode": "agent", "checkpoint": {"planner": {"observations": list(observations)}}}


def test_followup_budget_remains_elevated_after_mutation(monkeypatch):
    monkeypatch.setenv("BEAST_OLLAMA_NUM_PREDICT", "256")
    monkeypatch.delenv("BEAST_OLLAMA_POST_MUTATION_NUM_PREDICT", raising=False)
    provider = OllamaPlannerProvider(model="qwen3:4b", max_retries=1)
    assert provider._decision_num_predict(_run()) == 256
    assert provider._decision_num_predict(_run(
        {"tool_id": "worktree.bind", "status": "completed"},
        {"tool_id": "workspace.read_range", "status": "completed"},
    )) >= 512
    after_edit = _run({"tool_id": "worktree.replace_exact", "status": "completed"})
    assert provider._decision_num_predict(after_edit) >= 768
    assert provider._decision_num_ctx(after_edit) >= 3072
    assert provider._decision_num_predict(_run({"tool_id": "worktree.replace_exact", "status": "failed"})) == 256


def test_malformed_json_retry_gets_more_output_budget(monkeypatch):
    monkeypatch.setenv("BEAST_OLLAMA_NUM_PREDICT", "256")
    monkeypatch.delenv("BEAST_OLLAMA_POST_MUTATION_NUM_PREDICT", raising=False)
    provider = OllamaPlannerProvider(model="qwen3:4b", max_retries=1)
    provider._preflight_ok = True
    monkeypatch.setattr(provider, "_prepare_sensorium", lambda run: None)
    monkeypatch.setattr(provider, "_finish_sensorium", lambda: None)
    monkeypatch.setattr(provider, "_govern_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(provider, "_apply_pressure_budget", lambda **kwargs: None)
    monkeypatch.setattr(provider, "_try_crystal_reuse", lambda *args, **kwargs: None)
    budgets = []

    def fake_request(path, payload, timeout):
        assert path == "/api/generate"
        budgets.append(payload["options"]["num_predict"])
        if len(budgets) == 1:
            return {"response": '{"decision_type":"tool",', "done_reason": "length"}
        return {"response": '{"decision_type":"complete","arguments":{},"summary":"Done"}', "done_reason": "stop"}

    monkeypatch.setattr(provider, "_request_json", fake_request)
    result = asyncio.run(provider.next_decision(
        "Return one decision", run=_run({"tool_id": "worktree.replace_exact", "status": "completed"}), turn=4,
    ))
    assert result.decision_type.value == "complete"
    assert budgets == [768, 1536]
    assert provider.last_usage["attempt"] == 2
    assert provider.last_usage["done_reason"] == "stop"


def test_exhausted_malformed_provider_finishes_run_as_policy_blocked(tmp_path):
    class BadProvider:
        last_usage = {"done_reason": "length", "num_predict": 1536, "attempt": 2}
        async def next_decision(self, prompt, *, run, turn):
            raise PlannerDecisionError("invalid planner JSON")

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    engine = AgentRunEngine(root)
    run = engine.create_run(session_id="malformed-followup", objective="Inspect code", mode="agent")
    result = asyncio.run(AgentPlannerRuntime(engine, BadProvider(), max_turns=2).run(run["run_id"]))
    assert result["state"] == "policy_blocked"
    assert "REFUSE_PLANNER_PROVIDER_DECISION" in result["error"]
    assert engine.store.approvals(run["run_id"]) == []
    assert engine.store.verify_chain(run["run_id"])["ok"] is True
    events = engine.store.events(run["run_id"], limit=100)
    assert any(e["event_type"] == "agent.provider.decision_refused" for e in events)
