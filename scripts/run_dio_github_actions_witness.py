#!/usr/bin/env python3
"""Emit a DIO GitHub Actions remote witness packet.

GitHub Actions is a remote software witness, not hardware attestation.  Its
strong identity comes from workflow OIDC and GitHub artifact attestations.  This
script creates the packet that the workflow uploads and asks GitHub to attest.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest, utc_now_iso


AUTHORITY = "remote_oidc_sigstore_software_witness_only"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("evidence/dai-diode/phase2.1-github-witness/dio_github_actions_witness_packet.json"))
    parser.add_argument("--test-status", default=os.environ.get("DIO_GITHUB_TEST_STATUS", "unknown"))
    parser.add_argument("--test-command", default=os.environ.get("DIO_GITHUB_TEST_COMMAND", ""))
    args = parser.parse_args()
    packet = build_packet(test_status=args.test_status, test_command=args.test_command)
    packet["packet_digest"] = sha256_digest(packet)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(packet) + "\n", encoding="utf-8")
    print(json.dumps({"witness_packet": str(args.out), "packet_digest": packet["packet_digest"]}, indent=2, sort_keys=True))
    return 0


def build_packet(*, test_status: str, test_command: str) -> dict[str, Any]:
    head = _run(["git", "rev-parse", "HEAD"])
    workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "")
    workflow_sha = os.environ.get("GITHUB_WORKFLOW_SHA", "")
    workflow_identity = {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "repository_id": os.environ.get("GITHUB_REPOSITORY_ID", ""),
        "repository_owner": os.environ.get("GITHUB_REPOSITORY_OWNER", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "job": os.environ.get("GITHUB_JOB", ""),
        "event_name": os.environ.get("GITHUB_EVENT_NAME", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "sha": os.environ.get("GITHUB_SHA", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "runner_os": os.environ.get("RUNNER_OS", ""),
        "runner_arch": os.environ.get("RUNNER_ARCH", ""),
        "server_url": os.environ.get("GITHUB_SERVER_URL", ""),
        "api_url": os.environ.get("GITHUB_API_URL", ""),
    }
    return {
        "beast_object_type": "dio_github_actions_remote_witness_packet",
        "version": "2026-08-04.phase2.1.github-actions-witness.v1",
        "node_id": "dio:github:actions-witness-01",
        "role": "semantic_or_adversarial_witness",
        "authority_boundary": AUTHORITY,
        "maximum_authority": AUTHORITY,
        "hardware_rooted_identity": False,
        "remote_runtime": True,
        "requires_github_artifact_attestation": True,
        "requires_oidc_identity": True,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "provider_calls_used": 0,
        "workflow_identity": workflow_identity,
        "workflow_identity_digest": sha256_digest(workflow_identity),
        "source": {
            "git_head": head.get("stdout", "").strip(),
            "git_head_digest": sha256_digest({"git_head": head.get("stdout", "").strip()}),
            "git_status_short": _run(["git", "status", "--short"]).get("stdout", ""),
        },
        "test_evidence": {
            "test_status": test_status,
            "test_command": test_command,
            "test_command_digest": sha256_digest({"command": test_command}),
        },
        "runtime": {
            "created_at": utc_now_iso(),
            "python": sys.version,
            "platform": platform.platform(),
        },
        "nonclaims": (
            "not_hardware_attestation",
            "not_execution_authority",
            "not_production_authority",
            "not_a_substitute_for_azure_or_gcp_tee",
        ),
    }


def _run(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=30)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    raise SystemExit(main())
