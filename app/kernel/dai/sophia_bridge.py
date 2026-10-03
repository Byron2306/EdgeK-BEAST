"""Sophia -> BEAST DAI bridge.

This module turns a Sophia semantic export into a quarantined BEAST
`ConceptCandidate`.  It is intentionally stricter than a format adapter: Sophia
must demonstrate support rows, visible source-span grounding, distinct semantic
families, and explicit contradiction/negative-control rows before BEAST accepts
the candidate as even a candidate.
"""
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


class SophiaBridgeError(ValueError):
    """Raised when a Sophia export cannot honestly propose a DAI candidate."""


@dataclass(frozen=True, slots=True)
class SophiaExportBridgeSummary:
    export_digest: str
    total_rows: int
    support_rows: int
    contradiction_rows: int
    distinct_support_case_ids: tuple[str, ...]
    distinct_support_families: tuple[str, ...]
    negative_case_ids: tuple[str, ...]
    source_span_row_digests: tuple[str, ...]

    @property
    def summary_digest(self) -> str:
        return sha256_digest(self)


def concept_candidate_from_sophia_export(
    export_path: str | Path,
    *,
    source_receipt: ArtifactReceipt,
) -> tuple[ConceptCandidate, SophiaExportBridgeSummary]:
    """Compile a Sophia semantic export into a quarantined concept candidate."""

    if source_receipt.organ is not DAIOrgan.SOPHIA:
        raise SophiaBridgeError("Sophia concept candidates require a Sophia artifact receipt")
    if not source_receipt.verify_file_digest():
        raise SophiaBridgeError("Sophia artifact digest does not recompute")

    source = Path(export_path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    rows = payload.get("rows") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(rows, list):
        raise SophiaBridgeError("Sophia export must contain summary and rows")
    if summary.get("passes_phase3_export_semantic_gate") is not True:
        raise SophiaBridgeError("Sophia export semantic gate is not green")
    if int(summary.get("passed") or 0) != int(summary.get("total") or -1):
        raise SophiaBridgeError("Sophia export contains failed rows")

    support_rows: list[Mapping[str, Any]] = []
    contradiction_rows: list[Mapping[str, Any]] = []
    source_span_row_digests: list[str] = []

    for row in rows:
        if not isinstance(row, Mapping) or row.get("passed") is not True:
            continue
        top = row.get("top")
        if not isinstance(top, Mapping):
            continue
        label = str(top.get("support_label") or "").strip().lower()
        entailment = str(top.get("entailment_status") or "").strip().lower()
        exact_span = str(top.get("exact_span") or "").strip()
        page_locator = str(top.get("page_locator") or "").strip()
        page_status = str(top.get("page_status") or "").strip().lower()
        if label == "supports" and entailment == "entailed_by_visible_span":
            if not exact_span:
                raise SophiaBridgeError("support row lacks exact visible span")
            if not page_locator and "visible" not in page_status:
                raise SophiaBridgeError("support row lacks page/span visibility")
            support_rows.append(row)
            source_span_row_digests.append(sha256_digest({"sophia_row": _bounded_row(row)}))
        elif label == "contradicts":
            if entailment in {"entailed_by_visible_span", "supports"}:
                raise SophiaBridgeError("contradiction row is mislabeled as entailed support")
            contradiction_rows.append(row)

    support_case_ids = tuple(sorted({str(row.get("case_id")) for row in support_rows if row.get("case_id")}))
    negative_case_ids = tuple(sorted({str(row.get("case_id")) for row in contradiction_rows if row.get("case_id")}))
    support_families = tuple(sorted(_semantic_families(support_rows)))

    if len(support_rows) < 2 or len(support_case_ids) < 2:
        raise SophiaBridgeError("Sophia export needs at least two distinct support cases")
    if len(support_families) < 2:
        raise SophiaBridgeError("Sophia export needs support across at least two semantic families")
    if not contradiction_rows or not negative_case_ids:
        raise SophiaBridgeError("Sophia export needs explicit contradiction/negative-control rows")

    bridge_summary = SophiaExportBridgeSummary(
        export_digest=source_receipt.artifact_digest,
        total_rows=len(rows),
        support_rows=len(support_rows),
        contradiction_rows=len(contradiction_rows),
        distinct_support_case_ids=support_case_ids,
        distinct_support_families=support_families,
        negative_case_ids=negative_case_ids,
        source_span_row_digests=tuple(sorted(source_span_row_digests)),
    )

    candidate = ConceptCandidate(
        candidate_id="sophia:academic-source-support:v1",
        source_organ=DAIOrgan.SOPHIA,
        source_artifact_receipts=(source_receipt.receipt_digest,),
        concept_label=(
            "academic source-support predicate family "
            f"derived from {bridge_summary.support_rows} support rows and "
            f"{bridge_summary.contradiction_rows} contradiction rows"
        ),
        candidate_predicates=(
            CandidatePredicateSpec(
                predicate="source_supports_claim",
                value_type="bool",
                subject_kinds=("source_span", "citation_lead"),
                true_text="supports the claim",
                false_text="does not support the claim",
                visual_true="support badge and green source-to-claim edge",
                visual_false="no-support badge and broken source-to-claim edge",
                conflicts_with=({"predicate": "source_contradicts_claim", "value": True},),
            ),
            CandidatePredicateSpec(
                predicate="source_contradicts_claim",
                value_type="bool",
                subject_kinds=("source_span", "citation_lead"),
                true_text="contradicts the claim",
                false_text="does not contradict the claim",
                visual_true="contradiction badge and red source-to-claim edge",
                visual_false="no-contradiction badge",
                conflicts_with=({"predicate": "source_supports_claim", "value": True},),
            ),
            CandidatePredicateSpec(
                predicate="citation_needed",
                value_type="bool",
                subject_kinds=("claim",),
                true_text="needs a citation before it can be asserted",
                false_text="has enough citation support for this bounded use",
                visual_true="citation-needed warning marker",
                visual_false="citation-ready marker",
            ),
        ),
        transfer_evidence=TransferEvidence(
            near_transfer_case_ids=(support_case_ids[0],),
            far_transfer_case_ids=support_case_ids[1:],
            negative_case_ids=negative_case_ids,
            source_span_receipts=(source_receipt.receipt_digest, bridge_summary.summary_digest, *bridge_summary.source_span_row_digests[:8]),
        ),
        authorship_boundary=(
            "Sophia semantic export proposes academic source-support laws; "
            "BEAST promotion, independent entailment and later quorum are required."
        ),
    )
    return candidate, bridge_summary


def _semantic_families(rows: list[Mapping[str, Any]]) -> set[str]:
    families: set[str] = set()
    for row in rows:
        top = row.get("top")
        if not isinstance(top, Mapping):
            continue
        for field_name in ("semantic_overlap", "broad_field_overlap"):
            values = top.get(field_name)
            if isinstance(values, list):
                families.update(str(value) for value in values if str(value).strip())
    return families


def _bounded_row(row: Mapping[str, Any]) -> dict[str, Any]:
    top = row.get("top")
    top = top if isinstance(top, Mapping) else {}
    return {
        "case_id": row.get("case_id"),
        "passed": row.get("passed"),
        "support_label": top.get("support_label"),
        "entailment_status": top.get("entailment_status"),
        "exact_span": top.get("exact_span"),
        "page_locator": top.get("page_locator"),
        "semantic_overlap": top.get("semantic_overlap"),
        "source_name": top.get("source_name"),
        "source_role": top.get("source_role"),
    }

