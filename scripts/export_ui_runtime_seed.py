#!/usr/bin/env python3
"""Export a tracked, JSON-only seed for BEAST TUI runtime panels."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cli.api import load_local_kv_cache_state
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder
from app.kernel.networking.commons_economy import ComputeReductionEconomy
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry


SAFE_SPACE_FILES = {
    "beast_space.json",
    "compute_reduction_receipt.json",
    "compute_reduction_receipt.md",
    "README.md",
    "integrity_manifest.json",
    "coverage_matrix.json",
    "live_verifier_contract.json",
    "provider_fitness.json",
    "cost_latency_summary.md",
    "failures_by_bucket.json",
    "run_manifest.json",
    "forge_candidate.json",
    "normalized_orchestration_plan.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export BEAST UI runtime seed")
    parser.add_argument("--output", default=str(ROOT / "seeds" / "ui_runtime"))
    parser.add_argument("--space-limit", type=int, default=100)
    parser.add_argument("--chronicle-limit", type=int, default=120)
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    registry = CommonsSpaceRegistry()
    economy = ComputeReductionEconomy(registry)
    ledger = ComputeLedger()
    chronicles = TaskEnvelopeBuilder().list_chronicles(limit=max(1, args.chronicle_limit))
    kv_state = load_local_kv_cache_state()

    commons_registry = registry.list_spaces()
    commons_economy = economy.state()
    compute_payload = {
        "beast_object_type": "beast_ui_compute_economy_seed",
        "version": "1.0",
        "state": ledger.state(),
        "metrics": ledger.metrics(500),
        "savings": ledger.savings_summary(2000),
        "recent_receipts": ledger.recent_receipts(50),
        "recent_plans": ledger.recent_plans(50),
        "counterfactual_summary": ledger.counterfactual_summary(),
        "escrow_summary": ledger.escrow_summary(),
    }
    kv_payload = {
        "beast_object_type": "beast_ui_kv_cache_seed",
        "version": "1.0",
        "state": kv_state,
        "ingest": {
            "beast_object_type": "meta_tool_commons_kv_cache_ingest",
            "source": "ui_runtime_seed",
            "prepared": int(kv_state.get("total_blocks") or 0),
            "accepted": int(kv_state.get("total_blocks") or 0),
            "duplicates": 0,
            "skipped": 0 if int(kv_state.get("total_blocks") or 0) else 1,
        },
    }

    _write_json(out / "compute_economy.json", compute_payload)
    _write_json(out / "kv_cache_state.json", kv_payload)
    _write_json(out / "chronicles.json", {
        "beast_object_type": "beast_ui_chronicle_seed",
        "version": "1.0",
        **chronicles,
    })
    _write_json(out / "commons_spaces_registry.json", {
        "beast_object_type": "beast_ui_commons_spaces_seed",
        "version": "1.0",
        "registry": commons_registry,
    })
    _write_json(out / "commons_economy.json", {
        "beast_object_type": "beast_ui_commons_economy_seed",
        "version": "1.0",
        "economy": commons_economy,
    })

    copied_spaces = copy_space_artifacts(registry.root, out / "commons_spaces", commons_registry.get("spaces") or [], args.space_limit)
    manifest = {
        "beast_object_type": "beast_ui_runtime_seed_manifest",
        "version": "1.0",
        "created_at_epoch": int(time.time()),
        "source_root": str(ROOT),
        "seed_scope": "ui_hydration_only_not_runtime_authority",
        "counts": {
            "commons_spaces": int(commons_registry.get("count") or 0),
            "copied_space_artifacts": copied_spaces,
            "commons_credits": int(commons_economy.get("credit_count") or 0),
            "compute_receipts": int(compute_payload["state"].get("receipts") or 0),
            "compute_metric_samples": int(compute_payload["metrics"].get("sample_size") or 0),
            "chronicles": int(chronicles.get("count") or len(chronicles.get("chronicles") or [])),
            "kv_blocks": int(kv_state.get("total_blocks") or 0),
        },
        "files": [
            "manifest.json",
            "compute_economy.json",
            "kv_cache_state.json",
            "chronicles.json",
            "commons_spaces_registry.json",
            "commons_economy.json",
            "commons_spaces/",
        ],
    }
    _write_json(out / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def copy_space_artifacts(source_root: Path, target_root: Path, spaces: Iterable[Dict[str, Any]], limit: int) -> int:
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    copied = 0
    for row in list(spaces)[: max(1, limit)]:
        space_id = str(row.get("space_id") or "").strip()
        if not space_id:
            continue
        src = source_root / space_id
        dst = target_root / space_id
        if not src.is_dir():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for name in SAFE_SPACE_FILES:
            source_file = src / name
            if source_file.is_file():
                shutil.copy2(source_file, dst / name)
        copied += 1
    return copied


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
