import os
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.socket_guardian_daemon import build_server
from scripts.generate_socket_guardian_units import generate


def _write_key_material(tmp_path):
    receipt = Ed25519PrivateKey.generate()
    receipt_path = tmp_path / "receipt.pem"
    receipt_path.write_bytes(receipt.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    receipt_path.chmod(0o600)
    authority_path = tmp_path / "arda.pub.pem"
    authority_path.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return receipt_path, authority_path


def _config(tmp_path, *, placeholder=False):
    receipt_path, authority_path = _write_key_material(tmp_path)
    registry = tmp_path / "services.yaml"
    registry.write_text(yaml.safe_dump({
        "services": {
            "reverse_proxy": {"port": 80},
            "beast": {
                "hostname": "beast.test",
                "upstream": "127.0.0.1:18101",
                "port": 18101,
                "trust_domain": "operator",
            },
        }
    }), encoding="utf-8")
    config = tmp_path / "guardian.yaml"
    config.write_text(yaml.safe_dump({
        "guardian": {
            "control_socket": str(tmp_path / "guardian.sock"),
            "lease_ledger": str(tmp_path / "leases.sqlite3"),
            "capability_ledger": str(tmp_path / "capabilities.sqlite3"),
            "service_registry": str(registry),
            "receipt_signing_key": str(receipt_path),
            "operation_authority_public_keys": {"arda": str(authority_path)},
            "systemd_bindings": {
                "beast": {
                    "workspace_id": "REPLACE_WITH_WORKSPACE_UUID" if placeholder else "workspace-1",
                    "authority_ref": "arda",
                    "capability_ref": "deployment-capability:1",
                    "appraisal_ref": "arda-appraisal:1",
                    "policy_generation": "policy:7",
                }
            },
        }
    }), encoding="utf-8")
    return registry, config


def test_guardian_daemon_config_builds_fail_closed_server(tmp_path):
    _registry, config = _config(tmp_path)
    server, bindings = build_server(config)
    assert server.require_authority is True
    assert server.require_process_lease is True
    assert bindings["beast"]["registry_digest"].startswith("sha256:")


def test_guardian_daemon_refuses_placeholder_authority_binding(tmp_path):
    _registry, config = _config(tmp_path, placeholder=True)
    with pytest.raises(RuntimeError, match="placeholder"):
        build_server(config)


def test_unit_generator_uses_named_descriptors_and_does_not_install(tmp_path):
    registry, config = _config(tmp_path)
    output = tmp_path / "generated"
    paths = generate(registry, config, output, Path("/opt/beast"))
    service = (output / "beast-socket-guardian.service").read_text(encoding="utf-8")
    socket_unit = (output / "beast-socket-guardian-beast.socket").read_text(encoding="utf-8")
    assert "NoNewPrivileges=yes" in service
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in service
    assert "FileDescriptorName=beast" in socket_unit
    assert "ListenStream=127.0.0.1:18101" in socket_unit
    assert "Requires=beast-socket-guardian-beast.socket" in service
    consumer = (output / "beast-beast-guardian-consumer.service").read_text(encoding="utf-8")
    assert "gateway --socket-mode guardian" in consumer
    assert "BEAST_STATE_ROOT=%S/beast" in consumer
    assert "BEAST_COMMONS_ROOT=%S/beast/commons-spaces" in consumer
    assert "BEAST_GUARDIAN_CONTROL_SOCKET=%t/beast/socket-guardian.sock" in consumer
    assert "LoadCredential=guardian_authorization_token:" in consumer
    assert "BEAST_GUARDIAN_AUTHORIZATION_TOKEN_FILE=%d/guardian_authorization_token" in consumer
    assert all(path.parent == output for path in paths)
