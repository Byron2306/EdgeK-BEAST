#!/usr/bin/env python3
"""Provision a host-local, fail-closed Guardian/ARDA validation profile.

This intentionally does not claim hardware attestation or production HSM key
custody. It creates distinct host-only Ed25519 roots, binds a reviewed static
sovereign-proof digest into the deployment appraisal, and writes no secrets to
the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from datetime import datetime, timezone

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.networking.service_registry import ServiceRegistry
from app.kernel.workspaces.workspace_identity import discover, stable_workspace_uuid


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_TRUNC
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary, flags, mode)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(f"short write while provisioning {path}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _private_key(path: Path) -> Ed25519PrivateKey:
    if path.exists():
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise PermissionError(f"refusing insecure existing private key: {path}")
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError(f"existing key is not Ed25519: {path}")
        return key
    key = Ed25519PrivateKey.generate()
    _atomic_write(
        path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        0o600,
    )
    return key


def _public_key(path: Path, key: Ed25519PrivateKey) -> None:
    _atomic_write(
        path,
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        0o644,
    )


def _token(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise PermissionError(f"refusing insecure existing token: {path}")
        if not path.read_text(encoding="utf-8").strip():
            raise ValueError("existing Guardian authorization token is empty")
        return
    _atomic_write(path, (secrets.token_urlsafe(48) + "\n").encode(), 0o600)


def provision(config_root: Path, state_root: Path, proof: Path) -> dict[str, str]:
    config_root = config_root.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    proof = proof.expanduser().resolve()
    for directory in (config_root, state_root):
        if directory.is_symlink():
            raise PermissionError(f"provisioning directory must not be a symbolic link: {directory}")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    if not proof.is_file() or proof.is_symlink():
        raise FileNotFoundError("reviewed sovereign proof manifest is unavailable")

    registry_path = ROOT / ".byron" / "services.yaml"
    registry = ServiceRegistry.from_file(registry_path)
    identity = discover(ROOT, workspace_uuid=stable_workspace_uuid(ROOT))
    workspace_id = identity.digest()
    registry_digest = registry.digest()
    interpreter = Path(sys.executable).resolve()
    executable_digest = _sha256_file(interpreter)
    policy_generation = "beast-policy:2026-07-15:s13-guardian-v1"
    proof_digest = _sha256_file(proof)
    reference_seed = {
        "policy_generation": policy_generation,
        "registry_digest": registry_digest,
        "sovereign_proof_digest": proof_digest,
        "workspace_id": workspace_id,
    }
    reference_digest = _sha256_bytes(
        json.dumps(reference_seed, sort_keys=True, separators=(",", ":")).encode()
    )
    appraisal_ref = "arda:guardian-appraisal:" + reference_digest.removeprefix("sha256:")
    capability_ref = "deployment:beast-commons:" + reference_digest.removeprefix("sha256:")

    receipt_private = config_root / "guardian-receipt-ed25519.pem"
    receipt_public = config_root / "guardian-receipt-ed25519.pub.pem"
    authority_private = config_root / "arda-guardian-operation-ed25519.pem"
    authority_public = config_root / "arda-operation-ed25519.pub.pem"
    token_path = config_root / "guardian-authorization.token"
    receipt_key = _private_key(receipt_private)
    authority_key = _private_key(authority_private)
    _public_key(receipt_public, receipt_key)
    _public_key(authority_public, authority_key)
    _token(token_path)

    evidence_path = state_root / "guardian-deployment-appraisal.json"
    evidence = {
        "schema": "beast.guardian.deployment-appraisal.v1",
        "status": "local_validation",
        "claim_boundary": "static sovereign-proof binding; not live boot attestation or HSM custody",
        "workspace_id": workspace_id,
        "workspace_uuid": identity.workspace_uuid,
        "registry_digest": registry_digest,
        "interpreter": str(interpreter),
        "executable_digest": executable_digest,
        "policy_generation": policy_generation,
        "appraisal_ref": appraisal_ref,
        "deployment_capability_ref": capability_ref,
        "sovereign_proof": {
            "source": "metatron/live_horror_class_proof_qwen15m/00_manifest.json",
            "digest": proof_digest,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(
        evidence_path,
        (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode(),
        0o644,
    )
    evidence_digest = _sha256_file(evidence_path)

    binding = {
        "workspace_id": workspace_id,
        "authority_ref": "arda",
        "capability_ref": capability_ref,
        "appraisal_ref": appraisal_ref,
        "policy_generation": policy_generation,
    }
    guardian_config = {
        "version": 1,
        "guardian": {
            "control_socket": "${XDG_RUNTIME_DIR}/beast/socket-guardian.sock",
            "lease_ledger": "${XDG_STATE_HOME}/beast/socket-guardian-leases.sqlite3",
            "capability_ledger": "${XDG_STATE_HOME}/beast/socket-guardian-capabilities.sqlite3",
            "service_registry": str(registry_path),
            "receipt_signing_key": str(receipt_private),
            "operation_authority_public_keys": {"arda": str(authority_public)},
            "systemd_bindings": {
                name: {
                    **binding,
                    "vrf": service.trust_domain,
                }
                for name, service in registry.services.items()
                if service.enabled
            },
        },
    }
    guardian_config_path = config_root / "socket-guardian.yaml"
    _atomic_write(
        guardian_config_path,
        yaml.safe_dump(guardian_config, sort_keys=False).encode(),
        0o600,
    )

    consumer_environment = "\n".join(
        (
            "BEAST_GUARDIAN_AUTHORIZATION_URL=http://127.0.0.1:18401/authorize/socket-guardian",
            "BEAST_GUARDIAN_AUTHORITY=arda",
            f"BEAST_GUARDIAN_WORKSPACE_ID={workspace_id}",
            f"BEAST_GUARDIAN_POLICY_GENERATION={policy_generation}",
            f"BEAST_GUARDIAN_APPRAISAL_REF={appraisal_ref}",
            "BEAST_GUARDIAN_STARTUP_TIMEOUT=30",
            "BEAST_WORKSPACE_IDENTITY_MODE=enforce",
            "",
        )
    )
    _atomic_write(
        config_root / "socket-consumer.env", consumer_environment.encode(), 0o600
    )

    compose = {
        "services": {
            "arda-authorizer": {
                "restart": "unless-stopped",
                "ports": ["127.0.0.1:18401:8080"],
                "environment": {
                    "ARDA_GUARDIAN_AUTHORIZATION_MODE": "allow-listed",
                    "ARDA_GUARDIAN_OPERATION_PRIVATE_KEY": "/run/arda-roots/arda-guardian-operation.pem",
                    "ARDA_GUARDIAN_AUTHORIZATION_TOKEN_FILE": "/run/arda-roots/guardian-authorization.token",
                    "ARDA_GUARDIAN_APPRAISAL_EVIDENCE_FILE": "/run/arda-roots/guardian-deployment-appraisal.json",
                    "ARDA_GUARDIAN_APPRAISAL_EVIDENCE_DIGEST": evidence_digest,
                    "ARDA_GUARDIAN_WORKSPACE_ID": workspace_id,
                    "ARDA_GUARDIAN_POLICY_GENERATION": policy_generation,
                    "ARDA_GUARDIAN_APPRAISAL_REF": appraisal_ref,
                    "ARDA_GUARDIAN_DEPLOYMENT_CAPABILITY_REF": capability_ref,
                    "ARDA_GUARDIAN_SERVICE_REGISTRY_DIGEST": registry_digest,
                    "ARDA_GUARDIAN_EXECUTABLE_DIGESTS": executable_digest,
                    "ARDA_GUARDIAN_KEY_ID": "arda-guardian-operation-v1",
                    "ARDA_GUARDIAN_CAPABILITY_TTL": "20",
                },
                "volumes": [
                    f"{authority_private}:/run/arda-roots/arda-guardian-operation.pem:ro",
                    f"{token_path}:/run/arda-roots/guardian-authorization.token:ro",
                    f"{evidence_path}:/run/arda-roots/guardian-deployment-appraisal.json:ro",
                ],
            }
        }
    }
    compose_path = config_root / "arda-guardian-compose.yaml"
    _atomic_write(compose_path, yaml.safe_dump(compose, sort_keys=False).encode(), 0o600)

    return {
        "appraisal_ref": appraisal_ref,
        "capability_ref": capability_ref,
        "compose": str(compose_path),
        "evidence": str(evidence_path),
        "evidence_digest": evidence_digest,
        "executable_digest": executable_digest,
        "guardian_config": str(guardian_config_path),
        "policy_generation": policy_generation,
        "registry_digest": registry_digest,
        "workspace_id": workspace_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", default="~/.config/beast")
    parser.add_argument("--state-root", default="~/.local/state/beast")
    parser.add_argument(
        "--sovereign-proof",
        default=(
            "/home/byron/Downloads/Metatron-triune-outbound-gate/"
            "live_horror_class_proof_qwen15m/00_manifest.json"
        ),
    )
    args = parser.parse_args()
    result = provision(Path(args.config_root), Path(args.state_root), Path(args.sovereign_proof))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
