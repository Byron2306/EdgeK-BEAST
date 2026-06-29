from __future__ import annotations

from pathlib import Path

from app.kernel.registry.adapter_comparison import AdapterComparisonGauntlet, evaluate_proposal, extract_json
from app.kernel.compute.hardware_adapter_validation import HardwareAdapterValidator


def test_phase6_hardware_adapter_cards_are_cpu_gated(tmp_path: Path) -> None:
    report = HardwareAdapterValidator(output_root=tmp_path).validate(probe=False)
    assert report["status"] == "implemented"
    assert all(report["exit_criteria"].values())
    by_id = {item["adapter_id"]: item for item in report["cards"]}
    assert by_id["ollama"]["cpu_supported"] is True
    assert by_id["vllm"]["promotion_allowed"] is False
    assert by_id["nvidia_dynamo"]["authority"] == "metadata_only_not_authoritative"


def test_adapter_comparison_extracts_and_scores_beast_json() -> None:
    text = 'prefix {"beast_object_type":"adapter_assisted_local_proposal","task_family":"schema_validation","task_envelope":{"task_id":"x","task_family":"schema_validation"},"action_ir":{},"required_verifiers":["schema_validation"],"beast_systems_used":["task_envelope","compute_governor","local_verifiers"],"agent_awareness":{"must_use_beast_systems":true},"authority":"proposal_only"} suffix'
    parsed = extract_json(text)
    metrics = evaluate_proposal(parsed, {"task_family": "schema_validation", "required_verifier": "schema_validation"})
    assert metrics["raw_json_parse_rate"] == 1
    assert metrics["schema_validity"] is True
    assert metrics["hidden_verifier_pass"] is True


def test_adapter_comparison_malformed_system_entries_do_not_crash() -> None:
    parsed = {
        "beast_object_type": "adapter_assisted_local_proposal",
        "task_family": "schema_validation",
        "task_envelope": {"task_id": "x", "task_family": "schema_validation"},
        "action_ir": {},
        "required_verifiers": ["schema_validation"],
        "beast_systems_used": ["task_envelope", {"system": "compute_governor"}, "local_verifiers"],
        "agent_awareness": {"must_use_beast_systems": True},
        "authority": "proposal_only",
    }
    metrics = evaluate_proposal(parsed, {"task_family": "schema_validation", "required_verifier": "schema_validation"})
    assert metrics["malformed_system_entries"] == 1
    assert metrics["schema_validity"] is False
    assert metrics["hidden_verifier_pass"] is False


def test_heldout_adapter_comparison_offline_keeps_adapters_proposal_only(tmp_path: Path) -> None:
    report = AdapterComparisonGauntlet(output_root=tmp_path).run(live_ollama=False, run_loaded_lora=False)
    assert report["promotion_rule"]["adapter_can_execute"] is False
    assert report["summary"]["crystal_only_route"]["hidden_verifier_pass"] == 1
    assert report["promotion_verdict"]["crystal_only_route"]["promote_to_execution"] is False
    assert report["promotion_verdict"]["trained_beast_lora_adapter"]["promote_to_execution"] is False
    assert report["promotion_verdict"]["cloud_provider_route"]["promote_to_execution"] is False
    assert "not_run_live_ollama_disabled" in report["summary"]["baseline_qwen_05b"]["statuses"]
    assert "not_run_live_cloud_disabled" in report["summary"]["cloud_provider_route"]["statuses"]
    assert (tmp_path / "heldout_adapter_comparison_latest.json").is_file()
    assert (tmp_path / "heldout_adapter_comparison_offline_latest.json").is_file()
