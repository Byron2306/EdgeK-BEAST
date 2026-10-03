#!/usr/bin/env python3
"""Package a fresh hardened Phase-2.1 X2 run without modifying Phase-2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import package_dai_phase2_exact_artifact as capsule


RELEASE_ID = "DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04"
EVIDENCE_RELATIVE_PATH = "evidence/dai-diode/phase2.1-stale-listener-001/x2-exact-ring"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--evidence", type=Path, default=ROOT / EVIDENCE_RELATIVE_PATH)
    args = parser.parse_args()
    summary_path = args.evidence / "phase2_x2_exact_ring_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not summary.get("green"):
        raise RuntimeError("refusing to fossilize a non-green Phase-2.1 X2 proof")
    capsule.RELEASE_ID = RELEASE_ID
    capsule.EXPECTED_SUMMARY_DIGEST = str(summary["summary_digest"])
    capsule.EXPECTED_EVIDENCE = args.evidence
    capsule.EVIDENCE_RELATIVE_PATH = EVIDENCE_RELATIVE_PATH
    capsule.SOURCE_PATHS = list(dict.fromkeys([
        *capsule.SOURCE_PATHS,
        "scripts/package_dai_phase2_1_artifact.py",
        "scripts/deploy_dio_hf_witness_space.py",
        "scripts/verify_dio_hf_witness.py",
        "scripts/verify_dio_github_actions_witness.py",
        "app/dio_hf_witness_main.py",
        "deploy/dio-hf-witness",
        ".github/workflows/dio-remote-witness.yml",
    ]))
    result = capsule.package(out_root=args.out_root, evidence=args.evidence)
    result["phase2_1_summary_digest"] = summary["summary_digest"]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
