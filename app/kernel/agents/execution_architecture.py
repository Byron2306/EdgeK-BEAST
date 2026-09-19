"""Phase 8 governed execution contract for the coding agent.

This contract makes the mutation spine explicit. Planner/model output is intent,
not authority. Only the live worktree tool context may mutate, and every
mutation invalidates prior verification.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


MUTATION_TOOLS = {"worktree.write_file", "worktree.replace_exact"}
VERIFY_TOOL = "worktree.verify"


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def execution_authority_contract() -> dict[str, Any]:
    contract = {
        "beast_object_type": "beast_agent_execution_authority_contract",
        "version": "1.0",
        "spine": [
            "planner_intent",
            "tool_schema_validation",
            "approval_if_required",
            "isolated_worktree",
            "bounded_mutation",
            "verification",
            "evidence_receipt",
            "governed_promotion",
        ],
        "authorities": {
            "planner_output": "intent_only",
            "provider_output": "intent_only",
            "crystal_reuse": "advisory_or_compute_reuse_only",
            "exact_source": "workspace.read_range",
            "mutation": "worktree_tools",
            "verification": "worktree.verify",
            "promotion": "explicit_governed_gate",
        },
        "invariants": [
            "no mutation outside an isolated bound worktree",
            "no mutation authority inherited from model memory or crystal replay",
            "every mutation advances the mutation epoch and stales prior verification",
            "promotion requires verification for the current mutation epoch",
            "execution evidence records what happened but cannot authorize a future mutation",
        ],
    }
    contract["contract_digest"] = _digest(contract)
    return contract


def execution_gate(decision: Any, context: Any) -> dict[str, Any]:
    tool_id = str(getattr(decision, "tool_id", "") or "")
    approval_id = str(getattr(decision, "approval_id", "") or "")
    worktree_root = str(getattr(context, "worktree_root", "") or "")
    result = {
        "beast_object_type": "beast_agent_execution_gate",
        "version": "1.0",
        "tool_id": tool_id,
        "allowed": True,
        "reason": "non_mutating_tool",
        "requires_worktree": tool_id in MUTATION_TOOLS or tool_id == VERIFY_TOOL,
        "worktree_bound": bool(worktree_root),
        "approval_present": bool(approval_id),
        "authority_source": "live_tool_context",
        "inherited_authority_accepted": False,
    }
    if result["requires_worktree"] and not worktree_root:
        result["allowed"] = False
        result["reason"] = "isolated_worktree_required"
    elif tool_id in MUTATION_TOOLS:
        result["reason"] = "bounded_worktree_mutation"
    elif tool_id == VERIFY_TOOL:
        result["reason"] = "fresh_worktree_verification"
    result["gate_digest"] = _digest(result)
    return result


def current_epoch_receipt(checkpoint: dict[str, Any]) -> dict[str, Any]:
    verification = checkpoint.get("verification") if isinstance(checkpoint.get("verification"), dict) else {}
    mutation_epoch = max(0, int(checkpoint.get("worktree_mutation_epoch") or 0))
    verification_epoch = int(verification.get("mutation_epoch") if verification.get("mutation_epoch") is not None else -1)
    current = bool(verification.get("ok")) and not bool(verification.get("stale")) and verification_epoch == mutation_epoch
    receipt = {
        "beast_object_type": "beast_agent_current_epoch_receipt",
        "version": "1.0",
        "current": current,
        "mutation_epoch": mutation_epoch,
        "verification_epoch": verification_epoch,
        "verification_ok": bool(verification.get("ok")),
        "verification_stale": bool(verification.get("stale")),
        "execution_target": str(verification.get("execution_target") or ""),
        "authority": "evidence_only_no_future_mutation_authority",
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt
