#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.scientific_uplift_experiment import ScientificUpliftReceipt, UpliftTrial
from app.kernel.compute.compute_plane import ScientificPromotionGate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt")
    args = parser.parse_args()
    payload = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    payload["trials"] = tuple(UpliftTrial(**item) for item in payload["trials"])
    receipt = ScientificUpliftReceipt(**payload)
    receipt.validate()
    ScientificPromotionGate.require(receipt.promotion_evidence())
    print(json.dumps({
        "verified": receipt.verified, "receipt_digest": receipt.receipt_digest,
        "baseline_successes": receipt.baseline_successes,
        "assisted_successes": receipt.assisted_successes,
        "exact_mcnemar_p": receipt.exact_mcnemar_p,
        "provider_calls_avoided": receipt.provider_calls_avoided,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
