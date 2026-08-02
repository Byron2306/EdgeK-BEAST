from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .state import ApprovalState, require_transition

CONTRACT_VERSION = "4.1"
REQUEST_OBJECT_TYPE = "beast_approval_request"
DECISION_OBJECT_TYPE = "beast_approval_decision"
TRANSITION_OBJECT_TYPE = "beast_approval_transition"


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    EDIT_AND_APPROVE = "EDIT_AND_APPROVE"
    REJECT = "REJECT"
    REQUEST_REPLAN = "REQUEST_REPLAN"
    PERMANENTLY_DENY = "PERMANENTLY_DENY"


class ApprovalScope(str, Enum):
    ONCE = "ONCE"
    EQUIVALENT_CALLS_THIS_RUN = "EQUIVALENT_CALLS_THIS_RUN"
    TOOL_SCOPE_THIS_WORKSPACE = "TOOL_SCOPE_THIS_WORKSPACE"
    READ_ONLY_THIS_TARGET = "READ_ONLY_THIS_TARGET"
    EDITED_SCOPE_ONCE = "EDITED_SCOPE_ONCE"


class RiskClass(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PermissionMode(str, Enum):
    REVIEW = "REVIEW"
    GUIDED = "GUIDED"
    BOUNDED_AUTONOMY = "BOUNDED_AUTONOMY"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    LOCKED = "LOCKED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(name: str, value: Any, *, maximum: int = 512) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    if len(text) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return text


def _string_list(name: str, value: Sequence[Any] | None, *, maximum: int = 128) -> list[str]:
    items = []
    for item in value or []:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    if len(items) > maximum:
        raise ValueError(f"{name} exceeds {maximum} entries")
    return items


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    run_id: str
    step_id: str
    agent_id: str
    model_id: str
    provider_id: str
    tool_id: str
    tool_version: str
    arguments: Mapping[str, Any]
    workspace_id: str
    execution_target: str
    affected_resources: tuple[str, ...]
    data_egress: tuple[str, ...]
    expected_side_effects: tuple[str, ...]
    risk_class: RiskClass
    reason: str
    budget_impact: Mapping[str, Any]
    expires_at: str
    evidence_policy: Mapping[str, Any]
    requested_scope: ApprovalScope
    permission_mode: PermissionMode
    policy_generation: str
    created_at: str
    state: ApprovalState = ApprovalState.REQUESTED
    version: str = CONTRACT_VERSION
    beast_object_type: str = REQUEST_OBJECT_TYPE
    request_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self)))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["request_digest"] = self.request_digest or sha256_digest(self.semantic_dict())
        return payload

    def verify(self) -> bool:
        return self.request_digest == sha256_digest(self.semantic_dict())


@dataclass(frozen=True)
class ApprovalDecisionRecord:
    approval_id: str
    request_digest: str
    operator_id: str
    decision: ApprovalDecision
    scope: ApprovalScope | None
    reason: str
    decided_at: str
    edited_arguments: Mapping[str, Any] = field(default_factory=dict)
    edited_resources: tuple[str, ...] = field(default_factory=tuple)
    policy_generation: str = ""
    version: str = CONTRACT_VERSION
    beast_object_type: str = DECISION_OBJECT_TYPE
    decision_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"decision_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["decision_digest"] = self.decision_digest or sha256_digest(self.semantic_dict())
        return payload

    def verify(self) -> bool:
        return self.decision_digest == sha256_digest(self.semantic_dict())


@dataclass(frozen=True)
class ApprovalTransition:
    approval_id: str
    request_digest: str
    from_state: ApprovalState
    to_state: ApprovalState
    actor: str
    reason: str
    occurred_at: str
    decision_digest: str = ""
    previous_transition_digest: str = ""
    version: str = CONTRACT_VERSION
    beast_object_type: str = TRANSITION_OBJECT_TYPE
    transition_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self)))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["transition_digest"] = self.transition_digest or sha256_digest(self.semantic_dict())
        return payload

    def verify(self) -> bool:
        return self.transition_digest == sha256_digest(self.semantic_dict())


