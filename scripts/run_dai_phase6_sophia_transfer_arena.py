#!/usr/bin/env python3
"""Run the Phase-6.1 Sophia -> BEAST deterministic transfer arena."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.phase6_sophia_transfer_arena import (
    DEFAULT_SOPHIA_EXPORT,
    run_phase6_sophia_transfer_arena,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-path", type=Path, default=DEFAULT_SOPHIA_EXPORT)
    parser.add_argument("--freeze-seed", default="dai-phase6-1-sophia-transfer-freeze-2026-08-04")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json")
    args = parser.parse_args()
    receipt = run_phase6_sophia_transfer_arena(export_path=args.export_path, freeze_seed=args.freeze_seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "green": receipt["green"],
        "sophia_export_digest": receipt["sophia_export_digest"],
        "candidate_digest": receipt["candidate_digest"],
        "case_count": receipt["case_count"],
        "answerable_case_count": receipt["answerable_case_count"],
        "refusal_case_count": receipt["refusal_case_count"],
        "bounded_acquisition_calls_before_promotion": receipt["bounded_acquisition_calls_before_promotion"],
        "provider_calls_after_promotion": receipt["provider_calls_after_promotion"],
        "semantic_correct_count": receipt["semantic_correct_count"],
        "text_visual_joined_green_count": receipt["text_visual_joined_green_count"],
        "receipt_digest": receipt["receipt_digest"],
        "out": str(args.out),
    }, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
