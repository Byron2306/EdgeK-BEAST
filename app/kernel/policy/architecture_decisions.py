"""Implemented architecture decision contract for BEAST governance.

The upgrade plan ADRs are not only documentation. This module exposes their
accepted status and creates compact receipts that can be attached to provider
handoffs, SourcePlan scorecards, safety receipts, and evidence packets.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List


ADR_ORDER = [f"ADR-{index:03d}" for index in range(1, 9)]


ADR_RECORDS: Dict[str, Dict[str, Any]] = {
    "ADR-001": {
        "title": "BEAST remains governance-first",
        "status": "accepted_implemented",
        "invariant": "sourceplan_is_authoritative_mutation_path",
    },
    "ADR-002": {
        "title": "Workspace graph is advisory, receipts are authoritative",
        "status": "accepted_implemented",
        "invariant": "append_only_receipts_and_rollback_are_authoritative",
    },
    "ADR-003": {
        "title": "Optional Code Cortex adapters, no hard dependency",
        "status": "accepted_implemented",
        "invariant": "code_cortex_adapters_are_optional_read_accelerators",
    },
    "ADR-004": {
        "title": "Action IR becomes the primary provider edit contract",
        "status": "accepted_implemented",
        "invariant": "providers_return_action_ir_compiled_to_sourceplan_operations",
    },
    "ADR-005": {
        "title": "Agent modes are permission boundaries",
        "status": "accepted_implemented",
        "invariant": "mode_router_controls_tool_and_mutation_permissions",
    },
    "ADR-006": {
        "title": "Risky edits default to worktree isolation",
        "status": "accepted_implemented",
        "invariant": "risky_sourceplans_require_worktree_or_explicit_override",
    },
    "ADR-007": {
        "title": "Project instructions are compiled, not pasted",
        "status": "accepted_implemented",
        "invariant": "spec_covenant_digest_replaces_unscoped_instruction_paste",
    },
    "ADR-008": {
        "title": "No implicit trust in setup/bootstrap commands",
        "status": "accepted_implemented",
        "invariant": "setup_and_bootstrap_commands_pass_safety_governor",
    },
}


def architecture_decision_register() -> Dict[str, Any]:
    return {
        "beast_object_type": "beast_architecture_decision_register",
        "version": "1.0",
        "status": "accepted_implemented",
        "decision_count": len(ADR_ORDER),
        "decisions": [{**ADR_RECORDS[adr_id], "adr_id": adr_id} for adr_id in ADR_ORDER],
        "enforcement_summary": {
            "mutation_path": "SourcePlan -> approval -> verification -> rollback -> evidence",
            "context_path": "Code Cortex front door with graph adapters",
            "provider_contract": "Action IR primary, local SourcePlan compiler authoritative",
            "receipt_authority": "Evidence Bus, Chronicle, Memory Hull, rollback snapshots",
            "command_trust": "Safety Governor before setup/bootstrap execution",
        },
    }


def architecture_contract_receipt(
    *,
    surface: str,
    sourceplan: Dict[str, Any] | None = None,
    scorecard: Dict[str, Any] | None = None,
    provider_handoff: Dict[str, Any] | None = None,
    safety_receipt: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    sourceplan = sourceplan or {}
    scorecard = scorecard or {}
    provider_handoff = provider_handoff or {}
    safety_receipt = safety_receipt or {}
    policy = scorecard.get("policy_gate_result") if isinstance(scorecard.get("policy_gate_result"), dict) else {}
    worktree = scorecard.get("worktree_recommendation") if isinstance(scorecard.get("worktree_recommendation"), dict) else {}
    spec = scorecard.get("spec_covenant") if isinstance(scorecard.get("spec_covenant"), dict) else {}
    graph = scorecard.get("graph_impact") if isinstance(scorecard.get("graph_impact"), dict) else {}
    handoff_output = provider_handoff.get("output") if isinstance(provider_handoff.get("output"), dict) else {}
    output_profile = handoff_output.get("profile") if isinstance(handoff_output.get("profile"), dict) else {}
    command_decision = str(safety_receipt.get("decision") or "")
    safety_findings: List[Any] = []
    if isinstance(safety_receipt.get("reasons"), list):
        safety_findings = safety_receipt.get("reasons") or []
    elif isinstance(safety_receipt.get("findings"), list):
        safety_findings = safety_receipt.get("findings") or []

    return {
        "beast_object_type": "beast_architecture_contract_receipt",
        "version": "1.0",
        "surface": surface,
        "created_at": int(time.time()),
        "adr_status": {adr_id: ADR_RECORDS[adr_id]["status"] for adr_id in ADR_ORDER},
        "invariants": {
            "governance_first": {
                "adr": "ADR-001",
                "enforced": True,
                "authoritative_mutation_path": "sourceplan",
                "plan_id": sourceplan.get("plan_id") or scorecard.get("plan_id") or "",
            },
            "receipt_authority": {
                "adr": "ADR-002",
                "enforced": True,
                "workspace_graph_role": "advisory",
                "rollback_required": bool(policy.get("rollback_required", True)),
                "evidence_required": True,
            },
            "optional_code_cortex": {
                "adr": "ADR-003",
                "enforced": True,
                "hard_dependency": False,
                "adapter_role": "read_context_accelerator",
                "code_cortex_present": bool(graph.get("code_cortex") or scorecard.get("code_cortex")),
            },
            "action_ir_primary": {
                "adr": "ADR-004",
                "enforced": True,
                "provider_contract": output_profile.get("role") or "action_ir_to_sourceplan",
                "compiled_operations": int(scorecard.get("selected_count") or len(sourceplan.get("operations") or [])),
            },
            "mode_permissions": {
                "adr": "ADR-005",
                "enforced": True,
                "selected_mode": ((scorecard.get("mode_route") or {}) if isinstance(scorecard.get("mode_route"), dict) else {}).get("selected_mode") or "",
                "mutation_permission": ((((scorecard.get("mode_route") or {}) if isinstance(scorecard.get("mode_route"), dict) else {}).get("definition") or {}) if isinstance(((scorecard.get("mode_route") or {}) if isinstance(scorecard.get("mode_route"), dict) else {}).get("definition"), dict) else {}).get("mutation_permission") or "",
            },
            "worktree_isolation": {
                "adr": "ADR-006",
                "enforced": True,
                "recommended": bool(worktree.get("recommended") or policy.get("worktree_required")),
                "required": bool(policy.get("worktree_required")),
                "override_required_for_main_workspace": bool(policy.get("worktree_required")),
            },
            "compiled_project_instructions": {
                "adr": "ADR-007",
                "enforced": True,
                "spec_covenant_hash": spec.get("covenant_hash") or "",
                "raw_instruction_paste_allowed": False,
            },
            "bootstrap_safety": {
                "adr": "ADR-008",
                "enforced": True,
                "safety_decision": command_decision,
                "finding_count": len(safety_findings),
                "implicit_trust": False,
            },
        },
    }
