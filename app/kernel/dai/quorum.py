"""Role-diverse quorum and authenticated veto for DAI Phase 1."""
from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import hashlib
import hmac
from typing import Mapping, Sequence

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.commons_admission import CommonsAdmissionReceipt
from app.kernel.dai.contracts import AuthorityScope, QuorumVote, VoteDecision


@dataclass(frozen=True, slots=True)
class DAIVetoReceipt:
    veto_id: str
    voter_id: str
    witness_role: str
    proposal_digest: str
    world_state_digest: str
    epoch_id: str
    reason: str
    signature: str = ""
    maximum_authority: AuthorityScope = AuthorityScope.QUORUM_APPROVAL

    @property
    def signing_payload(self) -> Mapping[str, object]:
        return {
            "veto_id": self.veto_id,
            "voter_id": self.voter_id,
            "witness_role": self.witness_role,
            "proposal_digest": self.proposal_digest,
            "world_state_digest": self.world_state_digest,
            "epoch_id": self.epoch_id,
            "reason": self.reason,
        }

    @property
    def veto_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class QuorumDecisionReceipt:
    proposal_digest: str
    world_state_digest: str
    epoch_id: str
    decision: VoteDecision
    admitted_node_count: int
    witness_roles: tuple[str, ...]
    vote_digests: tuple[str, ...]
    veto_digests: tuple[str, ...]
    red_gates: tuple[str, ...]
    execution_authority_allowed: bool = False
    object_type: str = "dai_role_diverse_quorum_decision_receipt"
    schema_version: str = "2026-08-04.phase1"

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def sign_vote(vote: QuorumVote, *, secret: bytes) -> QuorumVote:
    payload = _vote_signing_payload(vote)
    signature = hmac.new(secret, canonical_json(payload).encode("utf-8"), hashlib.sha256).digest()
    return replace(vote, signature=base64.b64encode(signature).decode("ascii"))


def verify_vote(vote: QuorumVote, *, secrets: Mapping[str, bytes]) -> bool:
    secret = secrets.get(vote.voter_id)
    if not secret:
        return False
    expected = hmac.new(secret, canonical_json(_vote_signing_payload(vote)).encode("utf-8"), hashlib.sha256).digest()
    try:
        return hmac.compare_digest(base64.b64decode(vote.signature, validate=True), expected)
    except Exception:
        return False


def sign_veto(veto: DAIVetoReceipt, *, secret: bytes) -> DAIVetoReceipt:
    signature = hmac.new(secret, canonical_json(veto.signing_payload).encode("utf-8"), hashlib.sha256).digest()
    return replace(veto, signature=base64.b64encode(signature).decode("ascii"))


def verify_veto(veto: DAIVetoReceipt, *, secrets: Mapping[str, bytes]) -> bool:
    secret = secrets.get(veto.voter_id)
    if not secret:
        return False
    expected = hmac.new(secret, canonical_json(veto.signing_payload).encode("utf-8"), hashlib.sha256).digest()
    try:
        return hmac.compare_digest(base64.b64decode(veto.signature, validate=True), expected)
    except Exception:
        return False


def decide_quorum(
    *,
    admission: CommonsAdmissionReceipt,
    votes: Sequence[QuorumVote],
    vetoes: Sequence[DAIVetoReceipt],
    proposal_digest: str,
    world_state_digest: str,
    epoch_id: str,
    secrets: Mapping[str, bytes],
) -> QuorumDecisionReceipt:
    admitted = {node.node_id: node for node in admission.admitted_nodes if node.admitted}
    roles = {node.witness_role for node in admitted.values()}
    gates = {
        "commons_admission_valid": admission.admitted,
        "minimum_three_admitted_nodes": len(admitted) >= 3,
        "role_diverse_witnesses": {"semantic", "physical", "adversarial"}.issubset(roles),
        "votes_from_admitted_nodes": all(vote.voter_id in admitted for vote in votes),
        "vote_roles_match_admission": all(admitted.get(vote.voter_id, None) and admitted[vote.voter_id].witness_role == vote.witness_role for vote in votes),
        "vote_signatures_valid": all(verify_vote(vote, secrets=secrets) for vote in votes),
        "votes_bind_proposal": all(vote.proposal_digest == proposal_digest for vote in votes),
        "votes_bind_world_state": all(vote.world_state_digest == world_state_digest for vote in votes),
        "votes_bind_epoch": all(vote.epoch_id == epoch_id for vote in votes),
        "no_execution_authority": True,
    }
    valid_vetoes = tuple(
        veto for veto in vetoes
        if veto.voter_id in admitted
        and admitted[veto.voter_id].witness_role == veto.witness_role
        and veto.proposal_digest == proposal_digest
        and veto.world_state_digest == world_state_digest
        and veto.epoch_id == epoch_id
        and verify_veto(veto, secrets=secrets)
    )
    approvals = tuple(vote for vote in votes if vote.decision is VoteDecision.APPROVED)
    gates["approval_count"] = len(approvals) >= 3
    gates["approval_roles_diverse"] = {"semantic", "physical", "adversarial"}.issubset({vote.witness_role for vote in approvals})
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    if valid_vetoes:
        decision = VoteDecision.VETOED
    elif red_gates:
        decision = VoteDecision.QUORUM_UNAVAILABLE
    else:
        decision = VoteDecision.APPROVED
    return QuorumDecisionReceipt(
        proposal_digest=proposal_digest,
        world_state_digest=world_state_digest,
        epoch_id=epoch_id,
        decision=decision,
        admitted_node_count=len(admitted),
        witness_roles=tuple(sorted(roles)),
        vote_digests=tuple(vote.vote_digest for vote in votes),
        veto_digests=tuple(veto.veto_digest for veto in valid_vetoes),
        red_gates=red_gates,
        execution_authority_allowed=False,
    )


def _vote_signing_payload(vote: QuorumVote) -> Mapping[str, object]:
    return {
        "vote_id": vote.vote_id,
        "voter_id": vote.voter_id,
        "witness_role": vote.witness_role,
        "decision": vote.decision.value if isinstance(vote.decision, VoteDecision) else str(vote.decision),
        "proposal_digest": vote.proposal_digest,
        "world_state_digest": vote.world_state_digest,
        "epoch_id": vote.epoch_id,
        "maximum_authority": vote.maximum_authority.value if isinstance(vote.maximum_authority, AuthorityScope) else str(vote.maximum_authority),
    }

