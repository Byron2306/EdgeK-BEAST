"""Recovery Phase 6 canonical memory architecture for the coding agent.

Memory can inform planning and continuity, but it never becomes exact-source,
mutation, verification, or promotion authority merely because it persisted.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


MEMORY_ROLES = {
    "working": {
        "owner": "agent_run_state",
        "purpose": "bounded current-run continuity: active plan, recent observations, repair state",
        "persistence": "run checkpoint",
        "authority": "advisory_continuity_only",
    },
    "episodic": {
        "owner": "memory_hull_chronicle",
        "purpose": "prior task decisions, outcomes, route cards and operator-visible residue",
        "persistence": "Memory Hull / Chronicle",
        "authority": "advisory_prior_experience_only",
    },
    "durable": {
        "owner": "workspace_graph_skill_tree",
        "purpose": "rebuildable project knowledge and explicitly promoted reusable patterns",
        "persistence": "Workspace Graph / Skill Tree",
        "authority": "advisory_retrieval_only",
    },
    "evidence": {
        "owner": "evidence_bus",
        "purpose": "pointers, receipts and summaries that lead back to authoritative evidence",
        "persistence": "Evidence Bus and evidence stores",
        "authority": "reference_only_resolve_source_before_use",
    },
    "forensic": {
        "owner": "forensic_archive",
        "purpose": "append-only audit history of attempts, failures, checks and interception events",
        "persistence": "L4 forensic archive",
        "authority": "audit_only",
    },
}

PROHIBITED_PROMOTIONS = {
    "exact_source": "workspace.read_range",
    "mutation": "worktree_tools",
    "verification": "verifier_receipt",
    "promotion": "human_or_governed_promotion_gate",
}


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def memory_authority_contract() -> dict[str, Any]:
    body = {
        "beast_object_type": "beast_agent_memory_authority_contract",
        "version": "1.0",
        "roles": MEMORY_ROLES,
        "prohibited_implicit_promotions": PROHIBITED_PROMOTIONS,
        "rules": [
            "Memory is retrieved as advisory context unless an external authority contract says otherwise.",
            "Memory text never becomes editable source bytes.",
            "Evidence memory stores references; authoritative claims must resolve to their source receipt.",
            "Forensic memory is append-only audit context and cannot authorize retry, mutation or promotion.",
            "Durable reuse requires an explicit promotion path; recurrence alone is insufficient.",
        ],
    }
    body["contract_digest"] = _digest(body)
    return body


def build_memory_context(
    run: dict[str, Any],
    state: Any,
    *,
    episodic: list[dict[str, Any]] | None = None,
    durable: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    forensic: list[dict[str, Any]] | None = None,
    per_role_limit: int = 6,
) -> dict[str, Any]:
    observations = getattr(state, "observations", []) if state is not None else []
    working = []
    for item in list(observations or [])[-per_role_limit:]:
        if not isinstance(item, dict):
            continue
        working.append({
            "tool_id": str(item.get("tool_id") or ""),
            "status": str(item.get("status") or ""),
            "evidence_digest": str(item.get("evidence_digest") or ""),
        })

    def bounded(items: list[dict[str, Any]] | None, role: str) -> list[dict[str, Any]]:
        output = []
        for item in list(items or [])[:per_role_limit]:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["memory_role"] = role
            row["authority"] = MEMORY_ROLES[role]["authority"]
            row["grants_mutation_authority"] = False
            row["grants_exact_source_authority"] = False
            output.append(row)
        return output

    body = {
        "beast_object_type": "beast_agent_memory_context",
        "version": "1.0",
        "run_id": str(run.get("run_id") or getattr(state, "run_id", "") or ""),
        "working": {
            "memory_role": "working",
            "authority": MEMORY_ROLES["working"]["authority"],
            "items": working,
        },
        "episodic": bounded(episodic, "episodic"),
        "durable": bounded(durable, "durable"),
        "evidence": bounded(evidence, "evidence"),
        "forensic": bounded(forensic, "forensic"),
        "promotion_boundary": PROHIBITED_PROMOTIONS,
        "memory_contract_digest": memory_authority_contract()["contract_digest"],
    }
    body["context_digest"] = _digest(body)
    return body
