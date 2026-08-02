from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .classifier import ApprovalRequirement, ApprovalRiskClassifier
from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .models import ApprovalContractFactory, ApprovalScope

ENVELOPE_VERSION = "4.4"
ENVELOPE_OBJECT_TYPE = "beast_rich_approval_request_envelope"

_SENSITIVE_KEYS = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "private_key",
    "credential", "authorization", "cookie", "session", "signing_key",
)


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
    return result


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(marker in lowered for marker in _SENSITIVE_KEYS)


def _safe_value(value: Any, *, key: str = "", max_text: int = 240, depth: int = 0) -> Any:
    if depth > 8:
        return {"redacted": True, "reason": "maximum_depth", "digest": sha256_digest(canonicalize(value))}
    if _is_sensitive_key(key):
        return {"redacted": True, "reason": "sensitive_key", "value_type": type(value).__name__, "digest": sha256_digest(canonicalize(value))}
    if isinstance(value, Mapping):
        return {str(k): _safe_value(v, key=str(k), max_text=max_text, depth=depth + 1) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_value(v, key=key, max_text=max_text, depth=depth + 1) for v in list(value)[:128]]
    if isinstance(value, (bytes, bytearray)):
        return {"redacted": True, "reason": "binary_value", "byte_count": len(value), "digest": sha256_digest(bytes(value).hex())}
    if isinstance(value, str) and len(value) > max_text:
        return {"truncated": True, "character_count": len(value), "preview": value[:max_text], "digest": sha256_digest(value)}
    return canonicalize(value)


@dataclass(frozen=True)
class RichApprovalEnvelope:
    approval_request: Mapping[str, Any]
    classification: Mapping[str, Any]
    argument_view: Mapping[str, Any]
    argument_digest: str
    affected_files: tuple[str, ...]
    commands: tuple[str, ...]
    urls: tuple[str, ...]
    external_services: tuple[str, ...]
    data_egress: tuple[str, ...]
    expected_side_effects: tuple[str, ...]
    budget_impact: Mapping[str, Any]
    evidence_policy: Mapping[str, Any]
    operator_summary: str
    generated_at: str
    authority: str = "approval_request_description_only"
    capability_issued: bool = False
    execution_authorized: bool = False
    version: str = ENVELOPE_VERSION
    beast_object_type: str = ENVELOPE_OBJECT_TYPE
    envelope_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"envelope_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["envelope_digest"] = self.envelope_digest or sha256_digest(self.semantic_dict())
        return payload


class RichApprovalEnvelopeBuilder:
    def __init__(self) -> None:
        self.contracts = ApprovalContractFactory()
        self.classifier = ApprovalRiskClassifier()

    def build(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        classification = payload.get("classification") if isinstance(payload.get("classification"), Mapping) else {}
        if not self.classifier.verify(classification):
            raise ValueError("classification receipt is invalid or tampered")
        requirement = str(classification.get("requirement") or "")
        if requirement not in {ApprovalRequirement.REQUIRE_APPROVAL.value, ApprovalRequirement.REQUIRE_SENSITIVE_APPROVAL.value}:
            raise ValueError("classification does not require an approval envelope")

        request_input = payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
        merged = dict(request_input)
        for field in ("tool_id", "tool_version", "workspace_id", "execution_target", "permission_mode", "policy_generation", "risk_class"):
            expected = classification.get(field)
            supplied = merged.get(field)
            if supplied not in (None, "") and str(supplied).upper() != str(expected).upper():
                raise ValueError(f"request {field} does not match classification")
            merged[field] = expected
        resources = _strings(merged.get("affected_resources") or classification.get("matched_sensitive_resources") or [])
        merged["affected_resources"] = resources
        merged.setdefault("requested_scope", ApprovalScope.ONCE.value)
        request = self.contracts.create_request(merged)

        arguments = request.get("arguments") if isinstance(request.get("arguments"), Mapping) else {}
        argument_digest = sha256_digest(canonicalize(arguments))
        safe_arguments = _safe_value(arguments)
        if not isinstance(safe_arguments, Mapping):
            safe_arguments = {"value": safe_arguments}

        affected_files = tuple(_strings(payload.get("affected_files") or resources))
        commands = tuple(_strings(payload.get("commands")))
        urls = tuple(_strings(payload.get("urls")))
        external_services = tuple(_strings(payload.get("external_services")))
        data_egress = tuple(_strings(payload.get("data_egress") or request.get("data_egress")))
        side_effects = tuple(_strings(payload.get("expected_side_effects") or request.get("expected_side_effects")))
        summary = str(payload.get("operator_summary") or request.get("reason") or "").strip()
        if not summary:
            raise ValueError("operator_summary or request reason is required")
        if len(summary) > 2000:
            raise ValueError("operator_summary exceeds 2000 characters")

        envelope = RichApprovalEnvelope(
            approval_request=request,
            classification=canonicalize(classification),
            argument_view=canonicalize(safe_arguments),
            argument_digest=argument_digest,
            affected_files=affected_files,
            commands=commands,
            urls=urls,
            external_services=external_services,
            data_egress=data_egress,
            expected_side_effects=side_effects,
            budget_impact=canonicalize(request.get("budget_impact") or {}),
            evidence_policy=canonicalize(request.get("evidence_policy") or {}),
            operator_summary=summary,
            generated_at=_utcnow(),
        ).to_dict()
        if not self.verify(envelope):
            raise RuntimeError("approval envelope digest generation failed")
        return envelope

    def verify(self, envelope: Mapping[str, Any]) -> bool:
        if envelope.get("beast_object_type") != ENVELOPE_OBJECT_TYPE or str(envelope.get("version")) != ENVELOPE_VERSION:
            return False
        if envelope.get("authority") != "approval_request_description_only":
            return False
        if envelope.get("capability_issued") is not False or envelope.get("execution_authorized") is not False:
            return False
        request = envelope.get("approval_request") if isinstance(envelope.get("approval_request"), Mapping) else {}
        classification = envelope.get("classification") if isinstance(envelope.get("classification"), Mapping) else {}
        try:
            self.contracts.validate_request(request)
        except (TypeError, ValueError):
            return False
        if not self.classifier.verify(classification):
            return False
        if str(request.get("tool_id")) != str(classification.get("tool_id")):
            return False
        if str(request.get("policy_generation")) != str(classification.get("policy_generation")):
            return False
        if str(request.get("workspace_id")) != str(classification.get("workspace_id")):
            return False
        if str(request.get("execution_target")) != str(classification.get("execution_target")):
            return False
        arguments = request.get("arguments") if isinstance(request.get("arguments"), Mapping) else {}
        if envelope.get("argument_digest") != sha256_digest(canonicalize(arguments)):
            return False
        return verify_digest(semantic_payload(envelope, exclude={"envelope_digest"}), str(envelope.get("envelope_digest") or ""))
