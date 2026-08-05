"""Phase-4 Commons coordinator for one shared proposal/session/quorum."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.dio_commons_adapters import DIOCommonsSpaceAdapterReport
from app.kernel.dai.dio_commons_online import (
    DIO_COMMONS_ONLINE_VERSION,
    DIOCommonsActiveLease,
    DIOCommonsAdmissionPolicy,
    DIOCommonsAdmissionReport,
    DIOCommonsCapabilityManifest,
    DIOCommonsChallenge,
    DIOCommonsRegisteredSpace,
    DIOCommonsSpaceIdentity,
    admit_commons_online_space,
)
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIODistributedQuorumReport,
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
from app.kernel.dai.dio_remote_witness_packet import DIOAutonomousRemoteWitnessPacket, verify_autonomous_remote_witness_packet


DIO_COMMONS_COORDINATOR_VERSION = "2026-08-04.phase4.commons-coordinator.v1"
ADAPTER_SIMULATED_VERIFIER_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ADAPTER_AUTHORITY_MAP = {
    "provider_hardware_attestation": HARDWARE_WITNESS_AUTHORITY,
    "local_physical_witness": LOCAL_EXECUTION_WITNESS_AUTHORITY,
    "ephemeral_build_provenance": "semantic_vote_only",
}
ROLE_MAP = {
    "physical_execution_witness": DIOWitnessRole.PHYSICAL_EXECUTION,
    "semantic_witness": DIOWitnessRole.SEMANTIC,
    "semantic_or_adversarial_witness": DIOWitnessRole.ADVERSARIAL,
    "adversarial_witness": DIOWitnessRole.ADVERSARIAL,
    "governance_witness": DIOWitnessRole.GOVERNANCE,
}


@dataclass(frozen=True, slots=True)
class DIOCommonsCoordinatorSession:
    beast_object_type: str
    version: str
    proposal: DIOProposalPacket
    challenge: DIOCommonsChallenge
    online_admission_reports: tuple[DIOCommonsAdmissionReport, ...]
    online_lease_digests: tuple[str, ...]
    autonomous_packet_digests: tuple[str, ...]
    autonomous_packet_count: int
    adapter_report_digests: tuple[str, ...]
    adapter_admission_count: int
    vote_digests: tuple[str, ...]
    quorum_report_digest: str
    red_gates: tuple[str, ...]
    quorum_available: bool
    adapter_votes_simulated: bool
    provider_calls_used: int
    execution_authority_allowed: bool
    production_authority_allowed: bool

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_coordinator_session":
            raise ValueError("unexpected Commons coordinator session object type")
        if self.version != DIO_COMMONS_COORDINATOR_VERSION:
            raise ValueError("unexpected Commons coordinator version")
        for digest in (*self.online_lease_digests, *self.autonomous_packet_digests, *self.adapter_report_digests, *self.vote_digests):
            require_digest(digest, field_name="coordinator_digest")
        if self.quorum_report_digest:
            require_digest(self.quorum_report_digest, field_name="quorum_report_digest")
        if self.provider_calls_used != 0 or self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("Commons coordinator cannot grant provider, execution or production authority")
        if self.quorum_available and self.red_gates:
            raise ValueError("quorum cannot be available with red gates")

    @property
    def session_digest(self) -> str:
        return sha256_digest(self)


def mint_phase4_proposal(
    *,
    proposal_digest: str,
    capability_digest: str,
    evidence_root: str,
    world_state_hash: str,
    governance_epoch: str,
    challenge_nonce: str,
    now: datetime,
    ttl_seconds: int = 300,
) -> tuple[DIOProposalPacket, DIOCommonsChallenge]:
    issued_at = now.astimezone(timezone.utc).isoformat()
    expires_at = (now.astimezone(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=proposal_digest,
        capability_digest=capability_digest,
        evidence_root=evidence_root,
        world_state_hash=world_state_hash,
        governance_epoch=governance_epoch,
        challenge_nonce=challenge_nonce,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    challenge = DIOCommonsChallenge(
        beast_object_type="dio_commons_challenge",
        version=DIO_COMMONS_ONLINE_VERSION,
        proposal_digest=proposal_digest,
        evidence_root=evidence_root,
        world_state_hash=world_state_hash,
        governance_epoch=governance_epoch,
        challenge_nonce=challenge_nonce,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return proposal, challenge


def run_commons_coordinator_session(
    *,
    online_identity: DIOCommonsSpaceIdentity,
    online_identity_signature: str,
    online_manifest: DIOCommonsCapabilityManifest,
    adapter_reports: Iterable[DIOCommonsSpaceAdapterReport],
    proposal: DIOProposalPacket,
    challenge: DIOCommonsChallenge,
    coordinator_key: Ed25519PrivateKey,
    now: datetime,
    adapter_vote_keys: Mapping[str, Ed25519PrivateKey] | None = None,
    online_votes: Iterable[DIORemoteWitnessVote] = (),
    autonomous_witness_envelopes: Iterable[Mapping[str, Any]] = (),
    expect_autonomous_packets: bool = False,
    require_hardware_root: bool = True,
) -> tuple[DIOCommonsCoordinatorSession, DIODistributedQuorumReport]:
    red: set[str] = set()
    adapter_rows = tuple(adapter_reports)
    autonomous_rows = tuple(autonomous_witness_envelopes)
    autonomous_packet_digests: list[str] = []
    if len({adapter.node_id for adapter in adapter_rows}) != len(adapter_rows):
        red.add("adapter_node_ids_distinct")
    if len({adapter.operator_root for adapter in adapter_rows}) != len(adapter_rows):
        red.add("adapter_operator_roots_distinct")
    if proposal.proposal_digest != challenge.proposal_digest or proposal.evidence_root != challenge.evidence_root or proposal.world_state_hash != challenge.world_state_hash:
        red.add("proposal_challenge_binding")
    if proposal.governance_epoch != challenge.governance_epoch or proposal.challenge_nonce != challenge.challenge_nonce:
        red.add("proposal_challenge_epoch_nonce")

    policy = DIOCommonsAdmissionPolicy(
        beast_object_type="dio_commons_admission_policy",
        version=DIO_COMMONS_ONLINE_VERSION,
        governance_epoch=proposal.governance_epoch,
        coordinator_public_key=public_key_b64(coordinator_key.public_key()),
        registered_spaces=(
            DIOCommonsRegisteredSpace(
                online_identity.node_id,
                online_identity.role,
                online_identity.operator_root,
                online_identity.key_fingerprint,
                online_identity.verifier_digest,
                online_identity.capability_manifest_digest,
                online_identity.attestation_class,
                online_identity.maximum_authority,
            ),
        ),
        required_unique_roles=(online_identity.role,),
        permitted_attestation_classes=("signed_software_runtime",),
    )
    online_report, lease = admit_commons_online_space(
        identity=online_identity,
        identity_signature=online_identity_signature,
        manifest=online_manifest,
        challenge=challenge,
        policy=policy,
        coordinator=coordinator_key,
        now=now,
    )
    if not online_report.admitted or lease is None:
        red.add("online_hf_admission")

    admissions: list[DIOWitnessAdmission] = []
    votes: list[DIORemoteWitnessVote] = []
    permitted_verifiers: set[str] = {online_identity.verifier_digest, ADAPTER_SIMULATED_VERIFIER_DIGEST}
    if online_report.admitted:
        online_admission = DIOWitnessAdmission(
            node_id=online_identity.node_id,
            role=online_identity.role,
            runtime_platform=online_identity.runtime_platform,
            infrastructure_provider=online_identity.infrastructure_provider,
            public_key_b64=online_identity.public_signing_key,
            key_fingerprint=online_identity.key_fingerprint,
            verifier_commit=online_identity.verifier_digest,
            maximum_authority=HF_SOFTWARE_WITNESS_AUTHORITY,
            verifier_build_permitted=True,
            remote_runtime=True,
            hardware_rooted_identity=False,
            attestation_digest=online_report.report_digest,
            container_manifest=online_manifest.manifest_digest,
        )
        admissions.append(online_admission)

    for envelope in autonomous_rows:
        try:
            admission_payload = dict(envelope.get("admission") or {})
            admission_payload.pop("admission_digest", None)
            packet_payload = dict(envelope.get("packet") or {})
            claimed_packet_digest = str(packet_payload.pop("packet_digest", ""))
            admission = DIOWitnessAdmission(**admission_payload)
            packet = DIOAutonomousRemoteWitnessPacket(**packet_payload)
            verification = verify_autonomous_remote_witness_packet(
                packet=packet,
                admission=admission,
                proposal=proposal,
                permitted_verifier_commits=(admission.verifier_commit,),
                evaluation_time=now,
            )
            if verification.verified and packet.packet_digest == claimed_packet_digest:
                admissions.append(admission)
                votes.append(packet.vote)
                autonomous_packet_digests.append(packet.packet_digest)
                permitted_verifiers.add(admission.verifier_commit)
            else:
                red.add(f"autonomous_packet_not_verified:{admission.node_id}")
                red.update(f"autonomous:{gate}" for gate in verification.red_gates)
        except Exception:
            red.add("autonomous_packet_parse_failed")

    adapter_keys = dict(adapter_vote_keys or {})
    if expect_autonomous_packets and adapter_rows:
        red.add("simulated_adapter_votes_refused_when_autonomous_expected")
    for adapter in (() if expect_autonomous_packets else adapter_rows):
        if not adapter.adapted:
            red.add(f"adapter_not_adapted:{adapter.node_id}")
            continue
        authority = ADAPTER_AUTHORITY_MAP.get(adapter.attestation_class, adapter.maximum_authority)
        role = ROLE_MAP.get(adapter.role, DIOWitnessRole.ADVERSARIAL)
        key = adapter_keys.get(adapter.node_id)
        if key is None:
            red.add(f"adapter_vote_key_missing:{adapter.node_id}")
            continue
        pub = public_key_b64(key.public_key())
        admissions.append(
            DIOWitnessAdmission(
                node_id=adapter.node_id,
                role=role,
                runtime_platform=adapter.runtime_platform,
                infrastructure_provider=adapter.infrastructure_provider,
                public_key_b64=pub,
                key_fingerprint=public_key_fingerprint(pub),
                verifier_commit=ADAPTER_SIMULATED_VERIFIER_DIGEST,
                maximum_authority=authority,
                verifier_build_permitted=True,
                remote_runtime=adapter.infrastructure_provider != "local",
                hardware_rooted_identity=adapter.attestation_class == "provider_hardware_attestation",
                attestation_digest=adapter.report_digest,
                container_manifest=adapter.capability_manifest_digest,
            )
        )

    for admission in admissions:
        key = adapter_keys.get(admission.node_id)
        if admission.node_id == online_identity.node_id:
            continue
        if key is None:
            continue
        try:
            votes.append(_vote(proposal, admission, key, now=now))
        except ValueError:
            red.add(f"adapter_vote_construction_valid:{admission.node_id}")
    votes.extend(tuple(online_votes))

    quorum_report = evaluate_dio_distributed_quorum(
        proposal=proposal,
        admissions=admissions,
        votes=votes,
        permitted_verifier_commits=permitted_verifiers,
        evaluation_time=now,
        require_hardware_root=require_hardware_root,
    )
    red.update(quorum_report.red_gates)
    session = DIOCommonsCoordinatorSession(
        beast_object_type="dio_commons_coordinator_session",
        version=DIO_COMMONS_COORDINATOR_VERSION,
        proposal=proposal,
        challenge=challenge,
        online_admission_reports=(online_report,),
        online_lease_digests=(lease.lease_digest,) if lease else (),
        autonomous_packet_digests=tuple(sorted(autonomous_packet_digests)),
        autonomous_packet_count=len(autonomous_packet_digests),
        adapter_report_digests=tuple(adapter.report_digest for adapter in adapter_rows),
        adapter_admission_count=sum(1 for admission in admissions if admission.node_id != online_identity.node_id),
        vote_digests=tuple(sorted(vote.vote_digest for vote in votes)),
        quorum_report_digest=quorum_report.report_digest,
        red_gates=tuple(sorted(red)),
        quorum_available=quorum_report.passed and not red,
        adapter_votes_simulated=bool(adapter_rows) and not expect_autonomous_packets,
        provider_calls_used=0,
        execution_authority_allowed=False,
        production_authority_allowed=False,
    )
    return session, quorum_report


def _vote(proposal: DIOProposalPacket, admission: DIOWitnessAdmission, key: Ed25519PrivateKey, *, now: datetime) -> DIORemoteWitnessVote:
    vote = DIORemoteWitnessVote(
        beast_object_type="dio_remote_witness_vote",
        node_id=admission.node_id,
        role=admission.role,
        decision=DIOVoteDecision.APPROVE,
        proposal_digest=proposal.proposal_digest,
        capability_digest=proposal.capability_digest,
        evidence_root=proposal.evidence_root,
        world_state_hash=proposal.world_state_hash,
        governance_epoch=proposal.governance_epoch,
        verifier_commit=admission.verifier_commit,
        challenge_nonce=proposal.challenge_nonce,
        evidence_checked=tuple(digest for digest in (proposal.evidence_root, admission.attestation_digest) if digest),
        reason_codes=("commons_adapter_material_checked", "phase4_authority_bounded"),
        issued_at=now.astimezone(timezone.utc).isoformat(),
        expires_at=proposal.expires_at,
        maximum_authority=admission.maximum_authority,
    )
    return sign_dio_vote(vote, key)
