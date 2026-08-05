from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.dio_cloud_autonomous_packet import build_cloud_autonomous_witness_envelope
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    public_key_b64,
    public_key_fingerprint,
)


def _harvest(key: Ed25519PrivateKey) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    pub = public_key_b64(key.public_key())
    admission = DIOWitnessAdmission(
        node_id="dio:gcp:tee-governance-01",
        role=DIOWitnessRole.GOVERNANCE,
        runtime_platform="gcp_confidential_vm_vtpm",
        infrastructure_provider="gcp",
        public_key_b64=pub,
        key_fingerprint=public_key_fingerprint(pub),
        verifier_commit=sha256_digest({"verifier": "gcp"}),
        maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        verifier_build_permitted=True,
        remote_runtime=True,
        hardware_rooted_identity=True,
        attestation_digest=sha256_digest({"attestation": "gcp"}),
        container_manifest=sha256_digest({"container": "gcp"}),
        admitted=True,
    )
    evidence = {
        "governance_epoch": "dio-phase5-cloud-autonomous-001",
        "challenge_nonce": "cloud-autonomous-" + "x" * 32,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    harvest = {
        "beast_object_type": "dio_gcp_tee_attestation_harvest",
        "green": True,
        "evidence": evidence,
        "evidence_digest": sha256_digest(evidence),
        "admission": asdict(admission),
        "admission_report_digest": sha256_digest({"admission_report": "green"}),
        "production_authority_allowed": False,
        "provider_calls_used": 0,
    }
    harvest["harvest_digest"] = sha256_digest(harvest)
    return harvest


def test_cloud_harvest_can_emit_green_autonomous_packet_when_remote_runtime_observed() -> None:
    key = Ed25519PrivateKey.generate()
    envelope = build_cloud_autonomous_witness_envelope(
        harvest=_harvest(key),
        private_key=key,
        remote_runtime_observed=True,
    )

    assert envelope["beast_object_type"] == "dio_cloud_autonomous_witness_envelope"
    assert envelope["verification"]["verified"] is True
    assert envelope["verification"]["red_gates"] == []
    assert envelope["packet"]["remote_runtime_observed"] is True
    assert envelope["production_authority_allowed"] is False
    assert envelope["execution_authority_allowed"] is False


def test_cloud_harvest_autonomous_packet_is_red_without_remote_runtime_observation() -> None:
    key = Ed25519PrivateKey.generate()
    envelope = build_cloud_autonomous_witness_envelope(
        harvest=_harvest(key),
        private_key=key,
        remote_runtime_observed=False,
    )

    assert envelope["verification"]["verified"] is False
    assert "packet_remote_runtime_observed" in envelope["verification"]["red_gates"]
    assert envelope["packet"]["remote_runtime_observed"] is False


def test_cloud_harvest_autonomous_packet_can_bind_coordinator_supplied_proposal() -> None:
    key = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": "shared-phase5-quorum"}),
        capability_digest=sha256_digest({"capability": "shared-phase5-quorum"}),
        evidence_root=sha256_digest({"evidence": "shared-phase5-quorum"}),
        world_state_hash=sha256_digest({"world": "shared-phase5-quorum"}),
        governance_epoch="dio-phase5-shared-quorum-001",
        challenge_nonce="phase5-shared-quorum-" + "x" * 32,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )
    envelope = build_cloud_autonomous_witness_envelope(
        harvest=_harvest(key),
        private_key=key,
        remote_runtime_observed=True,
        proposal=proposal,
        evaluation_time=now,
    )

    assert envelope["verification"]["verified"] is True
    assert envelope["proposal"]["packet_digest"] == proposal.packet_digest
    assert envelope["packet"]["proposal_packet_digest"] == proposal.packet_digest
    assert envelope["packet"]["vote"]["proposal_digest"] == proposal.proposal_digest
