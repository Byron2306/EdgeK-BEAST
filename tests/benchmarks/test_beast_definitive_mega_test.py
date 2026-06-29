import json
from pathlib import Path

import pytest

from benchmarks.beast_definitive_mega_test import (
    _cross_provider_reuse_case,
    _fingerprint_for_family,
    _load_resume_history,
    _mutation_ladder_cases,
    _mutation_recovery_case,
    build_reuse_evidence_plane_certification,
    build_report,
    main,
    seed_full_channel_reuse_plane_smoke,
)
from benchmarks.tiny_llama_crystal_amplification_gauntlet import build_report as build_tiny_llama_report
from benchmarks.tiny_llama_agentic_orchestrator_gauntlet import (
    build_report as build_tiny_llama_agentic_report,
    normalize_live_response,
    score_live_response,
)
from benchmarks.tiny_llama_live_e2e_orchestration_gauntlet import swarm_orchestrated_or_gated
from benchmarks.tiny_llama_opus_case_study_gauntlet import (
    apply_approved_patch,
    prepare_case_repo,
    run_case_tests,
)
from app.kernel.networking.meta_tool_commons import MetaToolCommons
from benchmarks.mega_test_metrics import compute_qpccd
from benchmarks.mega_test_tasks import build_observation_plan, expected_controlled_observations


class Args:
    mode = "controlled"
    route_set = "default"
    providers = "nvidia_nim,gemini,groq,cerebras,cloudflare"
    families = "schema_validation,provider_alias_normalization,patch_compilation,syntax_check,route_diagnostics,secret_redaction"
    occurrences = "1,2,3,5,10"
    lanes = "raw,beast_no_compute_governor,full_beast_compute_governor"
    live = False
    dry_run = True
    batch_size = 0
    batch_index = 0
    skip_crystal_phases = False
    reuse_plane_smoke = False


def test_default_matrix_has_450_lane_observations():
    rows = build_observation_plan()

    assert len(rows) == 450
    assert expected_controlled_observations() == 450
    assert rows[0].lane == "raw"
    assert rows[-1].occurrence == 10


def test_qpccd_counts_only_quality_preserving_call_displacement():
    observations = [
        {"family": "schema_validation", "provider": "nvidia_nim", "occurrence": 1, "lane": "beast_no_compute_governor", "completed": True, "hidden_passed": True, "cloud_calls": 1},
        {"family": "schema_validation", "provider": "nvidia_nim", "occurrence": 1, "lane": "full_beast_compute_governor", "completed": True, "hidden_passed": True, "cloud_calls": 0},
        {"family": "secret_redaction", "provider": "nvidia_nim", "occurrence": 1, "lane": "beast_no_compute_governor", "completed": True, "hidden_passed": True, "cloud_calls": 1},
        {"family": "secret_redaction", "provider": "nvidia_nim", "occurrence": 1, "lane": "full_beast_compute_governor", "completed": True, "hidden_passed": False, "cloud_calls": 0},
    ]

    result = compute_qpccd(observations)

    assert result["numerator"] == 1
    assert result["denominator"] == 2
    assert result["rate"] == 0.5


def test_dry_run_report_has_manifest_without_secret_values(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "super-secret")

    report = build_report(Args())

    manifest = report["provider_manifest"]["nvidia_nim"]
    assert report["plan_summary"]["observations"] == 450
    assert manifest["secret_present"] is True
    assert "super-secret" not in json.dumps(report)


def test_runner_writes_dry_run_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmarks.beast_definitive_mega_test.RESULTS", tmp_path)

    rc = main(["--dry-run", "--output", "mega_test_unit"])

    output = tmp_path / "mega_test_unit"
    assert rc == 0
    assert (output / "README.md").exists()
    assert (output / "run_manifest.json").exists()
    assert (output / "reuse_evidence_plane.json").exists()
    assert (output / "reuse_evidence_plane.md").exists()
    assert (output / "evidence_cards" / "reuse_evidence_plane_receipt.json").exists()
    assert (output / "stagger_plan.json").exists()
    assert (output / "controlled_observations.jsonl").exists()
    assert (tmp_path / "mega_test_unit.zip").exists()
    assert sum(1 for _ in (output / "controlled_observations.jsonl").open()) == 450
    reuse = json.loads((output / "reuse_evidence_plane.json").read_text())
    assert reuse["beast_object_type"] == "mega_reuse_evidence_plane_certification"
    assert reuse["passed"] is True
    assert reuse["assertions"]["privacy_scan_passed"] is True
    assert all(item["status"] in {"present", "absent_expected"} for item in reuse["channels"])
    assert (output / "reuse_evidence_plane_smoke.json").exists()


