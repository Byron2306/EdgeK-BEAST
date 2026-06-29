#!/usr/bin/env python3
"""Local Phase 5 temporal fork and annealing benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_forks import TemporalCrystalForkManager

OUT = ROOT / "benchmarks" / "results"


def run() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="beast-phase5-forks-") as temp:
        manager = TemporalCrystalForkManager(Path(temp) / "forks.json")
        stable = manager.create_fork("cap:stable", "code", channel="stable", traffic_share=1.0, confidence=0.95)
        candidate = manager.create_fork("cap:candidate", "code", channel="candidate", traffic_share=0.9)
        experimental = manager.create_fork("cap:experimental", "code", channel="experimental", traffic_share=0.9)
        for _ in range(3):
            candidate = manager.record_outcome(
                candidate.fork_id,
                clean_completion=True,
                rollback_success=True,
                friction_score=0.05,
                cost_usd=0.001,
            )
        rolled = manager.record_outcome(
            experimental.fork_id,
            clean_completion=False,
            rollback_success=True,
            friction_score=0.9,
            cost_usd=0.002,
        )
        promoted = manager.promote(candidate.fork_id, approved_by="phase5_benchmark")

        duplicate_a = manager.create_fork("cap:dup", "code", channel="candidate", confidence=0.8)
        manager.create_fork("cap:dup", "code", channel="candidate", confidence=0.7)
        multimodal = manager.create_fork("cap:multi", "code", channel="candidate", confidence=0.8)
        stale = manager.create_fork("cap:stale", "code", channel="candidate", confidence=0.2)
        for _ in range(2):
            manager.record_outcome(multimodal.fork_id, clean_completion=True, friction_score=0.1)
            manager.record_outcome(multimodal.fork_id, clean_completion=False, friction_score=0.9)
        for _ in range(3):
            manager.record_outcome(stale.fork_id, clean_completion=False, friction_score=0.9)
        anneal = manager.anneal()
        state = manager.state()
        stable_after = next(item for item in state["forks"] if item["fork_id"] == stable.fork_id)
        passed = bool(
            candidate.traffic_share <= 0.25
            and experimental.traffic_share <= 0.05
            and rolled.state == "rolled_back"
            and stable_after["traffic_share"] == 1.0
            and promoted.channel == "stable"
            and anneal["merged_duplicates"] >= 1
            and anneal["split_multimodal"] >= 1
            and anneal["retired_stale"] >= 1
        )
        return {
            "beast_object_type": "compute_governor_phase5_temporal_forks",
            "version": "1.0",
            "candidate_traffic_share": candidate.traffic_share,
            "experimental_traffic_share": experimental.traffic_share,
            "experimental_state_after_failure": rolled.state,
            "stable_traffic_after_experiment": stable_after["traffic_share"],
            "promoted_channel": promoted.channel,
            "annealing": anneal,
            "fork_state": {
                "channels": state["channels"],
                "states": state["states"],
            },
            "passed": passed,
            "claim_boundary": "Local benchmark proves bounded temporal channels, rollback isolation, promotion gating, and annealing operations; production rollout remains approval/policy gated.",
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase5_temporal_forks.json"
    md_path = OUT / "compute_governor_phase5_temporal_forks.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 5 Temporal Forks",
        "",
        f"- Candidate traffic share: `{report['candidate_traffic_share']}`",
        f"- Experimental traffic share: `{report['experimental_traffic_share']}`",
        f"- Experimental state after failure: `{report['experimental_state_after_failure']}`",
        f"- Stable traffic after experiment: `{report['stable_traffic_after_experiment']}`",
        f"- Promoted channel: `{report['promoted_channel']}`",
        f"- Merged duplicates: `{report['annealing']['merged_duplicates']}`",
        f"- Split multimodal: `{report['annealing']['split_multimodal']}`",
        f"- Retired stale: `{report['annealing']['retired_stale']}`",
        f"- Result: `{'PASS' if report['passed'] else 'FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        str(report["claim_boundary"]),
        "",
    ]), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = run()
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
