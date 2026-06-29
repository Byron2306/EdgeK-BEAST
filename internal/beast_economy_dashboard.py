#!/usr/bin/env python3
"""One-command BEAST economy status across compute phases, Forge, and storage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.capability.capability_crystallization import CapabilityCrystallizationEngine
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from scripts.compute_rollout_monitor import evaluate_rollout


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _forge_snapshots(path: Path) -> List[Dict[str, Any]]:
    if not path.is_dir():
        return []
    snapshots = []
    for item in sorted(path.glob("*.json")):
        payload = _load_json(item)
        if payload.get("beast_object_type") == "forge_node_snapshot":
            snapshots.append(payload)
    return snapshots


def _json_files(path: Path) -> List[Path]:
    return sorted(path.glob("*.json")) if path.is_dir() else []


def _count_crystallize_events(path: Path) -> int:
    total = 0
    for item in _json_files(path):
        payload = _load_json(item)
        text = json.dumps(payload).lower() if payload else ""
        if "crystallize" in text or "crystallized" in text or "promotion_candidate" in text:
            total += 1
    return total


def _artifact_passed(value: Dict[str, Any]) -> bool:
    if not value:
        return False
    if any(bool(value.get(name)) for name in value if name.endswith("_passed")):
        return True
    for key in ("passed", "success", "ok", "all_behavior_preserved"):
        if value.get(key) is True:
            return True
    result = str(value.get("result") or value.get("status") or "").strip().lower()
    return result in {"pass", "passed", "success", "succeeded"}


def build_dashboard(
    *,
    ledger_path: str | None = None,
    results_dir: Path = ROOT / "benchmarks" / "results",
    forge_dir: Path = ROOT / "data" / "forge_nodes",
    storage_dir: Path = ROOT / "data" / "durable_inference",
    crystallization_state: Path = ROOT / "data" / "crystallization",
) -> Dict[str, Any]:
    ledger = ComputeLedger(ledger_path) if ledger_path else ComputeLedger()
    rollout = evaluate_rollout(ledger_path=ledger_path, results_dir=results_dir)
    storage = DurableInferenceStorage(storage_dir)
    crystallization = CapabilityCrystallizationEngine(storage_path=crystallization_state)
    forge = _forge_snapshots(forge_dir)
    promotion_candidate_files = _json_files(ROOT / "data" / "promotion_candidates")
    evidence_chronicle_dir = ROOT / "data" / "evidence_chronicles"
    forge_totals = {
        "nodes": len(forge),
        "tokens_displaced": 0,
        "candidates_produced": 0,
        "work_items": 0,
    }
    for snapshot in forge:
        profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
        credits = snapshot.get("credits") if isinstance(snapshot.get("credits"), dict) else {}
        forge_totals["tokens_displaced"] += int(profile.get("total_tokens_displaced") or 0)
        forge_totals["candidates_produced"] += int(profile.get("total_candidates_produced") or 0)
        forge_totals["work_items"] += int(credits.get("total_work_items") or 0)
    phase_artifacts = {
        "phase1": _load_json(results_dir / "compute_governor_phase1_shadow.json"),
        "phase2": _load_json(results_dir / "compute_governor_phase2_live_displacement.json"),
        "phase3": _load_json(results_dir / "compute_governor_phase3_live_false_reuse.json"),
        "phase4": _load_json(results_dir / "compute_governor_phase4_groq_routing.json"),
        "phase5": _load_json(results_dir / "compute_governor_phase5_groq_streaming.json"),
        "phase6": _load_json(results_dir / "compute_governor_phase6_lifecycle.json"),
        "phase7": _load_json(results_dir / "compute_governor_phase7_runtime_reuse.json"),
    }
    crystal_metrics = crystallization.to_dict().get("metrics", {})
    crystallization_observed = {
        "promoted_count": int(crystal_metrics.get("promoted_count") or 0),
        "engine_candidates": int(crystal_metrics.get("total_candidates") or 0),
        "promotion_candidate_files": len(promotion_candidate_files),
        "evidence_crystallize_events": _count_crystallize_events(evidence_chronicle_dir),
        "promotion_candidate_dir": str(ROOT / "data" / "promotion_candidates"),
        "evidence_chronicle_dir": str(evidence_chronicle_dir),
    }

    crystallization_observed["observed_total"] = (
        crystallization_observed["promoted_count"]
        + crystallization_observed["promotion_candidate_files"]
        + crystallization_observed["evidence_crystallize_events"]
    )

    # NEW: Ingest FSM lattice
    fsm_lattice = _load_json(ROOT / "data" / "fsm_lattice.json")
    fsm_summary = {
        "node_count": len(fsm_lattice.get("transitions", {})),
        "status": "deterministic_locked" if fsm_lattice else "uninitialized"
    }

    return {
        "beast_object_type": "beast_unified_economy_dashboard",
        "version": "1.1",
        "rollout": rollout,
        "fsm": fsm_summary,
        "compute": {
            "state": ledger.get_state(),
            "metrics": ledger.metrics(500),
            "savings": {}, # Placeholder
        },
        "storage": storage.get_metrics(),
        "crystallization": {
            **crystal_metrics,
            "observed": crystallization_observed,
        },
        "forge": {
            "directory": str(forge_dir),
            "totals": forge_totals,
            "nodes": forge,
        },
        "phase_artifacts": {
            key: {
                "present": bool(value),
                "passed": _artifact_passed(value),
            }
            for key, value in phase_artifacts.items()
        },
    }



def print_human(report: Dict[str, Any]) -> None:
    rollout = report["rollout"]
    compute = report["compute"]["metrics"]
    forge = report["forge"]["totals"]
    storage = report["storage"]
    crystal = report["crystallization"]
    print("BEAST Unified Economy Dashboard")
    print("=" * 36)
    print(f"Rollout readiness      : {rollout['readiness']}")
    print(f"Redlines               : {', '.join(rollout['redlines']) or 'none'}")
    print(f"Receipts               : {compute.get('sample_size', 0)}")
    print(f"Observed tokens        : {compute.get('observed_total_tokens', 0)}")
    print(f"Stream tokens saved    : {compute.get('stream_tokens_saved', 0)}")
    print(f"FSM State              : {report['fsm']['status']} ({report['fsm']['node_count']} nodes)")
    print(f"Forge nodes            : {forge['nodes']}")
    print(f"Forge work items       : {forge['work_items']}")
    print(f"Forge tokens displaced : {forge['tokens_displaced']}")
    print(f"Storage active credits : {storage.get('active_credits', 0)}")
    print(f"Measured reuse saved   : {storage.get('measured_reuse_tokens_saved', 0)}")
    print(f"Crystallized promoted  : {crystal.get('promoted_count', 0)}")
    print("")
    print("Phase artifacts")
    for phase, status in report["phase_artifacts"].items():
        print(f"  {phase:7} present={str(status['present']):5} passed={status['passed']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human summary")
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--results-dir", default=str(ROOT / "benchmarks" / "results"))
    parser.add_argument("--forge-dir", default=str(ROOT / "data" / "forge_nodes"))
    parser.add_argument("--storage-dir", default=str(ROOT / "data" / "durable_inference"))
    parser.add_argument("--crystallization-state", default=str(ROOT / "data" / "crystallization"))
    args = parser.parse_args()
    report = build_dashboard(
        ledger_path=args.ledger,
        results_dir=Path(args.results_dir),
        forge_dir=Path(args.forge_dir),
        storage_dir=Path(args.storage_dir),
        crystallization_state=Path(args.crystallization_state),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if not report["rollout"]["redlines"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
