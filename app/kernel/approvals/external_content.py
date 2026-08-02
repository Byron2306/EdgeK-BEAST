from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest

EXTERNAL_CONTENT_VERSION = "4.10"
CLASSIFICATION_OBJECT_TYPE = "beast_external_content_risk_classification"
ADMISSION_OBJECT_TYPE = "beast_external_content_admission_receipt"

_HIGH_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("policy_override", re.compile(r"(?i)\b(?:ignore|disregard|override|replace)\b.{0,80}\b(?:system|developer|policy|safety|instructions?)\b")),
    ("authority_widening", re.compile(r"(?i)\b(?:grant|enable|allow|authorize|unlock|bypass|disable)\b.{0,80}\b(?:tool|shell|filesystem|network|approval|policy|guard|sandbox|permission|authority)\b")),
    ("secret_exfiltration", re.compile(r"(?i)\b(?:send|upload|post|exfiltrate|reveal|print|dump)\b.{0,100}\b(?:secret|token|credential|password|private key|\.env)\b")),
    ("role_impersonation", re.compile(r"(?i)\b(?:system message|developer message|you are now|act as root|admin instruction)\b")),
    ("tool_directive", re.compile(r"(?i)\b(?:run|execute|invoke|call)\b.{0,60}\b(?:shell|terminal|bash|powershell|curl|wget|tool|command)\b")),
)

_MEDIUM_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instructional_language", re.compile(r"(?i)\b(?:must|always|never|required to|do not)\b.{0,100}\b(?:follow|obey|execute|use|ignore|reveal|send)\b")),
    ("context_widening", re.compile(r"(?i)\b(?:read|open|search|scan)\b.{0,80}\b(?:entire repository|all files|home directory|credentials|secrets|\.ssh|\.aws)\b")),
    ("encoded_payload", re.compile(r"(?i)\b(?:base64|decode this|eval\(|exec\(|javascript:)\b")),
)

_ALLOWED_SOURCES = {"url", "github", "mcp", "database", "log", "remote_terminal", "documentation", "issue", "pull_request"}
_ALLOWED_DECISIONS = {"ADMIT", "ADMIT_REDACTED", "QUARANTINE", "REJECT"}


def _string_list(value: Any, maximum: int = 128) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    output: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in output:
            output.append(text)
    if len(output) > maximum:
        raise ValueError(f"list exceeds {maximum} entries")
    return tuple(output)


def _text(value: Any, maximum: int) -> str:
    if isinstance(value, str):
        return value[:maximum]
    if isinstance(value, (bytes, bytearray)):
        return bytes(value[:maximum]).decode("utf-8", errors="replace")
    return str(value or "")[:maximum]


@dataclass(frozen=True)
class ExternalContentPolicy:
    generation: str
    maximum_content_chars: int = 200_000
    maximum_model_visible_chars: int = 40_000
    quarantine_high_risk: bool = True
    require_review_for_medium_risk: bool = True
    permit_low_risk_admission: bool = True
    strip_instructional_segments: bool = True
    require_provenance: bool = True
    approved_domains: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExternalContentClassification:
    policy_generation: str
    source_type: str
    source_uri: str
    source_domain: str
    fetch_receipt_digest: str
    content_digest: str
    content_length: int
    risk_level: str
    risk_score: int
    matched_signals: tuple[str, ...]
    provenance_complete: bool
    fetch_authorized: bool
    context_admission_authorized: bool
    human_review_required: bool
    quarantine_required: bool
    policy_effect_allowed: bool = False
    authority_widening_allowed: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)
    version: str = EXTERNAL_CONTENT_VERSION
    beast_object_type: str = CLASSIFICATION_OBJECT_TYPE
    classification_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["classification_digest"] = self.classification_digest or sha256_digest(
            semantic_payload(payload, exclude={"classification_digest"})
        )
        return payload


@dataclass(frozen=True)
class ExternalContentAdmissionReceipt:
    policy_generation: str
    classification_digest: str
    source_type: str
    source_uri: str
    content_digest: str
    decision: str
    admitted_content: str
    admitted_content_digest: str
    admitted_character_count: int
    provenance_label: Mapping[str, Any]
    quarantined: bool
    human_review_required: bool
    model_context_allowed: bool
    policy_effect_allowed: bool = False
    authority_widening_allowed: bool = False
    raw_content_persisted: bool = False
    authority: str = "external_content_admission_classification_only"
    version: str = EXTERNAL_CONTENT_VERSION
    beast_object_type: str = ADMISSION_OBJECT_TYPE
    receipt_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["receipt_digest"] = self.receipt_digest or sha256_digest(
            semantic_payload(payload, exclude={"receipt_digest"})
        )
        return payload


