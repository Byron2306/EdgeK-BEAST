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
    def review(self, replies, *, long_source=False, request=None, native=False, source_override=None, one_turn=False, objective=None):
        async def run(root):
            path = root / PATH
            path.parent.mkdir(parents=True)
            comment = "# " + "x" * (100 if long_source else 8)
            source = source_override if source_override is not None else "\n".join([comment] * 84 + ["return 500"]) + "\n"
            path.write_text(source)
            prompts = []

            async def respond(prompt, run, turn):
                if not prompt.startswith(("BEAST FILE REVIEW RESULT", "BEAST SOURCE EXPLANATION")):
                    return STATUS
                prompts.append(prompt)
                result = replies[min(len(prompts) - 1, len(replies) - 1)]
                if isinstance(result, Exception):
                    raise result
                return result

            engine = AgentRunEngine(root)
            run_id = engine.create_run(
                session_id="desktop-review", objective=objective or f"Review {PATH} for inconsistencies.",
                mode="analysis", provider="ollama", model="granite3.3:2b",
                request={"context_files": [PATH], **(request or {})},
            )["run_id"]
            provider = CallbackPlannerProvider(respond)
            provider.supports_native_file_review = native
            runtime = AgentPlannerRuntime(engine, provider, max_turns=4)
            if one_turn:
                first = await runtime.run_one_turn(run_id)
                self.assertEqual(first["state"], "updating_plan")
                self.assertEqual(prompts, [])
                for _ in range(4):
                    final = await runtime.run_one_turn(run_id)
                    if final["state"] in {"completed", "failed"}:
                        break
            else:
                final = await runtime.run(run_id)
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


def test_explanation_prioritizes_outline_and_validates_citations():
    from app.kernel.agents.file_review import collect_review_evidence
    from app.kernel.agents.planner_provider import parse_planner_decision

    path = "app.py"
    def observed(start, content, **extra):
        return {"tool_id": "workspace.read_range", "status": "completed",
                "result": {"path": path, "start_line": start, "end_line": start,
                           "total_lines": 100, "content": content, **extra}}

    first = observed(1, "import os", outline=[{"line": 90, "name": "main"}])
    evidence = collect_review_evidence((path,), [first], explain=True)
    assert evidence.next_read["start_line"] == 90
    evidence = collect_review_evidence((path,), [first, observed(90, "def main():")], explain=True)
    assert "findings" not in evidence.explanation_prompt("What does main do?")
    decision = parse_planner_decision({"decision_type": "complete", "summary": "Source explanation",
        "arguments": {"points": [{"path": path, "line": 90, "evidence": "def main():", "text": "Defines the main entry point."}]}})
    answer, reason = evidence.explanation_answer(decision)
    assert not reason and "app.py:90" in answer and "(partial)" in answer
    decision.arguments["points"][0]["line"] = 91
    assert not evidence.explanation_answer(decision)[0]



def test_attached_ask_uses_outline_then_completes_with_advisory():
    source = "\n".join(["# intro"] * 140 + ["def main():", "    return 42"]) + "\n"
    reply = {"decision_type": "complete", "summary": "Source explanation",
             "arguments": {"points": [{"path": PATH, "line": 142, "evidence": "return 42",
                                       "text": "The main function returns 42."}]}}
    final, events, prompts, _ = FileReviewContract().review(
        [reply], request={"file_answer_style": "explain", "read_only_file_review": True},
        source_override=source,
    )
    assert final["state"] == "completed", final["error"]
    assert len(prompts) == 1 and prompts[0].startswith("BEAST SOURCE EXPLANATION")
    assert "142 |     return 42" in prompts[0]
    advisory = next(event["payload"]["text"] for event in events if event["event_type"] == "agent.run.advisory")
    assert "returns 42" in advisory and "(partial)" in advisory
    assert not any(event["event_type"] == "agent.planner.review_incomplete" for event in events)


def test_attached_ask_reads_past_first_slice_through_turn_endpoint_contract():
    source = "# intro\n" * 140 + "def main():\n    return 42\n"
    reply = {"decision_type": "complete", "summary": "Source explanation",
             "arguments": {"points": [{"path": PATH, "line": 142, "evidence": "return 42",
                                       "text": "The main function returns 42."}]}}
    final, events, prompts, _ = FileReviewContract().review(
        [reply], request={"file_answer_style": "explain", "read_only_file_review": True},
        source_override=source, one_turn=True,
    )
    assert final["state"] == "completed", final["error"]
    assert len(prompts) == 1 and "142 |     return 42" in prompts[0]
    assert any(event["event_type"] == "agent.run.advisory" for event in events)



