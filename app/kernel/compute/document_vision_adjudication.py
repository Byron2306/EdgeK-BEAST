"""Independent document-vision adjudication for C4-X.

The document arena is only meaningful if visual/scientific PDF claims are not
graded by BEAST's own answer.  This module compares three independent lanes:

* native Gemini vision observations
* blinded human inspection observations
* frozen oracle annotations

Truth credit is intentionally certificate-shaped.  A document can pass one
lane and still fail another; no average score hides a custody or independence
failure.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .deterministic_intelligence import sha256_digest, utc_now_iso


REQUIRED_STRUCTURAL_FIELDS = (
    "tables",
    "merged_headers",
    "footnotes",
    "statistical_notation",
    "chart_values",
)


def adjudicate_document_vision_lanes(
    documents: Sequence[Mapping[str, Any]],
    *,
    gemini_rows: Sequence[Mapping[str, Any]] = (),
    human_rows: Sequence[Mapping[str, Any]] = (),
    oracle_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Compare Gemini/human/oracle sidecars without reading BEAST answers."""
    real_documents = [dict(doc) for doc in documents if not doc.get("missing")]
    gemini_by_doc = _index_rows(gemini_rows)
    human_by_doc = _index_rows(human_rows)
    oracle_by_doc = _index_rows(oracle_rows)
    document_receipts = []
    for doc in real_documents:
        document_receipts.append(
            _adjudicate_one(
                doc,
                gemini=_first(gemini_by_doc.get(str(doc.get("document_id") or ""), ())),
                human=_first(human_by_doc.get(str(doc.get("document_id") or ""), ())),
                oracle=_first(oracle_by_doc.get(str(doc.get("document_id") or ""), ())),
            )
        )
    gates = _certificate_gates(document_receipts, real_document_count=len(real_documents))
    receipt_core = {
        "beast_object_type": "c4x_document_vision_adjudication",
        "version": "1.0",
        "created_at": utc_now_iso(),
        "real_document_count": len(real_documents),
        "document_receipts": document_receipts,
        "certificate_gates": gates,
        "truth_credit_awarded": bool(real_documents) and all(bool(value) for value in gates.values()),
        "claim_boundary": (
            "Independent visual/scientific document adjudication only. Expected "
            "answers must come from frozen oracle rows, not BEAST conclusions. "
            "Gemini rows must be native vision observations; human rows must be "
            "blinded; all rows must bind to PDF or rendered-page source digests."
        ),
    }
    return {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}


def findings_digest(row: Mapping[str, Any] | None) -> str:
    return sha256_digest(_normalized_findings(row))


def _adjudicate_one(
    doc: Mapping[str, Any],
    *,
    gemini: Mapping[str, Any] | None,
    human: Mapping[str, Any] | None,
    oracle: Mapping[str, Any] | None,
) -> dict[str, Any]:
    document_id = str(doc.get("document_id") or "")
    source_digests = _source_digests(doc)
    oracle_norm = _normalized_findings(oracle)
    gemini_norm = _normalized_findings(gemini)
    human_norm = _normalized_findings(human)
    field_agreement = {
        field: {
            "oracle_field_present": field in oracle_norm,
            "gemini_matches_oracle": field in oracle_norm and gemini_norm.get(field) == oracle_norm.get(field),
            "human_matches_oracle": field in oracle_norm and human_norm.get(field) == oracle_norm.get(field),
            "gemini_human_match": field in gemini_norm and gemini_norm.get(field) == human_norm.get(field),
        }
        for field in REQUIRED_STRUCTURAL_FIELDS
    }
    oracle_valid = _oracle_valid(oracle, source_digests=source_digests)
    gemini_custody = _source_digest_valid(gemini, source_digests=source_digests)
    human_custody = _source_digest_valid(human, source_digests=source_digests)
    gemini_independent = _gemini_independent(gemini)
    human_blinded = _human_blinded(human)
    all_fields_present = all(field_agreement[field]["oracle_field_present"] for field in REQUIRED_STRUCTURAL_FIELDS)
    all_gemini_match = all(field_agreement[field]["gemini_matches_oracle"] for field in REQUIRED_STRUCTURAL_FIELDS)
    all_human_match = all(field_agreement[field]["human_matches_oracle"] for field in REQUIRED_STRUCTURAL_FIELDS)
    all_mutual_match = all(field_agreement[field]["gemini_human_match"] for field in REQUIRED_STRUCTURAL_FIELDS)
    pass_reasons = {
        "oracle_valid": oracle_valid,
        "gemini_source_custody_valid": gemini_custody,
        "human_source_custody_valid": human_custody,
        "gemini_native_vision_independent": gemini_independent,
        "human_blinded_independent": human_blinded,
        "oracle_has_required_structural_fields": all_fields_present,
        "gemini_matches_oracle": all_gemini_match,
        "human_matches_oracle": all_human_match,
        "gemini_human_match": all_mutual_match,
    }
    passed = all(pass_reasons.values())
    receipt_core = {
        "document_id": document_id,
        "document_sha256": str(doc.get("sha256") or ""),
        "source_digests": source_digests,
        "gemini_row_present": gemini is not None,
        "human_row_present": human is not None,
        "oracle_row_present": oracle is not None,
        "gemini_findings_digest": findings_digest(gemini),
        "human_findings_digest": findings_digest(human),
        "oracle_findings_digest": findings_digest(oracle),
        "field_agreement": field_agreement,
        "pass_reasons": pass_reasons,
        "passed": passed,
        "failure_reasons": tuple(name for name, ok in pass_reasons.items() if not ok),
    }
    return {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}


