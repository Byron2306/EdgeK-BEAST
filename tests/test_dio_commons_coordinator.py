from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_commons_adapters import DIOCommonsSpaceAdapterReport
from app.kernel.dai.dio_commons_coordinator import mint_phase4_proposal, run_commons_coordinator_session
from app.kernel.dai.dio_commons_online import (
    DIO_COMMONS_ONLINE_VERSION,
    DIOCommonsCapabilityManifest,
    DIOCommonsSpaceIdentity,
    sign_commons_identity,
)
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    HF_SOFTWARE_WITNESS_AUTHORITY,
    LOCAL_EXECUTION_WITNESS_AUTHORITY,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)
from app.kernel.dai.dio_remote_witness_packet import DIOAutonomousRemoteWitnessPacket, sign_autonomous_remote_witness_packet


def _hf_identity_manifest(key):
    pub = public_key_b64(key.public_key())
    verifier = sha256_digest({"verifier": "hf-phase4"})
    manifest = DIOCommonsCapabilityManifest(
        "dio_commons_capability_manifest",
        DIO_COMMONS_ONLINE_VERSION,
        "dio:hf:semantic-witness-01",
        verifier,
        ("semantic_vote", "challenge_attestation"),
        HF_SOFTWARE_WITNESS_AUTHORITY,
        True,
    )
    identity = DIOCommonsSpaceIdentity(
        "dio_commons_space_identity",
        DIO_COMMONS_ONLINE_VERSION,
        "dio:hf:semantic-witness-01",
        DIOWitnessRole.SEMANTIC,
        "hf:Byron230686",
        "huggingface-docker-space",
        "huggingface",
        pub,
        public_key_fingerprint(pub),
        verifier,
        manifest.manifest_digest,
        "signed_software_runtime",
        HF_SOFTWARE_WITNESS_AUTHORITY,
        "dio-phase4-online-001",
    )
    return identity, manifest


def _adapter(node_id, role, attestation_class, authority, provider):
    return DIOCommonsSpaceAdapterReport(
        beast_object_type="dio_commons_space_adapter_report",
        version="2026-08-04.phase4.commons-adapter.v1",
        adapter_kind="arda_local_physical" if provider == "local" else "aws_nitro_tpm",
        node_id=node_id,
        role=role,
        operator_root=f"{provider}:operator",
        runtime_platform=f"{provider}:runtime",
        infrastructure_provider=provider,
        attestation_class=attestation_class,
        maximum_authority=authority,
        capability_manifest_digest=sha256_digest({"manifest": node_id}),
        source_receipt_digest=sha256_digest({"receipt": node_id}),
        source_verification_digest=sha256_digest({"verification": node_id}),
        persistent_service=False,
        online_protocol_ready=False,
        identity_signature_present=False,
        challenge_endpoint_present=False,
        red_gates=(),
        adapted=True,
    )


def _proposal(now):
    return mint_phase4_proposal(
        proposal_digest=sha256_digest({"proposal": "phase4-coordinator"}),
        capability_digest=sha256_digest({"capability": "commons-coordinator"}),
        evidence_root=sha256_digest({"evidence": "phase4"}),
        world_state_hash=sha256_digest({"world": "phase4"}),
        governance_epoch="dio-phase4-online-001",
        challenge_nonce="phase4-shared-challenge-" + "x" * 24,
        now=now,
    )


