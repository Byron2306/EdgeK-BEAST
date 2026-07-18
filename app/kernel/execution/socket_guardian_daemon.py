"""Production entry point for the externally supervised Socket Guardian."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import threading
from typing import Any, Mapping

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.execution.guardian_authorization import GuardianCapabilityAuthorizer
from app.kernel.execution.socket_guardian import SocketGuardianServer
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.networking.service_registry import ServiceRegistry


def _resolve(config_path: Path, value: str) -> Path:
    expanded = os.path.expandvars(str(value))
    if "$" in expanded:
        raise RuntimeError(f"socket guardian path contains an unresolved environment variable: {value}")
    path = Path(expanded).expanduser()
    return path if path.is_absolute() else (config_path.parent / path).resolve()


def _required(payload: Mapping[str, Any], field: str) -> Any:
    value = payload.get(field)
    if value in (None, "", {}, []):
        raise RuntimeError(f"socket guardian configuration requires {field}")
    return value


def _authority_reference(payload: Mapping[str, Any], field: str) -> str:
    value = str(_required(payload, field))
    if value.startswith("REPLACE_"):
        raise RuntimeError(f"socket guardian refuses placeholder authority reference {field}")
    return value


def _private_signer(path: Path) -> Ed25519PrivateKey:
    if path.is_symlink():
        raise PermissionError("guardian signing key must not be a symbolic link")
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise PermissionError("guardian signing key permissions must be 0600 or stricter")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("guardian receipt key must be Ed25519")
    return key


def _authority_verifiers(config_path: Path, values: Mapping[str, Any]) -> dict[str, Ed25519PublicKey]:
    verifiers: dict[str, Ed25519PublicKey] = {}
    for authority, raw_path in values.items():
        path = _resolve(config_path, str(raw_path))
        if path.is_symlink():
            raise PermissionError(f"authority key for {authority} must not be a symbolic link")
        key = serialization.load_pem_public_key(path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError(f"authority key for {authority} must be Ed25519")
        verifiers[str(authority)] = key
    if not verifiers:
        raise RuntimeError("at least one ARDA/Metatron authority public key is required")
    return verifiers


def build_server(config_file: str | Path) -> tuple[SocketGuardianServer, Mapping[str, Mapping[str, Any]]]:
    config_path = Path(config_file).expanduser().resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise RuntimeError("socket guardian configuration must be a mapping")
    guardian = _required(payload, "guardian")
    if not isinstance(guardian, Mapping):
        raise RuntimeError("guardian configuration must be a mapping")

    registry_path = _resolve(config_path, str(_required(guardian, "service_registry")))
    registry = ServiceRegistry.from_file(registry_path)
    signer = _private_signer(_resolve(config_path, str(_required(guardian, "receipt_signing_key"))))
    verifiers = _authority_verifiers(
        config_path, _required(guardian, "operation_authority_public_keys")
    )
    capability_ledger = OneUseCapabilityLedger(
        verifiers,
        _resolve(config_path, str(_required(guardian, "capability_ledger"))),
        require_verifier=True,
    )
    authorizer = GuardianCapabilityAuthorizer(
        capability_ledger, allowed_authorities=verifiers.keys()
    )
    server = SocketGuardianServer(
        _resolve(config_path, str(_required(guardian, "control_socket"))),
        _resolve(config_path, str(_required(guardian, "lease_ledger"))),
        expected_uid=int(guardian.get("expected_uid", os.getuid())),
        signer=signer,
        guardian_id=str(guardian.get("guardian_id") or "beast.socket-guardian.v1"),
        require_authority=True,
        require_process_lease=True,
        authorize=authorizer,
        service_registry=registry,
    )
    raw_bindings = _required(guardian, "systemd_bindings")
    if not isinstance(raw_bindings, Mapping):
        raise RuntimeError("systemd_bindings must be a mapping")
    bindings: dict[str, Mapping[str, Any]] = {}
    for service_id, item in raw_bindings.items():
        if service_id not in registry.services:
            raise RuntimeError(f"systemd binding references unknown service {service_id}")
        if not isinstance(item, Mapping):
            raise RuntimeError(f"systemd binding for {service_id} must be a mapping")
        bindings[str(service_id)] = {
            "workspace_id": _authority_reference(item, "workspace_id"),
            "authority_ref": _authority_reference(item, "authority_ref"),
            "capability_ref": _authority_reference(item, "capability_ref"),
            "appraisal_ref": _authority_reference(item, "appraisal_ref"),
            "policy_generation": _authority_reference(item, "policy_generation"),
            "registry_digest": registry.digest(),
            "network_namespace": str(item.get("network_namespace") or "host"),
            "vrf": str(item.get("vrf") or registry.services[str(service_id)].trust_domain),
        }
    return server, bindings


def run(config_file: str | Path) -> None:
    server, bindings = build_server(config_file)
    server.adopt_systemd_environment(bindings)
    server.start()
    stop = threading.Event()

    def shutdown(_signum, _frame):
        stop.set()
        server.stop()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever()
    finally:
        if not stop.is_set():
            server.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BEAST Socket Guardian")
    parser.add_argument("--config", required=True, help="Path to the fail-closed guardian YAML configuration")
    args = parser.parse_args()
    run(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
