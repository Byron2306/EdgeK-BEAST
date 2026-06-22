import json
import shutil
from pathlib import Path

import pytest

from app.kernel.commons_policy import CommonsPolicyLearner
from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.commons_spaces import package_tiny_llama_case


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"


def prepared_registry(tmp_path):
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    package_tiny_llama_case(CASE, registry.root / "tiny_llama_opus_gateway_repair")
    return registry


def test_registry_lists_scores_and_details_local_spaces(tmp_path):
    registry = prepared_registry(tmp_path)

    listed = registry.list_spaces()
    detail = registry.get("tiny_llama_opus_gateway_repair")

    assert listed["count"] == 1
    assert listed["scoreboard"]["verified_spaces"] == 1
    assert listed["artifact_sources"]["artifact_types"]["orchestration_plan"] == 1
    assert detail["manifest_validation"]["valid"] is True
    assert detail["receipt_validation"]["valid"] is True
    assert listed["spaces"][0]["adoption_state"] == "quarantined_hypothesis"


def test_public_registry_projects_cloud_safe_hypothesis_cards(tmp_path):
    registry = prepared_registry(tmp_path)
    registry.replay("tiny_llama_opus_gateway_repair")

    public = registry.public_registry()
    card = registry.public_space_card("tiny_llama_opus_gateway_repair")
    encoded = json.dumps(card)

    assert public["authority"] == "public_hypothesis_catalog"
    assert public["primary_action"] == "import_as_quarantined_hypothesis"
    assert card["authority"] == "advisory_remote_hypothesis"
    assert card["risk_approval"]["adoption_state"] == "reproduced"
    assert card["local_adoption_engine"]["required"] is True
    assert card["manifest"]["artifacts"][0]["sha256"].startswith("sha256:")
    assert "artifact_payload_bytes" in card["excluded_from_public_card"]
    assert "opus_case_report" not in encoded
    assert "/home/" not in encoded


def test_scale_readiness_names_unknowns_and_next_actions(tmp_path):
    registry = prepared_registry(tmp_path)

    readiness = registry.scale_readiness()

    assert readiness["corpus"]["spaces"] == 1
    assert readiness["latency_interpretation"]["comparison"] == "broken_vs_working"
    assert "case_study_scale" in readiness["unknowns"]
    assert readiness["milestones"][0]["target"] == 10
    assert "federate_signed_manifests_between_two_allowlisted_nodes" in readiness["next_actions"]


def test_registration_candidates_discovers_benchmark_result_folders(tmp_path):
    registry = prepared_registry(tmp_path)

    candidates = registry.registration_candidates(limit=5)

    assert candidates["beast_object_type"] == "commons_registration_candidates"
    assert candidates["count"] >= 1
    assert candidates["registration_pipeline"][0] == "discover_candidate_artifacts"
    assert all("registration_score" in item for item in candidates["candidates"])


def test_registry_root_can_be_isolated_by_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_COMMONS_ROOT", str(tmp_path / "node_root"))
    registry = CommonsSpaceRegistry()

    assert registry.root == (tmp_path / "node_root").resolve()


def test_registry_exports_and_imports_untrusted_bundle_after_verification(tmp_path):
    source = prepared_registry(tmp_path / "source")
    exported = source.export_bundle("tiny_llama_opus_gateway_repair")
    target = CommonsSpaceRegistry(tmp_path / "target" / "spaces")

    preview = target.import_untrusted_bundle(Path(exported["path"]), approved=False, dry_run=True)
    imported = target.import_untrusted_bundle(Path(exported["path"]), approved=True, dry_run=False)

    assert preview["imported"] is False
    assert preview["bundle_validation"]["entries_valid"] is True
    assert imported["imported"] is True
    assert target.get("tiny_llama_opus_gateway_repair")["manifest_validation"]["valid"] is True


def test_adoption_requires_approval_reason_and_records_only_references(tmp_path):
    registry = prepared_registry(tmp_path)

    preview = registry.adopt("tiny_llama_opus_gateway_repair", approved=False, dry_run=False)
    assert preview["adopted"] is False
    assert preview["status"] == "approval_required"

    with pytest.raises(ValueError, match="reason"):
        registry.adopt("tiny_llama_opus_gateway_repair", approved=True, dry_run=False)

    adopted = registry.adopt(
        "tiny_llama_opus_gateway_repair",
        artifact_paths=["normalized_orchestration_plan.json"],
        approved=True,
        dry_run=False,
        approved_by="test",
        reason="verified local case",
    )
    assert adopted["adopted"] is True
    assert adopted["artifact_references"][0]["sha256"].startswith("sha256:")
    stored = json.loads(Path(adopted["receipt_path"]).read_text(encoding="utf-8"))
    assert "raw_response" not in json.dumps(stored)


def test_policy_extracts_labels_trains_and_recommends_in_shadow(tmp_path):
    learner = CommonsPolicyLearner(prepared_registry(tmp_path))

    dataset = learner.extract_examples()
    model = learner.train(dataset["examples"])
    recommendation = learner.recommend({
        "task_class": "hard_gateway_repair",
        "risk": "high",
        "gpu_available": False,
        "approval_required": True,
    }, model)
    evaluation = learner.evaluate(dataset["examples"])

    assert dataset["count"] == 1
    assert "pytest" in dataset["examples"][0]["labels"]["tools"]
    assert model["model_type"] == "tiny_hashed_linear_ranker"
    assert recommendation["mode"] == "shadow"
    assert recommendation["enforcing"] is False
    assert recommendation["recommendation"]["route"] == "tiny_local_model_beast_orchestration"
    assert recommendation["verification_projection"]["would_preserve_verification"] is True
    assert evaluation["protocol"] == "in_sample_insufficient_for_holdout"
