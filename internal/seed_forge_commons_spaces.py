#!/usr/bin/env python3
"""Package Forge candidate metadata as quarantined Commons hypotheses.

This grows corpus breadth without claiming live reproduction or displacement.
Promotion still requires a real verifier bundle, replay, approval, and receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.commons_spaces import build_manifest, build_reduction_receipt, validate_manifest, write_space


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")[:72] or "candidate"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Forge candidates until the Commons corpus target is reached")
    parser.add_argument("--snapshot", default=str(ROOT / "data/forge_nodes/local_cpu_forge_commons.json"))
    parser.add_argument("--target-spaces", type=int, default=100)
    parser.add_argument("--output", default=str(ROOT / "benchmarks/results/forge_commons_seed_latest.json"))
    args = parser.parse_args()

    registry = CommonsSpaceRegistry()
    snapshot_path = Path(args.snapshot)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    feed = snapshot.get("commons_candidate_feed") or {}
    snapshot_hash = "sha256:" + hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    rows = []
    for candidate in feed.get("candidates") or []:
        if registry.list_spaces()["count"] >= max(1, args.target_spaces):
            break
        artifact_id = str(candidate.get("artifact_id") or candidate.get("name") or "candidate")
        space_id = "forge_" + slug(str(candidate.get("candidate_kind") or "candidate")) + "_" + slug(artifact_id)[:48]
        root = registry.root / space_id
        if (root / "beast_space.json").is_file():
            rows.append({"space_id": space_id, "status": "already_exists"})
            continue
        root.mkdir(parents=True, exist_ok=True)
        artifact = {
            "beast_object_type": "forge_commons_candidate_hypothesis",
            "version": "1.0",
            "space_id": space_id,
            "candidate_kind": candidate.get("candidate_kind"),
            "artifact_id": candidate.get("artifact_id"),
            "name": candidate.get("name"),
            "task_class": candidate.get("task_class"),
            "signals": candidate.get("signals") or [],
            "registration_score": candidate.get("registration_score"),
            "recommended_next_step": candidate.get("recommended_next_step"),
            "source_snapshot_hash": snapshot_hash,
            "raw_forge_state_exported": False,
            "claim_boundary": "Registration hypothesis only; no reproduction or compute displacement is claimed.",
        }
        artifact_path = root / "forge_candidate.json"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = build_manifest(
            root,
            space_id=space_id,
            name=str(candidate.get("name") or artifact_id),
            task_class=str(candidate.get("task_class") or "forge_candidate_evaluation"),
            artifacts=[{"path": "forge_candidate.json", "artifact_type": str(candidate.get("candidate_kind") or "forge_candidate")}],
            hardware_profile={"execution_class": "metadata_hypothesis", "gpu_required": False},
            verifier_bundles=[{
                "bundle_id": "pending_candidate_specific_verifier",
                "commands": [],
                "expected_returncode": 0,
                "artifact_scope": "metadata_only",
            }],
            reduction_claims={
                "cloud_calls_avoided": 0,
                "cloud_calls_evidence": "none_pending_live_replay",
                "tokens_avoided": None,
                "gpu_avoided": False,
                "capability_preserved": False,
            },
            safety={
                "risk": "medium",
                "approval_required": True,
                "rollback_required": False,
                "promotion_state": "candidate",
                "adoption_mode": "advisory",
            },
            lineage={
                "case_study": "forge_candidate_" + artifact_id,
                "source_snapshot_hash": snapshot_hash,
                "candidate_kind": candidate.get("candidate_kind"),
            },
        )
        receipt = build_reduction_receipt(
            space_manifest=manifest,
            baseline_route={"route_id": "unregistered_forge_candidate", "status": "not_reusable"},
            optimized_route={"route_id": "commons_quarantined_forge_hypothesis", "status": "quarantined_hypothesis", "provider_calls": 0},
            displacement={
                "provider_calls_avoided": 0,
                "tokens_avoided": None,
                "latency_avoided_ms": None,
                "evidence_class": "pending_local_replay",
                "counterfactual": False,
                "notes": "Corpus registration only; no displacement credit.",
            },
            verifier={"passed": False, "returncode": None, "command": None, "latency_ms": None},
            resource_deltas={"gpu_avoided": False, "measurement_status": "not_measured"},
            provenance={"source_snapshot_hash": snapshot_hash, "artifact_id": artifact_id},
            rollback_available=False,
            approval_required=True,
        )
        write_space(root, manifest, receipt)
        validation = validate_manifest(root, manifest)
        rows.append({"space_id": space_id, "status": "seeded" if validation["valid"] else "invalid", "validation": validation})

    result: Dict[str, Any] = {
        "beast_object_type": "forge_commons_seed_receipt",
        "version": "1.0",
        "target_spaces": args.target_spaces,
        "registry_count": registry.list_spaces()["count"],
        "seeded": sum(1 for item in rows if item["status"] == "seeded"),
        "rows": rows,
        "claim_boundary": "Forge candidates increase hypothesis breadth; they do not increase live-proof density until promoted.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
