import unittest

from app.kernel.compute.coder_crystal_feedback import trial_request, verifier_outcome
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeBuilder, episode_observations


class DirectCrystalEvidenceTests(unittest.TestCase):
    def test_only_canonical_verifier_with_executed_tests_counts(self):
        argv = ["python3", "-m", "unittest", "discover", "-p", "test_plain.py", "-q"]
        step = {"tool_id": "worktree.run", "arguments": {"command": argv},
                "result": {"returncode": 1, "stderr": "Ran 2 tests\nFAILED (failures=1)"}, "status": "failed"}
        self.assertIsNone(verifier_outcome(step, argv))
        step["tool_id"] = "worktree.verify"
        self.assertEqual(verifier_outcome(step, argv), 1)
        step["result"]["stderr"] = "runner exited unexpectedly"
        self.assertIsNone(verifier_outcome(step, argv))

    def test_envelope_uses_durable_direct_tool_events_not_planner_checkpoint(self):
        rows = [{"tool_id": "workspace.read_range", "arguments": {"path": "plain.py"}, "status": "completed"},
                {"tool_id": "worktree.verify", "status": "failed", "result": {"returncode": 1}},
                {"tool_id": "worktree.replace_exact", "arguments": {"path": "plain.py"}, "status": "completed"},
                {"tool_id": "worktree.verify", "status": "completed", "result": {"returncode": 0}}]
        class Store:
            def get_run(self, key):
                return {"run_id": key, "request": {"launch_strategy": "direct_coder"},
                        "checkpoint": {"planner": {"observations": []}}}
            def events(self, key, *, after, limit):
                return [{"event_type": "agent.tool." + row["status"], "payload": {"observation": row}}
                        for row in rows]
        store = Store()
        self.assertEqual(episode_observations(store, "test"), rows)
        sealed = EpisodeEnvelopeBuilder().build(store, "test")
        self.assertTrue(sealed.verification["passed"])
        self.assertEqual(sealed.verification["failures_before_pass"], 1)

    def test_ui_profile_preserves_direct_coder(self):
        scope = trial_request("agent", ("plain.py", "test_plain.py"), enabled=True)
        self.assertEqual(scope["launch_strategy"], "direct_coder")

    def test_native_extractor_accepts_bound_direct_observations(self):
        self._check_native_extraction()

    def test_native_extractor_accepts_proven_equivalent_edit_arguments(self):
        self._check_native_extraction(old_text="BATCH_SIZE = 3\n", new_text="BATCH_SIZE = 5\n")

    def test_native_extractor_refuses_equivalence_without_exact_result_evidence(self):
        for overrides in (
            {"after_sha256": "0" * 64},
            {"before_sha256": "0" * 64},
            {"replacements": 2},
        ):
            with self.subTest(overrides=overrides):
                self._check_native_extraction(old_text="BATCH_SIZE = 3\n", new_text="BATCH_SIZE = 5\n",
                                              overrides=overrides, accepted=False)
        self._check_native_extraction(old_text="BATCH_SIZE = 3\n", new_text="BATCH_SIZE = 5\n# extra\n",
                                      accepted=False)
        self._check_native_extraction(old_text="BATCH_SIZE = 3\nRETRY_LIMIT = 17\n",
                                      new_text="BATCH_SIZE = 5\nRETRY_LIMIT = 18\n",
                                      overrides={"after_sha256": "extra_change"}, accepted=False)

    def _check_native_extraction(self, *, old_text="BATCH_SIZE = 3", new_text="BATCH_SIZE = 5",
                                 overrides=None, accepted=True):
        import hashlib
        import json

        from app.kernel.compute.coding_crystals import CodingCrystalExtractor

        request = trial_request("agent", ("plain.py", "test_plain.py"), enabled=True)
        before = "BATCH_SIZE = 3\nRETRY_LIMIT = 17\n"
        after = "BATCH_SIZE = 5\nRETRY_LIMIT = 17\n"
        def sha(content):
            return hashlib.sha256(content.encode()).hexdigest()

        result = {"path": "plain.py", "before_sha256": sha(before), "after_sha256": sha(after),
                  "replacements": 1, **(overrides or {})}
        if result["after_sha256"] == "extra_change":
            result["after_sha256"] = sha(before.replace(old_text, new_text, 1))
        observations = [
            {"tool_id": "workspace.read_range", "arguments": {"path": "plain.py"}, "status": "completed",
             "result": {"content": before.removesuffix("\n")}},
            {"tool_id": "worktree.verify", "arguments": {}, "status": "failed",
             "result": {"returncode": 1, "stderr": "AssertionError: 3 != 5\n"}},
            {"tool_id": "worktree.replace_exact", "arguments": {"path": "plain.py",
              "old_text": old_text, "new_text": new_text}, "status": "completed",
             "result": result},
            {"tool_id": "worktree.verify", "arguments": {}, "status": "completed", "result": {"returncode": 0}},
        ]
        for obs in observations:
            obs["evidence_digest"] = hashlib.sha256(json.dumps(obs["result"], sort_keys=True).encode()).hexdigest()

        class Store:
            def get_run(self, key):
                return {"run_id": key, "request": request}

            def events(self, key, *, after, limit):
                return [{"event_type": "agent.tool." + obs["status"], "payload": {"observation": obs}}
                        for obs in observations]

        envelope = EpisodeEnvelopeBuilder().build(Store(), "direct-run")
        learned = CodingCrystalExtractor().extract(envelope, observations)
        if accepted:
            self.assertIsNotNone(learned)
            self.assertEqual(learned.source_run_id, "direct-run")
        else:
            self.assertIsNone(learned)
