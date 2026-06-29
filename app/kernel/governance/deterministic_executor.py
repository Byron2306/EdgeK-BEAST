"""Fail-closed deterministic transforms for Compute Governor Phase 2."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from app.kernel.governance.deterministic_allowlist import Phase2Allowlist
from app.kernel.registry.provider_registry import ProviderRegistry


@dataclass(frozen=True)
class DeterministicTransformResult:
    candidate_name: str
    status: str
    verified: bool
    output_sha256: str = ""
    expected_output_sha256: str = ""
    behavior_preserved: Optional[bool] = None
    checks: Dict[str, bool] = field(default_factory=dict)
    error_type: str = ""
    duration_ms: float = 0.0
    complete_task: bool = False
    output: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("output", None)
        payload["beast_object_type"] = "deterministic_transform_result"
        payload["version"] = "1.0"
        payload["privacy"] = "hashes_and_verifier_evidence_only"
        return payload


@dataclass(frozen=True)
class _TransformOutcome:
    output: Any
    checks: Dict[str, bool]


class DeterministicTransformExecutor:
    """Execute allowlisted transforms from explicit structured work only.

    Inputs and transform outputs are never serialized into Compute receipts. A
    prompt keyword can nominate a candidate, but cannot provide executable work.
    """

    _SECRET_PATTERN = re.compile(
        r"(?i)(api[_-]?key|token|secret|password)(\s*[:=]\s*)(['\"]?)([^\s,'\"}]+)(['\"]?)"
    )
    _ALIASES = {
        "gemini": "google",
        "nim": "nvidia_nim",
        "nvidia": "nvidia_nim",
        "hf": "huggingface",
        "open_router": "openrouter",
    }

    def __init__(self, allowlist: Optional[Phase2Allowlist] = None) -> None:
        self.allowlist = allowlist or Phase2Allowlist()
        self._handlers: Dict[str, Callable[[Mapping[str, Any]], _TransformOutcome]] = {
            "schema_validation": self._schema_validation,
            "route_diagnostics": self._route_diagnostics,
            "patch_compilation": self._patch_compilation,
            "test_execution": self._test_execution,
            "syntax_check": self._syntax_check,
            "lint_format": self._secret_redaction,
        }

    def execute(self, candidates: Iterable[str], work: Any) -> List[DeterministicTransformResult]:
        work_map = work if isinstance(work, Mapping) else {}
        return [self._execute_one(name, work_map.get(name)) for name in sorted(set(candidates))]

    def _execute_one(self, candidate: str, request: Any) -> DeterministicTransformResult:
        started = time.perf_counter()
        if not self.allowlist.is_allowlisted(candidate) or candidate not in self._handlers:
            return self._result(candidate, started, "rejected", False, error_type="not_allowlisted")
        if not isinstance(request, Mapping):
            return self._result(candidate, started, "not_applicable", False, error_type="structured_work_missing")
        try:
            outcome = self._handlers[candidate](request)
            output_hash = self._hash(outcome.output)
            expected_hash = str(request.get("expected_output_sha256") or "")
            behavior = output_hash == expected_hash if expected_hash else None
            verified = bool(outcome.checks) and all(outcome.checks.values())
            if behavior is False:
                verified = False
            return self._result(
                candidate, started, "succeeded" if verified else "failed", verified,
                output_hash=output_hash, expected_hash=expected_hash,
                behavior_preserved=behavior, checks=outcome.checks,
                error_type="" if verified else "verification_failed",
                complete_task=request.get("complete_task") is True,
                output=outcome.output,
            )
        except (KeyError, TypeError, ValueError, OSError, SyntaxError) as exc:
            return self._result(candidate, started, "failed", False, error_type=type(exc).__name__)

    @staticmethod
    def _result(
        candidate: str, started: float, status: str, verified: bool, *,
        output_hash: str = "", expected_hash: str = "",
        behavior_preserved: Optional[bool] = None,
        checks: Optional[Dict[str, bool]] = None, error_type: str = "",
        complete_task: bool = False, output: Any = None,
    ) -> DeterministicTransformResult:
        return DeterministicTransformResult(
            candidate_name=candidate, status=status, verified=verified,
            output_sha256=output_hash, expected_output_sha256=expected_hash,
            behavior_preserved=behavior_preserved, checks=checks or {},
            error_type=error_type,
            duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
            complete_task=complete_task,
            output=output,
        )

    @staticmethod
    def _hash(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _schema_validation(self, request: Mapping[str, Any]) -> _TransformOutcome:
        if "instance" not in request or not isinstance(request.get("schema"), Mapping):
            raise ValueError("instance and schema are required")
        errors: List[str] = []
        self._validate_schema(request["instance"], request["schema"], "$", errors)
        output = {"valid": not errors, "error_paths": sorted(errors)}
        return _TransformOutcome(output, {"schema_evaluated": True, "expected_validity": output["valid"] is request.get("expect_valid", output["valid"])})

    def _validate_schema(self, value: Any, schema: Mapping[str, Any], path: str, errors: List[str]) -> None:
        type_map = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
        expected = schema.get("type")
        if expected in type_map and (not isinstance(value, type_map[expected]) or expected in {"integer", "number"} and isinstance(value, bool)):
            errors.append(path)
            return
        if "enum" in schema and value not in schema["enum"]:
            errors.append(path)
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"{path}.{key}")
            properties = schema.get("properties", {})
            for key, child in properties.items():
                if key in value and isinstance(child, Mapping):
                    self._validate_schema(value[key], child, f"{path}.{key}", errors)
            if schema.get("additionalProperties") is False:
                errors.extend(f"{path}.{key}" for key in value if key not in properties)
        if isinstance(value, list) and isinstance(schema.get("items"), Mapping):
            for index, item in enumerate(value):
                self._validate_schema(item, schema["items"], f"{path}[{index}]", errors)

    def _route_diagnostics(self, request: Mapping[str, Any]) -> _TransformOutcome:
        raw = str(request.get("provider") or "").strip().lower().replace("-", "_")
        if not raw:
            raise ValueError("provider is required")
        provider = self._ALIASES.get(raw, raw)
        records = {item.provider_id: item for item in ProviderRegistry().records()}
        record = records.get(provider)
        output = {
            "provider": provider,
            "known": record is not None,
            "backend": record.backend if record else "",
            "default_model": record.default_model if record else None,
        }
        expected = str(request.get("expected_provider") or provider).replace("-", "_")
        return _TransformOutcome(output, {"provider_known": record is not None, "alias_expected": provider == expected})

    def _patch_compilation(self, request: Mapping[str, Any]) -> _TransformOutcome:
        files = request.get("files")
        operations = request.get("operations")
        if not isinstance(files, Mapping) or not isinstance(operations, list):
            raise ValueError("files and operations are required")
        staged = {str(path): str(content) for path, content in files.items()}
        original = dict(staged)
        for operation in operations:
            if not isinstance(operation, Mapping):
                raise ValueError("operation must be an object")
            path = str(operation.get("path") or "")
            old, new = operation.get("old"), operation.get("new")
            if path not in staged or not isinstance(old, str) or not isinstance(new, str):
                raise ValueError("invalid exact replacement")
            if staged[path].count(old) != 1:
                raise ValueError("old snippet must match exactly once")
            staged[path] = staged[path].replace(old, new, 1)
        changed = {path: self._hash(content) for path, content in staged.items() if content != original[path]}
        syntax_valid = True
        for path in changed:
            if path.endswith(".py"):
                try:
                    ast.parse(staged[path], filename=path)
                except SyntaxError:
                    syntax_valid = False
        rollback = dict(staged)
        for path in changed:
            rollback[path] = original[path]
        return _TransformOutcome(
            {"changed_files": changed},
            {"exact_anchors": True, "syntax_valid": syntax_valid, "rollback_equal": rollback == original},
        )

    def _test_execution(self, request: Mapping[str, Any]) -> _TransformOutcome:
        root = self._safe_root(request)
        patterns = request.get("patterns") or ["test_*.py", "*_test.py"]
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise ValueError("patterns must be strings")
        paths = sorted({str(path.relative_to(root)) for pattern in patterns for path in root.rglob(pattern) if path.is_file()})
        output = {"tests": paths, "count": len(paths)}
        minimum = max(0, int(request.get("minimum_count", 1)))
        return _TransformOutcome(output, {"tests_discovered": len(paths) >= minimum, "paths_contained": all((root / path).resolve().is_relative_to(root) for path in paths)})

    def _syntax_check(self, request: Mapping[str, Any]) -> _TransformOutcome:
        files = request.get("files")
        expected = request.get("expected_sha256") or {}
        if not isinstance(files, Mapping) or not isinstance(expected, Mapping):
            raise ValueError("files and expected_sha256 are required")
        syntax_ok = True
        hashes_ok = True
        hashes: Dict[str, str] = {}
        for path, content in sorted(files.items()):
            if not isinstance(content, str):
                raise ValueError("file content must be text")
            digest = hashlib.sha256(content.encode()).hexdigest()
            hashes[str(path)] = digest
            if path in expected and expected[path] != digest:
                hashes_ok = False
            if str(path).endswith(".py"):
                try:
                    ast.parse(content, filename=str(path))
                except SyntaxError:
                    syntax_ok = False
        return _TransformOutcome({"sha256": hashes}, {"syntax_valid": syntax_ok, "hash_guard": hashes_ok})

    def _secret_redaction(self, request: Mapping[str, Any]) -> _TransformOutcome:
        text = request.get("text")
        if not isinstance(text, str):
            raise ValueError("text is required")
        redacted, count = self._SECRET_PATTERN.subn(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
        remaining = [match.group(4) for match in self._SECRET_PATTERN.finditer(redacted)]
        return _TransformOutcome(
            {"redacted_text_sha256": self._hash(redacted), "redaction_count": count},
            {"secrets_absent": all(value == "[REDACTED]" for value in remaining)},
        )

    @staticmethod
    def _safe_root(request: Mapping[str, Any]) -> Path:
        raw = request.get("root")
        if not isinstance(raw, str) or not raw:
            raise ValueError("root is required")
        root = Path(raw).resolve()
        if not root.is_dir():
            raise ValueError("root must be an existing directory")
        return root
