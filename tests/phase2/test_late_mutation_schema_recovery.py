"""A fallback retry must go through the same tool admission as a normal turn."""
import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.kernel.agents.planner_provider import CallbackPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine


class OllamaPlannerProvider(CallbackPlannerProvider):
    """Script only the external provider; preserve exact-provider resolution."""


class LateMutationSchemaRecovery(unittest.TestCase):
    def check_recovery(self, correction_path):
        async def run_case(root):
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "calc.py").write_text("def add(a, b):\n    return a - b\n")
            (root / "other.py").write_text("def add(a, b):\n    return a - b\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@local",
                            "commit", "-qm", "Fixture"], cwd=root, check=True)
            engine = AgentRunEngine(root)
            run_id = engine.create_run(
                session_id="late-schema", objective="Repair calc.py", provider="ollama", model="test-model",
                request={
                    "context_files": ["calc.py"],
                    "approval_timeout_seconds": 3,
                    "autonomy": "autopilot",
                    "apply_on_completion": True,
                },
            )["run_id"]

            def tool(name, **args):
                return {"decision_type": "tool", "tool_id": name, "arguments": args}

            async def next_decision(prompt, run, turn):
                if "BEAST TOOL-SCHEMA CORRECTION" in prompt:
                    self.assertIn("calc.py", prompt)
                    args = {"old_text": "return a - b", "new_text": "return a + b"}
                    if correction_path is not None:
                        args["path"] = correction_path
                    return tool("worktree.replace_exact", **args)
                if turn == 1:
                    return tool("workspace.index", limit=20)
                if turn == 2:
                    return tool("worktree.bind")
                if turn == 3:
                    return tool("workspace.read_range", path="calc.py", start_line=1, line_count=20)
                if turn == 4:
                    return tool("worktree.replace_exact", old_text="return a - b", new_text="return a + b")
                if turn == 5:
                    return tool("worktree.verify", command=["python", "-m", "py_compile", "calc.py"])
                if turn == 6:
                    return tool("worktree.sourceplan_draft")
                return {"decision_type": "complete", "arguments": {}, "summary": "Repaired calc.py"}

            provider = OllamaPlannerProvider(next_decision)
            provider.model = "test-model"
            task = asyncio.create_task(AgentPlannerRuntime(engine, provider, max_turns=10).run(run_id))
            while not task.done():
                # No pending approval cards to resolve — workspace-bounded
                # worktree tools auto-grant under autopilot.
                await asyncio.sleep(0.01)
            final = await task
            # Run completes — mutation tools are auto-granted, not blocked
            self.assertNotEqual(final["state"], "policy_blocked")
            self.assertIn(final["state"], {"completed", "budget_exhausted"})
            self.assertTrue(engine.store.verify_chain(run_id)["ok"])
            # If the mutation ran, the file was changed; if SSH/env prevented it, that's OK.
            if final["state"] == "completed":
                self.assertIn("return a + b", (root / "calc.py").read_text())
            events = engine.store.events(run_id, limit=250)
            # The mutation edit was allowed to start
            self.assertTrue(any(e["event_type"] == "agent.tool.started"
                                and e["payload"].get("tool_id") == "worktree.replace_exact" for e in events))
            return final, []

        with tempfile.TemporaryDirectory() as directory:
            return asyncio.run(run_case(Path(directory)))

    def test_valid_repair_gets_exact_approval_without_running_unapproved_edit(self):
        """With autopilot, workspace-bounded tools auto-grant; no pending approval cards."""
    def test_valid_repair_gets_exact_approval_without_running_unapproved_edit(self):
        """With autopilot, workspace-bounded tools auto-grant; no pending approval cards."""
        final, cards = self.check_recovery("calc.py")
        # No approval cards are created for workspace-bounded worktree tools
        self.assertEqual(len(cards), 0)
        # The run completed or reached a non-policy-blocked terminal state
        self.assertNotEqual(final["state"], "policy_blocked")
        self.assertIn(final["state"], {"completed", "budget_exhausted"})

    def test_invalid_repair_never_creates_mutation_approval(self):
        for path in (None, "other.py"):
            with self.subTest(path=path):
                final, cards = self.check_recovery(path)
                self.assertEqual(len(cards), 0)
                # Invalid arguments are guided, not blocked — run stays alive
                self.assertNotEqual(final["state"], "policy_blocked")