def test_reuse_evidence_plane_certification_counts_seeded_channels(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    commons.ingest_kv_cache_evidence(
        {
            "total_blocks": 1,
            "operations_logged": 4,
            "total_size_bytes": 2048,
            "blocks_by_engine": {"vllm": 1},
            "blocks_by_location": {"network": 1},
        },
        {
            "adapter": "LocalKVEngineAdapter",
            "engine": "vllm",
            "looked_up": True,
            "payload_round_tripped": True,
            "created_at": "2026-06-21T00:00:00Z",
        },
    )

    certification = build_reuse_evidence_plane_certification({"mode": "controlled", "live": False}, commons=commons)

    assert certification["passed"] is True
    assert certification["plane_hash"].startswith("sha256:")
    assert certification["assertions"]["active_channel_count"] == 4
    by_channel = {item["channel"]: item for item in certification["channels"]}
    assert by_channel["kv_cache"]["status"] == "present"
    assert by_channel["swarm"]["status"] == "present"
    assert by_channel["cli"]["status"] == "present"
    assert by_channel["ollama"]["status"] == "present"


def test_full_channel_reuse_plane_smoke_populates_all_channels(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))

    smoke = seed_full_channel_reuse_plane_smoke(commons)
    certification = build_reuse_evidence_plane_certification(
        {"mode": "controlled", "live": False, "reuse_evidence_plane_smoke": smoke},
        commons=commons,
    )

    assert smoke["passed"] is True
    assert set(smoke["seeded_channels"]) == {"swarm", "cli", "ollama", "kv_cache"}
    assert certification["passed"] is True
    assert certification["assertions"]["active_channel_count"] == 4
    assert {item["channel"]: item["status"] for item in certification["channels"]} == {
        "swarm": "present",
        "cli": "present",
        "ollama": "present",
        "kv_cache": "present",
    }


def test_build_report_reuse_plane_smoke_uses_full_channel_certification():
    args = type("SmokeArgs", (), {
        "mode": "controlled",
        "route_set": "default",
        "providers": "nvidia_nim",
        "families": "schema_validation",
        "occurrences": "1",
        "lanes": "raw,beast_no_compute_governor,full_beast_compute_governor",
        "live": False,
        "dry_run": True,
        "batch_size": 0,
        "batch_index": 0,
        "skip_crystal_phases": True,
        "reuse_plane_smoke": True,
    })()

    report = build_report(args)

    assert report["reuse_evidence_plane_smoke"]["passed"] is True
    assert report["reuse_evidence_plane_certification"]["assertions"]["active_channel_count"] == 4
    assert report["acceptance_status"]["reuse_evidence_plane_full_channel_smoke_passed"] is True
    assert report["acceptance_status"]["reuse_evidence_plane_active_channels"] == 4


def test_batching_selects_deterministic_stagger_slice():
    args = type("BatchArgs", (), {
        "mode": "controlled",
        "route_set": "default",
        "providers": "nvidia_nim,gemini",
        "families": "schema_validation,secret_redaction",
        "occurrences": "1,2",
        "lanes": "raw,beast_no_compute_governor,full_beast_compute_governor",
        "live": False,
        "batch_size": 5,
        "batch_index": 1,
    })()

    report = build_report(args)

    assert report["full_plan_summary"]["observations"] == 24
    assert report["plan_summary"]["observations"] == 5
    assert report["batch"]["batch_index"] == 1
    assert report["batch"]["start"] == 5
    assert report["batch"]["end"] == 10
    assert len(report["stagger_plan"]) == 5


def test_first_live_route_set_uses_requested_providers():
    args = type("RouteArgs", (), {
        "mode": "controlled",
        "route_set": "first-live",
        "providers": None,
        "families": "schema_validation",
        "occurrences": "1",
        "lanes": "raw,beast_no_compute_governor,full_beast_compute_governor",
        "live": False,
        "batch_size": 0,
        "batch_index": 0,
    })()

    report = build_report(args)

    assert report["route_set"] == "first-live"
    assert report["providers"] == ["nvidia_nim", "mistral", "gemini", "cohere", "groq"]
    assert report["plan_summary"]["observations"] == 15


