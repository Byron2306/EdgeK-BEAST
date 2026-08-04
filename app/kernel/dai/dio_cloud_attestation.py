"""Cloud TEE attestation admission for DIO distributed witnesses.

Azure/GCP accounts do not create quorum authority by themselves.  This module
admits a cloud witness only after a provider-verified attestation has been
normalized and pinned to the exact DIO policy: provider, TEE class, verifier
build, measurement, signing key, nonce, role and freshness.

The raw Azure MAA / Google Cloud Attestation token parser lives outside this
contract.  This contract consumes its normalized, digest-bound output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.dio_distributed_quorum import (
    DIOWitnessAdmission,
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    public_key_fingerprint,
)


DIO_CLOUD_ATTESTATION_VERSION = "2026-08-04.phase2.1.dio-cloud-tee-attestation.v1"


class DIOCloudProvider(str, Enum):
    AZURE = "azure"
    GCP = "gcp"


class DIOCloudTeeType(str, Enum):
    AZURE_SEV_SNP = "azure_sev_snp"
    AZURE_TDX = "azure_tdx"
    GCP_CONFIDENTIAL_VM_VTPM = "gcp_confidential_vm_vtpm"
    GCP_CONFIDENTIAL_SPACE = "gcp_confidential_space"


class DIOCloudVerifier(str, Enum):
    AZURE_MAA = "azure_maa"
    GOOGLE_CLOUD_ATTESTATION = "google_cloud_attestation"


@dataclass(frozen=True, slots=True)
class DIOCloudTeePolicy:
    policy_id: str
    provider: DIOCloudProvider | str
    tee_type: DIOCloudTeeType | str
    service_verifier: DIOCloudVerifier | str
    node_id: str
    role: DIOWitnessRole | str
    permitted_verifier_commit: str
    permitted_measurement_digest: str
    permitted_public_key_fingerprint: str
    required_challenge_nonce: str
    governance_epoch: str
    maximum_authority: str = HARDWARE_WITNESS_AUTHORITY

    def __post_init__(self) -> None:
        if not isinstance(self.provider, DIOCloudProvider):
            object.__setattr__(self, "provider", DIOCloudProvider(self.provider))
        if not isinstance(self.tee_type, DIOCloudTeeType):
            object.__setattr__(self, "tee_type", DIOCloudTeeType(self.tee_type))
        if not isinstance(self.service_verifier, DIOCloudVerifier):
            object.__setattr__(self, "service_verifier", DIOCloudVerifier(self.service_verifier))
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        for name in ("policy_id", "node_id", "required_challenge_nonce", "governance_epoch"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"DIO cloud TEE policy requires {name}")
        for field_name in (
            "permitted_verifier_commit",
            "permitted_measurement_digest",
            "permitted_public_key_fingerprint",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCloudTeeEvidence:
    beast_object_type: str
    provider: DIOCloudProvider | str
    tee_type: DIOCloudTeeType | str
    service_verifier: DIOCloudVerifier | str
    node_id: str
    role: DIOWitnessRole | str
    runtime_platform: str
    infrastructure_provider: str
    public_key_b64: str
    key_fingerprint: str
    verifier_commit: str
    container_manifest: str
    tee_measurement_digest: str
    raw_attestation_digest: str
    service_verification_digest: str
    challenge_nonce: str
    governance_epoch: str
    issued_at: str
    expires_at: str
    maximum_authority: str = HARDWARE_WITNESS_AUTHORITY

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_cloud_tee_attestation_evidence":
            raise ValueError("DIO cloud TEE evidence has the wrong object type")
        if not isinstance(self.provider, DIOCloudProvider):
            object.__setattr__(self, "provider", DIOCloudProvider(self.provider))
        if not isinstance(self.tee_type, DIOCloudTeeType):
            object.__setattr__(self, "tee_type", DIOCloudTeeType(self.tee_type))
        if not isinstance(self.service_verifier, DIOCloudVerifier):
            object.__setattr__(self, "service_verifier", DIOCloudVerifier(self.service_verifier))
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        for name in ("node_id", "runtime_platform", "infrastructure_provider", "challenge_nonce", "governance_epoch"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"DIO cloud TEE evidence requires {name}")
        for field_name in (
            "key_fingerprint",
            "verifier_commit",
            "container_manifest",
            "tee_measurement_digest",
            "raw_attestation_digest",
            "service_verification_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.key_fingerprint != public_key_fingerprint(self.public_key_b64):
            raise ValueError("DIO cloud TEE key fingerprint does not match public key")
        issued = _parse_time(self.issued_at, field_name="issued_at")
        expires = _parse_time(self.expires_at, field_name="expires_at")
        if expires <= issued:
            raise ValueError("DIO cloud TEE evidence expires_at must be after issued_at")

    @property
    def evidence_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCloudTeeAdmissionReport:
    beast_object_type: str
    version: str
    policy_digest: str
    evidence_digest: str
    admitted: bool
    provider: str
    tee_type: str
    service_verifier: str
    node_id: str
    role: str
    red_gates: tuple[str, ...]
    maximum_authority: str
    production_authority_allowed: bool

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def admit_cloud_tee_witness(
    evidence: DIOCloudTeeEvidence,
    policy: DIOCloudTeePolicy,
    *,
    evaluation_time: datetime | None = None,
) -> tuple[DIOWitnessAdmission | None, DIOCloudTeeAdmissionReport]:
    current = evaluation_time or datetime.now(timezone.utc)
    gates = {
        "provider_matches_policy": evidence.provider is policy.provider,
        "tee_type_matches_policy": evidence.tee_type is policy.tee_type,
        "service_verifier_matches_policy": evidence.service_verifier is policy.service_verifier,
        "node_id_matches_policy": evidence.node_id == policy.node_id,
        "role_matches_policy": evidence.role is policy.role,
        "verifier_commit_pinned": evidence.verifier_commit == policy.permitted_verifier_commit,
        "measurement_digest_pinned": evidence.tee_measurement_digest == policy.permitted_measurement_digest,
        "public_key_fingerprint_pinned": evidence.key_fingerprint == policy.permitted_public_key_fingerprint,
        "challenge_nonce_bound": evidence.challenge_nonce == policy.required_challenge_nonce,
        "governance_epoch_bound": evidence.governance_epoch == policy.governance_epoch,
        "evidence_fresh": _fresh(evidence.issued_at, evidence.expires_at, current),
        "authority_bounded": evidence.maximum_authority == policy.maximum_authority == HARDWARE_WITNESS_AUTHORITY,
        "raw_attestation_digest_present": bool(evidence.raw_attestation_digest),
        "service_verification_digest_present": bool(evidence.service_verification_digest),
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    report = DIOCloudTeeAdmissionReport(
        beast_object_type="dio_cloud_tee_admission_report",
        version=DIO_CLOUD_ATTESTATION_VERSION,
        policy_digest=policy.policy_digest,
        evidence_digest=evidence.evidence_digest,
        admitted=not red_gates,
        provider=evidence.provider.value,
        tee_type=evidence.tee_type.value,
        service_verifier=evidence.service_verifier.value,
        node_id=evidence.node_id,
        role=evidence.role.value,
        red_gates=red_gates,
        maximum_authority=HARDWARE_WITNESS_AUTHORITY,
        production_authority_allowed=False,
    )
    if red_gates:
        return None, report
    return (
        DIOWitnessAdmission(
            node_id=evidence.node_id,
            role=evidence.role,
            runtime_platform=evidence.runtime_platform,
            infrastructure_provider=evidence.infrastructure_provider,
            public_key_b64=evidence.public_key_b64,
            key_fingerprint=evidence.key_fingerprint,
            verifier_commit=evidence.verifier_commit,
            maximum_authority=HARDWARE_WITNESS_AUTHORITY,
            verifier_build_permitted=True,
            remote_runtime=True,
            hardware_rooted_identity=True,
            attestation_digest=report.report_digest,
            container_manifest=evidence.container_manifest,
            admitted=True,
        ),
        report,
    )


def _parse_time(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed.astimezone(timezone.utc)


def _fresh(issued_at: str, expires_at: str, current: datetime) -> bool:
    issued = _parse_time(issued_at, field_name="issued_at")
    expires = _parse_time(expires_at, field_name="expires_at")
    return issued <= current < expires
