#!/usr/bin/env python3
"""Harvest/normalize Google Cloud DIO TEE witness evidence.

This script is intentionally honest about the difference between:

* project/API readiness;
* a Confidential VM existing;
* a provider-verified attestation token/report being available.

When no instance is supplied or present, it emits a blocked receipt instead of
inventing evidence.  When an instance is supplied, it inventories the VM and
only produces normalized `DIOCloudTeeEvidence` when the instance advertises
confidential-compute configuration and all digest pins can be formed.
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
from app.kernel.dai.dio_distributed_quorum import DIOWitnessRole, HARDWARE_WITNESS_AUTHORITY, public_key_fingerprint


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/gcp"
DEFAULT_KEY = ROOT / ".beast/dio-cloud-witness/gcp-governance-01.ed25519.pem"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="")
    parser.add_argument("--zone", default="")
    parser.add_argument("--instance", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--node-id", default="dio:gcp:tee-governance-01")
    parser.add_argument("--role", default=DIOWitnessRole.GOVERNANCE.value)
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--challenge-nonce", default="")
    parser.add_argument("--governance-epoch", default="dai-phase2.1-gcp-cloud-witness")
    args = parser.parse_args()
    result = harvest(
        project=args.project,
        zone=args.zone,
        instance=args.instance,
        out=args.out,
        node_id=args.node_id,
        role=DIOWitnessRole(args.role),
        key_path=args.key_path,
        challenge_nonce=args.challenge_nonce,
        governance_epoch=args.governance_epoch,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("green") else 2


def harvest(
    *,
    project: str,
    zone: str,
    instance: str,
    out: Path,
    node_id: str,
    role: DIOWitnessRole,
    key_path: Path,
    challenge_nonce: str,
    governance_epoch: str,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    active_project = project or _gcloud_value(["config", "get-value", "project"])
    if not active_project:
        return _blocked(out, reason="gcp_project_not_configured", details={})

    api_state = {
        "compute": _service_enabled(active_project, "compute.googleapis.com"),
        "confidentialcomputing": _service_enabled(active_project, "confidentialcomputing.googleapis.com"),
    }
    if not all(api_state.values()):
        return _blocked(out, reason="gcp_required_api_disabled", details={"project": active_project, "api_state": api_state})

    instances = _instances(active_project)
    if not instance:
        if not instances:
            return _blocked(
                out,
                reason="gcp_no_compute_instances_found",
                details={
                    "project": active_project,
                    "api_state": api_state,
                    "next_step": (
                        "Create a Confidential VM witness, then rerun with "
                        "--instance <name> --zone <zone>."
                    ),
                },
            )
        if len(instances) == 1:
            instance = str(instances[0].get("name") or "")
            zone = zone or _zone_name(str(instances[0].get("zone") or ""))
        else:
            return _blocked(
                out,
                reason="gcp_multiple_instances_require_explicit_target",
                details={"project": active_project, "instances": [_instance_ref(row) for row in instances]},
            )

    if not zone:
        zone = _find_instance_zone(instances, instance)
    if not zone:
        return _blocked(out, reason="gcp_instance_zone_required", details={"project": active_project, "instance": instance})

    described = _gcloud_json([
        "compute",
        "instances",
        "describe",
        instance,
        "--zone",
        zone,
        "--project",
        active_project,
    ])
    if not described:
        return _blocked(out, reason="gcp_instance_not_found", details={"project": active_project, "instance": instance, "zone": zone})

    confidential_config = described.get("confidentialInstanceConfig") or {}
    confidential_enabled = confidential_config.get("enableConfidentialCompute") is True
    if not confidential_enabled:
        return _blocked(
            out,
            reason="gcp_instance_not_confidential_compute",
            details={
                "project": active_project,
                "instance": instance,
                "zone": zone,
                "confidentialInstanceConfig": confidential_config,
            },
        )

    key = _load_or_create_key(key_path)
    public_b64 = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    nonce = challenge_nonce or "dio-gcp-" + sha256_digest({"project": active_project, "instance": instance, "zone": zone, "time": now.isoformat()})[-48:]
    instance_identity = {
        "project": active_project,
        "zone": zone,
        "instance": instance,
        "id": described.get("id", ""),
        "selfLink": described.get("selfLink", ""),
        "machineType": described.get("machineType", ""),
        "confidentialInstanceConfig": confidential_config,
        "shieldedInstanceConfig": described.get("shieldedInstanceConfig", {}),
        "disks": described.get("disks", []),
        "metadata": described.get("metadata", {}),
    }
    # This is not the raw Google attestation token. It is the current VM config
    # measurement placeholder until a live in-guest/provider attestation report
    # is harvested. Admission remains honest because the service verification
    # digest declares this exact boundary.
    measurement_digest = sha256_digest(instance_identity)
    evidence = DIOCloudTeeEvidence(
        beast_object_type="dio_cloud_tee_attestation_evidence",
        provider=DIOCloudProvider.GCP,
        tee_type=DIOCloudTeeType.GCP_CONFIDENTIAL_VM_VTPM,
        service_verifier=DIOCloudVerifier.GOOGLE_CLOUD_ATTESTATION,
        node_id=node_id,
        role=role,
        runtime_platform="gcp_confidential_vm_vtpm",
        infrastructure_provider="gcp",
        public_key_b64=public_b64,
        key_fingerprint=public_key_fingerprint(public_b64),
        verifier_commit=sha256_bytes((ROOT / "app/kernel/dai/dio_cloud_attestation.py").read_bytes()),
        container_manifest=sha256_digest({"script": "harvest_dio_gcp_tee_attestation.py", "project": active_project, "zone": zone, "instance": instance}),
        tee_measurement_digest=measurement_digest,
        raw_attestation_digest=sha256_digest({"gcp_instance_identity_inventory": instance_identity}),
        service_verification_digest=sha256_digest({
            "boundary": "gcp_api_inventory_not_in_guest_attestation_token",
            "confidential_compute_enabled": True,
        }),
        challenge_nonce=nonce,
        governance_epoch=governance_epoch,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    policy = DIOCloudTeePolicy(
        policy_id="policy:gcp:confidential-vm:governance:v1",
        provider=DIOCloudProvider.GCP,
        tee_type=DIOCloudTeeType.GCP_CONFIDENTIAL_VM_VTPM,
        service_verifier=DIOCloudVerifier.GOOGLE_CLOUD_ATTESTATION,
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
        "beast_object_type": "dio_gcp_tee_attestation_harvest",
        "project": active_project,
        "zone": zone,
        "instance": instance,
        "green": bool(admission is not None and report.admitted),
        "authority_boundary": (
            "gcp_confidential_compute_inventory_admitted; provider raw attestation token "
            "harvester still required for publication-grade hardware-rooted claim"
        ),
        "production_authority_allowed": False,
        "provider_calls_used": 0,
        "evidence": asdict(evidence),
        "evidence_digest": evidence.evidence_digest,
        "policy": asdict(policy),
        "policy_digest": policy.policy_digest,
        "admission": None if admission is None else asdict(admission),
        "admission_report": asdict(report),
        "admission_report_digest": report.report_digest,
    }
    payload["harvest_digest"] = sha256_digest(payload)
    _write_json(out / "dio_gcp_tee_attestation_harvest.json", payload)
    _write_json(out / "dio_gcp_tee_evidence.json", asdict(evidence) | {"evidence_digest": evidence.evidence_digest})
    _write_json(out / "dio_gcp_tee_policy.json", asdict(policy) | {"policy_digest": policy.policy_digest})
    return payload


def _blocked(out: Path, *, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "beast_object_type": "dio_gcp_tee_attestation_harvest",
        "green": False,
        "blocked": True,
        "blocked_reason": reason,
        "details": details,
        "production_authority_allowed": False,
        "provider_calls_used": 0,
    }
    payload["harvest_digest"] = sha256_digest(payload)
    _write_json(out / "dio_gcp_tee_attestation_harvest.json", payload)
    return payload


def _load_or_create_key(path: Path) -> Ed25519PrivateKey:
    path = path.expanduser().resolve()
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise RuntimeError(f"DIO GCP witness key is not Ed25519: {path}")
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


def _instances(project: str) -> list[dict[str, Any]]:
    payload = _gcloud_json(["compute", "instances", "list", "--project", project])
    return payload if isinstance(payload, list) else []


def _find_instance_zone(instances: list[dict[str, Any]], name: str) -> str:
    for row in instances:
        if row.get("name") == name:
            return _zone_name(str(row.get("zone") or ""))
    return ""


def _instance_ref(row: dict[str, Any]) -> dict[str, str]:
    return {"name": str(row.get("name") or ""), "zone": _zone_name(str(row.get("zone") or ""))}


def _zone_name(value: str) -> str:
    return value.rsplit("/", 1)[-1] if value else ""


def _service_enabled(project: str, service: str) -> bool:
    result = _run(["gcloud", "services", "list", "--enabled", "--project", project, "--filter", f"config.name={service}", "--format", "value(config.name)"])
    return result.returncode == 0 and service in result.stdout.splitlines()


def _gcloud_value(args: list[str]) -> str:
    result = _run(["gcloud", *args])
    return result.stdout.strip() if result.returncode == 0 else ""


def _gcloud_json(args: list[str]) -> Any:
    result = _run(["gcloud", *args, "--format", "json"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=120)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
