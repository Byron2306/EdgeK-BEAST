"""Fail-closed, proof-carrying retirement of an owned stale listener."""

from __future__ import annotations

import signal
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Mapping

from app.kernel.execution.process_supervisor import (
    ProcessLeaseSupervisor,
    ProcessSignalAuthorization,
)
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.contracts import ProcessLease
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.execution.process_descendants import LinuxProcessDescendantInspector
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.execution.destructive_authority import DestructiveAuthorityVerifier


RETIRE_PROCESS_AUTHORITY = "beast.process.retire"
RETIRE_PROCESS_AUDIENCE = "beast-stale-process-retirement"


@dataclass(frozen=True)
class StaleProcessRetirementRequest:
    mission_id: str
    lease_id: str
    executable_digest: str
    cgroup_id: str
    pid_namespace_inode: int
    mount_namespace_inode: int
    owner_scope: str
    workspace_identity: str
    service_id: str
    registry_digest: str
    listener_generation: int
    policy_generation: str
    appraisal_ref: str
    reason: str

    def validate(self) -> None:
        if not all((
            self.mission_id, self.lease_id, self.executable_digest,
            self.cgroup_id, self.owner_scope, self.workspace_identity,
            self.service_id, self.registry_digest, self.policy_generation,
            self.appraisal_ref, self.reason,
        )):
            raise ValueError("stale-process retirement request is incomplete")
        if self.listener_generation < 1:
            raise ValueError("listener generation must be positive")

    @property
    def request_digest(self) -> str:
        self.validate()
        return content_hash(asdict(self))


@dataclass(frozen=True)
class StaleProcessRetirementReceipt:
    request_digest: str
    lease_id: str
    capability_id: str
    operator_approval_id: str
    appraisal_ref: str
    identity_revalidated: bool
    targeted_via: str
    graceful_exit_observed: bool
    listener_retired: bool
    replacement_listener_identity: str
    replacement_healthy: bool
    orphan_descendants_absent: bool
    final_status: str
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def sealed(self) -> "StaleProcessRetirementReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("stale-process retirement receipt is tampered")
        if self.final_status == "verified_stale_process_retirement" and not all((
            self.identity_revalidated,
            self.targeted_via == "pidfd",
            self.graceful_exit_observed,
            self.listener_retired,
            self.replacement_listener_identity,
            self.replacement_healthy,
            self.orphan_descendants_absent,
        )):
            raise ValueError("verified retirement receipt is incomplete")


