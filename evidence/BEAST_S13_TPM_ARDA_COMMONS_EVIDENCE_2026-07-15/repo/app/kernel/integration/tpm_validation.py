"""Local TPM 2.0 evidence collection with explicit claim boundaries."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import serialization


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _run(arguments: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments),
        check=check,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _secure_boot() -> tuple[bool, str]:
    result = _run(("mokutil", "--sb-state"), check=False)
    text = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
    return result.returncode == 0 and "SecureBoot enabled" in text, text


def _flush(path: Path) -> None:
    if path.exists():
        _run(("tpm2_flushcontext", str(path)), check=False)


def _hex_digest(value: Any) -> str:
    if isinstance(value, int):
        return format(value, "064x")
    return str(value).strip().lower().removeprefix("0x").zfill(64)


def compare_replayed_pcrs(
    replayed: dict[Any, Any], live: dict[Any, Any], selection: tuple[int, ...]
) -> dict[str, Any]:
    """Compare a parser-replayed PCR map with live TPM values."""
    replay_map = {int(index): _hex_digest(value) for index, value in replayed.items()}
    live_map = {int(index): _hex_digest(value) for index, value in live.items()}
    covered = tuple(index for index in selection if index in replay_map)
    uncovered = tuple(index for index in selection if index not in replay_map)
    mismatched = tuple(
        index
        for index in covered
        if index not in live_map
        or not secrets.compare_digest(replay_map[index], live_map[index])
    )
    matched = tuple(index for index in covered if index not in mismatched)
    return {
        "covered_pcrs": list(covered),
        "matched_pcrs": list(matched),
        "mismatched_pcrs": list(mismatched),
        "uncovered_pcrs": list(uncovered),
        "replayed_values": {
            str(index): "sha256:" + replay_map[index] for index in covered
        },
        "live_values": {
            str(index): "sha256:" + live_map[index]
            for index in covered
            if index in live_map
        },
        "valid": bool(covered) and not mismatched and not uncovered,
    }


def compare_vendor_pcr_baseline(
    expected: dict[Any, Any], live: dict[Any, Any], selection: tuple[int, ...]
) -> dict[str, Any]:
    """Compare vendor-published PCR baselines with live TPM values."""
    expected_map = {int(index): _hex_digest(value) for index, value in expected.items()}
    live_map = {int(index): _hex_digest(value) for index, value in live.items()}
    covered = tuple(index for index in selection if index in expected_map)
    uncovered = tuple(index for index in selection if index not in expected_map)
    mismatched = tuple(
        index
        for index in covered
        if index not in live_map
        or not secrets.compare_digest(expected_map[index], live_map[index])
    )
    matched = tuple(index for index in covered if index not in mismatched)
    return {
        "covered_pcrs": list(covered),
        "matched_pcrs": list(matched),
        "mismatched_pcrs": list(mismatched),
        "uncovered_pcrs": list(uncovered),
        "expected_values": {
            str(index): "sha256:" + expected_map[index] for index in covered
        },
        "live_values": {
            str(index): "sha256:" + live_map[index]
            for index in covered
            if index in live_map
        },
        "valid": bool(covered) and not mismatched,
    }


def parse_hp_history_pcr_baselines(
    history_text: str, *, bios_version: str
) -> dict[int, str]:
    """Extract HP-published PCR baselines for the active BIOS version."""
    target = str(bios_version).strip()
    if not target:
        return {}
    version = re.search(r"(\d+\.\d+\.\d+)", target)
    normalized = version.group(1) if version else target
    section = re.search(
        rf"Version\s+{re.escape(normalized)}(?P<body>.*?)(?:\n\s*Version\s+\d+\.\d+\.\d+|\Z)",
        history_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return {}
    baselines: dict[int, str] = {}
    for match in re.finditer(
        r"PCR\s*(?P<pcr>\d+)\s*\(TPM2\.0\)\s*=\s*(?P<digest>[0-9A-Fa-f]{64})",
        section.group("body"),
    ):
        baselines[int(match.group("pcr"))] = match.group("digest").lower()
    return baselines


def _read_live_pcrs(pcr_spec: str) -> dict[Any, Any]:
    live_result = _run(("tpm2_pcrread", pcr_spec), check=False)
    live_document = yaml.safe_load(live_result.stdout) or {}
    return (live_document.get("sha256") or {}) if live_result.returncode == 0 else {}


def replay_ima_ascii_measurements(data: str, *, bank: str = "sha256") -> dict[str, Any]:
    """Replay IMA template hashes into their PCRs without trusting file paths."""
    if bank != "sha256":
        raise ValueError("only SHA-256 IMA replay is supported")
    values: dict[int, bytes] = {}
    event_counts: dict[int, int] = {}
    invalid_lines = 0
    for line in data.splitlines():
        fields = line.split(maxsplit=4)
        if len(fields) < 4:
            invalid_lines += 1
            continue
        try:
            index = int(fields[0])
            template_hash = bytes.fromhex(fields[1])
        except ValueError:
            invalid_lines += 1
            continue
        if index < 0 or index > 23 or len(template_hash) != 32:
            invalid_lines += 1
            continue
        previous = values.get(index, bytes(32))
        values[index] = hashlib.sha256(previous + template_hash).digest()
        event_counts[index] = event_counts.get(index, 0) + 1
    return {
        "pcrs": {index: value.hex() for index, value in values.items()},
        "event_counts": event_counts,
        "invalid_lines": invalid_lines,
        "valid": bool(values) and invalid_lines == 0,
    }


def combine_measurement_reconciliations(
    selection: tuple[int, ...], *sources: dict[str, Any]
) -> dict[str, Any]:
    """Require at least one exact replay source for every selected PCR."""
    matched_by: dict[int, list[str]] = {index: [] for index in selection}
    mismatched_by: dict[int, list[str]] = {index: [] for index in selection}
    for source in sources:
        name = str(source.get("source") or "unknown")
        for index in source.get("matched_pcrs") or []:
            if int(index) in matched_by:
                matched_by[int(index)].append(name)
        for index in source.get("mismatched_pcrs") or []:
            if int(index) in mismatched_by:
                mismatched_by[int(index)].append(name)
    uncovered = [index for index in selection if not matched_by[index] and not mismatched_by[index]]
    mismatched = [index for index in selection if mismatched_by[index] and not matched_by[index]]
    matched = [index for index in selection if matched_by[index]]
    return {
        "matched_pcrs": matched,
        "mismatched_pcrs": mismatched,
        "uncovered_pcrs": uncovered,
        "matched_by": {str(index): names for index, names in matched_by.items() if names},
        "mismatched_by": {str(index): names for index, names in mismatched_by.items() if names},
        "valid": len(matched) == len(selection) and not mismatched and not uncovered,
    }


def _activate_credential(
    work: Path,
    *,
    ek_context: Path,
    ak_context: Path,
    image: str,
) -> dict[str, Any]:
    """Bind the AK to the EK using an isolated verifier-side MakeCredential."""
    secret_path = work / "activation.secret"
    recovered_path = work / "activation.recovered"
    credential_path = work / "credential.blob"
    session_path = work / "activation-session.ctx"
    secret_path.write_bytes(secrets.token_bytes(32))
    secret_path.chmod(0o600)
    try:
        inspection = _run(("docker", "image", "inspect", image, "--format", "{{.Id}}"), check=False)
        if inspection.returncode != 0:
            return {
                "verified": False,
                "method": "makecredential-activatecredential",
                "verifier_image": image,
                "verifier_image_id": "",
                "detail": "pinned MakeCredential verifier image is unavailable",
            }
        image_id = inspection.stdout.decode("ascii", "replace").strip()
        uid = str(os.getuid())
        gid = str(os.getgid())
        ak_name_hex = (work / "ak.name").read_bytes().hex()
        make = _run(
            (
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", f"{uid}:{gid}", "--volume", f"{work}:/work:rw",
                image, "-Q", "-T", "none", "-G", "rsa", "-u", "/work/ek.pem",
                "-s", "/work/activation.secret", "-n", ak_name_hex,
                "-o", "/work/credential.blob",
            ),
            check=False,
        )
        if make.returncode != 0 or not credential_path.is_file():
            return {
                "verified": False,
                "method": "makecredential-activatecredential",
                "verifier_image": image,
                "verifier_image_id": image_id,
                "detail": "verifier-side MakeCredential failed",
            }
        _run(("tpm2_startauthsession", "-Q", "--policy-session", "-S", str(session_path)))
        _run(("tpm2_policysecret", "-Q", "-S", str(session_path), "-c", "e"))
        activated = _run(
            (
                "tpm2_activatecredential", "-Q", "-c", str(ak_context),
                "-C", str(ek_context), "-i", str(credential_path),
                "-o", str(recovered_path), "-P", f"session:{session_path}",
            ),
            check=False,
        )
        verified = (
            activated.returncode == 0
            and recovered_path.is_file()
            and secrets.compare_digest(secret_path.read_bytes(), recovered_path.read_bytes())
        )
        return {
            "verified": verified,
            "method": "makecredential-activatecredential",
            "verifier_image": image,
            "verifier_image_id": image_id,
            "secret_digest": _digest(secret_path.read_bytes()),
            "credential_blob_digest": _digest(credential_path.read_bytes()),
            "detail": "activation secret recovered by TPM" if verified else "TPM activation failed",
        }
    finally:
        _flush(session_path)


def collect_local_tpm_evidence(
    *,
    node_id: str,
    challenge_id: str = "",
    nonce: str = "",
    pcrs: tuple[int, ...] = (0, 2, 4, 7, 10, 14),
    root_certificate: str | Path | None = None,
    intermediate_certificate: str | Path | None = None,
    firmware_event_log: str | Path = "/sys/kernel/security/tpm0/binary_bios_measurements",
    ima_measurements: str | Path | None = None,
    vendor_pcr_baseline: str | Path | None = None,
    makecredential_image: str = "beast-tpm2-makecredential:local-validation",
) -> dict[str, Any]:
    """Collect a fresh TPM quote and verify every check possible on this host.

    No persistent TPM handles are created.  The returned bundle is evidence,
    not an ARDA appraisal and not by itself a Commons admission credential.
    """
    node = str(node_id).strip()
    if not node:
        raise ValueError("node_id is required")
    challenge = str(nonce).strip().lower() or secrets.token_hex(32)
    if len(challenge) < 64:
        raise ValueError("TPM quote nonce must contain at least 256 bits")
    try:
        bytes.fromhex(challenge)
    except ValueError as exc:
        raise ValueError("TPM quote nonce must be hexadecimal") from exc
    selection = tuple(sorted({int(value) for value in pcrs}))
    if not selection or any(value < 0 or value > 23 for value in selection):
        raise ValueError("invalid PCR selection")

    with tempfile.TemporaryDirectory(prefix="beast-tpm-") as temporary:
        work = Path(temporary)
        ek_context = work / "ek.ctx"
        ak_context = work / "ak.ctx"
        try:
            _run(("tpm2_createek", "-Q", "-G", "rsa", "-c", str(ek_context), "-u", str(work / "ek.pub")))
            _run(("tpm2_readpublic", "-Q", "-c", str(ek_context), "-f", "pem", "-o", str(work / "ek.pem"), "-n", str(work / "ek.name")))
            _run(("tpm2_createak", "-Q", "-C", str(ek_context), "-G", "ecc", "-g", "sha256", "-s", "ecdsa", "-c", str(ak_context), "-u", str(work / "ak.pub"), "-n", str(work / "ak.name")))
            _run(("tpm2_readpublic", "-Q", "-c", str(ak_context), "-f", "pem", "-o", str(work / "ak.pem")))
            pcr_spec = "sha256:" + ",".join(str(value) for value in selection)
            _run(("tpm2_quote", "-Q", "-c", str(ak_context), "-l", pcr_spec, "-q", challenge, "-m", str(work / "quote.msg"), "-s", str(work / "quote.sig"), "-o", str(work / "quote.pcr"), "-g", "sha256"))
            _run(("tpm2_checkquote", "-Q", "-u", str(work / "ak.pem"), "-m", str(work / "quote.msg"), "-s", str(work / "quote.sig"), "-f", str(work / "quote.pcr"), "-g", "sha256", "-q", challenge))
            _run(("tpm2_nvread", "-Q", "-C", "o", "0x1c00002", "-o", str(work / "ek-cert.der")))

            certificate = x509.load_der_x509_certificate((work / "ek-cert.der").read_bytes())
            certificate_spki = certificate.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            ek_public = serialization.load_pem_public_key((work / "ek.pem").read_bytes())
            ek_spki = ek_public.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            ek_matches = secrets.compare_digest(certificate_spki, ek_spki)

            chain_valid = False
            chain_detail = "trust roots not supplied"
            if root_certificate and intermediate_certificate:
                verification = _run(
                    (
                        "openssl", "verify", "-purpose", "any",
                        "-CAfile", str(Path(root_certificate).expanduser()),
                        "-untrusted", str(Path(intermediate_certificate).expanduser()),
                        str(work / "ek-cert.der"),
                    ),
                    check=False,
                )
                chain_valid = verification.returncode == 0
                chain_detail = (verification.stdout + verification.stderr).decode("utf-8", "replace").strip()

            secure_boot, secure_boot_detail = _secure_boot()
            activation = _activate_credential(
                work,
                ek_context=ek_context,
                ak_context=ak_context,
                image=makecredential_image,
            )
            live_pcrs = _read_live_pcrs(pcr_spec)
            event_path = Path(firmware_event_log)
            event_readable = event_path.is_file() and os.access(event_path, os.R_OK)
            event_digest = ""
            event_parser_valid = False
            event_parser_detail = "firmware event log is not readable by the collector"
            event_log_b64 = ""
            event_reconciliation = {
                "covered_pcrs": [],
                "matched_pcrs": [],
                "mismatched_pcrs": [],
                "uncovered_pcrs": list(selection),
                "valid": False,
            }
            if event_readable:
                event_bytes = event_path.read_bytes()
                event_digest = _digest(event_bytes)
                event_log_b64 = base64.b64encode(event_bytes).decode("ascii")
                parsed = _run(("tpm2_eventlog", str(event_path)), check=False)
                event_parser_valid = parsed.returncode == 0
                event_parser_detail = (parsed.stderr or b"parsed successfully").decode("utf-8", "replace").strip()
                if event_parser_valid:
                    parsed_document = yaml.safe_load(parsed.stdout) or {}
                    replayed = (parsed_document.get("pcrs") or {}).get("sha256") or {}
                    event_reconciliation = compare_replayed_pcrs(replayed, live_pcrs, selection)

            firmware_source = {**event_reconciliation, "source": "firmware_event_log"}
            vendor_path = Path(vendor_pcr_baseline).expanduser() if vendor_pcr_baseline else None
            vendor_readable = bool(vendor_path and vendor_path.is_file() and os.access(vendor_path, os.R_OK))
            vendor_baselines: dict[int, str] = {}
            vendor_detail = "vendor PCR baseline not supplied"
            vendor_digest = ""
            vendor_reconciliation = {
                "covered_pcrs": [],
                "matched_pcrs": [],
                "mismatched_pcrs": [],
                "uncovered_pcrs": list(selection),
                "valid": False,
            }
            if vendor_readable and vendor_path is not None:
                vendor_bytes = vendor_path.read_bytes()
                vendor_digest = _digest(vendor_bytes)
                bios_version = Path("/sys/class/dmi/id/bios_version").read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
                vendor_baselines = parse_hp_history_pcr_baselines(
                    vendor_bytes.decode("utf-8", "replace"),
                    bios_version=bios_version,
                )
                if vendor_baselines:
                    vendor_detail = f"matched HP history baseline for BIOS {bios_version}"
                    vendor_reconciliation = compare_vendor_pcr_baseline(
                        vendor_baselines, live_pcrs, selection
                    )
                else:
                    vendor_detail = f"no PCR baseline found for BIOS {bios_version}"
            vendor_source = {**vendor_reconciliation, "source": "vendor_pcr_baseline"}
            ima_path = Path(ima_measurements).expanduser() if ima_measurements else None
            ima_readable = bool(ima_path and ima_path.is_file() and os.access(ima_path, os.R_OK))
            ima_digest = ""
            ima_replay = {"pcrs": {}, "event_counts": {}, "invalid_lines": 0, "valid": False}
            ima_reconciliation = {
                "covered_pcrs": [], "matched_pcrs": [], "mismatched_pcrs": [],
                "uncovered_pcrs": list(selection), "valid": False,
            }
            if ima_readable and ima_path is not None:
                ima_bytes = ima_path.read_bytes()
                ima_digest = _digest(ima_bytes)
                ima_replay = replay_ima_ascii_measurements(ima_bytes.decode("utf-8", "strict"))
                ima_reconciliation = compare_replayed_pcrs(
                    ima_replay["pcrs"], live_pcrs, selection
                )
            ima_source = {**ima_reconciliation, "source": "ima_runtime_measurements"}
            measurement_reconciliation = combine_measurement_reconciliations(
                selection, firmware_source, ima_source, vendor_source
            )

            quote_valid = True
            activation_valid = bool(activation["verified"])
            reasons = []
            if not ek_matches:
                reasons.append("ek_certificate_key_mismatch")
            if not chain_valid:
                reasons.append("ek_chain_untrusted")
            if not activation_valid:
                reasons.append("ak_credential_activation_not_completed")
            if not secure_boot:
                reasons.append("secure_boot_not_enabled")
            if not event_readable:
                reasons.append("firmware_event_log_unavailable")
            elif not event_parser_valid:
                reasons.append("firmware_event_log_parse_failed")
            if not measurement_reconciliation["valid"]:
                reasons.append("measurement_logs_do_not_reconcile_all_selected_pcrs")

            bundle = {
                "schema": "beast.commons.tpm-evidence.v1",
                "platform": "linux",
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip(),
                "kernel_release": os.uname().release,
                "node_id": node,
                "challenge_id": challenge_id,
                "nonce": challenge,
                "audience": "beast-commons-node-attestation",
                "collected_at": datetime.now(UTC).isoformat(),
                "pcr_bank": "sha256",
                "pcrs": list(selection),
                "secure_boot": {"enabled": secure_boot, "detail": secure_boot_detail},
                "quote": {
                    "verified_locally": quote_valid,
                    "message_b64": _b64(work / "quote.msg"),
                    "signature_b64": _b64(work / "quote.sig"),
                    "pcr_blob_b64": _b64(work / "quote.pcr"),
                    "message_digest": _digest((work / "quote.msg").read_bytes()),
                    "signature_digest": _digest((work / "quote.sig").read_bytes()),
                },
                "ak": {
                    "public_pem": (work / "ak.pem").read_text(encoding="ascii"),
                    "name_hex": (work / "ak.name").read_bytes().hex(),
                    "credential_activation_verified": activation_valid,
                    "credential_activation": activation,
                },
                "ek": {
                    "public_pem": (work / "ek.pem").read_text(encoding="ascii"),
                    "name_hex": (work / "ek.name").read_bytes().hex(),
                    "certificate_der_b64": _b64(work / "ek-cert.der"),
                    "certificate_digest": _digest((work / "ek-cert.der").read_bytes()),
                    "certificate_public_matches_ek": ek_matches,
                    "certificate_chain_valid": chain_valid,
                    "certificate_chain_detail": chain_detail,
                    "issuer": certificate.issuer.rfc4514_string(),
                    "serial_hex": format(certificate.serial_number, "x"),
                },
                "firmware_event_log": {
                    "readable": event_readable,
                    "digest": event_digest,
                    "parser_valid": event_parser_valid,
                    "parser_detail": event_parser_detail,
                    "reconciliation": event_reconciliation,
                    "replay_valid": event_reconciliation["valid"],
                    "content_b64": event_log_b64,
                },
                "vendor_pcr_baseline": {
                    "readable": vendor_readable,
                    "digest": vendor_digest,
                    "detail": vendor_detail,
                    "baselines": {
                        str(index): "sha256:" + value
                        for index, value in sorted(vendor_baselines.items())
                    },
                    "reconciliation": vendor_reconciliation,
                    "valid": vendor_reconciliation["valid"],
                },
                "ima_runtime_measurements": {
                    "readable": ima_readable,
                    "digest": ima_digest,
                    "replay": ima_replay,
                    "reconciliation": ima_reconciliation,
                    "replay_valid": ima_reconciliation["valid"],
                },
                "measurement_reconciliation": measurement_reconciliation,
                "verifier_facts": {
                    "quote_valid": quote_valid,
                    "ek_public_matches_certificate": ek_matches,
                    "ek_chain_valid": chain_valid,
                    "ak_credential_activated": activation_valid,
                    "secure_boot_accepted": secure_boot,
                    "event_log_replay_valid": measurement_reconciliation["valid"],
                },
                "eligible_for_commons": not reasons,
                "status": (
                    "hardware_quote_valid_measurements_reconciled"
                    if not reasons
                    else "hardware_quote_valid_admission_blocked"
                ),
                "claim_boundary": "fresh TPM quote and certified EK evidence; not an ARDA appraisal or Commons execution grant",
                "blockers": reasons,
            }
            canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
            bundle["evidence_digest"] = _digest(canonical)
            return bundle
        finally:
            _flush(ak_context)
            _flush(ek_context)
