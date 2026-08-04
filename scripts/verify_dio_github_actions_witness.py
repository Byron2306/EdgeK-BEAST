#!/usr/bin/env python3
"""Verify a downloaded DIO GitHub Actions witness packet.

This script verifies the packet's internal digest locally.  If `--repo` is
provided and `gh` is installed/authenticated, it also asks GitHub CLI to verify
the artifact attestation for the packet.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
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
from app.kernel.dai.dio_distributed_quorum import DIOProposalPacket, DIOWitnessAdmission
from app.kernel.dai.dio_remote_witness_packet import DIOAutonomousRemoteWitnessPacket, verify_autonomous_remote_witness_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--repo", default="")
    parser.add_argument("--out", type=Path, help="write the verification receipt here")
    args = parser.parse_args()
    result = verify(args.packet, repo=args.repo)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 1


def verify(packet_path: Path, *, repo: str = "") -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if packet.get("beast_object_type") == "dio_github_actions_autonomous_witness_envelope":
        return _verify_autonomous_envelope(packet_path, packet, repo=repo)
    return _verify_legacy_packet(packet_path, packet, repo=repo)


def _verify_legacy_packet(packet_path: Path, packet: dict[str, Any], *, repo: str = "") -> dict[str, Any]:
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
    receipt = {
        "beast_object_type": "dio_github_actions_witness_verification",
        "verified": not red_gates,
        "packet_path": str(packet_path),
        "packet_file_sha256": "sha256:" + hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "packet_digest": claimed,
        "recomputed_packet_digest": recomputed,
        "red_gates": red_gates,
        "github_attestation": attestation,
    }
    receipt["verification_digest"] = sha256_digest(receipt)
    return receipt


def _verify_autonomous_envelope(packet_path: Path, envelope: dict[str, Any], *, repo: str = "") -> dict[str, Any]:
    claimed = str(envelope.get("envelope_digest") or "")
    body = dict(envelope)
    body.pop("envelope_digest", None)
    recomputed = sha256_digest(body)
    proposal_payload = dict(envelope.get("proposal") or {})
    claimed_proposal_packet_digest = str(proposal_payload.pop("packet_digest", ""))
    admission_payload = dict(envelope.get("admission") or {})
    claimed_admission_digest = str(admission_payload.pop("admission_digest", ""))
    packet_payload = dict(envelope.get("packet") or {})
    claimed_autonomous_packet_digest = str(packet_payload.pop("packet_digest", ""))
    autonomous_red: tuple[str, ...] = ("autonomous_packet_not_parsed",)
    autonomous_verification: dict[str, Any] = {}
    parsed_ok = False
    try:
        proposal = DIOProposalPacket(**proposal_payload)
        admission = DIOWitnessAdmission(**admission_payload)
        autonomous_packet = DIOAutonomousRemoteWitnessPacket(**packet_payload)
        evaluation_time = _historical_evaluation_time(autonomous_packet.issued_at)
        verified = verify_autonomous_remote_witness_packet(
            packet=autonomous_packet,
            admission=admission,
            proposal=proposal,
            permitted_verifier_commits=(admission.verifier_commit,),
            evaluation_time=evaluation_time,
        )
        autonomous_red = verified.red_gates
        autonomous_verification = {
            field: getattr(verified, field)
            for field in verified.__dataclass_fields__
        } | {"verification_digest": verified.verification_digest}
        parsed_ok = True
    except Exception as exc:
        autonomous_verification = {"error": f"{type(exc).__name__}: {exc}"}
        proposal = None
        admission = None
        autonomous_packet = None

    gates = {
        "object_type": envelope.get("beast_object_type") == "dio_github_actions_autonomous_witness_envelope",
        "envelope_digest_recomputes": claimed == recomputed,
        "phase5_envelope_version": envelope.get("version") == "2026-08-04.phase5.github-actions-autonomous-witness.v1",
        "remote_runtime": envelope.get("remote_runtime") is True,
        "requires_github_artifact_attestation": envelope.get("requires_github_artifact_attestation") is True,
        "requires_oidc_identity": envelope.get("requires_oidc_identity") is True,
        "authority_bounded": envelope.get("maximum_authority") == "remote_oidc_sigstore_software_witness_only",
        "production_authority_denied": envelope.get("production_authority_allowed") is False,
        "execution_authority_denied": envelope.get("execution_authority_allowed") is False,
        "provider_calls_zero": envelope.get("provider_calls_used") == 0,
        "tests_passed": (envelope.get("test_evidence") or {}).get("test_status") == "passed",
        "github_subject_digest_recomputes": envelope.get("github_attestation_subject_digest")
        == sha256_digest(envelope.get("github_attestation_subject") or {}),
        "workflow_identity_digest_recomputes": envelope.get("workflow_identity_digest")
        == sha256_digest(envelope.get("workflow_identity") or {}),
        "proposal_packet_digest_recomputes": parsed_ok and proposal is not None and proposal.packet_digest == claimed_proposal_packet_digest,
        "admission_digest_recomputes": parsed_ok and admission is not None and admission.admission_digest == claimed_admission_digest,
        "autonomous_packet_digest_recomputes": parsed_ok
        and autonomous_packet is not None
        and autonomous_packet.packet_digest == claimed_autonomous_packet_digest,
        "autonomous_packet_verified": parsed_ok and not autonomous_red,
        "autonomous_packet_authority_bounded": parsed_ok
        and autonomous_packet is not None
        and autonomous_packet.maximum_authority == "remote_oidc_sigstore_software_witness_only",
        "autonomous_packet_independently_evaluated": parsed_ok
        and autonomous_packet is not None
        and autonomous_packet.independently_evaluated is True,
        "autonomous_packet_remote_runtime_observed": parsed_ok
        and autonomous_packet is not None
        and autonomous_packet.remote_runtime_observed is True,
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
    receipt = {
        "beast_object_type": "dio_github_actions_autonomous_witness_verification",
        "verified": not red_gates,
        "packet_path": str(packet_path),
        "packet_file_sha256": "sha256:" + hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "envelope_digest": claimed,
        "recomputed_envelope_digest": recomputed,
        "autonomous_packet_digest": claimed_autonomous_packet_digest,
        "autonomous_packet_verification": autonomous_verification,
        "autonomous_packet_red_gates": autonomous_red,
        "red_gates": red_gates,
        "github_attestation": attestation,
        "maximum_authority": "remote_oidc_sigstore_software_witness_only",
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["verification_digest"] = sha256_digest(receipt)
    return receipt


def _historical_evaluation_time(issued_at: str) -> datetime:
    parsed = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) + timedelta(seconds=1)


if __name__ == "__main__":
    raise SystemExit(main())
