#!/usr/bin/env python3
"""Emit a DIO GitHub Actions remote witness packet.

GitHub Actions is a remote software witness, not hardware attestation.  Its
strong identity comes from workflow OIDC and GitHub artifact attestations.  This
script creates the packet that the workflow uploads and asks GitHub to attest.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest, utc_now_iso
from app.kernel.dai.dio_distributed_quorum import (
    DIOProposalPacket,
    DIORemoteWitnessVote,
    DIOVoteDecision,
    DIOWitnessAdmission,
    DIOWitnessRole,
    public_key_b64,
    public_key_fingerprint,
    sign_dio_vote,
)
from app.kernel.dai.dio_remote_witness_packet import DIOAutonomousRemoteWitnessPacket, sign_autonomous_remote_witness_packet


AUTHORITY = "remote_oidc_sigstore_software_witness_only"
GITHUB_AUTONOMOUS_ENVELOPE_VERSION = "2026-08-04.phase5.github-actions-autonomous-witness.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("evidence/dai-diode/phase5-github-witness/dio_github_actions_autonomous_witness_packet.json"))
    parser.add_argument("--test-status", default=os.environ.get("DIO_GITHUB_TEST_STATUS", "unknown"))
    parser.add_argument("--test-command", default=os.environ.get("DIO_GITHUB_TEST_COMMAND", ""))
    parser.add_argument("--legacy", action="store_true", help="emit the older Phase-2.1 GitHub packet shape")
    args = parser.parse_args()
    packet = (
        build_legacy_packet(test_status=args.test_status, test_command=args.test_command)
        if args.legacy
        else build_autonomous_packet(test_status=args.test_status, test_command=args.test_command)
    )
    digest_field = "packet_digest" if args.legacy else "envelope_digest"
    packet[digest_field] = sha256_digest(packet)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(packet) + "\n", encoding="utf-8")
    print(json.dumps({"witness_packet": str(args.out), digest_field: packet[digest_field]}, indent=2, sort_keys=True))
    return 0


def build_legacy_packet(*, test_status: str, test_command: str) -> dict[str, Any]:
    head = _run(["git", "rev-parse", "HEAD"])
    workflow_identity = _workflow_identity()
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


def build_autonomous_packet(*, test_status: str, test_command: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = (now + timedelta(hours=24)).isoformat()
    workflow_identity = _workflow_identity()
    workflow_identity_digest = sha256_digest(workflow_identity)
    source = _source_state()
    test_evidence = _test_evidence(test_status=test_status, test_command=test_command)
    github_attestation_subject = {
        "beast_object_type": "dio_github_actions_oidc_sigstore_subject",
        "workflow_identity_digest": workflow_identity_digest,
        "repository": workflow_identity["repository"],
        "run_id": workflow_identity["run_id"],
        "run_attempt": workflow_identity["run_attempt"],
        "workflow_ref": workflow_identity["workflow_ref"],
        "workflow_sha": workflow_identity["workflow_sha"],
        "artifact_attestation_required": True,
        "oidc_identity_required": True,
        "authority_boundary": AUTHORITY,
    }
    github_attestation_digest = sha256_digest(github_attestation_subject)
    signing_key = Ed25519PrivateKey.generate()
    public = public_key_b64(signing_key.public_key())
    verifier_commit = sha256_digest(
        {
            "github_actions_autonomous_verifier": "v1",
            "workflow_sha": workflow_identity["workflow_sha"],
            "git_head": source["git_head"],
            "script": "scripts/run_dio_github_actions_witness.py",
        }
    )
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest(
            {
                "proposal": "github-actions-autonomous-witness",
                "workflow_identity_digest": workflow_identity_digest,
                "test_command_digest": test_evidence["test_command_digest"],
            }
        ),
        capability_digest=sha256_digest({"capability": "github-actions-oidc-sigstore-software-witness"}),
        evidence_root=sha256_digest({"evidence": "github-actions", "workflow_identity_digest": workflow_identity_digest}),
        world_state_hash=sha256_digest({"world": "github-actions-witness", "git_head": source["git_head"]}),
        governance_epoch="dio-phase5-github-actions-autonomous-001",
        challenge_nonce="github-actions-autonomous-" + sha256_digest(workflow_identity).removeprefix("sha256:")[-32:],
        issued_at=now.isoformat(),
        expires_at=expires_at,
    )
    admission = DIOWitnessAdmission(
        node_id="dio:github:actions-witness-01",
        role=DIOWitnessRole.ADVERSARIAL,
        runtime_platform="github-actions-ubuntu",
        infrastructure_provider="github",
        public_key_b64=public,
        key_fingerprint=public_key_fingerprint(public),
        verifier_commit=verifier_commit,
        maximum_authority=AUTHORITY,
        verifier_build_permitted=True,
        remote_runtime=True,
        hardware_rooted_identity=False,
        attestation_digest=github_attestation_digest,
        container_manifest=sha256_digest({"runner_os": workflow_identity["runner_os"], "runner_arch": workflow_identity["runner_arch"]}),
        admitted=True,
    )
    vote = sign_dio_vote(
        DIORemoteWitnessVote(
            beast_object_type="dio_remote_witness_vote",
            node_id=admission.node_id,
            role=admission.role,
            decision=DIOVoteDecision.APPROVE if test_status == "passed" else DIOVoteDecision.REFUSE,
            proposal_digest=proposal.proposal_digest,
            capability_digest=proposal.capability_digest,
            evidence_root=proposal.evidence_root,
            world_state_hash=proposal.world_state_hash,
            governance_epoch=proposal.governance_epoch,
            verifier_commit=verifier_commit,
            challenge_nonce=proposal.challenge_nonce,
            evidence_checked=(proposal.evidence_root, github_attestation_digest, test_evidence["test_command_digest"]),
            reason_codes=("github_actions_tests_passed" if test_status == "passed" else "github_actions_tests_not_passed", "artifact_attestation_required"),
            issued_at=now.isoformat(),
            expires_at=expires_at,
            maximum_authority=AUTHORITY,
        ),
        signing_key,
    )
    packet = sign_autonomous_remote_witness_packet(
        DIOAutonomousRemoteWitnessPacket(
            beast_object_type="dio_autonomous_remote_witness_packet",
            version="2026-08-04.phase5.autonomous-remote-witness.v1",
            node_id=admission.node_id,
            role=admission.role,
            runtime_platform=admission.runtime_platform,
            infrastructure_provider=admission.infrastructure_provider,
            public_key_b64=public,
            key_fingerprint=admission.key_fingerprint,
            verifier_commit=verifier_commit,
            admission_digest=admission.admission_digest,
            admission_attestation_digest=github_attestation_digest,
            proposal_packet_digest=proposal.packet_digest,
            vote=vote,
            evidence_receipts=(proposal.evidence_root, github_attestation_digest, test_evidence["test_command_digest"]),
            independently_evaluated=True,
            remote_runtime_observed=True,
            issued_at=now.isoformat(),
            expires_at=expires_at,
            maximum_authority=AUTHORITY,
        ),
        signing_key,
    )
    return {
        "beast_object_type": "dio_github_actions_autonomous_witness_envelope",
        "version": GITHUB_AUTONOMOUS_ENVELOPE_VERSION,
        "node_id": admission.node_id,
        "role": admission.role.value,
        "maximum_authority": AUTHORITY,
        "authority_boundary": AUTHORITY,
        "hardware_rooted_identity": False,
        "remote_runtime": True,
        "requires_github_artifact_attestation": True,
        "requires_oidc_identity": True,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "provider_calls_used": 0,
        "workflow_identity": workflow_identity,
        "workflow_identity_digest": workflow_identity_digest,
        "github_attestation_subject": github_attestation_subject,
        "github_attestation_subject_digest": github_attestation_digest,
        "source": source,
        "test_evidence": test_evidence,
        "proposal": _jsonable(proposal) | {"packet_digest": proposal.packet_digest},
        "admission": _jsonable(admission) | {"admission_digest": admission.admission_digest},
        "packet": _jsonable(packet) | {"packet_digest": packet.packet_digest},
        "runtime": {
            "created_at": now.isoformat(),
            "python": sys.version,
            "platform": platform.platform(),
        },
        "nonclaims": (
            "not_hardware_attestation",
            "not_execution_authority",
            "not_production_authority",
            "not_a_substitute_for_azure_or_gcp_tee",
            "github_artifact_attestation_must_verify_the_envelope_file",
        ),
    }


def build_packet(*, test_status: str, test_command: str) -> dict[str, Any]:
    """Backward-compatible alias for tests/importers that expect the old name."""
    return build_autonomous_packet(test_status=test_status, test_command=test_command)


def _workflow_identity() -> dict[str, str]:
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "repository_id": os.environ.get("GITHUB_REPOSITORY_ID", ""),
        "repository_owner": os.environ.get("GITHUB_REPOSITORY_OWNER", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", ""),
        "workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA", ""),
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


def _source_state() -> dict[str, Any]:
    head = _run(["git", "rev-parse", "HEAD"])
    git_head = head.get("stdout", "").strip()
    return {
        "git_head": git_head,
        "git_head_digest": sha256_digest({"git_head": git_head}),
        "git_status_short": _run(["git", "status", "--short"]).get("stdout", ""),
    }


def _test_evidence(*, test_status: str, test_command: str) -> dict[str, str]:
    return {
        "test_status": test_status,
        "test_command": test_command,
        "test_command_digest": sha256_digest({"command": test_command}),
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _run(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=30)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    raise SystemExit(main())
