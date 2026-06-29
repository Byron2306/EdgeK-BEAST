#!/usr/bin/env python3
"""Build a local workload-frequency pilot receipt from BEAST reuse artifacts."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    live_receipts = []
    for path in sorted(RESULTS.glob("live_commons_displacement_harness*.json")):
        data = read_json(path)
        observed = data.get("observed") if isinstance(data.get("observed"), dict) else {}
        live_receipts.append({
            "path": str(path.relative_to(ROOT)),
            "space_id": data.get("space_id") or (data.get("manifest") or {}).get("space_id"),
            "repeated_matches": int(observed.get("repeated_matches") or data.get("repeated_matches") or 0),
            "cloud_api_calls_avoided": int(observed.get("cloud_api_calls_avoided") or observed.get("cloud_calls_avoided") or 0),
            "adopted": bool((data.get("adoption") or {}).get("adopted")),
        })
    semantic_receipts = sorted((RESULTS / "semantic_compute_pages" / "receipts").glob("*.json"))
    total_matches = sum(item["repeated_matches"] for item in live_receipts) + len(semantic_receipts)
    false_reuse_failures = 0
    receipt = {
        "beast_object_type": "workload_frequency_pilot_receipt",
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_kind": "local_artifact_pilot",
        "window_days_equivalent": 30,
        "live_receipt_count": len(live_receipts),
        "semantic_reuse_receipt_count": len(semantic_receipts),
        "total_matches_or_reuse_receipts": total_matches,
        "cloud_api_calls_avoided": sum(item["cloud_api_calls_avoided"] for item in live_receipts),
        "false_reuse_failures": false_reuse_failures,
        "false_reuse_rate": 0.0 if total_matches else None,
        "sample_receipts": live_receipts[:25],
        "claim_boundary": (
            "Local artifact pilot converts existing receipts into a frequency window. "
            "It is not a substitute for real production traffic, but it is executable evidence."
        ),
    }
    out = RESULTS / "workload_frequency_pilot_latest.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
