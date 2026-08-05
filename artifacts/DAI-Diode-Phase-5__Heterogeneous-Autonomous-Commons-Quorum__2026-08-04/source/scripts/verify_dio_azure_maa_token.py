#!/usr/bin/env python3
"""Verify an Azure Confidential VM MAA JWT for DIO cloud-witness evidence.

This verifier is intentionally separate from the Azure evidence harvester.  The
harvester proves that BEAST captured and digest-bound a token.  This script
checks the token itself: JWT shape, Azure Attestation issuer/JWKS binding,
RS256 signature, temporal validity, Confidential VM/SNP claims, and VM identity
binding against an Azure VM description captured by `az vm show -d`.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("token_file", type=Path)
    parser.add_argument("--vm-description-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--jwks-file", type=Path, default=None)
    parser.add_argument("--save-jwks", type=Path, default=None)
    parser.add_argument("--evaluation-time", default="")
    parser.add_argument("--verify-signature", action="store_true")
    args = parser.parse_args()
    result = verify(
        token_file=args.token_file,
        vm_description_file=args.vm_description_file,
        out=args.out,
        jwks_file=args.jwks_file,
        save_jwks=args.save_jwks,
        evaluation_time=args.evaluation_time,
        verify_signature=args.verify_signature,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


def verify(
    *,
    token_file: Path,
    vm_description_file: Path,
    out: Path | None = None,
    jwks_file: Path | None = None,
    save_jwks: Path | None = None,
    evaluation_time: str = "",
    verify_signature: bool = False,
) -> dict[str, Any]:
    token = token_file.read_text(encoding="utf-8").strip()
    vm = json.loads(vm_description_file.read_text(encoding="utf-8"))
    header, claims = _decode_jwt(token)
    now = _parse_time(evaluation_time) if evaluation_time else datetime.now(timezone.utc)

    jku = str(header.get("jku") or "")
    issuer = str(claims.get("iss") or "")
    isolation = claims.get("x-ms-isolation-tee") if isinstance(claims.get("x-ms-isolation-tee"), dict) else {}
    runtime = isolation.get("x-ms-runtime") if isinstance(isolation.get("x-ms-runtime"), dict) else {}
    vm_config = runtime.get("vm-configuration") if isinstance(runtime.get("vm-configuration"), dict) else {}
    vm_id_claim = str(claims.get("x-ms-azurevm-vmid") or vm_config.get("vmUniqueId") or "")
    described_vm_id = str(vm.get("vmId") or "")
    security = vm.get("securityProfile") if isinstance(vm.get("securityProfile"), dict) else {}
    temporal = _temporal(claims, now)
    signature = _verify_signature(
        token=token,
        header=header,
        jku=jku,
        jwks_file=jwks_file,
        save_jwks=save_jwks,
        verify_signature=verify_signature,
        now=now,
    )

    gates: dict[str, bool] = {
        "compact_jwt_shape": token.count(".") == 2,
        "jwt_alg_rs256": header.get("alg") == "RS256",
        "jwt_type_jwt": str(header.get("typ") or "").upper() == "JWT",
        "jwt_kid_present": bool(header.get("kid")),
        "jwt_jku_is_azure_attestation_https": _azure_attestation_jku(jku),
        "jwt_issuer_matches_jku_origin": issuer == _origin(jku),
        "jwt_temporal_order_valid": temporal["temporal_order_valid"],
        "jwt_currently_fresh": temporal["currently_fresh"],
        "azure_attestation_type_vm": claims.get("x-ms-attestation-type") == "azurevm",
        "azure_attestation_protocol_v3": str(claims.get("x-ms-azurevm-attestation-protocol-ver") or "").startswith("3."),
        "azure_secure_boot_claim_true": claims.get("secureboot") is True,
        "azure_isolation_tee_sev_snp": isolation.get("x-ms-attestation-type") == "sevsnpvm",
        "azure_compliance_status_cvm": isolation.get("x-ms-compliance-status") == "azure-compliant-cvm",
        "azure_vm_config_secure_boot_true": vm_config.get("secure-boot") is True,
        "azure_vm_config_tpm_enabled_true": vm_config.get("tpm-enabled") is True,
        "azure_vm_id_matches_description": _same_guid(vm_id_claim, described_vm_id),
        "azure_description_confidential_vm": str(security.get("securityType") or "").lower() == "confidentialvm",
        "azure_description_vtpm_enabled": (security.get("uefiSettings") or {}).get("vTpmEnabled") is True,
        "azure_description_secure_boot_enabled": (security.get("uefiSettings") or {}).get("secureBootEnabled") is True,
    }
    if verify_signature:
        gates["jwt_signature_rs256_azure_jwks_valid"] = signature["signature_verified"]
        gates["jwt_x5c_leaf_temporally_valid"] = signature["x5c_leaf_temporally_valid"]

    red_gates = [name for name, passed in gates.items() if not passed]
    result = {
        "beast_object_type": "dio_azure_maa_token_verification",
        "passed": not red_gates,
        "red_gates": red_gates,
        "gates": gates,
        "production_authority_allowed": False,
        "provider_calls_used": 0,
        "token_digest": sha256_digest({"azure_maa_token": token}),
        "vm_description_digest": sha256_digest(vm),
        "jwks_digest": signature.get("jwks_digest", ""),
        "signature": signature,
        "jwt_header": {
            "alg": header.get("alg", ""),
            "typ": header.get("typ", ""),
            "kid": header.get("kid", ""),
            "jku": jku,
        },
        "jwt_claim_summary": {
            "issuer": issuer,
            "issued_at": temporal["issued_at"],
            "not_before": temporal["not_before"],
            "expires_at": temporal["expires_at"],
            "attestation_type": claims.get("x-ms-attestation-type", ""),
            "attestation_protocol": claims.get("x-ms-azurevm-attestation-protocol-ver", ""),
            "secureboot": claims.get("secureboot", None),
            "vm_id": vm_id_claim,
            "isolation_attestation_type": isolation.get("x-ms-attestation-type", ""),
            "compliance_status": isolation.get("x-ms-compliance-status", ""),
            "snp_chip_family": isolation.get("x-ms-sevsnpvm-chip-family", ""),
            "snp_launchmeasurement_digest": sha256_digest({"launchmeasurement": isolation.get("x-ms-sevsnpvm-launchmeasurement", "")}),
            "pcr_count": len(claims.get("x-ms-azurevm-attested-pcrs") or []),
        },
        "vm_description_summary": {
            "id": vm.get("id", ""),
            "vmId": described_vm_id,
            "name": vm.get("name", ""),
            "resourceGroup": vm.get("resourceGroup", ""),
            "location": vm.get("location", ""),
            "vmSize": (vm.get("hardwareProfile") or {}).get("vmSize", ""),
            "securityType": security.get("securityType", ""),
            "vTpmEnabled": (security.get("uefiSettings") or {}).get("vTpmEnabled", None),
            "secureBootEnabled": (security.get("uefiSettings") or {}).get("secureBootEnabled", None),
        },
        "evaluation_time": now.isoformat(),
        "authority_boundary": (
            "Azure MAA compact JWT verified against Azure Attestation JWKS/x5c leaf and bound to "
            "Confidential VM identity. This is provider-service attestation verification, not an "
            "independent AMD VCEK reconstruction of the raw SNP report."
        ),
    }
    result["verification_digest"] = sha256_digest(result)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _decode_jwt(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        header_b64, claims_b64, _sig_b64 = token.split(".")
    except ValueError as exc:
        raise ValueError("Azure MAA token is not compact JWT") from exc
    return _b64_json(header_b64), _b64_json(claims_b64)


def _verify_signature(
    *,
    token: str,
    header: dict[str, Any],
    jku: str,
    jwks_file: Path | None,
    save_jwks: Path | None,
    verify_signature: bool,
    now: datetime,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "signature_requested": verify_signature,
        "signature_verified": False,
        "jwks_source": str(jwks_file) if jwks_file else jku,
        "jwks_digest": "",
        "kid_matched": False,
        "x5c_leaf_present": False,
        "x5c_leaf_temporally_valid": False,
        "error": "",
    }
    if not verify_signature:
        return result
    try:
        jwks = _load_jwks(jku=jku, jwks_file=jwks_file)
        result["jwks_digest"] = sha256_digest(jwks)
        if save_jwks:
            save_jwks.parent.mkdir(parents=True, exist_ok=True)
            save_jwks.write_text(json.dumps(jwks, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        keys = jwks.get("keys") if isinstance(jwks, dict) else None
        if not isinstance(keys, list):
            raise ValueError("JWKS missing keys list")
        key = next((row for row in keys if row.get("kid") == header.get("kid")), None)
        if not isinstance(key, dict):
            raise ValueError("JWKS does not contain token kid")
        result["kid_matched"] = True
        public_key = _public_key_from_jwk(key)
        signing_input, signature_b64 = token.rsplit(".", 1)
        public_key.verify(
            _b64_bytes(signature_b64),
            signing_input.encode("ascii"),
            padding.PKCS1v15(),
            SHA256(),
        )
        result["signature_verified"] = True
        x5c = key.get("x5c")
        if isinstance(x5c, list) and x5c:
            result["x5c_leaf_present"] = True
            cert = x509.load_der_x509_certificate(base64.b64decode(str(x5c[0])))
            not_before = _aware(cert.not_valid_before_utc)
            not_after = _aware(cert.not_valid_after_utc)
            result["x5c_leaf_temporally_valid"] = not_before <= now <= not_after
            result["x5c_leaf_not_before"] = not_before.isoformat()
            result["x5c_leaf_not_after"] = not_after.isoformat()
            result["x5c_leaf_subject"] = cert.subject.rfc4514_string()
            result["x5c_leaf_issuer"] = cert.issuer.rfc4514_string()
    except Exception as exc:  # noqa: BLE001 - verifier reports exact failure as data.
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _load_jwks(*, jku: str, jwks_file: Path | None) -> dict[str, Any]:
    if jwks_file:
        return json.loads(jwks_file.read_text(encoding="utf-8"))
    if not _azure_attestation_jku(jku):
        raise ValueError(f"refusing non-Azure-Attestation jku: {jku}")
    request = Request(jku, headers={"User-Agent": "BEAST-DIO-Azure-Attestation-Verifier/1.0"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - guarded by host allow-list above.
        return json.loads(response.read())


def _public_key_from_jwk(key: dict[str, Any]) -> rsa.RSAPublicKey:
    x5c = key.get("x5c")
    if isinstance(x5c, list) and x5c:
        cert = x509.load_der_x509_certificate(base64.b64decode(str(x5c[0])))
        public_key = cert.public_key()
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("x5c leaf key is not RSA")
        return public_key
    n = int.from_bytes(_b64_bytes(str(key["n"])), "big")
    e = int.from_bytes(_b64_bytes(str(key["e"])), "big")
    return rsa.RSAPublicNumbers(e=e, n=n).public_key()


def _temporal(claims: dict[str, Any], now: datetime) -> dict[str, Any]:
    iat = _epoch(claims.get("iat"))
    nbf = _epoch(claims.get("nbf"))
    exp = _epoch(claims.get("exp"))
    order = bool(iat and nbf and exp and iat <= nbf <= exp)
    fresh = bool(nbf and exp and nbf <= now <= exp)
    return {
        "issued_at": "" if iat is None else iat.isoformat(),
        "not_before": "" if nbf is None else nbf.isoformat(),
        "expires_at": "" if exp is None else exp.isoformat(),
        "temporal_order_valid": order,
        "currently_fresh": fresh,
    }


def _b64_json(value: str) -> dict[str, Any]:
    parsed = json.loads(_b64_bytes(value))
    if not isinstance(parsed, dict):
        raise ValueError("JWT part decoded to non-object JSON")
    return parsed


def _b64_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _azure_attestation_jku(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname is not None and parsed.hostname.endswith(".attest.azure.net")


def _same_guid(left: str, right: str) -> bool:
    return left.replace("-", "").lower() == right.replace("-", "").lower() and bool(left and right)


def _epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
