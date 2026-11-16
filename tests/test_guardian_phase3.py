"""Guardian Phase 3 Tasks 2-4: topology-bound daemon with host roots (D3.1), generated units (D3.2), Docker
custody records (D3.3). Everything runs in tmp dirs: no ~/.config writes, no ARDA, no systemctl."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_fabric_topology import _sources  # noqa: E402

from app.kernel.execution.socket_guardian_daemon import build_server  # noqa: E402

BINDING = {"workspace_id": "workspace-1", "authority_ref": "arda", "capability_ref": "deployment-capability:1",
           "appraisal_ref": "arda-appraisal:1", "policy_generation": "policy:7"}


def _keys(tmp_path):
    receipt = Ed25519PrivateKey.generate()
    receipt_path = tmp_path / "receipt.pem"
    receipt_path.write_bytes(receipt.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    receipt_path.chmod(0o600)
    authority_path = tmp_path / "arda.pub.pem"
    authority_path.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return receipt, receipt_path, authority_path


def _config(tmp_path, *, bindings=("beast", "commons"), authorities=("arda",), **source_kw):
    tmp_path.mkdir(parents=True, exist_ok=True)
    services, manifest, compose, override = _sources(tmp_path, **source_kw)
    _receipt, receipt_path, authority_path = _keys(tmp_path)
    config = tmp_path / "guardian.yaml"
    config.write_text(yaml.safe_dump({"guardian": {
        "control_socket": str(tmp_path / "guardian.sock"),
        "lease_ledger": str(tmp_path / "leases.sqlite3"),
        "capability_ledger": str(tmp_path / "caps.sqlite3"),
        "service_registry": str(services),
        "receipt_signing_key": str(receipt_path),
        "operation_authority_public_keys": {a: str(authority_path) for a in authorities},
        "topology": {"lab_manifest": str(manifest), "compose_base": str(compose),
                     "compose_override": str(override or "")},
        "systemd_bindings": {name: dict(BINDING) for name in bindings},
    }}), encoding="utf-8")
    return config, services, manifest, compose


# -- Task 2: topology-bound daemon (D3.1) -----------------------------------------------------------------------
def test_daemon_binds_exactly_the_topology_contract(tmp_path):
    config, *_ = _config(tmp_path)
    server, bindings = build_server(config)
    assert set(bindings) == {"beast", "commons"}
    assert bindings["beast"]["contract_port"] == 8101 and bindings["commons"]["contract_port"] == 8601
    assert bindings["beast"]["topology_digest"].startswith("sha256:")
    assert server.require_authority is True


def test_topology_drift_blocks_daemon_startup(tmp_path):
    config, *_ = _config(tmp_path, compose_ports=(8111, 8112, 8199))
    with pytest.raises(RuntimeError, match="topology drift"):
        build_server(config)


def test_daemon_bindings_are_adoptable_and_enforce_contract_port(tmp_path):
    """Regression (2026-11-16 live lab): build_server bindings must be accepted by adopt_inherited_socket."""
    import socket as _socket

    from app.kernel.execution.socket_guardian_daemon import build_server

    config, *_ = _config(tmp_path)
    server, bindings = build_server(config)
    listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        with pytest.raises(PermissionError, match="topology contract port"):
            server.adopt_inherited_socket("beast", listener, **bindings["beast"])  # 8101 != ephemeral
        lease = server.adopt_inherited_socket("beast", listener, **{**bindings["beast"], "contract_port": port})
        assert lease.service_id == "beast"
    finally:
        listener.close()


def test_guardian_commons_port_collision_blocks_startup(tmp_path):
    config, *_ = _config(tmp_path, beast_port=8111)
    with pytest.raises(RuntimeError, match="topology drift"):
        build_server(config)


def test_binding_outside_contract_or_missing_contract_service_refused(tmp_path):
    extra, *_ = _config(tmp_path / "a", bindings=("beast", "commons", "seraph_ui"))
    with pytest.raises(RuntimeError, match="binding set must equal the topology contract"):
        build_server(extra)
    missing, *_ = _config(tmp_path / "b", bindings=("beast",))
    with pytest.raises(RuntimeError, match="binding set must equal the topology contract"):
        build_server(missing)


def test_arda_operation_authority_is_required(tmp_path):
    config, *_ = _config(tmp_path, authorities=("metatron",))
    with pytest.raises(RuntimeError, match="ARDA operation authority"):
        build_server(config)


def test_insecure_receipt_key_refused(tmp_path):
    config, *_ = _config(tmp_path)
    (tmp_path / "receipt.pem").chmod(0o644)
    with pytest.raises(PermissionError):
        build_server(config)


# -- D3.1 provisioning into a tmp config root (never ~/.config/beast in tests) ----------------------------------
def test_provision_writes_host_roots_with_arda_and_contract_bindings_only(tmp_path, monkeypatch):
    from scripts import provision_guardian_validation as provision

    proof = tmp_path / "proof.json"
    proof.write_text('{"proof": 1}')
    services, manifest, compose, _ = _sources(tmp_path)
    result = provision.provision(tmp_path / "cfg", tmp_path / "state", proof, registry_path=services,
                                 lab_manifest=manifest, compose_base=compose)
    cfg = tmp_path / "cfg"
    for name in ("guardian-receipt-ed25519.pem", "arda-guardian-operation-ed25519.pem", "guardian-authorization.token",
                 "socket-guardian.yaml", "socket-consumer.env"):
        assert (cfg / name).stat().st_mode & 0o077 == 0, name
    config = yaml.safe_load((cfg / "socket-guardian.yaml").read_text())["guardian"]
    assert set(config["systemd_bindings"]) == {"beast", "commons"}  # socket_guardian services only
    assert set(config["operation_authority_public_keys"]) == {"arda"}
    assert config["topology"]["lab_manifest"] == str(manifest)
    assert result["topology_digest"].startswith("sha256:")
    blob = json.dumps(result)
    assert "PRIVATE KEY" not in blob


def _arda_source(tmp_path, mode=0o644):
    services = tmp_path / "arda_os" / "backend" / "services"
    services.mkdir(parents=True)
    for name in ("arda_authorization_service.py", "guardian_operation_authority.py"):
        (services / name).write_text(f"# {name}\n")
        (services / name).chmod(mode)
    return tmp_path / "arda_os"


def _provision_with_arda(tmp_path, sub="cfg", **kwargs):
    from scripts import provision_guardian_validation as provision

    proof = tmp_path / "proof.json"
    proof.write_text('{"proof": 1}')
    services, manifest, compose, _ = _sources(tmp_path) if not (tmp_path / "services.yaml").exists() else (
        tmp_path / "services.yaml", tmp_path / "manifest.json", tmp_path / "docker-compose.commons-lab.yml", None)
    kwargs.setdefault("arda_source", _arda_source(tmp_path) if not (tmp_path / "arda_os").exists() else tmp_path / "arda_os")
    result = provision.provision(tmp_path / sub, tmp_path / (sub + "-state"), proof, registry_path=services,
                                 lab_manifest=manifest, compose_base=compose, **kwargs)
    spec = yaml.safe_load((tmp_path / sub / "arda-guardian-compose.yaml").read_text())
    return result, spec


def test_arda_compose_runs_metatron_authorizer_from_installed_source_in_seraph_image(tmp_path):
    result, spec = _provision_with_arda(tmp_path)
    svc = spec["services"]["arda-authorizer"]
    assert spec["name"] == "beast-arda-guardian"
    assert svc["image"].startswith("seraph-backend@sha256:") and "build" not in svc  # closure 2026-11-16: digest pin
    assert svc["command"] == ["uvicorn", "backend.services.arda_authorization_service:app",
                              "--host", "0.0.0.0", "--port", "8080"]
    assert svc["ports"] == ["127.0.0.1:18401:8080"]
    assert svc["user"] == f"{os.getuid()}:{os.getgid()}"
    assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in svc["security_opt"]
    assert svc["working_dir"] == "/opt/arda" and svc["environment"]["PYTHONPATH"] == "/opt/arda"
    assert svc["environment"]["ARDA_CRYSTAL_AUTHORIZATION_MODE"] == "deny"
    assert svc["environment"]["ARDA_GUARDIAN_AUTHORIZATION_MODE"] == "allow-listed"
    assert all(v.endswith(":ro") for v in svc["volumes"])
    mounts = {v.split(":")[1]: v.split(":")[0] for v in svc["volumes"]}
    env = svc["environment"]
    for var in ("ARDA_GUARDIAN_OPERATION_PRIVATE_KEY", "ARDA_GUARDIAN_AUTHORIZATION_TOKEN_FILE",
                "ARDA_GUARDIAN_APPRAISAL_EVIDENCE_FILE"):
        host = Path(mounts[env[var]])
        assert host.is_file() and not host.is_symlink(), var
    for var in ("ARDA_GUARDIAN_OPERATION_PRIVATE_KEY", "ARDA_GUARDIAN_AUTHORIZATION_TOKEN_FILE"):
        assert Path(mounts[env[var]]).stat().st_mode & 0o077 == 0, var  # authority requires 0600
    assert Path(mounts[env["ARDA_GUARDIAN_APPRAISAL_EVIDENCE_FILE"]]).stat().st_mode & 0o022 == 0
    assert "/opt/arda/backend/services/arda_authorization_service.py" in mounts
    assert "/opt/arda/backend/services/guardian_operation_authority.py" in mounts
    for var in ("ARDA_GUARDIAN_WORKSPACE_ID", "ARDA_GUARDIAN_POLICY_GENERATION", "ARDA_GUARDIAN_APPRAISAL_REF",
                "ARDA_GUARDIAN_DEPLOYMENT_CAPABILITY_REF", "ARDA_GUARDIAN_SERVICE_REGISTRY_DIGEST",
                "ARDA_GUARDIAN_EXECUTABLE_DIGESTS", "ARDA_GUARDIAN_APPRAISAL_EVIDENCE_DIGEST"):
        assert env[var] and not str(env[var]).startswith("REPLACE_"), var
    assert env["ARDA_GUARDIAN_SERVICE_REGISTRY_DIGEST"] == result["registry_digest"]
    assert env["ARDA_GUARDIAN_APPRAISAL_EVIDENCE_DIGEST"] == result["evidence_digest"]
    assert result["arda_source_digests"]["arda_authorization_service.py"].startswith("sha256:")
    assert svc["labels"]["beast.arda.source.arda_authorization_service"] == \
        result["arda_source_digests"]["arda_authorization_service.py"]
    assert "curl" in " ".join(svc["healthcheck"]["test"]) and "8080/docs" in " ".join(svc["healthcheck"]["test"])
    assert result["warnings"] == []
    blob = (tmp_path / "cfg" / "arda-guardian-compose.yaml").read_text()
    assert "PRIVATE KEY" not in blob and "BEGIN" not in blob


def test_arda_compose_build_mode_uses_metatron_live_fabric_dockerfile(tmp_path):
    metatron = tmp_path / "Metatron"
    (metatron / "live_arda_fabric").mkdir(parents=True)
    (metatron / "live_arda_fabric" / "Dockerfile.python-service").write_text("FROM python:3.11-slim\n")
    (metatron / "backend" / "services").mkdir(parents=True)
    for name in ("arda_authorization_service.py", "guardian_operation_authority.py"):
        (metatron / "backend" / "services" / name).write_text("# metatron\n")
    _, spec = _provision_with_arda(tmp_path, arda_build_context=metatron)
    svc = spec["services"]["arda-authorizer"]
    assert svc["build"] == {"context": str(metatron), "dockerfile": "live_arda_fabric/Dockerfile.python-service"}
    assert svc["image"] == "beast-arda-guardian-authorizer:local"
    assert not any("/opt/arda" in v for v in svc["volumes"])  # code baked from the build context
    assert svc["working_dir"] == "/app"


def test_arda_compose_refuses_missing_or_writable_authorizer_source(tmp_path):
    with pytest.raises(FileNotFoundError, match="arda_authorization_service"):
        _provision_with_arda(tmp_path, arda_source=tmp_path / "nowhere")
    with pytest.raises(PermissionError, match="writable"):
        _provision_with_arda(tmp_path, sub="cfg2", arda_source=_arda_source(tmp_path / "w", mode=0o664))
    with pytest.raises(FileNotFoundError, match="Dockerfile"):
        _provision_with_arda(tmp_path, sub="cfg3", arda_build_context=tmp_path / "empty")


def test_provision_plan_reports_missing_sovereign_proof(tmp_path):
    from scripts import provision_guardian_validation as provision

    plan = provision.plan(tmp_path / "cfg", tmp_path / "state", proof=tmp_path / "missing.json")
    assert plan["sovereign_proof_exists"] is False


def test_provision_plan_only_writes_nothing(tmp_path):
    from scripts import provision_guardian_validation as provision

    plan = provision.plan(tmp_path / "cfg", tmp_path / "state")
    assert not (tmp_path / "cfg").exists() and not (tmp_path / "state").exists()
    assert any(item.endswith("guardian-receipt-ed25519.pem") for item in plan["would_create"])


# -- Task 2/D3.2: generated units consume the topology contract -------------------------------------------------
def test_units_generated_from_contract_with_install_instructions(tmp_path):
    from scripts.generate_socket_guardian_units import generate

    config, services, manifest, compose = _config(tmp_path)
    output = tmp_path / "units"
    paths = generate(services, config, output, ROOT, lab_manifest=manifest, compose_base=compose)
    names = {p.name for p in paths}
    assert {"beast-socket-guardian-beast.socket", "beast-socket-guardian-commons.socket",
            "beast-socket-guardian.service", "INSTALL.md"} <= names
    assert "beast-socket-guardian-seraph_ui.socket" not in names
    socket_unit = (output / "beast-socket-guardian-beast.socket").read_text()
    assert "ListenStream=127.0.0.1:8101" in socket_unit and "X-Beast-Topology-Digest=sha256:" in socket_unit
    service = (output / "beast-socket-guardian.service").read_text()
    assert str(ROOT / ".venv" / "bin" / "python") in service or sys.executable in service
    install = (output / "INSTALL.md").read_text()
    assert "systemctl --user daemon-reload" in install and "systemctl --user enable" in install
    assert "8101" in install  # warns that enabling the beast socket reserves the operator's port


def test_unit_generation_refuses_drift(tmp_path):
    from scripts.generate_socket_guardian_units import generate

    config, services, manifest, compose = _config(tmp_path, compose_ports=(8111, 8112, 8199))
    with pytest.raises(RuntimeError, match="topology drift"):
        generate(services, config, tmp_path / "units", ROOT, lab_manifest=manifest, compose_base=compose)
    assert not (tmp_path / "units").exists()


# -- Task 3: gateway listener refuses lease/topology mismatch --------------------------------------------------
class _Lease:
    def __init__(self, port, registry_digest="sha256:r"):
        self.lease_id, self.service_id, self.workspace_id = "lease-1", "beast", "workspace-1"
        self.policy_generation, self.appraisal_ref = "policy:7", "arda-appraisal:1"
        self.protocol, self.port, self.capability_ref = "TCP", port, "cap"
        self.registry_digest, self.listener_generation = registry_digest, 1


class _Client:
    def __init__(self, lease):
        self.lease, self.recovered = lease, False

    def snapshot(self):
        return [self.lease]

    def recover(self, *args, **kwargs):
        self.recovered = True
        raise AssertionError("must refuse before recover")


def test_recover_refuses_lease_port_outside_topology_contract():
    from app.kernel.execution.guardian_uvicorn import GuardianStartupError, recover_named_listener

    client = _Client(_Lease(9999))
    with pytest.raises(GuardianStartupError, match="topology contract"):
        recover_named_listener(client, service_id="beast", workspace_id="workspace-1", policy_generation="policy:7",
                               appraisal_ref="arda-appraisal:1", expected_port=8131)
    assert client.recovered is False


def test_recover_refuses_registry_digest_mismatch():
    from app.kernel.execution.guardian_uvicorn import GuardianStartupError, recover_named_listener

    client = _Client(_Lease(8131, registry_digest="sha256:old"))
    with pytest.raises(GuardianStartupError, match="registry digest"):
        recover_named_listener(client, service_id="beast", workspace_id="workspace-1", policy_generation="policy:7",
                               appraisal_ref="arda-appraisal:1", expected_port=8131,
                               expected_registry_digest="sha256:new")


def test_environment_topology_expectations(tmp_path):
    from app.kernel.execution.guardian_uvicorn import topology_expectations

    services, manifest, compose, _ = _sources(tmp_path)
    expected = topology_expectations("beast", {"BEAST_GUARDIAN_SERVICE_REGISTRY": str(services),
                                               "BEAST_GUARDIAN_LAB_MANIFEST": str(manifest),
                                               "BEAST_GUARDIAN_COMPOSE_BASE": str(compose)})
    assert expected["expected_port"] == 8101 and expected["expected_registry_digest"].startswith("sha256:")
    with pytest.raises(Exception, match="not a Guardian-owned service"):
        topology_expectations("seraph_ui", {"BEAST_GUARDIAN_SERVICE_REGISTRY": str(services),
                                            "BEAST_GUARDIAN_LAB_MANIFEST": str(manifest),
                                            "BEAST_GUARDIAN_COMPOSE_BASE": str(compose)})


# -- Task 4: Docker Commons signed custody records (D3.3) ------------------------------------------------------
def _attestor(tmp_path):
    from app.kernel.commons.docker_custody import DockerCustodyAttestor
    from app.kernel.networking.fabric_topology import FabricTopology

    services, manifest, compose, _ = _sources(tmp_path)
    topology = FabricTopology.load(services_path=services, lab_manifest_path=manifest, compose_base_path=compose)
    key = Ed25519PrivateKey.generate()
    return DockerCustodyAttestor(key, signer_id="guardian-receipt-v1", topology=topology), key


def _row(port=8111, age=10.0, status="healthy", now=1000.0):
    return {"node_id": "commons-node-a", "endpoint": f"http://127.0.0.1:{port}", "status": status,
            "checked_at": now - age, "descriptor_digest": "sha256:" + "d" * 64}


def test_custody_record_binds_port_container_and_fresh_descriptor(tmp_path):
    from app.kernel.commons.docker_custody import verify_custody_record

    attestor, key = _attestor(tmp_path)
    record = attestor.attest(_row(), container="compose:commons-node-a", now=1000.0)
    assert record["binding"] == "127.0.0.1:8111" and record["socket_owner"] == "docker"
    assert record["custody"] == "observe_and_attest" and record["authority"] == "verify_only"
    assert record["descriptor_digest"] == "sha256:" + "d" * 64
    assert verify_custody_record(record, key.public_key(), now=1001.0)["valid"] is True
    forged = {**record, "binding": "127.0.0.1:8112"}
    assert verify_custody_record(forged, key.public_key(), now=1001.0)["valid"] is False
    assert verify_custody_record(record, key.public_key(), now=record["expires_at"] + 1)["valid"] is False


@pytest.mark.parametrize("row, reason", [
    (_row(port=8199), "published_port_outside_topology_contract"),
    (_row(age=900.0), "descriptor_not_freshly_verified"),
    (_row(status="refused"), "descriptor_not_freshly_verified"),
    ({**_row(), "descriptor_digest": ""}, "descriptor_not_freshly_verified"),
])
def test_custody_refused_without_contract_port_or_fresh_descriptor(tmp_path, row, reason):
    from app.kernel.commons.docker_custody import CustodyRefused

    attestor, _ = _attestor(tmp_path)
    with pytest.raises(CustodyRefused, match=reason):
        attestor.attest(row, container="compose:commons-node-a", now=1000.0)


def test_gateway_health_carries_custody_per_node(tmp_path):
    import asyncio

    from app.kernel.commons.remote_client import RemoteCommonsGateway

    attestor, _ = _attestor(tmp_path)

    class Registry:
        def list(self):
            return [{"node_id": "commons-node-a", "endpoint": "http://127.0.0.1:8111", "trust_policy": "pinned",
                     "state": "authenticated_unattested",
                     "last_probe": {"checked_at": time.time() - 5, "admission_valid_until": time.time() + 600,
                                    "descriptor_digest": "sha256:" + "d" * 64}},
                    {"node_id": "commons-node-b", "endpoint": "http://127.0.0.1:8112", "trust_policy": "pinned",
                     "state": "refused", "last_probe": {}}]

    gateway = RemoteCommonsGateway(Registry(), gate=None, custody=attestor)
    health = asyncio.run(gateway.health())
    a, b = health["nodes"]
    assert a["custody"]["binding"] == "127.0.0.1:8111" and a["custody"]["signature"]
    assert b["custody"] == {"status": "refused", "reason": "descriptor_not_freshly_verified"}
    assert health["custody_model"] == "signed_custody_records_only"


def test_custody_attestor_is_default_off_and_requires_private_key(tmp_path):
    from app.kernel.commons.docker_custody import attestor_from_environment

    assert attestor_from_environment({}) is None
    _key, key_path, _ = _keys(tmp_path)
    services, manifest, compose, _ = _sources(tmp_path)
    env = {"BEAST_COMMONS_CUSTODY_SIGNING_KEY": str(key_path), "BEAST_GUARDIAN_SERVICE_REGISTRY": str(services),
           "BEAST_GUARDIAN_LAB_MANIFEST": str(manifest), "BEAST_GUARDIAN_COMPOSE_BASE": str(compose)}
    assert attestor_from_environment(env).signer_id
    key_path.chmod(0o644)
    with pytest.raises(PermissionError):
        attestor_from_environment(env)
