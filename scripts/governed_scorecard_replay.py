#!/usr/bin/env python3
"""Rebuild .beast/governed-interception/capability_scorecard.json by replaying every proof call in time order.

Used after the scorecard learned to keep liveness smoke probes out of the "*" aggregate. No model calls.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.kernel.compute.capability_scorecard import CapabilityScorecard  # noqa: E402

EV = ROOT / "evidence" / "governed-interception-2026-11-16"
PATTERNS = ["live/routed-*.json", "live/h2h-*.json", "live/hard-*.json", "tgi/tgi-solo-*.json", "tgi/tgi-routed-*.json",
            "tgi/hf-smoke-2*.json", "tgi/hf-smoke-retry-*.json", "providers/provider-smoke-*.json", "providers/provider-hard-*.json"]
SKIP = {"skipped_circuit_open", "refused_governor"}


def stamp(p: str) -> str:
    m = re.search(r"(\d{8}T\d{6})", p)
    return m.group(1) if m else "0"


def main() -> int:
    files = sorted({f for pat in PATTERNS for f in glob.glob(str(EV / pat))}, key=stamp)
    out = ROOT / ".beast" / "governed-interception" / "capability_scorecard.json"
    out.unlink(missing_ok=True)
    sc = CapabilityScorecard(out)
    n = 0
    for f in files:
        for row in json.loads(Path(f).read_text()):
            if "calls" in row:  # task rows
                fam = row.get("family") or "unknown"
                calls = row["calls"]
            else:  # smoke rows
                fam, calls = "smoke-tiny", [{**row, "provider": row.get("provider") or "hf", "model": row["route"],
                                             "placement": "cloud", "passed": row["accepted"]}]
            for c in calls:
                if c.get("status") in SKIP:
                    continue
                st = c.get("status")
                kind = "transport_error" if st == "transport_error" else ("http_error" if st == "http_error" else "")
                sc.record(provider=c["provider"], model=c["model"], family=fam, placement=c.get("placement") or "cloud",
                          passed=bool(c.get("passed")), json_valid=bool(c.get("json_valid")),
                          tokens=int((c.get("tokens_prompt") or 0) + (c.get("tokens_completion") or 0)),
                          latency_ms=float(c.get("latency_ms") or 0), spend_usd=float(c.get("spend_usd") or 0), failure_kind=kind)
                n += 1
    print(json.dumps({"files": [str(Path(f).relative_to(EV)) for f in files], "calls_replayed": n, "cells": len(sc.snapshot()["cells"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
