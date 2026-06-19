"""Provider output governance and deterministic patch-intent compilation."""

from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.kernel.action_ir import ACTION_IR_KIND, ActionIR, action_ir_schema
from app.kernel.action_resolver import build_file_references, resolve_action_ir
from app.kernel.local_patch_compiler import compile_resolved_actions
from app.kernel.output_evidence import base_output_evidence


@dataclass(frozen=True)
class ProviderOutputProfile:
    provider: str
    role: str = "source_patch_generator"
    max_operations: int = 5
    max_output_chars: int = 12000
    max_old_chars: int = 800
    max_new_chars: int = 1600
    allowed_ops: List[str] = field(default_factory=lambda: ["create_or_replace", "replace_exact", "insert_after", "delete_exact"])
    forbid_full_file_replacement: bool = False
    refs_only: bool = False
    forbid_old_when_anchor_ref: bool = False
    require_exact_old_snippet: bool = True
    repair_attempts: int = 1
    fallback_provider_on_schema_failure: bool = False


class OutputValidationError(ValueError):
    """Raised when provider output cannot be safely compiled."""


@dataclass
class OutputGateResult:
    ok: bool
    operations: List[Dict[str, str]]
    evidence: Dict[str, Any]
    error: str = ""
    non_mutating_requests: List[Dict[str, Any]] = field(default_factory=list)


def extract_json_object_from_text(text: str) -> Dict[str, Any]:
    """Extract the first usable JSON object from raw provider output."""
    text = (text or "").strip()
    if not text:
        return {}
    candidates: List[str] = []
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(match.group(1))
    candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            continue
    return {}


def provider_output_profile(provider: str) -> ProviderOutputProfile:
    provider_id = str(provider or "").lower().replace("-", "_")
    if "nvidia" in provider_id or "nim" in provider_id:
        return ProviderOutputProfile(
            provider=provider_id or "nvidia_nim",
            role="refs_only_action_ir_generator",
            max_operations=4,
            max_output_chars=6000,
            max_old_chars=500,
            max_new_chars=600,
            allowed_ops=["replace_exact", "insert_after", "delete_exact"],
            forbid_full_file_replacement=True,
            refs_only=True,
            forbid_old_when_anchor_ref=True,
            require_exact_old_snippet=False,
            repair_attempts=1,
            fallback_provider_on_schema_failure=True,
        )
    if "huggingface" in provider_id or "openrouter" in provider_id:
        return ProviderOutputProfile(
            provider=provider_id,
            role="live_action_ir_generator",
            max_operations=5,
            max_output_chars=12000,
            max_old_chars=500,
            max_new_chars=900,
            allowed_ops=["replace_exact", "insert_after", "delete_exact"],
            forbid_full_file_replacement=True,
            refs_only=False,
            forbid_old_when_anchor_ref=True,
            require_exact_old_snippet=False,
            repair_attempts=2,
        )
    return ProviderOutputProfile(provider=provider_id or "default")


def _anchor_label(anchor: str) -> str:
    compact = " ".join((anchor or "").strip().split())
    if len(compact) <= 96:
        return compact
    return compact[:93].rstrip() + "..."


def _public_file_ref(item: Any, redact_anchors: bool) -> Dict[str, Any]:
    data = item.to_dict()
    if not redact_anchors:
        return data
    data["anchors"] = [
        {
            "ref": ref,
            "label": _anchor_label(anchor),
            "chars": len(anchor),
            "sha256": hashlib.sha256(anchor.encode("utf-8")).hexdigest(),
        }
        for ref, anchor in sorted((item.anchors or {}).items())
    ]
    return data


def output_contract_schema(profile: ProviderOutputProfile) -> Dict[str, Any]:
    if profile.forbid_full_file_replacement:
        return action_ir_schema()
    return {
        "kind": "beast.source_patch.v1 or beast.patch_intent.v1",
        "operations": [
            {
                "op_id": "op_001",
                "op": "create_or_replace | replace_exact | insert_after | delete_exact",
                "path": "one allowed path",
                "content": "complete replacement content only for create_or_replace",
                "old": "exact snippet for intent ops",
                "new": "replacement snippet for intent ops",
                "why": "short reason",
            }
        ],
        "tests": ["python -m pytest tests -q"],
    }