def _autonomous_envelope(
    proposal: DIOProposalPacket,
    *,
    node_id: str,
    role: DIOWitnessRole,
    authority: str,
    provider: str,
    platform: str,
    hardware: bool,
    now: datetime,
):
    key = Ed25519PrivateKey.generate()
    pub = public_key_b64(key.public_key())
    verifier = sha256_digest({"verifier": node_id})
    admission = DIOWitnessAdmission(
        node_id=node_id,
        role=role,
        runtime_platform=platform,
        infrastructure_provider=provider,
        public_key_b64=pub,
        key_fingerprint=public_key_fingerprint(pub),
        verifier_commit=verifier,
        maximum_authority=authority,
        verifier_build_permitted=True,
        remote_runtime=True,
        hardware_rooted_identity=hardware,
        attestation_digest=sha256_digest({"attestation": node_id}),
        container_manifest=sha256_digest({"container": node_id}),
    )
    vote = sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=node_id,
            role=role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=verifier,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root, admission.attestation_digest),
            reason_codes=("autonomous_commons_vote",),
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=authority,
        ),
        key,
    )
    packet = sign_autonomous_remote_witness_packet(
        DIOAutonomousRemoteWitnessPacket(
            beast_object_type="dio_autonomous_remote_witness_packet",
            version="2026-08-04.phase5.autonomous-remote-witness.v1",
            node_id=node_id,
            role=role,
            runtime_platform=platform,
            infrastructure_provider=provider,
            public_key_b64=pub,
            key_fingerprint=admission.key_fingerprint,
            verifier_commit=verifier,
            admission_digest=admission.admission_digest,
            admission_attestation_digest=admission.attestation_digest,
            proposal_packet_digest=proposal.packet_digest,
            vote=vote,
            evidence_receipts=(proposal.evidence_root, admission.attestation_digest),
            independently_evaluated=True,
            remote_runtime_observed=True,
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=authority,
        ),
        key,
    )
    return {
        "admission": {**{field: getattr(admission, field) for field in DIOWitnessAdmission.__dataclass_fields__}, "admission_digest": admission.admission_digest},
        "packet": {**{field: getattr(packet, field) for field in DIOAutonomousRemoteWitnessPacket.__dataclass_fields__}, "packet_digest": packet.packet_digest},
    }


def test_commons_coordinator_mints_leases_collects_votes_and_keeps_execution_off():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hf_key = Ed25519PrivateKey.generate()
    coordinator_key = Ed25519PrivateKey.generate()
    identity, manifest = _hf_identity_manifest(hf_key)
    proposal, challenge = _proposal(now)
    physical = _adapter("dio:arda:local-physical-01", "physical_execution_witness", "local_physical_witness", LOCAL_EXECUTION_WITNESS_AUTHORITY, "local")
    governance = _adapter("dio:aws:tee-governance-01", "governance_witness", "provider_hardware_attestation", HARDWARE_WITNESS_AUTHORITY, "aws")
    adapter_keys = {physical.node_id: Ed25519PrivateKey.generate(), governance.node_id: Ed25519PrivateKey.generate()}
    online_vote = sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=identity.node_id,
            role=identity.role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=identity.verifier_digest,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root,),
            reason_codes=("online_hf_semantic_vote",),
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HF_SOFTWARE_WITNESS_AUTHORITY,
        ),
        hf_key,
    )

    session, quorum = run_commons_coordinator_session(
        online_identity=identity,
        online_identity_signature=sign_commons_identity(identity, hf_key),
        online_manifest=manifest,
        adapter_reports=(physical, governance),
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        adapter_vote_keys=adapter_keys,
        online_votes=(online_vote,),
    )

    assert session.quorum_available is True
    assert session.red_gates == ()
    assert session.online_lease_digests
    assert session.adapter_admission_count == 2
    assert len(session.vote_digests) == 3
    assert quorum.hardware_rooted_node_count == 1
    assert quorum.execution_authority_allowed is False
    assert session.execution_authority_allowed is False
    assert session.production_authority_allowed is False


def test_commons_coordinator_accepts_autonomous_packets_without_adapter_simulation():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hf_key = Ed25519PrivateKey.generate()
    coordinator_key = Ed25519PrivateKey.generate()
    identity, manifest = _hf_identity_manifest(hf_key)
    proposal, challenge = _proposal(now)
    online_vote = sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=identity.node_id,
            role=identity.role,
            decision=DIOVoteDecision.APPROVE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=identity.verifier_digest,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root,),
            reason_codes=("online_hf_semantic_vote",),
            issued_at=now.isoformat(),
            expires_at=proposal.expires_at,
            maximum_authority=HF_SOFTWARE_WITNESS_AUTHORITY,
        ),
        hf_key,
    )
    physical = _autonomous_envelope(
        proposal,
        node_id="dio:remote:physical-01",
        role=DIOWitnessRole.PHYSICAL_EXECUTION,
        authority=LOCAL_EXECUTION_WITNESS_AUTHORITY,
        provider="remote-arda",
        platform="remote-linux-physical",
        hardware=False,
        now=now,
    )
    governance = _autonomous_envelope(
        proposal,
        node_id="dio:aws:tee-governance-01",
        role=DIOWitnessRole.GOVERNANCE,
        authority=HARDWARE_WITNESS_AUTHORITY,
        provider="aws",
        platform="aws-nitro-tpm",
        hardware=True,
        now=now,
    )

    session, quorum = run_commons_coordinator_session(
        online_identity=identity,
        online_identity_signature=sign_commons_identity(identity, hf_key),
        online_manifest=manifest,
        adapter_reports=(),
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        online_votes=(online_vote,),
        autonomous_witness_envelopes=(physical, governance),
        expect_autonomous_packets=True,
    )

    assert session.quorum_available is True
    assert session.adapter_votes_simulated is False
    assert session.autonomous_packet_count == 2
    assert len(session.autonomous_packet_digests) == 2
    assert quorum.valid_vote_count == 3


