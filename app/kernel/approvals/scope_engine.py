from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .classifier import ApprovalRequirement, ApprovalRiskClassifier, ToolClass
from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .envelope import ENVELOPE_OBJECT_TYPE, ENVELOPE_VERSION, RichApprovalEnvelopeBuilder
from .models import ApprovalContractFactory, ApprovalDecision, ApprovalScope, RiskClass

SCOPE_VERSION = "4.5"
SCOPE_GRANT_OBJECT_TYPE = "beast_approval_scope_grant"
SCOPE_MATCH_OBJECT_TYPE = "beast_approval_scope_match_receipt"


class ScopeMatchResult(str, Enum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    DENIED = "DENIED"


_RISK_ORDER = {
    RiskClass.LOW.value: 0,
    RiskClass.MEDIUM.value: 1,
    RiskClass.HIGH.value: 2,
    RiskClass.CRITICAL.value: 3,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strings(value: Any, *, maximum: int = 128) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    if len(result) > maximum:
        raise ValueError(f"list exceeds {maximum} entries")
    return sorted(result)


def _subset(candidate: Sequence[str], allowed: Sequence[str]) -> bool:
    return set(candidate).issubset(set(allowed))


def _call_identity(request: Mapping[str, Any]) -> dict[str, Any]:
    return canonicalize({
        "tool_id": request.get("tool_id"),
        "tool_version": request.get("tool_version"),
        "arguments": request.get("arguments") if isinstance(request.get("arguments"), Mapping) else {},
        "workspace_id": request.get("workspace_id"),
        "execution_target": request.get("execution_target"),
        "affected_resources": _strings(request.get("affected_resources")),
        "data_egress": _strings(request.get("data_egress")),
        "expected_side_effects": _strings(request.get("expected_side_effects")),
        "permission_mode": request.get("permission_mode"),
        "policy_generation": request.get("policy_generation"),
    })


@dataclass(frozen=True)
class ApprovalScopeGrant:
    grant_id: str
    approval_id: str
    request_digest: str
    decision_digest: str
    envelope_digest: str
    scope: str
    operator_id: str
    run_id: str
    step_id: str
    tool_id: str
    tool_version: str
    workspace_id: str
    execution_target: str
    policy_generation: str
    maximum_risk_class: str
    call_identity_digest: str
    allowed_resources: tuple[str, ...]
    allowed_data_egress: tuple[str, ...]
    allowed_side_effects: tuple[str, ...]
    read_only_required: bool
    reusable_within_run_only: bool
    single_use: bool
    created_at: str
    expires_at: str
    authority: str = "scope_matching_only"
    capability_issued: bool = False
    execution_authorized: bool = False
    consumed: bool = False
    version: str = SCOPE_VERSION
    beast_object_type: str = SCOPE_GRANT_OBJECT_TYPE
    grant_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"grant_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["grant_digest"] = self.grant_digest or sha256_digest(self.semantic_dict())
        return payload


@dataclass(frozen=True)
class ApprovalScopeMatchReceipt:
    grant_id: str
    grant_digest: str
    candidate_request_digest: str
    candidate_classification_digest: str
    result: str
    reasons: tuple[str, ...]
    matched_scope: str
    evaluated_at: str
    authority: str = "scope_match_classification_only"
    capability_issued: bool = False
    execution_authorized: bool = False
    version: str = SCOPE_VERSION
    beast_object_type: str = SCOPE_MATCH_OBJECT_TYPE
    match_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"match_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["match_digest"] = self.match_digest or sha256_digest(self.semantic_dict())
        return payload


class ApprovalScopeEngine:
    def __init__(self) -> None:
        self.contracts = ApprovalContractFactory()
        self.envelopes = RichApprovalEnvelopeBuilder()
        self.classifier = ApprovalRiskClassifier()

    def create_grant(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        root_path = payload.get("root_path")
        if root_path:
            from .revocation import RevocationPolicyStore
            revocations = RevocationPolicyStore(str(root_path))
            for artifact_name in ("envelope", "decision"):
                artifact = payload.get(artifact_name)
                if isinstance(artifact, Mapping):
                    revocations.assert_active(artifact)
        envelope = payload.get("envelope") if isinstance(payload.get("envelope"), Mapping) else {}
        decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
        if not self.envelopes.verify(envelope):
            raise ValueError("approval envelope is invalid or tampered")
        request = envelope.get("approval_request") if isinstance(envelope.get("approval_request"), Mapping) else {}
        self.contracts.validate_decision(decision, request=request)
        decision_name = str(decision.get("decision") or "")
        if decision_name not in {ApprovalDecision.APPROVE.value, ApprovalDecision.EDIT_AND_APPROVE.value}:
            raise ValueError("only approved decisions can create a scope grant")
        scope = ApprovalScope(str(decision.get("scope") or ""))
        risk = str(request.get("risk_class") or "")
        classification = envelope.get("classification") if isinstance(envelope.get("classification"), Mapping) else {}
        tool_class = str(classification.get("tool_class") or "")

        if scope == ApprovalScope.READ_ONLY_THIS_TARGET and tool_class != ToolClass.READ_ONLY.value:
            raise ValueError("READ_ONLY_THIS_TARGET requires a read-only tool classification")
        if risk in {RiskClass.HIGH.value, RiskClass.CRITICAL.value} and scope not in {ApprovalScope.ONCE, ApprovalScope.EDITED_SCOPE_ONCE}:
            raise ValueError("high and critical actions require a single-use approval scope")
        if scope == ApprovalScope.EDITED_SCOPE_ONCE and decision_name != ApprovalDecision.EDIT_AND_APPROVE.value:
            raise ValueError("EDITED_SCOPE_ONCE requires EDIT_AND_APPROVE")

        effective_request = dict(request)
        if scope == ApprovalScope.EDITED_SCOPE_ONCE:
            effective_request["arguments"] = canonicalize(decision.get("edited_arguments") or {})
            effective_request["affected_resources"] = _strings(decision.get("edited_resources"))
        resources = tuple(_strings(effective_request.get("affected_resources")))
        grant = ApprovalScopeGrant(
            grant_id=str(payload.get("grant_id") or f"scope_{uuid4().hex}"),
            approval_id=str(request.get("approval_id")),
            request_digest=str(request.get("request_digest")),
            decision_digest=str(decision.get("decision_digest")),
            envelope_digest=str(envelope.get("envelope_digest")),
            scope=scope.value,
            operator_id=str(decision.get("operator_id")),
            run_id=str(request.get("run_id")),
            step_id=str(request.get("step_id")),
            tool_id=str(request.get("tool_id")),
            tool_version=str(request.get("tool_version")),
            workspace_id=str(request.get("workspace_id")),
            execution_target=str(request.get("execution_target")),
            policy_generation=str(request.get("policy_generation")),
            maximum_risk_class=risk,
            call_identity_digest=sha256_digest(_call_identity(effective_request)),
            allowed_resources=resources,
            allowed_data_egress=tuple(_strings(effective_request.get("data_egress"))),
            allowed_side_effects=tuple(_strings(effective_request.get("expected_side_effects"))),
            read_only_required=scope == ApprovalScope.READ_ONLY_THIS_TARGET,
            reusable_within_run_only=scope == ApprovalScope.EQUIVALENT_CALLS_THIS_RUN,
            single_use=scope in {ApprovalScope.ONCE, ApprovalScope.EDITED_SCOPE_ONCE},
            created_at=_utcnow(),
            expires_at=str(request.get("expires_at")),
        ).to_dict()
        if not self.verify_grant(grant):
            raise RuntimeError("scope grant digest generation failed")
        return grant

    def verify_grant(self, grant: Mapping[str, Any]) -> bool:
        if grant.get("beast_object_type") != SCOPE_GRANT_OBJECT_TYPE or str(grant.get("version")) != SCOPE_VERSION:
            return False
        if grant.get("authority") != "scope_matching_only":
            return False
        if grant.get("capability_issued") is not False or grant.get("execution_authorized") is not False:
            return False
        if grant.get("consumed") is not False:
            return False
        try:
            scope = ApprovalScope(str(grant.get("scope") or ""))
        except ValueError:
            return False
        risk = str(grant.get("maximum_risk_class") or "")
        if risk not in _RISK_ORDER:
            return False
        if risk in {RiskClass.HIGH.value, RiskClass.CRITICAL.value} and scope not in {ApprovalScope.ONCE, ApprovalScope.EDITED_SCOPE_ONCE}:
            return False
        if scope == ApprovalScope.READ_ONLY_THIS_TARGET and grant.get("read_only_required") is not True:
            return False
        return verify_digest(semantic_payload(grant, exclude={"grant_digest"}), str(grant.get("grant_digest") or ""))

    def evaluate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        root_path = payload.get("root_path")
        if root_path:
            from .revocation import RevocationPolicyStore
            revocations = RevocationPolicyStore(str(root_path))
            for artifact_name in ("grant", "request", "classification"):
                artifact = payload.get(artifact_name)
                if isinstance(artifact, Mapping):
                    revocations.assert_active(artifact)
        grant = payload.get("grant") if isinstance(payload.get("grant"), Mapping) else {}
        request = payload.get("candidate_request") if isinstance(payload.get("candidate_request"), Mapping) else {}
        classification = payload.get("candidate_classification") if isinstance(payload.get("candidate_classification"), Mapping) else {}
        reasons: list[str] = []
        if not self.verify_grant(grant):
            reasons.append("invalid_scope_grant")
        try:
            self.contracts.validate_request(request)
        except (TypeError, ValueError):
            reasons.append("invalid_candidate_request")
        if not self.classifier.verify(classification):
            reasons.append("invalid_candidate_classification")
        if reasons:
            result = ScopeMatchResult.DENIED
        else:
            requirement = str(classification.get("requirement") or "")
            if requirement in {ApprovalRequirement.POLICY_DENY.value, ApprovalRequirement.PERMANENTLY_DENIED.value}:
                reasons.append("candidate_policy_denied")
            for field in ("tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation"):
                if str(request.get(field)) != str(grant.get(field)):
                    reasons.append(f"{field}_mismatch")
            if str(classification.get("tool_id")) != str(request.get("tool_id")):
                reasons.append("classification_tool_mismatch")
            if str(classification.get("policy_generation")) != str(request.get("policy_generation")):
                reasons.append("classification_policy_mismatch")
            candidate_risk = str(request.get("risk_class") or "")
            if candidate_risk not in _RISK_ORDER or _RISK_ORDER[candidate_risk] > _RISK_ORDER[str(grant.get("maximum_risk_class"))]:
                reasons.append("risk_exceeds_grant")
            if not _subset(_strings(request.get("affected_resources")), _strings(grant.get("allowed_resources"))):
                reasons.append("resource_scope_widened")
            if not _subset(_strings(request.get("data_egress")), _strings(grant.get("allowed_data_egress"))):
                reasons.append("data_egress_widened")
            if not _subset(_strings(request.get("expected_side_effects")), _strings(grant.get("allowed_side_effects"))):
                reasons.append("side_effect_scope_widened")
            scope = ApprovalScope(str(grant.get("scope")))
            if scope == ApprovalScope.EQUIVALENT_CALLS_THIS_RUN and str(request.get("run_id")) != str(grant.get("run_id")):
                reasons.append("run_scope_mismatch")
            if scope in {ApprovalScope.ONCE, ApprovalScope.EDITED_SCOPE_ONCE}:
                if sha256_digest(_call_identity(request)) != str(grant.get("call_identity_digest")):
                    reasons.append("single_use_call_mismatch")
            elif scope in {ApprovalScope.EQUIVALENT_CALLS_THIS_RUN, ApprovalScope.TOOL_SCOPE_THIS_WORKSPACE}:
                if sha256_digest(_call_identity(request)) != str(grant.get("call_identity_digest")):
                    reasons.append("call_not_semantically_equivalent")
            elif scope == ApprovalScope.READ_ONLY_THIS_TARGET:
                if str(classification.get("tool_class")) != ToolClass.READ_ONLY.value:
                    reasons.append("candidate_not_read_only")
                if _strings(request.get("data_egress")):
                    reasons.append("read_only_scope_disallows_egress")
            result = ScopeMatchResult.NO_MATCH if reasons else ScopeMatchResult.MATCH

        receipt = ApprovalScopeMatchReceipt(
            grant_id=str(grant.get("grant_id") or ""),
            grant_digest=str(grant.get("grant_digest") or ""),
            candidate_request_digest=str(request.get("request_digest") or ""),
            candidate_classification_digest=str(classification.get("classification_digest") or ""),
            result=result.value,
            reasons=tuple(sorted(set(reasons))),
            matched_scope=str(grant.get("scope") or ""),
            evaluated_at=_utcnow(),
        ).to_dict()
        if not self.verify_match(receipt):
            raise RuntimeError("scope match receipt digest generation failed")
        return receipt

    def verify_match(self, receipt: Mapping[str, Any]) -> bool:
        if receipt.get("beast_object_type") != SCOPE_MATCH_OBJECT_TYPE or str(receipt.get("version")) != SCOPE_VERSION:
            return False
        if receipt.get("authority") != "scope_match_classification_only":
            return False
        if receipt.get("capability_issued") is not False or receipt.get("execution_authorized") is not False:
            return False
        try:
            ScopeMatchResult(str(receipt.get("result") or ""))
        except ValueError:
            return False
        return verify_digest(semantic_payload(receipt, exclude={"match_digest"}), str(receipt.get("match_digest") or ""))
