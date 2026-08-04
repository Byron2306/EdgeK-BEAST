from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient
import pytest

from app.dio_hf_witness_main import DIOHFWitnessConfig, build_dio_hf_witness_app
from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    HF_SOFTWARE_WITNESS_AUTHORITY,
    LOCAL_EXECUTION_WITNESS_AUTHORITY,
    evaluate_dio_distributed_quorum,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
    verify_dio_vote_signature,
)


def _key():
    return Ed25519PrivateKey.generate()


def _time_pair():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now, (now - timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=5)).isoformat()


def _proposal() -> DIOProposalPacket:
    _now, issued, expires = _time_pair()
    return DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": "phase2.1"}),
        capability_digest=sha256_digest({"capability": "stale-listener"}),
        evidence_root=sha256_digest({"evidence": "root"}),
        world_state_hash=sha256_digest({"world": "state"}),
        governance_epoch="dai-phase2.1-epoch",
        challenge_nonce="nonce-phase2-1-" + "x" * 32,
        issued_at=issued,
        expires_at=expires,
    )


def _admission(
    *,
    node_id: str,
    role: DIOWitnessRole,
    key: Ed25519PrivateKey,
    platform: str,
    provider: str,
    remote: bool,
    hardware: bool,
    verifier: str,
    authority: str,
) -> DIOWitnessAdmission:
    pub = public_key_b64(key.public_key())
    return DIOWitnessAdmission(
        node_id=node_id,
        role=role,
        runtime_platform=platform,
        infrastructure_provider=provider,
        public_key_b64=pub,
        key_fingerprint=public_key_fingerprint(pub),
        verifier_commit=verifier,
        container_manifest=sha256_digest({"container": node_id}),
        maximum_authority=authority,
        verifier_build_permitted=True,
        remote_runtime=remote,
        hardware_rooted_identity=hardware,
        attestation_digest=sha256_digest({"attestation": node_id}) if hardware else "",
    )


def _vote(
    proposal: DIOProposalPacket,
    *,
    node_id: str,
    role: DIOWitnessRole,
    verifier: str,
    key: Ed25519PrivateKey,
    authority: str,
    decision: DIOVoteDecision = DIOVoteDecision.APPROVE,
) -> DIORemoteWitnessVote:
    _now, issued, expires = _time_pair()
    vote = DIORemoteWitnessVote(
        beast_object_type="dio_remote_witness_vote",
        node_id=node_id,
        role=role,
        decision=decision,
        proposal_digest=proposal.proposal_digest,
        capability_digest=proposal.capability_digest,
        evidence_root=proposal.evidence_root,
        world_state_hash=proposal.world_state_hash,
        governance_epoch=proposal.governance_epoch,
        verifier_commit=verifier,
        challenge_nonce=proposal.challenge_nonce,
        evidence_checked=(proposal.evidence_root,),
        reason_codes=("jurisdiction_checked",),
        issued_at=issued,
        expires_at=expires,
        maximum_authority=authority,
    )
    return sign_dio_vote(vote, key)


def _three_node_fixture():
    proposal = _proposal()
    verifier = sha256_digest({"verifier": "dio-phase2.1"})
    local_key = _key()
    hf_key = _key()
    phone_key = _key()
    admissions = (
        _admission(
            node_id="dio:local:physical-01",
            role=DIOWitnessRole.PHYSICAL_EXECUTION,
            key=local_key,
            platform="linux-local-host",
            provider="byron-local",
            remote=False,
            hardware=False,
            verifier=verifier,
            authority=LOCAL_EXECUTION_WITNESS_AUTHORITY,
        ),
        _admission(
            node_id="dio:hf:semantic-witness-01",
            role=DIOWitnessRole.SEMANTIC,
            key=hf_key,
            platform="huggingface-docker-space",
            provider="huggingface",
            remote=True,
            hardware=False,
            verifier=verifier,
            authority=HF_SOFTWARE_WITNESS_AUTHORITY,
        ),
        _admission(
            node_id="dio:phone:governance-01",
            role=DIOWitnessRole.GOVERNANCE,
            key=phone_key,
            platform="android-hardware-keystore",
            provider="separate-phone",
            remote=True,
            hardware=True,
            verifier=verifier,
            authority=HARDWARE_WITNESS_AUTHORITY,
        ),
    )
    votes = (
        _vote(proposal, node_id=admissions[0].node_id, role=admissions[0].role, verifier=verifier, key=local_key, authority=LOCAL_EXECUTION_WITNESS_AUTHORITY),
        _vote(proposal, node_id=admissions[1].node_id, role=admissions[1].role, verifier=verifier, key=hf_key, authority=HF_SOFTWARE_WITNESS_AUTHORITY),
        _vote(proposal, node_id=admissions[2].node_id, role=admissions[2].role, verifier=verifier, key=phone_key, authority=HARDWARE_WITNESS_AUTHORITY),
    )
    return proposal, admissions, votes, {item.node_id: key for item, key in zip(admissions, (local_key, hf_key, phone_key))}, verifier


