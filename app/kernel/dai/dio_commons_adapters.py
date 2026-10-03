"""Adapters from existing witness evidence into Phase-4 Commons space adverts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.dio_commons_online import DIO_COMMONS_ONLINE_VERSION, DIOCommonsCapabilityManifest
from app.kernel.dai.dio_distributed_quorum import (
    DIOWitnessRole,
    HARDWARE_WITNESS_AUTHORITY,
    LOCAL_EXECUTION_WITNESS_AUTHORITY,
)


DIO_COMMONS_ADAPTER_VERSION = "2026-08-04.phase4.commons-adapter.v1"


class DIOCommonsAdapterKind(str, Enum):
    GCP_CONFIDENTIAL_SPACE = "gcp_confidential_space"
    AWS_NITRO_TPM = "aws_nitro_tpm"
    GITHUB_ACTIONS_PROVENANCE = "github_actions_provenance"
    ARDA_LOCAL_PHYSICAL = "arda_local_physical"


@dataclass(frozen=True, slots=True)
class DIOCommonsSpaceAdapterReport:
    beast_object_type: str
    version: str
    adapter_kind: DIOCommonsAdapterKind | str
    node_id: str
    role: str
    operator_root: str
    runtime_platform: str
    infrastructure_provider: str
    attestation_class: str
    maximum_authority: str
    capability_manifest_digest: str
    source_receipt_digest: str
    source_verification_digest: str
    persistent_service: bool
    online_protocol_ready: bool
    identity_signature_present: bool
    challenge_endpoint_present: bool
    red_gates: tuple[str, ...]
    adapted: bool
    provider_calls_used: int = 0
    execution_authority_allowed: bool = False
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_space_adapter_report":
            raise ValueError("unexpected Commons adapter report object type")
        if self.version != DIO_COMMONS_ADAPTER_VERSION:
            raise ValueError("unexpected Commons adapter version")
        if not isinstance(self.adapter_kind, DIOCommonsAdapterKind):
            object.__setattr__(self, "adapter_kind", DIOCommonsAdapterKind(self.adapter_kind))
        for name in ("node_id", "role", "operator_root", "runtime_platform", "infrastructure_provider", "attestation_class", "maximum_authority"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"Commons adapter report requires {name}")
        for name in ("capability_manifest_digest", "source_receipt_digest"):
            require_digest(getattr(self, name), field_name=name)
        if self.source_verification_digest:
            require_digest(self.source_verification_digest, field_name="source_verification_digest")
        if self.provider_calls_used != 0 or self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("Commons adapters cannot grant provider, execution or production authority")
        if self.online_protocol_ready and not (self.persistent_service and self.identity_signature_present and self.challenge_endpoint_present):
            raise ValueError("online-ready Commons adapter requires persistent signed challenge surface")
        if self.adapted and self.red_gates:
            raise ValueError("adapted Commons report cannot contain red gates")

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def adapt_cloud_harvest_to_commons_space(harvest: Mapping[str, Any], *, adapter_kind: DIOCommonsAdapterKind | str) -> tuple[DIOCommonsCapabilityManifest, DIOCommonsSpaceAdapterReport]:
    kind = adapter_kind if isinstance(adapter_kind, DIOCommonsAdapterKind) else DIOCommonsAdapterKind(adapter_kind)
    if kind not in {DIOCommonsAdapterKind.GCP_CONFIDENTIAL_SPACE, DIOCommonsAdapterKind.AWS_NITRO_TPM}:
        raise ValueError("cloud harvest adapter supports only GCP/AWS hardware harvests")
    evidence = _mapping(harvest.get("evidence"), "cloud harvest evidence")
    admission = _mapping(harvest.get("admission"), "cloud harvest admission")
    node_id = str(evidence.get("node_id") or admission.get("node_id") or "")
    authority = str(evidence.get("maximum_authority") or admission.get("maximum_authority") or HARDWARE_WITNESS_AUTHORITY)
    manifest = _manifest(
        node_id=node_id,
        verifier_digest=str(evidence.get("verifier_commit") or ""),
        capability_ids=("hardware_attestation_reference", "governance_vote_material"),
        maximum_authority=authority,
        persistent_service=False,
    )
    expected_provider = "gcp" if kind is DIOCommonsAdapterKind.GCP_CONFIDENTIAL_SPACE else "aws"
    accepted_tees = (
        {"gcp_confidential_space", "gcp_confidential_vm_vtpm"}
        if kind is DIOCommonsAdapterKind.GCP_CONFIDENTIAL_SPACE
        else {"aws_nitro_tpm", "aws_nitro_enclave"}
    )
    verification_digest = str(
        harvest.get("admission_report_digest")
        or _mapping(harvest.get("admission_report"), "cloud admission report").get("report_digest")
        or _mapping(harvest.get("nitro_document_verification"), "nitro verification").get("verification_digest")
        or ""
    )
    gates = {
        "harvest_green": harvest.get("green") is True,
        "provider_matches_adapter": evidence.get("provider") == expected_provider,
        "tee_matches_adapter": evidence.get("tee_type") in accepted_tees,
        "admission_hardware_rooted": admission.get("hardware_rooted_identity") is True,
        "admission_remote_runtime": admission.get("remote_runtime") is True,
        "authority_bounded": authority == HARDWARE_WITNESS_AUTHORITY,
        "production_authority_false": harvest.get("production_authority_allowed") is False,
        "provider_calls_zero": harvest.get("provider_calls_used") == 0,
    }
    red = tuple(sorted(name for name, passed in gates.items() if not passed))
    return manifest, DIOCommonsSpaceAdapterReport(
        beast_object_type="dio_commons_space_adapter_report",
        version=DIO_COMMONS_ADAPTER_VERSION,
        adapter_kind=kind,
        node_id=node_id,
        role=str(evidence.get("role") or admission.get("role") or DIOWitnessRole.GOVERNANCE.value),
        operator_root=f"{expected_provider}:attested-witness",
        runtime_platform=str(evidence.get("runtime_platform") or sorted(accepted_tees)[0]),
        infrastructure_provider=expected_provider,
        attestation_class="provider_hardware_attestation",
        maximum_authority=authority,
        capability_manifest_digest=manifest.manifest_digest,
        source_receipt_digest=str(harvest.get("harvest_digest") or harvest.get("evidence_digest") or ""),
        source_verification_digest=verification_digest,
        persistent_service=False,
        online_protocol_ready=False,
        identity_signature_present=False,
        challenge_endpoint_present=False,
        red_gates=red,
        adapted=not red,
    )


def adapt_github_actions_verification_to_commons_space(packet: Mapping[str, Any], verification: Mapping[str, Any]) -> tuple[DIOCommonsCapabilityManifest, DIOCommonsSpaceAdapterReport]:
    node_id = str(packet.get("node_id") or "")
    manifest = _manifest(
        node_id=node_id,
        verifier_digest=str(verification.get("verification_digest") or packet.get("packet_digest") or ""),
        capability_ids=("ephemeral_provenance_reference", "software_witness_material"),
        maximum_authority=str(packet.get("maximum_authority") or "remote_oidc_sigstore_software_witness_only"),
        persistent_service=False,
    )
    gates = {
        "packet_digest_recomputes": packet.get("packet_digest") == verification.get("packet_digest") == verification.get("recomputed_packet_digest"),
        "verification_green": verification.get("verified") is True,
        "github_attestation_verified": _mapping(verification.get("github_attestation"), "github attestation").get("verified") is True,
        "remote_runtime": packet.get("remote_runtime") is True,
        "hardware_rooted_false": packet.get("hardware_rooted_identity") is False,
        "execution_authority_false": packet.get("execution_authority_allowed") is False,
        "production_authority_false": packet.get("production_authority_allowed") is False,
        "provider_calls_zero": packet.get("provider_calls_used") == 0,
    }
    red = tuple(sorted(name for name, passed in gates.items() if not passed))
    return manifest, DIOCommonsSpaceAdapterReport(
        beast_object_type="dio_commons_space_adapter_report",
        version=DIO_COMMONS_ADAPTER_VERSION,
        adapter_kind=DIOCommonsAdapterKind.GITHUB_ACTIONS_PROVENANCE,
        node_id=node_id,
        role=str(packet.get("role") or DIOWitnessRole.ADVERSARIAL.value),
        operator_root=str(_mapping(packet.get("workflow_identity"), "workflow identity").get("repository") or "github-actions"),
        runtime_platform=str(_mapping(packet.get("runtime"), "runtime").get("platform") or "github-actions"),
        infrastructure_provider="github",
        attestation_class="ephemeral_build_provenance",
        maximum_authority=str(packet.get("maximum_authority") or "remote_oidc_sigstore_software_witness_only"),
        capability_manifest_digest=manifest.manifest_digest,
        source_receipt_digest=str(packet.get("packet_digest") or ""),
        source_verification_digest=str(verification.get("verification_digest") or ""),
        persistent_service=False,
        online_protocol_ready=False,
        identity_signature_present=False,
        challenge_endpoint_present=False,
        red_gates=red,
        adapted=not red,
    )


def adapt_arda_receipt_to_commons_space(receipt: Mapping[str, Any]) -> tuple[DIOCommonsCapabilityManifest, DIOCommonsSpaceAdapterReport]:
    authority = str(receipt.get("maximum_authority") or LOCAL_EXECUTION_WITNESS_AUTHORITY)
    manifest = _manifest(
        node_id="dio:arda:local-physical-01",
        verifier_digest=str(receipt.get("arda_attestation_digest") or ""),
        capability_ids=("local_physical_execution_reference", "bounded_replay_material"),
        maximum_authority=authority,
        persistent_service=False,
    )
    gates = {
        "receipt_digest_present": bool(receipt.get("receipt_digest")),
        "arda_attestation_present": bool(receipt.get("arda_attestation_digest")),
        "bounded_sandbox_execution": receipt.get("execution_mode") == "arda_bounded_sandbox_replay",
        "host_mutation_false": receipt.get("host_mutation_allowed") is False,
        "execution_authority_false": receipt.get("execution_authority_allowed") is False,
        "provider_calls_zero": receipt.get("provider_calls_used") == 0,
    }
    red = tuple(sorted(name for name, passed in gates.items() if not passed))
    return manifest, DIOCommonsSpaceAdapterReport(
        beast_object_type="dio_commons_space_adapter_report",
        version=DIO_COMMONS_ADAPTER_VERSION,
        adapter_kind=DIOCommonsAdapterKind.ARDA_LOCAL_PHYSICAL,
        node_id="dio:arda:local-physical-01",
        role=DIOWitnessRole.PHYSICAL_EXECUTION.value,
        operator_root="byron-local-arda",
        runtime_platform=str(receipt.get("execution_mode") or "arda_local"),
        infrastructure_provider="local",
        attestation_class="local_physical_witness",
        maximum_authority=authority,
        capability_manifest_digest=manifest.manifest_digest,
        source_receipt_digest=str(receipt.get("receipt_digest") or ""),
        source_verification_digest=str(receipt.get("arda_attestation_digest") or ""),
        persistent_service=False,
        online_protocol_ready=False,
        identity_signature_present=False,
        challenge_endpoint_present=False,
        red_gates=red,
        adapted=not red,
    )


def _manifest(*, node_id: str, verifier_digest: str, capability_ids: tuple[str, ...], maximum_authority: str, persistent_service: bool) -> DIOCommonsCapabilityManifest:
    return DIOCommonsCapabilityManifest(
        beast_object_type="dio_commons_capability_manifest",
        version=DIO_COMMONS_ONLINE_VERSION,
        node_id=node_id,
        verifier_digest=verifier_digest,
        capability_ids=capability_ids,
        maximum_authority=maximum_authority,
        persistent_service=persistent_service,
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value
