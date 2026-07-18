"""Separately authorized, one-use cgroup.kill escalation boundary."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

from app.kernel.execution.cgroup_capsule import CgroupAuthorization, CgroupMissionCapsule
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.execution.destructive_authority import DestructiveAuthorityVerifier


CGROUP_KILL_AUTHORITY = "beast.cgroup.kill"
CGROUP_KILL_AUDIENCE = "beast-cgroup-kill-escalation"


@dataclass(frozen=True)
class CgroupKillEscalationRequest:
    mission_id: str
    retirement_request_digest: str
    cgroup_path: str
    expected_member_pids: tuple[int, ...]
    policy_generation: str
    appraisal_ref: str
    reason: str

    def validate(self) -> None:
        if not all((
            self.mission_id, self.retirement_request_digest, self.cgroup_path,
            self.policy_generation, self.appraisal_ref, self.reason,
        )):
            raise ValueError("cgroup kill escalation request is incomplete")
        if not self.expected_member_pids or any(pid <= 0 for pid in self.expected_member_pids):
            raise ValueError("cgroup kill requires exact positive expected members")
        if tuple(sorted(set(self.expected_member_pids))) != self.expected_member_pids:
            raise ValueError("expected cgroup members must be sorted and unique")

    @property
    def request_digest(self) -> str:
        self.validate()
        return content_hash(asdict(self))


@dataclass(frozen=True)
class CgroupKillEscalationReceipt:
    request_digest: str
    capability_id: str
    members_revalidated: bool
    kill_control_written: bool
    populated_zero_observed: bool
    final_status: str
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_digest", None)
        return value

    def sealed(self) -> "CgroupKillEscalationReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("cgroup kill escalation receipt is tampered")
        if self.final_status == "verified_cgroup_kill" and not (
            self.members_revalidated and self.kill_control_written and self.populated_zero_observed
        ):
            raise ValueError("verified cgroup kill receipt is incomplete")


class CgroupKillEscalationCoordinator:
    def __init__(self, capsule: CgroupMissionCapsule, ledger: OneUseCapabilityLedger, *, sensorium: SensoriumRuntime | None = None, authority_verifier: DestructiveAuthorityVerifier | None = None):
        self.capsule = capsule
        self.ledger = ledger
        self.sensorium = sensorium
        self.authority_verifier = authority_verifier

    def execute(
        self,
        request: CgroupKillEscalationRequest,
        *,
        operator_approval: Mapping[str, Any],
        arda_appraisal: Mapping[str, Any],
        one_use_capability: Mapping[str, Any],
        timeout_seconds: float = 2.0,
        now: float | None = None,
    ) -> CgroupKillEscalationReceipt:
        try:
            return self._execute(
                request,
                operator_approval=operator_approval,
                arda_appraisal=arda_appraisal,
                one_use_capability=one_use_capability,
                timeout_seconds=timeout_seconds,
                now=now,
            )
        except Exception as exc:
            if self.sensorium is not None:
                self.sensorium.observe_physical(
                    event_type="cgroup.kill_refused",
                    source="cgroup_kill_escalation",
                    payload_schema="beast.sensor.cgroup.kill_escalation.v1",
                    operation="cgroup.kill",
                    phase="refusal",
                    subject=f"cgroup:{request.mission_id}",
                    result="refused",
                    payload={
                        "error_type": type(exc).__name__,
                        "message_retained": False,
                        "reads": [f"cgroup_membership:{request.cgroup_path}"],
                        "produces": [f"cgroup_kill_refusal:{request.mission_id}"],
                        "descriptor_refs": [f"cgroup:{request.mission_id}"],
                    },
                    mission_id=request.mission_id,
                    confidence_method="fail_closed_destructive_boundary",
                )
            raise

    def _execute(
        self,
        request: CgroupKillEscalationRequest,
        *,
        operator_approval: Mapping[str, Any],
        arda_appraisal: Mapping[str, Any],
        one_use_capability: Mapping[str, Any],
        timeout_seconds: float = 2.0,
        now: float | None = None,
    ) -> CgroupKillEscalationReceipt:
        request.validate()
        if request.mission_id != self.capsule.mission_id or request.cgroup_path != str(self.capsule.path):
            raise PermissionError("cgroup escalation capsule binding mismatch")
        if self.authority_verifier is not None:
            self.authority_verifier.verify(
                operator_approval=operator_approval,
                arda_appraisal=arda_appraisal,
                action_authority=CGROUP_KILL_AUTHORITY,
                request_digest=request.request_digest,
                audience=CGROUP_KILL_AUDIENCE,
                policy_generation=request.policy_generation,
                appraisal_ref=request.appraisal_ref,
                now=now,
            )
        approval_id = self._validate_operator(operator_approval, request)
        self._validate_arda(arda_appraisal, request, now=now)
        expected = list(request.expected_member_pids)
        if self.capsule.member_pids() != expected:
            raise PermissionError("cgroup membership drifted before authority consumption")
        capability = self.ledger.consume(
            one_use_capability,
            request_digest=request.request_digest,
            authority=CGROUP_KILL_AUTHORITY,
            now=now,
            expected_audience=CGROUP_KILL_AUDIENCE,
            expected_policy_generation=request.policy_generation,
            expected_appraisal_ref=request.appraisal_ref,
        )
        # Revalidate after consumption and immediately before the destructive
        # kernel control write. A raced capability is safely spent, not retargeted.
        if self.capsule.member_pids() != expected:
            raise PermissionError("cgroup membership drifted before kill control write")
        kill_receipt = self.capsule.kill(CgroupAuthorization(
            action="kill",
            mission_id=request.mission_id,
            approved_by=str(operator_approval["approved_by"]),
            approval_receipt_id=approval_id,
            reason=request.reason,
            destructive=True,
        ))
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while not self.capsule.empty() and time.monotonic() < deadline:
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
        empty = self.capsule.empty()
        receipt = CgroupKillEscalationReceipt(
            request_digest=request.request_digest,
            capability_id=capability.capability_id,
            members_revalidated=True,
            kill_control_written=bool(kill_receipt.get("details", {}).get("requested")),
            populated_zero_observed=empty,
            final_status="verified_cgroup_kill" if empty else "cgroup_kill_unconfirmed",
        ).sealed()
        receipt.validate()
        if self.sensorium is not None:
            self.sensorium.observe_physical(
                event_type="cgroup.kill_verified" if empty else "cgroup.kill_unconfirmed",
                source="cgroup_kill_escalation",
                payload_schema="beast.sensor.cgroup.kill_escalation.v1",
                operation="cgroup.kill",
                phase="verification",
                subject=f"cgroup:{request.mission_id}",
                result="success" if empty else "failure",
                payload={
                    "request_digest": request.request_digest,
                    "receipt_digest": receipt.receipt_digest,
                    "expected_member_count": len(request.expected_member_pids),
                    "members_revalidated": True,
                    "populated_zero_observed": empty,
                    "reads": [f"cgroup_membership:{request.cgroup_path}"],
                    "writes": [f"cgroup_kill:{request.cgroup_path}"],
                    "produces": [f"cgroup_kill_receipt:{receipt.receipt_digest}"],
                    "descriptor_refs": [f"cgroup:{request.mission_id}"],
                },
                mission_id=request.mission_id,
                confidence_method="cgroup_v2_control_and_events",
            )
        return receipt

    @staticmethod
    def _validate_operator(approval: Mapping[str, Any], request: CgroupKillEscalationRequest) -> str:
        approval_id = str(approval.get("approval_receipt_id") or "")
        if (
            not approval_id or not approval.get("approved_by")
            or approval.get("request_digest") != request.request_digest
            or approval.get("action") != CGROUP_KILL_AUTHORITY
            or approval.get("destructive") is not True
        ):
            raise PermissionError("exact destructive cgroup operator approval is required")
        return approval_id

    @staticmethod
    def _validate_arda(appraisal: Mapping[str, Any], request: CgroupKillEscalationRequest, *, now: float | None) -> None:
        wall_now = time.time() if now is None else float(now)
        if (
            appraisal.get("appraisal_ref") != request.appraisal_ref
            or appraisal.get("request_digest") != request.request_digest
            or appraisal.get("policy_generation") != request.policy_generation
            or appraisal.get("audience") != CGROUP_KILL_AUDIENCE
            or appraisal.get("state") not in {"verified", "appraised"}
            or float(appraisal.get("expires_at") or 0) <= wall_now
        ):
            raise PermissionError("current ARDA cgroup-kill appraisal is required")
