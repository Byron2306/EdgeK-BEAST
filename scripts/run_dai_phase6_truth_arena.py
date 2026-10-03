#!/usr/bin/env python3
"""Run the Phase-6.2 mixed-capability Truth Arena."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.capability_ledger import build_phase6_capability_ledger, write_capability_ledger
from app.kernel.dai.phase6_truth_arena import run_phase6_truth_arena


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart-receipt", type=Path, default=ROOT / "evidence/dai-diode/phase6-deterministic-arena/dai_phase6_deterministic_arena_receipt.json")
    parser.add_argument("--sophia-receipt", type=Path, default=ROOT / "evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json")
    parser.add_argument("--freeze-seed", default="dai-phase6-2-truth-arena-freeze-2026-08-04")
    parser.add_argument("--include-rds-rag", action="store_true", help="Run the configured RDS/Aurora pgvector RAG adapter as an optional baseline.")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json")
    parser.add_argument("--ledger-out", type=Path, default=ROOT / "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json")
    args = parser.parse_args()

    ledger = build_phase6_capability_ledger(
        restart_arena_receipt=_read_json(args.restart_receipt),
        sophia_transfer_receipt=_read_json(args.sophia_receipt),
    )
    rds_runner = None
    if args.include_rds_rag:
        from scripts.run_c4x_rds_rag_adapter import run_rds_rag

        rds_runner = run_rds_rag
    receipt = run_phase6_truth_arena(ledger=ledger, freeze_seed=args.freeze_seed, rds_rag_runner=rds_runner)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    write_capability_ledger(args.ledger_out, ledger)
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "green": receipt["green"],
        "ledger_digest": receipt["ledger_digest"],
        "case_count": receipt["case_count"],
        "mixed_capability_cases": receipt["mixed_capability_cases"],
        "answerable_case_count": receipt["answerable_case_count"],
        "refusal_case_count": receipt["refusal_case_count"],
        "semantic_correct_count": receipt["semantic_correct_count"],
        "text_visual_joined_green_count": receipt["text_visual_joined_green_count"],
        "visual_proposition_coverage_count": receipt["visual_proposition_coverage_count"],
        "provider_calls_after_ledger": receipt["provider_calls_after_ledger"],
        "rds_rag_enabled": receipt["baseline_report"]["rds_rag_enabled"],
        "receipt_digest": receipt["receipt_digest"],
        "out": str(args.out),
        "ledger_out": str(args.ledger_out),
    }, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
