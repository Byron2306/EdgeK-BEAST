#!/usr/bin/env python3
"""Run Phase-6.5 formal hardening: SMT, ML-DSA and Byzantine model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.constitutional_formal_hardening import run_formal_hardening_demo


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--constitutional-receipt",
        type=Path,
        default=ROOT / "evidence/dai-diode/phase6-constitutional-extensions/dai_phase6_constitutional_extensions_receipt.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "evidence/dai-diode/phase6-formal-hardening/dai_phase6_formal_hardening_receipt.json",
    )
    args = parser.parse_args()

    receipt = run_formal_hardening_demo(constitutional_receipt=_read_json(args.constitutional_receipt))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    print(json.dumps({
        "beast_object_type": receipt["beast_object_type"],
        "green": receipt["green"],
        "formal_gates": receipt["formal_gates"],
        "hostile_controls": receipt["hostile_controls"],
        "phase6_4_constitutional_receipt_digest": receipt["phase6_4_constitutional_receipt_digest"],
        "z3_receipt_digest": receipt["z3_effect_containment_receipt"]["receipt_digest"],
        "hybrid_signature_packet_digest": receipt["hybrid_signature_packet"].packet_digest,
        "byzantine_model_receipt_digest": receipt["byzantine_commons_model_receipt"]["receipt_digest"],
        "receipt_digest": receipt["receipt_digest"],
        "out": str(args.out),
    }, indent=2, sort_keys=True))
    return 0 if receipt["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
