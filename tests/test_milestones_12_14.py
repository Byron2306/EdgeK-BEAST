import time
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.proof_carrying_artifact import ProofArtifactAdmission, CommonsFederation
from app.kernel.compute.displacement_economics import DisplacementEconomics, PairedOccurrence, WorkMeasurement


def measurement(route: str, calls: int, tokens: int, latency: float, *, state: str = "state:1") -> WorkMeasurement:
    return WorkMeasurement(route, calls, tokens, latency, cpu_ms=8 if route == "local" else 2,
        memory_byte_ms=1024, io_bytes=64, sensing_ms=1 if route == "local" else 0,
        applicability_ms=1 if route == "local" else 0, authorization_ms=1 if route == "local" else 0,
        replay_ms=2 if route == "local" else 0, verification_ms=1, provider_cost_usd=.02 if calls else 0,
        postcondition_digest="post:equal", verifier_digest="verifier:1", policy_generation="policy:1",
        initial_state_digest=state, task_digest="task:1")


def economics(node_id=None):
    return DisplacementEconomics.evaluate([
        PairedOccurrence("o1", measurement("provider", 1, 900, 100), measurement("local", 0, 0, 20)),
        PairedOccurrence("o2", measurement("provider", 1, 1000, 110), measurement("local", 0, 0, 22), mutation_invalidated=True),
        PairedOccurrence("negative", measurement("provider", 1, 800, 90),
                         replace(measurement("local", 0, 0, 18), postcondition_digest="post:wrong"), false_hit=True),
    ], setup_cost_usd=.01, setup_latency_ms=5,
        measurement_scope={"node_id": node_id, "origin": "node_local"} if node_id else None)


def bundle(receipt):
    return {
        "crystal": {"identity": "crystal:1", "digest": "sha256:" + "a" * 64},
        "opcode_catalog": [{"name": "render", "version": "1"}],
        "applicability_contract": {"parameters": ["workspace_identity"]},
        "negative_boundaries": ["stale_manifest", "policy_mismatch"],
        "replay_corpus_summary": {"heldout": 4, "raw_events": False},
        "displacement_receipt": receipt,
        "provenance": {"contributor": "contributor:projected"},
        "privacy_projection": {"raw_sensitive_events_exported": False, "ambient_authority_exported": False},
        "policy_attestation_requirements": {"policy_generation": "policy:1", "attestation": "fresh"},
        "decay_rules": {"ttl_seconds": 3600, "demote_on_false_hit": True},
    }


def test_m12_paired_economics_counts_avoided_and_moved_work():
    receipt = economics()
    DisplacementEconomics.validate(receipt)
    assert receipt["provider_calls_avoided"] == 2
    assert receipt["provider_tokens_avoided"] == 1900
    assert receipt["work_moved_locally"]["cpu_ms"] == 16
    assert receipt["impact_feedback"]["false_hits"] == 1
    assert receipt["mutation_invalidation"]["tested"] is True
    assert receipt["break_even_occurrences_cost"] == 1
    assert receipt["confidence_intervals"]["calls_per_occurrence"]["low"] == 1


def test_m12_refuses_zero_call_receipt_and_binding_mismatch():
    receipt = economics(); receipt["provider_calls_avoided"] = 0
    with pytest.raises(ValueError, match="tampered"):
        DisplacementEconomics.validate(receipt)
    bad = PairedOccurrence("bad", measurement("provider", 1, 1, 4), measurement("local", 0, 0, 2, state="state:2"))
    with pytest.raises(PermissionError, match="no behaviorally equivalent"):
        DisplacementEconomics.evaluate([bad, bad])


def test_m13_admits_signed_private_projection_under_verify_only_authority(tmp_path):
    signer = Ed25519PrivateKey.generate()
    admission = ProofArtifactAdmission(tmp_path, signer,
        arda_appraiser=lambda manifest: {"allowed": True, "appraisal_ref": "arda:1"}).admit(
            bundle(economics()), space_id="space:proof", explicit_space_admission=True)
    assert admission.authority == "remote_hypothesis"
    assert admission.maximum_authority == "verify_only"
    assert admission.artifact_digest.startswith("sha256:")
    assert admission.chunk_digests


