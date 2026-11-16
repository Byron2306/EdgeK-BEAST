"""Canonical protocol objects for constitutional DIO Commons online spaces."""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest
from app.kernel.dai.dio_distributed_quorum import DIOWitnessRole, public_key_b64, public_key_fingerprint


DIO_COMMONS_ONLINE_VERSION = "1.0"
ATTESTATION_CLASSES = frozenset({"signed_software_runtime", "provider_hardware_attestation", "ephemeral_build_provenance", "local_physical_witness"})


def _time(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} needs timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class DIOCommonsSpaceIdentity:
    beast_object_type: str
    version: str
    node_id: str
    role: DIOWitnessRole | str
    operator_root: str
    runtime_platform: str
    infrastructure_provider: str
    public_signing_key: str
    key_fingerprint: str
    verifier_digest: str
    capability_manifest_digest: str
    attestation_class: str
    maximum_authority: str
    governance_epoch: str
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_space_identity" or self.version != DIO_COMMONS_ONLINE_VERSION:
            raise ValueError("unexpected Commons online identity version")
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        if not all(str(item).strip() for item in (self.node_id, self.operator_root, self.runtime_platform, self.infrastructure_provider, self.public_signing_key, self.maximum_authority, self.governance_epoch)):
            raise ValueError("Commons identity requires non-empty constitutional fields")
        for name in ("key_fingerprint", "verifier_digest", "capability_manifest_digest"):
            require_digest(getattr(self, name), field_name=name)
        if self.key_fingerprint != public_key_fingerprint(self.public_signing_key):
            raise ValueError("Commons identity public key fingerprint mismatch")
        if self.attestation_class not in ATTESTATION_CLASSES:
            raise ValueError("unknown Commons attestation class")
        if self.production_authority_allowed:
            raise ValueError("online Commons identity cannot grant production authority")

    @property
    def identity_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCommonsCapabilityManifest:
    beast_object_type: str
    version: str
    node_id: str
    verifier_digest: str
    capability_ids: tuple[str, ...]
    maximum_authority: str
    persistent_service: bool
    provider_calls_used: int = 0
    execution_authority_allowed: bool = False
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_capability_manifest" or self.version != DIO_COMMONS_ONLINE_VERSION:
            raise ValueError("unexpected Commons manifest version")
        require_digest(self.verifier_digest, field_name="verifier_digest")
        if not self.node_id or not self.capability_ids or self.provider_calls_used != 0:
            raise ValueError("Commons manifest requires node capabilities and zero provider calls")
        if self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("Commons manifest cannot grant execution or production authority")

    @property
    def manifest_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCommonsChallenge:
    beast_object_type: str
    version: str
    proposal_digest: str
    evidence_root: str
    world_state_hash: str
    governance_epoch: str
    challenge_nonce: str
    issued_at: str
    expires_at: str

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_challenge" or self.version != DIO_COMMONS_ONLINE_VERSION:
            raise ValueError("unexpected Commons challenge version")
        for name in ("proposal_digest", "evidence_root", "world_state_hash"):
            require_digest(getattr(self, name), field_name=name)
        if len(self.challenge_nonce) < 16 or _time(self.expires_at, "expires_at") <= _time(self.issued_at, "issued_at"):
            raise ValueError("invalid Commons challenge freshness")

    def is_fresh(self, now: datetime) -> bool:
        return _time(self.issued_at, "issued_at") <= now < _time(self.expires_at, "expires_at")

    @property
    def challenge_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCommonsActiveLease:
    beast_object_type: str
    version: str
    node_id: str
    identity_digest: str
    manifest_digest: str
    challenge_digest: str
    governance_epoch: str
    issued_at: str
    expires_at: str
    coordinator_public_key: str
    coordinator_signature: str
    maximum_authority: str
    execution_authority_allowed: bool = False
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_active_lease" or self.version != DIO_COMMONS_ONLINE_VERSION:
            raise ValueError("unexpected Commons lease version")
        for name in ("identity_digest", "manifest_digest", "challenge_digest"):
            require_digest(getattr(self, name), field_name=name)
        if _time(self.expires_at, "expires_at") <= _time(self.issued_at, "issued_at"):
            raise ValueError("Commons lease expires before issuance")
        if self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("Commons lease cannot grant execution or production authority")

    @property
    def signing_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coordinator_signature"] = ""
        return payload

    @property
    def lease_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCommonsRegisteredSpace:
    node_id: str
    role: DIOWitnessRole | str
    operator_root: str
    key_fingerprint: str
    verifier_digest: str
    capability_manifest_digest: str
    attestation_class: str
    maximum_authority: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        if not all(str(item).strip() for item in (self.node_id, self.operator_root, self.maximum_authority)):
            raise ValueError("registered Commons space requires non-empty identity fields")
        for name in ("key_fingerprint", "verifier_digest", "capability_manifest_digest"):
            require_digest(getattr(self, name), field_name=name)
        if self.attestation_class not in ATTESTATION_CLASSES:
            raise ValueError("registered Commons space has unknown attestation class")


@dataclass(frozen=True, slots=True)
class DIOCommonsAdmissionPolicy:
    beast_object_type: str
    version: str
    governance_epoch: str
    coordinator_public_key: str
    registered_spaces: tuple[DIOCommonsRegisteredSpace, ...]
    required_unique_roles: tuple[DIOWitnessRole | str, ...]
    permitted_attestation_classes: tuple[str, ...] = tuple(sorted(ATTESTATION_CLASSES))
    maximum_lease_seconds: int = 300

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_admission_policy" or self.version != DIO_COMMONS_ONLINE_VERSION:
            raise ValueError("unexpected Commons admission policy version")
        if not self.governance_epoch.strip() or self.maximum_lease_seconds <= 0:
            raise ValueError("Commons admission policy requires epoch and positive lease duration")
        public_key_fingerprint(self.coordinator_public_key)
        roles = tuple(role if isinstance(role, DIOWitnessRole) else DIOWitnessRole(role) for role in self.required_unique_roles)
        object.__setattr__(self, "required_unique_roles", roles)
        if any(item not in ATTESTATION_CLASSES for item in self.permitted_attestation_classes):
            raise ValueError("Commons policy permits unknown attestation class")
        if not self.registered_spaces:
            raise ValueError("Commons policy requires registered spaces")
        if len({item.node_id for item in self.registered_spaces}) != len(self.registered_spaces):
            raise ValueError("Commons policy cannot register duplicate node ids")
        if len({item.key_fingerprint for item in self.registered_spaces}) != len(self.registered_spaces):
            raise ValueError("Commons policy cannot register duplicate signing keys")
        if len({item.operator_root for item in self.registered_spaces}) != len(self.registered_spaces):
            raise ValueError("Commons policy cannot register duplicate operator roots")

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DIOCommonsAdmissionReport:
    beast_object_type: str
    version: str
    node_id: str
    role: DIOWitnessRole | str
    identity_digest: str
    manifest_digest: str
    challenge_digest: str
    policy_digest: str
    governance_epoch: str
    attestation_class: str
    active_lease_digest: str
    red_gates: tuple[str, ...]
    admitted: bool
    execution_authority_allowed: bool = False
    production_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dio_commons_admission_report" or self.version != DIO_COMMONS_ONLINE_VERSION:
            raise ValueError("unexpected Commons admission report version")
        if not isinstance(self.role, DIOWitnessRole):
            object.__setattr__(self, "role", DIOWitnessRole(self.role))
        for name in ("identity_digest", "manifest_digest", "challenge_digest", "policy_digest"):
            require_digest(getattr(self, name), field_name=name)
        if self.active_lease_digest:
            require_digest(self.active_lease_digest, field_name="active_lease_digest")
        if self.execution_authority_allowed or self.production_authority_allowed:
            raise ValueError("Commons admission report cannot grant execution or production authority")

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def sign_commons_identity(identity: DIOCommonsSpaceIdentity, key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.sign(canonical_json(asdict(identity)).encode("utf-8"))).decode("ascii")


def verify_commons_identity(identity: DIOCommonsSpaceIdentity, signature: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(identity.public_signing_key, validate=True)).verify(base64.b64decode(signature, validate=True), canonical_json(asdict(identity)).encode("utf-8"))
        return True
    except Exception:
        return False


def issue_commons_lease(identity: DIOCommonsSpaceIdentity, manifest: DIOCommonsCapabilityManifest, challenge: DIOCommonsChallenge, coordinator: Ed25519PrivateKey, *, issued_at: str, expires_at: str) -> DIOCommonsActiveLease:
    if identity.node_id != manifest.node_id or identity.verifier_digest != manifest.verifier_digest or identity.capability_manifest_digest != manifest.manifest_digest:
        raise ValueError("identity and manifest are not bound")
    if identity.governance_epoch != challenge.governance_epoch:
        raise ValueError("identity governance epoch does not bind challenge")
    unsigned = DIOCommonsActiveLease("dio_commons_active_lease", DIO_COMMONS_ONLINE_VERSION, identity.node_id, identity.identity_digest, manifest.manifest_digest, challenge.challenge_digest, challenge.governance_epoch, issued_at, expires_at, base64.b64encode(coordinator.public_key().public_bytes_raw()).decode("ascii"), "", identity.maximum_authority)
    signature = base64.b64encode(coordinator.sign(canonical_json(unsigned.signing_payload).encode("utf-8"))).decode("ascii")
    return DIOCommonsActiveLease(**{**asdict(unsigned), "coordinator_signature": signature})


def verify_commons_lease(lease: DIOCommonsActiveLease, *, now: datetime) -> bool:
    try:
        if not (_time(lease.issued_at, "issued_at") <= now < _time(lease.expires_at, "expires_at")):
            return False
        Ed25519PublicKey.from_public_bytes(base64.b64decode(lease.coordinator_public_key, validate=True)).verify(base64.b64decode(lease.coordinator_signature, validate=True), canonical_json(lease.signing_payload).encode("utf-8"))
        return True
    except Exception:
        return False


