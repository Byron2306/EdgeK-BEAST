"""Phase-2 Sophia acquisition bridge for stale-listener capability candidates."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.contracts import (
    ArtifactReceipt,
    CandidatePredicateSpec,
    ConceptCandidate,
    DAIOrgan,
    TransferEvidence,
)


PHASE2_SOPHIA_STALE_LISTENER_SCHEMA = "dai.phase2.sophia_stale_listener_examples.v1"


class Phase2SophiaAcquisitionError(ValueError):
    """Raised when Sophia-side examples cannot propose a bounded Phase-2 candidate."""


@dataclass(frozen=True, slots=True)
class Phase2SophiaAcquisitionSummary:
    artifact_digest: str
    total_examples: int
    near_case_ids: tuple[str, ...]
    far_case_ids: tuple[str, ...]
    negative_case_ids: tuple[str, ...]
    refusal_case_ids: tuple[str, ...]
    domains: tuple[str, ...]
    source_example_digests: tuple[str, ...]

    @property
    def summary_digest(self) -> str:
        return sha256_digest(self)


REQUIRED_POSITIVE_TERMS = {
    "owned_process",
    "listener_socket",
    "stale_generation",
    "same_port_replacement",
}
REQUIRED_NEGATIVE_BOUNDARIES = {
    "must_not_retire_unknown_process",
    "must_not_retire_healthy_current_service",
}


def stale_listener_candidate_from_sophia_examples(
    examples_path: str | Path,
    *,
    source_receipt: ArtifactReceipt,
) -> tuple[ConceptCandidate, Phase2SophiaAcquisitionSummary]:
    """Compile Sophia-style operational examples into a quarantined candidate.

    The examples may propose `stale_listener_conflict`; they cannot grant
    execution authority.  BEAST requires near transfer, far transfer, negative
    controls and explicit refusal boundaries before even accepting the concept
    candidate.
    """
    if source_receipt.organ is not DAIOrgan.SOPHIA:
        raise Phase2SophiaAcquisitionError("Phase-2 stale-listener acquisition requires a Sophia artifact receipt")
    if not source_receipt.verify_file_digest():
        raise Phase2SophiaAcquisitionError("Sophia acquisition artifact digest does not recompute")

    source = Path(examples_path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise Phase2SophiaAcquisitionError("Sophia acquisition artifact must be a JSON object")
    if payload.get("schema") != PHASE2_SOPHIA_STALE_LISTENER_SCHEMA:
        raise Phase2SophiaAcquisitionError("unsupported Sophia stale-listener acquisition schema")
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if summary.get("passes_acquisition_gate") is not True:
        raise Phase2SophiaAcquisitionError("Sophia acquisition gate is not green")
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        raise Phase2SophiaAcquisitionError("Sophia acquisition artifact requires examples")

    bounded = [_bounded_example(example) for example in examples]
    near = tuple(sorted(example["case_id"] for example in bounded if example["transfer_class"] == "near"))
    far = tuple(sorted(example["case_id"] for example in bounded if example["transfer_class"] == "far"))
    negative = tuple(sorted(example["case_id"] for example in bounded if example["transfer_class"] == "negative"))
    refusal = tuple(sorted(example["case_id"] for example in bounded if example["outcome_label"] == "safe_refusal"))
    domains = tuple(sorted({example["domain"] for example in bounded}))
    source_example_digests = tuple(sorted(sha256_digest({"sophia_phase2_example": example}) for example in bounded))

    if not near:
        raise Phase2SophiaAcquisitionError("Sophia acquisition requires at least one near-transfer example")
    if not far:
        raise Phase2SophiaAcquisitionError("Sophia acquisition requires at least one far-transfer example")
    if len(domains) < 3:
        raise Phase2SophiaAcquisitionError("Sophia acquisition requires at least three operational domains")
    if len(negative) < 2 or len(refusal) < 1:
        raise Phase2SophiaAcquisitionError("Sophia acquisition requires negative and refusal examples")

    positive_terms = set().union(*(set(example["evidence_terms"]) for example in bounded if example["outcome_label"] == "stale_listener_conflict"))
    if not REQUIRED_POSITIVE_TERMS.issubset(positive_terms):
        missing = ", ".join(sorted(REQUIRED_POSITIVE_TERMS - positive_terms))
        raise Phase2SophiaAcquisitionError(f"Sophia acquisition lacks required positive evidence terms: {missing}")
    negative_boundaries = set().union(*(set(example["required_boundaries"]) for example in bounded if example["transfer_class"] == "negative"))
    if not REQUIRED_NEGATIVE_BOUNDARIES.issubset(negative_boundaries):
        missing = ", ".join(sorted(REQUIRED_NEGATIVE_BOUNDARIES - negative_boundaries))
        raise Phase2SophiaAcquisitionError(f"Sophia acquisition lacks required negative boundaries: {missing}")

    bridge_summary = Phase2SophiaAcquisitionSummary(
        artifact_digest=source_receipt.artifact_digest,
        total_examples=len(bounded),
        near_case_ids=near,
        far_case_ids=far,
        negative_case_ids=negative,
        refusal_case_ids=refusal,
        domains=domains,
        source_example_digests=source_example_digests,
    )
    candidate = ConceptCandidate(
        candidate_id="sophia:phase2:stale-listener-conflict:v1",
        source_organ=DAIOrgan.SOPHIA,
        source_artifact_receipts=(source_receipt.receipt_digest,),
        concept_label=(
            "stale_listener_conflict derived from Sophia operational examples "
            f"across {len(domains)} domains with near, far and negative transfer"
        ),
        candidate_predicates=(
            CandidatePredicateSpec(
                predicate="stale_listener_conflict",
                value_type="bool",
                subject_kinds=("service_listener", "process_socket"),
                true_text="has a stale listener conflict",
                false_text="does not have a stale listener conflict",
                visual_true="stale listener warning badge on the occupied port",
                visual_false="no stale-listener warning badge",
                conflicts_with=(
                    {"predicate": "listener_current_and_healthy", "value": True},
                    {"predicate": "listener_owner_unknown", "value": True},
                ),
            ),
            CandidatePredicateSpec(
                predicate="listener_owner_verified",
                value_type="bool",
                subject_kinds=("process_socket",),
                true_text="has a verified listener owner",
                false_text="does not have a verified listener owner",
                visual_true="owner-verified badge",
                visual_false="owner-unknown refusal marker",
            ),
            CandidatePredicateSpec(
                predicate="same_port_replacement_healthy",
                value_type="bool",
                subject_kinds=("service_listener",),
                true_text="has a healthy replacement on the same port",
                false_text="does not have a healthy replacement on the same port",
                visual_true="replacement healthy badge on the original port",
                visual_false="replacement health missing marker",
            ),
            CandidatePredicateSpec(
                predicate="unrelated_listener_unchanged",
                value_type="bool",
                subject_kinds=("service_listener",),
                true_text="left unrelated listeners unchanged",
                false_text="changed an unrelated listener",
                visual_true="unchanged-control badge",
                visual_false="side-effect warning badge",
            ),
        ),
        transfer_evidence=TransferEvidence(
            near_transfer_case_ids=near,
            far_transfer_case_ids=far,
            negative_case_ids=negative,
            source_span_receipts=(source_receipt.receipt_digest, bridge_summary.summary_digest, *source_example_digests),
        ),
        authorship_boundary=(
            "Sophia examples propose the stale-listener conflict concept; BEAST live execution, "
            "Seraph attacks, Harmonic transfer, Commons quorum and Sensorium evidence are still required."
        ),
    )
    return candidate, bridge_summary


def _bounded_example(example: Any) -> dict[str, Any]:
    if not isinstance(example, Mapping):
        raise Phase2SophiaAcquisitionError("Sophia acquisition example must be an object")
    required = ("case_id", "transfer_class", "domain", "outcome_label", "source_span", "evidence_terms", "required_boundaries")
    missing = [field for field in required if field not in example]
    if missing:
        raise Phase2SophiaAcquisitionError("Sophia acquisition example missing fields: " + ", ".join(missing))
    transfer_class = str(example["transfer_class"]).strip()
    if transfer_class not in {"near", "far", "negative"}:
        raise Phase2SophiaAcquisitionError("Sophia acquisition transfer_class must be near, far or negative")
    evidence_terms = tuple(sorted(str(term).strip() for term in example["evidence_terms"] if str(term).strip()))
    required_boundaries = tuple(sorted(str(term).strip() for term in example["required_boundaries"] if str(term).strip()))
    if not evidence_terms or not required_boundaries:
        raise Phase2SophiaAcquisitionError("Sophia acquisition example requires terms and boundaries")
    return {
        "case_id": str(example["case_id"]).strip(),
        "transfer_class": transfer_class,
        "domain": str(example["domain"]).strip(),
        "outcome_label": str(example["outcome_label"]).strip(),
        "source_span": str(example["source_span"]).strip(),
        "evidence_terms": evidence_terms,
        "required_boundaries": required_boundaries,
    }


def phase2_acquisition_receipt(candidate: ConceptCandidate, summary: Phase2SophiaAcquisitionSummary) -> dict[str, Any]:
    return {
        "beast_object_type": "dai_phase2_sophia_stale_listener_acquisition_receipt",
        "version": "2026-08-04.phase2.sophia-acquisition.v1",
        "candidate_id": candidate.candidate_id,
        "candidate_digest": candidate.candidate_digest,
        "summary_digest": summary.summary_digest,
        "source_example_digests": summary.source_example_digests,
        "near_case_ids": summary.near_case_ids,
        "far_case_ids": summary.far_case_ids,
        "negative_case_ids": summary.negative_case_ids,
        "refusal_case_ids": summary.refusal_case_ids,
        "domains": summary.domains,
        "candidate_authority": candidate.maximum_authority.value,
        "promotion_state": candidate.promotion_state.value,
        "provider_calls_used": 0,
        "execution_authority_allowed": False,
    }


def write_phase2_acquisition_receipt(path: str | Path, candidate: ConceptCandidate, summary: Phase2SophiaAcquisitionSummary) -> Path:
    payload = phase2_acquisition_receipt(candidate, summary)
    payload["receipt_digest"] = sha256_digest(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return target

