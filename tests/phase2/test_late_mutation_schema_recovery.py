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
                request={"context_files": ["calc.py"], "approval_timeout_seconds": 3},
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
                if provider.last_route.get("route_kind") == "callback":
                    provider.last_route = {"route_kind": "fallback"}
                    return {"decision_type": "blocked", "blocker": "No mutation from fallback."}
                return tool("worktree.replace_exact", old_text="return a - b", new_text="return a + b")

            provider = OllamaPlannerProvider(next_decision)
            provider.model = "test-model"
            task = asyncio.create_task(AgentPlannerRuntime(engine, provider, max_turns=4).run(run_id))
            while not task.done():
                for card in engine.store.approvals(run_id):
                    if card["status"] == "pending":
                        engine.store.resolve_approval(run_id, card["approval_id"],
                                                      {"approved": card["request"]["tool_id"] == "worktree.bind"})
                await asyncio.sleep(0.01)
            final = await task
            self.assertEqual(final["state"], "policy_blocked")
            self.assertTrue(engine.store.verify_chain(run_id)["ok"])
            self.assertIn("return a - b", (root / "calc.py").read_text())
            events = engine.store.events(run_id, limit=250)
            self.assertEqual(sum(e["event_type"] == "agent.provider.tool_schema_retry" for e in events), 1)
            self.assertFalse(any(e["event_type"] == "agent.tool.started"
                                 and e["payload"].get("tool_id") == "worktree.replace_exact" for e in events))
            return final, [a for a in engine.store.approvals(run_id)
                           if a["request"]["tool_id"] == "worktree.replace_exact"]

        with tempfile.TemporaryDirectory() as directory:
            return asyncio.run(run_case(Path(directory)))

    def test_valid_repair_gets_exact_approval_without_running_unapproved_edit(self):
        _, cards = self.check_recovery("calc.py")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["request"]["safe_arguments"], {
            "path": "calc.py", "old_text": "return a - b", "new_text": "return a + b",
        })
        self.assertEqual(cards[0]["status"], "rejected")

    def test_invalid_repair_never_creates_mutation_approval(self):
        for path in (None, "other.py"):
            with self.subTest(path=path):
                final, cards = self.check_recovery(path)
                self.assertEqual(cards, [])
                self.assertIn("REFUSE_INVALID_TOOL_ARGUMENTS", final["error"])
