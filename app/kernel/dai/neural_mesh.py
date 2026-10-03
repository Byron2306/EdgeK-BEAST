"""DAI Neural Mesh activation across admitted Commons witnesses.

This is the first governed mesh slice.  It does not create a distributed brain
by assertion; it creates a digest-bound activation fabric over admitted Commons
nodes.  Each node receives the same capability/world/quorum boundary and may
only participate in deterministic replay/observation for this phase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.kernel.compute.deterministic_intelligence import require_digest, sha256_digest
from app.kernel.dai.capability_promotion import DAICapability, DAICapabilityPromotionReceipt
from app.kernel.dai.commons_admission import CommonsAdmissionReceipt, CommonsNodeAdmission
from app.kernel.dai.contracts import AuthorityScope, VoteDecision
from app.kernel.dai.quorum import QuorumDecisionReceipt


@dataclass(frozen=True, slots=True)
class MeshNodeActivation:
    node_id: str
    witness_role: str
    admitted_node_digest: str
    capability_digest: str
    world_state_digest: str
    promotion_receipt_digest: str
    quorum_decision_receipt_digest: str
    channel_digest: str
    activation_mode: str = "governed_replay_only"
    activated: bool = True
    maximum_authority: AuthorityScope = AuthorityScope.NEURAL_MESH_ACTIVATION_ONLY

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.witness_role.strip():
            raise ValueError("mesh activation requires node_id and witness_role")
        for field_name in (
            "admitted_node_digest",
            "capability_digest",
            "world_state_digest",
            "promotion_receipt_digest",
            "quorum_decision_receipt_digest",
            "channel_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if self.activation_mode != "governed_replay_only":
            raise ValueError("Phase-1 neural mesh activation is governed_replay_only")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def activation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DAINeuralMeshActivationReceipt:
    capability_digest: str
    world_state_digest: str
    promotion_receipt_digest: str
    commons_admission_receipt_digest: str
    quorum_decision_receipt_digest: str
    active_nodes: tuple[MeshNodeActivation, ...]
    topology_digest: str
    activated: bool
    gates: Mapping[str, bool]
    red_gates: tuple[str, ...]
    provider_calls_used: int = 0
    execution_authority_allowed: bool = False
    object_type: str = "dai_neural_mesh_activation_receipt"
    schema_version: str = "2026-08-04.phase1"
    maximum_authority: AuthorityScope = AuthorityScope.NEURAL_MESH_ACTIVATION_ONLY

    def __post_init__(self) -> None:
        for field_name in (
            "capability_digest",
            "world_state_digest",
            "promotion_receipt_digest",
            "commons_admission_receipt_digest",
            "quorum_decision_receipt_digest",
            "topology_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)

    @property
    def witness_roles(self) -> tuple[str, ...]:
        return tuple(sorted({node.witness_role for node in self.active_nodes if node.activated}))


def activate_neural_mesh(
    *,
    capability: DAICapability,
    promotion_receipt: DAICapabilityPromotionReceipt,
    admission_receipt: CommonsAdmissionReceipt,
    quorum_receipt: QuorumDecisionReceipt,
) -> DAINeuralMeshActivationReceipt:
    admitted_nodes = tuple(node for node in admission_receipt.admitted_nodes if node.admitted)
    active_nodes = tuple(
        _activate_node(
            node=node,
            capability=capability,
            promotion_receipt=promotion_receipt,
            quorum_receipt=quorum_receipt,
        )
        for node in admitted_nodes
    )
    roles = {node.witness_role for node in active_nodes if node.activated}
    topology_digest = sha256_digest(
        {
            "capability_digest": capability.capability_digest,
            "world_state_digest": capability.world_state_digest,
            "nodes": tuple(sorted(node.activation_digest for node in active_nodes)),
        }
    )
    gates = {
        "capability_promoted": promotion_receipt.promoted and promotion_receipt.capability_digest == capability.capability_digest,
        "capability_is_test_only": capability.execution_authority_allowed is False,
        "promotion_binds_world": promotion_receipt.world_state_digest == capability.world_state_digest,
        "commons_admission_green": admission_receipt.admitted and not admission_receipt.red_gates,
        "quorum_approved": quorum_receipt.decision is VoteDecision.APPROVED and not quorum_receipt.red_gates,
        "quorum_binds_capability_candidate": quorum_receipt.proposal_digest == capability.candidate_digest,
        "quorum_binds_world": quorum_receipt.world_state_digest == capability.world_state_digest,
        "minimum_three_active_nodes": len(active_nodes) >= 3,
        "role_diverse_active_nodes": {"semantic", "physical", "adversarial"}.issubset(roles),
        "node_channels_bound": all(node.channel_digest.startswith("sha256:") for node in active_nodes),
        "governed_replay_only": all(node.activation_mode == "governed_replay_only" for node in active_nodes),
        "zero_provider_activation": True,
        "no_execution_authority": not capability.execution_authority_allowed,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    return DAINeuralMeshActivationReceipt(
        capability_digest=capability.capability_digest,
        world_state_digest=capability.world_state_digest,
        promotion_receipt_digest=promotion_receipt.receipt_digest,
        commons_admission_receipt_digest=admission_receipt.receipt_digest,
        quorum_decision_receipt_digest=quorum_receipt.receipt_digest,
        active_nodes=active_nodes,
        topology_digest=topology_digest,
        activated=not red_gates,
        gates=gates,
        red_gates=red_gates,
    )


def _activate_node(
    *,
    node: CommonsNodeAdmission,
    capability: DAICapability,
    promotion_receipt: DAICapabilityPromotionReceipt,
    quorum_receipt: QuorumDecisionReceipt,
) -> MeshNodeActivation:
    channel_digest = sha256_digest(
        {
            "node_id": node.node_id,
            "witness_role": node.witness_role,
            "admitted_node_digest": node.admission_digest,
            "capability_digest": capability.capability_digest,
            "world_state_digest": capability.world_state_digest,
            "promotion_receipt_digest": promotion_receipt.receipt_digest,
            "quorum_decision_receipt_digest": quorum_receipt.receipt_digest,
            "mode": "governed_replay_only",
        }
    )
    return MeshNodeActivation(
        node_id=node.node_id,
        witness_role=node.witness_role,
        admitted_node_digest=node.admission_digest,
        capability_digest=capability.capability_digest,
        world_state_digest=capability.world_state_digest,
        promotion_receipt_digest=promotion_receipt.receipt_digest,
        quorum_decision_receipt_digest=quorum_receipt.receipt_digest,
        channel_digest=channel_digest,
    )