def test_commons_coordinator_refuses_simulated_adapter_votes_when_autonomous_packets_expected():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hf_key = Ed25519PrivateKey.generate()
    coordinator_key = Ed25519PrivateKey.generate()
    identity, manifest = _hf_identity_manifest(hf_key)
    proposal, challenge = _proposal(now)
    physical = _adapter("dio:arda:local-physical-01", "physical_execution_witness", "local_physical_witness", LOCAL_EXECUTION_WITNESS_AUTHORITY, "local")

    session, _quorum = run_commons_coordinator_session(
        online_identity=identity,
        online_identity_signature=sign_commons_identity(identity, hf_key),
        online_manifest=manifest,
        adapter_reports=(physical,),
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        adapter_vote_keys={physical.node_id: Ed25519PrivateKey.generate()},
        expect_autonomous_packets=True,
        require_hardware_root=False,
    )

    assert session.quorum_available is False
    assert session.adapter_votes_simulated is False
    assert "simulated_adapter_votes_refused_when_autonomous_expected" in session.red_gates


def test_commons_coordinator_rejects_stale_epoch_and_missing_adapter_vote_key():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hf_key = Ed25519PrivateKey.generate()
    coordinator_key = Ed25519PrivateKey.generate()
    identity, manifest = _hf_identity_manifest(hf_key)
    proposal, challenge = _proposal(now)
    stale_identity = DIOCommonsSpaceIdentity(
        **{
            **{field: getattr(identity, field) for field in DIOCommonsSpaceIdentity.__dataclass_fields__},
            "governance_epoch": "stale-epoch",
        }
    )
    physical = _adapter("dio:arda:local-physical-01", "physical_execution_witness", "local_physical_witness", LOCAL_EXECUTION_WITNESS_AUTHORITY, "local")

    session, _quorum = run_commons_coordinator_session(
        online_identity=stale_identity,
        online_identity_signature=sign_commons_identity(stale_identity, hf_key),
        online_manifest=manifest,
        adapter_reports=(physical,),
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        adapter_vote_keys={},
    )

    assert session.quorum_available is False
    assert "online_hf_admission" in session.red_gates
    assert f"adapter_vote_key_missing:{physical.node_id}" in session.red_gates
    assert session.online_lease_digests == ()


def test_commons_coordinator_rejects_hf_attestation_downgrade_and_duplicate_adapter_operator():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hf_key = Ed25519PrivateKey.generate()
    coordinator_key = Ed25519PrivateKey.generate()
    identity, manifest = _hf_identity_manifest(hf_key)
    downgraded_identity = replace(identity, attestation_class="provider_hardware_attestation")
    proposal, challenge = _proposal(now)
    physical = _adapter("dio:arda:local-physical-01", "physical_execution_witness", "local_physical_witness", LOCAL_EXECUTION_WITNESS_AUTHORITY, "local")
    governance = _adapter("dio:aws:tee-governance-01", "governance_witness", "provider_hardware_attestation", HARDWARE_WITNESS_AUTHORITY, "aws")
    duplicate_operator = replace(governance, operator_root=physical.operator_root)
    adapter_keys = {physical.node_id: Ed25519PrivateKey.generate(), duplicate_operator.node_id: Ed25519PrivateKey.generate()}

    session, _quorum = run_commons_coordinator_session(
        online_identity=downgraded_identity,
        online_identity_signature=sign_commons_identity(downgraded_identity, hf_key),
        online_manifest=manifest,
        adapter_reports=(physical, duplicate_operator),
        proposal=proposal,
        challenge=challenge,
        coordinator_key=coordinator_key,
        now=now,
        adapter_vote_keys=adapter_keys,
    )

    assert session.quorum_available is False
    assert "online_hf_admission" in session.red_gates
    assert "adapter_operator_roots_distinct" in session.red_gates
    assert session.online_lease_digests == ()
