#!/usr/bin/env python3
"""Summarize a held-out adapter comparison receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize BEAST held-out adapter comparison")
    parser.add_argument("receipt", nargs="?", default="benchmarks/results/adapter_comparison/heldout_adapter_comparison_latest.json")
    args = parser.parse_args()
    path = Path(args.receipt)
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for lane, summary in sorted((data.get("summary") or {}).items()):
        rows.append({
            "lane_id": lane,
            "statuses": summary.get("statuses") or [],
            "hidden_verifier_pass": summary.get("hidden_verifier_pass", 0),
            "schema_validity": summary.get("schema_validity", 0),
            "raw_json_parse_rate": summary.get("raw_json_parse_rate", 0),
            "required_verifier_present": summary.get("required_verifier_present", 0),
            "malformed_system_entries": summary.get("malformed_system_entries", 0),
            "malformed_verifier_entries": summary.get("malformed_verifier_entries", 0),
            "unsafe_action_attempts": summary.get("unsafe_action_attempts", 0),
            "avg_latency_ms": summary.get("avg_latency_ms", 0),
            "tokens_generated": summary.get("tokens_generated", 0),
        })
    failures = []
    for result in data.get("results") or []:
        metrics = result.get("metrics") or {}
        if not metrics.get("hidden_verifier_pass"):
            failures.append({
                "lane_id": result.get("lane_id"),
                "task_id": result.get("task_id"),
                "task_family": result.get("task_family"),
                "status": result.get("status"),
                "metrics": metrics,
                "parsed_preview": result.get("parsed"),
            })
    report = {
        "beast_object_type": "heldout_adapter_comparison_summary",
        "version": "1.0",
        "source": str(path),
        "live_ollama": data.get("live_ollama"),
        "promotion_rule": data.get("promotion_rule"),
        "promotion_verdict": data.get("promotion_verdict"),
        "lanes": rows,
        "first_failures": failures[:8],
        "claim_boundary": "summary_only_adapters_remain_proposal_only",
    }
    out = path.with_name("heldout_adapter_comparison_summary_latest.json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
