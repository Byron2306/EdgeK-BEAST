#!/usr/bin/env python3
"""Verify the Sophia/Integritas lineage certificate against the pinned key policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.phase6_sophia_integritas_lineage import verify_lineage_certificate_against_key_policy


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certificate", type=Path, default=ROOT / "evidence/dai-diode/phase6-sophia-integritas-lineage/sophia_integritas_unified_lineage_certificate.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "release-keys/sophia_integritas_lineage_key_policy.json")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase6-sophia-integritas-lineage/sophia_integritas_project_key_policy_verification.json")
    args = parser.parse_args()
    verification = verify_lineage_certificate_against_key_policy(_read_json(args.certificate), _read_json(args.policy))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(verification) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified": verification["verified"],
        "certificate_digest": verification["certificate_digest"],
        "policy_digest": verification["policy_digest"],
        "public_key_fingerprint": verification["public_key_fingerprint"],
        "verification_digest": verification["verification_digest"],
        "red_gates": verification["red_gates"],
        "out": str(args.out),
    }, indent=2, sort_keys=True))
    return 0 if verification["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
