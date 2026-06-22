#!/usr/bin/env python3
"""Collect Forge Node candidate proposals and promote centrally."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.capability_crystallization import CapabilityCrystallizationEngine
from app.kernel.compute_forge import CentralForgePromotionCollector


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def promote_from_fleet(forge_dir: Path, state_path: Path) -> Dict[str, Any]:
    engine = CapabilityCrystallizationEngine(storage_path=state_path)
    collector = CentralForgePromotionCollector(engine)
    results = []
    for snapshot_path in sorted(forge_dir.glob("*.json")) if forge_dir.is_dir() else []:
        snapshot = _load_json(snapshot_path)
        if snapshot.get("beast_object_type") != "forge_node_snapshot":
            continue
        result = collector.ingest_snapshot(snapshot)
        result["snapshot_path"] = str(snapshot_path)
        results.append(result)
    promoted: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for result in results:
        promoted.extend(result.get("promoted") or [])
        blocked.extend(result.get("blocked") or [])
    metrics = engine.update_metrics().to_dict()
    return {
        "beast_object_type": "forge_fleet_promotion_report",
        "version": "1.0",
        "forge_dir": str(forge_dir),
        "state_path": str(state_path),
        "snapshots_processed": len(results),
        "promoted": promoted,
        "blocked": blocked,
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-dir", default=str(ROOT / "data" / "forge_nodes"))
    parser.add_argument("--state", default=str(ROOT / "data" / "crystallization"))
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = promote_from_fleet(Path(args.forge_dir), Path(args.state))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
