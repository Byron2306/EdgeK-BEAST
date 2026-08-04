import hashlib
import json
from pathlib import Path

from benchmarks.c4x_document_truth_arena import run_document_truth_arena
from benchmarks.c4x_freeze_identities import freeze_identities


def test_freeze_identities_writes_core_and_truth_stack_receipt(tmp_path: Path):
    receipt = freeze_identities(evidence_root=tmp_path, run_id="pytest-freeze")

    assert receipt["beast_object_type"] == "c4x_freeze_identity_receipt"
    assert receipt["identities"]["c4x-core-v1.0"]["all_files_present"] is True
    assert receipt["identities"]["c4x-core-v1.0"]["identity_digest"].startswith("sha256:")
    assert "truth" in receipt["certificate_contract"]
    assert (tmp_path / "pytest-freeze" / "freeze_identities.json").is_file()
    assert (tmp_path / "pytest-freeze" / "freeze_identities.md").is_file()


def test_document_truth_arena_exports_real_pdf_audit_packets(tmp_path: Path):
    pdf = Path("docs/external/obsidian-beast/Blurred Text Extraction Limitations.pdf")
    receipt = run_document_truth_arena(
        corpus=(pdf,),
        evidence_root=tmp_path,
        run_id="pytest-document-arena",
        render_first_page=True,
    )
    root = tmp_path / "pytest-document-arena"

    assert receipt["beast_object_type"] == "c4x_document_truth_arena"
    assert receipt["scorecard"]["real_pdf_count"] == 1
    assert receipt["scorecard"]["truth_credit_awarded"] is False
    assert receipt["corpus"][0]["sha256"].startswith("sha256:")
    assert receipt["corpus"][0]["first_page_image"]["status"] == "ok"
    assert (root / "audit_packets" / "document_corpus.jsonl").is_file()
    assert (root / "audit_packets" / "document_corpus.csv").is_file()
    assert (root / "audit_packets" / "zotero_items.json").is_file()
    assert (root / "audit_packets" / "gemini_vs_human_protocol.jsonl").is_file()
    assert (root / "audit_packets" / "human_annotation_packet.jsonl").is_file()
    assert (root / "audit_packets" / "oracle_packet_template.jsonl").is_file()
    assert (root / "audit_packets" / "document_vision_adjudication.jsonl").is_file()
    assert (root / "audit_packets" / "document_vision_disagreements.csv").is_file()
    assert (root / "SHA256SUMS.txt").is_file()


def test_document_truth_arena_awards_credit_only_with_independent_matching_sidecars(tmp_path: Path):
    pdf = Path("docs/external/obsidian-beast/Blurred Text Extraction Limitations.pdf")
    doc_digest = "sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    doc_id = "blurred_text_extraction_limitations"
    findings = {
        "tables": [{"id": "t1", "caption": "extraction limitations matrix"}],
        "merged_headers": [{"table_id": "t1", "headers": ["condition", "observed failure mode"]}],
        "footnotes": [{"marker": "*", "text": "ocr confidence can drop under blur"}],
        "statistical_notation": [{"token": "p < .05", "meaning": "example significance threshold"}],
        "chart_values": [{"chart_id": "c1", "series": [{"label": "ocr", "values": [0.81, 0.42]}]}],
    }
    gemini = tmp_path / "gemini.jsonl"
    human = tmp_path / "human.jsonl"
    oracle = tmp_path / "oracle.jsonl"
    _write_jsonl(
        gemini,
        [
            {
                "document_id": doc_id,
                "observer_type": "gemini_native_vision",
                "source_mode": "native_pdf_or_page_image_vision",
                "source_digest": doc_digest,
                "raw_text_answer_used": False,
                "live_execution": True,
                "provider_calls_used": 1,
                "model": "gemini-test-vision",
                "request_digest": "sha256:" + "1" * 64,
                "raw_response_digest": "sha256:" + "2" * 64,
                "findings": findings,
            }
        ],
    )
    _write_jsonl(
        human,
        [
            {
                "document_id": doc_id,
                "observer_type": "blinded_human",
                "blinded": True,
                "saw_gemini_output": False,
                "saw_beast_answer": False,
                "source_digest": doc_digest,
                "findings": findings,
            }
        ],
    )
    _write_jsonl(
        oracle,
        [
            {
                "document_id": doc_id,
                "oracle_type": "scientific_pdf_structural_truth",
                "frozen_before_scoring": True,
                "source_digest": doc_digest,
                "findings": findings,
            }
        ],
    )

    receipt = run_document_truth_arena(
        corpus=(pdf,),
        evidence_root=tmp_path,
        run_id="pytest-document-arena-sidecars",
        gemini_vision_sidecar=gemini,
        human_annotation_sidecar=human,
        oracle_sidecar=oracle,
    )

    assert receipt["scorecard"]["truth_credit_awarded"] is True
    assert all(receipt["scorecard"]["certificate_gates"].values())
    assert receipt["vision_adjudication"]["document_receipts"][0]["passed"] is True


def test_document_truth_arena_refuses_text_answer_derived_gemini_sidecar(tmp_path: Path):
    pdf = Path("docs/external/obsidian-beast/Blurred Text Extraction Limitations.pdf")
    doc_digest = "sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    doc_id = "blurred_text_extraction_limitations"
    findings = {
        "tables": [],
        "merged_headers": [],
        "footnotes": [],
        "statistical_notation": [],
        "chart_values": [],
    }
    gemini = tmp_path / "gemini_bad.jsonl"
    human = tmp_path / "human_ok.jsonl"
    oracle = tmp_path / "oracle_ok.jsonl"
    _write_jsonl(
        gemini,
        [
            {
                "document_id": doc_id,
                "observer_type": "gemini_native_vision",
                "source_mode": "native_pdf_or_page_image_vision",
                "source_digest": doc_digest,
                "raw_text_answer_used": True,
                "live_execution": True,
                "provider_calls_used": 1,
                "model": "gemini-test-vision",
                "request_digest": "sha256:" + "3" * 64,
                "raw_response_digest": "sha256:" + "4" * 64,
                "findings": findings,
            }
        ],
    )
    _write_jsonl(
        human,
        [{"document_id": doc_id, "observer_type": "blinded_human", "blinded": True, "source_digest": doc_digest, "findings": findings}],
    )
    _write_jsonl(
        oracle,
        [{"document_id": doc_id, "oracle_type": "scientific_pdf_structural_truth", "source_digest": doc_digest, "findings": findings}],
    )

    receipt = run_document_truth_arena(
        corpus=(pdf,),
        evidence_root=tmp_path,
        run_id="pytest-document-arena-refusal",
        gemini_vision_sidecar=gemini,
        human_annotation_sidecar=human,
        oracle_sidecar=oracle,
    )

    assert receipt["scorecard"]["truth_credit_awarded"] is False
    assert receipt["scorecard"]["certificate_gates"]["no_text_answer_generation"] is False
    assert "gemini_native_vision_independent" in receipt["vision_adjudication"]["document_receipts"][0]["failure_reasons"]


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