def output_reference_packet(root: Path, allowed_paths: Iterable[str], profile: ProviderOutputProfile) -> Dict[str, Any]:
    refs = build_file_references(root, allowed_paths, include_anchors=profile.forbid_full_file_replacement)
    return {
        "files": [_public_file_ref(item, redact_anchors=profile.refs_only) for item in refs],
        "rules": {
            "prefer_refs": True,
            "use_file_ref": True,
            "use_anchor_ref": profile.forbid_full_file_replacement,
            "do_not_copy_anchor_text": profile.forbid_full_file_replacement,
        },
    }


def output_contract_instructions(profile: ProviderOutputProfile) -> List[str]:
    lines = [
        "Return exactly one compact JSON object. No markdown. Do not explain.",
        "Do not include chain-of-thought or analysis.",
        "Use only allowed paths and allowed operations.",
        f"Use at most {profile.max_operations} operation(s).",
        f"Keep every old snippet under {profile.max_old_chars} characters.",
        f"Keep every new snippet under {profile.max_new_chars} characters.",
        "Prefer several small anchored edits over one large block replacement.",
    ]
    if profile.forbid_full_file_replacement:
        lines.append("Do not output full files.")
        lines.append("Return BEAST Action IR, not source files or diffs.")
        lines.append("Use file_ref and anchor_ref from the reference packet; do not copy anchor text into old unless no anchor_ref applies.")
        lines.append("When target.anchor_ref is present, omit the old field entirely.")
        lines.append("Copy trace.provider_handoff_hash into the top-level provider_handoff_hash field.")
        lines.append("Use replace_anchor actions with the smallest possible new snippet.")
    return lines


def _validate_action_ir(action_ir: ActionIR, profile: ProviderOutputProfile) -> None:
    if len(action_ir.actions) > profile.max_operations:
        raise OutputValidationError(f"too many actions: {len(action_ir.actions)}>{profile.max_operations}")
    for action in action_ir.actions:
        if profile.forbid_old_when_anchor_ref and action.target.anchor_ref and action.old:
            raise OutputValidationError(f"action {action.id} copied old despite anchor_ref")
        if action.old and len(action.old) > profile.max_old_chars:
            raise OutputValidationError(f"action {action.id} old exceeded {profile.max_old_chars} chars")
        if action.new and len(action.new) > profile.max_new_chars:
            raise OutputValidationError(f"action {action.id} new exceeded {profile.max_new_chars} chars")


def output_gate(
    root: Path,
    raw_text: str,
    allowed_paths: Iterable[str],
    profile: ProviderOutputProfile,
    usage: Dict[str, Any] | None = None,
    latency_ms: float | None = None,
    expected_handoff_hash: str = "",
) -> OutputGateResult:
    """Intercept, parse, validate, and compile provider output into actions."""

    payload = extract_json_object_from_text(raw_text)
    contract = ACTION_IR_KIND if profile.forbid_full_file_replacement else "beast.source_patch.v1"
    evidence = base_output_evidence(profile, contract, raw_text, usage=usage, latency_ms=latency_ms)
    evidence["json_parse_ok"] = bool(payload)
    try:
        is_action_ir = str(payload.get("kind") or "") == ACTION_IR_KIND or isinstance(payload.get("actions"), list)
        if is_action_ir and not str(payload.get("provider_handoff_hash") or ""):
            raise OutputValidationError("Action IR missing provider_handoff_hash")
        if profile.refs_only and not is_action_ir:
            raise OutputValidationError("refs-only provider must return BEAST Action IR")
        if is_action_ir:
            file_refs = build_file_references(root, allowed_paths)
            action_ir = ActionIR.from_dict(payload)
            _validate_action_ir(action_ir, profile)
            resolved, non_mutating = resolve_action_ir(root, action_ir, file_refs, allowed_paths, expected_handoff_hash=expected_handoff_hash)
            operations = compile_resolved_actions(
                root,
                resolved,
                max_old_chars=profile.max_old_chars,
                max_new_chars=profile.max_new_chars,
            )
            evidence["contract"] = ACTION_IR_KIND
            evidence["action_count"] = len(action_ir.actions)
            evidence["non_mutating_request_count"] = len(non_mutating)
            evidence["non_mutating_requests"] = [item.to_dict() for item in non_mutating]
        else:
            operations = compile_provider_output(root, payload, allowed_paths, profile)
            non_mutating = []
        evidence.update({
            "schema_valid": True,
            "path_valid": True,
            "operation_valid": True,
            "anchor_match_rate": 1.0,
            "diff_compiled": True,
            "compiled_operation_count": len(operations),
            "final_status": "compiled",
        })
        return OutputGateResult(True, operations, evidence, non_mutating_requests=[item.to_dict() for item in non_mutating])
    except Exception as exc:
        evidence["final_status"] = "output_validation_failed"
        evidence["error"] = str(exc)
        return OutputGateResult(False, [], evidence, error=str(exc))


