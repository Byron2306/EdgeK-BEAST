from __future__ import annotations

from scripts.run_beast_coding_agent_census_journeys import (
    render_runtime_map,
    run_analysis_journey,
    run_cross_file_mutation_journey,
    run_failed_verification_repair_journey,
    run_single_file_mutation_journey,
)


def _tool_ids(journey: dict) -> list[str]:
    return [item["tool_id"] for item in journey["tool_observations"]]


def test_analysis_journey_observes_planner_and_read_tools(tmp_path):
    journey = run_analysis_journey(tmp_path / "analysis")

    assert journey["final_state"] == "completed"
    assert journey["chain_verification"]["head_matches"] is True
    assert _tool_ids(journey) == ["workspace.search_text", "workspace.read_range"]
    assert "agent.planner.completed" in journey["event_types"]
    assert journey["evidence_class"] == "observed_production_backend_scripted_provider"


def test_single_file_mutation_journey_observes_full_governed_lifecycle(tmp_path):
    journey = run_single_file_mutation_journey(tmp_path / "single")

    assert journey["final_state"] == "completed"
    assert journey["chain_verification"]["head_matches"] is True
    tools = _tool_ids(journey)
    assert tools == [
        "workspace.index",
        "worktree.bind",
        "workspace.read_range",
        "worktree.replace_exact",
        "worktree.verify",
        "worktree.sourceplan_draft",
    ]
    assert journey["final_source"]["answer.py"] == "VALUE = 2\n"
    assert "agent.verification.passed" in journey["event_types"]


def test_cross_file_mutation_journey_observes_two_file_change(tmp_path):
    journey = run_cross_file_mutation_journey(tmp_path / "cross")

    assert journey["final_state"] == "completed"
    assert journey["chain_verification"]["head_matches"] is True
    tools = _tool_ids(journey)
    assert tools.count("workspace.read_range") >= 2
    assert tools.count("worktree.replace_exact") == 2
    assert journey["final_source"]["values.py"] == "VALUE = 2\n"
    assert "from values import VALUE\nRESULT = VALUE + 1\n" == journey["final_source"]["consumer.py"]


def test_failed_verification_repair_journey_records_failure_and_recovery(tmp_path):
    journey = run_failed_verification_repair_journey(tmp_path / "repair")

    assert journey["final_state"] == "completed"
    assert journey["chain_verification"]["head_matches"] is True
    assert "agent.verification.failed" in journey["event_types"]
    assert "agent.repair.required" in journey["event_types"]
    assert "agent.verification.passed" in journey["event_types"]
    assert _tool_ids(journey).count("worktree.replace_exact") == 2
    assert journey["final_source"]["answer.py"] == "VALUE = 2\n"


def test_runtime_map_keeps_harness_observation_separate_from_unproven_edges(tmp_path):
    journey = run_analysis_journey(tmp_path / "map")
    text = render_runtime_map([journey])

    assert "Observed production backend path (scripted provider)" in text
    assert "Desktop renderer / Pair Programmer ingress: **not proven by this harness**" in text
    assert "Real Ollama/NIM provider execution: **not proven by this harness**" in text
    assert "Sensorium mirror receipt: **not proven by AgentRun ledger events alone**" in text
    assert "app/kernel/agents/planner_runtime.py" in text
    assert "app/kernel/agents/tool_runtime.py" in text
