"""Structural crystal assistance compiler.

Retrieval is broad enough to help the residual solver, while execution remains
strictly bound to repository, verifier, policy, and tool fingerprints.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CrystalAssistancePacket:
    task_family: str
    lifecycle_phase: str
    verifier_signature: str
    target_files: List[str]
    target_symbols: List[str]
    compatible_crystals: List[Dict[str, Any]] = field(default_factory=list)
    prior_effect_patterns: List[Dict[str, Any]] = field(default_factory=list)
    allowed_operations: List[str] = field(default_factory=lambda: ["replace_exact"])
    forbidden_operations: List[str] = field(default_factory=lambda: ["choose_file", "choose_tool", "choose_command", "choose_approval"])
    action_template: Dict[str, Any] = field(default_factory=dict)
    unresolved_fields: List[str] = field(default_factory=lambda: ["new"])
    confidence: float = 0.0
    refusal_reasons: List[str] = field(default_factory=list)
    assistance_key: str = ""
    applicability_key: str = ""
    assistance_mode: str = "fresh_bounded"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_family": self.task_family,
            "lifecycle_phase": self.lifecycle_phase,
            "verifier_signature": self.verifier_signature,
            "target_files": list(self.target_files),
            "target_symbols": list(self.target_symbols),
            "compatible_crystals": list(self.compatible_crystals),
            "prior_effect_patterns": list(self.prior_effect_patterns),
            "allowed_operations": list(self.allowed_operations),
            "forbidden_operations": list(self.forbidden_operations),
            "action_template": dict(self.action_template),
            "unresolved_fields": list(self.unresolved_fields),
            "confidence": self.confidence,
            "refusal_reasons": list(self.refusal_reasons),
            "assistance_key": self.assistance_key,
            "applicability_key": self.applicability_key,
            "assistance_mode": self.assistance_mode,
            "crystal_assistance_compiled": True,
            "mutation_authorized": False,
            "model_call_required": self.assistance_mode != "deterministic_reuse",
        }


class CrystalAssistanceCompiler:
    """Compile crystal candidates into bounded assistance, never authority."""

    def compile(self, request: Dict[str, Any]) -> CrystalAssistancePacket:
        task_family = str(request.get("task_family") or request.get("task_class") or "general")
        failure_signature = str(request.get("verifier_signature") or request.get("failure_signature") or "")
        symbol_shape = str(request.get("symbol_shape") or request.get("target_symbol") or "unknown")
        operation_family = str(request.get("operation_family") or "replace_exact")
        policy_class = str(request.get("policy_class") or "local_first")
        authority_boundary = str(request.get("authority_boundary") or "isolated_worktree")
        assistance_key = _hash({
            "task_family": task_family,
            "failure_signature": failure_signature,
            "symbol_shape": symbol_shape,
            "operation_family": operation_family,
        })
        applicability_key = _hash({
            "repository_fingerprint": request.get("repository_fingerprint") or "",
            "target_hash": request.get("target_hash") or "",
            "verifier_contract": request.get("verifier_contract") or failure_signature,
            "policy_generation": request.get("policy_generation") or policy_class,
            "tool_schema": request.get("tool_schema") or "replace_exact:v1",
        })
        advisory = [dict(item) for item in request.get("advisory_crystals") or [] if isinstance(item, dict)]
        scaffold = [dict(item) for item in request.get("scaffold_crystals") or [] if isinstance(item, dict)]
        execution = [dict(item) for item in request.get("execution_crystals") or [] if isinstance(item, dict)]
        compatible = [item for item in execution if item.get("applicability_key") in {applicability_key, "", None} and item.get("compatible", True)]
        refusal_reasons = []
        if execution and not compatible:
            refusal_reasons.append("execution crystal applicability proof did not match")
        if compatible:
            mode = "deterministic_reuse"
        elif scaffold:
            mode = "scaffolded"
        elif advisory:
            mode = "advisory"
        else:
            mode = "fresh_bounded"
        patterns = advisory + scaffold + compatible
        confidence = min(1.0, max([float(item.get("confidence") or 0.0) for item in patterns] or [0.0]))
        template = {
            "kind": "replace_exact",
            "path": str(request.get("target_file") or (request.get("target_files") or [""])[0]),
            "symbol": symbol_shape,
            "old": str(request.get("old") or ""),
            "new": "<UNRESOLVED>",
            "verifier": str(request.get("verifier_command") or "pytest -q"),
            "authority": authority_boundary,
        }
        if compatible and compatible[0].get("replacement"):
            template["new"] = str(compatible[0]["replacement"])
        return CrystalAssistancePacket(
            task_family=task_family,
            lifecycle_phase=str(request.get("lifecycle_phase") or "PATCH_REQUIRED"),
            verifier_signature=failure_signature,
            target_files=[str(item) for item in request.get("target_files") or ([request.get("target_file")] if request.get("target_file") else [])],
            target_symbols=[symbol_shape] if symbol_shape and symbol_shape != "unknown" else [],
            compatible_crystals=compatible,
            prior_effect_patterns=patterns,
            action_template=template,
            unresolved_fields=[] if compatible and compatible[0].get("replacement") else ["new"],
            confidence=confidence,
            refusal_reasons=refusal_reasons,
            assistance_key=assistance_key,
            applicability_key=applicability_key,
            assistance_mode=mode,
        )
