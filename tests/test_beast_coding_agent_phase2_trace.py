from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.beast_coding_agent_phase2_trace import build_phase2_trace
from scripts.run_beast_coding_agent_census_journeys import run_analysis_journey, run_cross_file_mutation_journey


def test_observed_backend_trace_keeps_unproven_edges_explicit(tmp_path):
    analysis = run_analysis_journey(tmp_path / "analysis")
    cross = run_cross_file_mutation_journey(tmp_path / "cross")
    report = build_phase2_trace([analysis, cross])

    assert report["journeys"][0]["chain_head"] == analysis["chain_verification"]["head_hash"]
    assert report["journeys"][0]["observation_sequence"]
    assert all(step["evidence_ref"].startswith("agent_run:") for step in report["journeys"][0]["observation_sequence"])
    assert report["edges"]["backend_planner_and_tools"]["state"] == "observed_scripted_provider"
    for edge in ("desktop_ingress", "real_model_provider", "sensorium_delivery", "remote_dispatch_return"):
        assert report["edges"][edge]["state"] == "unverified"
    assert report["journeys"][1]["objective_assessment"]["satisfied"] is True
    assert report["journeys"][1]["objective_assessment"]["unresolved_paths"] == []


def test_missing_chain_proof_or_unsupported_provider_claim_fails_closed(tmp_path):
    journey = run_analysis_journey(tmp_path / "analysis")
    broken = deepcopy(journey)
    broken["chain_verification"]["head_matches"] = False
    with pytest.raises(ValueError, match="chain"):
        build_phase2_trace([broken])

    broken = deepcopy(journey)
    broken["proof_boundaries"]["real_ollama_or_nim_provider"] = True
    with pytest.raises(ValueError, match="independent receipt"):
        build_phase2_trace([broken])


def test_tampered_observation_or_raw_event_cannot_inherit_chain_proof(tmp_path):
    journey = run_analysis_journey(tmp_path / "analysis")
    broken = deepcopy(journey)
    original_ref = str(broken["trace_records"][0]["evidence_ref"])
    replacement = "0" if not original_ref.endswith("0") else "1"
    broken["trace_records"][0]["evidence_ref"] = original_ref[:-1] + replacement
    assert broken["trace_records"][0]["evidence_ref"] != original_ref
    with pytest.raises(ValueError, match="event hash"):
        build_phase2_trace([broken])

    broken = deepcopy(journey)
    broken["event_chain"][0]["payload"] = {"tampered": True}
    with pytest.raises(ValueError, match="hash mismatch"):
        build_phase2_trace([broken])
