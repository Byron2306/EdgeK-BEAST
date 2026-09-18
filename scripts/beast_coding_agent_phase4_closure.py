#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def junit(path: Path, *, min_tests: int = 1) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))

    def total(name: str) -> int:
        values = [int(float(s.attrib.get(name, "0") or 0)) for s in suites]
        if root.tag == "testsuites":
            declared = int(float(root.attrib.get(name, "0") or 0))
            return max(declared, sum(values))
        return sum(values)

    case_names = sorted({
        str(case.attrib.get("name") or "").strip()
        for case in root.findall(".//testcase")
        if str(case.attrib.get("name") or "").strip()
    })
    result = {
        "path": path.name,
        "digest": digest(path),
        "tests": total("tests"),
        "failures": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
        "test_cases": case_names,
    }
    result["passed"] = (
        result["tests"] >= min_tests
        and result["failures"] == 0
        and result["errors"] == 0
        and result["skipped"] == 0
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile BEAST Coding Agent Phase 4 acceptance receipts.")
    parser.add_argument("--canonical-junit", type=Path, required=True)
    parser.add_argument("--live-approval-junit", type=Path, required=True)
    parser.add_argument("--modes-junit", type=Path, required=True)
    parser.add_argument("--sensitive-external-junit", type=Path, required=True)
    parser.add_argument("--phase3-regression-junit", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    live_gate = junit(args.live_approval_junit, min_tests=6)
    required_live_tests = {
        "test_live_planner_uses_one_use_phase4_capability",
        "test_review_mode_lifts_read_only_tool_into_durable_approval",
        "test_restart_paused_approval_consumes_exact_capability",
        "test_request_replan_continues_same_run_with_governance_observation",
        "test_permanent_deny_persists_tool_revocation_across_runs",
        "test_restart_approval_route_executes_exact_step_before_worker_relaunch",
    }
    observed_live_tests = set(live_gate.get("test_cases") or [])
    missing_live_tests = sorted(required_live_tests - observed_live_tests)
    live_gate["required_tests"] = sorted(required_live_tests)
    live_gate["missing_required_tests"] = missing_live_tests
    live_gate["required_tests_present"] = not missing_live_tests
    live_gate["passed"] = bool(live_gate.get("passed")) and not missing_live_tests

    gates = {
        "canonical_phase4_subsystem": junit(args.canonical_junit, min_tests=20),
        "live_durable_approval_and_restart": live_gate,
        "permission_modes_and_bounded_autonomy": junit(args.modes_junit, min_tests=5),
        "sensitive_and_external_content_controls": junit(args.sensitive_external_junit, min_tests=3),
        "phase3_behavior_preserved": junit(args.phase3_regression_junit, min_tests=20),
    }
    phase4_exit_met = all(bool(gate.get("passed")) for gate in gates.values())

    report = {
        "schema": "beast.coding_agent.phase4.closure.v1",
        "phase": 4,
        "title": "BEAST Coding Agent Phase 4 Completion Receipt",
        "phase4_exit_met": phase4_exit_met,
        "gates": gates,
        "exit_gate": {
            "approval_survives_restart": True if phase4_exit_met else False,
            "exact_paused_step_resumed": True if phase4_exit_met else False,
            "restart_route_executes_exact_step_before_replanning": True if phase4_exit_met else False,
            "request_replan_continues_same_run": True if phase4_exit_met else False,
            "permanent_deny_persists_tool_revocation": True if phase4_exit_met else False,
            "request_bound_capability": True if phase4_exit_met else False,
            "single_use_capability": True if phase4_exit_met else False,
            "future_authority_widened": False,
        },
        "permission_boundary": {
            "REVIEW": "consequential and configured read actions require approval",
            "GUIDED": "ordinary reads automatic; governed mutation/execution approval-gated",
            "BOUNDED_AUTONOMY": "scoped worktree actions only within explicit file/command/budget/network boundaries",
            "OBSERVE_ONLY": "mutation denied",
            "LOCKED": "agent execution denied",
        },
        "data_boundary": {
            "sensitive_access": "explicit one-use approval required",
            "raw_sensitive_persistence": False,
            "external_content": "classified before model admission",
            "high_risk_external_content": "quarantined",
            "external_policy_effect_allowed": False,
            "external_authority_widening_allowed": False,
        },
        "promotion_boundary": {
            "sourceplan_promotion_authority_granted": False,
            "global_policy_mutation_authority_granted": False,
        },
        "deployment_boundary": {
            "hosted_linux_phase4": "claimed when all gates pass",
            "android_termux_phase4": "not claimed by this receipt",
        },
    }
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# BEAST Coding Agent Phase 4 Completion Receipt",
        "",
        f"**Phase 4 exit:** {'PASS' if phase4_exit_met else 'REFUSE'}",
        "",
        "| Gate | State | Evidence digest |",
        "|---|---|---|",
    ]
    for name, gate in gates.items():
        lines.append(
            f"| `{name}` | **{'PASS' if gate.get('passed') else 'FAIL'}** | `{gate.get('digest') or ''}` |"
        )
    lines.extend([
        "",
        "## Exit boundary",
        "",
        "A persisted approval may resume only its exact paused step through a request-bound, single-use capability. Replay is denied and future authority is not widened.",
        "",
        "## Permission boundary",
        "",
        "Bounded Autonomy remains constrained by worktree isolation, file and command allowlists, budgets, network policy, evidence generation and the SourcePlan promotion boundary.",
        "",
        "## Data boundary",
        "",
        "Sensitive values are not persisted raw into the AgentRun/model-visible path. External content is classified separately from fetch authorization and high-risk content is quarantined before model admission.",
        "",
        "## Deployment boundary",
        "",
        "This closure proves the hosted Linux Phase 4 acceptance matrix. Android/Termux Phase 4 remains a separate rerun boundary.",
    ])
    args.md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "phase4_exit_met": phase4_exit_met,
        "gates": {name: bool(gate.get("passed")) for name, gate in gates.items()},
    }, sort_keys=True))
    return 0 if phase4_exit_met else 2


if __name__ == "__main__":
    raise SystemExit(main())
