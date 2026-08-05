#!/usr/bin/env python3
"""Harvest/normalize Azure DIO TEE witness evidence.

This script keeps a hard line between:

* Azure account and region readiness;
* a Confidential VM existing;
* a raw Azure guest-attestation / MAA token being available.

Azure CLI can inventory the subscription and VM from outside the guest.  It
cannot, by itself, prove the guest's measured runtime.  Publication-grade DIO
hardware-witness admission therefore requires a raw attestation token/report
captured from the guest or verifier path and supplied with
``--raw-attestation-token-file``.  Without that token, the script writes a
blocked receipt instead of manufacturing hardware truth.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest
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


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/azure"
DEFAULT_KEY = ROOT / ".beast/dio-cloud-witness/azure-governance-01.ed25519.pem"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription", default="")
    parser.add_argument("--location", default="westeurope")
    parser.add_argument("--resource-group", default="")
    parser.add_argument("--vm", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--node-id", default="dio:azure:tee-governance-01")
    parser.add_argument("--role", default=DIOWitnessRole.GOVERNANCE.value)
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--challenge-nonce", default="")
    parser.add_argument("--governance-epoch", default="dai-phase2.1-azure-cloud-witness")
    parser.add_argument(
        "--raw-attestation-token-file",
        type=Path,
        default=None,
        help="Raw Azure guest-attestation / MAA token or report captured from the confidential guest.",
    )
    parser.add_argument("--emit-autonomous-packet", action="store_true")
    parser.add_argument("--remote-runtime-observed", action="store_true")
    parser.add_argument("--proposal-file", type=Path, default=None)
    args = parser.parse_args()
    result = harvest(
        subscription=args.subscription,
        location=args.location,
        resource_group=args.resource_group,
        vm=args.vm,
        out=args.out,
        node_id=args.node_id,
        role=DIOWitnessRole(args.role),
        key_path=args.key_path,
        challenge_nonce=args.challenge_nonce,
        governance_epoch=args.governance_epoch,
        raw_attestation_token_file=args.raw_attestation_token_file,
        emit_autonomous_packet=args.emit_autonomous_packet,
        remote_runtime_observed=args.remote_runtime_observed,
        proposal_file=args.proposal_file,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("green") else 2


def harvest(
    *,
    subscription: str,
    location: str,
    resource_group: str,
    vm: str,
    out: Path,
    node_id: str,
    role: DIOWitnessRole,
    key_path: Path,
    challenge_nonce: str,
    governance_epoch: str,
    raw_attestation_token_file: Path | None,
    emit_autonomous_packet: bool = False,
    remote_runtime_observed: bool = False,
    proposal_file: Path | None = None,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    account = _az_json(["account", "show"])
    if not account:
        return _blocked(out, reason="azure_cli_not_logged_in", details={"next_step": "Run `az login` and select the DIO subscription."})

    active_subscription = subscription or str(account.get("id") or "")
    if subscription:
        set_result = _run(["az", "account", "set", "--subscription", subscription])
        if set_result.returncode != 0:
            return _blocked(
                out,
                reason="azure_subscription_set_failed",
                details={"subscription": subscription, "stderr": set_result.stderr.strip()},
            )
        account = _az_json(["account", "show"]) or account

    provider_state = {
        "Microsoft.Attestation": _provider_state("Microsoft.Attestation"),
        "Microsoft.Compute": _provider_state("Microsoft.Compute"),
    }
    if provider_state["Microsoft.Attestation"] != "Registered":
        return _blocked(
            out,
            reason="azure_attestation_provider_not_registered",
            details={
                "subscription": active_subscription,
                "provider_state": provider_state,
                "next_step": "Run `az provider register --namespace Microsoft.Attestation`.",
            },
        )

    location = _normalize_location(location)
    groups = _az_json(["group", "list"]) or []
    location_groups = [
        row for row in groups
        if _normalize_location(str(row.get("location") or "")) == location
    ]
    vms = _az_json(["vm", "list", "--show-details"]) or []
    location_vms = [
        row for row in vms
        if _normalize_location(str(row.get("location") or "")) == location
    ]

    if not resource_group and not vm:
        if not location_vms:
            return _blocked(
                out,
                reason="azure_no_vms_found_in_location",
                details={
                    "subscription": active_subscription,
                    "account_user": (account.get("user") or {}).get("name", ""),
                    "location": location,
                    "provider_state": provider_state,
                    "resource_groups_in_location": [str(row.get("name") or "") for row in location_groups],
                    "next_step": (
                        "Create an Azure Confidential VM in West Europe, run the guest attestation collector "
                        "inside it, then rerun this harvester with --resource-group, --vm and "
                        "--raw-attestation-token-file."
                    ),
                },
            )
        if len(location_vms) == 1:
            vm = str(location_vms[0].get("name") or "")
            resource_group = str(location_vms[0].get("resourceGroup") or "")
        else:
            return _blocked(
                out,
                reason="azure_multiple_vms_require_explicit_target",
                details={
                    "subscription": active_subscription,
                    "location": location,
                    "vms": [_vm_ref(row) for row in location_vms],
                },
            )

    if not resource_group or not vm:
        return _blocked(
            out,
            reason="azure_resource_group_and_vm_required",
            details={"subscription": active_subscription, "location": location, "resource_group": resource_group, "vm": vm},
        )

    described = _az_json(["vm", "show", "--resource-group", resource_group, "--name", vm, "--show-details"])
    if not described:
        return _blocked(
            out,
            reason="azure_vm_not_found",
            details={"subscription": active_subscription, "location": location, "resource_group": resource_group, "vm": vm},
        )

    security = described.get("securityProfile") or {}
    security_type = str(security.get("securityType") or "")
    if security_type.lower() != "confidentialvm":
        return _blocked(
            out,
            reason="azure_vm_not_confidential_vm",
            details={
                "subscription": active_subscription,
                "location": location,
                "resource_group": resource_group,
                "vm": vm,
                "securityProfile": security,
            },
        )

    if raw_attestation_token_file is None or not raw_attestation_token_file.exists():
        return _blocked(
            out,
            reason="azure_raw_guest_attestation_token_required",
            details={
                "subscription": active_subscription,
                "location": location,
                "resource_group": resource_group,
                "vm": vm,
                "securityProfile": security,
                "next_step": (
                    "Run Azure guest attestation / MAA collection inside the Confidential VM and pass the "
                    "saved token/report with --raw-attestation-token-file."
                ),
            },
        )

    raw_token = raw_attestation_token_file.read_text(encoding="utf-8", errors="replace")
    token_shape = _token_shape(raw_token)
    if token_shape["shape"] == "empty":
        return _blocked(
            out,
            reason="azure_raw_guest_attestation_token_empty",
            details={"token_file": str(raw_attestation_token_file)},
        )

    key = _load_or_create_key(key_path)
    public_b64 = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    nonce = challenge_nonce or "dio-azure-" + sha256_digest({"subscription": active_subscription, "resource_group": resource_group, "vm": vm, "time": now.isoformat()})[-48:]
    vm_identity = {
        "subscription": active_subscription,
        "tenantId": account.get("tenantId", ""),
        "location": location,
        "resource_group": resource_group,
        "vm": vm,
        "id": described.get("id", ""),
        "vmId": described.get("vmId", ""),
        "hardwareProfile": described.get("hardwareProfile", {}),
        "securityProfile": security,
        "storageProfile": described.get("storageProfile", {}),
        "osProfile": described.get("osProfile", {}),
        "identity": described.get("identity", {}),
    }
    measurement_digest = sha256_digest({"azure_vm_identity": vm_identity, "raw_token_shape": token_shape})
    raw_attestation_digest = sha256_digest({"azure_raw_attestation_token": raw_token})
    evidence = DIOCloudTeeEvidence(
        beast_object_type="dio_cloud_tee_attestation_evidence",
        provider=DIOCloudProvider.AZURE,
        tee_type=_tee_type_for_vm(described),
        service_verifier=DIOCloudVerifier.AZURE_MAA,
        node_id=node_id,
        role=role,
        runtime_platform="azure_confidential_vm",
        infrastructure_provider="azure",
        public_key_b64=public_b64,
        key_fingerprint=public_key_fingerprint(public_b64),
        verifier_commit=sha256_bytes((ROOT / "app/kernel/dai/dio_cloud_attestation.py").read_bytes()),
        container_manifest=sha256_digest({"script": "harvest_dio_azure_tee_attestation.py", "subscription": active_subscription, "location": location, "resource_group": resource_group, "vm": vm}),
        tee_measurement_digest=measurement_digest,
        raw_attestation_digest=raw_attestation_digest,
        service_verification_digest=sha256_digest({
            "boundary": "azure_guest_attestation_token_digest_bound_parser_not_full_x5c_chain_verifier",
            "token_shape": token_shape,
            "confidential_vm": True,
        }),
        challenge_nonce=nonce,
        governance_epoch=governance_epoch,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    policy = DIOCloudTeePolicy(
        policy_id="policy:azure:confidential-vm:governance:v1",
        provider=DIOCloudProvider.AZURE,
        tee_type=evidence.tee_type,
        service_verifier=DIOCloudVerifier.AZURE_MAA,
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
        "beast_object_type": "dio_azure_tee_attestation_harvest",
        "subscription_digest": sha256_digest({"subscription": active_subscription}),
        "location": location,
        "resource_group": resource_group,
        "vm": vm,
        "green": bool(admission is not None and report.admitted),
        "authority_boundary": (
            "azure_confidential_vm_with_raw_attestation_token_digest_bound; full MAA JWT/x5c "
            "chain verification still required before publication-grade hardware-rooted claim"
        ),
        "production_authority_allowed": False,
        "provider_calls_used": 0,
        "token_shape": token_shape,
        "evidence": asdict(evidence),
        "evidence_digest": evidence.evidence_digest,
        "policy": asdict(policy),
        "policy_digest": policy.policy_digest,
        "admission": None if admission is None else asdict(admission),
        "admission_report": asdict(report),
        "admission_report_digest": report.report_digest,
    }
    payload["harvest_digest"] = sha256_digest(payload)
    _write_json(out / "dio_azure_tee_attestation_harvest.json", payload)
    _write_json(out / "dio_azure_tee_evidence.json", asdict(evidence) | {"evidence_digest": evidence.evidence_digest})
    _write_json(out / "dio_azure_tee_policy.json", asdict(policy) | {"policy_digest": policy.policy_digest})
    if emit_autonomous_packet:
        proposal = _load_proposal(proposal_file) if proposal_file else None
        envelope = build_cloud_autonomous_witness_envelope(
            harvest=payload,
            private_key=key,
            remote_runtime_observed=remote_runtime_observed,
            proposal=proposal,
            evaluation_time=now,
        )
        _write_json(out / "dio_azure_autonomous_witness_envelope.json", envelope)
    return payload


def _blocked(out: Path, *, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "beast_object_type": "dio_azure_tee_attestation_harvest",
        "green": False,
        "blocked": True,
        "blocked_reason": reason,
        "details": details,
        "production_authority_allowed": False,
        "provider_calls_used": 0,
    }
    payload["harvest_digest"] = sha256_digest(payload)
    _write_json(out / "dio_azure_tee_attestation_harvest.json", payload)
    return payload


def _load_or_create_key(path: Path) -> Ed25519PrivateKey:
    path = path.expanduser().resolve()
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise RuntimeError(f"DIO Azure witness key is not Ed25519: {path}")
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


def _provider_state(namespace: str) -> str:
    result = _run(["az", "provider", "show", "--namespace", namespace, "--query", "registrationState", "-o", "tsv"])
    return result.stdout.strip() if result.returncode == 0 else f"unavailable:{result.stderr.strip()[:120]}"


def _tee_type_for_vm(vm: dict[str, Any]) -> DIOCloudTeeType:
    size = str((vm.get("hardwareProfile") or {}).get("vmSize") or "").lower()
    if "tdx" in size:
        return DIOCloudTeeType.AZURE_TDX
    return DIOCloudTeeType.AZURE_SEV_SNP


def _token_shape(raw_token: str) -> dict[str, Any]:
    stripped = raw_token.strip()
    if not stripped:
        return {"shape": "empty"}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        compact = canonical_json(parsed)
        candidates = [
            value for key, value in parsed.items()
            if isinstance(value, str) and ("token" in key.lower() or value.count(".") == 2)
        ]
        return {
            "shape": "json",
            "json_digest": sha256_digest(parsed),
            "json_key_count": len(parsed),
            "jwt_like_field_count": len(candidates),
            "byte_count": len(compact.encode("utf-8")),
        }
    return {
        "shape": "jwt_compact" if stripped.count(".") == 2 else "opaque_text",
        "byte_count": len(stripped.encode("utf-8")),
        "line_count": len(stripped.splitlines()),
    }


def _vm_ref(row: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(row.get("name") or ""),
        "resource_group": str(row.get("resourceGroup") or ""),
        "location": _normalize_location(str(row.get("location") or "")),
        "vm_size": str((row.get("hardwareProfile") or {}).get("vmSize") or ""),
        "security_type": str((row.get("securityProfile") or {}).get("securityType") or ""),
    }


def _normalize_location(value: str) -> str:
    return value.lower().replace(" ", "").replace("-", "")


def _az_json(args: list[str]) -> Any:
    result = _run(["az", *args, "-o", "json"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=120)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_proposal(path: Path) -> DIOProposalPacket:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("packet_digest", None)
    return DIOProposalPacket(**payload)


if __name__ == "__main__":
    raise SystemExit(main())
