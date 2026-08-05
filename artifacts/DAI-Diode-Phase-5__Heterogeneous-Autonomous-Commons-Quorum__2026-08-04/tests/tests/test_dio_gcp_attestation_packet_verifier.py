from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes

from scripts.verify_dio_gcp_attestation_packet import canonical_json, sha256_digest, verify_packet


def test_google_confidential_space_packet_verifier_accepts_offline_jwks(tmp_path: Path) -> None:
    packet_path, jwks_path, expected = _write_fixture(tmp_path)

    result = verify_packet(
        packet_path=packet_path,
        expected_image_digest=expected["image_digest"],
        expected_image_reference=expected["image_reference"],
        expected_evidence_root=expected["evidence_root"],
        expected_instance=expected["instance"],
        expected_project=expected["project"],
        expected_zone=expected["zone"],
        require_current=True,
        evaluation_time="2026-08-04T19:17:03+00:00",
        verify_google_signature=True,
        jwks_file=jwks_path,
    )

    assert result["passed"] is True
    assert result["signature_verified"] is True
    assert result["gates"]["jwt_signature_rs256_google_jwks_valid"] is True
    assert result["red_gates"] == ()


def test_google_confidential_space_packet_verifier_rejects_tampered_signature(tmp_path: Path) -> None:
    packet_path, jwks_path, expected = _write_fixture(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    header, claims, signature = packet["attestation_token"].split(".")
    tampered_claims = json.loads(_b64decode(claims))
    tampered_claims["secboot"] = False
    packet["attestation_token"] = ".".join([header, _b64json(tampered_claims), signature])
    packet_body = dict(packet)
    packet_body.pop("packet_digest", None)
    packet["packet_digest"] = sha256_digest(canonical_json(packet_body))
    packet_path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")

    result = verify_packet(
        packet_path=packet_path,
        expected_image_digest=expected["image_digest"],
        expected_image_reference=expected["image_reference"],
        expected_evidence_root=expected["evidence_root"],
        expected_instance=expected["instance"],
        expected_project=expected["project"],
        expected_zone=expected["zone"],
        evaluation_time="2026-08-04T19:17:03+00:00",
        verify_google_signature=True,
        jwks_file=jwks_path,
    )

    assert result["passed"] is False
    assert result["signature_verified"] is False
    assert "jwt_signature_rs256_google_jwks_valid" in result["red_gates"]


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    kid = "test-google-confidential-space-kid"
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "kid": kid,
                "n": _b64int(public_numbers.n),
                "e": _b64int(public_numbers.e),
            }
        ]
    }
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(jwks, sort_keys=True), encoding="utf-8")

    expected = {
        "image_digest": "sha256:" + "1" * 64,
        "image_reference": "example.pkg.dev/repo/image@sha256:" + "1" * 64,
        "evidence_root": "sha256:" + "2" * 64,
        "instance": "dio-gcp-phase2-witness-test",
        "project": "dio-attested-witnesses",
        "zone": "africa-south1-a",
    }
    vote = {
        "beast_object_type": "dio_cloud_witness_vote",
        "evidence_root": expected["evidence_root"],
        "maximum_authority": "attestation_test_only",
        "world_state_hash": "sha256:" + "3" * 64,
    }
    challenge_nonce = "dio-test-nonce"
    binding = sha256_digest(canonical_json(vote) + b"\n" + challenge_nonce.encode("utf-8"))
    claims = {
        "aud": "dio://phase2/quorum/v1",
        "iss": "https://confidentialcomputing.googleapis.com",
        "sub": (
            "https://www.googleapis.com/compute/v1/projects/"
            f"{expected['project']}/zones/{expected['zone']}/instances/{expected['instance']}"
        ),
        "eat_nonce": binding,
        "secboot": True,
        "hwmodel": "GCP_AMD_SEV",
        "swname": "CONFIDENTIAL_SPACE",
        "iat": 1785870416,
        "nbf": 1785870416,
        "exp": 1785874016,
        "submods": {
            "container": {
                "image_digest": expected["image_digest"],
                "image_reference": expected["image_reference"],
                "env_override": {"DIO_PHASE2_EVIDENCE_ROOT": expected["evidence_root"]},
            },
            "gce": {
                "instance_name": expected["instance"],
                "project_id": expected["project"],
                "zone": expected["zone"],
            },
        },
    }
    token = _sign_jwt(private_key, {"alg": "RS256", "kid": kid, "typ": "JWT"}, claims)
    packet: dict[str, Any] = {
        "beast_object_type": "dio_google_attestation_packet",
        "attestation_token": token,
        "audience": "dio://phase2/quorum/v1",
        "binding": binding,
        "challenge_nonce": challenge_nonce,
        "maximum_authority": "attestation_test_only",
        "vote": vote,
        "vote_digest": sha256_digest(canonical_json(vote)),
    }
    packet["packet_digest"] = sha256_digest(canonical_json(packet))
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")
    return packet_path, jwks_path, expected


def _sign_jwt(private_key: rsa.RSAPrivateKey, header: dict[str, Any], claims: dict[str, Any]) -> str:
    signing_input = f"{_b64json(header)}.{_b64json(claims)}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode('ascii')}.{_b64(signature)}"


def _b64json(value: dict[str, Any]) -> str:
    return _b64(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _b64int(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return _b64(value.to_bytes(length, "big"))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding_text = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding_text)
