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

    result = {
        "path": path.name,
        "digest": digest(path),
        "tests": total("tests"),
        "failures": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
    }
    result["passed"] = (
        result["tests"] >= min_tests
        and result["failures"] == 0
        and result["errors"] == 0
        and result["skipped"] == 0
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile BEAST Coding Agent Phase 3 acceptance receipts.")
    parser.add_argument("--authority-junit", type=Path, required=True)
    parser.add_argument("--budget-junit", type=Path, required=True)
    parser.add_argument("--stagnation-junit", type=Path, required=True)
    parser.add_argument("--verification-junit", type=Path, required=True)
    parser.add_argument("--gauntlet-junit", type=Path, required=True)
    parser.add_argument("--live-model-junit", type=Path, required=True)
    parser.add_argument("--phase2-regression-junit", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    gates = {
        "least_authority_tool_plane": junit(args.authority_junit, min_tests=6),
        "policy_profile_budgets": junit(args.budget_junit, min_tests=6),
        "stagnation_and_oscillation_control": junit(args.stagnation_junit, min_tests=5),
        "verification_ladder": junit(args.verification_junit, min_tests=4),
        "seeded_multifile_repair_to_sourceplan": junit(args.gauntlet_junit, min_tests=1),
        "real_model_directed_tool_use": junit(args.live_model_junit, min_tests=1),
        "phase2_behavior_preserved": junit(args.phase2_regression_junit, min_tests=10),
    }
    phase3_exit_met = all(bool(gate.get("passed")) for gate in gates.values())

    report = {
        "schema": "beast.coding_agent.phase3.closure.v1",
        "phase": 3,
        "title": "BEAST Coding Agent Phase 3 Completion Receipt",
        "phase3_exit_met": phase3_exit_met,
        "gates": gates,
        "authority_boundary": {
            "class_a": "model_authorized_when_contract_allows",
            "class_b": "request_bound_approval_required",
            "class_c": "isolated_worktree_mutation_plus_request_bound_approval",
            "class_d": "consequential_execution_subject_to_declared approval policy",
            "class_e": "never_model_authorized",
            "sourceplan_promotion": "human_or_separate_governed_promotion_boundary",
        },
        "verification_boundary": {
            "phase3_ladder": "diff_safety_then_language_check_then_focused_affected_verification",
            "mutation_epoch_freshness": True,
            "sourceplan_requires_complete_ladder": True,
        },
        "deployment_boundary": {
            "hosted_linux_phase3": "claimed_when_all_gates_pass",
            "android_termux_phase3": "not_claimed_by_this_receipt",
            "note": "Android/Termux Phase 2 acceptance remains separate evidence. Phase 3 Android execution requires its own rerun.",
        },
    }
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# BEAST Coding Agent Phase 3 Completion Receipt",
        "",
        f"**Phase 3 exit:** {'PASS' if phase3_exit_met else 'REFUSE'}",
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
        "## Authority boundary",
        "",
        "Class E actions remain structurally unavailable to model authority. SourcePlan promotion is not granted by this phase.",
        "",
        "## Deployment boundary",
        "",
        "This receipt proves the hosted Linux Phase 3 acceptance matrix only. It does not upgrade the separate Android/Termux Phase 2 evidence into a Phase 3 Android claim.",
        "",
        "Phase 3 is complete only when every gate above is PASS in the same completion run.",
    ])
    args.md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "phase3_exit_met": phase3_exit_met,
        "gates": {name: bool(gate.get("passed")) for name, gate in gates.items()},
    }, sort_keys=True))
    return 0 if phase3_exit_met else 2


if __name__ == "__main__":
    raise SystemExit(main())