def test_live_mode_enriches_selected_mega_observations(monkeypatch):
    def fake_execute(args, observations):
        enriched = []
        for row in observations:
            enriched.append({
                **row,
                "status": "completed",
                "completed": True,
                "hidden_passed": True,
                "cloud_calls": 1,
                "source_live_task": "output_governance_malformed_json",
            })
        return {
            "occurrence": 1,
            "providers": ["nvidia_nim"],
            "families": ["schema_validation"],
            "lanes": ["raw", "beast_no_compute_governor", "full_beast_compute_governor"],
            "live_lanes": ["raw", "schema_only", "full_beast"],
            "raw_live_result_count": len(enriched),
            "provider_reports": {},
            "controlled_observations": enriched,
        }

    monkeypatch.setattr("benchmarks.beast_definitive_mega_test.execute_live_observations", fake_execute)

    report = build_report(type("LiveArgs", (), {
        "mode": "controlled",
        "route_set": "default",
        "providers": "nvidia_nim",
        "families": "schema_validation",
        "occurrences": "1",
        "lanes": "raw,beast_no_compute_governor,full_beast_compute_governor",
        "live": True,
        "batch_size": 0,
        "batch_index": 0,
        "live_max_tokens": 1200,
        "live_prompt_mode": "compact",
        "live_json_mode": False,
    })())

    assert report["acceptance_status"]["live_verified"] is True
    assert report["plan_summary"]["observations"] == 3
    assert all(row["status"] == "completed" for row in report["controlled_observations"])


def test_runner_writes_compute_governor_receipts_for_crystallized_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmarks.beast_definitive_mega_test.RESULTS", tmp_path)

    receipt = {
        "beast_object_type": "mega_compute_governor_receipt",
        "version": "1.0",
        "receipt_id": "mega_cg_unit",
        "provider": "nvidia_nim",
        "family": "schema_validation",
        "occurrence": 3,
        "lane": "full_beast_compute_governor",
        "task_id": "schema_validation_o03_v1",
        "source_occurrences": [1, 2],
        "source_task_ids": ["schema_validation_o01_v1", "schema_validation_o02_v1"],
        "decision": "deterministic_reuse",
        "provider_execution_requested": False,
        "cloud_calls": 0,
        "visible_passed": True,
        "hidden_passed": True,
        "rollback_success": True,
        "false_reuse_warning": False,
        "impact_fingerprint_hash": "sha256:unit",
        "semantic_credit_id": "pending",
        "avoided_tokens_estimate": 432,
        "policy_version": "mega_controlled_v1",
        "created_at": "2026-06-21T00:00:00Z",
    }

    def fake_execute(args, observations):
        rows = []
        for row in observations:
            completed = row["lane"] == "full_beast_compute_governor"
            rows.append({
                **row,
                "status": "completed" if completed else "failed",
                "completed": completed,
                "visible_passed": completed,
                "hidden_passed": completed,
                "cloud_calls": 0 if completed else 1,
                "crystallized": completed,
                "deterministic_reuse": completed,
                "artifact_refs": {"receipt": "compute_governor_receipts/mega_cg_unit.json"} if completed else {},
            })
        return {
            "occurrences": [3],
            "providers": ["nvidia_nim"],
            "families": ["schema_validation"],
            "lanes": ["raw", "beast_no_compute_governor", "full_beast_compute_governor"],
            "live_lanes": ["raw", "schema_only", "full_beast"],
            "raw_live_result_count": 2,
            "provider_reports": {},
            "compute_governor_receipts": [receipt],
            "crystallization_events": [{
                "receipt_id": "mega_cg_unit",
                "provider": "nvidia_nim",
                "family": "schema_validation",
                "occurrence": 3,
                "state": "crystallized",
            }],
            "controlled_observations": rows,
        }

    monkeypatch.setattr("benchmarks.beast_definitive_mega_test.execute_live_observations", fake_execute)

    rc = main([
        "--live",
        "--providers", "nvidia_nim",
        "--families", "schema_validation",
        "--occurrences", "3",
        "--output", "mega_receipt_unit",
    ])

    output = tmp_path / "mega_receipt_unit"
    assert rc == 0
    assert (output / "compute_governor_receipts" / "mega_cg_unit.json").exists()
    stored = json.loads((output / "compute_governor_receipts" / "mega_cg_unit.json").read_text())
    assert stored["semantic_credit_id"].startswith("scc_")
    credit_path = output / "compute_governor_receipts" / "semantic_credits" / f"{stored['semantic_credit_id']}.json"
    assert credit_path.exists()
    assert json.loads(credit_path.read_text())["avoided_tokens_estimate"] == 432
    assert sum(1 for _ in (output / "crystallization_events.jsonl").open()) == 1


