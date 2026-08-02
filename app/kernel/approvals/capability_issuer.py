from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .models import ApprovalContractFactory
from .scope_engine import ApprovalScopeEngine, ScopeMatchResult

CAPABILITY_VERSION = "4.6"
CAPABILITY_OBJECT_TYPE = "beast_request_bound_tool_capability"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("capability expiry is required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("capability expiry must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RequestBoundCapability:
    capability_id: str
    approval_id: str
    grant_id: str
    grant_digest: str
    scope_match_digest: str
    request_digest: str
    classification_digest: str
    decision_digest: str
    run_id: str
    step_id: str
    tool_id: str
    tool_version: str
    workspace_id: str
    execution_target: str
    policy_generation: str
    call_identity_digest: str
    scope: str
    audience: str
    issued_at: str
    expires_at: str
    nonce: str
    single_use: bool
    authority: str = "request_bound_capability_descriptor_only"
    capability_issued: bool = True
    capability_consumed: bool = False
    execution_authorized: bool = False
    workspace_mutation_authorized: bool = False
    promotion_authorized: bool = False
    phase2_governance_bypass_allowed: bool = False
    version: str = CAPABILITY_VERSION
    beast_object_type: str = CAPABILITY_OBJECT_TYPE
    capability_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"capability_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["capability_digest"] = self.capability_digest or sha256_digest(self.semantic_dict())
        return payload


class RequestBoundCapabilityIssuer:
    def __init__(self) -> None:
        self.scopes = ApprovalScopeEngine()
        self.contracts = ApprovalContractFactory()

    def issue(self, payload: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        root_path = payload.get("root_path")
        if root_path:
            from .revocation import RevocationPolicyStore
            revocations = RevocationPolicyStore(str(root_path))
            for artifact_name in ("grant", "request", "decision", "classification"):
                artifact = payload.get(artifact_name)
                if isinstance(artifact, Mapping):
                    revocations.assert_active(artifact)
        grant = payload.get("grant") if isinstance(payload.get("grant"), Mapping) else {}
        match = payload.get("scope_match") if isinstance(payload.get("scope_match"), Mapping) else {}
        request = payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
        decision = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
        classification = payload.get("classification") if isinstance(payload.get("classification"), Mapping) else {}
        if not self.scopes.verify_grant(grant):
            raise ValueError("scope grant is invalid or tampered")
        if not self.scopes.verify_match(match):
            raise ValueError("scope match receipt is invalid or tampered")
        if str(match.get("result")) != ScopeMatchResult.MATCH.value:
            raise ValueError("capability issuance requires a successful scope match")
        self.contracts.validate_request(request)
        self.contracts.validate_decision(decision, request=request)
        if str(match.get("grant_id")) != str(grant.get("grant_id")) or str(match.get("grant_digest")) != str(grant.get("grant_digest")):
            raise ValueError("scope match is not bound to the supplied grant")
        if str(match.get("candidate_request_digest")) != str(request.get("request_digest")):
            raise ValueError("scope match is not bound to the supplied request")
        if str(match.get("candidate_classification_digest")) != str(classification.get("classification_digest")):
            raise ValueError("scope match is not bound to the supplied classification")
        if str(grant.get("approval_id")) != str(request.get("approval_id")):
            raise ValueError("grant approval identity mismatch")
        if str(grant.get("decision_digest")) != str(decision.get("decision_digest")):
            raise ValueError("grant decision binding mismatch")
        for field in ("run_id", "step_id", "tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation"):
            if str(grant.get(field)) != str(request.get(field)):
                raise ValueError(f"grant {field} binding mismatch")
        if str(classification.get("tool_id")) != str(request.get("tool_id")):
            raise ValueError("classification tool binding mismatch")
        if str(classification.get("policy_generation")) != str(request.get("policy_generation")):
            raise ValueError("classification policy binding mismatch")
        now = now or _utcnow()
        expiry = min(_parse_time(grant.get("expires_at")), _parse_time(request.get("expires_at")))
        if expiry <= now:
            raise ValueError("approval scope has expired")
        capability = RequestBoundCapability(
            capability_id=str(payload.get("capability_id") or f"cap_{uuid4().hex}"),
            approval_id=str(request.get("approval_id")),
            grant_id=str(grant.get("grant_id")),
            grant_digest=str(grant.get("grant_digest")),
            scope_match_digest=str(match.get("match_digest")),
            request_digest=str(request.get("request_digest")),
            classification_digest=str(classification.get("classification_digest")),
            decision_digest=str(decision.get("decision_digest")),
            run_id=str(request.get("run_id")),
            step_id=str(request.get("step_id")),
            tool_id=str(request.get("tool_id")),
            tool_version=str(request.get("tool_version")),
            workspace_id=str(request.get("workspace_id")),
            execution_target=str(request.get("execution_target")),
            policy_generation=str(request.get("policy_generation")),
            call_identity_digest=str(grant.get("call_identity_digest")),
            scope=str(grant.get("scope")),
            audience="beast-tool-runtime",
            issued_at=_iso(now),
            expires_at=_iso(expiry),
            nonce=uuid4().hex,
            single_use=bool(grant.get("single_use")),
        ).to_dict()
        if not self.verify(capability):
            raise RuntimeError("capability digest generation failed")
        return capability

    def verify(self, capability: Mapping[str, Any], *, now: datetime | None = None, require_unexpired: bool = False) -> bool:
        if capability.get("beast_object_type") != CAPABILITY_OBJECT_TYPE or str(capability.get("version")) != CAPABILITY_VERSION:
            return False
        if capability.get("authority") != "request_bound_capability_descriptor_only":
            return False
        if capability.get("capability_issued") is not True or capability.get("capability_consumed") is not False:
            return False
        for field in ("execution_authorized", "workspace_mutation_authorized", "promotion_authorized", "phase2_governance_bypass_allowed"):
            if capability.get(field) is not False:
                return False
        required = ("capability_id", "approval_id", "grant_id", "grant_digest", "scope_match_digest", "request_digest", "classification_digest", "decision_digest", "run_id", "step_id", "tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation", "call_identity_digest", "scope", "audience", "issued_at", "expires_at", "nonce")
        if any(not str(capability.get(field) or "").strip() for field in required):
            return False
        if capability.get("audience") != "beast-tool-runtime":
            return False
        try:
            issued = _parse_time(capability.get("issued_at")); expiry = _parse_time(capability.get("expires_at"))
        except (TypeError, ValueError):
            return False
        if expiry <= issued:
            return False
        if require_unexpired and expiry <= (now or _utcnow()):
            return False
        return verify_digest(semantic_payload(capability, exclude={"capability_digest"}), str(capability.get("capability_digest") or ""))
