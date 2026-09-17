#!/usr/bin/env python3
"""Verify and publish the BEAST coding-agent Phase 0 census exit receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STATUS = "phase0_census_complete_with_phase1_queue"
EXPECTED_PHASE1 = [
    "agent_memory_and_continuity",
    "agent_run_launch_and_provider_selection",
    "coding_evidence_production",
    "context_budget_and_compaction",
    "crystal_generalization_promotion_and_replay",
    "crystal_transport_and_memfd_capsules",
    "governed_inference_routing",
    "local_planner_provider_budget",
    "mission_edit_reuse_lattice",
    "model_output_protocol",
    "planner_completion_decision",
    "repository_context_selection",
    "sensorium_agent_observation",
    "sourceplan_handoff_and_approval",
    "task_input_governance",
    "verification_gate",
    "verified_inference_reuse",
]
EXPECTED_JOURNEYS = [
    "analysis_only",
    "single_file_mutation",
    "cross_file_mutation",
    "verification_failure_repair",
]
RUNTIME_BOUNDARIES = {
    "desktop_renderer_ingress_proven": (
        "Desktop renderer / Pair Programmer ingress: **not proven by this harness**"
    ),
    "real_ollama_or_nim_provider_proven": (
        "Real Ollama/NIM provider execution: **not proven by this harness**"
    ),
    "sensorium_mirror_proven": (
        "Sensorium mirror receipt: **not proven by AgentRun ledger events alone**"
    ),
}
CROSS_FILE_GAP = "completed_with_unresolved_cross_file_objective"
MEMFD_BOUNDARY = "not ambient execution or confidentiality authority"


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _responsibility_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in report.get("responsibilities") or []
        if isinstance(item, dict) and str(item.get("id") or "")
    }


def _verify_static_runtime_boundary(census: dict[str, Any]) -> None:
    promoted: list[str] = []
    for item in census.get("components") or []:
        if not isinstance(item, dict):
            continue
        runtime = item.get("runtime") if isinstance(item.get("runtime"), dict) else {}
        if any(value != "unverified" for value in runtime.values()):
            promoted.append(str(item.get("path") or "<unknown>"))
    if promoted:
        raise ValueError(
            "static full-system census promoted runtime truth: " + ", ".join(promoted[:20])
        )


def _verify_responsibility_boundary(responsibility: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    summary = _require_object(responsibility.get("summary"), "responsibility summary")
    expected = {
        "responsibility_count": 24,
        "claimant_count": 70,
        "unique_claimant_count": 42,
        "unresolved_conflict_count": 13,
        "phase1_conflict_count": 17,
    }
    for key, wanted in expected.items():
        actual = summary.get(key)
        if actual != wanted:
            raise ValueError(f"responsibility {key} drifted: {actual!r} != {wanted!r}")

    phase1 = responsibility.get("phase1_conflicts")
    if list(phase1 or []) != EXPECTED_PHASE1:
        raise ValueError("Phase 1 conflict queue changed without Phase 0 contract update")

    by_id = _responsibility_by_id(responsibility)
    completion = by_id.get("planner_completion_decision") or {}
    completion_finding = str(completion.get("finding") or "")
    if completion.get("phase1_required") is not True or "cross-file" not in completion_finding:
        raise ValueError("cross-file planner completion defect is not retained")

    transport = by_id.get("crystal_transport_and_memfd_capsules") or {}
    transport_finding = str(transport.get("finding") or "")
    if MEMFD_BOUNDARY not in transport_finding:
        raise ValueError("memfd transport boundary no longer denies ambient authority")
    return summary, by_id


def _verify_runtime_map(runtime_map: str) -> dict[str, Any]:
    text = str(runtime_map or "")
    for field, marker in RUNTIME_BOUNDARIES.items():
        if marker not in text:
            friendly = field.replace("_proven", "").replace("_", " ")
            raise ValueError(f"runtime map no longer preserves unproven {friendly} boundary")

    missing_journeys = [
        journey
        for journey in EXPECTED_JOURNEYS
        if f"| \`{journey}\` | \`completed\` |" not in text
    ]
    if missing_journeys:
        raise ValueError("runtime map missing completed journeys: " + ", ".join(missing_journeys))
    if f"\`{CROSS_FILE_GAP}\`" not in text or "\`consumer.py\`" not in text:
        raise ValueError("runtime map is missing the observed cross-file completion gap")

    producers = [
        path
        for path in (
            "app/kernel/agents/planner_runtime.py",
            "app/kernel/agents/run_store.py",
            "app/kernel/agents/tool_runtime.py",
        )
        if f"\`{path}\`" in text
    ]
    if len(producers) != 3:
        raise ValueError("runtime map lost an observed backend producer")

    return {
        "backend_path_observed": True,
        "journey_count": len(EXPECTED_JOURNEYS),
        "journeys": list(EXPECTED_JOURNEYS),
        "observed_component_producers": producers,
        "desktop_renderer_ingress_proven": False,
        "real_ollama_or_nim_provider_proven": False,
        "sensorium_mirror_proven": False,
    }


def build_phase0_closure(
    census: dict[str, Any],
    responsibility: dict[str, Any],
    runtime_map: str,
) -> dict[str, Any]:
    census = _require_object(census, "full-system census")
    responsibility = _require_object(responsibility, "responsibility census")
    if census.get("beast_object_type") != "beast_full_system_census":
        raise ValueError("wrong full-system census object type")
    if responsibility.get("beast_object_type") != "beast_coding_agent_responsibility_census":
        raise ValueError("wrong responsibility census object type")

    _verify_static_runtime_boundary(census)
    responsibility_summary, by_id = _verify_responsibility_boundary(responsibility)
    runtime_evidence = _verify_runtime_map(runtime_map)

    census_summary = _require_object(census.get("summary"), "full-system census summary")
    layer_counts = census_summary.get("layer_counts")
    if not isinstance(layer_counts, dict) or not layer_counts:
        raise ValueError("full-system census has no layer coverage")

    return {
        "beast_object_type": "beast_coding_agent_phase0_closure",
        "version": "1.0",
        "status": STATUS,
        "coding_agent_fixed": False,
        "scope": {
            "full_repository_static_inventory_complete": True,
            "coding_agent_responsibility_claimants_classified": True,
            "runtime_backend_slice_observed": True,
            "phase1_authority_resolution_required": True,
        },
        "summary": {
            "static_component_count": int(census_summary.get("component_count") or 0),
            "static_layer_count": len(layer_counts),
            "responsibility_count": responsibility_summary["responsibility_count"],
            "claimant_count": responsibility_summary["claimant_count"],
            "unique_claimant_count": responsibility_summary["unique_claimant_count"],
            "unresolved_conflict_count": responsibility_summary["unresolved_conflict_count"],
            "phase1_conflict_count": responsibility_summary["phase1_conflict_count"],
        },
        "runtime_evidence": runtime_evidence,
        "observed_gaps": [CROSS_FILE_GAP],
        "invariants": {
            "static_census_runtime_truth": "unverified_until_observed_receipt",
            "memfd_transport_boundary": str(
                (by_id.get("crystal_transport_and_memfd_capsules") or {}).get("finding") or ""
            ),
            "compression_edit_boundary": (
                "Editable source and patch anchors remain exact; compressed representations "
                "must not become mutation authority."
            ),
            "closure_meaning": (
                "Phase 0 proves census, responsibility classification, and a bounded observed "
                "backend runtime slice. It does not prove the desktop/model/Sensorium path and "
                "does not mean the coding agent is repaired."
            ),
        },
        "phase1_conflicts": list(EXPECTED_PHASE1),
        "exit_conditions": {
            "full_static_census_present": True,
            "responsibility_manifest_resolved_against_census": True,
            "responsibility_artifacts_deterministic": True,
            "observed_backend_journeys_present": True,
            "cross_file_defect_retained": True,
            "runtime_overclaim_prohibited": True,
            "phase1_queue_finite_and_explicit": True,
        },
    }


def render_phase0_closure_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    runtime = report["runtime_evidence"]
    lines = [
        "# BEAST Coding Agent Phase 0 Closure",
        "",
        f"**Status:** \`{report['status']}\`",
        "",
        "Phase 0 closes the census and responsibility-mapping problem. It does **not** claim the coding agent is fixed.",
        "",
        "## Census boundary",
        "",
        f"- Static components inventoried: **{summary['static_component_count']}**",
        f"- Static layers represented: **{summary['static_layer_count']}**",
        f"- Coding-agent responsibilities: **{summary['responsibility_count']}**",
        f"- Claimant relationships: **{summary['claimant_count']}** across **{summary['unique_claimant_count']}** unique organs",
        f"- Explicit unresolved authority conflicts: **{summary['unresolved_conflict_count']}**",
        f"- Phase 1 queue: **{summary['phase1_conflict_count']}** items",
        "",
        "Static census runtime fields remain \`unverified\` until receipt-backed observation exists.",
        "",
        "## Runtime evidence",
        "",
        "The production backend path is observed through scripted-provider journeys.",
        "",
    ]
    for journey in runtime["journeys"]:
        lines.append(f"- \`{journey}\`: completed")
    lines.extend(
        [
            "",
            "- Desktop renderer / Pair Programmer ingress: **not proven**",
            "- Real Ollama/NIM provider execution: **not proven**",
            "- Sensorium mirror receipt: **not proven**",
            "",
            "## Retained observed defect",
            "",
            f"- \`{CROSS_FILE_GAP}\`: the cross-file journey may complete while \`consumer.py\` remains unresolved.",
            "",
            "## Authority invariants",
            "",
            f"- memfd/capsule: {report['invariants']['memfd_transport_boundary']}",
            f"- compression: {report['invariants']['compression_edit_boundary']}",
            "",
            "## Phase 1 authority queue",
            "",
        ]
    )
    lines.extend(f"- \`{item}\`" for item in report["phase1_conflicts"])
    lines.extend(
        [
            "",
            "## Exit meaning",
            "",
            report["invariants"]["closure_meaning"],
            "",
        ]
    )
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {path}") from exc
    return _require_object(value, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--responsibility", type=Path, required=True)
    parser.add_argument("--runtime-map", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    report = build_phase0_closure(
        _load_json(args.census),
        _load_json(args.responsibility),
        args.runtime_map.read_text(encoding="utf-8"),
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.md_out.write_text(render_phase0_closure_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
