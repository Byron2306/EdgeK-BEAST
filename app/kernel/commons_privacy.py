"""Privacy and archive-safety checks for portable BEAST Compute Spaces."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List


SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "password", "secret", "token",
    "access_token", "refresh_token", "private_key", "raw_prompt", "source_code",
}
SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._-]{8,}|(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,}\]]{6,})"
)
PRIVATE_PATH = re.compile(r"(?m)(?:^|[\s\"'])/(?:home|Users|workspace|private|tmp)/")
PRIVATE_KEY_BLOCK = re.compile(
    rb"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED |)PRIVATE KEY-----"
)
PRIVATE_KEY_NAME = re.compile(
    r"(?i)(?:^|/)(?:id_(?:rsa|dsa|ecdsa|ed25519)|.*(?:private[_-]?key|node_ed25519).*|.*\.(?:pem|key|p8|p12))$"
)
FORBIDDEN_EXPORT_NAME = re.compile(
    r"(?i)(?:^|/)(?:.*raw[_-]?prompt.*|.*rollback[_-]?(?:snapshot|fixture).*|.*(?:private[_-]?)?source[_-]?fixture.*|.*private[_-]?test[_-]?fixture.*)$"
)


class CommonsPrivacyScrubber:
    def __init__(self, *, max_files: int = 256, max_uncompressed_bytes: int = 20_000_000):
        self.max_files = max_files
        self.max_uncompressed_bytes = max_uncompressed_bytes

    def scan_payload(self, payload: Any, path: str = "$") -> List[Dict[str, str]]:
        findings: List[Dict[str, str]] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized = str(key).strip().lower().replace("-", "_")
                child = f"{path}.{key}"
                if normalized in SENSITIVE_KEYS and value not in (None, "", False, "***REDACTED***"):
                    findings.append({"path": child, "reason": "sensitive_key"})
                findings.extend(self.scan_payload(value, child))
        elif isinstance(payload, list):
            for index, value in enumerate(payload):
                findings.extend(self.scan_payload(value, f"{path}[{index}]"))
        elif isinstance(payload, str):
            if SECRET_VALUE.search(payload):
                findings.append({"path": path, "reason": "possible_secret_material"})
            if PRIVATE_PATH.search(payload):
                findings.append({"path": path, "reason": "absolute_private_path"})
        return findings

    def scan_file(self, path: Path) -> Dict[str, Any]:
        body = path.read_bytes()
        findings: List[Dict[str, str]] = []
        if self.looks_like_private_key_path(str(path)):
            findings.append({"path": path.name, "reason": "private_key_file"})
        forbidden_reason = self.forbidden_export_path_reason(str(path))
        if forbidden_reason:
            findings.append({"path": path.name, "reason": forbidden_reason})
        if PRIVATE_KEY_BLOCK.search(body[:16_384]):
            findings.append({"path": path.name, "reason": "private_key_material"})
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                findings.extend(self.scan_payload(json.loads(body.decode("utf-8"))))
            except (UnicodeDecodeError, json.JSONDecodeError):
                findings.append({"path": path.name, "reason": "invalid_json"})
        elif suffix in {".md", ".txt", ".yaml", ".yml", ".toml"}:
            text = body.decode("utf-8", errors="replace")
            if SECRET_VALUE.search(text):
                findings.append({"path": path.name, "reason": "possible_secret_material"})
            if PRIVATE_PATH.search(text):
                findings.append({"path": path.name, "reason": "absolute_private_path"})
        return {"path": str(path), "bytes": len(body), "safe": not findings, "findings": findings}

    def scan_space(self, root: Path, relative_paths: List[str]) -> Dict[str, Any]:
        reports = []
        for rel in relative_paths:
            safe_rel = self.safe_relative_path(rel)
            path = root / safe_rel
            if not path.is_file():
                reports.append({
                    "path": str(path),
                    "bytes": 0,
                    "safe": False,
                    "findings": [{"path": safe_rel, "reason": "missing_artifact"}],
                })
                continue
            reports.append(self.scan_file(path))
        findings = [finding for report in reports for finding in report["findings"]]
        return {
            "beast_object_type": "commons_privacy_scan",
            "version": "1.0",
            "safe": not findings,
            "files_scanned": len(reports),
            "findings": findings,
        }

    def scan_bundle(self, bundle: Path) -> Dict[str, Any]:
        findings: List[Dict[str, str]] = []
        with zipfile.ZipFile(bundle) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                findings.append({"path": "$archive", "reason": "duplicate_archive_entry"})
            if len(infos) > self.max_files:
                findings.append({"path": "$archive", "reason": "file_count_limit_exceeded"})
            total = sum(max(0, info.file_size) for info in infos)
            if total > self.max_uncompressed_bytes:
                findings.append({"path": "$archive", "reason": "uncompressed_size_limit_exceeded"})
            for info in infos[: self.max_files + 1]:
                try:
                    rel = self.safe_relative_path(info.filename)
                except ValueError:
                    findings.append({"path": info.filename, "reason": "unsafe_archive_path"})
                    continue
                if self.looks_like_private_key_path(rel):
                    findings.append({"path": rel, "reason": "private_key_file"})
                forbidden_reason = self.forbidden_export_path_reason(rel)
                if forbidden_reason:
                    findings.append({"path": rel, "reason": forbidden_reason})
                if info.flag_bits & 0x1:
                    findings.append({"path": rel, "reason": "encrypted_archive_entry"})
                    continue
                if info.compress_size and info.file_size / info.compress_size > 100:
                    findings.append({"path": rel, "reason": "compression_ratio_limit_exceeded"})
                    continue
                if info.file_size > 2_000_000:
                    findings.append({"path": rel, "reason": "entry_size_limit_exceeded"})
                    continue
                body = archive.read(info)
                if PRIVATE_KEY_BLOCK.search(body[:16_384]):
                    findings.append({"path": rel, "reason": "private_key_material"})
                    continue
                suffix = Path(rel).suffix.lower()
                if suffix not in {".json", ".md", ".txt", ".yaml", ".yml", ".toml"}:
                    continue
                if suffix == ".json":
                    try:
                        findings.extend(self.scan_payload(json.loads(body.decode("utf-8")), rel))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        findings.append({"path": rel, "reason": "invalid_json"})
                else:
                    text = body.decode("utf-8", errors="replace")
                    if SECRET_VALUE.search(text):
                        findings.append({"path": rel, "reason": "possible_secret_material"})
                    if PRIVATE_PATH.search(text):
                        findings.append({"path": rel, "reason": "absolute_private_path"})
        return {
            "beast_object_type": "commons_bundle_privacy_scan",
            "version": "1.0",
            "safe": not findings,
            "files_scanned": len(infos),
            "uncompressed_bytes": total,
            "findings": findings,
        }

    @staticmethod
    def safe_relative_path(value: str) -> str:
        path = PurePosixPath(str(value).replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts or path == PurePosixPath("."):
            raise ValueError(f"path must be local and relative: {value}")
        return str(path)

    @staticmethod
    def looks_like_private_key_path(value: str) -> bool:
        rel = str(PurePosixPath(str(value).replace("\\", "/")))
        return bool(PRIVATE_KEY_NAME.search(rel))

    @staticmethod
    def forbidden_export_path_reason(value: str) -> str:
        rel = str(PurePosixPath(str(value).replace("\\", "/")))
        return "forbidden_private_fixture_path" if FORBIDDEN_EXPORT_NAME.search(rel) else ""
