"""Deterministic Hermes lifecycle for governed swarm work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class HermesState(str, Enum):
    CREATED = "CREATED"
    MAPPING_REQUIRED = "MAPPING_REQUIRED"
    WORKTREE_REQUIRED = "WORKTREE_REQUIRED"
    BASELINE_REQUIRED = "BASELINE_REQUIRED"
    FAILURE_ANALYSIS_REQUIRED = "FAILURE_ANALYSIS_REQUIRED"
    CRYSTAL_LOOKUP_REQUIRED = "CRYSTAL_LOOKUP_REQUIRED"
    PATCH_TEMPLATE_REQUIRED = "PATCH_TEMPLATE_REQUIRED"
    MODEL_RESIDUAL_REQUIRED = "MODEL_RESIDUAL_REQUIRED"
    MUTATION_REQUIRED = "MUTATION_REQUIRED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    CRITIC_REQUIRED = "CRITIC_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class HermesDecision:
    state: HermesState
    next_role: str
    allowed_operation: str
    ollama_allowed: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "next_role": self.next_role,
            "allowed_operation": self.allowed_operation,
            "ollama_allowed": self.ollama_allowed,
            "reason": self.reason,
        }


class HermesLifecycle:
    """Choose the next legal role from evidence already present in a payload."""

    def decide(self, payload: Dict[str, Any]) -> HermesDecision:
        payload = payload or {}
        if payload.get("blocked") or payload.get("approval_required"):
            return HermesDecision(HermesState.BLOCKED, "sentinel", "resolve_gate", False, "policy or approval gate is unresolved")
        if not payload.get("workspace_mapped") and not (payload.get("files") or payload.get("context_files") or payload.get("workspace_nodes")):
            return HermesDecision(HermesState.MAPPING_REQUIRED, "cartographer", "repository_mapping", False, "repository context is required before downstream roles")
        if payload.get("requires_worktree") and not payload.get("worktree_task_id"):
            return HermesDecision(HermesState.WORKTREE_REQUIRED, "sentinel", "bind_isolated_worktree", False, "mutation work requires an isolated worktree")
        if payload.get("task_type") in {"test_repair", "code_change"} and not payload.get("baseline_verified") and not payload.get("failure"):
            return HermesDecision(HermesState.BASELINE_REQUIRED, "verifier", "baseline_verification", False, "baseline verification precedes mutation")
        if payload.get("failure") and not payload.get("failure_signature"):
            return HermesDecision(HermesState.FAILURE_ANALYSIS_REQUIRED, "failure_analyst", "normalize_failure", False, "a stable failure signature is required")
        if not payload.get("crystal_lookup_complete"):
            return HermesDecision(HermesState.CRYSTAL_LOOKUP_REQUIRED, "crystalist", "lookup_crystals", False, "crystal reuse is checked before model inference")
        if payload.get("needs_patch_template") and not payload.get("action_ir"):
            return HermesDecision(HermesState.PATCH_TEMPLATE_REQUIRED, "patch_compiler", "compile_action_ir", False, "BEAST must construct the bounded patch template")
        if payload.get("residual_fields") and not payload.get("residual_solved"):
            return HermesDecision(HermesState.MODEL_RESIDUAL_REQUIRED, "residual_solver", "solve_declared_residual", True, "only declared residual fields may reach Ollama")
        if payload.get("mutation_required") and not payload.get("mutation_receipt"):
            return HermesDecision(HermesState.MUTATION_REQUIRED, "forge_executor", "apply_one_approved_action", False, "mutation requires a governed Forge receipt")
        if payload.get("mutation_receipt") and not payload.get("verification_receipt"):
            return HermesDecision(HermesState.VERIFICATION_REQUIRED, "verifier", "fresh_verification", False, "verification must be fresh for the mutation epoch")
        if payload.get("verification_receipt") and not payload.get("critic_receipt"):
            return HermesDecision(HermesState.CRITIC_REQUIRED, "critic", "scope_and_provenance_review", False, "completed work requires targeted review")
        return HermesDecision(HermesState.COMPLETED, "archivist", "archive_verified_receipt", False, "all required evidence is present")