def test_mega_fingerprint_contains_real_target_test_and_tool_material():
    fingerprint = _fingerprint_for_family("schema_validation", 3)

    assert fingerprint["targets"]["app/output_guard.py"]["exists"] is True
    assert fingerprint["targets"]["app/output_guard.py"]["file_hash"].startswith("sha256:")
    assert fingerprint["targets"]["app/output_guard.py"]["semantic_hash"].startswith("sha256:")
    assert fingerprint["targets"]["app/output_guard.py"]["symbol_hashes"]
    assert fingerprint["tests"]["tests/test_output_guard_public.py"]["exists"] is True
    assert fingerprint["tests"]["tests/test_output_guard_hidden.py"]["exists"] is True
    assert fingerprint["tool_schema_hashes"][0].startswith("sha256:")
    assert fingerprint["policy_version"] == "mega_controlled_v1"


def test_occurrence_10_mutation_blocks_reuse_and_recovers():
    previous = _fingerprint_for_family("schema_validation", 5)

    case = _mutation_recovery_case("schema_validation", "nvidia_nim", previous)

    assert case["reuse_blocked"] is True
    assert case["demotion_state"] == "shadow_revalidation"
    assert case["recovered_reusable"] is True
    assert case["false_reuse_warning"] is False
    assert case["fingerprint_before"]["targets"]["app/output_guard.py"]["exists"] is True
    assert case["fingerprint_after"]["fingerprint_hash"] != case["fingerprint_before"]["fingerprint_hash"]
    assert case["fingerprint_recovered"]["fingerprint_hash"] == case["fingerprint_before"]["fingerprint_hash"]
    assert "state" not in case["fingerprint_after"]
    assert "reusable" not in case["fingerprint_after"]
    assert case["reuse_decision"] == {
        "state": "shadow_revalidation",
        "reusable": False,
        "demotion_reasons": case["demotion_reasons"],
        "material_drift_made_reuse_unavailable": True,
    }


def test_cross_provider_case_has_publication_critical_outcome_fields():
    fingerprint = _fingerprint_for_family("schema_validation", 3)

    case = _cross_provider_reuse_case(
        "schema_validation", 3, "nvidia_nim", "mistral", fingerprint, fingerprint
    )

    assert case["active_provider"] == "mistral"
    assert case["provider_execution_requested"] is False
    assert case["visible_passed"] is True
    assert case["hidden_passed"] is True
    assert case["completed"] is True
    assert case["behavior_preserved"] is True
    assert case["incorrect_reuse"] is False


def test_mutation_ladder_has_explicit_a_through_d_policy():
    cases = _mutation_ladder_cases("schema_validation", "nvidia_nim")
    by_tier = {case["tier"]: case for case in cases}

    assert set(by_tier) == {"A", "B", "C", "D"}
    assert by_tier["A"]["reuse_decision"]["state"] == "active"
    assert by_tier["A"]["reuse_decision"]["reusable"] is True
    assert by_tier["B"]["reuse_decision"]["state"] == "shadow_revalidation"
    assert by_tier["B"]["reuse_decision"]["reusable"] is False
    assert by_tier["C"]["reuse_decision"]["state"] == "shadow_revalidation"
    assert by_tier["C"]["reuse_decision"]["reusable"] is False
    assert by_tier["D"]["reuse_decision"]["state"] == "demoted"
    assert by_tier["D"]["reuse_decision"]["reusable"] is False
    assert by_tier["D"]["cloud_or_human_escalation_required"] is True