def test_m13_rejects_ambient_authority_and_host_identity(tmp_path):
    value = bundle(economics()); value["live_descriptors"] = {"workspace_root": "/home/alice/private"}
    admission = ProofArtifactAdmission(tmp_path, Ed25519PrivateKey.generate(),
        arda_appraiser=lambda manifest: {"allowed": True, "appraisal_ref": "arda:1"})
    with pytest.raises(PermissionError, match="privacy"):
        admission.admit(value, space_id="space:proof", explicit_space_admission=True)


def test_m14_local_reproduction_sovereignty_and_verified_aggregation(tmp_path):
    admission = ProofArtifactAdmission(tmp_path / "source", Ed25519PrivateKey.generate(),
        arda_appraiser=lambda manifest: {"allowed": True, "appraisal_ref": "arda:1"}).admit(
            bundle(economics()), space_id="space:proof", explicit_space_admission=True)
    federation = CommonsFederation()
    receipt = federation.reproduce(admission, node_id="node:1", contributor_id="contributor:1",
        node_attestation={"verified": True, "expires_at": time.time() + 60},
        local_context={"policy_generation": "policy:1", "verifier_digest": "verifier:1"},
        heldout_results=[{"verified": True, "negative_boundary_preserved": True}],
        displacement_receipt=economics("node:1"), expected_verifier_digest="verifier:1",
        expected_policy_generation="policy:1")
    assert receipt["authority"]["execution"] == "node_local"
    assert federation.aggregate_verified_displacement()["provider_calls_avoided"] == 2
    federation.revoke_contributor("contributor:1", reason="key compromise")
    assert federation.aggregate_verified_displacement()["provider_calls_avoided"] == 0


def test_m14_rejects_malicious_manifest(tmp_path):
    admission = ProofArtifactAdmission(tmp_path, Ed25519PrivateKey.generate(),
        arda_appraiser=lambda manifest: {"allowed": True, "appraisal_ref": "arda:1"}).admit(
            bundle(economics()), space_id="space:proof", explicit_space_admission=True)
    with pytest.raises(PermissionError, match="malicious"):
        CommonsFederation().reproduce(replace(admission, artifact_digest="sha256:evil"),
            node_id="node:1", contributor_id="contributor:1",
            node_attestation={"verified": True, "expires_at": time.time() + 60},
            local_context={"policy_generation": "policy:1", "verifier_digest": "verifier:1"},
            heldout_results=[{"verified": True, "negative_boundary_preserved": True}],
            displacement_receipt=economics("node:1"), expected_verifier_digest="verifier:1",
            expected_policy_generation="policy:1")
    with pytest.raises(PermissionError, match="signature"):
        CommonsFederation().reproduce(replace(admission, signature=admission.signature[:-4] + "AAAA"),
            node_id="node:1", contributor_id="contributor:1",
            node_attestation={"verified": True, "expires_at": time.time() + 60},
            local_context={"policy_generation": "policy:1", "verifier_digest": "verifier:1"},
            heldout_results=[{"verified": True, "negative_boundary_preserved": True}],
            displacement_receipt=economics("node:1"), expected_verifier_digest="verifier:1",
            expected_policy_generation="policy:1")


@pytest.mark.parametrize("context,match", [
    ({"policy_generation": "policy:wrong", "verifier_digest": "verifier:1"}, "policy mismatch"),
    ({"policy_generation": "policy:1", "verifier_digest": "verifier:evil"}, "verifier substitution"),
])
def test_m14_rejects_policy_and_verifier_substitution(tmp_path, context, match):
    admission = ProofArtifactAdmission(tmp_path, Ed25519PrivateKey.generate(),
        arda_appraiser=lambda manifest: {"allowed": True, "appraisal_ref": "arda:1"}).admit(
            bundle(economics()), space_id="space:proof", explicit_space_admission=True)
    with pytest.raises(PermissionError, match=match):
        CommonsFederation().reproduce(admission, node_id="node:1", contributor_id="contributor:1",
            node_attestation={"verified": True, "expires_at": time.time() + 60}, local_context=context,
            heldout_results=[{"verified": True, "negative_boundary_preserved": True}],
            displacement_receipt=economics("node:1"), expected_verifier_digest="verifier:1",
            expected_policy_generation="policy:1")
