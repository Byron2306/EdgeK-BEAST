"""Closed-loop DAI plasticity through promotion, never live mutation.

Phase 1 ends with a strict learning law:

    observed outcome evidence -> quarantined revision/reinforcement proposal
    -> future promotion gauntlet

The currently promoted capability is immutable inside this loop.  Plasticity may
record what happened and propose a next candidate; it may not patch the live
capability, alter the neural mesh channel or broaden execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.arda_execution import ArdaReverseEvidenceReceipt, ArdaSandboxExecutionReceipt
from app.kernel.dai.capability_promotion import DAICapability, DAICapabilityPromotionReceipt
from app.kernel.dai.contracts import AuthorityScope, PromotionState
from app.kernel.dai.neural_mesh import DAINeuralMeshActivationReceipt


@dataclass(frozen=True, slots=True)
class DAIOutcomeSignal:
    signal_id: str
    capability_digest: str
    world_state_digest: str
    execution_receipt_digest: str
    reverse_evidence_receipt_digest: str
    outcome: str
    verified: bool
    provider_calls_used: int = 0
    host_mutation_observed: bool = False

    def __post_init__(self) -> None:
        if not self.signal_id.strip() or not self.outcome.strip():
            raise ValueError("outcome signal requires signal_id and outcome")
        for field_name in (
            "capability_digest",
            "world_state_digest",
            "execution_receipt_digest",
            "reverse_evidence_receipt_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)

    @property
    def signal_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAICapabilityRevisionProposal:
    proposal_id: str
    parent_capability_digest: str
    parent_candidate_digest: str
    world_state_digest: str
    outcome_signal_digest: str
    proposed_changes: Mapping[str, object]
    source_receipts: tuple[str, ...]
    promotion_required: bool = True
    live_mutation_performed: bool = False
    promotion_state: PromotionState = PromotionState.QUARANTINED_CANDIDATE
    maximum_authority: AuthorityScope = AuthorityScope.PLASTICITY_PROPOSAL_ONLY

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("revision proposal requires proposal_id")
        for field_name in (
            "parent_capability_digest",
            "parent_candidate_digest",
            "world_state_digest",
            "outcome_signal_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        for digest in self.source_receipts:
            require_digest(digest, field_name="source_receipts")
        if self.live_mutation_performed:
            raise ValueError("DAI plasticity proposals cannot live-mutate capabilities")
        if not self.promotion_required:
            raise ValueError("DAI plasticity proposals must require promotion")
        if not isinstance(self.promotion_state, PromotionState):
            object.__setattr__(self, "promotion_state", PromotionState(self.promotion_state))
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def proposal_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAIPlasticityReceipt:
    capability_digest: str
    world_state_digest: str
    promotion_receipt_digest: str
    mesh_activation_receipt_digest: str
    execution_receipt_digest: str
    reverse_evidence_receipt_digest: str
    outcome_signal_digest: str
    revision_proposal_digest: str
    closed_loop_recorded: bool
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    provider_calls_used: int = 0
    promotion_required_for_change: bool = True
    live_mutation_performed: bool = False
    execution_authority_allowed: bool = False
    object_type: str = "dai_closed_loop_plasticity_receipt"
    schema_version: str = "2026-08-04.phase1"
    maximum_authority: AuthorityScope = AuthorityScope.PLASTICITY_PROPOSAL_ONLY

    def __post_init__(self) -> None:
        for field_name in (
            "capability_digest",
            "world_state_digest",
            "promotion_receipt_digest",
            "mesh_activation_receipt_digest",
            "execution_receipt_digest",
            "reverse_evidence_receipt_digest",
            "outcome_signal_digest",
            "revision_proposal_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.live_mutation_performed or self.execution_authority_allowed:
            raise ValueError("DAI plasticity cannot live-mutate or grant execution authority")
        if not self.promotion_required_for_change:
            raise ValueError("DAI plasticity changes must require future promotion")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def close_plasticity_loop(
    *,
    capability: DAICapability,
    promotion_receipt: DAICapabilityPromotionReceipt,
    mesh_receipt: DAINeuralMeshActivationReceipt,
    execution_receipt: ArdaSandboxExecutionReceipt,
    reverse_receipt: ArdaReverseEvidenceReceipt,
    live_mutation_requested: bool = False,
) -> tuple[DAIOutcomeSignal, DAICapabilityRevisionProposal, DAIPlasticityReceipt]:
    """Record outcome evidence and emit a future-promotion proposal."""

    outcome = "verified_replay_reinforcement" if reverse_receipt.verified else "reverse_evidence_repair_required"
    signal = DAIOutcomeSignal(
        signal_id=f"outcome:{capability.capability_id}",
        capability_digest=capability.capability_digest,
        world_state_digest=capability.world_state_digest,
        execution_receipt_digest=execution_receipt.receipt_digest,
        reverse_evidence_receipt_digest=reverse_receipt.receipt_digest,
        outcome=outcome,
        verified=reverse_receipt.verified,
        provider_calls_used=reverse_receipt.provider_calls_used,
        host_mutation_observed=reverse_receipt.host_mutation_observed,
    )
    proposal = DAICapabilityRevisionProposal(
        proposal_id=f"plasticity-proposal:{capability.capability_id}",
        parent_capability_digest=capability.capability_digest,
        parent_candidate_digest=capability.candidate_digest,
        world_state_digest=capability.world_state_digest,
        outcome_signal_digest=signal.signal_digest,
        proposed_changes={
            "proposal_kind": "reinforce" if reverse_receipt.verified else "repair",
            "carry_forward_predicate_law_count": len(capability.predicate_laws),
            "add_outcome_signal_receipt": signal.signal_digest,
            "next_required_step": "rerun_promotion_gauntlet_before_capability_change",
        },
        source_receipts=(
            promotion_receipt.receipt_digest,
            mesh_receipt.receipt_digest,
            execution_receipt.receipt_digest,
            reverse_receipt.receipt_digest,
        ),
    )
    gates = {
        "promotion_receipt_green": promotion_receipt.promoted and promotion_receipt.capability_digest == capability.capability_digest,
        "mesh_activation_green": mesh_receipt.activated and mesh_receipt.capability_digest == capability.capability_digest,
        "execution_receipt_green": execution_receipt.executed and not execution_receipt.red_gates,
        "reverse_evidence_verified": reverse_receipt.verified and not reverse_receipt.red_gates,
        "reverse_binds_execution": reverse_receipt.execution_receipt_digest == execution_receipt.receipt_digest,
        "reverse_binds_capability": reverse_receipt.capability_digest == capability.capability_digest,
        "reverse_binds_world": reverse_receipt.world_state_digest == capability.world_state_digest,
        "signal_binds_reverse_evidence": signal.reverse_evidence_receipt_digest == reverse_receipt.receipt_digest,
        "proposal_binds_parent_capability": proposal.parent_capability_digest == capability.capability_digest,
        "proposal_requires_future_promotion": proposal.promotion_required,
        "proposal_is_quarantined": proposal.promotion_state is PromotionState.QUARANTINED_CANDIDATE,
        "live_mutation_not_requested": not live_mutation_requested,
        "live_capability_digest_unchanged": capability.capability_digest == promotion_receipt.capability_digest,
        "provider_calls_zero": signal.provider_calls_used == 0,
        "no_execution_authority": not capability.execution_authority_allowed,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    receipt = DAIPlasticityReceipt(
        capability_digest=capability.capability_digest,
        world_state_digest=capability.world_state_digest,
        promotion_receipt_digest=promotion_receipt.receipt_digest,
        mesh_activation_receipt_digest=mesh_receipt.receipt_digest,
        execution_receipt_digest=execution_receipt.receipt_digest,
        reverse_evidence_receipt_digest=reverse_receipt.receipt_digest,
        outcome_signal_digest=signal.signal_digest,
        revision_proposal_digest=proposal.proposal_digest,
        closed_loop_recorded=not red_gates,
        gates=gates,
        red_gates=red_gates,
    )
    return signal, proposal, receipt
