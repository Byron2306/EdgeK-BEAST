#!/usr/bin/env python3
"""Aggregate PGEC 450 batch artifacts and produce claim-bounded descriptive analysis."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def load_rows(root: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    registrations: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("controlled_observations.jsonl")):
        registration_path = path.parent / "pgec_registration.json"
        registration = json.loads(registration_path.read_text()) if registration_path.exists() else {}
        if registration:
            registrations.append(registration)
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row["_source"] = str(path)
                row["_classification"] = registration.get("classification", "unknown")
                rows.append(row)
    return rows, registrations


def boolish(row: Dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if key in row:
            return bool(row.get(key))
    return False


def number(row: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> Tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    den = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / den
    return max(0.0, centre - margin), min(1.0, centre + margin)


def exact_sign_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = max(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    return min(1.0, tail if wins != losses else 1.0)


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    confirmatory = [r for r in rows if r.get("_classification") == "confirmatory"]
    cells = {(r.get("family"), r.get("provider"), r.get("occurrence"), r.get("lane")) for r in confirmatory}
    by_lane: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_provider: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in confirmatory:
        by_lane[str(row.get("lane"))].append(row)
        by_provider[str(row.get("provider"))].append(row)

    def lane_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(items)
        verified = sum(boolish(r, "verified", "completed", "verification_passed") for r in items)
        hidden = sum(boolish(r, "hidden_passed", "hidden_pass", "hidden_verified") for r in items)
        false_reuse = sum(boolish(r, "false_reuse", "observed_false_reuse") for r in items)
        provider_calls = sum(number(r, "provider_calls", "cloud_calls") for r in items)
        lo, hi = wilson(verified, n)
        return {
            "n": n,
            "verified": verified,
            "verified_rate": verified / n if n else 0.0,
            "verified_wilson95": [lo, hi],
            "hidden_passes": hidden,
            "false_reuse": false_reuse,
            "provider_calls": provider_calls,
        }

    return {
        "beast_object_type": "pgec_450_analysis_summary",
        "version": "1.0",
        "confirmatory_rows": len(confirmatory),
        "unique_confirmatory_cells": len(cells),
        "expected_cells": 450,
        "matrix_complete": len(cells) == 450,
        "duplicate_confirmatory_rows": len(confirmatory) - len(cells),
        "lane_summary": {k: lane_summary(v) for k, v in sorted(by_lane.items())},
        "provider_summary": {k: lane_summary(v) for k, v in sorted(by_provider.items())},
        "claim_boundary": "Descriptive output is valid for available sealed confirmatory cells. Confirmatory inferential claims require a complete matrix or explicitly complete paired subsets.",
    }


def write_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    rows = list(rows)
    keys = sorted({key for row in rows for key in row if not key.startswith("_")})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.input)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows, registrations = load_rows(source)
    summary = summarize(rows)
    write_csv(output / "observations.csv", rows)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "registrations.json").write_text(json.dumps(registrations, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