def test_named_ask_prefers_body_even_when_symbol_is_not_in_broad_outline_sample():
    source = "".join(f"def other_{i}():\n    return {i}\n\n" for i in range(61))
    source += "class Coder:\n    async def _run_turn(self):\n        run = await start_run()\n"
    source += "        # body\n" * 86
    source += "        return await final_advisory(run)\n"
    source += "".join(f"def later_{i}():\n    return {i}\n\n" for i in range(60))
    handoff = "return await final_advisory(run)"
    line = next(i for i, text in enumerate(source.splitlines(), 1) if handoff in text)
    reply = {"decision_type": "complete", "summary": "Source explanation",
             "arguments": {"points": [{"ref": f"S1L{line}",
                                       "text": "The run is handed off to the final advisory."}]}}
    final, events, prompts, _ = FileReviewContract().review(
        [reply], request={"file_answer_style": "explain", "read_only_file_review": True},
        source_override=source, one_turn=True, objective=f"Trace `_run_turn` in {PATH}.",
    )
    assert final["state"] == "completed", final["error"]
    assert len(prompts) == 1
    assert "run = await start_run()" in prompts[0]
    assert handoff in prompts[0]
    assert "def other_0" not in prompts[0]
    assert "def later_0" not in prompts[0]
    assert any(event["event_type"] == "agent.run.advisory" for event in events)


def test_exact_coder_turn_trace_receives_all_four_handoffs():
    source = (Path(__file__).resolve().parents[2] / "app/cli/coder.py").read_text()
    quotes = ("await self.runtime.start_run(", "self.runtime.start_turn(run_id)",
              "async for runtime_event in self.runtime.turn_events(",
              'final_text = advisory or ("" if grounded else visible)')
    lines = [next(i for i, text in enumerate(source.splitlines(), 1) if quote in text) for quote in quotes]
    points = [{"ref": f"S1L{line}", "text": f"Observed handoff {index}."} for index, line in enumerate(lines)]
    reply = {"decision_type": "complete", "summary": "Source explanation", "arguments": {"points": points}}
    final, events, prompts, _ = FileReviewContract().review(
        [reply], request={"file_answer_style": "explain", "read_only_file_review": True},
        source_override=source, one_turn=True,
        objective=f"Trace _run_turn in {PATH} from submission to the final advisory. Cite the relevant handoffs.",
    )
    assert final["state"] == "completed", final["error"]
    assert len(prompts) == 1 and all(quote in prompts[0] for quote in quotes)
    assert all(f"S1L{line} |" in prompts[0] for line in lines)
    final_summary = final["checkpoint"]["planner"]["final_summary"]
    assert all(f"{PATH}:{line}" in final_summary for line in lines)
    attempt = next(e["payload"] for e in events if e["event_type"] == "agent.planner.review_attempt")
    assert attempt["source_mode"] == "symbol_focused"
    assert attempt["integration_context_appended"] is False



def test_focused_ask_refuses_a_reference_to_source_it_did_not_supply():
    source = "# intro\n" * 140 + "def main():\n    return 42\n"
    reply = {"decision_type": "complete", "summary": "Source explanation",
             "arguments": {"points": [{"ref": "S1L1", "text": "An unrelated line."}]}}
    final, events, prompts, _ = FileReviewContract().review(
        [reply], request={"file_answer_style": "explain", "read_only_file_review": True},
        source_override=source, objective=f"Explain `main` in {PATH}.",
    )
    assert final["state"] == "failed"
    assert "copy a source reference shown" in final["error"]
    assert len(prompts) == 2
    assert not any(event["event_type"] == "agent.run.advisory" for event in events)


def test_focused_ask_accepts_the_six_contiguous_ranges_returned_by_live_nim():
    source = (Path(__file__).resolve().parents[2] / "app/cli/coder.py").read_text()
    lines = source.splitlines()
    first = next(i for i, text in enumerate(lines, 1) if "async def _run_turn(" in text)
    window_end = min(len(lines), first + 239)
    span = max(6, window_end - first + 1)
    step = span // 6
    bounds: list[tuple[int, int]] = []
    cursor = first
    for index in range(6):
        stop = window_end if index == 5 else cursor + step - 1
        bounds.append((cursor, stop))
        cursor = stop + 1
    points = [{"ref": f"S1L{start}-S1L{end}", "text": "Identifies a handoff."} for start, end in bounds]
    final, _, prompts, _ = FileReviewContract().review(
        [{"decision_type": "complete", "summary": "Trace", "arguments": {"points": points}}],
        request={"file_answer_style": "explain", "read_only_file_review": True},
        source_override=source, one_turn=True, objective=f"Trace _run_turn in {PATH}.",
    )
    assert final["state"] == "completed", final["error"]
    assert len(prompts) == 1
    summary = final["checkpoint"]["planner"]["final_summary"]
    assert all(f"{PATH}:{start}–{end}" in summary for start, end in bounds)


def test_focused_ask_refuses_ranges_that_cross_gaps_files_or_reverse_direction():
    from app.kernel.agents.planner_provider import parse_planner_decision

    evidence = file_review.ReviewEvidence("", {"a.py": {2, 4, 5}, "b.py": {2}}, {"a.py": 5, "b.py": 2}, None,
        source_lines={"a.py": {2: "x = 1", 4: "y = 2", 5: "z = 3"}, "b.py": {2: "a = 4"}},
        symbol_focused=True)
    for ref in ("S1L2-S1L4", "S1L4-S2L2", "S1L5-S1L4", "S1L4-S1L6", "S1L4-S1L5-S1L6"):
        decision = parse_planner_decision({"decision_type": "complete", "summary": "Trace",
                                          "arguments": {"points": [{"ref": ref, "text": "A claim."}]}})
        assert not evidence.explanation_answer(decision)[0], ref
