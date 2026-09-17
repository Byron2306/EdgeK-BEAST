from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_beast_phase0_census_exit import (
    build_phase0_closure,
    render_phase0_closure_markdown,
)


def _census() -> dict:
    return {
        "beast_object_type": "beast_full_system_census",
        "summary": {
            "component_count": 18885,
            "layer_counts": {"agency_planning": 33, "compute_reuse": 234},
        },
        "components": [
            {
                "path": "app/kernel/agents/planner_runtime.py",
                "runtime": {
                    "constructed": "unverified",
                    "invoked": "unverified",
                    "evidence_producing": "unverified",
                },
            }
        ],
    }


def _responsibility() -> dict:
    phase1 = [
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
    return {
        "beast_object_type": "beast_coding_agent_responsibility_census",
        "summary": {
            "responsibility_count": 24,
            "claimant_count": 70,
            "unique_claimant_count": 42,
            "unresolved_conflict_count": 13,
            "phase1_conflict_count": 17,
        },
        "phase1_conflicts": phase1,
        "responsibilities": [
            {
                "id": "planner_completion_decision",
                "phase1_required": True,
                "status": "observed_authoritative",
                "finding": (
                    "Current completion authority is observed, but the Phase 0 "
                    "cross-file journey completed with consumer.py unresolved."
                ),
            },
            {
                "id": "crystal_transport_and_memfd_capsules",
                "phase1_required": True,
                "status": "dormant_or_stranded",
                "finding": (
                    "Sealed memfd/capsule transport is immutable transport evidence, "
                    "not ambient execution or confidentiality authority."
                ),
            },
        ],
    }


def _runtime_map() -> str:
    return """# BEAST Coding Agent Runtime Map

## Evidence boundary
- Desktop renderer / Pair Programmer ingress: **not proven by this harness**
- Real Ollama/NIM provider execution: **not proven by this harness**
- Sensorium mirror receipt: **not proven by AgentRun ledger events alone**

## Observed component producers
- `app/kernel/agents/planner_runtime.py`
- `app/kernel/agents/run_store.py`
- `app/kernel/agents/tool_runtime.py`

## Journey results
| `analysis_only` | `completed` | 18 | 2 |
| `single_file_mutation` | `completed` | 95 | 6 |
| `cross_file_mutation` | `completed` | 124 | 8 |
| `verification_failure_repair` | `completed` | 127 | 8 |

## Observed gaps
- `completed_with_unresolved_cross_file_objective`: unresolved paths `consumer.py`.
"""


def test_builds_truthful_phase0_closure_without_claiming_agent_is_fixed():
    report = build_phase0_closure(_census(), _responsibility(), _runtime_map())

    assert report["status"] == "phase0_census_complete_with_phase1_queue"
    assert report["coding_agent_fixed"] is False
    assert report["summary"]["responsibility_count"] == 24
    assert report["summary"]["phase1_conflict_count"] == 17
    assert report["runtime_evidence"]["journey_count"] == 4
    assert report["runtime_evidence"]["backend_path_observed"] is True
    assert report["runtime_evidence"]["desktop_renderer_ingress_proven"] is False
    assert report["runtime_evidence"]["real_ollama_or_nim_provider_proven"] is False
    assert report["runtime_evidence"]["sensorium_mirror_proven"] is False
    assert report["observed_gaps"] == ["completed_with_unresolved_cross_file_objective"]
    assert "not ambient execution or confidentiality authority" in report["invariants"]["memfd_transport_boundary"]


def test_rejects_overclaimed_or_incomplete_runtime_map():
    overclaim = _runtime_map().replace(
        "Desktop renderer / Pair Programmer ingress: **not proven by this harness**",
        "Desktop renderer / Pair Programmer ingress: **proven**",
    )
    with pytest.raises(ValueError, match="desktop renderer"):
        build_phase0_closure(_census(), _responsibility(), overclaim)

    missing_gap = _runtime_map().replace(
        "- `completed_with_unresolved_cross_file_objective`: unresolved paths `consumer.py`.\n",
        "",
    )
    with pytest.raises(ValueError, match="cross-file"):
        build_phase0_closure(_census(), _responsibility(), missing_gap)


def test_repo_commits_exact_closure_artifacts_and_ci_regenerates_them():
    root = Path(__file__).resolve().parents[1]
    census = json.loads(
        (root / "docs" / "evidence" / "BEAST_FULL_SYSTEM_CENSUS.json").read_text(encoding="utf-8")
    )
    responsibility = json.loads(
        (root / "docs" / "evidence" / "BEAST_CODING_AGENT_RESPONSIBILITY_CENSUS.json").read_text(
            encoding="utf-8"
        )
    )
    runtime_map = (root / "docs" / "BEAST_CODING_AGENT_RUNTIME_MAP.md").read_text(encoding="utf-8")
    expected = build_phase0_closure(census, responsibility, runtime_map)

    json_path = root / "docs" / "evidence" / "BEAST_CODING_AGENT_PHASE0_CLOSURE.json"
    md_path = root / "docs" / "BEAST_CODING_AGENT_PHASE0_CLOSURE.md"
    assert json_path.exists()
    assert md_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8")) == expected
    assert md_path.read_text(encoding="utf-8") == render_phase0_closure_markdown(expected)

    workflow = (root / ".github" / "workflows" / "beast-phase0-census.yml").read_text(encoding="utf-8")
    for fragment in [
        "scripts/verify_beast_phase0_census_exit.py",
        "BEAST_CODING_AGENT_PHASE0_CLOSURE.json",
        "BEAST_CODING_AGENT_PHASE0_CLOSURE.md",
        "phase0_census_complete_with_phase1_queue",
    ]:
        assert fragment in workflow
