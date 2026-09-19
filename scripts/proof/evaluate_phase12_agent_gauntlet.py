#!/usr/bin/env python3
"""Assemble Phase 12 case receipts and emit a promotion decision."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.agents.phase12_gauntlet import evaluate_agent_gauntlet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", nargs="+", required=True, help="JSON case receipt files")
    parser.add_argument("--output", default="build/proof/BEAST_PHASE12_AGENT_GAUNTLET.json")
    args = parser.parse_args()
    cases = []
    sources = []
    for name in args.receipts:
        path = Path(name).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            cases.extend(payload)
        elif isinstance(payload.get("cases"), list):
            cases.extend(payload["cases"])
        else:
            cases.append(payload)
        sources.append(str(path))
    result = evaluate_agent_gauntlet(cases)
    result["receipt_sources"] = sources
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"PHASE12_PROOF={out}")
    return 0 if result["promotion_decision"] == "PROMOTE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
