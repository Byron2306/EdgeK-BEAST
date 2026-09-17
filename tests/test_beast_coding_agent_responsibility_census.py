from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.beast_coding_agent_responsibility_census import (
    build_responsibility_report,
    render_responsibility_markdown,
    validate_responsibility_config,
)


def _census(*paths: str) -> dict:
    return {
        "beast_object_type": "beast_full_system_census",
        "version": "0.2",
        "components": [
            {
                "path": path,
                "runtime": {
                    "constructed": "unverified",
                    "invoked": "unverified",
                    "evidence_producing": "unverified",
                },
                "authority": "unverified",
                "disposition": "unclassified",
                "agent_relevance": "unclassified",
            }
            for path in paths
        ],
    }


def _config() -> dict:
    return {
        "version": "1.0",
        "responsibilities": [
            {
                "id": "context_selection",
                "phase1_required": True,
                "status": "unresolved_conflict",
                "claimants": [
                    {
                        "path": "app/kernel/data_processing/context_packet.py",
                        "role": "candidate_authority",
                        "disposition": "online_supporting",
                        "agent_relevance": "direct",
                        "evidence": "static_contract",
                    },
                    {
                        "path": "desktop-ide/renderer/js/ai/context-picker.js",
                        "role": "candidate_authority",
                        "disposition": "online_supporting",
                        "agent_relevance": "direct",
                        "evidence": "static_contract",
                    },
                ],
                "finding": "Two layers currently claim context selection responsibility.",
            },
            {
                "id": "runtime_planning",
                "phase1_required": False,
                "status": "observed_authoritative",
                "claimants": [
                    {
                        "path": "app/kernel/agents/planner_runtime.py",
                        "role": "current_authority",
                        "disposition": "online_authoritative",
                        "agent_relevance": "direct",
                        "evidence": "observed_runtime",
                    }
                ],
                "finding": "Observed backend journeys execute AgentPlannerRuntime.",
            },
        ],
    }


def test_validates_claimants_against_census_and_builds_finite_conflict_list():
    census = _census(
        "app/kernel/data_processing/context_packet.py",
        "desktop-ide/renderer/js/ai/context-picker.js",
        "app/kernel/agents/planner_runtime.py",
    )
    config = _config()

    validation = validate_responsibility_config(census, config)
    report = build_responsibility_report(census, config)

    assert validation["valid"] is True
    assert validation["missing_paths"] == []
    assert report["summary"]["responsibility_count"] == 2
    assert report["summary"]["unresolved_conflict_count"] == 1
    assert report["phase1_conflicts"] == ["context_selection"]
    planning = next(item for item in report["responsibilities"] if item["id"] == "runtime_planning")
    assert planning["current_authorities"] == ["app/kernel/agents/planner_runtime.py"]


def test_rejects_missing_claimant_path_and_invalid_status_role_or_disposition():
    census = _census("app/kernel/agents/planner_runtime.py")
    config = _config()

    with pytest.raises(ValueError, match="missing claimant path"):
        validate_responsibility_config(census, config)

    bad_status = _config()
    bad_status["responsibilities"][1]["status"] = "mystery"
    with pytest.raises(ValueError, match="invalid responsibility status"):
        validate_responsibility_config(
            _census(
                "app/kernel/data_processing/context_packet.py",
                "desktop-ide/renderer/js/ai/context-picker.js",
                "app/kernel/agents/planner_runtime.py",
            ),
            bad_status,
        )

    bad_role = _config()
    bad_role["responsibilities"][1]["claimants"][0]["role"] = "king"
    with pytest.raises(ValueError, match="invalid claimant role"):
        validate_responsibility_config(
            _census(
                "app/kernel/data_processing/context_packet.py",
                "desktop-ide/renderer/js/ai/context-picker.js",
                "app/kernel/agents/planner_runtime.py",
            ),
            bad_role,
        )

    bad_disposition = _config()
    bad_disposition["responsibilities"][1]["claimants"][0]["disposition"] = "magic"
    with pytest.raises(ValueError, match="invalid claimant disposition"):
        validate_responsibility_config(
            _census(
                "app/kernel/data_processing/context_packet.py",
                "desktop-ide/renderer/js/ai/context-picker.js",
                "app/kernel/agents/planner_runtime.py",
            ),
            bad_disposition,
        )


