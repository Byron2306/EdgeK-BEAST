#!/usr/bin/env python3
"""Verify an AWS NitroTPM/Nitro attestation document for DIO admission.

This verifier follows the AWS Nitro attestation validation shape:

1. Decode the CBOR COSE_Sign1 object.
2. Decode the attestation-document payload.
3. Verify the x509 chain to the pinned AWS Nitro root.
4. Verify the COSE ES384 signature with the attestation leaf certificate.
5. Verify DIO policy bindings such as nonce, user_data, module/instance and PCRs.

It intentionally emits a receipt even on failure.  Production authority remains
controlled by the caller's policy; this script proves cryptographic document
validity and selected semantic bindings.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from zipfile import ZipFile

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils


AWS_NITRO_ROOT_ZIP_URL = "https://aws-nitro-enclaves.amazonaws.com/AWS_NitroEnclaves_Root-G1.zip"
AWS_NITRO_ROOT_SHA256_COLON = "64:1A:03:21:A3:E2:44:EF:E4:56:46:31:95:D6:06:31:7E:D7:CD:CC:3C:17:56:E0:98:93:F3:C6:8F:79:BB:5B"
AWS_NITRO_ROOT_SHA256_HEX = AWS_NITRO_ROOT_SHA256_COLON.replace(":", "").lower()
COSE_ALG_ES384 = -35


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--root-pem", type=Path, default=None)
    parser.add_argument("--root-zip", type=Path, default=None)
    parser.add_argument("--fetch-root", action="store_true")
    parser.add_argument("--expected-nonce-hex", default="")
    parser.add_argument("--expected-user-data-file", type=Path, default=None)
    parser.add_argument("--expected-module-id", default="")
    parser.add_argument("--expected-instance-id", default="")
    parser.add_argument("--expected-digest", default="SHA384")
    parser.add_argument("--expected-pcr", action="append", default=[])
    parser.add_argument("--expected-pcr-file", type=Path, default=None)
    parser.add_argument("--evaluation-time", default="")
    args = parser.parse_args()

    result = verify_document(
        document_path=args.document,
        root_pem=args.root_pem,
        root_zip=args.root_zip,
        fetch_root=args.fetch_root,
        expected_nonce_hex=args.expected_nonce_hex,
        expected_user_data_file=args.expected_user_data_file,
        expected_module_id=args.expected_module_id,
        expected_instance_id=args.expected_instance_id,
        expected_digest=args.expected_digest,
        expected_pcr=args.expected_pcr,
        expected_pcr_file=args.expected_pcr_file,
        evaluation_time=args.evaluation_time,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 2


def verify_document(
    *,
    document_path: Path,
    root_pem: Path | None = None,
    root_zip: Path | None = None,
    fetch_root: bool = False,
    expected_nonce_hex: str = "",
    expected_user_data_file: Path | None = None,
    expected_module_id: str = "",
    expected_instance_id: str = "",
    expected_digest: str = "SHA384",
    expected_pcr: list[str] | tuple[str, ...] = (),
    expected_pcr_file: Path | None = None,
    evaluation_time: str = "",
) -> dict[str, Any]:
    raw = document_path.read_bytes()
    root_cert, root_source = _load_root_cert(root_pem=root_pem, root_zip=root_zip, fetch_root=fetch_root)
    evaluation_dt = _parse_time(evaluation_time) if evaluation_time else None
    gates: dict[str, bool] = {}
    errors: list[str] = []
    details: dict[str, Any] = {}

    try:
        cose = _decode_cose_sign1(raw)
        gates["cose_sign1_shape"] = True
        protected_map = _decode_cbor(cose.protected)
        gates["protected_header_decodes"] = isinstance(protected_map, dict)
        gates["protected_alg_es384"] = protected_map.get(1) == COSE_ALG_ES384
        payload = _decode_cbor(cose.payload)
        gates["payload_decodes"] = isinstance(payload, dict)
        required = ("module_id", "digest", "timestamp", "nitrotpm_pcrs", "certificate", "cabundle")
        gates["required_fields_present"] = all(name in payload for name in required)
    except Exception as exc:  # noqa: BLE001 - receipt should capture fail-closed reason
        payload = {}
        cose = None
        protected_map = {}
        gates["cose_sign1_shape"] = False
        errors.append(f"decode_failed:{type(exc).__name__}:{exc}")

    leaf_cert = None
    chain_result: ChainResult | None = None
    if payload:
        details["module_id"] = str(payload.get("module_id") or "")
        details["digest"] = str(payload.get("digest") or "")
        details["timestamp_ms"] = int(payload.get("timestamp") or 0)
        details["raw_document_digest"] = _sha256(raw)
        details["payload_digest"] = _sha256(cose.payload if cose else b"")
        details["protected_header"] = protected_map
        details["pcrs"] = _normalize_pcrs(payload.get("nitrotpm_pcrs") or {})
        details["expected_pcr_count"] = len(_expected_pcr_policy(expected_pcr, expected_pcr_file))
        details["nonce_digest"] = _sha256(payload.get("nonce") or b"") if isinstance(payload.get("nonce"), bytes) else ""
        details["user_data_digest"] = (
            _sha256(payload.get("user_data") or b"") if isinstance(payload.get("user_data"), bytes) else ""
        )
        details["cabundle_count"] = len(payload.get("cabundle") or [])
        try:
            leaf_cert = x509.load_der_x509_certificate(payload["certificate"])
            chain_result = _verify_chain(
                leaf_cert=leaf_cert,
                cabundle=[x509.load_der_x509_certificate(item) for item in payload.get("cabundle") or []],
                root_cert=root_cert,
                validation_time=_timestamp_dt(payload),
            )
            gates["aws_root_fingerprint_pinned"] = _fingerprint_hex(root_cert) == AWS_NITRO_ROOT_SHA256_HEX
            gates["certificate_chain_verified"] = chain_result.verified
            details["certificate_chain"] = chain_result.to_dict()
        except Exception as exc:  # noqa: BLE001
            gates["aws_root_fingerprint_pinned"] = _fingerprint_hex(root_cert) == AWS_NITRO_ROOT_SHA256_HEX
            gates["certificate_chain_verified"] = False
            errors.append(f"chain_failed:{type(exc).__name__}:{exc}")

        if leaf_cert is not None and cose is not None:
            try:
                _verify_cose_signature(cose=cose, leaf_cert=leaf_cert)
                gates["cose_signature_verified"] = True
            except Exception as exc:  # noqa: BLE001
                gates["cose_signature_verified"] = False
                errors.append(f"signature_failed:{type(exc).__name__}:{exc}")

        gates["digest_matches_expected"] = str(payload.get("digest") or "") == expected_digest
        gates["module_id_matches_expected"] = (
            True if not expected_module_id else str(payload.get("module_id") or "") == expected_module_id
        )
        gates["instance_id_bound"] = (
            True if not expected_instance_id else str(payload.get("module_id") or "").startswith(expected_instance_id)
        )
        gates["nonce_matches_expected"] = _expected_nonce_matches(payload.get("nonce"), expected_nonce_hex)
        gates["user_data_matches_expected"] = _expected_user_data_matches(payload.get("user_data"), expected_user_data_file)
        gates["pcr_policy_matches"] = _expected_pcrs_match(details["pcrs"], expected_pcr, expected_pcr_file)
        gates["timestamp_in_certificate_validity"] = _timestamp_in_leaf_validity(payload, leaf_cert)
        gates["timestamp_not_in_future"] = _timestamp_not_in_future(payload, evaluation_dt)

    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    result = {
        "beast_object_type": "dio_aws_nitro_attestation_document_verification",
        "document": str(document_path),
        "root_source": root_source,
        "root_fingerprint_sha256": _fingerprint_colon(root_cert),
        "passed": not red_gates,
        "red_gates": red_gates,
        "gates": gates,
        "details": details,
        "errors": errors,
        "production_authority_allowed": False,
        "authority_boundary": (
            "aws_nitro_cose_x509_pcr_document_verified; DIO policy still controls production authority"
        ),
    }
    result["verification_digest"] = _sha256_json(result)
    return result


@dataclass(frozen=True, slots=True)
class CoseSign1:
    protected: bytes
    unprotected: dict[Any, Any]
    payload: bytes
    signature: bytes


@dataclass(frozen=True, slots=True)
class ChainResult:
    verified: bool
    subjects: tuple[str, ...]
    issuers: tuple[str, ...]
    root_fingerprint_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "subjects": self.subjects,
            "issuers": self.issuers,
            "root_fingerprint_sha256": self.root_fingerprint_sha256,
        }


def _decode_cose_sign1(raw: bytes) -> CoseSign1:
    obj = _decode_cbor(raw)
    if isinstance(obj, CborTag):
        if obj.tag != 18:
            raise ValueError(f"unexpected COSE tag {obj.tag}")
        obj = obj.value
    if not isinstance(obj, list) or len(obj) != 4:
        raise ValueError("COSE_Sign1 must be a 4-item array")
    protected, unprotected, payload, signature = obj
    if not isinstance(protected, bytes):
        raise ValueError("COSE protected header must be bytes")
    if not isinstance(unprotected, dict):
        raise ValueError("COSE unprotected header must be a map")
    if not isinstance(payload, bytes):
        raise ValueError("COSE payload must be bytes")
    if not isinstance(signature, bytes):
        raise ValueError("COSE signature must be bytes")
    if len(signature) != 96:
        raise ValueError("ES384 COSE signature must be 96 raw bytes")
    return CoseSign1(protected=protected, unprotected=unprotected, payload=payload, signature=signature)


def _verify_cose_signature(*, cose: CoseSign1, leaf_cert: x509.Certificate) -> None:
    sig_structure = _encode_cbor(["Signature1", cose.protected, b"", cose.payload])
    r = int.from_bytes(cose.signature[:48], "big")
    s = int.from_bytes(cose.signature[48:], "big")
    der_signature = utils.encode_dss_signature(r, s)
    public_key = leaf_cert.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise ValueError("Nitro attestation leaf key must be EC")
    public_key.verify(der_signature, sig_structure, ec.ECDSA(hashes.SHA384()))


def _verify_chain(
    *,
    leaf_cert: x509.Certificate,
    cabundle: list[x509.Certificate],
    root_cert: x509.Certificate,
    validation_time: datetime | None,
) -> ChainResult:
    if _fingerprint_hex(root_cert) != AWS_NITRO_ROOT_SHA256_HEX:
        raise ValueError("AWS Nitro root fingerprint mismatch")
    certs = [leaf_cert, *cabundle, root_cert]
    by_subject = {cert.subject.rfc4514_string(): cert for cert in certs}
    subjects: list[str] = []
    issuers: list[str] = []
    current = leaf_cert
    for _ in range(len(certs) + 1):
        subjects.append(current.subject.rfc4514_string())
        issuers.append(current.issuer.rfc4514_string())
        if validation_time is not None:
            _require_cert_valid_at(current, validation_time)
        if current.subject == current.issuer:
            if _fingerprint_hex(current) != AWS_NITRO_ROOT_SHA256_HEX:
                raise ValueError("certificate chain terminated at non-AWS root")
            _verify_cert_signature(current, current)
            return ChainResult(
                verified=True,
                subjects=tuple(subjects),
                issuers=tuple(issuers),
                root_fingerprint_sha256=_fingerprint_colon(current),
            )
        issuer = by_subject.get(current.issuer.rfc4514_string())
        if issuer is None:
            raise ValueError(f"missing issuer {current.issuer.rfc4514_string()}")
        _verify_cert_signature(current, issuer)
        current = issuer
    raise ValueError("certificate chain loop or excessive depth")


def _verify_cert_signature(child: x509.Certificate, issuer: x509.Certificate) -> None:
    key = issuer.public_key()
    algorithm = child.signature_hash_algorithm
    if isinstance(key, ec.EllipticCurvePublicKey):
        key.verify(child.signature, child.tbs_certificate_bytes, ec.ECDSA(algorithm))
        return
    if isinstance(key, rsa.RSAPublicKey):
        key.verify(child.signature, child.tbs_certificate_bytes, padding.PKCS1v15(), algorithm)
        return
    raise ValueError("unsupported certificate public key type")


def _load_root_cert(*, root_pem: Path | None, root_zip: Path | None, fetch_root: bool) -> tuple[x509.Certificate, str]:
    if root_pem is not None:
        return _load_pem_cert(root_pem.read_bytes()), str(root_pem)
    if root_zip is not None:
        with ZipFile(root_zip) as archive:
            return _load_pem_cert(archive.read("root.pem")), str(root_zip)
    if fetch_root:
        with urlopen(AWS_NITRO_ROOT_ZIP_URL, timeout=20) as response:  # nosec: pinned fingerprint checked below
            data = response.read()
        from io import BytesIO

        with ZipFile(BytesIO(data)) as archive:
            return _load_pem_cert(archive.read("root.pem")), AWS_NITRO_ROOT_ZIP_URL
    raise ValueError("root certificate required: pass --root-pem, --root-zip or --fetch-root")


def _load_pem_cert(data: bytes) -> x509.Certificate:
    return x509.load_pem_x509_certificate(data)


def _require_cert_valid_at(cert: x509.Certificate, when: datetime) -> None:
    start = cert.not_valid_before_utc
    end = cert.not_valid_after_utc
    if not (start <= when <= end):
        raise ValueError(f"certificate not valid at {when.isoformat()}: {cert.subject.rfc4514_string()}")


def _timestamp_dt(payload: dict[str, Any]) -> datetime | None:
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, int):
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)


def _timestamp_in_leaf_validity(payload: dict[str, Any], leaf_cert: x509.Certificate | None) -> bool:
    when = _timestamp_dt(payload)
    if when is None or leaf_cert is None:
        return False
    return leaf_cert.not_valid_before_utc <= when <= leaf_cert.not_valid_after_utc


def _timestamp_not_in_future(payload: dict[str, Any], evaluation_time: datetime | None) -> bool:
    if evaluation_time is None:
        return True
    when = _timestamp_dt(payload)
    if when is None:
        return False
    return when <= evaluation_time


def _expected_nonce_matches(value: Any, expected_nonce_hex: str) -> bool:
    if not expected_nonce_hex:
        return True
    try:
        expected = bytes.fromhex(expected_nonce_hex)
    except ValueError:
        return False
    return isinstance(value, bytes) and value == expected


def _expected_user_data_matches(value: Any, expected_user_data_file: Path | None) -> bool:
    if expected_user_data_file is None:
        return True
    return isinstance(value, bytes) and value == expected_user_data_file.read_bytes()


def _expected_pcrs_match(
    actual: dict[str, str],
    expected_pcr: list[str] | tuple[str, ...],
    expected_pcr_file: Path | None = None,
) -> bool:
    for index, expected in _expected_pcr_policy(expected_pcr, expected_pcr_file).items():
        if actual.get(index) != expected:
            return False
    return True


def _expected_pcr_policy(
    expected_pcr: list[str] | tuple[str, ...],
    expected_pcr_file: Path | None = None,
) -> dict[str, str]:
    policy: dict[str, str] = {}
    if expected_pcr_file is not None:
        payload = json.loads(expected_pcr_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("expected PCR file must be a JSON object")
        source = payload.get("pcrs", payload)
        if not isinstance(source, dict):
            raise ValueError("expected PCR file pcrs must be a JSON object")
        for index, expected in source.items():
            policy[str(int(index))] = str(expected).lower().removeprefix("0x")
    for item in expected_pcr:
        if "=" not in item:
            raise ValueError("expected PCR must use INDEX=HEX")
        index, expected = item.split("=", 1)
        policy[str(int(index))] = expected.lower().removeprefix("0x")
    return policy


def _normalize_pcrs(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, int) and isinstance(item, bytes):
            out[str(key)] = item.hex()
        elif isinstance(item, int) and isinstance(key, bytes):
            out[str(item)] = key.hex()
    return dict(sorted(out.items(), key=lambda row: int(row[0])))


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _fingerprint_hex(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def _fingerprint_colon(cert: x509.Certificate) -> str:
    value = _fingerprint_hex(cert).upper()
    return ":".join(value[i : i + 2] for i in range(0, len(value), 2))


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class CborTag:
    tag: int
    value: Any


class _Break:
    pass


BREAK = _Break()


class CborDecoder:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def read(self, size: int) -> bytes:
        if self.offset + size > len(self.data):
            raise ValueError("truncated CBOR")
        value = self.data[self.offset : self.offset + size]
        self.offset += size
        return value

    def decode(self) -> Any:
        first = self.read(1)[0]
        if first == 0xFF:
            return BREAK
        major = first >> 5
        info = first & 0x1F
        arg = self._arg(info)
        if major == 0:
            return arg
        if major == 1:
            return -1 - int(arg)
        if major == 2:
            return self._bytes(arg)
        if major == 3:
            return self._text(arg)
        if major == 4:
            return self._array(arg)
        if major == 5:
            return self._map(arg)
        if major == 6:
            return CborTag(int(arg), self.decode())
        if major == 7:
            return self._simple(info, arg)
        raise ValueError(f"unsupported CBOR major type {major}")

    def _arg(self, info: int) -> int | None:
        if info < 24:
            return info
        if info == 24:
            return self.read(1)[0]
        if info == 25:
            return int.from_bytes(self.read(2), "big")
        if info == 26:
            return int.from_bytes(self.read(4), "big")
        if info == 27:
            return int.from_bytes(self.read(8), "big")
        if info == 31:
            return None
        raise ValueError(f"invalid CBOR additional info {info}")

    def _bytes(self, size: int | None) -> bytes:
        if size is not None:
            return self.read(size)
        parts: list[bytes] = []
        while True:
            item = self.decode()
            if item is BREAK:
                return b"".join(parts)
            if not isinstance(item, bytes):
                raise ValueError("indefinite bytes chunk is not bytes")
            parts.append(item)

    def _text(self, size: int | None) -> str:
        if size is not None:
            return self.read(size).decode("utf-8")
        parts: list[str] = []
        while True:
            item = self.decode()
            if item is BREAK:
                return "".join(parts)
            if not isinstance(item, str):
                raise ValueError("indefinite text chunk is not text")
            parts.append(item)

    def _array(self, size: int | None) -> list[Any]:
        items: list[Any] = []
        if size is None:
            while True:
                item = self.decode()
                if item is BREAK:
                    return items
                items.append(item)
        return [self.decode() for _ in range(size)]

    def _map(self, size: int | None) -> dict[Any, Any]:
        items: dict[Any, Any] = {}
        if size is None:
            while True:
                key = self.decode()
                if key is BREAK:
                    return items
                items[key] = self.decode()
        for _ in range(size):
            key = self.decode()
            items[key] = self.decode()
        return items

    def _simple(self, info: int, arg: int | None) -> Any:
        value = info if info < 24 else arg
        if value == 20:
            return False
        if value == 21:
            return True
        if value == 22:
            return None
        if value == 23:
            return None
        return value


def _decode_cbor(data: bytes) -> Any:
    decoder = CborDecoder(data)
    value = decoder.decode()
    if decoder.offset != len(data):
        raise ValueError("trailing CBOR bytes")
    return value


def _encode_cbor(value: Any) -> bytes:
    if isinstance(value, bool):
        return b"\xf5" if value else b"\xf4"
    if value is None:
        return b"\xf6"
    if isinstance(value, int):
        if value >= 0:
            return _encode_head(0, value)
        return _encode_head(1, -1 - value)
    if isinstance(value, bytes):
        return _encode_head(2, len(value)) + value
    if isinstance(value, str):
        data = value.encode("utf-8")
        return _encode_head(3, len(data)) + data
    if isinstance(value, (list, tuple)):
        return _encode_head(4, len(value)) + b"".join(_encode_cbor(item) for item in value)
    if isinstance(value, dict):
        return _encode_head(5, len(value)) + b"".join(_encode_cbor(k) + _encode_cbor(v) for k, v in value.items())
    raise TypeError(f"unsupported CBOR encode type {type(value).__name__}")


def _encode_head(major: int, value: int) -> bytes:
    prefix = major << 5
    if value < 24:
        return bytes([prefix | value])
    if value <= 0xFF:
        return bytes([prefix | 24, value])
    if value <= 0xFFFF:
        return bytes([prefix | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([prefix | 26]) + value.to_bytes(4, "big")
    return bytes([prefix | 27]) + value.to_bytes(8, "big")


if __name__ == "__main__":
    raise SystemExit(main())
