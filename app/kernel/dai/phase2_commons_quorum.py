"""Phase-2 Commons ML-KEM admission and role-diverse quorum binding."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest
from app.kernel.dai.commons_admission import CommonsAdmissionReceipt, admit_commons_nodes
from app.kernel.dai.contracts import (
    ArdaAttestationSummary,
    AuthorityScope,
    QuorumVote,
    VoteDecision,
    WorldStateSnapshot,
)
from app.kernel.dai.quorum import QuorumDecisionReceipt, decide_quorum, sign_vote


PHASE2_COMMONS_QUORUM_VERSION = "2026-08-04.phase2.commons-quorum.v1"
PHASE2_COMMONS_ROLES = {
    "commons-node-a": "semantic",
    "commons-node-b": "physical",
    "commons-node-c": "adversarial",
}
PHASE2_COMMONS_SECRETS = {
    "commons-node-a": b"dai-phase2-commons-node-a",
    "commons-node-b": b"dai-phase2-commons-node-b",
    "commons-node-c": b"dai-phase2-commons-node-c",
}


@dataclass(frozen=True, slots=True)
class Phase2CommonsQuorumReport:
    beast_object_type: str
    version: str
    report_id: str
    phase2_world_state_digest: str
    proposal_digest: str
    commons_admission_digest: str
    quorum_decision_digest: str
    admitted: bool
    quorum_decision: str
    admitted_node_count: int
    witness_roles: tuple[str, ...]
    vote_digests: tuple[str, ...]
    quorum_evidence_class: str
    independent_attested_quorum: bool
    red_gates: tuple[str, ...]
    provider_calls_used: int
    execution_authority_allowed: bool
    production_authority_allowed: bool
    maximum_authority: AuthorityScope = AuthorityScope.QUORUM_APPROVAL

    def __post_init__(self) -> None:
        for field_name in (
            "phase2_world_state_digest",
            "proposal_digest",
            "commons_admission_digest",
            "quorum_decision_digest",
        ):
            require_digest(getattr(self, field_name), field_name=field_name)
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def passed(self) -> bool:
        return (
            self.admitted
            and self.quorum_decision == VoteDecision.APPROVED.value
            and not self.red_gates
            and self.provider_calls_used == 0
            and not self.execution_authority_allowed
            and not self.production_authority_allowed
            and self.quorum_evidence_class == "local_world_bound_quorum_simulation"
        )

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def bind_phase2_commons_quorum(
    *,
    ml_kem_receipt: Mapping[str, Any],
    phase2_world_state_digest: str,
    proposal_digest: str,
    evidence_digests: Mapping[str, str],
    role_by_node: Mapping[str, str] | None = None,
    secrets: Mapping[str, bytes] | None = None,
) -> tuple[CommonsAdmissionReceipt, QuorumDecisionReceipt, Phase2CommonsQuorumReport]:
    """Bind the exact live Phase-2 world digest into Commons admission/quorum."""
    require_digest(phase2_world_state_digest, field_name="phase2_world_state_digest")
    require_digest(proposal_digest, field_name="proposal_digest")
    for key, digest in evidence_digests.items():
        require_digest(digest, field_name=f"evidence_digests.{key}")

    roles = dict(role_by_node or PHASE2_COMMONS_ROLES)
    vote_secrets = dict(secrets or PHASE2_COMMONS_SECRETS)
    world = WorldStateSnapshot(
        snapshot_id="world:dai-phase2-stale-listener-live",
        epoch_id="epoch:2026-08-04-phase2-stale-listener",
        facts={
            "phase2_world_state_digest": phase2_world_state_digest,
            "proposal_digest": proposal_digest,
            "evidence_digests": dict(evidence_digests),
            "authority_boundary": "commons_quorum_approval_only_no_execution_authority",
        },
        policy_generation="dai-phase2-live-world-bound-commons-quorum",
    )
    arda = ArdaAttestationSummary(
        attestation_id="arda:phase2:stale-listener-local-witness",
        source_artifact_receipts=tuple(sorted(evidence_digests.values()))[:8],
        workload_digest=proposal_digest,
        bpf_or_kernel_witness_present=True,
        measured_identity_present=True,
    )
    admission = admit_commons_nodes(
        ml_kem_receipt=ml_kem_receipt,
        arda_attestation=arda,
        world_state=world,
        role_by_node=roles,
        bound_world_state_digest=phase2_world_state_digest,
    )
    votes = tuple(
        sign_vote(
            QuorumVote(
                vote_id=f"vote:phase2:{node_id}",
                voter_id=node_id,
                witness_role=role,
                decision=VoteDecision.APPROVED,
                proposal_digest=proposal_digest,
                world_state_digest=phase2_world_state_digest,
                epoch_id=world.epoch_id,
            ),
            secret=vote_secrets[node_id],
        )
        for node_id, role in roles.items()
        if node_id in vote_secrets
    )
    quorum = decide_quorum(
        admission=admission,
        votes=votes,
        vetoes=(),
        proposal_digest=proposal_digest,
        world_state_digest=phase2_world_state_digest,
        epoch_id=world.epoch_id,
        secrets=vote_secrets,
    )
    gates = {
        "commons_admitted": admission.admitted,
        "admission_binds_phase2_world": admission.world_state_digest == phase2_world_state_digest,
        "all_nodes_bind_phase2_world": all(node.world_state_digest == phase2_world_state_digest for node in admission.admitted_nodes),
        "quorum_approved": quorum.decision is VoteDecision.APPROVED,
        "vote_world_exact": all(vote.world_state_digest == phase2_world_state_digest for vote in votes),
        "role_diverse": {"semantic", "physical", "adversarial"}.issubset(set(quorum.witness_roles)),
        "provider_call_boundary": True,
        "execution_authority_boundary": quorum.execution_authority_allowed is False,
    }
    independent_attested_quorum = _independent_attested_commons_quorum(ml_kem_receipt)
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    report = Phase2CommonsQuorumReport(
        beast_object_type="dai_phase2_commons_quorum_report",
        version=PHASE2_COMMONS_QUORUM_VERSION,
        report_id="commons:phase2:stale-listener-world-bound-quorum:v1",
        phase2_world_state_digest=phase2_world_state_digest,
        proposal_digest=proposal_digest,
        commons_admission_digest=admission.receipt_digest,
        quorum_decision_digest=quorum.receipt_digest,
        admitted=admission.admitted,
        quorum_decision=quorum.decision.value,
        admitted_node_count=quorum.admitted_node_count,
        witness_roles=quorum.witness_roles,
        vote_digests=quorum.vote_digests,
        quorum_evidence_class=(
            "independent_attested_external_quorum" if independent_attested_quorum else "local_world_bound_quorum_simulation"
        ),
        independent_attested_quorum=independent_attested_quorum,
        red_gates=red_gates + admission.red_gates + quorum.red_gates,
        provider_calls_used=0,
        execution_authority_allowed=quorum.execution_authority_allowed,
        production_authority_allowed=False,
    )
    return admission, quorum, report


def commons_quorum_report_to_dict(report: Phase2CommonsQuorumReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["maximum_authority"] = report.maximum_authority.value
    payload["passed"] = report.passed
    payload["report_digest"] = report.report_digest
    return payload


def _independent_attested_commons_quorum(ml_kem_receipt: Mapping[str, Any]) -> bool:
    return bool(
        ml_kem_receipt.get("independent_attested_external_quorum") is True
        and ml_kem_receipt.get("third_party_verifier_receipt_digest")
        and str(ml_kem_receipt.get("third_party_verifier_receipt_digest")).startswith("sha256:")
    )


def write_phase2_commons_quorum_packet(
    path: str | Path,
    *,
    admission: CommonsAdmissionReceipt,
    quorum: QuorumDecisionReceipt,
    report: Phase2CommonsQuorumReport,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "beast_object_type": "dai_phase2_commons_quorum_packet",
        "version": PHASE2_COMMONS_QUORUM_VERSION,
        "admission": asdict(admission),
        "admission_digest": admission.receipt_digest,
        "quorum": asdict(quorum),
        "quorum_digest": quorum.receipt_digest,
        "report": commons_quorum_report_to_dict(report),
        "packet_digest": "",
    }
    payload["packet_digest"] = sha256_digest({key: value for key, value in payload.items() if key != "packet_digest"})
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return target


def load_ml_kem_receipt(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ML-KEM receipt must be a JSON object")
    return payload
