#!/usr/bin/env python3
"""Run Phase-6.4 DIO Constitutional Extensions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.constitutional_extensions import run_constitutional_extensions_demo


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase6-2-truth",
        type=Path,
        default=ROOT / "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json",
    )
    parser.add_argument(
        "--lineage-policy-verification",
        type=Path,
        default=ROOT / "evidence/dai-diode/phase6-sophia-integritas-lineage/sophia_integritas_project_key_policy_verification.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evidence/dai-diode/phase6-constitutional-extensions/dai_phase6_constitutional_extensions_receipt.json",
    )
    args = parser.parse_args()

    receipt = run_constitutional_extensions_demo(
        phase6_2_truth_receipt=_read_json(args.phase6_2_truth),
        lineage_policy_verification=_read_json(args.lineage_policy_verification),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "green": receipt["green"],
        "extension_gates": receipt["extension_gates"],
        "hostile_controls": receipt["hostile_controls"],
        "phase6_2_truth_receipt_digest": receipt["phase6_2_truth_receipt_digest"],
        "lineage_policy_digest": receipt["lineage_policy_digest"],
        "receipt_digest": receipt["receipt_digest"],
        "out": str(args.out),
        "deferred_extensions_not_claimed_green": receipt["deferred_extensions_not_claimed_green"],
    }, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
