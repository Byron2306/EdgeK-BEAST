import base64
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from app.kernel.commons.discovery import CommonsDiscoveryCatalog, DISCOVERY_PROTOCOL
from app.kernel.commons.lattice_trust import (
    CrystalLatticeAttestationIssuer,
    CrystalLatticeTrustStore,
    LatticeAuthority,
)
from app.kernel.commons.remote_client import CommonsEgressGate, RemoteCommonsGateway, RemoteCommonsRegistry
from app.kernel.commons.remote_protocol import canonical_json, sha256_bytes


CAPABILITIES = ["bucket_registry", "immutable_blobs", "signed_revisions", "replay_resistant_requests"]
HEAD = "sha256:" + "a" * 64


def _fixture(tmp_path):
    authority_key = Ed25519PrivateKey.generate()
    node_key = Ed25519PrivateKey.generate()
    node_public = base64.b64encode(node_key.public_key().public_bytes_raw()).decode("ascii")
    subject = {
        "node_id": "commons-lattice-a",
        "workload_digest": "sha256:" + "b" * 64,
        "node_public_key": node_public,
        "protocol": "beast-commons-http-signature-v1",
        "capabilities": CAPABILITIES,
        "maximum_authority": "verify_only",
    }
    issuer = CrystalLatticeAttestationIssuer(
        authority_key, authority="lattice-root", key_id="root-v1", policy_generation="lattice-policy-v1",
    )
    evidence = issuer.issue(
        subject=subject,
        lattice_verification={"valid": True, "head_hash": HEAD, "checkpoint_count": 9},
        ttl_seconds=600,
    )
    store = CrystalLatticeTrustStore([LatticeAuthority(
        "lattice-root", "root-v1", authority_key.public_key(),
        frozenset({"lattice-policy-v1"}), frozenset({HEAD}), 9,
    )])
    descriptor = {
        "beast_object_type": "remote_commons_node_descriptor",
        "schema_version": "1.0",
        **subject,
        "attestation_subject_digest": sha256_bytes(canonical_json(subject)),
        "trust_evidence": [evidence],
        "arda_appraisal": {},
        "storage": {},
    }
    node_document = {
        "descriptor": descriptor,
        "descriptor_digest": sha256_bytes(canonical_json(descriptor)),
        "node_signature": base64.b64encode(node_key.sign(canonical_json(descriptor))).decode("ascii"),
    }
    gateway = RemoteCommonsGateway(
        RemoteCommonsRegistry(tmp_path / "nodes.sqlite3"),
        CommonsEgressGate(allowed_hosts=("commons.example.org", "mirror.example.org")),
        lattice_trust_store=store,
        discovery_catalog=CommonsDiscoveryCatalog(tmp_path / "discovery.sqlite3"),
    )
    return issuer, store, node_key, subject, node_document, gateway


def _endpoint_proof(node_key, node_document, nonce):
    proof = {
        "beast_object_type": "commons_discovery_endpoint_proof",
        "schema_version": "1.0",
        "node_id": node_document["descriptor"]["node_id"],
        "nonce": nonce,
        "descriptor_digest": node_document["descriptor_digest"],
        "issued_at": time.time(),
        "maximum_authority": "endpoint_possession_only",
    }
    return {"proof": proof, "node_signature": base64.b64encode(node_key.sign(canonical_json(proof))).decode("ascii")}


def test_lattice_attestation_is_bound_to_trusted_current_head_and_subject(tmp_path):
    _issuer, store, _node_key, subject, node_document, _gateway = _fixture(tmp_path)
    evidence = node_document["descriptor"]["trust_evidence"][0]
    verified = store.verify(evidence, expected_subject=subject)
    assert verified["lattice_head_hash"] == HEAD
    assert verified["checkpoint_count"] == 9

    changed = {**subject, "workload_digest": "sha256:" + "c" * 64}
    try:
        store.verify(evidence, expected_subject=changed)
    except PermissionError as exc:
        assert "binding" in str(exc)
    else:
        raise AssertionError("subject substitution must fail")


