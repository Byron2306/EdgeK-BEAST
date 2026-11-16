"""Read-only planner runs deliver findings without graduating a patch."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from app.kernel.agents.planner_provider import CallbackPlannerProvider, ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine

PATH = "app/adapters/openai_adapter.py"
SOURCE = "def status():\n    return 404\n"
FINDINGS = f"{PATH}:2 returns 404 unconditionally."


class ReadOnlyPlannerCompletion(unittest.TestCase):
    def run_review(self, mode, provider, *, files=(), exists=True):
        async def execute(root):
            if exists:
                source = root / PATH
                source.parent.mkdir(parents=True)
                source.write_text(SOURCE)
            engine = AgentRunEngine(root)
            run_id = engine.create_run(
                session_id="review", mode=mode, objective="Explain the adapter",
                request={"context_files": list(files), "approval_timeout_seconds": 0.02},
            )["run_id"]
            final = await AgentPlannerRuntime(engine, provider, max_turns=4).run(run_id)
            events = engine.store.events(run_id, limit=250)
            self.assertTrue(engine.store.verify_chain(run_id)["ok"])
            self.assertFalse(engine.store.approvals(run_id))
            self.assertNotIn("worktree_root", final["checkpoint"])
            if exists:
                self.assertEqual(source.read_text(), SOURCE)
            return final, events, engine

        with tempfile.TemporaryDirectory() as directory:
            return asyncio.run(execute(Path(directory)))

    def test_attached_file_is_read_before_advisory_completion(self):
        async def complete(prompt, run, turn):
            return {"decision_type": "complete", "summary": FINDINGS if "return 404" in prompt else "Inspected files."}

        final, events, engine = self.run_review("analysis", CallbackPlannerProvider(complete), files=[PATH])
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertEqual(final["checkpoint"]["planner"]["final_summary"], FINDINGS)
        self.assertEqual([e["payload"]["observation"]["result"]["path"] for e in events
                          if e["event_type"] == "agent.tool.completed"], [PATH])
        types = {e["event_type"] for e in events}
        self.assertFalse(types & {"agent.post_session.quality", "agent.graduation.assessed", "agent.sourceplan.ready"})
        advisory = next(e for e in events if e["event_type"] == "agent.run.advisory")
        self.assertIn("event: agent_run_advisory", engine.sse_event(advisory, projection="legacy"))
        self.assertEqual(advisory["payload"]["text"], FINDINGS)

    def test_missing_attachment_cannot_be_reported_as_reviewed(self):
        provider = ScriptedPlannerProvider([{"decision_type": "complete", "summary": FINDINGS}] * 2)
        final, events, _ = self.run_review("analysis", provider, files=[PATH], exists=False)
        self.assertEqual(final["state"], "policy_blocked")
        self.assertIn(PATH, final["error"])
        self.assertNotIn("agent.run.advisory", {e["event_type"] for e in events})
        self.assertEqual(sum(e["event_type"] == "agent.tool.failed" for e in events), 1)

    def test_chat_and_ask_can_answer_without_a_worktree_or_attachments(self):
        for mode in ("chat", "ask"):
            with self.subTest(mode=mode):
                provider = ScriptedPlannerProvider([{"decision_type": "complete", "summary": "An adapter translates between interfaces."}])
                final, events, _ = self.run_review(mode, provider)
                self.assertEqual(final["state"], "completed", final["error"])
                self.assertNotIn("agent.graduation.assessed", {e["event_type"] for e in events})

    def test_analysis_cannot_request_worktree_binding(self):
        provider = ScriptedPlannerProvider([{"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {}}])
        final, events, _ = self.run_review("analysis", provider, files=[PATH])
        self.assertEqual(final["state"], "policy_blocked")
        self.assertIn("REFUSE_READ_ONLY_TOOL", final["error"])
        self.assertNotIn("agent.tool.started", {e["event_type"] for e in events})
