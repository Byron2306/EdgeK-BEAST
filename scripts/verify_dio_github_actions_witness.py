#!/usr/bin/env python3
"""Verify a downloaded DIO GitHub Actions witness packet.

This script verifies the packet's internal digest locally.  If `--repo` is
provided and `gh` is installed/authenticated, it also asks GitHub CLI to verify
the artifact attestation for the packet.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--repo", default="")
    args = parser.parse_args()
    result = verify(args.packet, repo=args.repo)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 1


def verify(packet_path: Path, *, repo: str = "") -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    claimed = str(packet.get("packet_digest") or "")
    body = dict(packet)
    body.pop("packet_digest", None)
    recomputed = sha256_digest(body)
    gates = {
        "object_type": packet.get("beast_object_type") == "dio_github_actions_remote_witness_packet",
        "packet_digest_recomputes": claimed == recomputed,
        "remote_runtime": packet.get("remote_runtime") is True,
        "requires_github_artifact_attestation": packet.get("requires_github_artifact_attestation") is True,
        "requires_oidc_identity": packet.get("requires_oidc_identity") is True,
        "authority_bounded": packet.get("maximum_authority") == "remote_oidc_sigstore_software_witness_only",
        "production_authority_denied": packet.get("production_authority_allowed") is False,
        "execution_authority_denied": packet.get("execution_authority_allowed") is False,
        "tests_passed": (packet.get("test_evidence") or {}).get("test_status") == "passed",
    }
    gh = shutil.which("gh")
    attestation = {"attempted": False, "verified": False, "stdout": "", "stderr": ""}
    if repo and gh:
        result = subprocess.run(
            [gh, "attestation", "verify", str(packet_path), "--repo", repo],
            text=True,
            capture_output=True,
            timeout=120,
        )
        attestation = {
            "attempted": True,
            "verified": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        gates["github_attestation_verified"] = result.returncode == 0
    red_gates = tuple(sorted(name for name, ok in gates.items() if not ok))
    return {
        "beast_object_type": "dio_github_actions_witness_verification",
        "verified": not red_gates,
        "packet_digest": claimed,
        "recomputed_packet_digest": recomputed,
        "red_gates": red_gates,
        "github_attestation": attestation,
    }


if __name__ == "__main__":
    raise SystemExit(main())
