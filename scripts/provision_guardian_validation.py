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


CONFIG_FILES = ("guardian-receipt-ed25519.pem", "guardian-receipt-ed25519.pub.pem",
                "arda-guardian-operation-ed25519.pem", "arda-operation-ed25519.pub.pem",
                "guardian-authorization.token", "socket-guardian.yaml", "socket-consumer.env",
                "arda-guardian-compose.yaml")


# closure 2026-11-16: pinned to the digest of the image the live authorizer runs (built 2026-11-15 08:26 SAST).
# Override with BEAST_ARDA_IMAGE (e.g. "seraph-backend:latest") deliberately, never implicitly.
SERAPH_BACKEND_DIGEST = "sha256:a42de2079b075a0e4f57026d9d1a50e47e4d25bfe5daa230c75e201a91183af9"
DEFAULT_ARDA_IMAGE = os.environ.get("BEAST_ARDA_IMAGE") or f"seraph-backend@{SERAPH_BACKEND_DIGEST}"
DEFAULT_ARDA_SOURCE = Path("/usr/lib/arda/src/arda_os")  # root-owned installed ARDA OS tree
BUILD_ARDA_IMAGE = "beast-arda-guardian-authorizer:local"
ARDA_DOCKERFILE = "live_arda_fabric/Dockerfile.python-service"
ARDA_MODULES = ("arda_authorization_service.py", "guardian_operation_authority.py")
ARDA_PORT = "127.0.0.1:18401:8080"


def _arda_source_files(source_root: Path, *, forbidden_mode: int = 0o022) -> dict[str, Path]:
    """Locate the Metatron ARDA authorizer modules; refuse writable-by-others code.

    Mounted (image-mode) sources must be neither group- nor world-writable; a build context is the
    operator's own checkout (private user group), so only world-writable files are refused there.
    """
    files = {}
    for name in ARDA_MODULES:
        path = Path(source_root).expanduser() / "backend" / "services" / name
        if not path.is_file():
            raise FileNotFoundError(f"ARDA authorizer source missing: {path.name} under {source_root}")
        if path.is_symlink():
            raise PermissionError(f"ARDA authorizer source must not be a symlink: {path}")
        if stat.S_IMODE(path.stat().st_mode) & forbidden_mode:
            raise PermissionError(f"ARDA authorizer source is writable by others: {path}")
        files[name] = path.resolve()
    return files


def arda_compose(*, environment: dict[str, str], roots: dict[str, Path], arda_image: str = DEFAULT_ARDA_IMAGE,
                 arda_source: Path = DEFAULT_ARDA_SOURCE, arda_build_context: Path | None = None
                 ) -> tuple[dict[str, object], dict[str, str]]:
    """Standalone compose for the Metatron ARDA Guardian authorizer on 127.0.0.1:18401 (never started here).

    image mode: run the installed ``backend.services.arda_authorization_service`` from ``arda_source`` (two
    read-only file mounts, namespace package under /opt/arda) inside an image that already ships FastAPI,
    uvicorn and cryptography (default ``seraph-backend:latest``).
    build mode: rebuild the July 2026 ``Metatron/live_arda_fabric/Dockerfile.python-service`` image.
    """
    volumes = [f"{host}:{container}:ro" for container, host in roots.items()]
    labels: dict[str, str] = {}
    digests: dict[str, str] = {}
    if arda_build_context is not None:
        context = Path(arda_build_context).expanduser().resolve()
        if not (context / ARDA_DOCKERFILE).is_file():
            raise FileNotFoundError(f"ARDA build context lacks {ARDA_DOCKERFILE}: {context}")
        for name, path in _arda_source_files(context, forbidden_mode=0o002).items():
            digests[name] = _sha256_file(path)
        runtime: dict[str, object] = {"build": {"context": str(context), "dockerfile": ARDA_DOCKERFILE},
                                      "image": BUILD_ARDA_IMAGE, "working_dir": "/app"}
        python_path = "/app"
    else:
        for name, path in _arda_source_files(arda_source).items():
            digests[name] = _sha256_file(path)
            volumes.append(f"{path}:/opt/arda/backend/services/{name}:ro")
        runtime = {"image": arda_image, "working_dir": "/opt/arda"}
        python_path = "/opt/arda"
    for name, digest in digests.items():
        labels["beast.arda.source." + name.removesuffix(".py")] = digest
    service = {
        **runtime,
        "command": ["uvicorn", "backend.services.arda_authorization_service:app", "--host", "0.0.0.0",
                    "--port", "8080"],
        "user": f"{os.getuid()}:{os.getgid()}",
        "restart": "unless-stopped",
        "read_only": True,
        "tmpfs": ["/tmp"],
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "ports": [ARDA_PORT],
        "environment": {"PYTHONPATH": python_path, "PYTHONDONTWRITEBYTECODE": "1",
                        "ARDA_CRYSTAL_AUTHORIZATION_MODE": "deny", **environment},
        "volumes": volumes,
        "labels": labels,
        "healthcheck": {"test": ["CMD", "curl", "-fsS", "http://127.0.0.1:8080/docs"], "interval": "10s",
                        "timeout": "3s", "retries": 10},
    }
    return {"name": "beast-arda-guardian", "services": {"arda-authorizer": service}}, digests


