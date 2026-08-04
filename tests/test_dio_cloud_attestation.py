from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_cloud_attestation import (
    DIOCloudProvider,
    DIOCloudTeeEvidence,
    DIOCloudTeePolicy,
    DIOCloudTeeType,
    DIOCloudVerifier,
    admit_cloud_tee_witness,
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
    evaluate_dio_distributed_quorum,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)


def _time_pair():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now, (now - timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=5)).isoformat()


def _cloud_key():
    return Ed25519PrivateKey.generate()


def _policy_and_evidence(provider: DIOCloudProvider, tee_type: DIOCloudTeeType, service: DIOCloudVerifier):
    now, issued, expires = _time_pair()
    key = _cloud_key()
    pub = public_key_b64(key.public_key())
    verifier = sha256_digest({"verifier": provider.value})
    measurement = sha256_digest({"measurement": tee_type.value})
    nonce = "dio-cloud-nonce-" + "x" * 32
    policy = DIOCloudTeePolicy(
        policy_id=f"policy:{provider.value}:governance",
        provider=provider,
        tee_type=tee_type,
        service_verifier=service,
        node_id=f"dio:{provider.value}:tee-governance-01",
        role=DIOWitnessRole.GOVERNANCE,
        permitted_verifier_commit=verifier,
        permitted_measurement_digest=measurement,
        permitted_public_key_fingerprint=public_key_fingerprint(pub),
        required_challenge_nonce=nonce,
        governance_epoch="dai-phase2.1-cloud-epoch",
    )
    evidence = DIOCloudTeeEvidence(
        beast_object_type="dio_cloud_tee_attestation_evidence",
        provider=provider,
        tee_type=tee_type,
        service_verifier=service,
        node_id=policy.node_id,
        role=policy.role,
        runtime_platform=tee_type.value,
        infrastructure_provider=provider.value,
        public_key_b64=pub,
        key_fingerprint=public_key_fingerprint(pub),
        verifier_commit=verifier,
        container_manifest=sha256_digest({"container": provider.value}),
        tee_measurement_digest=measurement,
        raw_attestation_digest=sha256_digest({"raw": provider.value}),
        service_verification_digest=sha256_digest({"verified": service.value}),
        challenge_nonce=nonce,
        governance_epoch=policy.governance_epoch,
        issued_at=issued,
        expires_at=expires,
    )
    return now, key, policy, evidence


def test_azure_maa_sev_snp_attestation_admits_hardware_rooted_witness():
    now, _key, policy, evidence = _policy_and_evidence(
        DIOCloudProvider.AZURE,
        DIOCloudTeeType.AZURE_SEV_SNP,
        DIOCloudVerifier.AZURE_MAA,
    )

    admission, report = admit_cloud_tee_witness(evidence, policy, evaluation_time=now)

    assert report.admitted is True
    assert report.red_gates == ()
    assert admission is not None
    assert admission.hardware_rooted_identity is True
    assert admission.remote_runtime is True
    assert admission.maximum_authority == HARDWARE_WITNESS_AUTHORITY
    assert admission.infrastructure_provider == "azure"


def test_gcp_confidential_vm_attestation_admits_hardware_rooted_witness():
    now, _key, policy, evidence = _policy_and_evidence(
        DIOCloudProvider.GCP,
        DIOCloudTeeType.GCP_CONFIDENTIAL_VM_VTPM,
        DIOCloudVerifier.GOOGLE_CLOUD_ATTESTATION,
    )

    admission, report = admit_cloud_tee_witness(evidence, policy, evaluation_time=now)

    assert report.admitted is True
    assert admission is not None
    assert admission.infrastructure_provider == "gcp"
    assert admission.attestation_digest == report.report_digest


def test_cloud_tee_attestation_rejects_wrong_nonce():
    now, _key, policy, evidence = _policy_and_evidence(
        DIOCloudProvider.AZURE,
        DIOCloudTeeType.AZURE_TDX,
        DIOCloudVerifier.AZURE_MAA,
    )
    hostile = DIOCloudTeeEvidence(**{**asdict(evidence), "challenge_nonce": "wrong-nonce-" + "y" * 32})

    admission, report = admit_cloud_tee_witness(hostile, policy, evaluation_time=now)

    assert admission is None
    assert report.admitted is False
    assert "challenge_nonce_bound" in report.red_gates


def test_cloud_tee_attestation_rejects_unpinned_measurement():
    now, _key, policy, evidence = _policy_and_evidence(
        DIOCloudProvider.GCP,
        DIOCloudTeeType.GCP_CONFIDENTIAL_SPACE,
        DIOCloudVerifier.GOOGLE_CLOUD_ATTESTATION,
    )
    hostile = DIOCloudTeeEvidence(**{**asdict(evidence), "tee_measurement_digest": sha256_digest({"measurement": "evil"})})

    admission, report = admit_cloud_tee_witness(hostile, policy, evaluation_time=now)

    assert admission is None
    assert "measurement_digest_pinned" in report.red_gates


