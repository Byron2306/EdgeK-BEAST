import base64
import hashlib
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.appraisal_verifier import SignedArdaAppraisalVerifier, SignedNodeAttestationVerifier
from app.kernel.commons.job_choir import NodeAdvertisement
from app.kernel.commons.signature_verifier import canonical_bytes
from app.kernel.integration.signed_decision import (
    SignedDecision,
    signed_appraisal_body,
)


def test_signed_arda_appraisal_is_bound_to_exact_space_body(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "arda-public.pem"
    public_path.write_bytes(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    body = {
        "space_id": "beast/lab",
        "image_digest": "sha256:" + "a" * 64,
        "cpu": 1.0,
        "memory_mb": 128,
        "mounts": ["commons://datasets/x"],
        "outbound_policy": "deny",
        "port": 0,
        "authority_ref": "beast.release",
        "appraisal_ref": "arda:appraisal:1",
    }
    digest = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    decision = SignedDecision("arda", True, digest, "policy-7", "nonce-1", "", "arda-key-1")
    signature = base64.b64encode(private_key.sign(decision.unsigned())).decode("ascii")
    appraisal = {
        "appraisal_ref": "arda:appraisal:1",
        "policy_generation": "policy-7",
        "authority": "arda",
        "state": "verified",
        "expires_at": time.time() + 60,
        "audience": "commons-space-forge",
        "decision": {
            "authority": "arda",
            "allowed": True,
            "request_digest": digest,
            "policy_generation": "policy-7",
            "nonce": "nonce-1",
            "signature": signature,
            "verification_material": {"key_id": "arda-key-1"},
        },
    }
    verifier = SignedArdaAppraisalVerifier(public_path)

    assert verifier(appraisal, body)
    assert not verifier(appraisal, {**body, "cpu": 2.0})


def test_complete_signed_arda_appraisal_is_bound_to_exact_space_body(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "arda-public.pem"
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    body = {
        "space_id": "beast/lab",
        "image_digest": "sha256:" + "a" * 64,
        "cpu": 1.0,
        "memory_mb": 128,
        "mounts": ["commons://datasets/x"],
        "outbound_policy": "deny",
        "port": 0,
        "authority_ref": "beast.release",
        "appraisal_ref": "arda:appraisal:complete",
    }
    digest = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    appraisal = {
        "appraisal_ref": "arda:appraisal:complete",
        "authority": "arda",
        "audience": "commons-space-forge",
        "policy_generation": "policy-9",
        "state": "verified",
        "expires_at": time.time() + 60,
        "request_digest": digest,
        "nonce": "appraisal-nonce",
        "key_id": "arda-key-1",
        "evidence_digest": "sha256:" + "b" * 64,
    }
    appraisal["signature"] = base64.b64encode(
        private_key.sign(signed_appraisal_body(appraisal))
    ).decode("ascii")
    verifier = SignedArdaAppraisalVerifier(
        public_path, expected_policy_generation="policy-9"
    )

    assert verifier(appraisal, body)
    assert not verifier(appraisal, {**body, "cpu": 2.0})
    assert not verifier({**appraisal, "expires_at": time.time() - 1}, body)
    assert not verifier({**appraisal, "policy_generation": "policy-10"}, body)


def test_signed_node_attestation_binds_complete_advertisement(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "arda-node.pem"
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    base = {
        "node_id": "node-1",
        "attestation": "verified",
        "capabilities": ["cpu"],
        "pressure_budget": 0.8,
        "reliability": 0.9,
        "route_penalty": 0.0,
        "expires_at": time.time() + 60,
        "appraisal_ref": "arda:node:1",
    }
    digest = "sha256:" + hashlib.sha256(canonical_bytes(base)).hexdigest()
    decision = SignedDecision(
        "arda", True, digest, "policy-8", "nonce-2", "", "arda-key-1"
    )
    evidence = {
        "appraisal_ref": "arda:node:1",
        "policy_generation": "policy-8",
        "authority": "arda",
        "state": "verified",
        "expires_at": time.time() + 60,
        "audience": "commons-job-choir",
        "decision": {
            "authority": "arda",
            "allowed": True,
            "request_digest": digest,
            "policy_generation": "policy-8",
            "nonce": "nonce-2",
            "signature": base64.b64encode(
                private_key.sign(decision.unsigned())
            ).decode("ascii"),
            "verification_material": {"key_id": "arda-key-1"},
        },
    }
    node = NodeAdvertisement(
        "node-1",
        "verified",
        ("cpu",),
        0.8,
        0.9,
        expires_at=base["expires_at"],
        appraisal_ref="arda:node:1",
        attestation_evidence=evidence,
    )
    verifier = SignedNodeAttestationVerifier(public_path)
    assert verifier(node)
    assert not verifier(NodeAdvertisement(**{**node.__dict__, "pressure_budget": 0.7}))


def test_complete_signed_node_attestation_binds_complete_advertisement(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "arda-node.pem"
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    body = {
        "node_id": "node-2",
        "attestation": "verified",
        "capabilities": ["cpu", "tpm"],
        "pressure_budget": 0.8,
        "reliability": 0.9,
        "route_penalty": 0.0,
        "expires_at": time.time() + 60,
        "appraisal_ref": "arda:node:complete",
    }
    digest = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    evidence = {
        "appraisal_ref": "arda:node:complete",
        "authority": "arda",
        "audience": "commons-job-choir",
        "policy_generation": "policy-10",
        "state": "verified",
        "expires_at": time.time() + 60,
        "request_digest": digest,
        "nonce": "appraisal-nonce-2",
        "key_id": "arda-key-1",
        "evidence_digest": "sha256:" + "c" * 64,
    }
    evidence["signature"] = base64.b64encode(
        private_key.sign(signed_appraisal_body(evidence))
    ).decode("ascii")
    node = NodeAdvertisement(
        "node-2",
        "verified",
        ("cpu", "tpm"),
        0.8,
        0.9,
        expires_at=body["expires_at"],
        appraisal_ref="arda:node:complete",
        attestation_evidence=evidence,
    )
    verifier = SignedNodeAttestationVerifier(
        public_path, expected_policy_generation="policy-10"
    )

    assert verifier(node)
    assert not verifier(NodeAdvertisement(**{**node.__dict__, "route_penalty": 0.1}))
    assert not verifier(
        NodeAdvertisement(**{**node.__dict__, "attestation_evidence": {**evidence, "state": "failed"}})
    )
