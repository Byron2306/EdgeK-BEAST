#!/usr/bin/env python3
"""Verify a DIO Google Confidential Space attestation packet.

This verifier is intentionally split into two layers:

1. Local deterministic packet verification:
   - recompute packet_digest;
   - recompute vote_digest;
   - recompute binding from vote bytes + challenge nonce;
   - decode the provider JWT and compare its claims to the packet.

2. Optional provider-signature verification:
   - when --verify-google-signature is supplied, fetch or load Google's
     Confidential Space JWKS, select the JWT kid, and verify the RS256
     signature over the compact token's original signing input.
   - --jwks-file provides a frozen/offline verifier path for reproduction
     capsules after Google's live keys rotate.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes


GOOGLE_CONFIDENTIAL_COMPUTING_ISSUER = "https://confidentialcomputing.googleapis.com"
GOOGLE_CONFIDENTIAL_COMPUTING_JWKS_URI = (
    "https://www.googleapis.com/service_accounts/v1/metadata/jwk/"
    "signer@confidentialspace-sign.iam.gserviceaccount.com"
)
CONFIDENTIAL_SPACE_SWNAME = "CONFIDENTIAL_SPACE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--expected-image-digest", default="")
    parser.add_argument("--expected-image-reference", default="")
    parser.add_argument("--expected-evidence-root", default="")
    parser.add_argument("--expected-instance", default="")
    parser.add_argument("--expected-project", default="")
    parser.add_argument("--expected-zone", default="")
    parser.add_argument("--require-current", action="store_true")
    parser.add_argument(
        "--evaluation-time",
        default="",
        help="ISO-8601 UTC evaluation time for deterministic temporal checks; defaults to now.",
    )
    parser.add_argument(
        "--verify-google-signature",
        action="store_true",
        help="Verify the compact JWT RS256 signature against Google Confidential Space JWKS.",
    )
    parser.add_argument(
        "--jwks-uri",
        default=GOOGLE_CONFIDENTIAL_COMPUTING_JWKS_URI,
        help="JWKS URI used when --verify-google-signature is set and --jwks-file is not supplied.",
    )
    parser.add_argument(
        "--jwks-file",
        type=Path,
        default=None,
        help="Offline JWKS JSON file for signature verification/reproduction.",
    )
    parser.add_argument(
        "--save-jwks",
        type=Path,
        default=None,
        help="Write the fetched or loaded JWKS JSON to this path for audit custody.",
    )
    args = parser.parse_args()

    result = verify_packet(
        packet_path=args.packet,
        expected_image_digest=args.expected_image_digest,
        expected_image_reference=args.expected_image_reference,
        expected_evidence_root=args.expected_evidence_root,
        expected_instance=args.expected_instance,
        expected_project=args.expected_project,
        expected_zone=args.expected_zone,
        require_current=args.require_current,
        evaluation_time=args.evaluation_time,
        verify_google_signature=args.verify_google_signature,
        jwks_uri=args.jwks_uri,
        jwks_file=args.jwks_file,
        save_jwks=args.save_jwks,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 2


def verify_packet(
    *,
    packet_path: Path,
    expected_image_digest: str = "",
    expected_image_reference: str = "",
    expected_evidence_root: str = "",
    expected_instance: str = "",
    expected_project: str = "",
    expected_zone: str = "",
    require_current: bool = False,
    evaluation_time: str = "",
    verify_google_signature: bool = False,
    jwks_uri: str = GOOGLE_CONFIDENTIAL_COMPUTING_JWKS_URI,
    jwks_file: Path | None = None,
    save_jwks: Path | None = None,
) -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    token = str(packet.get("attestation_token") or "")
    header: dict[str, Any] = {}
    claims: dict[str, Any] = {}
    token_error = ""
    try:
        header, claims = _decode_jwt(token)
    except Exception as exc:  # noqa: BLE001 - verifier result should explain all failures
        token_error = f"{type(exc).__name__}: {exc}"

    vote = packet.get("vote") if isinstance(packet.get("vote"), dict) else {}
    packet_body = dict(packet)
    claimed_packet_digest = str(packet_body.pop("packet_digest", ""))
    recomputed_packet_digest = sha256_digest(canonical_json(packet_body))
    recomputed_vote_digest = sha256_digest(canonical_json(vote))
    challenge_nonce = str(packet.get("challenge_nonce") or "")
    recomputed_binding = sha256_digest(canonical_json(vote) + b"\n" + challenge_nonce.encode("utf-8"))

    submods = claims.get("submods") if isinstance(claims.get("submods"), dict) else {}
    container = submods.get("container") if isinstance(submods.get("container"), dict) else {}
    gce = submods.get("gce") if isinstance(submods.get("gce"), dict) else {}
    env_override = container.get("env_override") if isinstance(container.get("env_override"), dict) else {}
    temporal = _temporal_claims(claims, evaluation_time=evaluation_time)
    signature = _verify_signature(
        token=token,
        header=header,
        verify=verify_google_signature,
        jwks_uri=jwks_uri,
        jwks_file=jwks_file,
        save_jwks=save_jwks,
    )

    gates: dict[str, bool] = {
        "packet_object_type": packet.get("beast_object_type") == "dio_google_attestation_packet",
        "packet_digest_recomputes": claimed_packet_digest == recomputed_packet_digest,
        "vote_digest_recomputes": packet.get("vote_digest") == recomputed_vote_digest,
        "binding_recomputes": packet.get("binding") == recomputed_binding,
        "raw_token_present": bool(token),
        "compact_jwt_shape": token.count(".") == 2 and not token_error,
        "jwt_alg_rs256": header.get("alg") == "RS256",
        "jwt_issuer_google_confidential_computing": claims.get("iss") == GOOGLE_CONFIDENTIAL_COMPUTING_ISSUER,
        "jwt_audience_matches_packet": claims.get("aud") == packet.get("audience"),
        "jwt_nonce_binds_packet": _nonce_matches(claims.get("eat_nonce"), packet.get("binding")),
        "jwt_subject_present": bool(claims.get("sub")),
        "jwt_secure_boot_true": claims.get("secboot") is True,
        "jwt_confidential_space_swname": claims.get("swname") == CONFIDENTIAL_SPACE_SWNAME,
        "jwt_hwmodel_present": str(claims.get("hwmodel") or "").startswith("GCP_"),
        "jwt_container_image_digest_present": str(container.get("image_digest") or "").startswith("sha256:"),
        "jwt_container_image_reference_present": bool(container.get("image_reference")),
        "jwt_env_override_evidence_root_matches_vote": env_override.get("DIO_PHASE2_EVIDENCE_ROOT") == vote.get("evidence_root"),
        "jwt_temporal_order_valid": temporal["temporal_order_valid"],
        "authority_is_test_only": packet.get("maximum_authority") == "attestation_test_only"
        and vote.get("maximum_authority") == "attestation_test_only",
    }
    if expected_image_digest:
        gates["expected_image_digest_matches_jwt"] = container.get("image_digest") == expected_image_digest
    if expected_image_reference:
        gates["expected_image_reference_matches_jwt"] = container.get("image_reference") == expected_image_reference
    if expected_evidence_root:
        gates["expected_evidence_root_matches_vote"] = vote.get("evidence_root") == expected_evidence_root
        gates["expected_evidence_root_matches_env_override"] = env_override.get("DIO_PHASE2_EVIDENCE_ROOT") == expected_evidence_root
    if expected_instance:
        gates["expected_instance_matches_jwt"] = gce.get("instance_name") == expected_instance
    if expected_project:
        gates["expected_project_matches_jwt"] = gce.get("project_id") == expected_project
    if expected_zone:
        gates["expected_zone_matches_jwt"] = gce.get("zone") == expected_zone
    if require_current:
        gates["jwt_currently_fresh"] = temporal["currently_fresh"]
    if verify_google_signature:
        gates["jwt_signature_rs256_google_jwks_valid"] = signature["signature_verified"]

    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    result = {
        "beast_object_type": "dio_gcp_attestation_packet_verification",
        "packet": str(packet_path),
        "passed": not red_gates,
        "red_gates": red_gates,
        "gates": gates,
        "packet_digest": claimed_packet_digest,
        "recomputed_packet_digest": recomputed_packet_digest,
        "vote_digest": packet.get("vote_digest"),
        "recomputed_vote_digest": recomputed_vote_digest,
        "binding": packet.get("binding"),
        "recomputed_binding": recomputed_binding,
        "jwt_header": {
            "alg": header.get("alg"),
            "kid": header.get("kid"),
            "typ": header.get("typ"),
        },
        "jwt_claim_summary": {
            "aud": claims.get("aud"),
            "iss": claims.get("iss"),
            "sub": claims.get("sub"),
            "eat_nonce": claims.get("eat_nonce"),
            "secboot": claims.get("secboot"),
            "hwmodel": claims.get("hwmodel"),
            "swname": claims.get("swname"),
            "dbgstat": claims.get("dbgstat"),
            "container_image_digest": container.get("image_digest"),
            "container_image_reference": container.get("image_reference"),
            "gce_project_id": gce.get("project_id"),
            "gce_zone": gce.get("zone"),
            "gce_instance_name": gce.get("instance_name"),
            "gce_instance_id": gce.get("instance_id"),
            "env_override": env_override,
        },
        "temporal": temporal,
        "token_error": token_error,
        "signature_verified": signature["signature_verified"],
        "signature_verification": signature,
        "signature_boundary": (
            "JWT RS256 signature verified against Google Confidential Space JWKS; "
            "hardware claim remains bounded to the Google-attested token semantics and does not independently "
            "verify lower-level SNP/TDX quote material."
            if signature["signature_verified"]
            else signature["signature_boundary"]
        ),
        "production_authority_allowed": False,
    }
    result["verification_digest"] = sha256_digest(canonical_json(result))
    return result


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _decode_jwt(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("token is not a compact JWT")
    return _decode_part(parts[0]), _decode_part(parts[1])


def _verify_signature(
    *,
    token: str,
    header: dict[str, Any],
    verify: bool,
    jwks_uri: str,
    jwks_file: Path | None,
    save_jwks: Path | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "requested": verify,
        "signature_verified": False,
        "algorithm": header.get("alg"),
        "kid": header.get("kid"),
        "jwks_uri": jwks_uri,
        "jwks_file": str(jwks_file) if jwks_file else "",
        "jwks_digest": "",
        "matching_key_found": False,
        "error": "",
        "signature_boundary": "JWT RS256 signature was not requested; run with --verify-google-signature.",
    }
    if not verify:
        return result
    if header.get("alg") != "RS256":
        result["error"] = f"unsupported JWT alg: {header.get('alg')!r}"
        result["signature_boundary"] = "JWT signature verification requested but token alg was not RS256."
        return result
    kid = str(header.get("kid") or "")
    if not kid:
        result["error"] = "JWT header missing kid"
        result["signature_boundary"] = "JWT signature verification requested but token header has no kid."
        return result

    try:
        jwks = _load_jwks(jwks_uri=jwks_uri, jwks_file=jwks_file)
        result["jwks_digest"] = sha256_digest(canonical_json(jwks))
        if save_jwks:
            save_jwks.parent.mkdir(parents=True, exist_ok=True)
            save_jwks.write_text(json.dumps(jwks, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        keys = jwks.get("keys") if isinstance(jwks, dict) else None
        if not isinstance(keys, list):
            raise ValueError("JWKS did not contain a keys list")
        jwk = next((item for item in keys if isinstance(item, dict) and item.get("kid") == kid), None)
        result["matching_key_found"] = jwk is not None
        if jwk is None:
            raise ValueError(f"JWKS did not contain kid {kid}")
        _verify_rs256(token, jwk)
    except Exception as exc:  # noqa: BLE001 - verifier must return a receipt, not crash mid-proof
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["signature_boundary"] = "JWT signature verification requested but failed."
        return result

    result["signature_verified"] = True
    result["signature_boundary"] = "JWT RS256 signature verified against Google Confidential Space JWKS."
    return result


def _load_jwks(*, jwks_uri: str, jwks_file: Path | None) -> dict[str, Any]:
    if jwks_file:
        parsed = json.loads(jwks_file.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JWKS file did not decode to a JSON object")
        return parsed
    request = Request(jwks_uri, headers={"User-Agent": "BEAST-DIO-GCP-Attestation-Verifier/1.0"})
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit Google JWKS verifier endpoint
            body = response.read()
    except URLError as exc:
        raise RuntimeError(f"failed to fetch JWKS from {jwks_uri}: {exc}") from exc
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("JWKS endpoint did not decode to a JSON object")
    return parsed


def _verify_rs256(token: str, jwk: dict[str, Any]) -> None:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("token is not a compact JWT")
    if jwk.get("kty") != "RSA":
        raise ValueError(f"JWK kty is not RSA: {jwk.get('kty')!r}")
    if jwk.get("alg") not in (None, "RS256"):
        raise ValueError(f"JWK alg is not RS256: {jwk.get('alg')!r}")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    signature = _base64url_decode(parts[2])
    public_key = rsa.RSAPublicNumbers(
        e=int.from_bytes(_base64url_decode(str(jwk["e"])), "big"),
        n=int.from_bytes(_base64url_decode(str(jwk["n"])), "big"),
    ).public_key()
    public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())


def _base64url_decode(value: str) -> bytes:
    padding_text = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding_text)


def _nonce_matches(value: Any, expected: Any) -> bool:
    if isinstance(value, list):
        return expected in value
    return value == expected


def _decode_part(value: str) -> dict[str, Any]:
    decoded = _base64url_decode(value)
    parsed = json.loads(decoded)
    if not isinstance(parsed, dict):
        raise ValueError("JWT part did not decode to a JSON object")
    return parsed


def _temporal_claims(claims: dict[str, Any], *, evaluation_time: str = "") -> dict[str, Any]:
    now_dt = _parse_evaluation_time(evaluation_time) if evaluation_time else datetime.now(timezone.utc)
    now = now_dt.timestamp()
    iat = _number(claims.get("iat"))
    nbf = _number(claims.get("nbf"))
    exp = _number(claims.get("exp"))
    return {
        "iat": iat,
        "nbf": nbf,
        "exp": exp,
        "temporal_order_valid": iat is not None and nbf is not None and exp is not None and nbf <= iat < exp,
        "currently_fresh": nbf is not None and exp is not None and nbf <= now < exp,
        "evaluation_time": now_dt.replace(microsecond=0).isoformat(),
    }


def _parse_evaluation_time(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
