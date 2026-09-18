"""Phase 3 least-authority policy for model-directed AgentRun tools.

This module converts the typed ToolSpec contract into a deterministic authority
decision before any tool handler executes. It does not grant promotion
authority and it does not replace request-bound approvals or Worktree Forge.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.kernel.agents.tool_models import ToolEffect, ToolSpec


A_READ_AUTOMATIC = "A_READ_AUTOMATIC"
B_READ_SENSITIVE = "B_READ_SENSITIVE"
C_ISOLATED_MUTATION = "C_ISOLATED_MUTATION"
D_CONSEQUENTIAL_EXECUTION = "D_CONSEQUENTIAL_EXECUTION"
E_NEVER_MODEL_AUTHORIZED = "E_NEVER_MODEL_AUTHORIZED"

AUTHORITY_CLASSES = {
    A_READ_AUTOMATIC,
    B_READ_SENSITIVE,
    C_ISOLATED_MUTATION,
    D_CONSEQUENTIAL_EXECUTION,
    E_NEVER_MODEL_AUTHORIZED,
}


def authority_class_for(spec: ToolSpec) -> str:
    explicit = str(getattr(spec, "authority_class", "") or "").strip().upper()
    if explicit:
        if explicit not in AUTHORITY_CLASSES:
            return E_NEVER_MODEL_AUTHORIZED
        return explicit
    if spec.effect is ToolEffect.READ:
        return B_READ_SENSITIVE if spec.requires_approval else A_READ_AUTOMATIC
    if spec.effect is ToolEffect.ISOLATED_MUTATION:
        return C_ISOLATED_MUTATION
    if spec.effect is ToolEffect.EXECUTION:
        return D_CONSEQUENTIAL_EXECUTION
    return E_NEVER_MODEL_AUTHORIZED


def authorize_agent_tool(
    spec: ToolSpec,
    *,
    run_id: str,
    execution_target: str,
    approval_status: str = "",
    approval_id: str = "",
    worktree_bound: bool = False,
    policy_auto_authorized: bool = False,
) -> dict[str, Any]:
    """Return a fail-closed authority receipt for one requested tool call."""

    authority_class = authority_class_for(spec)
    approved = str(approval_status or "").strip().lower() == "approved"
    governed_authority = approved or bool(policy_auto_authorized)
    target = str(execution_target or "local").strip() or "local"

    allowed = True
    reason = "least-authority policy satisfied"

    if target not in spec.targets:
        allowed = False
        reason = f"execution target {target!r} is outside the tool contract"
    elif authority_class == E_NEVER_MODEL_AUTHORIZED:
        allowed = False
        reason = "tool class E is never model-authorized"
    elif authority_class in {B_READ_SENSITIVE, C_ISOLATED_MUTATION} and not governed_authority:
        allowed = False
        reason = "request-bound approval is required for this authority class"
    elif authority_class == D_CONSEQUENTIAL_EXECUTION and spec.requires_approval and not governed_authority:
        allowed = False
        reason = "consequential execution requires approval under this tool policy"
    elif spec.requires_worktree and not worktree_bound:
        allowed = False
        reason = "tool requires a bound isolated worktree"

    body = {
        "run_id": str(run_id or ""),
        "tool_id": spec.tool_id,
        "tool_version": spec.version,
        "authority_class": authority_class,
        "risk": spec.risk.value,
        "effect": spec.effect.value,
        "execution_target": target,
        "requires_approval": bool(spec.requires_approval),
        "approval_id": str(approval_id or ""),
        "approval_status": str(approval_status or ""),
        "policy_auto_authorized": bool(policy_auto_authorized),
        "requires_worktree": bool(spec.requires_worktree),
        "worktree_bound": bool(worktree_bound),
        "redaction_policy": str(getattr(spec, "redaction_policy", "source") or "source"),
        "evidence_level": str(getattr(spec, "evidence_level", "summary") or "summary"),
        "allowed": bool(allowed),
        "reason": reason,
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "beast_object_type": "agent_tool_authority_receipt",
        "version": "1.0",
        "receipt_id": f"auth_{digest[:20]}",
        "receipt_hash": f"sha256:{digest}",
        "issued_at": time.time(),
        **body,
    }