def admit_commons_online_space(
    *,
    identity: DIOCommonsSpaceIdentity,
    identity_signature: str,
    manifest: DIOCommonsCapabilityManifest,
    challenge: DIOCommonsChallenge,
    policy: DIOCommonsAdmissionPolicy,
    coordinator: Ed25519PrivateKey,
    now: datetime,
    active_identities: Iterable[DIOCommonsSpaceIdentity] = (),
    active_leases: Iterable[DIOCommonsActiveLease] = (),
    lease_seconds: int = 120,
) -> tuple[DIOCommonsAdmissionReport, DIOCommonsActiveLease | None]:
    """Admit one online Commons node and mint a bounded lease only if all laws pass."""

    red: set[str] = set()
    active_identity_rows = tuple(active_identities)
    active_lease_rows = tuple(active_leases)
    registered = {item.node_id: item for item in policy.registered_spaces}
    registration = registered.get(identity.node_id)

    if public_key_b64(coordinator.public_key()) != policy.coordinator_public_key:
        red.add("coordinator_key_matches_policy")
    if not verify_commons_identity(identity, identity_signature):
        red.add("identity_signature_valid")
    if identity.governance_epoch != policy.governance_epoch or challenge.governance_epoch != policy.governance_epoch:
        red.add("current_governance_epoch")
    if not challenge.is_fresh(now):
        red.add("challenge_fresh")
    if lease_seconds <= 0 or lease_seconds > policy.maximum_lease_seconds:
        red.add("lease_duration_bounded")
    if identity.node_id != manifest.node_id:
        red.add("manifest_node_matches_identity")
    if identity.verifier_digest != manifest.verifier_digest:
        red.add("manifest_verifier_matches_identity")
    if identity.capability_manifest_digest != manifest.manifest_digest:
        red.add("identity_binds_manifest_digest")
    if identity.attestation_class not in policy.permitted_attestation_classes:
        red.add("attestation_class_permitted")
    if identity.role not in policy.required_unique_roles:
        red.add("required_role_registered")

    if registration is None:
        red.add("node_registered")
    else:
        expected = {
            "registered_role_bound": identity.role == registration.role,
            "registered_operator_root_bound": identity.operator_root == registration.operator_root,
            "registered_key_bound": identity.key_fingerprint == registration.key_fingerprint,
            "registered_verifier_bound": identity.verifier_digest == registration.verifier_digest,
            "registered_manifest_bound": identity.capability_manifest_digest == registration.capability_manifest_digest,
            "registered_attestation_class_bound": identity.attestation_class == registration.attestation_class,
            "registered_authority_ceiling_bound": identity.maximum_authority == registration.maximum_authority,
        }
        red.update(name for name, passed in expected.items() if not passed)

    active_nodes = {item.node_id for item in active_identity_rows}
    active_keys = {item.key_fingerprint for item in active_identity_rows}
    active_operators = {item.operator_root for item in active_identity_rows}
    active_roles = {item.role for item in active_identity_rows}
    if identity.node_id in active_nodes:
        red.add("node_not_already_active")
    if identity.key_fingerprint in active_keys:
        red.add("signing_key_not_already_active")
    if identity.operator_root in active_operators:
        red.add("operator_root_not_already_active")
    if identity.role in active_roles:
        red.add("role_not_already_active")

    for lease in active_lease_rows:
        if not verify_commons_lease(lease, now=now):
            red.add("active_lease_verifies")
        if lease.node_id == identity.node_id and verify_commons_lease(lease, now=now):
            red.add("node_has_no_unexpired_lease")

    lease: DIOCommonsActiveLease | None = None
    if not red:
        issued_at = now.astimezone(timezone.utc).isoformat()
        expires_at = (now.astimezone(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        try:
            lease = issue_commons_lease(identity, manifest, challenge, coordinator, issued_at=issued_at, expires_at=expires_at)
        except Exception:
            red.add("lease_issuance")
        else:
            if not verify_commons_lease(lease, now=now):
                red.add("issued_lease_verifies")
                lease = None

    report = DIOCommonsAdmissionReport(
        beast_object_type="dio_commons_admission_report",
        version=DIO_COMMONS_ONLINE_VERSION,
        node_id=identity.node_id,
        role=identity.role,
        identity_digest=identity.identity_digest,
        manifest_digest=manifest.manifest_digest,
        challenge_digest=challenge.challenge_digest,
        policy_digest=policy.policy_digest,
        governance_epoch=policy.governance_epoch,
        attestation_class=identity.attestation_class,
        active_lease_digest=lease.lease_digest if lease else "",
        red_gates=tuple(sorted(red)),
        admitted=not red and lease is not None,
    )
    return report, lease
