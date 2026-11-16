"""Regression for the local IDE review that read 80 of 85 lines and returned a status."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.kernel.agents import file_review
from app.kernel.agents.planner_provider import CallbackPlannerProvider, PlannerDecisionError
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.run_engine import AgentRunEngine

PATH = "app/adapters/gemini_adapter.py"
STATUS = {"decision_type": "complete", "summary": "Code review complete"}
FINDING = {
    "path": PATH, "line": 85, "evidence": "return 500", "observed": "Returns 500 for every request.",
    "impact": "Successful requests are reported as server errors.",
}
CHECKED = {"path": PATH, "line": 85, "evidence": "return 500", "detail": "Checked how the adapter returns its HTTP status."}


class FileReviewContract(unittest.TestCase):
    def review(self, replies, *, long_source=False, request=None, native=False, source_override=None):
        async def run(root):
            path = root / PATH
            path.parent.mkdir(parents=True)
            comment = "# " + "x" * (100 if long_source else 8)
            source = source_override if source_override is not None else "\n".join([comment] * 84 + ["return 500"]) + "\n"
            path.write_text(source)
            prompts = []

            async def respond(prompt, run, turn):
                if "FILE REVIEW RESULT" not in prompt:
                    return STATUS
                prompts.append(prompt)
                result = replies[min(len(prompts) - 1, len(replies) - 1)]
                if isinstance(result, Exception):
                    raise result
                return result

            engine = AgentRunEngine(root)
            run_id = engine.create_run(
                session_id="desktop-review", objective=f"Review {PATH} for inconsistencies.",
                mode="analysis", provider="ollama", model="granite3.3:2b",
                request={"context_files": [PATH], **(request or {})},
            )["run_id"]
            provider = CallbackPlannerProvider(respond)
            provider.supports_native_file_review = native
            final = await AgentPlannerRuntime(engine, provider, max_turns=4).run(run_id)
            events = engine.store.events(run_id)
            self.assertEqual(path.read_text(), source)
            self.assertEqual(engine.store.approvals(run_id), [])
            self.assertNotIn("worktree_root", final["checkpoint"])
            self.assertTrue(engine.store.verify_chain(run_id)["ok"])
            self.assertFalse({"agent.graduation.assessed", "agent.sourceplan.ready"} & {e["event_type"] for e in events})
            return final, events, prompts, engine

        with tempfile.TemporaryDirectory() as directory:
            return asyncio.run(run(Path(directory)))

    def test_status_only_answer_is_retried_against_full_85_lines(self):
        result = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [FINDING]}}
        final, events, prompts, _ = self.review([STATUS, result])
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertEqual(len(prompts), 2)
        self.assertIn("85 | return 500", prompts[0])
        self.assertIn("85 | return 500", prompts[1])
        self.assertIn("previous", prompts[1].lower())
        self.assertEqual([(r["start_line"], r["end_line"]) for r in (
            e["payload"]["observation"]["result"] for e in events if e["event_type"] == "agent.tool.completed"
        )], [(1, 80), (81, 85)])
        summary = final["checkpoint"]["planner"]["final_summary"]
        self.assertIn("1–85 of 85", summary)
        self.assertIn(f"{PATH}:85", summary)
        self.assertIn(FINDING["impact"], summary)
        self.assertNotIn("Code review complete", summary)

    def test_persistent_status_is_incomplete_and_sent_as_failure(self):
        final, events, prompts, engine = self.review([STATUS])
        self.assertEqual(len(prompts), 2)
        self.assertEqual(final["state"], "failed")
        self.assertIn("no grounded review", final["error"])
        self.assertEqual(final["checkpoint"]["planner"]["status"], "review_incomplete")
        types = {e["event_type"] for e in events}
        self.assertNotIn("agent.run.advisory", types)
        self.assertNotIn("agent.planner.completed", types)
        failure = next(e for e in events if e["event_type"] == "agent.planner.review_incomplete")
        self.assertIn("event: agent_run_done", engine.sse_event(failure, projection="legacy"))

    def test_no_findings_requires_concrete_checks(self):
        final, _, prompts, _ = self.review([
            {"decision_type": "complete", "summary": "No issues.", "arguments": {"findings": []}},
            {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [], "checked": [CHECKED]}},
        ])
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertEqual(len(prompts), 2)
        self.assertIn("No inconsistencies found in the inspected lines", final["checkpoint"]["planner"]["final_summary"])
        self.assertIn(CHECKED["detail"], final["checkpoint"]["planner"]["final_summary"])

    def test_lines_cut_from_model_prompt_cannot_ground_findings(self):
        result = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [FINDING]}}
        final, _, prompts, _ = self.review([result], long_source=True)
        self.assertEqual(final["state"], "failed")
        self.assertNotIn("85 | return 500", prompts[0])
        self.assertIn("partial", prompts[0].lower())

    def test_a_valid_partial_review_discloses_coverage(self):
        finding = {**FINDING, "line": 1, "evidence": "xxxxxxxxxx", "observed": "The file starts with a long filler comment.",
                   "impact": "It adds no implementation context."}
        result = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [finding]}}
        final, _, prompts, _ = self.review([result], long_source=True)
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertEqual(len(prompts), 1)
        summary = final["checkpoint"]["planner"]["final_summary"]
        self.assertIn("of 85 (partial)", summary)
        self.assertNotIn("1–85", summary)

    def test_review_answer_never_executes_a_tool_request(self):
        result = {"decision_type": "tool", "tool_id": "worktree.bind", "arguments": {}}
        final, events, prompts, _ = self.review([result])
        self.assertEqual(final["state"], "failed")
        self.assertEqual(len(prompts), 2)
        self.assertNotIn("worktree.bind", [e["payload"].get("tool_id") for e in events])


    def test_walkthrough_is_not_a_finding_even_with_an_exact_source_quote(self):
        walkthrough = {
            **FINDING, "observed": "return 500",
            "impact": "No immediate inconsistencies found. This line returns an HTTP status.",
        }
        invalid = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [walkthrough]}}
        corrected = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [FINDING]}}
        final, events, prompts, _ = self.review([invalid, corrected])
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertEqual(len(prompts), 2)
        self.assertNotIn("No immediate inconsistencies found", final["checkpoint"]["planner"]["final_summary"])
        rejection = next(e for e in events if e["event_type"] == "agent.planner.review_answer_rejected")
        self.assertIn("checks", rejection["payload"]["reason"])

    def test_quote_from_another_visible_line_does_not_validate_citation(self):
        wrong_line = {**FINDING, "line": 84}
        reply = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [wrong_line]}}
        final, events, prompts, _ = self.review([reply])
        self.assertEqual(final["state"], "failed")
        self.assertEqual(len(prompts), 2)
        rejection = next(e for e in events if e["event_type"] == "agent.planner.review_answer_rejected")
        self.assertIn("verbatim", rejection["payload"]["reason"])

    def test_no_findings_checks_also_need_exact_source_quotes(self):
        invalid = {"decision_type": "complete", "summary": "Review", "arguments": {
            "findings": [], "checked": [{**CHECKED, "evidence": "unseen code"}],
        }}
        valid = {"decision_type": "complete", "summary": "Review", "arguments": {
            "findings": [], "checked": [CHECKED],
        }}
        final, _, prompts, _ = self.review([invalid, valid])
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertEqual(len(prompts), 2)
        self.assertIn("No inconsistencies found in the inspected lines", final["checkpoint"]["planner"]["final_summary"])

    def test_unanchored_finding_cannot_be_accepted(self):
        unanchored = {k: v for k, v in FINDING.items() if k != "evidence"}
        reply = {"decision_type": "complete", "summary": "Review", "arguments": {"findings": [unanchored]}}
        final, _, prompts, _ = self.review([reply])
        self.assertEqual(final["state"], "failed")
        self.assertEqual(len(prompts), 2)


    def test_timed_out_generation_is_not_immediately_submitted_again(self):
        final, events, prompts, engine = self.review([TimeoutError("model still running")])
        self.assertEqual(final["state"], "failed")
        self.assertEqual(len(prompts), 1)
        self.assertIn("timed out", final["error"])
        outcome = next(e for e in events if e["event_type"] == "agent.planner.review_result")
        self.assertEqual(outcome["payload"]["outcome"], "timeout")
        self.assertIn("timed out", engine.sse_event(outcome, projection="legacy"))

    def test_completed_invalid_packet_can_retry_and_timeout_is_distinguished(self):
        final, events, prompts, _ = self.review([
            file_review.ReviewPacketError("Invalid review packet."),
            TimeoutError("model still running"),
        ])
        self.assertEqual(len(prompts), 2)
        self.assertEqual(final["state"], "failed")
        results = [e["payload"] for e in events if e["event_type"] == "agent.planner.review_result"]
        self.assertEqual([row["outcome"] for row in results], ["invalid_packet", "timeout"])
        self.assertTrue(all(row["elapsed_ms"] >= 0 for row in results))
        self.assertIn("invalid review packet", prompts[1].lower())

    def test_native_review_packet_needs_no_planner_wrapper(self):
        finding = {k: FINDING[k] for k in ("evidence", "observed", "impact")}
        decision = file_review.parse_native_review_result(json.dumps({"findings": [finding], "checked": []}))
        self.assertEqual(decision.arguments["findings"], [finding])
        self.assertEqual(decision.decision_type.value, "complete")

    def test_native_review_parser_rejects_action_envelopes_and_truncated_json(self):
        for raw in ('{"decision_type":"tool","findings":[],"checked":[]}', '{"findings": ['):
            with self.subTest(raw=raw), self.assertRaises(PlannerDecisionError):
                file_review.parse_native_review_result(raw)

    def test_review_budget_is_separate_from_the_planner_deadline(self):
        final, events, _, _ = self.review([TimeoutError()], request={"decision_timeout_ms": 46000})
        attempt = next(e for e in events if e["event_type"] == "agent.planner.review_attempt")
        self.assertEqual(attempt["payload"]["timeout_seconds"], 75)
        self.assertEqual(final["state"], "failed")
        self.assertEqual(file_review.review_timeout_seconds({"request": {"review_timeout_ms": 90000}}), 90)


    def test_native_provider_gets_review_only_instructions_with_evidence(self):
        finding = {k: FINDING[k] for k in ("evidence", "observed", "impact")}
        result = file_review.parse_native_review_result(json.dumps({"findings": [finding], "checked": []}))
        final, _, prompts, _ = self.review([result], native=True)
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertIn('Return only {"findings":[...],"checked":[...]}', prompts[0])
        self.assertNotIn("decision_type=complete", prompts[0])
        self.assertIn("85 | return 500", prompts[0])
        self.assertIn("Copy evidence verbatim", prompts[0])


    def test_native_review_schema_requests_no_path_or_line_numbers(self):
        for group in ("findings", "checked"):
            schema = file_review.NATIVE_REVIEW_FORMAT["properties"][group]["items"]
            self.assertNotIn("path", schema["properties"])
            self.assertNotIn("line", schema["properties"])
            self.assertIn("evidence", schema["required"])

    def test_native_review_retries_ambiguous_quote_without_guessing(self):
        finding = {k: FINDING[k] for k in ("evidence", "observed", "impact")}
        first = file_review.parse_native_review_result(json.dumps({"findings": [finding], "checked": []}))
        corrected = {**finding, "evidence": "return 500  # fallback"}
        second = file_review.parse_native_review_result(json.dumps({"findings": [corrected], "checked": []}))
        source = "# header\n" * 83 + "return 500  # first case\nreturn 500  # fallback\n"
        final, events, prompts, _ = self.review([first, second], native=True, source_override=source)
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertIn(f"{PATH}:85", final["checkpoint"]["planner"]["final_summary"])
        self.assertNotIn(f"{PATH}:84", final["checkpoint"]["planner"]["final_summary"])
        self.assertEqual(len(prompts), 2)
        self.assertIn("matches multiple", prompts[1])
        self.assertTrue(any(e["payload"].get("outcome") == "evidence_rejected" for e in events))

    def test_native_review_rejects_unmatched_quote(self):
        finding = {k: FINDING[k] for k in ("evidence", "observed", "impact")}
        finding["evidence"] = "return 200"
        reply = file_review.parse_native_review_result(json.dumps({"findings": [finding], "checked": []}))
        final, _, prompts, _ = self.review([reply], native=True)
        self.assertEqual(final["state"], "failed")
        self.assertIn("did not match", final["error"])
        self.assertEqual(len(prompts), 2)

    def test_native_no_findings_checks_resolve_to_a_real_line(self):
        checked = {k: CHECKED[k] for k in ("evidence", "detail")}
        result = file_review.parse_native_review_result(json.dumps({"findings": [], "checked": [checked]}))
        final, _, prompts, _ = self.review([result], native=True)
        self.assertEqual(final["state"], "completed", final["error"])
        self.assertIn(f"{PATH}:85", final["checkpoint"]["planner"]["final_summary"])
        self.assertEqual(len(prompts), 1)

    def test_native_review_cannot_cite_quote_from_omitted_source(self):
        finding = {k: FINDING[k] for k in ("evidence", "observed", "impact")}
        reply = file_review.parse_native_review_result(json.dumps({"findings": [finding], "checked": []}))
        final, _, prompts, _ = self.review([reply], native=True, long_source=True)
        self.assertNotIn("85 | return 500", prompts[0])
        self.assertEqual(final["state"], "failed")
        self.assertIn("did not match any supplied source line", final["error"])
