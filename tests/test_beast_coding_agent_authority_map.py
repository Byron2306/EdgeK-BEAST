from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.beast_coding_agent_authority_map import (
    build_authority_map,
    render_authority_markdown,
    validate_authority_resolutions,
)


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


def _census(*paths: str) -> dict:
    return {
        "beast_object_type": "beast_full_system_census",
        "components": [{"path": path} for path in paths],
    }


def _responsibility() -> dict:
    return {
        "beast_object_type": "beast_coding_agent_responsibility_census",
        "phase1_conflicts": ["model_output_protocol", "governed_inference_routing"],
        "responsibilities": [
            {"id": "model_output_protocol"},
            {"id": "governed_inference_routing"},
        ],
    }


def _resolutions() -> dict:
    return {
        "version": "1.0",
        "resolutions": [
            {
                "id": "model_output_protocol",
                "kind": "scoped_chain",
                "authority_contracts": [
                    {
                        "scope": "typed_planner_decision",
                        "path": "app/kernel/agents/planner_provider.py",
                        "authority": "authoritative",
                    },
                    {
                        "scope": "direct_source_patch_output",
                        "path": "app/kernel/governance/output_governor.py",
                        "authority": "authoritative",
                    },
                ],
                "demotions": [
                    {
                        "path": "desktop-ide/renderer/js/ai/mode-controller.js",
                        "role": "ux_hint_only",
                    }
                ],
                "required_repairs": ["remove_frontend_action_ir_from_typed_planner_objective"],
                "invariant": "Typed planner decisions and source-patch Action IR are different protocols.",
            },
            {
                "id": "governed_inference_routing",
                "kind": "single_authority",
                "authority_contracts": [
                    {
                        "scope": "coding_agent_inference_composition",
                        "path": "app/kernel/compute/compute_plane.py",
                        "authority": "authoritative",
                    }
                ],
                "demotions": [],
                "required_repairs": ["route_typed_planner_provider_attempts_through_compute_plane"],
                "invariant": "One compute composition root governs provider attempts.",
            },
        ],
    }


def test_validates_scoped_authority_and_builds_repair_queue():
    paths = [
        "app/kernel/agents/planner_provider.py",
        "app/kernel/governance/output_governor.py",
        "desktop-ide/renderer/js/ai/mode-controller.js",
        "app/kernel/compute/compute_plane.py",
    ]
    validation = validate_authority_resolutions(_census(*paths), _responsibility(), _resolutions())
    report = build_authority_map(_census(*paths), _responsibility(), _resolutions())

    assert validation["valid"] is True
    assert validation["missing_paths"] == []
    assert report["summary"]["resolution_count"] == 2
    assert report["summary"]["phase1_conflicts_resolved"] == 2
    assert report["summary"]["required_repair_count"] == 2
    assert report["unresolved_phase1_ids"] == []


def test_rejects_missing_phase1_resolution_and_duplicate_scope():
    census = _census(
        "app/kernel/agents/planner_provider.py",
        "app/kernel/governance/output_governor.py",
        "desktop-ide/renderer/js/ai/mode-controller.js",
        "app/kernel/compute/compute_plane.py",
    )
    missing = _resolutions()
    missing["resolutions"] = missing["resolutions"][:1]
    with pytest.raises(ValueError, match="missing Phase 1 resolution"):
        validate_authority_resolutions(census, _responsibility(), missing)

    duplicate = _resolutions()
    duplicate["resolutions"][0]["authority_contracts"][1]["scope"] = "typed_planner_decision"
    with pytest.raises(ValueError, match="duplicate authority scope"):
        validate_authority_resolutions(census, _responsibility(), duplicate)


def test_repo_phase1_authority_contract_resolves_all_17_boundaries():
    root = Path(__file__).resolve().parents[1]
    census = json.loads(
        (root / "docs" / "evidence" / "BEAST_FULL_SYSTEM_CENSUS.json").read_text(encoding="utf-8")
    )
    responsibility = json.loads(
        (root / "docs" / "evidence" / "BEAST_CODING_AGENT_RESPONSIBILITY_CENSUS.json").read_text(
            encoding="utf-8"
        )
    )
    config_path = root / "config" / "beast_coding_agent_authority_resolutions.json"
    assert config_path.exists(), "Phase 1 requires a checked-in authority resolution contract"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    report = build_authority_map(census, responsibility, config)
    assert report["phase1_ids"] == EXPECTED_PHASE1
    assert report["unresolved_phase1_ids"] == []
    assert report["summary"]["resolution_count"] == 17
    assert report["summary"]["phase1_conflicts_resolved"] == 17
    assert report["summary"]["required_repair_count"] >= 14

    by_id = {item["id"]: item for item in report["resolutions"]}

    protocol = by_id["model_output_protocol"]
    assert protocol["authority_by_scope"]["typed_planner_decision"] == "app/kernel/agents/planner_provider.py"
    assert protocol["authority_by_scope"]["direct_source_patch_output"] == "app/kernel/governance/output_governor.py"

    routing = by_id["governed_inference_routing"]
    assert routing["authority_by_scope"]["coding_agent_inference_composition"] == "app/kernel/compute/compute_plane.py"

    context = by_id["repository_context_selection"]
    assert context["authority_by_scope"]["model_handoff_context"] == "app/kernel/data_processing/context_packet.py"

    task_input = by_id["task_input_governance"]
    assert task_input["authority_by_scope"]["typed_mission_envelope"] == "app/kernel/execution/task_envelope.py"

    verification = by_id["verification_gate"]
    assert verification["authority_by_scope"]["fresh_mutation_verification"] == "app/kernel/agents/phase_d_execution.py"

    memory = by_id["agent_memory_and_continuity"]
    assert memory["authority_by_scope"]["run_continuity_truth"] == "app/kernel/agents/run_store.py"
    assert memory["authority_by_scope"]["long_lived_residue"] == "app/kernel/storage/memory_hull.py"

    sensorium = by_id["sensorium_agent_observation"]
    assert sensorium["authority_by_scope"]["observation_admission"] == "app/kernel/sensorium/runtime.py"

    memfd = by_id["crystal_transport_and_memfd_capsules"]
    assert memfd["kind"] == "transport_only"
    assert memfd["authority_by_scope"]["immutable_capsule_transport"] == "app/kernel/crystal_bus/fd_transport.py"
    assert "does not grant execution or confidentiality authority" in memfd["invariant"]

    lattice = by_id["mission_edit_reuse_lattice"]
    assert lattice["kind"] == "advisory_only"
    assert lattice["authority_by_scope"]["verified_edit_reuse_advice"] == "app/kernel/compute/mission_crystal_lattice.py"

    markdown = render_authority_markdown(report)
    assert "# BEAST Coding Agent Phase 1 Authority Map" in markdown
    assert "typed_planner_decision" in markdown
    assert "Phase 2/3 repair queue" in markdown
