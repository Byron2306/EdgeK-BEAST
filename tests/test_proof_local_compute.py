from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.networking.commons_spaces import package_tiny_llama_case
from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.networking.federated_commons import FederatedCommons
from app.kernel.compute.proof_local_compute import (
    ProofRoutePlanner,
    ProofRouteRequest,
    build_capability_advertisement,
    build_manifest_stage,
    build_verifier_stage,
    staged_transfer_receipt,
    validate_capability_advertisement,
    validate_manifest_stage,
    validate_receipt_packet,
    validate_verifier_stage,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"


def prepared(tmp_path, name="node"):
    registry = CommonsSpaceRegistry(tmp_path / name / "spaces")
    package_tiny_llama_case(CASE, registry.root / "tiny_llama_opus_gateway_repair")
    return registry, FederatedCommons(registry, tmp_path / name / "federation")


def test_receipt_packet_is_signed_private_payload_free_and_deduplicated(tmp_path):
    registry, source = prepared(tmp_path, "source")
    _, receiver = prepared(tmp_path, "receiver")
    packet = source.prepare_receipt_packet(
        "tiny_llama_opus_gateway_repair", contributor_id="node_source",
    )
    second_packet = source.prepare_receipt_packet(
        "tiny_llama_opus_gateway_repair", contributor_id="node_source",
    )
    validation = validate_receipt_packet(packet)
    encoded = str(packet)
    assert validation["valid"] is True
    assert "raw prompt" not in encoded.lower()
    assert "/home/" not in encoded
    assert packet["credit_eligible"] is False
    assert packet["bundle_sha256"] == second_packet["bundle_sha256"]
    assert packet["declared_bundle_bytes"] == second_packet["declared_bundle_bytes"]

    receiver.allow_contributor(
        "node_source", public_key_hash=packet["signature"]["public_key_hash"],
        approved=True, reason="known LAN node",
    )
    accepted = receiver.ingest_receipt_packet(packet)
    duplicate = receiver.ingest_receipt_packet(packet)
    assert accepted["state"] == "receipt_only_hypothesis"
    assert accepted["next_stage"] == "request_manifest"
    assert duplicate["duplicate"] is True
    assert receiver.state()["transfer_metrics"]["bytes_avoided"] > 0


def test_receipt_packet_tampering_aborts_before_bundle_transfer(tmp_path):
    _, source = prepared(tmp_path, "source")
    _, receiver = prepared(tmp_path, "receiver")
    packet = source.prepare_receipt_packet("tiny_llama_opus_gateway_repair", contributor_id="node_source")
    receiver.allow_contributor(
        "node_source", public_key_hash=packet["signature"]["public_key_hash"],
        approved=True, reason="known LAN node",
    )
    packet["manifest_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="validation failed"):
        receiver.ingest_receipt_packet(packet)
    metrics = receiver.state()["transfer_metrics"]
    assert metrics["early_rejections"] == 1
    assert metrics["full_bundles_avoided"] == 1


def test_manifest_and_verifier_stages_are_inert_and_bound_to_manifest(tmp_path):
    registry, _ = prepared(tmp_path)
    card = registry.public_space_card("tiny_llama_opus_gateway_repair")
    manifest = build_manifest_stage(card)
    verifiers = build_verifier_stage(card)
    assert validate_manifest_stage(manifest, expected_manifest_hash=card["manifest_hash"])["valid"]
    assert validate_verifier_stage(verifiers, expected_manifest_hash=card["manifest_hash"])["valid"]
    assert all(item["remote_execution_allowed"] is False for item in verifiers["verifiers"])
    manifest["manifest_hash"] = "sha256:" + "0" * 64
    assert not validate_manifest_stage(manifest, expected_manifest_hash=card["manifest_hash"])["valid"]


def test_signed_advertisement_routes_by_proof_privacy_rtt_and_verifier(tmp_path):
    _, source = prepared(tmp_path, "source")
    _, receiver = prepared(tmp_path, "receiver")
    advertisement = source.prepare_capability_advertisement(
        node_id="cpu_node_a", contributor_id="node_source",
        task_classes=["hard_gateway_repair"], verifier_classes=["schema_validation"],
        load_bucket="low", rtt_bucket_ms=10, max_transfer_bytes=6_000_000,
    )
    receiver.allow_contributor(
        "node_source", public_key_hash=advertisement["signature"]["public_key_hash"],
        approved=True, reason="known LAN node",
    )
    ingested = receiver.ingest_capability_advertisement(advertisement)
    request = ProofRouteRequest(
        task_class="hard_gateway_repair", required_verifiers=["schema_validation"],
        max_lan_rtt_ms=50, max_transfer_bytes=5_000_000,
    )
    plan = receiver.plan_proof_route(request)
    quarantine = ComputeGovernor().gate_proof_local_route(plan)
    allowed = ComputeGovernor().gate_proof_local_route(plan, local_replay_verified=True)
    assert ingested["state"] == "fresh_advisory_metadata"
    assert plan["decision"] == "trusted_lan_candidate"
    assert quarantine["decision"] == "quarantine_and_replay"
    assert quarantine["allowed"] is False
    assert allowed["decision"] == "trusted_lan_replay"
    assert allowed["allowed"] is True
    assert allowed["provider_execution_requested"] is False


def test_stale_or_privacy_mismatched_advertisement_degrades_to_fallback():
    now = datetime.now(timezone.utc)
    advertisement = build_capability_advertisement(
        node_id="node", contributor_id="node", capability_hashes=[],
        task_classes=["task"], verifier_classes=["schema"], engine_profiles=["ollama_cpu"],
        privacy_classes_accepted=["public_metadata_only"], load_bucket="idle",
        rtt_bucket_ms=5, max_transfer_bytes=100,
        issued_at=(now - timedelta(minutes=2)).isoformat(),
        expires_at=(now - timedelta(minutes=1)).isoformat(),
    )
    assert not validate_capability_advertisement(advertisement)["valid"]
    plan = ProofRoutePlanner().plan(
        ProofRouteRequest(task_class="task", privacy_class="local_only", max_transfer_bytes=50),
        [advertisement], now=now,
    )
    assert plan["decision"] == "fallback"
    assert plan["selected"] is None

    fresh = build_capability_advertisement(
        node_id="node", contributor_id="node", capability_hashes=[],
        task_classes=["task"], verifier_classes=["schema"], engine_profiles=["ollama_cpu"],
        privacy_classes_accepted=["public_metadata_only"], load_bucket="idle",
        rtt_bucket_ms=5, max_transfer_bytes=100,
        issued_at=now.isoformat(), expires_at=(now + timedelta(minutes=1)).isoformat(),
    )
    privacy_plan = ProofRoutePlanner().plan(
        ProofRouteRequest(task_class="task", privacy_class="local_only", max_transfer_bytes=50), [fresh], now=now,
    )
    peer_loss = ProofRoutePlanner().plan(ProofRouteRequest(task_class="task"), [], now=now)
    assert privacy_plan["decision"] == "fallback"
    assert "privacy_class_mismatch" in privacy_plan["rejected"][0]["reasons"]
    assert peer_loss["decision"] == "fallback"


def test_transfer_receipt_measures_negative_bandwidth_without_credit():
    receipt = staged_transfer_receipt(
        transfer_id="xfer", stage="manifest", accepted=True,
        reason="stopped", bytes_received=100, declared_artifact_bytes=1000,
    )
    assert receipt["bytes_avoided"] == 900
    assert receipt["full_bundle_avoided"] is True
    assert receipt["credit_eligible"] is False
