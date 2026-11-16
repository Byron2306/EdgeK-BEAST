#!/usr/bin/env python3
"""Second chance for slow NIM providers: cold baselines with a 300 s timeout (DeepSeek v4.1-flash, gpt-oss-20b)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gauntlet_large as G  # noqa: E402


def main() -> int:
    os.environ.update(G.FLAGS)
    out = Path(G.ROOT / "evidence" / "gauntlet-2026-11-16-large")
    state = Path(G.ROOT / ".beast" / "gauntlets" / "2026-11-16-large-provider-retry")
    for cfg in G.PROVIDERS.values():
        cfg["timeout"] = 300
    g = G.Gauntlet(state, out, "", receipts="governor_receipts_provider_retry.jsonl")
    t0 = time.time()
    rows = {}
    for task in ("const-cold", "ren-cold"):
        rows[task] = G.h2h(g, task, ("deepseek", "gpt-oss"), "h2h-retry300")
    G.write(out, "provider_retry_long_timeout.json", {"started_at": t0, "timeout_s": 300, "rows": rows,
                                                       "model_calls": G.METER.calls, "governor_chain": g.governor.receipts.verify()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