def _certificate_gates(document_receipts: Sequence[Mapping[str, Any]], *, real_document_count: int) -> dict[str, bool]:
    if not document_receipts or real_document_count <= 0:
        return {
            "independent_oracle_present": False,
            "native_gemini_vision_custody": False,
            "blinded_human_inspection_custody": False,
            "gemini_human_oracle_agreement": False,
            "merged_header_scientific_tables": False,
            "footnotes_and_statistical_notation": False,
            "chart_image_extraction": False,
            "no_text_answer_generation": False,
        }
    return {
        "independent_oracle_present": all(bool(r["pass_reasons"]["oracle_valid"]) for r in document_receipts),
        "native_gemini_vision_custody": all(
            bool(r["pass_reasons"]["gemini_source_custody_valid"] and r["pass_reasons"]["gemini_native_vision_independent"])
            for r in document_receipts
        ),
        "blinded_human_inspection_custody": all(
            bool(r["pass_reasons"]["human_source_custody_valid"] and r["pass_reasons"]["human_blinded_independent"])
            for r in document_receipts
        ),
        "gemini_human_oracle_agreement": all(
            bool(r["pass_reasons"]["gemini_matches_oracle"] and r["pass_reasons"]["human_matches_oracle"] and r["pass_reasons"]["gemini_human_match"])
            for r in document_receipts
        ),
        "merged_header_scientific_tables": all(_field_passes(r, "merged_headers") for r in document_receipts),
        "footnotes_and_statistical_notation": all(
            _field_passes(r, "footnotes") and _field_passes(r, "statistical_notation")
            for r in document_receipts
        ),
        "chart_image_extraction": all(_field_passes(r, "chart_values") for r in document_receipts),
        "no_text_answer_generation": all(bool(r["pass_reasons"]["gemini_native_vision_independent"]) for r in document_receipts),
    }


def _field_passes(receipt: Mapping[str, Any], field: str) -> bool:
    agreement = receipt["field_agreement"][field]
    return bool(
        agreement["oracle_field_present"]
        and agreement["gemini_matches_oracle"]
        and agreement["human_matches_oracle"]
        and agreement["gemini_human_match"]
    )


def _index_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        doc_id = str(row.get("document_id") or "").strip()
        if doc_id:
            indexed.setdefault(doc_id, []).append(row)
    return indexed


def _first(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return rows[0] if rows else None


def _source_digests(doc: Mapping[str, Any]) -> tuple[str, ...]:
    digests = []
    if str(doc.get("sha256") or "").startswith("sha256:"):
        digests.append(str(doc["sha256"]))
    first_page = doc.get("first_page_image")
    if isinstance(first_page, Mapping) and str(first_page.get("sha256") or "").startswith("sha256:"):
        digests.append(str(first_page["sha256"]))
    return tuple(digests)


def _source_digest_valid(row: Mapping[str, Any] | None, *, source_digests: Sequence[str]) -> bool:
    if row is None:
        return False
    digest = str(row.get("source_digest") or row.get("pdf_sha256") or row.get("page_image_sha256") or "")
    return digest in set(source_digests)


def _oracle_valid(row: Mapping[str, Any] | None, *, source_digests: Sequence[str]) -> bool:
    if row is None or not _source_digest_valid(row, source_digests=source_digests):
        return False
    oracle_type = str(row.get("oracle_type") or row.get("observer_type") or "")
    frozen = row.get("frozen_before_scoring", True)
    return (oracle_type in {"scientific_pdf_structural_truth", "document_structural_oracle"} or row.get("is_oracle") is True) and frozen is not False


def _gemini_independent(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    observer = str(row.get("observer_type") or "")
    source_mode = str(row.get("source_mode") or "")
    raw_text_used = bool(row.get("raw_text_answer_used") or row.get("beast_text_answer_used"))
    live_provenance = (
        row.get("live_execution") is True
        and int(row.get("provider_calls_used") or 0) >= 1
        and _looks_digest(str(row.get("request_digest") or ""))
        and _looks_digest(str(row.get("raw_response_digest") or row.get("response_digest") or ""))
        and bool(str(row.get("model") or "").strip())
    )
    return observer in {"gemini_native_vision", "native_gemini_vision"} and "vision" in source_mode and not raw_text_used and live_provenance


def _human_blinded(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    return (
        (str(row.get("observer_type") or "") == "blinded_human" or row.get("blinded") is True)
        and row.get("blinded") is not False
        and not bool(row.get("saw_gemini_output"))
        and not bool(row.get("saw_beast_answer"))
    )


def _normalized_findings(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    raw = row.get("findings") or row.get("structural_findings") or {}
    if not isinstance(raw, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for field in REQUIRED_STRUCTURAL_FIELDS:
        if field in raw:
            normalized[field] = _normalize_value(raw[field])
    return normalized


def _looks_digest(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key).strip().lower(): _normalize_value(item) for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    return value