def test_dio_quorum_accepts_local_hf_phone_heterogeneous_distributed_quorum():
    proposal, admissions, votes, _keys, verifier = _three_node_fixture()
    now, _issued, _expires = _time_pair()

    report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=admissions,
        votes=votes,
        permitted_verifier_commits=(verifier,),
        evaluation_time=now,
        require_hardware_root=True,
    )

    assert report.passed is True
    assert report.quorum_class == "heterogeneous_distributed_quorum"
    assert report.valid_vote_count == 3
    assert report.remote_node_count == 2
    assert report.hardware_rooted_node_count == 1
    assert report.execution_authority_allowed is False
    assert report.production_authority_allowed is False


def test_dio_quorum_rejects_valid_signature_for_wrong_role():
    proposal, admissions, votes, keys, verifier = _three_node_fixture()
    now, _issued, _expires = _time_pair()
    wrong_role_vote = _vote(
        proposal,
        node_id="dio:phone:governance-01",
        role=DIOWitnessRole.SEMANTIC,
        verifier=verifier,
        key=keys["dio:phone:governance-01"],
        authority=HARDWARE_WITNESS_AUTHORITY,
    )

    report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=admissions,
        votes=(votes[0], votes[1], wrong_role_vote),
        permitted_verifier_commits=(verifier,),
        evaluation_time=now,
        require_hardware_root=True,
    )

    assert report.passed is False
    assert "vote_role_matches_admission" in report.red_gates


def test_dio_quorum_rejects_evidence_root_byte_mismatch():
    proposal, admissions, votes, _keys, verifier = _three_node_fixture()
    now, _issued, _expires = _time_pair()
    tampered = replace(votes[1], evidence_root=sha256_digest({"evidence": "one-byte-off"}))
    tampered = sign_dio_vote(replace(tampered, vote_signature=""), _keys["dio:hf:semantic-witness-01"])

    report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=admissions,
        votes=(votes[0], tampered, votes[2]),
        permitted_verifier_commits=(verifier,),
        evaluation_time=now,
        require_hardware_root=True,
    )

    assert report.passed is False
    assert "vote_binds_evidence_root" in report.red_gates


def test_dio_quorum_rejects_three_votes_from_one_duplicated_key():
    proposal, admissions, votes, keys, verifier = _three_node_fixture()
    now, _issued, _expires = _time_pair()
    shared_key = keys["dio:local:physical-01"]
    duplicated = tuple(
        replace(
            admission,
            public_key_b64=public_key_b64(shared_key.public_key()),
            key_fingerprint=public_key_fingerprint(public_key_b64(shared_key.public_key())),
        )
        for admission in admissions
    )

    report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=duplicated,
        votes=votes,
        permitted_verifier_commits=(verifier,),
        evaluation_time=now,
        require_hardware_root=True,
    )

    assert report.passed is False
    assert "distinct_signing_keys" in report.red_gates
    assert "vote_signature_valid" in report.red_gates


def test_dio_quorum_rejects_ml_kem_session_masquerading_as_identity():
    proposal, admissions, votes, _keys, verifier = _three_node_fixture()
    now, _issued, _expires = _time_pair()
    fake_identity = replace(admissions[1], maximum_authority="ml_kem_session_only")

    report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=(admissions[0], fake_identity, admissions[2]),
        votes=votes,
        permitted_verifier_commits=(verifier,),
        evaluation_time=now,
        require_hardware_root=True,
    )

    assert report.passed is False
    assert "ml_kem_session_cannot_be_identity_attestation" in report.red_gates
    assert "admitted_maximum_authority_bounded" in report.red_gates


@pytest.mark.asyncio
async def test_dio_hf_witness_app_attests_and_signs_bounded_vote():
    key = _key()
    verifier = sha256_digest({"verifier": "hf"})
    config = DIOHFWitnessConfig(
        node_id="dio:hf:semantic-witness-01",
        role=DIOWitnessRole.SEMANTIC,
        signing_key=key,
        verifier_commit=verifier,
        container_manifest=sha256_digest({"container": "hf-space"}),
    )
    app = build_dio_hf_witness_app(config)
    proposal = _proposal()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hf-witness") as client:
        health = await client.get("/health")
        attestation = await client.post("/attest", json={"challenge_nonce": proposal.challenge_nonce})
        vote_response = await client.post("/evaluate", json={"proposal": asdict(proposal)})

    assert health.json()["maximum_authority"] == HF_SOFTWARE_WITNESS_AUTHORITY
    assert attestation.json()["maximum_authority"] == HF_SOFTWARE_WITNESS_AUTHORITY
    assert vote_response.status_code == 200
    payload = vote_response.json()
    vote = DIORemoteWitnessVote(**{key: payload[key] for key in DIORemoteWitnessVote.__dataclass_fields__})
    assert vote.maximum_authority == HF_SOFTWARE_WITNESS_AUTHORITY
    assert verify_dio_vote_signature(vote, public_key_b64(key.public_key()))
