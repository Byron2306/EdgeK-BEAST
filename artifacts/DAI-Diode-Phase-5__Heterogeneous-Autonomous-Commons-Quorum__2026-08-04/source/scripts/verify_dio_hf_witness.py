#!/usr/bin/env python3
"""Harvest and independently verify a live Hugging Face DIO witness receipt."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.dio_distributed_quorum import DIOProposalPacket, DIORemoteWitnessVote, DIOWitnessAdmission, verify_dio_vote_signature
from app.kernel.dai.dio_commons_online import (
    DIOCommonsCapabilityManifest,
    DIOCommonsChallenge,
    DIOCommonsSpaceIdentity,
    verify_commons_identity,
)
from app.kernel.dai.dio_remote_witness_packet import DIOAutonomousRemoteWitnessPacket, verify_autonomous_remote_witness_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", type=Path, default=Path("evidence/dai-diode/phase2.1-hf-witness/dio_hf_space_deployment.json"))
    parser.add_argument("--base-url", default="")
    parser.add_argument("--proposal-file", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("evidence/dai-diode/phase2.1-hf-witness/dio_hf_live_witness_receipt.json"))
    args = parser.parse_args()
    result = verify(deployment_path=args.deployment, base_url=args.base_url, proposal_file=args.proposal_file)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 1


def verify(*, deployment_path: Path, base_url: str = "", proposal_file: Path | None = None) -> dict[str, Any]:
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    repo_id = str(deployment["repo_id"])
    url = base_url.rstrip("/") or f"https://{repo_id.replace('/', '-').lower()}.hf.space"
    health = _request_json(url + "/health")
    nonce = secrets.token_urlsafe(32)
    identity_payload = _request_json(url + "/identity")
    manifest_payload = _request_json(url + "/manifest")
    proposal = (
        _load_proposal(proposal_file)
        if proposal_file
        else _proposal(nonce, governance_epoch=str(deployment.get("governance_epoch") or "dio-phase4-online-001"))
    )
    nonce = str(proposal["challenge_nonce"])
    challenge_response = _request_json(url + "/v1/challenge", {
        "proposal_digest": proposal["proposal_digest"],
        "evidence_root": proposal["evidence_root"],
        "world_state_hash": proposal["world_state_hash"],
        "governance_epoch": proposal["governance_epoch"],
        "challenge_nonce": nonce,
    })
    attestation = challenge_response["attestation"]
    status_attestation = _request_json(url + "/attestation")
    refreshed_attestation = _request_json(url + "/v1/refresh-attestation", {"challenge_nonce": nonce})
    vote = _request_json(url + "/v1/vote", {"proposal": proposal})
    evaluated_vote = _request_json(url + "/v1/evaluate", {"proposal": proposal})
    autonomous_response = _request_json(url + "/v1/autonomous-packet", {"proposal": proposal})
    attestation_subject = dict(attestation)
    signature = str(attestation_subject.pop("challenge_signature", ""))
    expected_key = str(deployment["public_signing_key"])
    attestation_signature_valid = _verify_signature(expected_key, attestation_subject, signature)
    vote_model = DIORemoteWitnessVote(**{name: value for name, value in vote.items() if name != "vote_digest"})
    evaluated_vote_model = DIORemoteWitnessVote(**{name: value for name, value in evaluated_vote.items() if name != "vote_digest"})
    proposal_model = DIOProposalPacket(**proposal)
    identity_signature = str(identity_payload.pop("identity_signature", ""))
    claimed_identity_digest = str(identity_payload.pop("identity_digest", ""))
    claimed_manifest_digest = str(manifest_payload.pop("manifest_digest", ""))
    identity = DIOCommonsSpaceIdentity(**identity_payload)
    manifest = DIOCommonsCapabilityManifest(**manifest_payload)
    challenge = DIOCommonsChallenge(**challenge_response["challenge"])
    autonomous_admission_payload = dict(autonomous_response["admission"])
    claimed_autonomous_admission_digest = str(autonomous_admission_payload.pop("admission_digest", ""))
    autonomous_admission = DIOWitnessAdmission(**autonomous_admission_payload)
    autonomous_packet_payload = dict(autonomous_response["packet"])
    claimed_autonomous_packet_digest = str(autonomous_packet_payload.pop("packet_digest", ""))
    autonomous_packet = DIOAutonomousRemoteWitnessPacket(**autonomous_packet_payload)
    autonomous_verification = verify_autonomous_remote_witness_packet(
        packet=autonomous_packet,
        admission=autonomous_admission,
        proposal=proposal_model,
        permitted_verifier_commits=(deployment.get("verifier_commit"),),
        evaluation_time=datetime.now(timezone.utc),
    )
    gates = {
        "health_ok": health.get("ok") is True,
        "health_identity_matches": health.get("node_id") == deployment.get("node_id") and health.get("role") == deployment.get("role"),
        "health_authority_bounded": health.get("maximum_authority") == "remote_signed_software_witness_only",
        "identity_digest_recomputes": identity.identity_digest == claimed_identity_digest,
        "identity_signature_valid": verify_commons_identity(identity, identity_signature),
        "identity_key_matches_deployment": identity.public_signing_key == expected_key and identity.key_fingerprint == deployment.get("key_fingerprint"),
        "identity_binds_manifest": identity.capability_manifest_digest == manifest.manifest_digest,
        "identity_epoch_matches_deployment": identity.governance_epoch == deployment.get("governance_epoch"),
        "manifest_digest_recomputes": manifest.manifest_digest == claimed_manifest_digest,
        "manifest_authority_bounded": manifest.maximum_authority == "remote_signed_software_witness_only" and not manifest.execution_authority_allowed and not manifest.production_authority_allowed,
        "challenge_digest_recomputes": challenge.challenge_digest == challenge_response.get("challenge_digest"),
        "challenge_binds_proposal": challenge.proposal_digest == proposal_model.proposal_digest and challenge.evidence_root == proposal_model.evidence_root and challenge.world_state_hash == proposal_model.world_state_hash,
        "challenge_nonce_matches": challenge.challenge_nonce == nonce,
        "attestation_identity_matches": attestation.get("node_id") == deployment.get("node_id") and attestation.get("role") == deployment.get("role"),
        "attestation_nonce_matches": attestation.get("challenge_nonce") == nonce,
        "attestation_key_matches_deployment": attestation.get("public_signing_key") == expected_key and attestation.get("key_fingerprint") == deployment.get("key_fingerprint"),
        "attestation_signature_valid": attestation_signature_valid,
        "attestation_build_pins_match": attestation.get("verifier_commit") == deployment.get("verifier_commit") and attestation.get("container_manifest") == deployment.get("container_manifest"),
        "attestation_binds_identity_manifest": attestation.get("identity_digest") == identity.identity_digest and attestation.get("capability_manifest_digest") == manifest.manifest_digest,
        "status_attestation_bounded": status_attestation.get("maximum_authority") == "remote_signed_software_witness_only",
        "refresh_attestation_nonce_matches": refreshed_attestation.get("challenge_nonce") == nonce,
        "vote_signature_valid": verify_dio_vote_signature(vote_model, expected_key),
        "evaluated_vote_signature_valid": verify_dio_vote_signature(evaluated_vote_model, expected_key),
        "vote_binds_proposal": vote_model.proposal_digest == proposal_model.proposal_digest,
        "evaluated_vote_binds_proposal": evaluated_vote_model.proposal_digest == proposal_model.proposal_digest,
        "vote_binds_nonce": vote_model.challenge_nonce == nonce,
        "evaluated_vote_binds_nonce": evaluated_vote_model.challenge_nonce == nonce,
        "vote_authority_bounded": vote_model.maximum_authority == "remote_signed_software_witness_only",
        "evaluated_vote_authority_bounded": evaluated_vote_model.maximum_authority == "remote_signed_software_witness_only",
        "autonomous_packet_digest_recomputes": autonomous_packet.packet_digest == claimed_autonomous_packet_digest,
        "autonomous_admission_digest_recomputes": autonomous_admission.admission_digest == claimed_autonomous_admission_digest,
        "autonomous_packet_verified": autonomous_verification.verified,
        "autonomous_packet_authority_bounded": autonomous_packet.maximum_authority == "remote_signed_software_witness_only",
        "autonomous_packet_independently_evaluated": autonomous_packet.independently_evaluated is True,
        "autonomous_packet_remote_runtime_observed": autonomous_packet.remote_runtime_observed is True,
    }
    red_gates = tuple(sorted(name for name, passed in gates.items() if not passed))
    receipt = {
        "beast_object_type": "dio_hf_live_remote_witness_receipt",
        "repo_id": repo_id,
        "base_url": url,
        "verified": not red_gates,
        "red_gates": red_gates,
        "deployment_digest": deployment.get("deployment_digest"),
        "shared_proposal_supplied": proposal_file is not None,
        "proposal_packet_digest": proposal_model.packet_digest,
        "health": health,
        "identity": {**identity_payload, "identity_digest": claimed_identity_digest, "identity_signature": identity_signature},
        "manifest": {**manifest_payload, "manifest_digest": claimed_manifest_digest},
        "challenge": challenge_response,
        "status_attestation": status_attestation,
        "refreshed_attestation": refreshed_attestation,
        "attestation": attestation,
        "vote": vote,
        "evaluated_vote": evaluated_vote,
        "autonomous_packet": autonomous_response,
        "autonomous_packet_verification": {
            **{
                field: getattr(autonomous_verification, field)
                for field in autonomous_verification.__dataclass_fields__
            },
            "verification_digest": autonomous_verification.verification_digest,
        },
        "maximum_authority": "remote_signed_software_witness_only",
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _proposal(nonce: str, *, governance_epoch: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "beast_object_type": "dio_proposition_packet",
        "proposal_digest": sha256_digest({"proposal": "hf-live-witness-smoke"}),
        "capability_digest": sha256_digest({"capability": "semantic_witness_only"}),
        "evidence_root": sha256_digest({"evidence": "hf-live-witness-challenge"}),
        "world_state_hash": sha256_digest({"world": "hf-live-witness-smoke"}),
        "governance_epoch": governance_epoch,
        "challenge_nonce": nonce,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "audience": "dai-distributed-quorum",
    }


def _load_proposal(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("packet_digest", None)
    return payload


def _request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"} if data else {}, method="POST" if data else "GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"remote witness request failed for {url}: {exc}") from exc


def _verify_signature(public_key_b64: str, subject: dict[str, Any], signature_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True)).verify(
            base64.b64decode(signature_b64, validate=True), canonical_json(subject).encode("utf-8")
        )
        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
