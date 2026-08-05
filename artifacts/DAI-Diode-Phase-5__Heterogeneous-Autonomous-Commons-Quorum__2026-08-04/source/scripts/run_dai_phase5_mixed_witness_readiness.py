#!/usr/bin/env python3
"""Classify Phase-5 mixed witness evidence before attempting Commons quorum.

This runner is intentionally conservative.  It does not turn harvests,
adapters, or stale packets into quorum votes.  It answers one narrower
question:

    Which available witnesses are true fresh Phase-5 autonomous packets, which
    are cloud harvests that still need in-runtime autonomous signing, and what
    gates still block a full Commons quorum?
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase5-mixed-witness-readiness/dio_phase5_mixed_witness_readiness.json"
DEFAULT_HF = ROOT / "evidence/dai-diode/phase5-hf-witness/dio_hf_phase5_live_witness_receipt.json"
DEFAULT_GITHUB = ROOT / "evidence/dai-diode/phase5-github-witness/run-30959503947/dio_github_actions_autonomous_witness_packet.json"
DEFAULT_GITHUB_VERIFICATION = ROOT / "evidence/dai-diode/phase5-github-witness/run-30959503947/dio_github_actions_autonomous_witness_verification.json"
DEFAULT_GCP = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/harvest/dio_gcp_tee_attestation_harvest.json"
DEFAULT_AZURE = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/azure-live-001/dio_azure_tee_attestation_harvest.json"
DEFAULT_AWS = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/dio_aws_tee_attestation_harvest.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hf", type=Path, default=DEFAULT_HF)
    parser.add_argument("--github", type=Path, default=DEFAULT_GITHUB)
    parser.add_argument("--github-verification", type=Path, default=DEFAULT_GITHUB_VERIFICATION)
    parser.add_argument("--gcp", type=Path, default=DEFAULT_GCP)
    parser.add_argument("--azure", type=Path, default=DEFAULT_AZURE)
    parser.add_argument("--aws", type=Path, default=DEFAULT_AWS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = run(
        hf=args.hf,
        github=args.github,
        github_verification=args.github_verification,
        gcp=args.gcp,
        azure=args.azure,
        aws=args.aws,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["green"] else 2


def run(
    *,
    hf: Path,
    github: Path,
    github_verification: Path,
    gcp: Path,
    azure: Path,
    aws: Path,
    out: Path,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    witness_rows: list[dict[str, Any]] = []
    for row in (
        _hf_row(hf, now),
        _github_row(github, github_verification, now),
        _cloud_harvest_row("gcp", gcp),
        _cloud_harvest_row("azure", azure),
        _cloud_harvest_row("aws", aws),
    ):
        witness_rows.append(row)

    autonomous_green = [
        row
        for row in witness_rows
        if row.get("phase5_autonomous_packet") is True and row.get("fresh") is True and row.get("verified") is True
    ]
    green_proposal_groups = sorted({str(row.get("proposal_packet_digest") or "") for row in autonomous_green if row.get("proposal_packet_digest")})
    roles = sorted({str(row.get("role") or "") for row in autonomous_green if row.get("role")})
    red: list[str] = []
    if len(autonomous_green) < 3:
        red.append("minimum_three_fresh_autonomous_packets")
    if len(green_proposal_groups) != 1:
        red.append("fresh_autonomous_packets_must_share_one_proposal")
    if "semantic_witness" not in roles:
        red.append("semantic_witness_required")
    if "physical_execution_witness" not in roles:
        red.append("physical_execution_witness_required")
    if not ({"adversarial_witness", "governance_witness"} & set(roles)):
        red.append("adversarial_or_governance_witness_required")
    if not any(row.get("provider") in {"gcp", "azure", "aws"} and row.get("green_harvest") for row in witness_rows):
        red.append("at_least_one_green_cloud_harvest_required")
    if any(row.get("provider") == "azure" and not row.get("green_harvest") for row in witness_rows):
        red.append("azure_harvest_not_admitted")

    result = {
        "beast_object_type": "dio_phase5_mixed_witness_readiness",
        "evaluated_at": now.isoformat(),
        "green": not red,
        "red_gates": tuple(red),
        "fresh_autonomous_packet_count": len(autonomous_green),
        "fresh_autonomous_roles": tuple(roles),
        "fresh_autonomous_proposal_packet_digests": tuple(green_proposal_groups),
        "witnesses": witness_rows,
        "authority_boundary": (
            "readiness_only; cloud harvests are not counted as quorum votes until "
            "they emit fresh Phase-5 autonomous packets over the same coordinator proposal"
        ),
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "provider_calls_used": 0,
    }
    result["readiness_digest"] = sha256_digest(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _hf_row(path: Path, now: datetime) -> dict[str, Any]:
    if not path.exists():
        return _missing("hf", path)
    payload = _read(path)
    packet = dict(((payload.get("autonomous_packet") or {}).get("packet") or {}))
    verification = dict(payload.get("autonomous_packet_verification") or {})
    return _packet_row(
        provider="huggingface",
        path=path,
        packet=packet,
        verified=payload.get("verified") is True and verification.get("verified") is True,
        verification_digest=str(verification.get("verification_digest") or ""),
        source_digest=str(payload.get("receipt_digest") or ""),
        now=now,
        source_object_type=str(payload.get("beast_object_type") or ""),
    )


def _github_row(packet_path: Path, verification_path: Path, now: datetime) -> dict[str, Any]:
    if not packet_path.exists():
        return _missing("github", packet_path)
    payload = _read(packet_path)
    verification = _read(verification_path) if verification_path.exists() else {}
    return _packet_row(
        provider="github",
        path=packet_path,
        packet=dict(payload.get("packet") or {}),
        verified=verification.get("verified") is True and (verification.get("autonomous_packet_verification") or {}).get("verified") is True,
        verification_digest=str(verification.get("verification_digest") or ""),
        source_digest=str(payload.get("envelope_digest") or ""),
        now=now,
        source_object_type=str(payload.get("beast_object_type") or ""),
    )


def _packet_row(
    *,
    provider: str,
    path: Path,
    packet: dict[str, Any],
    verified: bool,
    verification_digest: str,
    source_digest: str,
    now: datetime,
    source_object_type: str,
) -> dict[str, Any]:
    issued_at = str(packet.get("issued_at") or "")
    expires_at = str(packet.get("expires_at") or "")
    fresh = _fresh(issued_at, expires_at, now)
    return {
        "provider": provider,
        "path": str(path),
        "source_object_type": source_object_type,
        "source_digest": source_digest,
        "phase5_autonomous_packet": bool(packet),
        "verified": verified,
        "fresh": fresh,
        "node_id": str(packet.get("node_id") or ""),
        "role": str(packet.get("role") or ""),
        "proposal_packet_digest": str(packet.get("proposal_packet_digest") or ""),
        "packet_digest": str(packet.get("packet_digest") or ""),
        "verification_digest": verification_digest,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "remote_runtime_observed": packet.get("remote_runtime_observed") is True,
        "maximum_authority": str(packet.get("maximum_authority") or ""),
        "counts_as_quorum_vote_now": bool(packet) and verified and fresh,
    }


def _cloud_harvest_row(provider: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return _missing(provider, path)
    payload = _read(path)
    admission = dict(payload.get("admission") or {})
    return {
        "provider": provider,
        "path": str(path),
        "source_object_type": str(payload.get("beast_object_type") or ""),
        "source_digest": str(payload.get("harvest_digest") or ""),
        "phase5_autonomous_packet": False,
        "verified": False,
        "fresh": False,
        "green_harvest": payload.get("green") is True,
        "blocked": payload.get("blocked") is True,
        "blocked_reason": str(payload.get("blocked_reason") or ""),
        "node_id": str(admission.get("node_id") or ""),
        "role": str(admission.get("role") or ""),
        "maximum_authority": str(admission.get("maximum_authority") or ""),
        "remote_runtime": admission.get("remote_runtime") is True,
        "hardware_rooted_identity": admission.get("hardware_rooted_identity") is True,
        "can_become_phase5_autonomous_packet": payload.get("green") is True and bool(admission),
        "required_next_step": (
            "emit a fresh autonomous packet inside the remote runtime over the shared coordinator proposal"
            if payload.get("green") is True and admission
            else "obtain a green admitted cloud harvest first"
        ),
        "counts_as_quorum_vote_now": False,
    }


def _fresh(issued_at: str, expires_at: str, now: datetime) -> bool:
    try:
        issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return False
    return issued <= now < expires


def _missing(provider: str, path: Path) -> dict[str, Any]:
    return {
        "provider": provider,
        "path": str(path),
        "missing": True,
        "phase5_autonomous_packet": False,
        "verified": False,
        "fresh": False,
        "counts_as_quorum_vote_now": False,
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
