from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import storage


TEE_SOCKET = "/run/container_launcher/teeserver.sock"
TOKEN_ENDPOINT = "/v1/token"

AUDIENCE = "dio://phase2/quorum/v1"

DEFAULT_PHASE2_EVIDENCE_ROOT = (
    "sha256:"
    "e2b8f75fba124399ee679e2eb530509f1eb84829a1402573a039408658aaa15a"
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str) -> None:
        super().__init__("localhost")
        self.socket_path = socket_path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(self.socket_path)
        self.sock = connection


def request_attestation_token(
    *,
    audience: str,
    binding: str,
) -> str:
    request_body = {
        "audience": audience,
        "token_type": "OIDC",
        "nonces": [binding],
    }

    encoded = canonical_json(request_body)

    connection = UnixSocketHTTPConnection(TEE_SOCKET)
    connection.request(
        "POST",
        TOKEN_ENDPOINT,
        body=encoded,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded)),
        },
    )

    response = connection.getresponse()
    raw = response.read().decode("utf-8").strip()

    if response.status != 200:
        raise RuntimeError(
            f"attestation endpoint returned HTTP {response.status}: {raw}"
        )

    token = raw

    try:
        parsed = json.loads(raw)

        if isinstance(parsed, str):
            token = parsed
        elif isinstance(parsed, dict):
            token = str(
                parsed.get("token")
                or parsed.get("attestation_token")
                or parsed.get("attestationToken")
                or ""
            )
    except json.JSONDecodeError:
        pass

    token = token.strip()

    if token.count(".") != 2:
        raise RuntimeError(
            "Google Confidential Space response was not a compact JWT"
        )

    return token


def upload_packet(
    *,
    packet: dict[str, Any],
    bucket_name: str,
    object_name: str,
) -> None:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    blob.upload_from_string(
        canonical_json(packet),
        content_type="application/json",
        if_generation_match=0,
    )


def main() -> None:
    bucket_name = os.environ.get("DIO_OUTPUT_BUCKET", "").strip()
    object_name = os.environ.get("DIO_OUTPUT_OBJECT", "").strip()

    if not bucket_name:
        raise RuntimeError("DIO_OUTPUT_BUCKET is required")

    if not object_name:
        raise RuntimeError("DIO_OUTPUT_OBJECT is required")

    evidence_root = os.environ.get(
        "DIO_PHASE2_EVIDENCE_ROOT",
        DEFAULT_PHASE2_EVIDENCE_ROOT,
    ).strip()

    if not evidence_root.startswith("sha256:"):
        raise RuntimeError(
            "DIO_PHASE2_EVIDENCE_ROOT must be a sha256 digest"
        )

    now = datetime.now(timezone.utc)
    challenge_nonce = secrets.token_urlsafe(32)

    proposal = {
        "beast_object_type": "dio_cloud_witness_proposal",
        "version": "1.0",
        "phase": "DIO Phase 2",
        "purpose": "google_confidential_space_attestation",
        "evidence_root": evidence_root,
        "maximum_authority": "attestation_test_only",
    }

    proposal_digest = sha256_digest(canonical_json(proposal))

    world_state = {
        "phase": "DIO Phase 2",
        "provider": "google_cloud",
        "environment": "confidential_space",
        "evidence_root": evidence_root,
    }

    world_state_hash = sha256_digest(canonical_json(world_state))

    vote = {
        "beast_object_type": "dio_cloud_witness_vote",
        "version": "1.0",
        "node_id": "dio:gcp:semantic-witness-01",
        "platform": "google_confidential_space",
        "role": "semantic_witness",
        "decision": "approve_attestation_test_only",
        "proposal_digest": proposal_digest,
        "evidence_root": evidence_root,
        "world_state_hash": world_state_hash,
        "governance_epoch": "dio-phase2-gcp-attestation-001",
        "reason_codes": [
            "phase2_evidence_root_bound",
            "confidential_space_attestation_requested",
        ],
        "maximum_authority": "attestation_test_only",
        "issued_at": now.isoformat(),
        "expires_at": (
            now + timedelta(minutes=10)
        ).isoformat(),
    }

    vote_bytes = canonical_json(vote)
    vote_digest = sha256_digest(vote_bytes)

    binding = sha256_digest(
        vote_bytes
        + b"\n"
        + challenge_nonce.encode("utf-8")
    )

    attestation_token = request_attestation_token(
        audience=AUDIENCE,
        binding=binding,
    )

    packet = {
        "beast_object_type": "dio_google_attestation_packet",
        "version": "1.0",
        "provider": "google_cloud",
        "environment": "confidential_space",
        "vote": vote,
        "vote_digest": vote_digest,
        "challenge_nonce": challenge_nonce,
        "binding": binding,
        "audience": AUDIENCE,
        "attestation_token": attestation_token,
        "raw_provider_attestation_token_present": True,
        "maximum_authority": "attestation_test_only",
    }

    packet_without_digest = dict(packet)
    packet["packet_digest"] = sha256_digest(
        canonical_json(packet_without_digest)
    )

    upload_packet(
        packet=packet,
        bucket_name=bucket_name,
        object_name=object_name,
    )


if __name__ == "__main__":
    main()
