#!/usr/bin/env python3
"""Run the Phase-6 deterministic intelligence arena."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.phase6_deterministic_arena import run_phase6_arena


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-seed", default="dai-phase6-freeze-2026-08-04")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase6-deterministic-arena/dai_phase6_deterministic_arena_receipt.json")
    args = parser.parse_args()
    receipt = run_phase6_arena(freeze_seed=args.freeze_seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "green": receipt["green"],
        "case_count": receipt["case_count"],
        "family_count": receipt["family_count"],
        "provider_calls_before_promotion": receipt["provider_calls_before_promotion"],
        "provider_calls_after_promotion": receipt["provider_calls_after_promotion"],
        "provider_call_displacement": receipt["provider_call_displacement"],
        "semantic_correct_count": receipt["semantic_correct_count"],
        "text_visual_joined_green_count": receipt["text_visual_joined_green_count"],
        "receipt_digest": receipt["receipt_digest"],
        "out": str(args.out),
    }, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
