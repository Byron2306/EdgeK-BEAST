#!/usr/bin/env python3
"""Phase 6 persisted crystallization lifecycle evidence harness."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.capability.capability_crystallization import CapabilityCrystallizationEngine
from app.kernel.capability.capability_impact import CapabilityImpactFingerprint


OUT = ROOT / "benchmarks" / "results"


def _write_repo(root: Path, value: str = "1") -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "app" / "phase6_contract.py").write_text(f"VALUE = {value}\n", encoding="utf-8")
    (root / "tests" / "test_phase6_contract.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def run() -> Dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="beast-phase6-lifecycle-") as temp:
        root = Path(temp) / "repo"
        state_dir = Path(temp) / "state"
        _write_repo(root, "1")
        boundary = {
            "root": str(root),
            "target_paths": ["app/phase6_contract.py"],
            "test_paths": ["tests/test_phase6_contract.py"],
            "policy_version": "phase6_lifecycle_v1",
            "confidence": 0.97,
        }
        fingerprint = CapabilityImpactFingerprint().build(
            root,
            target_paths=boundary["target_paths"],
            test_paths=boundary["test_paths"],
            policy_version=boundary["policy_version"],
            confidence=boundary["confidence"],
        )

        engine = CapabilityCrystallizationEngine(storage_path=state_dir)
        for _ in range(5):
            engine.register_shadow_run(
                "phase6_schema_cap",
                "contract",
                "deterministic",
                hidden_test_success=True,
                rollback_success=True,
                behavior_preserved=True,
                impact_fingerprint=fingerprint,
            )
        for index in range(3):
            engine.register_shadow_run(
                "phase6_flaky_cap",
                "contract",
                "deterministic",
                hidden_test_success=index < 2,
                rollback_success=index < 2,
                behavior_preserved=index < 2,
                impact_fingerprint=fingerprint,
            )
        promoted_id = "crystal_phase6_schema_cap_contract"
        flaky_id = "crystal_phase6_flaky_cap_contract"
        proof = engine.promote_candidate(promoted_id)
        flaky_eligible = engine.check_promotion_eligibility(flaky_id)
        metrics_before = engine.update_metrics(displaced_tokens=840, displaced_usd=0.0042).to_dict()

        reloaded = CapabilityCrystallizationEngine(storage_path=state_dir)
        active_boundary = reloaded.check_fingerprint_at_boundary(promoted_id, current_repo_state=boundary)
        _write_repo(root, "2")
        stale_boundary = reloaded.check_fingerprint_at_boundary(promoted_id, current_repo_state=boundary)
        metrics_after = reloaded.update_metrics().to_dict()

        passed = bool(
            proof is not None
            and flaky_eligible[0] is False
            and len(CapabilityCrystallizationEngine(storage_path=state_dir).list_promoted()) == 0
            and active_boundary.get("reusable") is True
            and stale_boundary.get("state") == "shadow_revalidation"
            and metrics_after.get("demoted_count") == 1
        )
        return {
            "beast_object_type": "compute_governor_phase6_lifecycle",
            "version": "1.0",
            "state_path": str(state_dir / "capability_crystallization_state.json"),
            "promoted_proof": proof.to_dict() if proof else None,
            "flaky_candidate_eligible": flaky_eligible[0],
            "flaky_candidate_reason": flaky_eligible[1],
            "active_boundary_decision": active_boundary,
            "stale_boundary_decision": stale_boundary,
            "metrics_before_demote": metrics_before,
            "metrics_after_demote": metrics_after,
            "observed_promotion_precision": metrics_after.get("promotion_precision"),
            "phase6_lifecycle_passed": passed,
            "wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "claim_boundary": (
                "This local harness persists crystallization state, reloads it, checks the active fingerprint "
                "at runtime, then changes the target file and observes automatic demotion. Promotion precision "
                "is measured over promoted vs demoted candidates in this bounded lifecycle sample."
            ),
        }


def write_report(report: Dict[str, Any]) -> List[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "compute_governor_phase6_lifecycle.json"
    md_path = OUT / "compute_governor_phase6_lifecycle.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Compute Governor Phase 6 Lifecycle Evidence",
        "",
        f"- Persisted state: `{report['state_path']}`",
        f"- Promoted proof emitted: `{report['promoted_proof'] is not None}`",
        f"- Flaky candidate blocked: `{not report['flaky_candidate_eligible']}`",
        f"- Active boundary reusable: `{report['active_boundary_decision'].get('reusable')}`",
        f"- Stale boundary state: `{report['stale_boundary_decision'].get('state')}`",
        f"- Demoted count: `{report['metrics_after_demote'].get('demoted_count')}`",
        f"- Observed promotion precision: `{report['observed_promotion_precision']}`",
        f"- Result: `{'PASS' if report['phase6_lifecycle_passed'] else 'FAIL'}`",
        "",
        "## Claim Boundary",
        "",
        report["claim_boundary"],
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [json_path, md_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = run()
    files = write_report(report)
    print(json.dumps({"report": report, "files": [str(path) for path in files]}, indent=2))
    return 0 if report["phase6_lifecycle_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