class ExternalContentAdmissionController:
    """Classify untrusted external content and gate its admission to model context."""

    def classify(self, payload: Mapping[str, Any], *, policy: ExternalContentPolicy) -> dict[str, Any]:
        source_type = str(payload.get("source_type") or "").strip().lower()
        if source_type not in _ALLOWED_SOURCES:
            raise ValueError("unsupported external content source_type")
        source_uri = str(payload.get("source_uri") or "").strip()
        source_domain = str(payload.get("source_domain") or "").strip().lower()
        fetch_receipt_digest = str(payload.get("fetch_receipt_digest") or "").strip()
        fetch_authorized = bool(payload.get("fetch_authorized", False))
        content = _text(payload.get("content"), policy.maximum_content_chars + 1)
        if len(content) > policy.maximum_content_chars:
            raise ValueError("external content exceeds policy maximum")

        provenance_complete = bool(source_uri and fetch_receipt_digest)
        signals: list[str] = []
        score = 0
        for name, pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(content):
                signals.append(name)
                score += 40
        for name, pattern in _MEDIUM_RISK_PATTERNS:
            if pattern.search(content):
                signals.append(name)
                score += 15
        if policy.require_provenance and not provenance_complete:
            signals.append("missing_provenance")
            score += 35
        if not fetch_authorized:
            signals.append("fetch_not_authorized")
            score += 50
        if policy.approved_domains and source_domain not in policy.approved_domains:
            signals.append("domain_not_approved")
            score += 20

        risk_level = "LOW"
        if score >= 60:
            risk_level = "CRITICAL"
        elif score >= 40:
            risk_level = "HIGH"
        elif score >= 15:
            risk_level = "MEDIUM"

        quarantine = (risk_level in {"HIGH", "CRITICAL"} and policy.quarantine_high_risk) or not fetch_authorized
        review = quarantine or (risk_level == "MEDIUM" and policy.require_review_for_medium_risk)
        context_allowed = bool(fetch_authorized and provenance_complete and not quarantine and risk_level == "LOW" and policy.permit_low_risk_admission)
        reasons: list[str] = []
        if signals:
            reasons.append("external content contains untrusted instruction or provenance signals")
        if fetch_authorized:
            reasons.append("fetch permission is recorded separately from context admission")
        if quarantine:
            reasons.append("content is quarantined and excluded from model context")

        result = ExternalContentClassification(
            policy_generation=policy.generation,
            source_type=source_type,
            source_uri=source_uri,
            source_domain=source_domain,
            fetch_receipt_digest=fetch_receipt_digest,
            content_digest=sha256_digest(content),
            content_length=len(content),
            risk_level=risk_level,
            risk_score=min(score, 100),
            matched_signals=tuple(sorted(set(signals))),
            provenance_complete=provenance_complete,
            fetch_authorized=fetch_authorized,
            context_admission_authorized=context_allowed,
            human_review_required=review,
            quarantine_required=quarantine,
            reasons=tuple(reasons),
        ).to_dict()
        if not self.verify_classification(result):
            raise RuntimeError("external-content classification digest generation failed")
        return result

    def admit(
        self,
        payload: Mapping[str, Any],
        *,
        classification: Mapping[str, Any],
        policy: ExternalContentPolicy,
        operator_decision: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.verify_classification(classification):
            raise ValueError("invalid external-content classification")
        if classification.get("policy_generation") != policy.generation:
            raise ValueError("policy generation mismatch")

        content = _text(payload.get("content"), policy.maximum_content_chars)
        if sha256_digest(content) != classification.get("content_digest"):
            raise ValueError("external content digest mismatch")

        decision = "ADMIT"
        if classification.get("quarantine_required") or classification.get("human_review_required"):
            operator_decision = operator_decision or {}
            decision = str(operator_decision.get("decision") or "").strip().upper()
            if decision not in _ALLOWED_DECISIONS:
                raise ValueError("explicit external-content admission decision required")
            if str(operator_decision.get("classification_digest") or "") != classification.get("classification_digest"):
                raise ValueError("operator decision is not bound to classification")
            if operator_decision.get("review_acknowledged") is not True:
                raise ValueError("external-content review acknowledgement required")
        elif not classification.get("context_admission_authorized"):
            decision = "REJECT"

        quarantined = decision in {"QUARANTINE", "REJECT"}
        admitted = ""
        if decision in {"ADMIT", "ADMIT_REDACTED"}:
            if classification.get("risk_level") in {"HIGH", "CRITICAL"} and decision == "ADMIT":
                raise ValueError("high-risk external content cannot be admitted raw")
            admitted = self._sanitize(content, policy=policy)
            if len(admitted) > policy.maximum_model_visible_chars:
                admitted = admitted[: policy.maximum_model_visible_chars] + "\n[BEAST: external content truncated]"

        provenance_label = {
            "untrusted_external_content": True,
            "source_type": classification.get("source_type"),
            "source_uri": classification.get("source_uri"),
            "source_domain": classification.get("source_domain"),
            "fetch_receipt_digest": classification.get("fetch_receipt_digest"),
            "classification_digest": classification.get("classification_digest"),
            "risk_level": classification.get("risk_level"),
            "policy_instruction": False,
        }
        receipt = ExternalContentAdmissionReceipt(
            policy_generation=policy.generation,
            classification_digest=str(classification.get("classification_digest")),
            source_type=str(classification.get("source_type")),
            source_uri=str(classification.get("source_uri")),
            content_digest=str(classification.get("content_digest")),
            decision=decision,
            admitted_content=admitted,
            admitted_content_digest=sha256_digest(admitted),
            admitted_character_count=len(admitted),
            provenance_label=provenance_label,
            quarantined=quarantined,
            human_review_required=bool(classification.get("human_review_required")),
            model_context_allowed=bool(admitted and not quarantined),
        ).to_dict()
        if not self.verify_admission(receipt):
            raise RuntimeError("external-content admission digest generation failed")
        return receipt

    def verify_classification(self, receipt: Mapping[str, Any]) -> bool:
        if receipt.get("beast_object_type") != CLASSIFICATION_OBJECT_TYPE or str(receipt.get("version")) != EXTERNAL_CONTENT_VERSION:
            return False
        if receipt.get("policy_effect_allowed") is not False or receipt.get("authority_widening_allowed") is not False:
            return False
        if receipt.get("quarantine_required") is True and receipt.get("context_admission_authorized") is True:
            return False
        return verify_digest(
            semantic_payload(receipt, exclude={"classification_digest"}),
            str(receipt.get("classification_digest") or ""),
        )

    def verify_admission(self, receipt: Mapping[str, Any]) -> bool:
        if receipt.get("beast_object_type") != ADMISSION_OBJECT_TYPE or str(receipt.get("version")) != EXTERNAL_CONTENT_VERSION:
            return False
        if receipt.get("authority") != "external_content_admission_classification_only":
            return False
        if receipt.get("policy_effect_allowed") is not False or receipt.get("authority_widening_allowed") is not False:
            return False
        if receipt.get("raw_content_persisted") is not False:
            return False
        if receipt.get("quarantined") is True and receipt.get("model_context_allowed") is True:
            return False
        if sha256_digest(str(receipt.get("admitted_content") or "")) != receipt.get("admitted_content_digest"):
            return False
        return verify_digest(
            semantic_payload(receipt, exclude={"receipt_digest"}),
            str(receipt.get("receipt_digest") or ""),
        )

    @staticmethod
    def _sanitize(content: str, *, policy: ExternalContentPolicy) -> str:
        if not policy.strip_instructional_segments:
            return content
        output: list[str] = []
        for line in content.splitlines():
            if any(pattern.search(line) for _, pattern in _HIGH_RISK_PATTERNS):
                output.append("[BEAST: quarantined instructional segment omitted]")
            else:
                output.append(line)
        return "\n".join(output)


def policy_from_external_payload(payload: Mapping[str, Any] | None) -> ExternalContentPolicy:
    payload = payload or {}
    generation = str(payload.get("generation") or "policy:default").strip()
    if not generation:
        raise ValueError("policy generation is required")
    return ExternalContentPolicy(
        generation=generation,
        maximum_content_chars=max(1, min(int(payload.get("maximum_content_chars", 200_000)), 2_000_000)),
        maximum_model_visible_chars=max(1, min(int(payload.get("maximum_model_visible_chars", 40_000)), 200_000)),
        quarantine_high_risk=bool(payload.get("quarantine_high_risk", True)),
        require_review_for_medium_risk=bool(payload.get("require_review_for_medium_risk", True)),
        permit_low_risk_admission=bool(payload.get("permit_low_risk_admission", True)),
        strip_instructional_segments=bool(payload.get("strip_instructional_segments", True)),
        require_provenance=bool(payload.get("require_provenance", True)),
        approved_domains=_string_list(payload.get("approved_domains")),
    )
