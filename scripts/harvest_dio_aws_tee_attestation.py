#!/usr/bin/env python3
"""Harvest/normalize AWS DIO TEE witness evidence.

This script keeps the same hard line as the Azure and GCP harvesters:

* AWS account and EC2 inventory are useful readiness evidence.
* An EC2 instance with NitroTPM support or Nitro Enclave options is stronger
  inventory evidence.
* Hardware-witness admission requires a raw NitroTPM or Nitro Enclave
  attestation document captured from the instance/enclave and supplied with
  --raw-attestation-document-file.

Without that raw document, the script writes a blocked receipt rather than
manufacturing hardware truth from AWS account ownership.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_bytes, sha256_digest
from app.kernel.dai.dio_cloud_attestation import (
    DIOCloudProvider,
    DIOCloudTeeEvidence,
    DIOCloudTeePolicy,
    DIOCloudTeeType,
    DIOCloudVerifier,
    admit_cloud_tee_witness,
)
from app.kernel.dai.dio_cloud_autonomous_packet import build_cloud_autonomous_witness_envelope
from app.kernel.dai.dio_distributed_quorum import DIOProposalPacket, DIOWitnessRole, public_key_fingerprint


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/aws"
DEFAULT_KEY = ROOT / ".beast/dio-cloud-witness/aws-governance-01.ed25519.pem"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="")
    parser.add_argument("--instance-id", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--node-id", default="dio:aws:tee-governance-01")
    parser.add_argument("--role", default=DIOWitnessRole.GOVERNANCE.value)
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--challenge-nonce", default="")
    parser.add_argument("--governance-epoch", default="dai-phase2.1-aws-cloud-witness")
    parser.add_argument(
        "--raw-attestation-document-file",
        type=Path,
        default=None,
        help="Raw NitroTPM/Nitro Enclave attestation document captured from the AWS runtime.",
    )
    parser.add_argument("--verify-nitro-document", action="store_true")
    parser.add_argument("--nitro-root-pem", type=Path, default=None)
    parser.add_argument("--nitro-root-zip", type=Path, default=None)
    parser.add_argument("--fetch-nitro-root", action="store_true")
    parser.add_argument("--expected-user-data-file", type=Path, default=None)
    parser.add_argument("--expected-pcr", action="append", default=[])
    parser.add_argument("--expected-pcr-file", type=Path, default=None)
    parser.add_argument("--emit-autonomous-packet", action="store_true")
    parser.add_argument("--remote-runtime-observed", action="store_true")
    parser.add_argument("--proposal-file", type=Path, default=None)
    args = parser.parse_args()
    result = harvest(
        region=args.region,
        instance_id=args.instance_id,
        out=args.out,
        node_id=args.node_id,
        role=DIOWitnessRole(args.role),
        key_path=args.key_path,
        challenge_nonce=args.challenge_nonce,
        governance_epoch=args.governance_epoch,
        raw_attestation_document_file=args.raw_attestation_document_file,
        verify_nitro_document=args.verify_nitro_document,
        nitro_root_pem=args.nitro_root_pem,
        nitro_root_zip=args.nitro_root_zip,
        fetch_nitro_root=args.fetch_nitro_root,
        expected_user_data_file=args.expected_user_data_file,
        expected_pcr=args.expected_pcr,
        expected_pcr_file=args.expected_pcr_file,
        emit_autonomous_packet=args.emit_autonomous_packet,
        remote_runtime_observed=args.remote_runtime_observed,
        proposal_file=args.proposal_file,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("green") else 2


def harvest(
    *,
    region: str,
    instance_id: str,
    out: Path,
    node_id: str,
    role: DIOWitnessRole,
    key_path: Path,
    challenge_nonce: str,
    governance_epoch: str,
    raw_attestation_document_file: Path | None,
    verify_nitro_document: bool = False,
    nitro_root_pem: Path | None = None,
    nitro_root_zip: Path | None = None,
    fetch_nitro_root: bool = False,
    expected_user_data_file: Path | None = None,
    expected_pcr: list[str] | tuple[str, ...] = (),
    expected_pcr_file: Path | None = None,
    emit_autonomous_packet: bool = False,
    remote_runtime_observed: bool = False,
    proposal_file: Path | None = None,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    identity = _aws_json(["sts", "get-caller-identity"])
    if not identity:
        return _blocked(
            out,
            reason="aws_cli_not_logged_in",
            details={"next_step": "Run `aws configure` or export AWS credentials for a DIO witness account."},
        )
    active_region = region or _aws_value(["configure", "get", "region"]) or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    active_region = active_region.strip()
    instances, describe_error = _ec2_instances(active_region)
    if describe_error:
        return _blocked(
            out,
            reason="aws_ec2_describe_instances_unavailable_or_unauthorized",
            details={
                "region": active_region,
                "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
                "stderr": _sanitize_aws_text(describe_error)[:500],
                "next_step": (
                    "Grant read-only EC2 inventory for this witness user, at minimum ec2:DescribeInstances "
                    "in the target region. For optional preflight, also grant ec2:DescribeRegions."
                ),
            },
        )
    running = [row for row in instances if str((row.get("State") or {}).get("Name") or "") in {"pending", "running", "stopping", "stopped"}]
    if not instance_id:
        candidates = [row for row in running if _has_nitro_witness_signal(row)]
        if len(candidates) == 1:
            instance_id = str(candidates[0].get("InstanceId") or "")
        elif len(candidates) > 1:
            return _blocked(
                out,
                reason="aws_multiple_nitro_witness_candidates_require_explicit_target",
                details={
                    "region": active_region,
                    "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
                    "instances": [_instance_ref(row) for row in candidates],
                },
            )
        elif len(running) == 1:
            instance_id = str(running[0].get("InstanceId") or "")
        else:
            return _blocked(
                out,
                reason="aws_no_ec2_instances_found_in_region" if not running else "aws_multiple_instances_require_explicit_target",
                details={
                    "region": active_region,
                    "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
                    "instance_count": len(running),
                    "instances": [_instance_ref(row) for row in running[:20]],
                    "next_step": (
                        "Launch or target an EC2 instance with NitroTPM support or Nitro Enclaves enabled, "
                        "collect a raw Nitro attestation document inside the runtime, then rerun with "
                        "--instance-id and --raw-attestation-document-file."
                    ),
                },
            )

    described = next((row for row in instances if row.get("InstanceId") == instance_id), None)
    if described is None:
        described = _describe_instance(active_region, instance_id)
    if described is None:
        return _blocked(
            out,
            reason="aws_instance_not_found",
            details={
                "region": active_region,
                "instance_id": instance_id,
                "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
            },
        )

    tee_type = _tee_type_for_instance(described)
    if tee_type is None:
        return _blocked(
            out,
            reason="aws_instance_has_no_nitro_tpm_or_enclave_signal",
            details={
                "region": active_region,
                "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
                "instance": _instance_ref(described),
                "next_step": (
                    "Use an EC2 instance launched with NitroTPM support or Nitro Enclaves enabled; "
                    "plain EC2 inventory is not hardware attestation."
                ),
            },
        )

    if raw_attestation_document_file is None or not raw_attestation_document_file.exists():
        return _blocked(
            out,
            reason="aws_raw_nitro_attestation_document_required",
            details={
                "region": active_region,
                "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
                "instance": _instance_ref(described),
                "tee_type": tee_type.value,
                "challenge_nonce_digest": sha256_digest({"challenge_nonce": challenge_nonce})
                if challenge_nonce
                else "",
                "next_step": (
                    "Inside the AWS runtime, collect a NitroTPM document with `nitro-tpm-attest` "
                    "or a Nitro Enclave attestation document through the NSM API, then pass it with "
                    "--raw-attestation-document-file."
                ),
            },
        )

    raw_document = raw_attestation_document_file.read_bytes()
    document_shape = _document_shape(raw_document)
    if document_shape["shape"] == "empty":
        return _blocked(
            out,
            reason="aws_raw_nitro_attestation_document_empty",
            details={"document_file": str(raw_attestation_document_file)},
        )
    nitro_verification: dict[str, Any] | None = None
    if verify_nitro_document:
        from scripts.verify_dio_aws_nitro_attestation_document import verify_document

        nitro_verification = verify_document(
            document_path=raw_attestation_document_file,
            root_pem=nitro_root_pem,
            root_zip=nitro_root_zip,
            fetch_root=fetch_nitro_root,
            expected_nonce_hex=challenge_nonce,
            expected_user_data_file=expected_user_data_file,
            expected_instance_id=instance_id,
            expected_pcr=expected_pcr,
            expected_pcr_file=expected_pcr_file,
        )
        _write_json(out / "dio_aws_nitro_attestation_document_verification.json", nitro_verification)
        if not nitro_verification.get("passed"):
            return _blocked(
                out,
                reason="aws_nitro_attestation_document_verification_failed",
                details={
                    "document_file": str(raw_attestation_document_file),
                    "verification_digest": nitro_verification.get("verification_digest", ""),
                    "red_gates": nitro_verification.get("red_gates", ()),
                },
            )

    key = _load_or_create_key(key_path)
    public_b64 = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    nonce = challenge_nonce or "dio-aws-" + sha256_digest({"region": active_region, "instance": instance_id, "time": now.isoformat()})[-48:]
    instance_identity = _instance_identity(active_region, identity, described)
    evidence = DIOCloudTeeEvidence(
        beast_object_type="dio_cloud_tee_attestation_evidence",
        provider=DIOCloudProvider.AWS,
        tee_type=tee_type,
        service_verifier=DIOCloudVerifier.AWS_NITRO_ATTESTATION,
        node_id=node_id,
        role=role,
        runtime_platform=tee_type.value,
        infrastructure_provider="aws",
        public_key_b64=public_b64,
        key_fingerprint=public_key_fingerprint(public_b64),
        verifier_commit=sha256_bytes((ROOT / "app/kernel/dai/dio_cloud_attestation.py").read_bytes()),
        container_manifest=sha256_digest({"script": "harvest_dio_aws_tee_attestation.py", "region": active_region, "instance_id": instance_id}),
        tee_measurement_digest=sha256_digest({"aws_instance_identity": instance_identity, "raw_document_shape": document_shape}),
        raw_attestation_digest=sha256_bytes(raw_document),
        service_verification_digest=(
            str(nitro_verification["verification_digest"])
            if nitro_verification
            else sha256_digest({
                "boundary": "aws_nitro_attestation_document_digest_bound_parser_not_full_cose_x509_chain_verifier",
                "document_shape": document_shape,
                "tee_type": tee_type.value,
            })
        ),
        challenge_nonce=nonce,
        governance_epoch=governance_epoch,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    policy = DIOCloudTeePolicy(
        policy_id="policy:aws:nitro:governance:v1",
        provider=DIOCloudProvider.AWS,
        tee_type=evidence.tee_type,
        service_verifier=DIOCloudVerifier.AWS_NITRO_ATTESTATION,
        node_id=node_id,
        role=role,
        permitted_verifier_commit=evidence.verifier_commit,
        permitted_measurement_digest=evidence.tee_measurement_digest,
        permitted_public_key_fingerprint=evidence.key_fingerprint,
        required_challenge_nonce=evidence.challenge_nonce,
        governance_epoch=governance_epoch,
    )
    admission, report = admit_cloud_tee_witness(evidence, policy, evaluation_time=now)
    payload = {
        "beast_object_type": "dio_aws_tee_attestation_harvest",
        "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
        "region": active_region,
        "instance_id": instance_id,
        "green": bool(admission is not None and report.admitted),
        "authority_boundary": (
            "aws_nitro_runtime_with_raw_attestation_document_digest_bound; full Nitro COSE/x509 "
            "chain and PCR policy verification still required before publication-grade hardware-rooted claim"
        ),
        "production_authority_allowed": False,
        "provider_calls_used": 0,
        "document_shape": document_shape,
        "evidence": asdict(evidence),
        "evidence_digest": evidence.evidence_digest,
        "policy": asdict(policy),
        "policy_digest": policy.policy_digest,
        "admission": None if admission is None else asdict(admission),
        "admission_report": asdict(report),
        "admission_report_digest": report.report_digest,
        "nitro_document_verification": nitro_verification,
    }
    if nitro_verification:
        payload["authority_boundary"] = (
            "aws_nitro_runtime_with_cose_x509_pcr_attestation_verified; "
            "DIO policy still keeps production authority off"
        )
    payload["harvest_digest"] = sha256_digest(payload)
    _write_json(out / "dio_aws_tee_attestation_harvest.json", payload)
    _write_json(out / "dio_aws_tee_evidence.json", asdict(evidence) | {"evidence_digest": evidence.evidence_digest})
    _write_json(out / "dio_aws_tee_policy.json", asdict(policy) | {"policy_digest": policy.policy_digest})
    if emit_autonomous_packet:
        proposal = _load_proposal(proposal_file) if proposal_file else None
        envelope = build_cloud_autonomous_witness_envelope(
            harvest=payload,
            private_key=key,
            remote_runtime_observed=remote_runtime_observed,
            proposal=proposal,
            evaluation_time=now,
        )
        _write_json(out / "dio_aws_autonomous_witness_envelope.json", envelope)
    return payload


def _blocked(out: Path, *, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "beast_object_type": "dio_aws_tee_attestation_harvest",
        "green": False,
        "blocked": True,
        "blocked_reason": reason,
        "details": details,
        "production_authority_allowed": False,
        "provider_calls_used": 0,
    }
    payload["harvest_digest"] = sha256_digest(payload)
    _write_json(out / "dio_aws_tee_attestation_harvest.json", payload)
    return payload


def _ec2_instances(region: str) -> tuple[list[dict[str, Any]], str]:
    result = _run(["aws", "ec2", "describe-instances", "--region", region, "--output", "json"])
    if result.returncode != 0:
        return [], result.stderr.strip()
    if not result.stdout.strip():
        return [], ""
    payload = json.loads(result.stdout)
    instances: list[dict[str, Any]] = []
    for reservation in payload.get("Reservations") or []:
        if isinstance(reservation, dict):
            instances.extend(row for row in reservation.get("Instances") or [] if isinstance(row, dict))
    return instances, ""


def _describe_instance(region: str, instance_id: str) -> dict[str, Any] | None:
    payload = _aws_json(["ec2", "describe-instances", "--region", region, "--instance-ids", instance_id])
    if not payload:
        return None
    for reservation in payload.get("Reservations") or []:
        for row in reservation.get("Instances") or []:
            if isinstance(row, dict) and row.get("InstanceId") == instance_id:
                return row
    return None


def _has_nitro_witness_signal(instance: dict[str, Any]) -> bool:
    return _tee_type_for_instance(instance) is not None


def _tee_type_for_instance(instance: dict[str, Any]) -> DIOCloudTeeType | None:
    enclave = instance.get("EnclaveOptions") if isinstance(instance.get("EnclaveOptions"), dict) else {}
    if enclave.get("Enabled") is True:
        return DIOCloudTeeType.AWS_NITRO_ENCLAVE
    if str(instance.get("TpmSupport") or "").lower() in {"v2.0", "2.0", "enabled"}:
        return DIOCloudTeeType.AWS_NITRO_TPM
    return None


def _instance_identity(region: str, identity: dict[str, Any], instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_digest": sha256_digest({"aws_account": identity.get("Account", "")}),
        "region": region,
        "instance_id": instance.get("InstanceId", ""),
        "image_id": instance.get("ImageId", ""),
        "instance_type": instance.get("InstanceType", ""),
        "state": (instance.get("State") or {}).get("Name", ""),
        "architecture": instance.get("Architecture", ""),
        "platform_details": instance.get("PlatformDetails", ""),
        "virtualization_type": instance.get("VirtualizationType", ""),
        "hypervisor": instance.get("Hypervisor", ""),
        "tpm_support": instance.get("TpmSupport", ""),
        "enclave_options": instance.get("EnclaveOptions", {}),
        "iam_instance_profile_digest": sha256_digest({"iam_instance_profile": instance.get("IamInstanceProfile", {})}),
    }


def _instance_ref(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "instance_id": instance.get("InstanceId", ""),
        "state": (instance.get("State") or {}).get("Name", ""),
        "instance_type": instance.get("InstanceType", ""),
        "image_id": instance.get("ImageId", ""),
        "tpm_support": instance.get("TpmSupport", ""),
        "enclave_enabled": (instance.get("EnclaveOptions") or {}).get("Enabled", False),
        "launch_time": str(instance.get("LaunchTime", "")),
    }


def _document_shape(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {"shape": "empty"}
    stripped = raw.strip()
    text = ""
    try:
        text = stripped.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return {
                "shape": "json",
                "json_digest": sha256_digest(parsed),
                "json_key_count": len(parsed),
                "byte_count": len(raw),
            }
        return {
            "shape": "pem_or_text" if "BEGIN" in text[:200] else "base64_or_text",
            "line_count": len(text.splitlines()),
            "byte_count": len(raw),
        }
    return {"shape": "binary_cbor_or_cose", "byte_count": len(raw)}


def _load_or_create_key(path: Path) -> Ed25519PrivateKey:
    path = path.expanduser().resolve()
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise RuntimeError(f"DIO AWS witness key is not Ed25519: {path}")
        return key
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    return key


def _aws_value(args: list[str]) -> str:
    result = _run(["aws", *args])
    return result.stdout.strip() if result.returncode == 0 else ""


def _aws_json(args: list[str]) -> Any:
    result = _run(["aws", *args, "--output", "json"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(command, cwd=str(ROOT), env=env, text=True, capture_output=True, timeout=120)


def _sanitize_aws_text(value: str) -> str:
    sanitized = re.sub(r"arn:aws:iam::[0-9]+:[^\s,]+", "arn:aws:iam::REDACTED:REDACTED", value)
    sanitized = re.sub(r"\b[0-9]{12}\b", "REDACTED_ACCOUNT", sanitized)
    sanitized = re.sub(r"AKIA[0-9A-Z]{16}", "REDACTED_ACCESS_KEY", sanitized)
    return sanitized


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_proposal(path: Path) -> DIOProposalPacket:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("packet_digest", None)
    return DIOProposalPacket(**payload)


if __name__ == "__main__":
    raise SystemExit(main())
