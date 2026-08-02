"""Read-only compiler from Cartographer evidence to bounded Action IR."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from app.kernel.compute.action_ir import ACTION_IR_KIND, ActionIR
from app.kernel.compute.crystal_ir import CrystalIR, compile_crystal_ir


class ResidualPatchCompiler:
    """Construct a template and leave only explicitly unresolved fields."""

    def compile_crystal_ir(self, ir: CrystalIR | Dict[str, Any], *, old: str, new: str = "") -> Dict[str, Any]:
        """Turn a validated interpretation into a bounded residual handoff.

        Crystal IR supplies intent and authority constraints.  The current
        source snippet is supplied by BEAST, never invented by the translator.
        """
        canonical = ir if isinstance(ir, CrystalIR) else compile_crystal_ir(ir)
        return self.compile({
            "target": {"path": canonical.target_file, "symbol": canonical.target_symbol},
            "objective": canonical.objective,
            "old": old,
            "new": new,
            "verify": list(canonical.postconditions),
            "residual_contract": {
                "scope": "exact_snippet",
                "value_schema": {"type": "nonempty_source_fragment", "field": "new"},
            },
        })

    def compile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
        path = str(target.get("path") or payload.get("path") or "").strip()
        if not path or path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/"):
            raise ValueError("Patch Compiler requires one safe relative target path")
        old = str(payload.get("old") or payload.get("residual_old") or "")
        if not old:
            raise ValueError("Patch Compiler requires an explicit exact old snippet; whole-file residuals are forbidden")
        new = str(payload.get("new") or "")
        unresolved = [] if new else ["new"]
        contract = payload.get("residual_contract") if isinstance(payload.get("residual_contract"), dict) else {}
        action = {
            "id": "a1",
            "type": "replace_exact",
            "target": {
                "path": path,
                "symbol": str(target.get("symbol") or ""),
                "sha256": str(target.get("sha256") or payload.get("target_fingerprint") or ""),
            },
            "intent": str(payload.get("objective") or payload.get("intent") or "bounded residual repair"),
            "constraints": ["one file", "one operation", "no commands", "fresh verification required"],
            "parameters": {
                "unresolved_field": "new" if unresolved else "",
                "scope": str(contract.get("scope") or "exact_snippet"),
                "value_schema": contract.get("value_schema") or {"type": "nonempty_source_fragment"},
            },
            "old": old,
            "new": new,
        }
        action_ir = ActionIR.from_dict({
            "kind": ACTION_IR_KIND,
            "objective": str(payload.get("objective") or ""),
            "actions": [action],
            "verify": [str(item) for item in payload.get("verify") or []],
            "fallback": "refuse_if_target_or_old_text_does_not_match",
        })
        serialized = action_ir.to_dict()
        handoff_hash = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
        return {
            "action_ir": serialized,
            "unresolved_fields": unresolved,
            "resolver_status": "template_valid",
            "handoff_hash": f"sha256:{handoff_hash}",
            "mutation_authorized": False,
            "read_only": True,
            "residual_contract": {
                "field": "new" if unresolved else "",
                "scope": str(contract.get("scope") or "exact_snippet"),
                "old": old,
                "value_schema": contract.get("value_schema") or {"type": "nonempty_source_fragment"},
                "forbidden_placeholders": ["complete replacement source", "replacement code here", "TODO", "insert code"],
            },
            "contribution_accounting": contribution_accounting(serialized, unresolved),
        }


def contribution_accounting(action_ir: Dict[str, Any], unresolved_fields: list[str], resolved_fields: list[str] | None = None) -> Dict[str, Any]:
    """Count bounded Action IR fields by their authoritative supplier."""
    actions = action_ir.get("actions") if isinstance(action_ir.get("actions"), list) else []
    action = actions[0] if actions and isinstance(actions[0], dict) else {}
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    fields = {
        "kind": action_ir.get("kind"), "objective": action_ir.get("objective"),
        "operation_type": action.get("type"), "target_path": target.get("path"),
        "target_symbol": target.get("symbol"), "old": action.get("old"),
        "new": action.get("new"), "verification": action_ir.get("verify"),
    }
    unresolved = {str(item) for item in unresolved_fields or []}
    resolved = {str(item) for item in resolved_fields or []}
    model_fields = sorted(field for field in unresolved if field in {"new", "replacement_statement", "replacement_expression"} and (not resolved or field in resolved))
    beast_fields = sorted(field for field in fields if field not in model_fields)
    total = len(fields)
    return {
        "action_fields_total": total,
        "fields_supplied_by_beast": len(beast_fields),
        "fields_supplied_by_ollama": len(model_fields),
        "beast_fields": beast_fields,
        "ollama_fields": model_fields,
        "ollama_semantic_share": round(len(model_fields) / max(1, total), 4),
        "model_authority": "declared_residual_fields_only",
    }
