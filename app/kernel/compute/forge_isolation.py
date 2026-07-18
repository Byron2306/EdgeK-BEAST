"""Isolation admission contract shared by Compute Forge nodes and scheduler."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import time
from typing import Any, Mapping

from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class ForgeIsolationAttestation:
    node_id: str
    worker_digest: str
    launch_receipt_digest: str
    delegation_receipt_digest: str
    race_free_cgroup_birth: bool
    namespace_isolation: bool
    filesystem_secret_isolation: bool
    cleanup_confirmed: bool
    enabled_controllers: tuple[str, ...]
    missing_controllers: tuple[str, ...]
    authority_mode: str
    attested_at: float = 0.0
    expires_at: float = 0.0
    attestation_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("attestation_digest", None)
        return value

    def sealed(self) -> "ForgeIsolationAttestation":
        return replace(self, attestation_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.attestation_digest != content_hash(self.content_payload()):
            raise ValueError("forge isolation attestation is tampered")
        if self.authority_mode == "isolated_execute" and not all((
            self.race_free_cgroup_birth,
            self.namespace_isolation,
            self.filesystem_secret_isolation,
            self.cleanup_confirmed,
        )):
            raise ValueError("isolated forge execution claim is incomplete")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"beast_object_type": "forge_isolation_attestation", "version": "1.0", **asdict(self)}

    @classmethod
    def from_receipts(
        cls,
        node_id: str,
        launch: Any,
        delegation: Any | None,
        *,
        required_controllers: tuple[str, ...] = ("cpu", "memory", "pids", "io"),
        ttl_seconds: float = 900.0,
    ) -> "ForgeIsolationAttestation":
        launch.validate()
        enabled = tuple(sorted(set(getattr(delegation, "enabled_controllers", ()))))
        missing = tuple(sorted(set(required_controllers) - set(enabled)))
        isolated = bool(
            launch.membership_observed_before_release
            and launch.combined_cgroup_namespace_proven
            and launch.filesystem_secret_isolation_proven
            and launch.root_cleanup_confirmed
        )
        now = time.time()
        value = cls(
            node_id=node_id,
            worker_digest=launch.worker_digest,
            launch_receipt_digest=launch.receipt_digest,
            delegation_receipt_digest=str(getattr(delegation, "receipt_digest", "")),
            race_free_cgroup_birth=bool(launch.membership_observed_before_release),
            namespace_isolation=bool(launch.combined_cgroup_namespace_proven),
            filesystem_secret_isolation=bool(launch.filesystem_secret_isolation_proven),
            cleanup_confirmed=bool(launch.root_cleanup_confirmed),
            enabled_controllers=enabled,
            missing_controllers=missing,
            authority_mode="isolated_execute" if isolated else "verify_only",
            attested_at=now,
            expires_at=now + max(1.0, float(ttl_seconds)),
        ).sealed()
        value.validate()
        return value


def forge_work_isolation_admitted(
    metadata: Mapping[str, Any] | None,
    attestation: Mapping[str, Any] | None,
) -> bool:
    metadata = metadata or {}
    if metadata.get("requires_isolation") is not True:
        return True
    if not isinstance(attestation, Mapping):
        return False
    required = set(metadata.get("required_controllers") or ())
    enabled = set(attestation.get("enabled_controllers") or ())
    return bool(
        attestation.get("authority_mode") == "isolated_execute"
        and attestation.get("race_free_cgroup_birth") is True
        and attestation.get("namespace_isolation") is True
        and attestation.get("filesystem_secret_isolation") is True
        and attestation.get("cleanup_confirmed") is True
        and required <= enabled
    )
