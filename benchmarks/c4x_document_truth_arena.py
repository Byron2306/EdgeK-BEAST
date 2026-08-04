#!/usr/bin/env python3
"""Document/scientific-PDF frontier for the C4-X Truth Arena.

This first slice uses real local PDFs and exports audit packets. It does not
pretend that live Gemini vision or blinded human inspection has run unless
their sidecar annotations are supplied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.compute.document_vision_adjudication import adjudicate_document_vision_lanes  # noqa: E402


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "c4x-document-truth-arena"
DEFAULT_CORPUS = (
    REPO_ROOT / "docs/external/obsidian-beast/Blurred Text Extraction Limitations.pdf",
    REPO_ROOT / "evidence/inference_economy_v0_9.pdf",
    REPO_ROOT / "assets/release/commons-media/inference-economy-paper.pdf",
)


def run_document_truth_arena(
    *,
    corpus: tuple[str | Path, ...] = DEFAULT_CORPUS,
    evidence_root: str | Path = DEFAULT_EVIDENCE_ROOT,
    run_id: str | None = None,
    render_first_page: bool = True,
    gemini_vision_sidecar: str | Path | None = None,
    human_annotation_sidecar: str | Path | None = None,
    oracle_sidecar: str | Path | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    root = Path(evidence_root) / run_id
    packet_root = root / "audit_packets"
    image_root = root / "page_images"
    packet_root.mkdir(parents=True, exist_ok=True)
    image_root.mkdir(parents=True, exist_ok=True)
    gemini = _load_optional_jsonl(gemini_vision_sidecar)
    human = _load_optional_jsonl(human_annotation_sidecar)
    oracle = _load_optional_jsonl(oracle_sidecar)
    documents = []
    for raw_path in corpus:
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            documents.append(_missing_document(path))
            continue
        documents.append(_inspect_pdf(path, image_root=image_root, render_first_page=render_first_page))
    adjudication = adjudicate_document_vision_lanes(documents, gemini_rows=gemini, human_rows=human, oracle_rows=oracle)
    lanes = _lanes(documents, gemini=gemini, human=human, oracle=oracle, adjudication=adjudication)
    receipt_core = {
        "beast_object_type": "c4x_document_truth_arena",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Real local PDF corpus audit packet. Poppler text/page extraction and "
            "page-image rendering are local observations. Native Gemini vision and "
            "blinded human inspection are protocol lanes only until sidecar results "
            "are supplied. Merged-header table, footnote/statistical-notation, and "
            "chart extraction certificates require human/oracle annotations before "
            "truth credit is awarded."
        ),
        "corpus": documents,
        "lanes": lanes,
        "vision_adjudication": adjudication,
        "exports": {
            "jsonl": "audit_packets/document_corpus.jsonl",
            "csv": "audit_packets/document_corpus.csv",
            "zotero": "audit_packets/zotero_items.json",
            "gemini_vs_human_protocol": "audit_packets/gemini_vs_human_protocol.jsonl",
            "human_annotation_packet": "audit_packets/human_annotation_packet.jsonl",
            "oracle_packet_template": "audit_packets/oracle_packet_template.jsonl",
            "adjudication": "audit_packets/document_vision_adjudication.jsonl",
            "disagreements": "audit_packets/document_vision_disagreements.csv",
        },
        "scorecard": _scorecard(documents, lanes, adjudication),
    }
    receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
    _write_exports(packet_root, receipt)
    (root / "document_truth_arena.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "document_truth_arena.md").write_text(_markdown(receipt), encoding="utf-8")
    _write_checksums(root)
    evidence_root = Path(evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)
    (evidence_root / "latest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "evidence_root": str(root)}


def _inspect_pdf(path: Path, *, image_root: Path, render_first_page: bool) -> dict[str, Any]:
    pdfinfo = _run(["pdfinfo", str(path)])
    text = _extract_text(path)
    page_count = _parse_pages(pdfinfo["stdout"])
    image_info = _pdfimages_list(path)
    page_image = _render_first_page(path, image_root) if render_first_page else {}
    char_count = len(text)
    likely_scanned = char_count < max(80, page_count * 120)
    return {
        "document_id": _safe_id(path.stem),
        "path": _rel(path),
        "title": path.stem,
        "sha256": _file_sha256(path),
        "bytes": path.stat().st_size,
        "page_count": page_count,
        "pdfinfo_status": pdfinfo["status"],
        "text_char_count": char_count,
        "text_digest": sha256_digest(text[:200000]),
        "likely_scanned_or_ocr_hostile": likely_scanned,
        "image_object_count": image_info["image_count"],
        "first_page_image": page_image,
        "frontier_tasks": {
            "real_corpus_messy_pdf": True,
            "native_gemini_vision_vs_blinded_human": "requires_sidecars",
            "merged_header_scientific_tables": "requires_oracle_annotation",
            "footnotes_and_statistical_notation": "requires_oracle_annotation",
            "chart_image_extraction_from_pdf": "page_image_rendered" if page_image else "render_unavailable",
        },
    }


def _missing_document(path: Path) -> dict[str, Any]:
    return {
        "document_id": _safe_id(path.stem),
        "path": _rel(path),
        "title": path.stem,
        "missing": True,
        "frontier_tasks": {},
    }


def _lanes(
    documents: list[dict[str, Any]],
    *,
    gemini: list[dict[str, Any]],
    human: list[dict[str, Any]],
    oracle: list[dict[str, Any]],
    adjudication: Mapping[str, Any],
) -> dict[str, Any]:
    gates = adjudication["certificate_gates"]
    return {
        "poppler_text_extraction": {
            "status": "observed",
            "documents": len([doc for doc in documents if not doc.get("missing")]),
            "scanned_or_ocr_hostile_count": sum(int(bool(doc.get("likely_scanned_or_ocr_hostile"))) for doc in documents),
        },
        "pdf_page_image_extraction": {
            "status": "observed",
            "rendered_first_page_count": sum(int(bool(doc.get("first_page_image"))) for doc in documents),
        },
        "native_gemini_vision": {
            "status": "sidecar_supplied" if gemini else "pending_live_or_sidecar",
            "annotation_count": len(gemini),
            "custody_valid": gates["native_gemini_vision_custody"],
        },
        "blinded_human_inspection": {
            "status": "sidecar_supplied" if human else "pending_blinded_annotations",
            "annotation_count": len(human),
            "custody_valid": gates["blinded_human_inspection_custody"],
        },
        "independent_oracle": {
            "status": "sidecar_supplied" if oracle else "pending_frozen_oracle_annotations",
            "annotation_count": len(oracle),
            "valid": gates["independent_oracle_present"],
        },
        "merged_header_scientific_tables": {
            "status": "passed" if gates["merged_header_scientific_tables"] else "pending_or_failed_oracle_adjudication",
            "truth_credit_awarded": gates["merged_header_scientific_tables"],
        },
        "footnotes_and_statistical_notation": {
            "status": "passed" if gates["footnotes_and_statistical_notation"] else "pending_or_failed_oracle_adjudication",
            "truth_credit_awarded": gates["footnotes_and_statistical_notation"],
        },
        "chart_image_extraction": {
            "status": "page_images_rendered_or_attempted",
            "truth_credit_awarded": gates["chart_image_extraction"],
        },
        "gemini_human_oracle_agreement": {
            "status": "passed" if gates["gemini_human_oracle_agreement"] else "pending_or_failed_three_way_agreement",
            "truth_credit_awarded": gates["gemini_human_oracle_agreement"],
        },
    }


def _scorecard(documents: list[dict[str, Any]], lanes: Mapping[str, Any], adjudication: Mapping[str, Any]) -> dict[str, Any]:
    real = [doc for doc in documents if not doc.get("missing")]
    gates = dict(adjudication["certificate_gates"])
    truth_credit = bool(adjudication["truth_credit_awarded"])
    return {
        "real_pdf_count": len(real),
        "missing_pdf_count": len(documents) - len(real),
        "scanned_or_ocr_hostile_count": sum(int(bool(doc.get("likely_scanned_or_ocr_hostile"))) for doc in real),
        "page_images_rendered": lanes["pdf_page_image_extraction"]["rendered_first_page_count"],
        "gemini_vs_human_ready": lanes["native_gemini_vision"]["status"] == "sidecar_supplied" and lanes["blinded_human_inspection"]["status"] == "sidecar_supplied",
        "independent_oracle_ready": lanes["independent_oracle"]["status"] == "sidecar_supplied",
        "certificate_gates": gates,
        "truth_credit_awarded": truth_credit,
        "reason_truth_credit_not_awarded": "" if truth_credit else "requires source-digest-bound Gemini vision, blinded human annotations, frozen oracle annotations, and field-level agreement",
    }


def _extract_text(path: Path) -> str:
    completed = _run(["pdftotext", "-layout", str(path), "-"])
    return completed["stdout"] if completed["status"] == "ok" else ""


def _pdfimages_list(path: Path) -> dict[str, Any]:
    completed = _run(["pdfimages", "-list", str(path)])
    if completed["status"] != "ok":
        return {"status": completed["status"], "image_count": 0}
    rows = [line for line in completed["stdout"].splitlines() if line.strip()]
    return {"status": "ok", "image_count": max(0, len(rows) - 2)}


def _render_first_page(path: Path, image_root: Path) -> dict[str, Any]:
    prefix = image_root / _safe_id(path.stem)
    completed = _run(["pdftoppm", "-png", "-f", "1", "-singlefile", str(path), str(prefix)])
    output = prefix.with_suffix(".png")
    if completed["status"] != "ok" or not output.exists():
        return {"status": completed["status"], "stderr_digest": sha256_digest(completed["stderr"])}
    return {
        "status": "ok",
        "path": _rel(output),
        "sha256": _file_sha256(output),
        "bytes": output.stat().st_size,
    }


def _parse_pages(pdfinfo_text: str) -> int:
    for line in pdfinfo_text.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return 0
    return 0


def _write_exports(packet_root: Path, receipt: Mapping[str, Any]) -> None:
    docs = list(receipt["corpus"])
    with (packet_root / "document_corpus.jsonl").open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, sort_keys=True) + "\n")
    with (packet_root / "document_corpus.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["document_id", "path", "sha256", "page_count", "text_char_count", "likely_scanned_or_ocr_hostile", "image_object_count"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for doc in docs:
            writer.writerow({field: doc.get(field, "") for field in fields})
    zotero = [
        {
            "itemType": "document",
            "title": doc.get("title", ""),
            "attachments": [{"path": doc.get("path", ""), "sha256": doc.get("sha256", "")}],
            "extra": f"BEAST document arena id: {doc.get('document_id', '')}",
        }
        for doc in docs
    ]
    (packet_root / "zotero_items.json").write_text(json.dumps(zotero, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (packet_root / "gemini_vs_human_protocol.jsonl").open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps({
                "document_id": doc.get("document_id"),
                "gemini_vision_status": receipt["lanes"]["native_gemini_vision"]["status"],
                "human_inspection_status": receipt["lanes"]["blinded_human_inspection"]["status"],
                "required_fields": ["tables", "merged_headers", "footnotes", "statistical_notation", "chart_values", "uncertainty_notes"],
            }, sort_keys=True) + "\n")
    with (packet_root / "human_annotation_packet.jsonl").open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(_human_annotation_template(doc), sort_keys=True) + "\n")
    with (packet_root / "oracle_packet_template.jsonl").open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(_oracle_annotation_template(doc), sort_keys=True) + "\n")
    with (packet_root / "document_vision_adjudication.jsonl").open("w", encoding="utf-8") as fh:
        for item in receipt["vision_adjudication"]["document_receipts"]:
            fh.write(json.dumps(item, sort_keys=True) + "\n")
    with (packet_root / "document_vision_disagreements.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["document_id", "field", "oracle_field_present", "gemini_matches_oracle", "human_matches_oracle", "gemini_human_match"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in receipt["vision_adjudication"]["document_receipts"]:
            for field, agreement in item["field_agreement"].items():
                if not (agreement["oracle_field_present"] and agreement["gemini_matches_oracle"] and agreement["human_matches_oracle"] and agreement["gemini_human_match"]):
                    writer.writerow({"document_id": item["document_id"], "field": field, **agreement})


def _human_annotation_template(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_id": doc.get("document_id"),
        "observer_type": "blinded_human",
        "blinded": True,
        "saw_gemini_output": False,
        "saw_beast_answer": False,
        "source_visibility": "pdf_or_rendered_page_image_only",
        "source_digest": _preferred_source_digest(doc),
        "findings": _empty_structural_findings(),
        "uncertainty_notes": "",
    }


def _oracle_annotation_template(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_id": doc.get("document_id"),
        "oracle_type": "scientific_pdf_structural_truth",
        "frozen_before_scoring": True,
        "source_digest": _preferred_source_digest(doc),
        "findings": _empty_structural_findings(),
        "oracle_notes": "Fill from independent inspection before reading BEAST/Gemini outputs.",
    }


def _preferred_source_digest(doc: Mapping[str, Any]) -> str:
    first_page = doc.get("first_page_image")
    if isinstance(first_page, Mapping) and str(first_page.get("sha256") or "").startswith("sha256:"):
        return str(first_page["sha256"])
    return str(doc.get("sha256") or "")


def _empty_structural_findings() -> dict[str, Any]:
    return {
        "tables": [],
        "merged_headers": [],
        "footnotes": [],
        "statistical_notation": [],
        "chart_values": [],
    }


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{_file_sha256(path).removeprefix('sha256:')}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _run(command: list[str]) -> dict[str, str]:
    try:
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=30)
    except Exception as exc:
        return {"status": type(exc).__name__, "stdout": "", "stderr": str(exc)}
    return {
        "status": "ok" if completed.returncode == 0 else f"exit_{completed.returncode}",
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _load_optional_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_") or "document"


def _markdown(receipt: Mapping[str, Any]) -> str:
    gates = receipt["scorecard"]["certificate_gates"]
    lines = [
        f"# C4-X document truth arena · {receipt['run_id']}",
        "",
        f"- Receipt: `{receipt['receipt_digest']}`",
        f"- Real PDFs: `{receipt['scorecard']['real_pdf_count']}`",
        f"- Scanned/OCR-hostile candidates: `{receipt['scorecard']['scanned_or_ocr_hostile_count']}`",
        f"- Page images rendered: `{receipt['scorecard']['page_images_rendered']}`",
        f"- Gemini vs human ready: `{receipt['scorecard']['gemini_vs_human_ready']}`",
        f"- Independent oracle ready: `{receipt['scorecard']['independent_oracle_ready']}`",
        f"- Truth credit awarded: `{receipt['scorecard']['truth_credit_awarded']}`",
        "",
        "## Certificate gates",
        "",
    ]
    for name, passed in gates.items():
        lines.append(f"- `{name}`: `{passed}`")
    lines.extend([
        "",
        "## Documents",
        "",
    ])
    for doc in receipt["corpus"]:
        lines.append(
            f"- `{doc.get('document_id')}` pages={doc.get('page_count')} "
            f"chars={doc.get('text_char_count')} scanned={doc.get('likely_scanned_or_ocr_hostile')} "
            f"image={bool(doc.get('first_page_image'))}"
        )
    lines.extend(["", "## Boundary", "", str(receipt["claim_boundary"])])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the C4-X document/scientific-PDF frontier arena.")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--gemini-vision-sidecar", default=None)
    parser.add_argument("--human-annotation-sidecar", default=None)
    parser.add_argument("--oracle-sidecar", default=None)
    parser.add_argument("pdfs", nargs="*")
    args = parser.parse_args()
    receipt = run_document_truth_arena(
        corpus=tuple(args.pdfs) if args.pdfs else DEFAULT_CORPUS,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
        render_first_page=not args.no_render,
        gemini_vision_sidecar=args.gemini_vision_sidecar,
        human_annotation_sidecar=args.human_annotation_sidecar,
        oracle_sidecar=args.oracle_sidecar,
    )
    print(json.dumps({
        "evidence_root": receipt["evidence_root"],
        "receipt_digest": receipt["receipt_digest"],
        "real_pdf_count": receipt["scorecard"]["real_pdf_count"],
        "page_images_rendered": receipt["scorecard"]["page_images_rendered"],
        "truth_credit_awarded": receipt["scorecard"]["truth_credit_awarded"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