class ApprovalContractFactory:
    def create_request(self, payload: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or _utcnow()
        expiry_seconds = int(payload.get("expiry_seconds") or 900)
        if expiry_seconds < 30 or expiry_seconds > 86400:
            raise ValueError("expiry_seconds must be between 30 and 86400")
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), Mapping) else {}
        request = ApprovalRequest(
            approval_id=_required_text("approval_id", payload.get("approval_id") or f"approval_{uuid4().hex}"),
            run_id=_required_text("run_id", payload.get("run_id")),
            step_id=_required_text("step_id", payload.get("step_id")),
            agent_id=_required_text("agent_id", payload.get("agent_id")),
            model_id=_required_text("model_id", payload.get("model_id")),
            provider_id=_required_text("provider_id", payload.get("provider_id")),
            tool_id=_required_text("tool_id", payload.get("tool_id")),
            tool_version=_required_text("tool_version", payload.get("tool_version")),
            arguments=canonicalize(arguments),
            workspace_id=_required_text("workspace_id", payload.get("workspace_id")),
            execution_target=_required_text("execution_target", payload.get("execution_target")),
            affected_resources=tuple(_string_list("affected_resources", payload.get("affected_resources"))),
            data_egress=tuple(_string_list("data_egress", payload.get("data_egress"))),
            expected_side_effects=tuple(_string_list("expected_side_effects", payload.get("expected_side_effects"))),
            risk_class=RiskClass(str(payload.get("risk_class") or "MEDIUM").upper()),
            reason=_required_text("reason", payload.get("reason"), maximum=2000),
            budget_impact=canonicalize(payload.get("budget_impact") if isinstance(payload.get("budget_impact"), Mapping) else {}),
            expires_at=_iso(now + timedelta(seconds=expiry_seconds)),
            evidence_policy=canonicalize(payload.get("evidence_policy") if isinstance(payload.get("evidence_policy"), Mapping) else {}),
            requested_scope=ApprovalScope(str(payload.get("requested_scope") or "ONCE").upper()),
            permission_mode=PermissionMode(str(payload.get("permission_mode") or "REVIEW").upper()),
            policy_generation=_required_text("policy_generation", payload.get("policy_generation")),
            created_at=_iso(now),
        )
        result = request.to_dict()
        if not verify_digest(semantic_payload(result), result["request_digest"]):
            raise RuntimeError("approval request digest generation failed")
        return result

    def create_decision(self, request: Mapping[str, Any], payload: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or _utcnow()
        self.validate_request(request)
        decision = ApprovalDecision(str(payload.get("decision") or "").upper())
        scope_raw = payload.get("scope")
        scope = ApprovalScope(str(scope_raw).upper()) if scope_raw else None
        if decision in {ApprovalDecision.APPROVE, ApprovalDecision.EDIT_AND_APPROVE} and scope is None:
            raise ValueError("approved decisions require an explicit bounded scope")
        if decision == ApprovalDecision.EDIT_AND_APPROVE and scope != ApprovalScope.EDITED_SCOPE_ONCE:
            raise ValueError("EDIT_AND_APPROVE requires EDITED_SCOPE_ONCE")
        if decision in {ApprovalDecision.REJECT, ApprovalDecision.REQUEST_REPLAN, ApprovalDecision.PERMANENTLY_DENY} and not str(payload.get("reason") or "").strip():
            raise ValueError("negative decisions require a reason")
        if decision == ApprovalDecision.PERMANENTLY_DENY and scope is not None:
            raise ValueError("permanent denial is policy state, not an approval scope")
        record = ApprovalDecisionRecord(
            approval_id=str(request["approval_id"]),
            request_digest=str(request["request_digest"]),
            operator_id=_required_text("operator_id", payload.get("operator_id")),
            decision=decision,
            scope=scope,
            reason=str(payload.get("reason") or "").strip(),
            decided_at=_iso(now),
            edited_arguments=canonicalize(payload.get("edited_arguments") if isinstance(payload.get("edited_arguments"), Mapping) else {}),
            edited_resources=tuple(_string_list("edited_resources", payload.get("edited_resources"))),
            policy_generation=_required_text("policy_generation", payload.get("policy_generation") or request.get("policy_generation")),
        )
        return record.to_dict()

    def create_transition(
        self,
        request: Mapping[str, Any],
        *,
        from_state: ApprovalState | str,
        to_state: ApprovalState | str,
        actor: str,
        reason: str,
        decision: Mapping[str, Any] | None = None,
        previous_transition_digest: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.validate_request(request)
        source, destination = require_transition(from_state, to_state)
        if decision:
            self.validate_decision(decision, request=request)
        transition = ApprovalTransition(
            approval_id=str(request["approval_id"]),
            request_digest=str(request["request_digest"]),
            from_state=source,
            to_state=destination,
            actor=_required_text("actor", actor),
            reason=str(reason or "").strip(),
            occurred_at=_iso(now or _utcnow()),
            decision_digest=str((decision or {}).get("decision_digest") or ""),
            previous_transition_digest=str(previous_transition_digest or ""),
        )
        return transition.to_dict()

    def validate_request(self, request: Mapping[str, Any]) -> None:
        if request.get("beast_object_type") != REQUEST_OBJECT_TYPE or str(request.get("version")) != CONTRACT_VERSION:
            raise ValueError("unsupported approval request contract")
        required = ("approval_id", "run_id", "step_id", "tool_id", "workspace_id", "execution_target", "policy_generation", "request_digest")
        for key in required:
            _required_text(key, request.get(key))
        if not verify_digest(semantic_payload(request), str(request.get("request_digest"))):
            raise ValueError("approval request digest mismatch")
        ApprovalState(str(request.get("state") or "").upper())
        ApprovalScope(str(request.get("requested_scope") or "").upper())
        PermissionMode(str(request.get("permission_mode") or "").upper())
        RiskClass(str(request.get("risk_class") or "").upper())

    def validate_decision(self, decision: Mapping[str, Any], *, request: Mapping[str, Any] | None = None) -> None:
        if decision.get("beast_object_type") != DECISION_OBJECT_TYPE or str(decision.get("version")) != CONTRACT_VERSION:
            raise ValueError("unsupported approval decision contract")
        if not verify_digest(semantic_payload(decision, exclude={"decision_digest"}), str(decision.get("decision_digest"))):
            raise ValueError("approval decision digest mismatch")
        ApprovalDecision(str(decision.get("decision") or "").upper())
        if decision.get("scope"):
            ApprovalScope(str(decision.get("scope")).upper())
        if request:
            self.validate_request(request)
            if decision.get("approval_id") != request.get("approval_id") or decision.get("request_digest") != request.get("request_digest"):
                raise ValueError("approval decision is not bound to request")
            if decision.get("policy_generation") != request.get("policy_generation"):
                raise ValueError("approval decision policy generation mismatch")

    def validate_transition(self, transition: Mapping[str, Any], *, request: Mapping[str, Any] | None = None) -> None:
        if transition.get("beast_object_type") != TRANSITION_OBJECT_TYPE or str(transition.get("version")) != CONTRACT_VERSION:
            raise ValueError("unsupported approval transition contract")
        if not verify_digest(semantic_payload(transition), str(transition.get("transition_digest"))):
            raise ValueError("approval transition digest mismatch")
        require_transition(str(transition.get("from_state")), str(transition.get("to_state")))
        if request:
            self.validate_request(request)
            if transition.get("approval_id") != request.get("approval_id") or transition.get("request_digest") != request.get("request_digest"):
                raise ValueError("approval transition is not bound to request")