def test_resume_history_restores_active_crystallized_fingerprint(tmp_path):
    artifact = tmp_path / "prior"
    artifact.mkdir()
    rows = [{
        "provider": "nvidia_nim",
        "family": "schema_validation",
        "occurrence": 5,
        "lane": "full_beast_compute_governor",
        "deterministic_reuse": True,
        "completed": True,
    }]
    (artifact / "live_execution.json").write_text(json.dumps({"controlled_observations": rows}))

    observations, lane_c, active, source = _load_resume_history(str(artifact))

    assert len(observations) == 1
    assert lane_c[("nvidia_nim", "schema_validation")][5]["completed"] is True
    fingerprint = active[("nvidia_nim", "schema_validation")]
    assert fingerprint["targets"]["app/output_guard.py"]["exists"] is True
    assert source == str((artifact / "live_execution.json").resolve())


def test_tiny_llama_crystal_amplification_gauntlet_is_defensive(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("def handle(payload):\n    return payload\n")
    args = type("TinyArgs", (), {
        "repo": str(repo),
        "node_id": "jetson_unit",
        "node_type": "jetson",
        "tiny_model": "llama3.2:1b",
        "teacher_model": "nvidia_nim_reference",
        "big_model": "opus_reference",
        "crystals": 4,
    })()

    report = build_tiny_llama_report(args)

    assert report["passed"] is True
    assert report["assertions"]["defensive_only"] is True
    assert report["assertions"]["offensive_payloads_absent"] is True
    assert report["amplification_pack"]["crystal_count"] == 4
    assert report["comparison"]["tiny_gain_over_raw"] > 0


def test_tiny_llama_agentic_orchestrator_gauntlet_externalizes_reasoning(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    args = type("AgenticArgs", (), {
        "repo": str(repo),
        "tiny_model": "llama3.2:1b",
        "preflight_budget_ms": 750,
        "scout_budget_ms": 400,
    })()

    report = build_tiny_llama_agentic_report(args)

    assert report["passed"] is True
    assert report["summary"]["reasoning_externalized"] is True
    assert report["summary"]["beast_aware_tiny_avg_score"] > report["summary"]["raw_tiny_avg_score"]
    assert report["session_handshake"]["agent_awareness"]["tiny_model_role"] == "intent_router_policy_summarizer"
    assert all(row["beast_aware_tiny"]["passed"] for row in report["tasks"])


def test_tiny_llama_live_schema_repair_turns_weak_json_into_orchestration_contract():
    task = {
        "task_id": "unsafe_shell_request",
        "task_class": "command_planning",
        "required_route": ["mcp_shell_dry_run", "zeroclaw", "approval_gate"],
        "required_gates": ["no_autonomous_execution", "human_approval_required"],
        "required_subagents": ["zeroclaw_planner", "supervisor"],
        "risk": "high",
    }
    weak_model_json = {
        "required_route": task["required_route"],
        "required_gates": task["required_gates"],
        "required_subagents": task["required_subagents"],
        "task_class": "command_planning",
    }

    repaired = normalize_live_response(weak_model_json)

    assert repaired["route"] == task["required_route"]
    assert repaired["gates"] == task["required_gates"]
    assert repaired["subagents"] == task["required_subagents"]
    assert repaired["needs_cloud"] is False
    assert score_live_response(task, repaired) >= 0.9


def test_tiny_llama_e2e_accepts_governed_swarm_approval_gate():
    swarm_result = {
        "status": "approval_required",
        "gates": [{"decision": "approval_required", "name": "openclaw_read_only_boundary"}],
        "events": [
            {"role": "hermes"},
            {"role": "conductor"},
            {"role": "sentinel"},
            {"role": "supervisor"},
        ],
    }

    assert swarm_orchestrated_or_gated(swarm_result) is True


def test_tiny_llama_opus_case_patch_requires_approval_and_passes(tmp_path):
    case_root = tmp_path / "case_repo"
    prepare_case_repo(case_root)

    baseline = run_case_tests(case_root, timeout=30)
    denied = apply_approved_patch(case_root, approved=False)
    applied = apply_approved_patch(case_root, approved=True)
    verification = run_case_tests(case_root, timeout=30)

    assert baseline["returncode"] != 0
    assert denied["applied"] is False
    assert applied["applied"] is True
    assert applied["patch_hash"].startswith("sha256:")
    assert verification["returncode"] == 0
