#!/usr/bin/env python3
"""Local Phase 6 durable-intelligence benchmark for Crystal Compute."""

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

from app.kernel.data_processing.semantic_raid import ArtifactFossilLayerStore, SemanticRaidStore

OUT = ROOT / "benchmarks" / "results"


def run() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="beast-phase6-durable-") as temp:
        root = Path(temp)
        raid = SemanticRaidStore(root / "semantic_raid")
        fossils = ArtifactFossilLayerStore(root / "fossils")
        shard = raid.store_shard(
            "promoted_crystal",
            {
                "capability_id": "cap:phase6_finale",
                "task_class": "code_generation",
                "promotion": {"clean_completion": 3, "rollback": 3, "friction": 0.05},
            },
            value_score=0.96,
        )
        fossils.checkpoint(
            "cap:phase6_finale",
            {"status": "candidate", "confidence": 0.82},
            decision="stage_candidate",
            evidence_ids=["ev-clean-1"],
        )
        fossils.checkpoint(
            "cap:phase6_finale",
            {"status": "promoted", "confidence": 0.94, "raid_shard_id": shard.shard_id},
            decision="promote",
            evidence_ids=["ev-clean-1", "ev-rollback-1", shard.shard_id],
        )

        before = raid.integrity_report()
        (raid.root / shard.primary_ref).write_text('{"corrupted": true}\n', encoding="utf-8")
        damaged = raid.integrity_report()
        reconstruction = raid.reconstruct()
        after = raid.integrity_report()
        replay = fossils.replay()
        gc = raid.garbage_collect(min_value_score=0.5)

    passed = bool(
        before["ok"]
        and not damaged["ok"]
        and reconstruction["ok"]
        and after["ok"]
        and replay["valid_lineage"]
        and replay["final_state"].get("status") == "promoted"
        and gc["retained"] == 1
    )
    return {
        "beast_object_type": "compute_governor_phase6_durable_intelligence",
        "version": "1.0",
        "semantic_raid": {
            "before_ok": before["ok"],
            "damaged_ok": damaged["ok"],
            "repaired_refs": reconstruction["repaired_refs"],
            "after_ok": after["ok"],
            "artifact_integrity_rate": after["artifact_integrity_rate"],
        },
        "fossil_replay": {
            "checkpoint_count": replay["checkpoint_count"],
            "valid_lineage": replay["valid_lineage"],
            "decisions": replay["decisions"],
            "final_status": replay["final_state"].get("status"),
            "replay_hash": replay["replay_hash"],
        },
        "garbage_collection": gc,
        "passed": passed,
        "claim_boundary": "Local benchmark proves redundant shard repair, deterministic promotion replay, and value-aware GC; distributed object-store replication remains future integration work.",
    }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase6_durable_intelligence.json"
    md_path = OUT / "compute_governor_phase6_durable_intelligence.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join([
        "# Compute Governor Phase 6 Durable Intelligence",
        "",
        f"- RAID before corruption OK: `{report['semantic_raid']['before_ok']}`",
        f"- RAID damaged OK: `{report['semantic_raid']['damaged_ok']}`",
        f"- RAID repaired refs: `{report['semantic_raid']['repaired_refs']}`",
        f"- RAID after repair OK: `{report['semantic_raid']['after_ok']}`",
        f"- Replay valid lineage: `{report['fossil_replay']['valid_lineage']}`",
        f"- Replay decisions: `{', '.join(report['fossil_replay']['decisions'])}`",
        f"- Final replay status: `{report['fossil_replay']['final_status']}`",
        f"- GC retained shards: `{report['garbage_collection']['retained']}`",
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