def plan(config_root: Path, state_root: Path, proof: Path | None = None) -> dict[str, object]:
    """Read-only preview of what ``provision`` would create (writes nothing)."""
    config_root = config_root.expanduser()
    state_root = state_root.expanduser()
    files = [str(config_root / name) for name in CONFIG_FILES]
    files.append(str(state_root / "guardian-deployment-appraisal.json"))
    return {"would_create": [f for f in files if not Path(f).exists()],
            "existing_kept": [f for f in files if Path(f).exists()],
            "sovereign_proof": str(proof) if proof else "",
            "sovereign_proof_exists": bool(proof and Path(proof).expanduser().is_file()),
            "note": "existing private keys/tokens are reused only if mode 0600 and not symlinks"}


def provision(config_root: Path, state_root: Path, proof: Path, *, registry_path: Path | None = None,
              lab_manifest: Path | None = None, compose_base: Path | None = None,
              compose_override: Path | None = None, arda_image: str = DEFAULT_ARDA_IMAGE,
              arda_source: Path = DEFAULT_ARDA_SOURCE, arda_build_context: Path | None = None) -> dict[str, object]:
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
    if arda_build_context is None:  # fail before writing any root material
        _arda_source_files(arda_source)
    elif not (Path(arda_build_context).expanduser() / ARDA_DOCKERFILE).is_file():
        raise FileNotFoundError(f"ARDA build context lacks {ARDA_DOCKERFILE}: {arda_build_context}")

    from app.kernel.networking.fabric_topology import FabricTopology

    registry_path = Path(registry_path or ROOT / ".byron" / "services.yaml").resolve()
    registry = ServiceRegistry.from_file(registry_path)
    lab_manifest = Path(lab_manifest or ROOT / ".beast" / "remote-commons-lab" / "manifest.json").resolve()
    compose_base = Path(compose_base or ROOT / "docker-compose.commons-lab.yml").resolve()
    topology = FabricTopology.load(services_path=registry_path, lab_manifest_path=lab_manifest,
                                   compose_base_path=compose_base, compose_override_path=compose_override)
    contract = topology.guardian_bindings()  # raises TopologyDriftError: never provision against drift
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
            "topology": {
                "lab_manifest": str(lab_manifest),
                "compose_base": str(compose_base),
                "compose_override": str(compose_override or ""),
            },
            # Ruling D3.1/Task 2: bindings equal the topology contract (socket_guardian services only).
            "systemd_bindings": {
                name: {
                    **binding,
                    "vrf": registry.services[name].trust_domain,
                }
                for name in sorted(contract["services"])
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

    compose, arda_source_digests = arda_compose(
        environment={
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
        roots={
            "/run/arda-roots/arda-guardian-operation.pem": authority_private,
            "/run/arda-roots/guardian-authorization.token": token_path,
            "/run/arda-roots/guardian-deployment-appraisal.json": evidence_path,
        },
        arda_image=arda_image or DEFAULT_ARDA_IMAGE,
        arda_source=arda_source,
        arda_build_context=arda_build_context,
    )
    compose_path = config_root / "arda-guardian-compose.yaml"
    _atomic_write(compose_path, yaml.safe_dump(compose, sort_keys=False).encode(), 0o600)

    return {
        "arda_image": compose["services"]["arda-authorizer"]["image"],
        "arda_source_digests": arda_source_digests,
        "warnings": [],
        "appraisal_ref": appraisal_ref,
        "capability_ref": capability_ref,
        "compose": str(compose_path),
        "evidence": str(evidence_path),
        "evidence_digest": evidence_digest,
        "executable_digest": executable_digest,
        "guardian_config": str(guardian_config_path),
        "policy_generation": policy_generation,
        "registry_digest": registry_digest,
        "topology_digest": contract["topology_digest"],
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
    parser.add_argument("--registry", default=str(ROOT / ".byron" / "services.yaml"))
    parser.add_argument("--plan", action="store_true", help="print what would be created; write nothing")
    parser.add_argument("--arda-image", default=DEFAULT_ARDA_IMAGE,
                        help="image providing fastapi/uvicorn/cryptography for the ARDA authorizer")
    parser.add_argument("--arda-source", default=str(DEFAULT_ARDA_SOURCE),
                        help="tree containing backend/services/arda_authorization_service.py (mounted read-only)")
    parser.add_argument("--arda-build-context", default="",
                        help="Metatron checkout: build live_arda_fabric/Dockerfile.python-service instead")
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(Path(args.config_root), Path(args.state_root), Path(args.sovereign_proof)),
                         sort_keys=True, indent=2))
        return 0
    result = provision(Path(args.config_root), Path(args.state_root), Path(args.sovereign_proof),
                       registry_path=Path(args.registry), arda_image=args.arda_image,
                       arda_source=Path(args.arda_source),
                       arda_build_context=Path(args.arda_build_context) if args.arda_build_context else None)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