class StaleProcessRetirementCoordinator:
    """Consumes exact authority and permits only graceful pidfd retirement.

    Escalation to ``cgroup.kill`` deliberately remains a distinct operation
    with a separate destructive receipt at the cgroup capsule boundary.
    """

    def __init__(
        self,
        supervisor: ProcessLeaseSupervisor,
        capability_ledger: OneUseCapabilityLedger,
        *,
        current_registry_digest: Callable[[], str],
        current_listener_generation: Callable[[str], int],
        listener_is_retired: Callable[[StaleProcessRetirementRequest], bool],
        start_replacement: Callable[[StaleProcessRetirementRequest], str],
        replacement_is_healthy: Callable[[str], bool],
        orphan_descendants_absent: Callable[[StaleProcessRetirementRequest], bool],
        prepare_physical_boundary: Callable[[StaleProcessRetirementRequest], None] | None = None,
        descendant_inspector: LinuxProcessDescendantInspector | None = None,
        sensorium: SensoriumRuntime | None = None,
        authority_verifier: DestructiveAuthorityVerifier | None = None,
    ):
        self.supervisor = supervisor
        self.capability_ledger = capability_ledger
        self.current_registry_digest = current_registry_digest
        self.current_listener_generation = current_listener_generation
        self.listener_is_retired = listener_is_retired
        self.start_replacement = start_replacement
        self.replacement_is_healthy = replacement_is_healthy
        self.orphan_descendants_absent = orphan_descendants_absent
        self.prepare_physical_boundary = prepare_physical_boundary
        self.descendant_inspector = descendant_inspector
        self.sensorium = sensorium
        self.authority_verifier = authority_verifier

    def retire(
        self,
        lease: ProcessLease,
        request: StaleProcessRetirementRequest,
        *,
        operator_approval: Mapping[str, Any],
        arda_appraisal: Mapping[str, Any],
        one_use_capability: Mapping[str, Any],
        timeout_seconds: float = 2.0,
        now: float | None = None,
    ) -> StaleProcessRetirementReceipt:
        try:
            return self._retire(
                lease,
                request,
                operator_approval=operator_approval,
                arda_appraisal=arda_appraisal,
                one_use_capability=one_use_capability,
                timeout_seconds=timeout_seconds,
                now=now,
            )
        except Exception as exc:
            self._observe(
                request,
                event_type="process.stale_retirement_refused",
                operation="process.stale_retire",
                phase="refusal",
                result="refused",
                payload={
                    "error_type": type(exc).__name__,
                    "message_retained": False,
                    "reads": [f"process_lease:{request.lease_id}"],
                    "produces": [f"retirement_refusal:{request.lease_id}"],
                    "descriptor_refs": [request.lease_id],
                },
            )
            raise

    def _retire(
        self,
        lease: ProcessLease,
        request: StaleProcessRetirementRequest,
        *,
        operator_approval: Mapping[str, Any],
        arda_appraisal: Mapping[str, Any],
        one_use_capability: Mapping[str, Any],
        timeout_seconds: float = 2.0,
        now: float | None = None,
    ) -> StaleProcessRetirementReceipt:
        request.validate()
        lease.validate()
        if self.prepare_physical_boundary is not None:
            self.prepare_physical_boundary(request)
        self._validate_binding(lease, request)
        if self.authority_verifier is not None:
            self.authority_verifier.verify(
                operator_approval=operator_approval,
                arda_appraisal=arda_appraisal,
                action_authority=RETIRE_PROCESS_AUTHORITY,
                request_digest=request.request_digest,
                audience=RETIRE_PROCESS_AUDIENCE,
                policy_generation=request.policy_generation,
                appraisal_ref=request.appraisal_ref,
                now=now,
            )
        approval_id = self._validate_operator(operator_approval, request)
        self._validate_arda(arda_appraisal, request, now=now)
        if self.current_registry_digest() != request.registry_digest:
            raise PermissionError("service registry drifted before retirement")
        if self.current_listener_generation(request.service_id) != request.listener_generation:
            raise PermissionError("listener generation drifted before retirement")
        if not self.supervisor.verify(lease.lease_id):
            raise ProcessLookupError("process lease is stale before authority consumption")
        descendant_snapshot = (
            self.descendant_inspector.capture(lease)
            if self.descendant_inspector is not None else None
        )
        if descendant_snapshot is not None and not descendant_snapshot.scan_complete:
            raise RuntimeError("governed descendant scan was incomplete before retirement")
        if descendant_snapshot is not None:
            self._observe(
                request,
                event_type="process.descendants_snapshotted",
                operation="process.descendants.snapshot",
                phase="observation",
                result="observed",
                payload={
                    "snapshot_digest": descendant_snapshot.snapshot_digest,
                    "descendant_lease_ids": [item.lease_id for item in descendant_snapshot.descendant_leases],
                    "scan_complete": descendant_snapshot.scan_complete,
                    "reads": [f"process_tree:{lease.lease_id}"],
                    "produces": [f"descendant_snapshot:{descendant_snapshot.snapshot_digest}"],
                    "descriptor_refs": [lease.lease_id, *[item.lease_id for item in descendant_snapshot.descendant_leases]],
                },
            )

        capability = self.capability_ledger.consume(
            one_use_capability,
            request_digest=request.request_digest,
            authority=RETIRE_PROCESS_AUTHORITY,
            now=now,
            expected_audience=RETIRE_PROCESS_AUDIENCE,
            expected_policy_generation=request.policy_generation,
            expected_appraisal_ref=request.appraisal_ref,
        )
        signal_receipt = self.supervisor.send_signal(
            lease.lease_id,
            signal.SIGTERM,
            ProcessSignalAuthorization(
                lease_id=lease.lease_id,
                signal_number=signal.SIGTERM,
                approved_by=str(operator_approval["approved_by"]),
                approval_receipt_id=approval_id,
                reason=request.reason,
            ),
            mission_id=request.mission_id,
        )

        exited = False
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            if any(item.lease_id == lease.lease_id for item in self.supervisor.poll(timeout=0.05)):
                exited = True
                break
        if not exited:
            raise RuntimeError("graceful retirement timed out; separate cgroup authority required")
        if not self.listener_is_retired(request):
            raise RuntimeError("listener remained after process exit")
        descendants_absent = (
            self.descendant_inspector.absence(descendant_snapshot)
            if self.descendant_inspector is not None and descendant_snapshot is not None
            else self.orphan_descendants_absent(request)
        )
        if not descendants_absent:
            raise RuntimeError("governed orphan descendants remain after retirement")
        replacement_identity = self.start_replacement(request)
        if not replacement_identity:
            raise RuntimeError("replacement listener identity was not produced")
        healthy = bool(self.replacement_is_healthy(replacement_identity))
        if not healthy:
            raise RuntimeError("replacement listener failed health verification")

        receipt = StaleProcessRetirementReceipt(
            request_digest=request.request_digest,
            lease_id=lease.lease_id,
            capability_id=capability.capability_id,
            operator_approval_id=approval_id,
            appraisal_ref=request.appraisal_ref,
            identity_revalidated=bool(signal_receipt.get("identity_revalidated_immediately_before_signal")),
            targeted_via=str(signal_receipt.get("targeted_via") or ""),
            graceful_exit_observed=True,
            listener_retired=True,
            replacement_listener_identity=replacement_identity,
            replacement_healthy=True,
            orphan_descendants_absent=True,
            final_status="verified_stale_process_retirement",
        ).sealed()
        receipt.validate()
        self._observe(
            request,
            event_type="process.stale_retirement_verified",
            operation="process.stale_retire",
            phase="verification",
            result="success",
            payload={
                "request_digest": request.request_digest,
                "receipt_digest": receipt.receipt_digest,
                "capability_id": receipt.capability_id,
                "targeted_via": receipt.targeted_via,
                "replacement_listener_identity": receipt.replacement_listener_identity,
                "reads": [f"process_lease:{lease.lease_id}", f"service_registry:{request.registry_digest}"],
                "writes": [f"process_state:{lease.lease_id}"],
                "produces": [f"retirement_receipt:{receipt.receipt_digest}"],
                "descriptor_refs": [lease.lease_id, receipt.replacement_listener_identity],
                "state_transition": {"resource": f"process:{lease.lease_id}", "from": "stale_listener", "to": "exited"},
            },
        )
        return receipt

    def _observe(
        self,
        request: StaleProcessRetirementRequest,
        *,
        event_type: str,
        operation: str,
        phase: str,
        result: str,
        payload: Mapping[str, Any],
    ) -> None:
        if self.sensorium is None:
            return
        self.sensorium.observe_physical(
            event_type=event_type,
            source="stale_process_retirement",
            payload_schema=f"beast.sensor.{event_type}.v1",
            operation=operation,
            phase=phase,
            subject=f"process_lease:{request.lease_id}",
            result=result,
            payload=dict(payload),
            mission_id=request.mission_id,
            workspace_id=request.workspace_identity,
            confidence_method="content_bound_pidfd_and_kernel_observation",
        )

    @staticmethod
    def _validate_binding(lease: ProcessLease, request: StaleProcessRetirementRequest) -> None:
        expected = (
            (lease.lease_id, request.lease_id),
            (lease.executable_digest, request.executable_digest),
            (lease.cgroup_id, request.cgroup_id),
            (lease.pid_namespace_inode, request.pid_namespace_inode),
            (lease.mount_namespace_inode, request.mount_namespace_inode),
            (lease.owner_scope, request.owner_scope),
        )
        if any(actual != declared for actual, declared in expected):
            raise PermissionError("process ownership binding mismatch")
        if lease.owner_scope not in {"beast_mission", "beast_service"}:
            raise PermissionError("process owner scope is not destructively manageable")

    @staticmethod
    def _validate_operator(approval: Mapping[str, Any], request: StaleProcessRetirementRequest) -> str:
        approval_id = str(approval.get("approval_receipt_id") or "")
        if (
            not approval_id
            or not approval.get("approved_by")
            or approval.get("request_digest") != request.request_digest
            or approval.get("action") != RETIRE_PROCESS_AUTHORITY
            or approval.get("destructive") is not True
        ):
            raise PermissionError("exact destructive operator approval is required")
        return approval_id

    @staticmethod
    def _validate_arda(appraisal: Mapping[str, Any], request: StaleProcessRetirementRequest, *, now: float | None) -> None:
        wall_now = time.time() if now is None else float(now)
        if (
            appraisal.get("appraisal_ref") != request.appraisal_ref
            or appraisal.get("request_digest") != request.request_digest
            or appraisal.get("policy_generation") != request.policy_generation
            or appraisal.get("audience") != RETIRE_PROCESS_AUDIENCE
            or appraisal.get("state") not in {"verified", "appraised"}
            or float(appraisal.get("expires_at") or 0) <= wall_now
        ):
            raise PermissionError("current ARDA destructive appraisal is required")
