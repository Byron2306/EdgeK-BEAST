import tempfile
import unittest
from pathlib import Path

from app.kernel.compute.coding_crystals import CodingCrystalRegistry
from app.kernel.compute.coder_crystal_feedback import trial_request, scope_digest


class CoderCrystalFeedbackTests(unittest.TestCase):
    def test_trial_scope_requires_explicit_unittest_attachment(self):
        self.assertEqual(trial_request("agent", ("service.py",), enabled=True), {})
        self.assertEqual(trial_request("review", ("service.py", "test_service.py"), enabled=True), {})
        self.assertEqual(trial_request("agent", ("service.py", "test_service.py"), enabled=False), {})
        self.assertEqual(trial_request("agent", ("service.py", "test_service.py"), enabled=True)["launch_strategy"],
                         "direct_coder")

    def test_negative_is_durable_and_applies_only_to_exact_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = trial_request("agent", ("service.py", "test_service.py"), enabled=True)
            run = {"request": request, "objective": "Repair the visible contract."}
            (root / "service.py").write_text("PAGE = 3\n")
            test = root / "test_service.py"
            test.write_text("assert PAGE == 5\n")
            a = scope_digest(root, run)
            self.assertTrue(a.startswith("sha256:"))
            db = root / "crystals.sqlite3"
            registry = CodingCrystalRegistry(db)
            receipt = registry.record_scoped_refusal("candidate", a, "run-first")
            self.assertEqual(CodingCrystalRegistry(db).scoped_refusal("candidate", a)["receipt_digest"],
                             receipt["receipt_digest"])
            test.write_text("assert PAGE == 7\n")
            b = scope_digest(root, run)
            self.assertNotEqual(a, b)
            self.assertIsNone(registry.scoped_refusal("candidate", b))
            self.assertIsNone(registry.scoped_refusal("other-candidate", a))


class FeedbackLoopTests(unittest.TestCase):
    def test_prior_negative_skips_activation_but_preserves_good_context(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.cli.coder_client import RuntimeEvent
        from app.cli.coder_state import project_runtime_event
        from app.kernel.compute.coding_crystals import (
            CRYSTAL_PARAMETERS, RECIPE_FIX_FAILING_ASSERTION, CodingCrystalCandidate, CodingCrystalPlanner,
            CodingCrystalSession, coding_catalog_digest,
        )
        from app.kernel.compute.heldout_replay import ReplayReceipt

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = trial_request("agent", ("service.py", "test_service.py"), enabled=True)
            run = {"request": request}
            (root / "service.py").write_text("PAGE = 3\nOTHER = 3\n")
            (root / "test_service.py").write_text("# Trial contract\n")
            candidate = CodingCrystalCandidate(
                "", request["task_family"], RECIPE_FIX_FAILING_ASSERTION, CRYSTAL_PARAMETERS,
                coding_catalog_digest(), "source", "sha256:" + "1" * 64,
            ).sealed()
            registry = CodingCrystalRegistry(root / "registry.sqlite3")
            registry.add_candidate(candidate)
            registry.promote(candidate.crystal_id, ReplayReceipt(candidate.crystal_id, 3, 3, True, "fixture"))
            events = []
            engine = SimpleNamespace(workspace_root=root,
                                     emit=lambda rid, kind, payload: events.append((rid, kind, payload)))
            ledger = SimpleNamespace(consume=lambda *args, **kwargs: self.fail("must not consume a capability"))
            planner = CodingCrystalPlanner(registry, object(), ledger, scoped_negatives=True)
            session = CodingCrystalSession(candidate, {}, planner=planner, engine=engine, run_id="failed-once",
                                           capability={}, negative_scope=scope_digest(root, run))
            self.assertLess(session.cursor, 4)
            planner.on_resolver_refused(session, run)
            self.assertEqual(events[-1][1], "agent.crystal.negative_recorded")
            with patch.object(planner, "_applicability", return_value=("", {})):
                self.assertIsNone(planner.activate(run, "next-run", engine=engine))
            rid, kind, payload = events[-1]
            self.assertEqual((rid, kind, payload["source_run_id"]),
                             ("next-run", "agent.crystal.negative_applied", "failed-once"))
            rendered = project_runtime_event(RuntimeEvent(kind, {"payload": payload}))
            self.assertEqual(rendered.kind, "integration")
            self.assertFalse(rendered.executed)
            self.assertIn("blocked activation", rendered.text)
            (root / "service.py").write_text("PAGE = 3\nOTHER = 17\n")
            self.assertIsNone(registry.scoped_refusal(candidate.crystal_id, scope_digest(root, run)))
            self.assertEqual(registry.get(candidate.crystal_id)["status"], "promoted")


class UIRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_coder_client_can_select_trial_without_changing_default(self):
        import json
        from unittest.mock import patch

        import httpx
        from app.cli.coder_client import CoderRuntimeClient

        requests = []
        def receive(request):
            requests.append(json.loads(request.content)["request"])
            return httpx.Response(200, json={"ok": True, "run": {"run_id": "test"}})
        client = CoderRuntimeClient("http://127.0.0.1:18100", ".", transport=httpx.MockTransport(receive))
        try:
            for enabled in ("0", "1"):
                with patch.dict("os.environ", {"BEAST_CODER_CRYSTAL_TRIAL": enabled}):
                    await client.start_run("session", "Fix service.py to pass test_service.py", "local", "test",
                                           mode="agent", context_files=("service.py", "test_service.py"))
        finally:
            await client.aclose()
        self.assertEqual(requests[0]["launch_strategy"], "direct_coder")
        self.assertNotIn("crystal_trial_profile", requests[0])
        self.assertEqual(requests[1]["launch_strategy"], "direct_coder")
        self.assertEqual(requests[1]["post_session_closure"], "verified_handoff")
        self.assertFalse(requests[1]["apply_on_completion"])
