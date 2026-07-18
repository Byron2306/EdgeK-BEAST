"""Authorized creation of cgroup v2 mission subtrees without overclaiming delegation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from app.kernel.execution.cgroup_capsule import CgroupAuthorization, CgroupMissionCapsule, CgroupV2Discovery
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.sensorium.contracts import ProcessLease


@dataclass(frozen=True)
class CgroupDelegationReceipt:
    mission_id: str
    parent_path: str
    requested_controllers: tuple[str, ...]
    available_controllers: tuple[str, ...]
    enabled_controllers: tuple[str, ...]
    parent_populated: bool
    capsule_created: bool
    full_controller_delegation: bool
    reason: str
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def sealed(self) -> "CgroupDelegationReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))


class CgroupDelegationManager:
    def __init__(self, parent: Path, *, sensorium: SensoriumRuntime | None = None, synthetic: bool = False):
        self.parent = Path(parent)
        self.sensorium = sensorium
        self.synthetic = synthetic

    def prepare(
        self,
        mission_id: str,
        controllers: Iterable[str],
        authorization: CgroupAuthorization,
    ) -> tuple[CgroupMissionCapsule | None, CgroupDelegationReceipt]:
        authorization.require("delegate", mission_id)
        requested = tuple(sorted(set(str(item) for item in controllers)))
        if not requested or any(item not in {"cpu", "memory", "pids", "io"} for item in requested):
            raise ValueError("delegation controllers are empty or unsupported")
        discovery = CgroupV2Discovery(self.parent).state()
        available = tuple(discovery["controllers"])
        enabled = set(discovery["delegated_controllers"])
        missing_available = set(requested) - set(available)
        parent_members = self._member_pids(self.parent / "cgroup.procs")
        reason = "delegated_controllers_ready"
        capsule: CgroupMissionCapsule | None = None
        if missing_available:
            reason = "requested_controllers_unavailable"
        else:
            missing_enabled = set(requested) - enabled
            if missing_enabled and parent_members:
                reason = "populated_parent_blocks_domain_controller_enablement"
            elif missing_enabled:
                control = self.parent / "cgroup.subtree_control"
                control.write_text(" ".join(f"+{item}" for item in sorted(missing_enabled)) + "\n", encoding="utf-8")
                # Synthetic files do not implement kernel '+' semantics.
                enabled = set(requested) if self.synthetic else set(CgroupV2Discovery(self.parent).state()["delegated_controllers"])
                if set(requested) - enabled:
                    reason = "controller_enablement_not_confirmed"
            if set(requested) <= enabled:
                capsule = CgroupMissionCapsule(self.parent, mission_id, sensorium=self.sensorium, synthetic=self.synthetic)
                capsule.create(CgroupAuthorization(
                    action="create",
                    mission_id=mission_id,
                    approved_by=authorization.approved_by,
                    approval_receipt_id=authorization.approval_receipt_id,
                    reason=authorization.reason,
                ))
                if not self.synthetic:
                    intermediate = capsule.path.parent
                    intermediate_control = intermediate / "cgroup.subtree_control"
                    intermediate_control.write_text(
                        " ".join(f"+{item}" for item in requested) + "\n", encoding="utf-8"
                    )
                    intermediate_enabled = set(
                        item.lstrip("+") for item in intermediate_control.read_text(encoding="utf-8").split()
                    )
                    required_files = {
                        "cpu": "cpu.max", "memory": "memory.max",
                        "pids": "pids.max", "io": "io.max",
                    }
                    if set(requested) - intermediate_enabled or any(
                        not (capsule.path / required_files[item]).exists() for item in requested
                    ):
                        reason = "intermediate_controller_enablement_not_confirmed"
                        capsule = None
        full = bool(capsule is not None and set(requested) <= enabled)
        receipt = CgroupDelegationReceipt(
            mission_id, str(self.parent), requested, available, tuple(sorted(enabled)),
            bool(parent_members), capsule is not None, full, reason,
        ).sealed()
        if self.sensorium is not None:
            self.sensorium.observe_physical(
                event_type="isolation.cgroup_delegated" if full else "isolation.cgroup_reduced",
                source="cgroup_delegation_manager",
                payload_schema="beast.sensor.isolation.cgroup.v1",
                operation="isolation.cgroup_delegate",
                phase="verification",
                subject=f"mission:{mission_id}",
                result="success" if full else "refused",
                payload={
                    "receipt_digest": receipt.receipt_digest,
                    "requested_controllers": list(requested),
                    "enabled_controllers": list(receipt.enabled_controllers),
                    "parent_populated": receipt.parent_populated,
                    "reason": reason,
                    "reads": [f"cgroup_delegation:{self.parent}"],
                    "produces": [f"cgroup_delegation_receipt:{receipt.receipt_digest}"],
                },
                mission_id=mission_id,
                confidence_method="cgroup_v2_readback",
            )
        return capsule, receipt

    def prepare_with_owned_anchor(
        self,
        mission_id: str,
        controllers: Iterable[str],
        anchor: ProcessLease,
        supervisor: Any,
        authorization: CgroupAuthorization,
    ) -> tuple[CgroupMissionCapsule | None, CgroupDelegationReceipt]:
        """Evacuate the exact owned anchor before enabling domain controls."""
        authorization.require("delegate", mission_id)
        anchor.validate()
        expected_parent = Path("/sys/fs/cgroup") / anchor.cgroup_id.lstrip("/")
        if not self.synthetic and expected_parent.resolve() != self.parent.resolve():
            raise PermissionError("anchor ProcessLease is not bound to delegation root")
        if not supervisor.verify(anchor.lease_id):
            raise ProcessLookupError("delegation anchor is stale before evacuation")
        members = self._member_pids(self.parent / "cgroup.procs")
        if members != (anchor.pid_at_observation,):
            raise PermissionError("delegation root contains tasks beyond the owned anchor")
        leaf = self.parent / "beast-anchor"
        leaf.mkdir(exist_ok=False)
        try:
            procs = leaf / "cgroup.procs"
            if self.synthetic:
                procs.write_text("", encoding="utf-8")
            procs.write_text(f"{anchor.pid_at_observation}\n", encoding="utf-8")
            if self.synthetic:
                (self.parent / "cgroup.procs").write_text("", encoding="utf-8")
            if self.synthetic:
                if not supervisor.verify(anchor.lease_id):
                    raise ProcessLookupError("delegation anchor changed during evacuation")
            else:
                successor = supervisor.collector.collect(
                    anchor.pid_at_observation, owner_scope=anchor.owner_scope
                )
                continuity_fields = (
                    "boot_id", "pid_at_observation", "start_time_ticks",
                    "executable_digest", "pid_namespace_inode", "mount_namespace_inode",
                    "parent_identity_hash", "owner_scope",
                )
                if any(getattr(successor, field) != getattr(anchor, field) for field in continuity_fields):
                    raise ProcessLookupError("delegation anchor identity changed during evacuation")
                expected_cgroup = anchor.cgroup_id.rstrip("/") + "/beast-anchor"
                if successor.cgroup_id != expected_cgroup:
                    raise ProcessLookupError("delegation anchor successor cgroup mismatch")
            if anchor.pid_at_observation not in self._member_pids(procs):
                raise RuntimeError("anchor membership was not observed in delegation leaf")
            if self._member_pids(self.parent / "cgroup.procs"):
                raise RuntimeError("delegation root remained populated after anchor evacuation")
            return self.prepare(mission_id, controllers, authorization)
        except Exception:
            if self.synthetic:
                for child in leaf.iterdir():
                    if child.is_file():
                        child.unlink()
                leaf.rmdir()
            raise

    @staticmethod
    def _member_pids(path: Path) -> tuple[int, ...]:
        try:
            return tuple(sorted(int(row) for row in path.read_text(encoding="utf-8").split() if int(row) > 0))
        except (OSError, ValueError):
            return ()
