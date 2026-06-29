#!/usr/bin/env python3
"""Promote nine benchmark Spaces through real, repeated local verifier proof.

The script is intentionally idempotent. A successful per-Space harness receipt
is reused unless ``--force-replay`` is supplied, preventing accidental match or
credit inflation from repeatedly running the grinder.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.commons_spaces import build_manifest, build_reduction_receipt, write_space
from scripts.live_commons_displacement_harness import run_displacement_harness


LATEST = ROOT / "benchmarks" / "results" / "commons_nine_space_promotion_latest.json"
CONTRACT_NAME = "live_verifier_contract.json"
VERIFIER_TEST = "tests/test_commons_promoted_space_verifiers.py"


def _read(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _harness_output(space_id: str) -> Path:
    return ROOT / "benchmarks" / "results" / f"live_commons_displacement_harness_{space_id}.json"


def _existing_success(space_id: str, manifest_hash: str) -> Dict[str, Any]:
    path = _harness_output(space_id)
    if not path.is_file():
        return {}
    try:
        receipt = _read(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if (
        receipt.get("success")
        and int((receipt.get("observed") or {}).get("repeated_matches") or 0) >= 3
        and (receipt.get("task_boundary") or {}).get("manifest_hash") == manifest_hash
    ):
        return receipt
    return {}


def _prepare_space(registry: CommonsSpaceRegistry, space_id: str) -> Dict[str, Any]:
    detail = registry.get(space_id)
    old_manifest = detail["manifest"]
    old_receipt = detail["reduction_receipt"]
    space_root = registry.root / space_id
    required = [str(item["path"]) for item in old_manifest.get("artifacts") or [] if item.get("path") != CONTRACT_NAME]
    integrity = _read(space_root / "integrity_manifest.json")
    archived = {str(item.get("path") or "") for item in integrity.get("files") or []}
    integrity_targets = sorted(path for path in required if path in archived)
    contract = {
        "beast_object_type": "commons_live_verifier_contract",
        "version": "1.0",
        "space_id": space_id,
        "workload_boundary": "local_benchmark_evidence_reuse",
        "required_artifacts": sorted(required),
        "integrity_targets": integrity_targets,
        "checks": [
            "manifest_artifact_hashes_and_sizes",
            "json_evidence_parseability",
            "archived_integrity_hashes",
            "definitive_benchmark_report_contract",
        ],
        "raw_private_data_required": False,
        "claim_boundary": (
            "This verifier proves repeatable local reuse of the published benchmark evidence. "
            "It does not re-run the original provider benchmark or claim production frequency."
        ),
    }
    (space_root / CONTRACT_NAME).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    artifacts = [
        {"path": str(item["path"]), "artifact_type": str(item.get("artifact_type") or "benchmark_evidence")}
        for item in old_manifest.get("artifacts") or []
        if item.get("path") != CONTRACT_NAME
    ]
    artifacts.append({"path": CONTRACT_NAME, "artifact_type": "live_verifier_contract"})
    command = f"python -m pytest {VERIFIER_TEST} -q -k {space_id}"
    manifest = build_manifest(
        space_root,
        space_id=space_id,
        name=str(old_manifest.get("name") or space_id),
        task_class="local_benchmark_evidence_reuse",
        artifacts=artifacts,
        hardware_profile={
            **(old_manifest.get("hardware_profile") or {}),
            "execution_class": "cpu_only_live_evidence_replay",
            "gpu_required": False,
        },
        verifier_bundles=[{
            "bundle_id": f"live_evidence_{space_id}",
            "commands": [command],
            "expected_returncode": 0,
            "artifact_scope": "space_local_hashed_benchmark_evidence",
        }],
        reduction_claims={
            "cloud_calls_avoided": 1,
            "cloud_calls_evidence": "local_route_policy_counterfactual",
            "tokens_avoided": None,
            "gpu_avoided": False,
            "capability_preserved": True,
        },
        safety={
            **(old_manifest.get("safety") or {}),
            "risk": "medium",
            "approval_required": True,
            "promotion_state": "approved_candidate",
            "adoption_mode": "advisory",
        },
        lineage={
            **(old_manifest.get("lineage") or {}),
            "promoted_from_manifest_hash": old_manifest.get("manifest_hash"),
            "proof_mode": "three_distinct_live_verifier_reproductions",
        },
        created_at=old_manifest.get("created_at"),
    )
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={
            **(old_receipt.get("baseline_route") or {}),
            "route_id": "uncrystallized_benchmark_evidence_reanalysis",
            "status": "would_require_probabilistic_reanalysis",
        },
        optimized_route={
            **(old_receipt.get("optimized_route") or {}),
            "route_id": "commons_local_benchmark_evidence_reuse",
            "provider": "local_beast_commons",
            "status": "live_verifier_ready",
            "provider_calls": 0,
            "cloud_provider_calls": 0,
        },
        displacement={
            "provider_calls_avoided": 1,
            "tokens_avoided": None,
            "latency_avoided_ms": None,
            "evidence_class": "lab_observed_replay_with_route_policy_counterfactual",
            "counterfactual": True,
            "notes": (
                "The local verifier execution is observed. One avoided probabilistic escalation is a "
                "route-policy counterfactual; it is not a metered production cloud call."
            ),
        },
        verifier={
            "passed": False,
            "returncode": None,
            "command": command,
            "latency_ms": None,
            "status": "pending_live_replay",
        },
        resource_deltas={
            "gpu_avoided": False,
            "measurement_status": "local_cpu_verifier_observed_other_resources_unknown",
        },
        provenance={
            **(old_receipt.get("provenance") or {}),
            "source_manifest_hash": old_manifest.get("manifest_hash"),
            "verifier_contract": CONTRACT_NAME,
        },
        rollback_available=False,
        approval_required=True,
        created_at=old_receipt.get("created_at"),
    )
    write_space(space_root, manifest, receipt)
    return {"manifest": manifest, "command": command, "old_receipt": old_receipt}


def _finalize_receipt(registry: CommonsSpaceRegistry, space_id: str, prepared: Dict[str, Any], harness: Dict[str, Any]) -> None:
    manifest = prepared["manifest"]
    receipt = registry.get(space_id)["reduction_receipt"]
    latencies = [
        float(command.get("latency_ms") or 0)
        for replay in harness.get("live_replays") or []
        for command in replay.get("commands") or []
    ]
    final = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route=receipt.get("baseline_route") or {},
        optimized_route={**(receipt.get("optimized_route") or {}), "status": "verified_local_reuse"},
        displacement=receipt.get("displacement") or {},
        verifier={
            "passed": bool(harness.get("success")),
            "returncode": 0 if harness.get("success") else 1,
            "command": prepared["command"],
            "latency_ms": round(sum(latencies), 3),
            "reproduction_ids": [item.get("reproduction_id") for item in harness.get("live_replays") or []],
        },
        resource_deltas=receipt.get("resource_deltas") or {},
        provenance={**(receipt.get("provenance") or {}), "harness_receipt_hash": harness.get("receipt_hash")},
        rollback_available=bool(receipt.get("rollback_available")),
        approval_required=True,
        created_at=receipt.get("created_at"),
    )
    write_space(registry.root / space_id, manifest, final)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote nine Commons Spaces through the 10x3 proof ladder")
    parser.add_argument("--count", type=int, default=9)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--force-replay", action="store_true")
    parser.add_argument("--output", default=str(LATEST))
    args = parser.parse_args()

    registry = CommonsSpaceRegistry()
    candidates = [
        str(item["space_id"])
        for item in registry.list_spaces().get("spaces") or []
        if item.get("valid") and str(item.get("space_id") or "").startswith("bench_")
    ][: max(1, int(args.count))]
    if len(candidates) < args.count:
        raise RuntimeError(f"requested {args.count} benchmark Spaces but found {len(candidates)}")

    rows: List[Dict[str, Any]] = []
    for space_id in candidates:
        current_manifest_hash = str(registry.get(space_id)["manifest"].get("manifest_hash") or "")
        existing = {} if args.force_replay else _existing_success(space_id, current_manifest_hash)
        if existing:
            rows.append({
                "space_id": space_id,
                "status": "existing_success_reused",
                "matches": int((existing.get("observed") or {}).get("repeated_matches") or 0),
                "live_replays": int((existing.get("observed") or {}).get("live_replay_attempts") or 0),
                "credit_id": (existing.get("credit_attempt") or {}).get("credit_id"),
                "receipt_path": str(_harness_output(space_id)),
            })
            continue
        prepared = _prepare_space(registry, space_id)
        harness = run_displacement_harness(
            space_id=space_id,
            target=ROOT,
            repeats=args.repeats,
            approved_by="commons_nine_space_promotion_grinder",
            reason="Approved local benchmark-evidence reuse after distinct live verifier reproductions.",
            output=_harness_output(space_id),
        )
        _finalize_receipt(registry, space_id, prepared, harness)
        rows.append({
            "space_id": space_id,
            "status": "promoted" if harness.get("success") else "failed",
            "matches": int((harness.get("observed") or {}).get("repeated_matches") or 0),
            "live_replays": int((harness.get("observed") or {}).get("live_replay_attempts") or 0),
            "credit_id": (harness.get("credit_attempt") or {}).get("credit_id"),
            "receipt_path": harness.get("receipt_path"),
        })

    result = {
        "beast_object_type": "commons_nine_space_promotion_receipt",
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_spaces": args.count,
        "repeats_per_space": args.repeats,
        "spaces": rows,
        "successful_spaces": sum(1 for item in rows if item.get("status") in {"promoted", "existing_success_reused"}),
        "observed_matches": sum(int(item.get("matches") or 0) for item in rows),
        "new_matches": sum(int(item.get("matches") or 0) for item in rows if item.get("status") == "promoted"),
        "claim_boundary": (
            "These are repeated local lab workload-boundary proofs. Production workload frequency and "
            "metered cloud savings remain unproven."
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
