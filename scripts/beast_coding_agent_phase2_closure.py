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
    parser = argparse.ArgumentParser(description="Compile independent BEAST Phase 2 acceptance receipts.")
    parser.add_argument("--backend-trace", type=Path, required=True)
    parser.add_argument("--desktop-receipt", type=Path, required=True)
    parser.add_argument("--sensorium-junit", type=Path, required=True)
    parser.add_argument("--ollama-junit", type=Path, required=True)
    parser.add_argument("--remote-junit", type=Path, required=True)
    parser.add_argument("--endurance-junit", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    backend = json.loads(args.backend_trace.read_text(encoding="utf-8"))
    desktop = json.loads(args.desktop_receipt.read_text(encoding="utf-8"))
    cross = next((j for j in backend.get("journeys", []) if j.get("journey_id") == "cross_file_mutation"), {})
    cross_assessment = cross.get("objective_assessment") if isinstance(cross.get("objective_assessment"), dict) else {}

    gates = {
        "backend_request_path": {
            "passed": backend.get("edges", {}).get("backend_planner_and_tools", {}).get("state") == "observed_scripted_provider",
            "receipt_digest": digest(args.backend_trace),
            "journeys": len(backend.get("journeys") or []),
        },
        "cross_file_objective": {
            "passed": cross_assessment.get("satisfied") is True and not cross_assessment.get("unresolved_paths"),
            "unresolved_paths": cross_assessment.get("unresolved_paths") or [],
            "assessment_basis": cross_assessment.get("assessment_basis") or "",
        },
        "sensorium_delivery": junit(args.sensorium_junit, min_tests=1),
        "desktop_ingress": {
            "passed": desktop.get("verified") is True
            and desktop.get("request_path") == "/edgek/ide/agent-sessions/create"
            and bool(desktop.get("backend_receipt", {}).get("session_id")),
            "receipt_digest": digest(args.desktop_receipt),
            "request_path": desktop.get("request_path") or "",
            "edge": desktop.get("edge") or "",
        },
        "real_model_provider": junit(args.ollama_junit, min_tests=1),
        "remote_dispatch_return": junit(args.remote_junit, min_tests=4),
        "planner_endurance": junit(args.endurance_junit, min_tests=3),
    }
    phase2_exit_met = all(bool(gate.get("passed")) for gate in gates.values())

    report = {
        "schema": "beast.coding_agent.phase2.closure.v1",
        "phase": 2,
        "title": "BEAST Coding Agent Phase 2 Completion Receipt",
        "phase2_exit_met": phase2_exit_met,
        "gates": gates,
        "boundary": {
            "termux_android_runtime": "not_claimed",
            "note": "Hosted Ollama/qwen2.5:0.5b proves the native constrained-model provider path, not Android/Termux-specific packaging.",
        },
    }
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# BEAST Coding Agent Phase 2 Completion Receipt",
        "",
        f"**Phase 2 exit:** {'PASS' if phase2_exit_met else 'REFUSE'}",
        "",
        "| Gate | State | Evidence |",
        "|---|---|---|",
    ]
    for name, gate in gates.items():
        evidence = gate.get("receipt_digest") or gate.get("digest") or gate.get("assessment_basis") or ""
        lines.append(f"| `{name}` | **{'PASS' if gate.get('passed') else 'FAIL'}** | `{evidence}` |")
    lines.extend([
        "",
        "## Boundary",
        "",
        "The hosted Ollama gate exercises BEAST's native provider using a small Qwen model. It does not claim an Android/Termux packaging acceptance run.",
        "",
        "Phase 2 is complete only when every gate above is PASS in the same hosted acceptance run.",
    ])
    args.md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"phase2_exit_met": phase2_exit_met, "gates": {k: v.get("passed") for k, v in gates.items()}}, sort_keys=True))
    return 0 if phase2_exit_met else 2


if __name__ == "__main__":
    raise SystemExit(main())
