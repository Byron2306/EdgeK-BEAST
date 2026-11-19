from __future__ import annotations

import asyncio
import subprocess

from app.kernel.agents.planner_provider import CallbackPlannerProvider, ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


class RecordingCoordinator:
    def __init__(self) -> None:
        self.prepare_calls = 0
        self.complete_calls = 0
        self.advisory_context = [{"capability": "memory", "summary": "bounded advice"}]

    def prepare(self, **_kwargs):
        self.prepare_calls += 1
        return {
            "events": [{
                "event_type": "agent.integration.fired",
                "payload": {
                    "capability": "compression.longcodezip",
                    "status": "fired",
                    "stage": "execution",
                    "operation": "context_compression",
                    "mode": "governed_compression",
                    "reason": "fidelity_passed",
                    "metrics": {"counted_savings_tokens": 4},
                    "artifacts": {},
                    "authority": "advisory_or_existing_gate_only",
                },
            }],
            "source_context": "compressed source",
            "source_files": {"sample.py": "compressed source"},
            "diagnostic_context": "",
            "repo_map": "sample.py: VALUE",
        }

    def complete(self, **_kwargs):
        self.complete_calls += 1
        return {
            "events": [{
                "event_type": "agent.integration.fired",
                "payload": {
                    "capability": "memory_hull.seal",
                    "status": "fired",
                    "stage": "postflight",
                    "operation": "residue_seal",
                    "mode": "sealed_local_residue",
                    "reason": "seal_verified",
                    "metrics": {"verified": True},
                    "artifacts": {},
                    "authority": "advisory_or_existing_gate_only",
                },
            }],
        }


def test_typed_planner_preflight_uses_real_observations_once_and_binds_packet_to_prompt(tmp_path):
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    engine = AgentRunEngine(tmp_path)
    run_id = engine.create_run(
        session_id="integration-preflight",
        objective="inspect sample",
        mode="analysis",
        provider="test",
        model="test",
    )["run_id"]
    prompts: list[str] = []

    async def decide(prompt, _run, turn):
        prompts.append(prompt)
        if turn == 1:
            return {
                "decision_type": "tool",
                "tool_id": "workspace.read_range",
                "arguments": {"path": "sample.py", "start_line": 1, "line_count": 10},
            }
        return {"decision_type": "complete", "summary": "sample.py defines VALUE as 1."}

    coordinator = RecordingCoordinator()
    final = asyncio.run(AgentPlannerRuntime(
        engine,
        CallbackPlannerProvider(decide),
        max_turns=3,
        integration_coordinator=coordinator,
    ).run(run_id))

    assert final["state"] == "completed", final
    assert coordinator.prepare_calls == 1
    assert "CODER INTEGRATIONS:" in prompts[1]
    assert "compressed source" in prompts[1]
    assert final["checkpoint"]["coder_integrations"]["preflight_completed"] is True
    events = engine.store.events(run_id, after=0, limit=200)
    assert any(
        event["event_type"] == "agent.integration.fired"
        and event["payload"]["capability"] == "compression.longcodezip"
        for event in events
    )


def test_verified_typed_planner_completion_runs_integration_postflight_once(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "beast@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=root, check=True)
    (root / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "test_answer.py").write_text(
        "import answer\n\n\ndef test_value():\n    assert answer.VALUE == 2\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "answer.py", "test_answer.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

    engine = AgentRunEngine(root)
    run_id = engine.create_run(
        session_id="integration-postflight",
        objective="Change VALUE to 2 and verify it",
        mode="agent",
        provider="test",
        model="test",
        request={
            "context_files": ["answer.py"],
            "implementation_target": "answer.py",
            "required_test_files": ["test_answer.py"],
        },
    )["run_id"]
    approval_id = "integration-mutation"
    engine.store.create_approval(
        run_id,
        {"request_id": approval_id, "capabilities": [{"id": "worktree_mutation"}]},
    )
    engine.store.resolve_approval(run_id, approval_id, {"approved": True, "scope": "run"})
    provider = ScriptedPlannerProvider([
        {"decision_type": "tool", "tool_id": "workspace.read_range", "arguments": {"path": "answer.py", "start_line": 1, "line_count": 20}},
        {"decision_type": "tool", "tool_id": "worktree.bind", "approval_id": approval_id, "arguments": {"objective": "Change VALUE to 2"}},
        {"decision_type": "tool", "tool_id": "worktree.replace_exact", "approval_id": approval_id, "arguments": {"path": "answer.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}},
        {"decision_type": "tool", "tool_id": "worktree.verify", "approval_id": approval_id, "arguments": {"command": ["python", "-m", "py_compile", "answer.py"]}},
        {"decision_type": "tool", "tool_id": "worktree.sourceplan_draft", "arguments": {}},
    ])
    coordinator = RecordingCoordinator()

    final = asyncio.run(AgentPlannerRuntime(
        engine,
        provider,
        max_turns=5,
        integration_coordinator=coordinator,
    ).run(run_id))

    assert final["state"] == "completed", (final.get("error"), final.get("checkpoint"))
    assert coordinator.complete_calls == 1
    assert final["checkpoint"]["coder_integrations"]["postflight_completed"] is True
    events = engine.store.events(run_id, after=0, limit=300)
    assert any(
        event["event_type"] == "agent.integration.fired"
        and event["payload"]["capability"] == "memory_hull.seal"
        for event in events
    )