def test_cloud_tee_attestation_rejects_expired_evidence():
    now, _key, policy, evidence = _policy_and_evidence(
        DIOCloudProvider.AZURE,
        DIOCloudTeeType.AZURE_SEV_SNP,
        DIOCloudVerifier.AZURE_MAA,
    )
    expired = DIOCloudTeeEvidence(
        **{
            **asdict(evidence),
            "issued_at": (now - timedelta(days=2)).isoformat(),
            "expires_at": (now - timedelta(days=1)).isoformat(),
        }
    )

    admission, report = admit_cloud_tee_witness(expired, policy, evaluation_time=now)

    assert admission is None
    assert "evidence_fresh" in report.red_gates


def test_cloud_tee_admission_integrates_into_dio_distributed_quorum():
    now, cloud_key, policy, evidence = _policy_and_evidence(
        DIOCloudProvider.AZURE,
        DIOCloudTeeType.AZURE_SEV_SNP,
        DIOCloudVerifier.AZURE_MAA,
    )
    cloud_admission, cloud_report = admit_cloud_tee_witness(evidence, policy, evaluation_time=now)
    assert cloud_admission is not None and cloud_report.admitted is True
    local_key = Ed25519PrivateKey.generate()
    hf_key = Ed25519PrivateKey.generate()
    local_pub = public_key_b64(local_key.public_key())
    hf_pub = public_key_b64(hf_key.public_key())
    local_admission = DIOWitnessAdmission(
        node_id="dio:local:physical-01",
        role=DIOWitnessRole.PHYSICAL_EXECUTION,
        runtime_platform="linux-local-host",
        infrastructure_provider="byron-local",
        public_key_b64=local_pub,
        key_fingerprint=public_key_fingerprint(local_pub),
        verifier_commit=policy.permitted_verifier_commit,
        maximum_authority=LOCAL_EXECUTION_WITNESS_AUTHORITY,
        verifier_build_permitted=True,
        remote_runtime=False,
        hardware_rooted_identity=False,
    )
    hf_admission = DIOWitnessAdmission(
        node_id="dio:hf:semantic-witness-01",
        role=DIOWitnessRole.SEMANTIC,
        runtime_platform="huggingface-docker-space",
        infrastructure_provider="huggingface",
        public_key_b64=hf_pub,
        key_fingerprint=public_key_fingerprint(hf_pub),
        verifier_commit=policy.permitted_verifier_commit,
        maximum_authority=HF_SOFTWARE_WITNESS_AUTHORITY,
        verifier_build_permitted=True,
        remote_runtime=True,
        hardware_rooted_identity=False,
    )
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": "cloud-quorum"}),
        capability_digest=sha256_digest({"capability": "stale-listener"}),
        evidence_root=sha256_digest({"evidence": "root"}),
        world_state_hash=sha256_digest({"world": "state"}),
        governance_epoch=policy.governance_epoch,
        challenge_nonce=policy.required_challenge_nonce,
        issued_at=(now - timedelta(minutes=1)).isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )

    def vote(node: DIOWitnessAdmission, key: Ed25519PrivateKey):
        return sign_dio_vote(
            DIORemoteWitnessVote(
                beast_object_type="dio_remote_witness_vote",
                node_id=node.node_id,
                role=node.role,
                decision=DIOVoteDecision.APPROVE,
                proposal_digest=proposal.proposal_digest,
                capability_digest=proposal.capability_digest,
                evidence_root=proposal.evidence_root,
                world_state_hash=proposal.world_state_hash,
                governance_epoch=proposal.governance_epoch,
                verifier_commit=policy.permitted_verifier_commit,
                challenge_nonce=proposal.challenge_nonce,
                evidence_checked=(proposal.evidence_root, cloud_report.report_digest),
                reason_codes=("jurisdiction_checked",),
                issued_at=(now - timedelta(seconds=10)).isoformat(),
                expires_at=(now + timedelta(minutes=5)).isoformat(),
                maximum_authority=node.maximum_authority,
            ),
            key,
        )

    report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=(local_admission, hf_admission, cloud_admission),
        votes=(vote(local_admission, local_key), vote(hf_admission, hf_key), vote(cloud_admission, cloud_key)),
        permitted_verifier_commits=(policy.permitted_verifier_commit,),
        evaluation_time=now,
        require_hardware_root=True,
    )

    assert report.passed is True
    assert report.quorum_class == "heterogeneous_distributed_quorum"
    assert report.hardware_rooted_node_count == 1
    assert report.distinct_infrastructure_provider_count == 3
