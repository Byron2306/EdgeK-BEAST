#!/usr/bin/env python3
"""Produce a conservative Phase 2 request-path trace from verified backend journeys."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_beast_coding_agent_census_journeys import run_all_journeys
from scripts.trace_beast_coding_agent_runtime import verify_agent_run_event_chain


UNPROVEN = {
    "desktop_ingress": "A desktop-to-backend request receipt is required.",
    "real_model_provider": "A real provider request and response receipt is required.",
    "sensorium_delivery": "An independent Sensorium admission receipt is required.",
    "remote_dispatch_return": "A remote dispatch and result receipt for the same run is required.",
}


def build_phase2_trace(journeys: list[dict]) -> dict:
    if not journeys:
        raise ValueError("at least one journey is required")
    result = []
    for journey in journeys:
        chain = journey.get("chain_verification") or {}
        run_id = journey.get("run_id")
        if chain.get("ok") is not True or chain.get("head_matches") is not True or not chain.get("head_hash"):
            raise ValueError("verified AgentRun chain and matching head required")
        if chain.get("events") != journey.get("event_count") or chain.get("run_id") != run_id:
            raise ValueError("AgentRun chain counts or identity differ")
        raw_events = journey.get("event_chain")
        if not isinstance(raw_events, list) or not raw_events:
            raise ValueError("raw AgentRun event chain required")
        verified = verify_agent_run_event_chain(raw_events)
        if verified["head_hash"] != chain["head_hash"] or verified["event_count"] != chain["events"] or verified["run_id"] != run_id:
            raise ValueError("raw event chain differs from journey summary")
        refs = {f"agent_run:{run_id}:event:{event['sequence']}:{event['event_hash']}" for event in raw_events}
        if journey.get("evidence_class") != "observed_production_backend_scripted_provider":
            raise ValueError("unexpected journey evidence class")
        boundary = journey.get("proof_boundaries") or {}
        if boundary.get("production_backend_classes") is not True or boundary.get("scripted_provider") is not True:
            raise ValueError("backend evidence class is not established")
        if any(boundary.get(key) is not False for key in (
            "desktop_renderer_ingress", "real_ollama_or_nim_provider", "sensorium_mirror_receipt"
        )):
            raise ValueError("unsupported live edge requires an independent receipt")
        sequence = []
        for record in journey.get("trace_records") or []:
            if record.get("run_id") != run_id or record.get("source") != "agent_run_event_chain":
                raise ValueError("trace record must belong to verified AgentRun chain")
            ref = str(record.get("evidence_ref") or "")
            if not ref.startswith(f"agent_run:{run_id}:event:"):
                raise ValueError("trace record missing AgentRun evidence reference")
            if ref not in refs:
                raise ValueError("trace record event hash not in verified AgentRun chain")
            sequence.append({"component": record["component_path"], "event": record["event"],
                             "evidence_ref": ref, "timestamp": record["timestamp"]})
        if not sequence:
            raise ValueError("verified run has no observable component sequence")
        sequence.sort(key=lambda x: (x["timestamp"], x["evidence_ref"], x["component"], x["event"]))
        result.append({
            "journey_id": journey["journey_id"], "run_id": run_id,
            "final_state": journey["final_state"], "event_count": chain["events"],
            "chain_head": chain["head_hash"], "observation_sequence": sequence,
            "objective_assessment": journey.get("objective_assessment"),
            "tool_observations": journey.get("tool_observations") or [],
        })
    return {
        "schema": "beast.coding_agent.phase2_request_trace.v1",
        "truth_boundary": "Sequence is observed event order, not proof of call causality between distinct organs.",
        "journeys": result,
        "edges": {
            "backend_planner_and_tools": {"state": "observed_scripted_provider", "evidence": [j["chain_head"] for j in result]},
            **{name: {"state": "unverified", "required_evidence": reason} for name, reason in UNPROVEN.items()},
        },
        "phase2_exit_met": False,
    }


def render_phase2_trace(report: dict) -> str:
    lines = ["# BEAST Coding Agent Phase 2 Request-Path Trace", "",
             "**Status:** backend sequence observed; end-to-end Phase 2 exit open.", "",
             report["truth_boundary"], "",
             "| Journey | Run | Events | Final state | Objective gap |",
             "|---|---|---:|---|---|"]
    for journey in report["journeys"]:
        assessment = journey.get("objective_assessment") or {}
        gap = ", ".join(assessment.get("unresolved_paths") or []) or "none assessed"
        lines.append(f"| `{journey['journey_id']}` | `{journey['run_id']}` | {journey['event_count']} | `{journey['final_state']}` | {gap} |")
    lines.extend(["", "## Edge status", ""])
    for name, edge in report["edges"].items():
        lines.append(f"- `{name}`: **{edge['state']}**. {edge.get('required_evidence', '')}".rstrip())
    lines.extend(["", "## Next receipt gates", "",
                  "A desktop ingress trace, real-model exchange, independent Sensorium receipt and remote dispatch/result pair must be added before the corresponding edges become observed. The cross-file `consumer.py` objective remains unresolved even though its backend run completed.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="beast-phase2-trace-") as folder:
        report = build_phase2_trace(run_all_journeys(Path(folder)))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.md_out.write_text(render_phase2_trace(report), encoding="utf-8")
    print(json.dumps({"journeys": len(report["journeys"]), "phase2_exit_met": report["phase2_exit_met"]}))


if __name__ == "__main__":
    main()