def test_discovery_requires_lattice_and_live_endpoint_proof_before_registration(tmp_path):
    _issuer, _store, node_key, _subject, node_document, gateway = _fixture(tmp_path)
    envelope = {"discovery_protocol": DISCOVERY_PROTOCOL, "node": node_document}
    candidate = gateway.ingest_discovery_document(
        origin="https://commons.example.org", document=envelope, source="registry", auto_register=True,
    )
    assert candidate["candidate"]["state"] == "trusted_candidate"
    assert candidate["registered"] is None

    nonce = "n" * 40
    admitted = gateway.ingest_discovery_document(
        origin="https://commons.example.org", document=envelope, source="well_known",
        endpoint_proof=_endpoint_proof(node_key, node_document, nonce), expected_nonce=nonce, auto_register=True,
    )
    assert admitted["admission"] == "registered_from_lattice_and_endpoint_proof"
    assert admitted["registered"]["state"] == "lattice_attested"


def test_trusted_discovery_cannot_silently_replace_existing_endpoint(tmp_path):
    _issuer, _store, node_key, _subject, node_document, gateway = _fixture(tmp_path)
    envelope = {"discovery_protocol": DISCOVERY_PROTOCOL, "node": node_document}
    nonce = "a" * 40
    gateway.ingest_discovery_document(
        origin="https://commons.example.org", document=envelope, source="well_known",
        endpoint_proof=_endpoint_proof(node_key, node_document, nonce), expected_nonce=nonce, auto_register=True,
    )
    other_nonce = "b" * 40
    conflict = gateway.ingest_discovery_document(
        origin="https://mirror.example.org", document=envelope, source="peer_exchange",
        endpoint_proof=_endpoint_proof(node_key, node_document, other_nonce), expected_nonce=other_nonce, auto_register=True,
    )
    assert conflict["admission"] == "identity_conflict"
    assert gateway.registry.get("commons-lattice-a")["endpoint"] == "https://commons.example.org"


def test_local_protocol_invariants_override_a_valid_lattice_signature(tmp_path):
    issuer, _store, node_key, subject, _node_document, gateway = _fixture(tmp_path)
    unsupported = {**subject, "protocol": "unknown-transport-v99"}
    evidence = issuer.issue(
        subject=unsupported,
        lattice_verification={"valid": True, "head_hash": HEAD, "checkpoint_count": 9},
        ttl_seconds=600,
    )
    descriptor = {
        "beast_object_type": "remote_commons_node_descriptor", "schema_version": "1.0", **unsupported,
        "attestation_subject_digest": sha256_bytes(canonical_json(unsupported)),
        "trust_evidence": [evidence], "arda_appraisal": {}, "storage": {},
    }
    document = {
        "descriptor": descriptor,
        "descriptor_digest": sha256_bytes(canonical_json(descriptor)),
        "node_signature": base64.b64encode(node_key.sign(canonical_json(descriptor))).decode("ascii"),
    }
    result = gateway.ingest_discovery_document(
        origin="https://commons.example.org",
        document={"discovery_protocol": DISCOVERY_PROTOCOL, "node": document},
        source="manual",
    )
    assert result["candidate"]["state"] == "observed_untrusted"
    assert result["registered"] is None


def test_lattice_history_cannot_roll_back_or_fork_at_same_height(tmp_path):
    _issuer, _store, _node_key, _subject, _document, gateway = _fixture(tmp_path)
    node = {"last_probe": {"lattice_attestation": {"checkpoint_count": 9, "lattice_head_hash": HEAD}}}
    with pytest.raises(PermissionError, match="rollback"):
        gateway._enforce_lattice_monotonic(node, {
            "lattice_attestation": {"checkpoint_count": 8, "lattice_head_hash": "sha256:" + "c" * 64},
        })
    with pytest.raises(PermissionError, match="fork"):
        gateway._enforce_lattice_monotonic(node, {
            "lattice_attestation": {"checkpoint_count": 9, "lattice_head_hash": "sha256:" + "d" * 64},
        })
