#!/usr/bin/env python3
"""Monitor Phase 2/3 rollout safety from compute receipts and evidence artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute_ledger import ComputeLedger


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _artifact_results(results_dir: Path) -> Dict[str, Any]:
    names = {
        "phase2_live_displacement": "compute_governor_phase2_live_displacement.json",
        "phase3_live_false_reuse": "compute_governor_phase3_live_false_reuse.json",
        "phase4_groq_routing": "compute_governor_phase4_groq_routing.json",
        "phase5_groq_streaming": "compute_governor_phase5_groq_streaming.json",
        "phase6_lifecycle": "compute_governor_phase6_lifecycle.json",
        "phase7_runtime_reuse": "compute_governor_phase7_runtime_reuse.json",
    }
    return {key: _load_json(results_dir / filename) for key, filename in names.items()}


def evaluate_rollout(
    *,
    ledger_path: str | None = None,
    results_dir: Path = ROOT / "benchmarks" / "results",
    limit: int = 500,
) -> Dict[str, Any]:
    ledger = ComputeLedger(ledger_path) if ledger_path else ComputeLedger()
    state = ledger.state()
    metrics = ledger.metrics(limit)
    receipts = ledger.recent_receipts(limit)
    artifacts = _artifact_results(results_dir)
    phase2_pass = bool(artifacts.get("phase2_live_displacement", {}).get("phase2_live_displacement_passed"))
    phase3_observed = bool(artifacts.get("phase3_live_false_reuse", {}).get("observed_false_reuse"))
    enforced_receipts = [
        item for item in receipts
        if item.get("mode") in {"phase2_enforce", "phase3_enforce", "phase4_enforce"}
        or item.get("gate_decision") in {"deterministic", "reuse", "require_approval", "local_inference"}
    ]
    false_reuse = [
        item for item in receipts
        if item.get("gate_decision") == "reuse" and item.get("behavior_preserved") is False
    ]
    provider_displaced = [
        item for item in receipts
        if item.get("provider_execution_requested") is False
        and item.get("gate_decision") in {"deterministic", "reuse", "local_inference"}
    ]
    redlines: List[str] = []
    if metrics.get("false_suppression_redline"):
        redlines.append("false_suppression_redline")
    if false_reuse:
        redlines.append("false_reuse_observed_in_receipts")
    readiness = "shadow_only"
    if phase2_pass and not redlines:
        readiness = "phase2_canary_ready"
    if phase2_pass and phase3_observed and not redlines:
        readiness = "phase2_phase3_monitored_canary_ready"
    return {
        "beast_object_type": "compute_rollout_monitor",
        "version": "1.0",
        "state": state,
        "metrics": metrics,
        "artifact_passes": {
            "phase2_live_displacement_passed": phase2_pass,
            "phase3_false_reuse_detection_observed": phase3_observed,
            "phase4_groq_routing_passed": bool(artifacts.get("phase4_groq_routing", {}).get("phase4_groq_routing_passed")),
            "phase5_groq_streaming_passed": bool(artifacts.get("phase5_groq_streaming", {}).get("phase5_groq_streaming_passed")),
            "phase6_lifecycle_passed": bool(artifacts.get("phase6_lifecycle", {}).get("phase6_lifecycle_passed")),
            "phase7_runtime_reuse_passed": bool(artifacts.get("phase7_runtime_reuse", {}).get("phase7_runtime_reuse_passed")),
        },
        "sample": {
            "receipts": len(receipts),
            "enforced_or_routed_receipts": len(enforced_receipts),
            "provider_calls_displaced": len(provider_displaced),
            "false_reuse_receipts": len(false_reuse),
        },
        "redlines": redlines,
        "readiness": readiness,
        "claim_boundary": "Rollout readiness is local evidence and receipt based; production canary still needs real workflow volume.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--results-dir", default=str(ROOT / "benchmarks" / "results"))
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    report = evaluate_rollout(ledger_path=args.ledger, results_dir=Path(args.results_dir), limit=args.limit)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report["redlines"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
