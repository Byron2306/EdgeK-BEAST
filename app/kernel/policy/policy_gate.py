"""Canonical BEAST policy gate result.

This module normalizes mode, spec, safety, and SourcePlan policy decisions into
one small shape that API, MCP, TUI, and evidence surfaces can compare directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


DECISION_ORDER = ["allow", "warn", "require_approval", "sandbox_only", "block"]


def _normalize_decision(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "ok": "allow",
        "allowed": "allow",
        "proceed": "allow",
        "proceed_with_verification": "allow",
        "recorded": "allow",
        "sandbox/worktree_only": "sandbox_only",
        "sandbox_worktree_only": "sandbox_only",
        "worktree_only": "sandbox_only",
        "block_until_resolved": "block",
        "blocked": "block",
    }
    return aliases.get(text, text if text in DECISION_ORDER else "allow")


def strongest_decision(values: Iterable[str]) -> str:
    normalized = [_normalize_decision(value) for value in values]
    if not normalized:
        return "allow"
    return max(normalized, key=lambda item: DECISION_ORDER.index(item))


@dataclass
class PolicyGateResult:
    decision: str = "allow"
    mutation_allowed: bool = False
    reasons: List[str] = field(default_factory=list)
    receipts: Dict[str, Any] = field(default_factory=dict)
    verification_required: bool = True
    approval_required: bool = False
    rollback_required: bool = True
    worktree_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        decision = _normalize_decision(self.decision)
        return {
            "beast_object_type": "beast_policy_gate_result",
            "version": "1.0",
            "decision": decision,
            "mutation_allowed": bool(self.mutation_allowed and decision in {"allow", "warn"}),
            "reasons": [str(item) for item in self.reasons if str(item or "").strip()],
            "receipts": self.receipts,
            "verification_required": bool(self.verification_required),
            "approval_required": bool(self.approval_required or decision in {"require_approval", "sandbox_only", "block"}),
            "rollback_required": bool(self.rollback_required),
            "worktree_required": bool(self.worktree_required or decision == "sandbox_only"),
        }


def from_mode_tool_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    allowed = bool(decision.get("allowed"))
    return PolicyGateResult(
        decision="allow" if allowed else "block",
        mutation_allowed=allowed and str(decision.get("tool_profile") or "") == "edit",
        reasons=[str(decision.get("reason") or "")],
        receipts={"mode_tool_decision": decision},
        verification_required=False,
        approval_required=not allowed,
        rollback_required=False,
    ).to_dict()


def from_spec_covenant(covenant: Dict[str, Any]) -> Dict[str, Any]:
    lint = covenant.get("lint") if isinstance(covenant.get("lint"), dict) else {}
    severity = str(lint.get("severity") or "ok")
    reasons: List[str] = []
    if lint.get("unsafe_rules"):
        reasons.append("Spec Covenant found unsafe rule markers")
    if lint.get("mode_conflicts"):
        reasons.append("Spec Covenant found mode conflicts")
    if lint.get("conflict_pairs"):
        reasons.append("Spec Covenant found contradictory rules")
    return PolicyGateResult(
        decision="warn" if severity == "warn" else "allow",
        mutation_allowed=True,
        reasons=reasons,
        receipts={"spec_covenant": covenant.get("receipt") or {}},
        verification_required=True,
        approval_required=severity == "warn",
        rollback_required=True,
    ).to_dict()


def from_safety_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    decision = _normalize_decision(str(receipt.get("decision") or "allow"))
    reasons = []
    for item in receipt.get("reasons") or receipt.get("findings") or []:
        if isinstance(item, dict):
            reasons.append(str(item.get("detail") or item.get("kind") or "safety finding"))
        else:
            reasons.append(str(item))
    compact_receipt = {
        key: value
        for key, value in receipt.items()
        if key not in {"policy_gate", "evidence_bus", "findings", "reasons"}
    }
    return PolicyGateResult(
        decision=decision,
        mutation_allowed=decision in {"allow", "warn"},
        reasons=reasons,
        receipts={"safety_governor": compact_receipt},
        verification_required=True,
        approval_required=decision in {"require_approval", "sandbox_only", "block"},
        rollback_required=True,
        worktree_required=decision == "sandbox_only",
    ).to_dict()


def from_output_gate_result(result: Any) -> Dict[str, Any]:
    ok = bool(getattr(result, "ok", False))
    evidence = getattr(result, "evidence", {}) if isinstance(getattr(result, "evidence", {}), dict) else {}
    error = str(getattr(result, "error", "") or evidence.get("error") or "")
    return PolicyGateResult(
        decision="allow" if ok else "block",
        mutation_allowed=ok,
        reasons=[] if ok else [error or "provider output failed governance"],
        receipts={
            "output_governor": {
                "final_status": evidence.get("final_status") or "",
                "contract": evidence.get("contract") or "",
                "schema_valid": bool(evidence.get("schema_valid")),
                "path_valid": bool(evidence.get("path_valid")),
                "operation_valid": bool(evidence.get("operation_valid")),
                "compiled_operation_count": int(evidence.get("compiled_operation_count") or 0),
            }
        },
        verification_required=True,
        approval_required=not ok,
        rollback_required=True,
    ).to_dict()


def from_agent_passport_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    allowed = bool(decision.get("allowed"))
    return PolicyGateResult(
        decision="allow" if allowed else "block",
        mutation_allowed=allowed,
        reasons=[str(decision.get("reason") or "")],
        receipts={
            "agent_passport": {
                "decision_id": decision.get("decision_id") or "",
                "caller": decision.get("caller") or "",
                "target": decision.get("target") or "",
                "action": decision.get("action") or "",
                "reason": decision.get("reason") or "",
                "matched_policy_ids": decision.get("matched_policy_ids") or [],
                "policy_set_hash": decision.get("policy_set_hash") or "",
            }
        },
        verification_required=False,
        approval_required=not allowed,
        rollback_required=False,
    ).to_dict()


def combine_policy_gates(
    *,
    mode: Optional[Dict[str, Any]] = None,
    spec: Optional[Dict[str, Any]] = None,
    safety: Optional[Dict[str, Any]] = None,
    sourceplan_decision: str = "",
    worktree_recommended: bool = False,
    reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    gates: List[Dict[str, Any]] = []
    if spec:
        gates.append(from_spec_covenant(spec))
    if safety:
        gates.append(from_safety_receipt(safety))
    if sourceplan_decision:
        gates.append(PolicyGateResult(
            decision=sourceplan_decision,
            mutation_allowed=_normalize_decision(sourceplan_decision) == "allow",
            reasons=list(reasons or []),
            receipts={"sourceplan": {"decision": sourceplan_decision}},
            verification_required=True,
            approval_required=True,
            rollback_required=True,
            worktree_required=worktree_recommended,
        ).to_dict())
    if mode:
        mode_receipt = mode.get("receipt") if isinstance(mode.get("receipt"), dict) else {}
        gates.append(PolicyGateResult(
            decision="allow",
            mutation_allowed=str(((mode.get("definition") or {}) if isinstance(mode.get("definition"), dict) else {}).get("mutation_permission") or "") == "sourceplan_only",
            reasons=[str(mode.get("why") or "")],
            receipts={"mode_route": mode_receipt},
            verification_required=True,
            approval_required=False,
            rollback_required=True,
        ).to_dict())

    decision = strongest_decision(gate.get("decision") for gate in gates)
    return PolicyGateResult(
        decision=decision,
        mutation_allowed=all(bool(gate.get("mutation_allowed")) for gate in gates) and decision in {"allow", "warn"},
        reasons=[reason for gate in gates for reason in gate.get("reasons", [])],
        receipts={key: value for gate in gates for key, value in (gate.get("receipts") or {}).items()},
        verification_required=any(bool(gate.get("verification_required")) for gate in gates) if gates else True,
        approval_required=any(bool(gate.get("approval_required")) for gate in gates),
        rollback_required=any(bool(gate.get("rollback_required")) for gate in gates) if gates else True,
        worktree_required=bool(worktree_recommended or any(bool(gate.get("worktree_required")) for gate in gates)),
    ).to_dict()
