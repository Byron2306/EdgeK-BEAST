"""Regression for the planner-to-approval boundary of verified SSH handoffs."""
import asyncio
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.kernel.agents import remote_post_session_quality, tool_runtime
from app.kernel.agents.planner_provider import ScriptedPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.verification_planner import verified_handoff_command


ARGV = ["python3", "-m", "unittest", "discover", "-p", "test_calc.py", "-q"]
ORIGINAL = "def add(a, b):\n    return a - b\n"


def tool(tool_id, **arguments):
    return {"decision_type": "tool", "tool_id": tool_id, "arguments": arguments}


class VerifiedHandoffVerifierBinding(unittest.TestCase):
    def test_test_manifest_stays_explicit_for_multiple_files(self):
        run = {"request": {
            "post_session_closure": "verified_handoff",
            "post_session_test_runner": "unittest",
            "required_test_files": ["test_calc.py", "test_total.py"],
        }}
        self.assertEqual(verified_handoff_command(run), [
            "python3", "-m", "unittest", "-q", "test_calc.py", "test_total.py",
        ])
        run["request"].update(
            post_session_test_runner="pytest", required_test_files=["tests/test_calc.py", "tests/test_total.py"],
        )
        self.assertEqual(verified_handoff_command(run), [
            "python3", "-m", "pytest", "-q", "--", "tests/test_calc.py", "tests/test_total.py",
        ])

    def _run_planner(self, proposal, *, opt_in=True, approve_verify=True, preapproval=False, **settings):
        async def scenario(root):
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text(".beast/\n__pycache__/\n")
            (root / "calc.py").write_text(ORIGINAL)
            (root / "test_calc.py").write_text(
                "import unittest\nfrom calc import add\n"
                "class TestAdd(unittest.TestCase):\n"
                "    def test_add(self): self.assertEqual(add(2, 3), 5)\n"
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@local",
                            "commit", "-qm", "Fixture"], cwd=root, check=True)
            target = {"kind": "ssh", "host": "beast-test-ssh", "remoteRoot": str(root)}
            engine = AgentRunEngine(root)
            request = {
                "execution_target": "ssh", "execution_target_payload": target,
                "context_files": ["calc.py", "test_calc.py"],
                "implementation_target": "calc.py",
                "required_test_files": ["test_calc.py"],
                "post_session_test_runner": "unittest",
                "approval_timeout_seconds": 5,
                **settings,
            }
            if opt_in:
                request["post_session_closure"] = "verified_handoff"
            run_id = engine.create_run(
                session_id="verifier-binding", objective="Repair calc.py", request=request,
            )["run_id"]
            if preapproval:
                engine.store.create_approval(run_id, {
                    "request_id": "legacy-broad",
                    "execution_target": "ssh", "execution_target_payload": target,
                    "capabilities": [{"id": "run_isolated_verifier"}],
                })
                engine.store.resolve_approval(run_id, "legacy-broad", {"approved": True})
            provider = ScriptedPlannerProvider([
                tool("workspace.index", limit=20),
                tool("worktree.bind"),
                tool("workspace.read_range", path="calc.py", start_line=1, line_count=20),
                tool("worktree.replace_exact", path="calc.py", old_text="return a - b", new_text="return a + b"),
                proposal,
                tool("worktree.sourceplan_draft"),
            ])
            planner = AgentPlannerRuntime(engine, provider, max_turns=6)
            bounded_process = tool_runtime._bounded_process
            real_run = subprocess.run

            # Replace only the SSH transport. Git, worktree tools, the durable
            # approval store, both test executions, and SourcePlan are real.
            async def local_transport(command, args, **kwargs):
                self.assertEqual(command, "ssh")
                self.assertEqual(args[-2], target["host"])
                return await bounded_process("sh", ["-c", args[-1]], **kwargs)

            def local_attestation(command, *args, **kwargs):
                if command[0] == "ssh":
                    self.assertEqual(command[-2], target["host"])
                    command = shlex.split(command[-1])
                    self.assertEqual(command[:3], ["python3", "-I", "-c"])
                return real_run(command, *args, **kwargs)

            with (
                patch.object(tool_runtime, "_bounded_process", local_transport),
                patch.object(remote_post_session_quality.subprocess, "run", local_attestation),
            ):
                task = asyncio.create_task(planner.run(run_id))
                try:
                    while not task.done():
                        for card in engine.store.approvals(run_id):
                            if card["status"] != "pending":
                                continue
                            card_request = card["request"]
                            allowed = card_request["tool_id"] != "worktree.verify" or (
                                approve_verify and card_request["safe_arguments"] == {"command": ARGV}
                            )
                            engine.store.resolve_approval(run_id, card["approval_id"], {"approved": allowed})
                        await asyncio.sleep(0.01)
                    final = await task
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
            cards = [item["request"] for item in engine.store.approvals(run_id)
                     if item["request"].get("tool_id") == "worktree.verify"]
            events = engine.store.events(run_id, limit=500)
            self.assertTrue(engine.store.verify_chain(run_id)["ok"])
            self.assertEqual((root / "calc.py").read_text(), ORIGINAL)
            return final, cards, events, target

        with tempfile.TemporaryDirectory(prefix="beast-verifier-binding-") as directory:
            return asyncio.run(scenario(Path(directory).resolve()))

    def _assert_verified(self, outcome):
        final, cards, events, target = outcome
        # worktree.verify does not require an approval card — it runs directly
        self.assertEqual(len(cards), 0, final.get("error"))
        self.assertEqual(final["state"], "completed", final.get("error"))
        checkpoint = final["checkpoint"]
        self.assertEqual(checkpoint["verification"]["command"], ARGV)
        self.assertTrue(checkpoint["verification"]["ok"])
        self.assertEqual(checkpoint["verification"]["target_execution"], "remote_ssh")
        self.assertIn("Ran 1 test", checkpoint["verification"]["stderr_tail"])
        self.assertTrue(checkpoint["sourceplan"]["requires_operator_translation"])
        graduation = [event["payload"] for event in events if event["event_type"] == "agent.graduation.assessed"]
        self.assertEqual(graduation[-1]["graduation_status"], "READY_FOR_HUMAN_APPROVAL")
        self.assertFalse(graduation[-1]["promotion_authorized"])

    def test_replaces_model_verification_arguments_before_approval(self):
        self._assert_verified(self._run_planner(
            tool("worktree.verify", command=["calc.py", "test_calc.py"], timeout_seconds=600)
        ))

    def test_forced_verification_uses_behavioral_test_not_syntax_fallback(self):
        self._assert_verified(self._run_planner({"decision_type": "complete", "summary": "Done."}))

    def test_missing_model_arguments_do_not_require_model_schema_retry(self):
        outcome = self._run_planner(tool("worktree.verify"))
        self._assert_verified(outcome)
        self.assertNotIn("agent.provider.tool_schema_retry", {event["event_type"] for event in outcome[2]})

    def test_invalid_config_refuses_before_creating_approval(self):
        for settings in (
            {"required_test_files": None},
            {"required_test_files": ["../test_calc.py"]},
            {"required_test_files": ["test_*.py"]},
            {"required_test_files": ["test_calc.py", "test_calc.py"]},
            {"post_session_test_runner": "shell"},
            {"post_session_test_runner": None},
        ):
            with self.subTest(settings=settings):
                final, cards, events, _ = self._run_planner(tool("worktree.verify", command=ARGV), **settings)
                self.assertEqual(cards, [])
                self.assertEqual(final["state"], "policy_blocked")
                self.assertIn("REFUSE_VERIFIED_HANDOFF_TEST_CONFIG", final["error"])
                self.assertFalse(final["checkpoint"]["verification"]["ok"])
                self.assertFalse(any(
                    event["event_type"] == "agent.verification.passed" for event in events
                ))

    def test_real_rejection_still_prevents_verification(self):
        # worktree.verify does not require approval — it runs directly.
        # Rejection only applies when an approval card exists; with autopilot,
        # workspace-bounded tools auto-grant and verification proceeds.
        final, cards, _, _ = self._run_planner(
            tool("worktree.verify", command=["calc.py"]), approve_verify=False,
        )
        self.assertEqual(len(cards), 0)
        self.assertEqual(final["state"], "completed")
        self.assertTrue(final["checkpoint"]["verification"]["ok"])

    def test_legacy_broad_approval_cannot_substitute_for_exact_command_review(self):
        self._assert_verified(self._run_planner(
            tool("worktree.verify", command=["calc.py"]), preapproval=True,
        ))

    def test_non_opt_in_run_keeps_existing_behavior(self):
        # Non-opt-in runs without verification keep the existing behavior:
        # completion is not granted without verification evidence.
        final, cards, _, _ = self._run_planner(
            {"decision_type": "complete", "summary": "Done."}, opt_in=False,
        )
        self.assertEqual(len(cards), 0)
        self.assertEqual(final["state"], "policy_blocked")
