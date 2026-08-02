from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest

SENSITIVE_DATA_VERSION = "4.9"
CLASSIFICATION_OBJECT_TYPE = "beast_sensitive_data_classification"
REDACTION_OBJECT_TYPE = "beast_sensitive_data_redaction_receipt"

_SECRET_KEY_MARKERS = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "private_key",
    "credential", "authorization", "cookie", "session_key", "signing_key", "client_secret",
)

_DEFAULT_PATH_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "*credential*", "*secret*", "*signing*", ".ssh/*", ".aws/*", ".config/gcloud/*",
    ".docker/config.json", ".npmrc", ".pypirc", "*policy*",
)

_SECRET_VALUE_PATTERNS = (
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/-]{12,}={0,2}"),
)


def _strings(value: Any, *, maximum: int = 256) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    if len(result) > maximum:
        raise ValueError(f"list exceeds {maximum} entries")
    return tuple(result)


def _sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SECRET_KEY_MARKERS)


def _path_matches(path: str, patterns: Sequence[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    candidate = PurePosixPath(normalized)
    return any(candidate.match(pattern) or candidate.name == pattern for pattern in patterns)


def _looks_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)


def _digestable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _digestable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_digestable(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return {"beast_binary": True, "byte_count": len(value), "hex": bytes(value).hex()}
    return canonicalize(value)


def _digest_any(value: Any) -> str:
    return sha256_digest(_digestable(value))


@dataclass(frozen=True)
class SensitiveDataPolicy:
    generation: str
    path_patterns: tuple[str, ...] = _DEFAULT_PATH_PATTERNS
    explicit_approval_required: bool = True
    redact_model_context: bool = True
    redact_chronicle: bool = True
    redact_sensorium: bool = True
    redact_evidence: bool = True
    local_model_only_for_raw_secrets: bool = True
    max_visible_text: int = 240


@dataclass(frozen=True)
class SensitiveDataClassification:
    policy_generation: str
    sensitive: bool
    explicit_approval_required: bool
    matched_resources: tuple[str, ...]
    matched_argument_keys: tuple[str, ...]
    detected_value_types: tuple[str, ...]
    provider_visibility: str
    model_context_allowed: bool
    durable_raw_persistence_allowed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    version: str = SENSITIVE_DATA_VERSION
    beast_object_type: str = CLASSIFICATION_OBJECT_TYPE
    classification_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["classification_digest"] = self.classification_digest or sha256_digest(
            semantic_payload(payload, exclude={"classification_digest"})
        )
        return payload


@dataclass(frozen=True)
class SensitiveDataRedactionReceipt:
    policy_generation: str
    surface: str
    source_digest: str
    redacted_payload: Any
    redacted_paths: tuple[str, ...]
    redaction_count: int
    raw_secret_persisted: bool
    authority: str = "redaction_and_admission_classification_only"
    version: str = SENSITIVE_DATA_VERSION
    beast_object_type: str = REDACTION_OBJECT_TYPE
    receipt_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["receipt_digest"] = self.receipt_digest or sha256_digest(
            semantic_payload(payload, exclude={"receipt_digest"})
        )
        return payload


class SensitiveDataController:
    """Classify and redact sensitive material without granting access authority."""

    def classify(
        self,
        payload: Mapping[str, Any],
        *,
        policy: SensitiveDataPolicy,
    ) -> dict[str, Any]:
        resources = _strings(payload.get("resources") or payload.get("affected_resources"))
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), Mapping) else {}
        provider = str(payload.get("provider") or "").strip()
        provider_is_local = bool(payload.get("provider_is_local", False))

        matched_resources = tuple(sorted(path for path in resources if _path_matches(path, policy.path_patterns)))
        matched_keys: set[str] = set()
        value_types: set[str] = set()
        self._inspect(arguments, matched_keys, value_types)
        sensitive = bool(matched_resources or matched_keys or value_types)

        reasons: list[str] = []
        if matched_resources:
            reasons.append("sensitive resource path matched policy")
        if matched_keys:
            reasons.append("sensitive argument key detected")
        if value_types:
            reasons.append("secret-like value detected")

        raw_context_allowed = not sensitive
        visibility = "normal"
        if sensitive:
            visibility = "redacted_only"
            if provider_is_local and policy.local_model_only_for_raw_secrets:
                visibility = "local_redacted_only"
            if provider and not provider_is_local:
                reasons.append("raw sensitive values are not admissible to external providers")

        result = SensitiveDataClassification(
            policy_generation=policy.generation,
            sensitive=sensitive,
            explicit_approval_required=bool(sensitive and policy.explicit_approval_required),
            matched_resources=matched_resources,
            matched_argument_keys=tuple(sorted(matched_keys)),
            detected_value_types=tuple(sorted(value_types)),
            provider_visibility=visibility,
            model_context_allowed=raw_context_allowed,
            durable_raw_persistence_allowed=False if sensitive else True,
            reasons=tuple(reasons),
        ).to_dict()
        if not self.verify_classification(result):
            raise RuntimeError("sensitive-data classification digest generation failed")
        return result

    def redact(
        self,
        payload: Any,
        *,
        surface: str,
        policy: SensitiveDataPolicy,
    ) -> dict[str, Any]:
        normalized_surface = str(surface or "").strip().lower()
        if normalized_surface not in {"model", "chronicle", "sensorium", "evidence", "approval", "log"}:
            raise ValueError("unsupported redaction surface")
        source_digest = _digest_any(payload)
        redacted_paths: list[str] = []
        redacted = self._redact_value(payload, path="$", redacted_paths=redacted_paths, max_text=policy.max_visible_text)
        receipt = SensitiveDataRedactionReceipt(
            policy_generation=policy.generation,
            surface=normalized_surface,
            source_digest=source_digest,
            redacted_payload=canonicalize(redacted),
            redacted_paths=tuple(redacted_paths),
            redaction_count=len(redacted_paths),
            raw_secret_persisted=False,
        ).to_dict()
        if not self.verify_redaction(receipt):
            raise RuntimeError("sensitive-data redaction receipt generation failed")
        return receipt

    def verify_classification(self, receipt: Mapping[str, Any]) -> bool:
        if receipt.get("beast_object_type") != CLASSIFICATION_OBJECT_TYPE:
            return False
        if str(receipt.get("version") or "") != SENSITIVE_DATA_VERSION:
            return False
        if receipt.get("sensitive") is True:
            if receipt.get("durable_raw_persistence_allowed") is not False:
                return False
            if receipt.get("model_context_allowed") is not False:
                return False
        return verify_digest(
            semantic_payload(receipt, exclude={"classification_digest"}),
            str(receipt.get("classification_digest") or ""),
        )

    def verify_redaction(self, receipt: Mapping[str, Any]) -> bool:
        if receipt.get("beast_object_type") != REDACTION_OBJECT_TYPE:
            return False
        if str(receipt.get("version") or "") != SENSITIVE_DATA_VERSION:
            return False
        if receipt.get("authority") != "redaction_and_admission_classification_only":
            return False
        if receipt.get("raw_secret_persisted") is not False:
            return False
        return verify_digest(
            semantic_payload(receipt, exclude={"receipt_digest"}),
            str(receipt.get("receipt_digest") or ""),
        )

    def assert_explicit_approval(
        self,
        classification: Mapping[str, Any],
        *,
        approval: Mapping[str, Any] | None,
    ) -> None:
        if not self.verify_classification(classification):
            raise ValueError("sensitive-data classification is invalid or tampered")
        if classification.get("explicit_approval_required") is not True:
            return
        approval = approval or {}
        if approval.get("decision") not in {"APPROVE", "EDIT_AND_APPROVE"}:
            raise ValueError("explicit sensitive-data approval is required")
        if str(approval.get("classification_digest") or "") != str(classification.get("classification_digest") or ""):
            raise ValueError("sensitive-data approval is not bound to this classification")
        if str(approval.get("scope") or "") not in {"ONCE", "EDITED_SCOPE_ONCE"}:
            raise ValueError("sensitive-data approval must be one-use")

    def _inspect(self, value: Any, matched_keys: set[str], value_types: set[str], *, key: str = "", depth: int = 0) -> None:
        if depth > 12:
            return
        if key and _sensitive_key(key):
            matched_keys.add(key)
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                self._inspect(child, matched_keys, value_types, key=str(child_key), depth=depth + 1)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in list(value)[:256]:
                self._inspect(child, matched_keys, value_types, key=key, depth=depth + 1)
        elif isinstance(value, (bytes, bytearray)):
            value_types.add("binary_secret_candidate")
        elif isinstance(value, str) and _looks_secret(value):
            value_types.add("secret_pattern")

    def _redact_value(self, value: Any, *, path: str, redacted_paths: list[str], max_text: int, key: str = "", depth: int = 0) -> Any:
        if depth > 12:
            redacted_paths.append(path)
            return {"redacted": True, "reason": "maximum_depth", "digest": _digest_any(value)}
        if key and _sensitive_key(key):
            redacted_paths.append(path)
            return {"redacted": True, "reason": "sensitive_key", "value_type": type(value).__name__, "digest": _digest_any(value)}
        if isinstance(value, Mapping):
            return {
                str(child_key): self._redact_value(
                    child, path=f"{path}.{child_key}", redacted_paths=redacted_paths,
                    max_text=max_text, key=str(child_key), depth=depth + 1,
                )
                for child_key, child in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [
                self._redact_value(child, path=f"{path}[{index}]", redacted_paths=redacted_paths, max_text=max_text, key=key, depth=depth + 1)
                for index, child in enumerate(list(value)[:256])
            ]
        if isinstance(value, (bytes, bytearray)):
            redacted_paths.append(path)
            return {"redacted": True, "reason": "binary_value", "byte_count": len(value), "digest": sha256_digest(bytes(value).hex())}
        if isinstance(value, str) and _looks_secret(value):
            redacted_paths.append(path)
            return {"redacted": True, "reason": "secret_pattern", "value_type": "str", "digest": sha256_digest(value)}
        if isinstance(value, str) and len(value) > max_text:
            return {"truncated": True, "character_count": len(value), "preview": value[:max_text], "digest": sha256_digest(value)}
        return canonicalize(value)


def policy_from_sensitive_payload(payload: Mapping[str, Any]) -> SensitiveDataPolicy:
    return SensitiveDataPolicy(
        generation=str(payload.get("generation") or "").strip() or "policy:default",
        path_patterns=_strings(payload.get("path_patterns")) or _DEFAULT_PATH_PATTERNS,
        explicit_approval_required=bool(payload.get("explicit_approval_required", True)),
        redact_model_context=bool(payload.get("redact_model_context", True)),
        redact_chronicle=bool(payload.get("redact_chronicle", True)),
        redact_sensorium=bool(payload.get("redact_sensorium", True)),
        redact_evidence=bool(payload.get("redact_evidence", True)),
        local_model_only_for_raw_secrets=bool(payload.get("local_model_only_for_raw_secrets", True)),
        max_visible_text=max(32, min(int(payload.get("max_visible_text") or 240), 4096)),
    )
