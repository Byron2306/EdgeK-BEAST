"""Privacy-before-admission policy for Sensorium events."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Tuple

from app.kernel.sensorium.contracts import SensorEvent


class SensorPrivacyError(ValueError):
    """Raised when an event cannot safely enter the retained Sensorium."""


class SensorPrivacyGate:
    """Redact sensitive values and mark the resulting event as scanned.

    This gate intentionally favors metadata over raw content.  It is not a DLP
    product; callers must still avoid collecting payloads they do not need.
    """

    SENSITIVE_KEYS = {
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "environment",
        "password",
        "private_key",
        "raw_content",
        "raw_prompt",
        "raw_source",
        "secret",
        "source_code",
        "token",
    }
    SECRET_PATTERNS = (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"(?i)\b(?:api[_-]?key|password|secret)\s*[:=]\s*\S+"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    )
    ALLOWED_PRIVACY_CLASSES = {
        "public",
        "internal",
        "internal_sensitive",
        "restricted",
    }
    ALLOWED_RETENTION = {"none", "ephemeral", "durable_internal"}

    def sanitize(self, event: SensorEvent) -> Tuple[SensorEvent, List[str]]:
        privacy = dict(event.privacy)
        privacy_class = str(privacy.get("class") or "")
        retention = str(privacy.get("raw_retention") or "")
        if privacy_class not in self.ALLOWED_PRIVACY_CLASSES:
            raise SensorPrivacyError(f"unsupported privacy class: {privacy_class or '<missing>'}")
        if retention not in self.ALLOWED_RETENTION:
            raise SensorPrivacyError(f"unsupported raw retention: {retention or '<missing>'}")
        if not isinstance(privacy.get("export_allowed"), bool):
            raise SensorPrivacyError("privacy.export_allowed must be boolean")

        sanitized, findings = self._sanitize_value(event.payload, path="payload")
        if not isinstance(sanitized, dict):
            raise SensorPrivacyError("sanitized payload must remain an object")
        privacy["redaction_status"] = "passed"
        privacy["redaction_count"] = len(findings)
        privacy["raw_content_retained"] = False
        if privacy_class in {"internal_sensitive", "restricted"}:
            privacy["export_allowed"] = False
        return replace(event, payload=sanitized, privacy=privacy, payload_sha256="", event_id="").sealed(), findings

    def _sanitize_value(self, value: Any, *, path: str) -> Tuple[Any, List[str]]:
        findings: List[str] = []
        if isinstance(value, dict):
            result: Dict[str, Any] = {}
            for key, item in value.items():
                normalized = str(key).lower()
                item_path = f"{path}.{key}"
                if normalized in self.SENSITIVE_KEYS or any(
                    fragment in normalized
                    for fragment in ("private_key", "api_key", "password", "raw_prompt", "raw_source")
                ):
                    result[str(key)] = "[REDACTED]"
                    findings.append(f"sensitive_key:{item_path}")
                    continue
                result[str(key)], child_findings = self._sanitize_value(item, path=item_path)
                findings.extend(child_findings)
            return result, findings
        if isinstance(value, list):
            result_list = []
            for index, item in enumerate(value):
                sanitized, child_findings = self._sanitize_value(item, path=f"{path}[{index}]")
                result_list.append(sanitized)
                findings.extend(child_findings)
            return result_list, findings
        if isinstance(value, tuple):
            return self._sanitize_value(list(value), path=path)
        if isinstance(value, str):
            sanitized = value
            for pattern in self.SECRET_PATTERNS:
                if pattern.search(sanitized):
                    sanitized = pattern.sub("[REDACTED]", sanitized)
                    findings.append(f"secret_pattern:{path}")
            return sanitized, findings
        if value is None or isinstance(value, (bool, int, float)):
            return value, findings
        findings.append(f"unsupported_value:{path}")
        return str(value), findings
