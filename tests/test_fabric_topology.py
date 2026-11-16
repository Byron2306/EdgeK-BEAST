import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.kernel.networking.fabric_topology import FabricTopology, TopologyDriftError

ROOT = Path(__file__).resolve().parents[1]


def _sources(tmp_path, *, node_ports=(8111, 8112, 8113), compose_ports=(8111, 8112, 8113),
             beast_port=8101, override_ports=None):
    services = tmp_path / "services.yaml"
    services.write_text(
        "version: 1\nservices:\n"
        "  reverse_proxy:\n    port: 80\n"
        f"  beast:\n    hostname: beast.test\n    upstream: 127.0.0.1:{beast_port}\n    port: {beast_port}\n"
        "    health_path: /health\n    trust_domain: operator\n    socket_guardian: true\n"
        "  commons:\n    hostname: commons.test\n    upstream: 127.0.0.1:8601\n    port: 8601\n"
        "    health_path: /edgek/control-plane/commons\n    trust_domain: commons\n    socket_guardian: true\n"
        "  seraph_ui:\n    hostname: seraph.test\n    upstream: 127.0.0.1:3000\n    port: 3000\n"
        "    health_path: /\n    trust_domain: operator\n    socket_guardian: false\n",
        encoding="utf-8",
    )
    names = ("commons-node-a", "commons-node-b", "commons-node-c")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "beast_object_type": "remote_commons_lab_provisioning",
        "version": "1.0",
        "nodes": [{"node_id": n, "port": p, "public_key": "pub-" + n} for n, p in zip(names, node_ports)],
    }), encoding="utf-8")
    compose = tmp_path / "docker-compose.commons-lab.yml"
    compose.write_text("services:\n" + "".join(
        f"  {n}:\n    build:\n      context: .\n    ports:\n      - \"127.0.0.1:{p}:8000\"\n"
        for n, p in zip(names, compose_ports)
    ), encoding="utf-8")
    override = None
    if override_ports is not None:
        override = tmp_path / "docker-compose.ports.yml"
        override.write_text("services:\n" + "".join(
            f"  {n}:\n    ports: !override\n      - \"127.0.0.1:{p}:8000\"\n"
            for n, p in zip(names, override_ports)
        ), encoding="utf-8")
    return services, manifest, compose, override


def _load(paths):
    services, manifest, compose, override = paths
    return FabricTopology.load(
        services_path=services, lab_manifest_path=manifest,
        compose_base_path=compose, compose_override_path=override,
    )


def test_consistent_sources_have_no_drift_and_stable_digest(tmp_path):
    topology = _load(_sources(tmp_path))
    endpoints = {f"commons-node-{x}": f"http://127.0.0.1:{p}" for x, p in zip("abc", (8111, 8112, 8113))}
    assert topology.drift(registry_endpoints=endpoints) == []
    topology.require_consistent(registry_endpoints=endpoints)
    assert topology.topology_digest.startswith("sha256:")
    assert topology.topology_digest == _load(_sources(tmp_path)).topology_digest


def test_manifest_and_compose_port_mismatch_is_drift(tmp_path):
    topology = _load(_sources(tmp_path, node_ports=(8121, 8122, 8123)))
    findings = topology.drift()
    assert {f["kind"] for f in findings} == {"compose_port_mismatch"}
    assert {f["subject"] for f in findings} == {"commons-node-a", "commons-node-b", "commons-node-c"}
    first = next(f for f in findings if f["subject"] == "commons-node-a")
    assert first["expected"] == 8121 and first["observed"] == [8111]
    with pytest.raises(TopologyDriftError):
        topology.require_consistent()


def test_compose_override_takes_precedence_over_base_ports(tmp_path):
    paths = _sources(tmp_path, node_ports=(8121, 8122, 8123), override_ports=(8121, 8122, 8123))
    assert _load(paths).drift() == []


def test_registry_endpoint_mismatch_is_drift(tmp_path):
    topology = _load(_sources(tmp_path))
    findings = topology.drift(registry_endpoints={
        "commons-node-a": "http://127.0.0.1:8121",
        "commons-node-b": "http://127.0.0.1:8112",
        "commons-node-c": "http://127.0.0.1:8113",
        "commons-node-z": "http://127.0.0.1:8199",
    })
    kinds = {(f["kind"], f["subject"]) for f in findings}
    assert kinds == {
        ("registry_endpoint_mismatch", "commons-node-a"),
        ("registry_unknown_node", "commons-node-z"),
    }


def test_guardian_service_and_commons_node_port_collision_fails_closed(tmp_path):
    topology = _load(_sources(tmp_path, beast_port=8111))
    findings = topology.drift()
    assert any(f["kind"] == "port_collision" and f["observed"] == 8111 for f in findings)
    with pytest.raises(TopologyDriftError):
        topology.guardian_bindings()


def test_guardian_bindings_cover_only_opted_in_loopback_services(tmp_path):
    topology = _load(_sources(tmp_path))
    bindings = topology.guardian_bindings()
    assert set(bindings["services"]) == {"beast", "commons"}
    assert bindings["services"]["beast"] == {
        "upstream": "127.0.0.1:8101", "port": 8101, "trust_domain": "operator", "protocol": "TCP",
    }
    assert bindings["topology_digest"] == topology.topology_digest
    assert bindings["registry_digest"].startswith("sha256:")
    assert "public_key" not in json.dumps(bindings)


def test_cli_exit_contract(tmp_path):
    script = ROOT / "scripts" / "check_fabric_topology.py"
    good_root = tmp_path / "good"
    good_root.mkdir()
    good = _sources(good_root)
    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    bad = _sources(bad_root, node_ports=(8121, 8122, 8123))

    def run(paths):
        services, manifest, compose, _ = paths
        return subprocess.run(
            [sys.executable, str(script), "--services", str(services), "--manifest", str(manifest),
             "--compose", str(compose)],
            capture_output=True, text=True, cwd=ROOT,
        )

    ok, drifted = run(good), run(bad)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["consistent"] is True
    assert drifted.returncode == 1
    report = json.loads(drifted.stdout)
    assert report["consistent"] is False and len(report["findings"]) == 3
