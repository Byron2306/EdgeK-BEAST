#!/usr/bin/env python3
"""Live Commons displacement harness.

This is the currency-worthy path:

1. Select an adopted or valid Commons Space.
2. Simulate repeated workload boundary matches.
3. Run approved live verifier replay against a local target.
4. Adopt locally after proof, if needed.
5. Attempt strict non-financial crystal credit issuance.

No cloud provider is called by this script. It records observed avoided calls as
local workload-match evidence, while the economy still decides credit from
manifest, receipt, live reproduction, adoption, and anti-gaming rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.commons_economy import ComputeReductionEconomy
from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.crystal_seal import canonical_bytes, seal_crystal_payload


LATEST_RECEIPT = ROOT / "benchmarks" / "results" / "live_commons_displacement_harness_latest.json"


def _task_boundary(detail: Dict[str, Any]) -> Dict[str, Any]:
    manifest = detail["manifest"]
    verifier_bundles = manifest.get("verifier_bundles") or []
    payload = {
        "space_id": manifest.get("space_id"),
        "task_class": manifest.get("task_class"),
        "manifest_hash": manifest.get("manifest_hash"),
        "verifier_bundle_ids": [item.get("bundle_id") for item in verifier_bundles],
        "artifact_types": sorted({str(item.get("artifact_type") or "") for item in manifest.get("artifacts") or []}),
    }
    payload["boundary_hash"] = "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def _choose_space(registry: CommonsSpaceRegistry, requested: str = "") -> str:
    if requested:
        registry.get(requested)
        return requested
    rows = [item for item in registry.list_spaces().get("spaces") or [] if item.get("valid")]
    if not rows:
        raise RuntimeError("no valid Commons Spaces available")
    rows.sort(key=lambda item: (
        0 if item.get("adoption_state") == "adopted" else 1,
        -int(item.get("provider_calls_avoided") or 0),
        str(item.get("space_id") or ""),
    ))
    return str(rows[0]["space_id"])


def _workload_matches(
    space_id: str,
    boundary: Dict[str, Any],
    reproductions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = []
    for index, reproduction in enumerate(reproductions):
        if not (
            reproduction.get("reproduced")
            and reproduction.get("mode") == "live_verifier"
            and reproduction.get("live_verifier_passed") is True
        ):
            continue
        seed = {
            "space_id": space_id,
            "boundary_hash": boundary["boundary_hash"],
            "repeat_index": index,
            "reproduction_id": reproduction.get("reproduction_id"),
        }
        rows.append({
            "beast_object_type": "commons_workload_boundary_match",
            "version": "1.0",
            "match_id": "match_" + hashlib.sha256(canonical_bytes(seed)).hexdigest()[:20],
            "space_id": space_id,
            "task_class": boundary.get("task_class"),
            "boundary_hash": boundary["boundary_hash"],
            "matched": True,
            "selected_action": "reuse_crystallized_compute_space",
            "cloud_api_call_avoided": True,
            "reproduction_id": reproduction.get("reproduction_id"),
            "reproduction_receipt_hash": (reproduction.get("local_seal") or {}).get("payload_hash"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def run_displacement_harness(
    *,
    space_id: str = "",
    target: Path = ROOT,
    repeats: int = 3,
    approved_by: str = "live_commons_displacement_harness",
    reason: str = "Live workload boundary matched; local verifier reproduced; cloud call avoided.",
    output: Path = LATEST_RECEIPT,
) -> Dict[str, Any]:
    """Execute and seal one live reproduction for every claimed match."""
    registry = CommonsSpaceRegistry()
    economy = ComputeReductionEconomy(registry)
    selected_space_id = _choose_space(registry, space_id)
    detail = registry.get(selected_space_id)
    boundary = _task_boundary(detail)
    reproductions = [
        registry.replay(
            selected_space_id,
            target=Path(target),
            deterministic_only=False,
            approved=True,
            timeout_seconds=300,
            contributor_id=f"live_displacement_harness_repeat_{index + 1}",
        )
        for index in range(max(1, int(repeats)))
    ]
    matches = _workload_matches(selected_space_id, boundary, reproductions)

    adoption = registry.adopt(
        selected_space_id,
        approved=True,
        dry_run=False,
        approved_by=approved_by,
        reason=reason,
    )
    try:
        credit = economy.issue_credit(
            selected_space_id,
            approved=True,
            approved_by=approved_by,
            reason=reason,
        )
    except ValueError as exc:
        credit = {
            "ok": False,
            "error": str(exc),
            "proof": economy.proof(selected_space_id),
        }

    replay = reproductions[-1]
    receipt = {
        "beast_object_type": "live_commons_displacement_harness_receipt",
        "version": "1.0",
        "space_id": selected_space_id,
        "target": str(Path(target).resolve()),
        "task_boundary": boundary,
        "workload_matches": matches,
        "live_replays": reproductions,
        "observed": {
            "repeated_matches": len(matches),
            "live_replay_attempts": len(reproductions),
            "cloud_api_calls_observed": 0,
            "cloud_api_calls_avoided": sum(1 for item in matches if item.get("cloud_api_call_avoided")),
        },
        "live_replay": replay,
        "adoption": adoption,
        "credit_attempt": credit,
        "success": bool(
            len(matches) == max(1, int(repeats))
            and adoption.get("adopted")
            and (credit.get("beast_object_type") == "non_financial_compute_reduction_credit" or credit.get("duplicate_issuance"))
        ),
        "claim_boundary": (
            "Every recorded match has a distinct sealed live-verifier reproduction. "
            "Avoided cloud calls remain local route evidence unless a metered baseline says otherwise."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt["receipt_hash"] = "sha256:" + hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    receipt["local_seal"] = seal_crystal_payload(receipt, purpose="live_commons_displacement_harness")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(output)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live Commons displacement proof harness")
    parser.add_argument("--space-id", default="", help="Space to test. Defaults to best local valid/adopted Space.")
    parser.add_argument("--target", default=str(ROOT), help="Local workspace target for live verifier replay.")
    parser.add_argument("--repeats", type=int, default=3, help="Repeated task-boundary matches to record.")
    parser.add_argument("--approved-by", default="live_commons_displacement_harness")
    parser.add_argument("--reason", default="Live workload boundary matched; local verifier reproduced; cloud call avoided.")
    parser.add_argument("--output", default=str(LATEST_RECEIPT))
    args = parser.parse_args()

    receipt = run_displacement_harness(
        space_id=args.space_id,
        target=Path(args.target),
        repeats=args.repeats,
        approved_by=args.approved_by,
        reason=args.reason,
        output=Path(args.output),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
