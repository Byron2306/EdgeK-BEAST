from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)
from app.kernel.dai.dio_remote_witness_packet import (
    DIOAutonomousRemoteWitnessPacket,
    sign_autonomous_remote_witness_packet,
    verify_autonomous_remote_witness_packet,
)


def _fixture():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    key = Ed25519PrivateKey.generate()
    pub = public_key_b64(key.public_key())
    verifier = sha256_digest({"verifier": "phase5-remote-witness"})
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": "phase5"}),
        capability_digest=sha256_digest({"capability": "commons-autonomous-witness"}),
        evidence_root=sha256_digest({"evidence": "phase5"}),
        world_state_hash=sha256_digest({"world": "phase5"}),
        governance_epoch="dio-phase5-online-001",
        challenge_nonce="phase5-autonomous-witness-" + "x" * 24,
        issued_at=(now - timedelta(seconds=30)).isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )
    admission = DIOWitnessAdmission(
        node_id="dio:aws:tee-governance-01",
        role=DIOWitnessRole.GOVERNANCE,
        runtime_platform="aws_nitro_tpm",
        infrastructure_provider="aws",
        public_key_b64=pub,
        key_fingerprint=public_key_fingerprint(pub),
        verifier_commit=verifier,
        maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        verifier_build_permitted=True,
        remote_runtime=True,
        hardware_rooted_identity=True,
        attestation_digest=sha256_digest({"aws": "nitro-attestation-report"}),
        container_manifest=sha256_digest({"container": "phase5-witness"}),
    )
    vote = sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=admission.node_id,
            role=admission.role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=verifier,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root, admission.attestation_digest),
            reason_codes=("phase5_remote_packet_fixture",),
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        ),
        key,
    )
    packet = sign_autonomous_remote_witness_packet(
        DIOAutonomousRemoteWitnessPacket(
            beast_object_type="dio_autonomous_remote_witness_packet",
            version="2026-08-04.phase5.autonomous-remote-witness.v1",
            node_id=admission.node_id,
            role=admission.role,
            runtime_platform=admission.runtime_platform,
            infrastructure_provider=admission.infrastructure_provider,
            public_key_b64=pub,
            key_fingerprint=admission.key_fingerprint,
            verifier_commit=verifier,
            admission_digest=admission.admission_digest,
            admission_attestation_digest=admission.attestation_digest,
            proposal_packet_digest=proposal.packet_digest,
            vote=vote,
            evidence_receipts=(admission.attestation_digest,),
            independently_evaluated=True,
            remote_runtime_observed=True,
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        ),
        key,
    )
    return now, key, proposal, admission, packet


def _verify(packet=None, proposal=None, admission=None):
    now, _key, fixture_proposal, fixture_admission, fixture_packet = _fixture()
    return verify_autonomous_remote_witness_packet(
        packet=packet or fixture_packet,
        admission=admission or fixture_admission,
        proposal=proposal or fixture_proposal,
        permitted_verifier_commits=(fixture_admission.verifier_commit,),
        evaluation_time=now,
    )


def test_autonomous_remote_witness_packet_verifies_signed_vote_and_admission_binding():
    report = _verify()

    assert report.verified is True
    assert report.red_gates == ()
    assert report.provider_calls_used == 0
    assert report.execution_authority_allowed is False
    assert report.production_authority_allowed is False


def test_autonomous_remote_witness_packet_rejects_bad_packet_signature():
    _now, _key, _proposal, _admission, packet = _fixture()
    hostile = replace(packet, packet_signature=packet.packet_signature[:-4] + "AAAA")

    report = _verify(packet=hostile)

    assert report.verified is False
    assert "packet_signature_valid" in report.red_gates


def test_autonomous_remote_witness_packet_rejects_wrong_proposal_binding():
    _now, _key, proposal, _admission, packet = _fixture()
    wrong = replace(proposal, world_state_hash=sha256_digest({"world": "different"}))

    report = _verify(packet=packet, proposal=wrong)

    assert report.verified is False
    assert "packet_proposal_digest_bound" in report.red_gates
    assert "vote_binds_world_state" in report.red_gates


def test_autonomous_remote_witness_packet_rejects_stale_packet():
    now, key, _proposal, _admission, packet = _fixture()
    stale = replace(
        packet,
        issued_at=(now - timedelta(days=2)).isoformat(),
        expires_at=(now - timedelta(days=1)).isoformat(),
        packet_signature="",
    )
    stale = sign_autonomous_remote_witness_packet(stale, key)

    report = _verify(packet=stale)

    assert report.verified is False
    assert "packet_fresh" in report.red_gates


def test_autonomous_remote_witness_packet_rejects_missing_independent_remote_runtime():
    now, key, _proposal, _admission, packet = _fixture()
    hostile = replace(packet, independently_evaluated=False, remote_runtime_observed=False, packet_signature="")
    hostile = sign_autonomous_remote_witness_packet(hostile, key)

    report = _verify(packet=hostile)

    assert report.verified is False
    assert "packet_declares_independent_evaluation" in report.red_gates
    assert "packet_remote_runtime_observed" in report.red_gates


def test_autonomous_remote_witness_packet_rejects_vote_tampering():
    now, key, _proposal, _admission, packet = _fixture()
    tampered_vote = replace(packet.vote, evidence_root=sha256_digest({"evidence": "tampered"}))
    hostile = replace(packet, vote=tampered_vote, packet_signature="")
    hostile = sign_autonomous_remote_witness_packet(hostile, key)

    report = _verify(packet=hostile)

    assert report.verified is False
    assert "vote_signature_valid" in report.red_gates
    assert "vote_binds_evidence_root" in report.red_gates
