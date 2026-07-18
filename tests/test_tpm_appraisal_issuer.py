import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient

import app.main as main
from app.kernel.commons.appraisal_verifier import SignedNodeAttestationVerifier
from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.tpm_appraisal import TpmNodeAppraisalIssuer


def _eligible_evidence(challenge):
    return {
        "schema": "beast.commons.tpm-evidence.v1",
        "platform": "linux",
        "node_id": challenge.node_id,
        "challenge_id": challenge.challenge_id,
        "nonce": challenge.nonce,
        "audience": "beast-commons-node-attestation",
        "pcrs": list(challenge.pcrs),
        "status": "hardware_quote_valid_measurements_reconciled",
        "eligible_for_commons": True,
        "evidence_digest": "sha256:" + "a" * 64,
        "measurement_reconciliation": {
            "valid": True,
            "matched_pcrs": [0, 2, 4, 7, 10, 14],
            "mismatched_pcrs": [],
            "uncovered_pcrs": [],
        },
        "verifier_facts": {
            "quote_valid": True,
            "ek_public_matches_certificate": True,
            "ek_chain_valid": True,
            "ak_credential_activated": True,
            "secure_boot_accepted": True,
            "event_log_replay_valid": True,
        },
    }


def _issuer_and_public_key(tmp_path):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "arda-appraisal-public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    issuer = TpmNodeAppraisalIssuer(
        private,
        policy_generation="policy-tpm-1",
        key_id="arda-tpm-key-1",
        ttl_seconds=60,
    )
    return issuer, public_path


def test_tpm_evidence_issues_signed_commons_node_appraisal(tmp_path):
    issuer, public_path = _issuer_and_public_key(tmp_path)
    verifier = SignedNodeAttestationVerifier(
        public_path, expected_policy_generation="policy-tpm-1"
    )
    plane = CommonsEnterprisePlane(
        tmp_path / "commons",
        signature_verifier=lambda *_args: True,
        appraisal_verifier=lambda *_args: True,
        node_attestation_verifier=verifier,
        tpm_appraisal_issuer=issuer,
    )
    challenge = plane.issue_tpm_challenge("node-local", ttl_seconds=120)
    appraisal, evidence_node = plane.appraise_tpm_node(
        _eligible_evidence(challenge),
        capabilities=("cpu", "tpm"),
        pressure_budget=0.75,
        reliability=0.91,
    )

    assert evidence_node.node_type == "commons_tpm_node_appraised"
    assert verifier(appraisal.node)
    selected, _schedule = plane.select_node(
        [appraisal.node], required="cpu", now=time.time()
    )
    assert selected.node_id == "node-local"
    assert plane.tpm_challenges.get(challenge.challenge_id).state == "consumed"


def test_tpm_appraisal_rejects_replay_and_unreconciled_evidence(tmp_path):
    issuer, public_path = _issuer_and_public_key(tmp_path)
    plane = CommonsEnterprisePlane(
        tmp_path / "commons",
        signature_verifier=lambda *_args: True,
        appraisal_verifier=lambda *_args: True,
        node_attestation_verifier=SignedNodeAttestationVerifier(public_path),
        tpm_appraisal_issuer=issuer,
    )
    challenge = plane.issue_tpm_challenge("node-local", ttl_seconds=120)
    evidence = _eligible_evidence(challenge)
    plane.appraise_tpm_node(evidence)

    with pytest.raises(PermissionError, match="already been consumed"):
        plane.appraise_tpm_node(evidence)

    second = plane.issue_tpm_challenge("node-local", ttl_seconds=120)
    denied = _eligible_evidence(second)
    denied["measurement_reconciliation"] = {"valid": False}
    with pytest.raises(PermissionError, match="not valid"):
        plane.appraise_tpm_node(denied)


@pytest.mark.asyncio
async def test_tpm_appraisal_endpoint_issues_node_appraisal(tmp_path, monkeypatch):
    issuer, public_path = _issuer_and_public_key(tmp_path)
    plane = CommonsEnterprisePlane(
        tmp_path / "commons",
        signature_verifier=lambda *_args: True,
        appraisal_verifier=lambda *_args: True,
        node_attestation_verifier=SignedNodeAttestationVerifier(
            public_path, expected_policy_generation="policy-tpm-1"
        ),
        tpm_appraisal_issuer=issuer,
    )
    monkeypatch.setattr(main, "commons_enterprise_plane", plane)
    digest = main._active_workspace_identity.digest()
    challenge = plane.issue_tpm_challenge("node-local", ttl_seconds=120)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/control-plane/commons/attestation/appraise",
            headers={"X-BEAST-Workspace-Identity": digest},
            json={
                "evidence": _eligible_evidence(challenge),
                "capabilities": ["cpu", "tpm"],
                "pressure_budget": 0.7,
                "reliability": 0.9,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "appraised"
    assert body["node"]["node_id"] == "node-local"
    assert body["appraisal"]["audience"] == "commons-job-choir"


@pytest.mark.asyncio
async def test_commons_job_select_endpoint_accepts_required_capability_list(tmp_path, monkeypatch):
    issuer, public_path = _issuer_and_public_key(tmp_path)
    plane = CommonsEnterprisePlane(
        tmp_path / "commons",
        signature_verifier=lambda *_args: True,
        appraisal_verifier=lambda *_args: True,
        node_attestation_verifier=SignedNodeAttestationVerifier(
            public_path, expected_policy_generation="policy-tpm-1"
        ),
        tpm_appraisal_issuer=issuer,
    )
    monkeypatch.setattr(main, "commons_enterprise_plane", plane)
    digest = main._active_workspace_identity.digest()
    challenge = plane.issue_tpm_challenge("node-local", ttl_seconds=120)
    appraisal, _evidence = plane.appraise_tpm_node(
        _eligible_evidence(challenge),
        capabilities=("cpu", "tpm"),
        pressure_budget=0.7,
        reliability=0.9,
    )

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/control-plane/commons/jobs/select",
            headers={"X-BEAST-Workspace-Identity": digest},
            json={"nodes": [appraisal.node.__dict__], "required": ["cpu"]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "selected"
    assert body["required"] == "cpu"
    assert body["node"]["node_id"] == "node-local"