def test_rejects_multiple_current_authorities_unless_status_is_explicit_conflict():
    census = _census("a.py", "b.py")
    config = {
        "version": "1.0",
        "responsibilities": [
            {
                "id": "routing",
                "phase1_required": True,
                "status": "observed_authoritative",
                "claimants": [
                    {"path": "a.py", "role": "current_authority", "disposition": "online_authoritative", "agent_relevance": "direct", "evidence": "observed_runtime"},
                    {"path": "b.py", "role": "current_authority", "disposition": "online_authoritative", "agent_relevance": "direct", "evidence": "observed_runtime"},
                ],
                "finding": "Ambiguous authority",
            }
        ],
    }

    with pytest.raises(ValueError, match="multiple current authorities"):
        validate_responsibility_config(census, config)

    config["responsibilities"][0]["status"] = "unresolved_conflict"
    assert validate_responsibility_config(census, config)["valid"] is True


def test_phase0_relevant_claimants_must_have_explicit_non_unclassified_disposition():
    census = _census("app/kernel/agents/planner_runtime.py")
    config = {
        "version": "1.0",
        "responsibilities": [
            {
                "id": "planning",
                "phase1_required": False,
                "status": "observed_authoritative",
                "claimants": [
                    {"path": "app/kernel/agents/planner_runtime.py", "role": "current_authority", "disposition": "unclassified", "agent_relevance": "direct", "evidence": "observed_runtime"}
                ],
                "finding": "Planner",
            }
        ],
    }

    with pytest.raises(ValueError, match="coding-agent-relevant claimant remains unclassified"):
        validate_responsibility_config(census, config)


def test_markdown_exposes_authority_conflicts_and_evidence_boundaries():
    census = _census(
        "app/kernel/data_processing/context_packet.py",
        "desktop-ide/renderer/js/ai/context-picker.js",
        "app/kernel/agents/planner_runtime.py",
    )
    report = build_responsibility_report(census, _config())
    text = render_responsibility_markdown(report)

    assert "# BEAST Coding Agent Responsibility Census" in text
    assert "context_selection" in text
    assert "unresolved_conflict" in text
    assert "observed_runtime" in text
    assert "Phase 1 ownership conflicts" in text


def test_repo_responsibility_manifest_is_complete_against_canonical_census():
    root = Path(__file__).resolve().parents[1]
    census_path = root / "docs" / "evidence" / "BEAST_FULL_SYSTEM_CENSUS.json"
    config_path = root / "config" / "beast_coding_agent_responsibilities.json"

    assert config_path.exists(), "Phase 0 requires the real coding-agent responsibility manifest"

    census = json.loads(census_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation = validate_responsibility_config(census, config)
    report = build_responsibility_report(census, config)

    assert validation["valid"] is True
    assert validation["missing_paths"] == []
    assert report["summary"]["responsibility_count"] >= 24
    assert report["summary"]["claimant_count"] >= 70
    assert report["summary"]["unique_claimant_count"] >= 40
    assert report["summary"]["phase1_conflict_count"] >= 15
    assert report["summary"]["unresolved_conflict_count"] >= 10

    ids = {item["id"] for item in report["responsibilities"]}
    expected = {
        "model_output_protocol",
        "repository_context_selection",
        "context_budget_and_compaction",
        "governed_inference_routing",
        "verification_gate",
        "agent_memory_and_continuity",
        "sensorium_agent_observation",
        "verified_inference_reuse",
        "mission_edit_reuse_lattice",
        "crystal_generalization_promotion_and_replay",
        "crystal_transport_and_memfd_capsules",
        "task_input_governance",
        "planner_completion_decision",
    }
    assert expected <= ids

    planning = next(item for item in report["responsibilities"] if item["id"] == "runtime_planning")
    assert planning["status"] == "observed_authoritative"
    assert planning["current_authorities"] == ["app/kernel/agents/planner_runtime.py"]
    assert planning["claimants"][0]["evidence"] == "observed_runtime"

    transport = next(
        item for item in report["responsibilities"]
        if item["id"] == "crystal_transport_and_memfd_capsules"
    )
    assert transport["status"] == "dormant_or_stranded"
    assert "not ambient execution or confidentiality authority" in transport["finding"]