def compile_provider_output(
    root: Path,
    payload: Dict[str, Any],
    allowed_paths: Iterable[str],
    profile: ProviderOutputProfile | None = None,
) -> List[Dict[str, str]]:
    profile = profile or provider_output_profile("")
    allowed = {str(path) for path in allowed_paths}
    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise OutputValidationError("provider output did not include operations list")
    if len(operations) > profile.max_operations:
        raise OutputValidationError(f"too many operations: {len(operations)}>{profile.max_operations}")

    staged: Dict[str, str] = {}
    compiled: List[Dict[str, str]] = []
    for index, raw in enumerate(operations):
        if not isinstance(raw, dict):
            raise OutputValidationError(f"operations[{index}] was not an object")
        rel = str(raw.get("path") or "").strip()
        if rel not in allowed:
            raise OutputValidationError(f"operations[{index}].path was not allowed: {rel}")
        op = str(raw.get("op") or ("create_or_replace" if "content" in raw else "")).strip()
        if op not in profile.allowed_ops:
            raise OutputValidationError(f"operations[{index}].op was not allowed: {op}")
        if op == "create_or_replace":
            if profile.forbid_full_file_replacement:
                raise OutputValidationError("full-file replacement forbidden for this provider")
            content = raw.get("content")
            if not isinstance(content, str) or not content.strip():
                raise OutputValidationError(f"operations[{index}].content was empty")
            staged[rel] = content
            compiled.append({"path": rel, "content": content, "description": str(raw.get("why") or raw.get("description") or "")})
            continue

        current = staged.get(rel)
        if current is None:
            path = (root / rel).resolve()
            if not path.exists():
                raise OutputValidationError(f"intent target did not exist: {rel}")
            current = path.read_text(encoding="utf-8")
        old = raw.get("old")
        new = "" if op == "delete_exact" else raw.get("new")
        if not isinstance(old, str) or not old:
            raise OutputValidationError(f"operations[{index}].old was empty")
        if not isinstance(new, str):
            raise OutputValidationError(f"operations[{index}].new was not a string")
        if len(old) > profile.max_old_chars:
            raise OutputValidationError(f"operations[{index}].old exceeded {profile.max_old_chars} chars")
        if len(new) > profile.max_new_chars:
            raise OutputValidationError(f"operations[{index}].new exceeded {profile.max_new_chars} chars")
        count = current.count(old)
        if count != 1:
            raise OutputValidationError(f"operations[{index}].old matched {count} times in {rel}")
        if op == "insert_after":
            updated = current.replace(old, old + new, 1)
        else:
            updated = current.replace(old, new, 1)
        staged[rel] = updated
        compiled.append({"path": rel, "content": updated, "description": str(raw.get("why") or "")})

    # Collapse multiple anchored edits to the same file into one deterministic write.
    by_path: Dict[str, Dict[str, str]] = {}
    for item in compiled:
        by_path[item["path"]] = item
    return [by_path[path] for path in sorted(by_path)]
