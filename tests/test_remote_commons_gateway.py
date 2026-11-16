import base64
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.kernel.commons.discovery import CommonsDiscoveryCatalog
from app.kernel.commons.remote_client import CommonsEgressGate, RemoteCommonsGateway, RemoteCommonsRegistry
from app.kernel.commons.remote_protocol import (
    CommonsClientTrustStore,
    CommonsRequestSigner,
    CommonsRequestVerifier,
    SqliteReplayLedger,
    TrustedClient,
    canonical_json,
    sha256_bytes,
)
from app.kernel.integration.signed_decision import signed_appraisal_body
from app.routes.commons_remote import build_remote_commons_router

CAPABILITIES = ["bucket_registry", "immutable_blobs", "signed_revisions", "replay_resistant_requests"]


def _raw_public_key() -> str:
    key = Ed25519PrivateKey.generate()
    return base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")


def _signed_node_document(
    key: Ed25519PrivateKey, *, node_id: str, workload: str
) -> dict:
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    subject = {
        "node_id": node_id,
        "workload_digest": workload,
        "node_public_key": public,
        "protocol": "beast-commons-http-signature-v1",
        "capabilities": CAPABILITIES,
        "maximum_authority": "verify_only",
    }
    descriptor = {
        "beast_object_type": "remote_commons_node_descriptor",
        "schema_version": "1.0",
        **subject,
        "attestation_subject_digest": sha256_bytes(canonical_json(subject)),
        "arda_appraisal": {},
        "storage": {"buckets": 0},
    }
    return {
        "descriptor": descriptor,
        "descriptor_digest": sha256_bytes(canonical_json(descriptor)),
        "node_signature": base64.b64encode(key.sign(canonical_json(descriptor))).decode("ascii"),
    }


def _observe_origin(catalog, origin, *, node_id="node-a", subject="subject-a", source="manual"):
    return catalog.observe(
        candidate_id=f"{source}/{origin}/{node_id}/{subject}",
        source=source,
        origin=origin,
        node_id=node_id,
        subject_digest=subject,
        state="trusted_candidate",
        trust={"verified": True},
        document={},
    )


def test_discovery_supersession_keeps_history_and_does_not_revive_old_origins(tmp_path):
    path = tmp_path / "discovery.sqlite3"
    catalog = CommonsDiscoveryCatalog(path)
    old, current = "http://127.0.0.1:8121", "http://127.0.0.1:8111"
    _observe_origin(catalog, old)
    _observe_origin(catalog, old, source="registry")
    _observe_origin(catalog, current)
    _observe_origin(catalog, old, node_id="node-b")
    _observe_origin(catalog, old, subject="subject-b", source="static_seed")

    assert catalog.supersede_origins("node-a", current, "subject-a") == 2
    assert catalog.supersede_origins("node-a", current, "subject-a") == 0
    catalog = CommonsDiscoveryCatalog(path)
    assert _observe_origin(catalog, old)["state"] == "superseded_candidate"
    assert _observe_origin(catalog, old, source="well_known")["state"] == "superseded_candidate"
    snapshot = catalog.snapshot()
    assert snapshot["candidate_count"] == 6
    assert snapshot["trusted_candidate_count"] == 3
    for row in snapshot["candidates"]:
        superseded = (
            row["node_id"] == "node-a" and row["subject_digest"] == "subject-a"
            and row["origin"] == old
        )
        assert row["state"] == ("superseded_candidate" if superseded else "trusted_candidate")

    assert catalog.supersede_origins("node-a", old, "subject-a") == 1
    assert catalog.find(source="manual", origin=old, node_id="node-a")["state"] == "trusted_candidate"
    assert catalog.find(source="manual", origin=current, node_id="node-a")["state"] == "superseded_candidate"


@pytest.mark.asyncio
@pytest.mark.parametrize("accept", [False, True])
async def test_gateway_reconcile_discovery_supersession_follows_admission(tmp_path, monkeypatch, accept):
    catalog = CommonsDiscoveryCatalog(tmp_path / "discovery.sqlite3")
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
        discovery_catalog=catalog,
    )
    key = Ed25519PrivateKey.generate()
    old, current = "http://127.0.0.1:8121", "http://127.0.0.1:8111"
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    workload = "sha256:" + "a" * 64
    gateway.register(node_id="node-a", endpoint=old, node_public_key=public,
                     expected_workload_digest=workload, trust_policy="pinned")
    document = _signed_node_document(key, node_id="node-a", workload=workload)
    subject = document["descriptor"]["attestation_subject_digest"]
    _observe_origin(catalog, old, subject=subject)
    if not accept:
        document = _signed_node_document(key, node_id="node-a", workload="sha256:" + "d" * 64)

    async def candidate_request(*_args, **_kwargs):
        return httpx.Response(200, json=document, request=httpx.Request("GET", current + "/v1/node"))

    original_supersede = getattr(catalog, "supersede_origins", None)

    if original_supersede is not None:
        def assert_committed(node_id, admitted_origin, subject_digest):
            assert accept
            assert registry.get(node_id)["endpoint"] == admitted_origin
            return original_supersede(node_id, admitted_origin, subject_digest)

        monkeypatch.setattr(catalog, "supersede_origins", assert_committed)
    monkeypatch.setattr(gateway, "_request", candidate_request)
    receipt = await gateway.reconcile_endpoint("node-a", current)

    assert receipt["status"] == ("reconciled" if accept else "refused")
    assert registry.get("node-a")["endpoint"] == (current if accept else old)
    assert catalog.find(source="manual", origin=old, node_id="node-a")["state"] == (
        "superseded_candidate" if accept else "trusted_candidate"
    )
    if accept:
        assert receipt["discovery_supersession"] == {"status": "updated", "count": 1}
    else:
        assert "discovery_supersession" not in receipt


@pytest.mark.asyncio
async def test_gateway_reconcile_discovery_supersession_can_retry_catalog_failure(tmp_path, monkeypatch):
    catalog = CommonsDiscoveryCatalog(tmp_path / "discovery.sqlite3")
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
        discovery_catalog=catalog,
    )
    key = Ed25519PrivateKey.generate()
    old, current = "http://127.0.0.1:8121", "http://127.0.0.1:8111"
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    workload = "sha256:" + "a" * 64
    gateway.register(node_id="node-a", endpoint=old, node_public_key=public,
                     expected_workload_digest=workload, trust_policy="pinned")
    document = _signed_node_document(key, node_id="node-a", workload=workload)
    subject = document["descriptor"]["attestation_subject_digest"]
    _observe_origin(catalog, old, subject=subject)

    async def candidate_request(*_args, **_kwargs):
        return httpx.Response(200, json=document, request=httpx.Request("GET", current + "/v1/node"))

    def unavailable(*_args):
        raise sqlite3.OperationalError("catalog unavailable")

    monkeypatch.setattr(gateway, "_request", candidate_request)
    with monkeypatch.context() as scoped:
        scoped.setattr(catalog, "supersede_origins", unavailable)
        receipt = await gateway.reconcile_endpoint("node-a", current)

    assert receipt["status"] == "reconciled"
    assert receipt["discovery_supersession"] == {"status": "retry_required"}
    assert registry.get("node-a")["endpoint"] == current
    assert catalog.find(source="manual", origin=old, node_id="node-a")["state"] == "trusted_candidate"
    retry = await gateway.reconcile_endpoint("node-a", current)
    assert retry["changed"] is False
    assert retry["discovery_supersession"] == {"status": "updated", "count": 1}
    assert catalog.find(source="manual", origin=old, node_id="node-a")["state"] == "superseded_candidate"


def test_registry_reconcile_endpoint_is_atomic_and_preserves_identity(tmp_path):
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    public = _raw_public_key()
    workload = "sha256:" + "a" * 64
    registry.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8121",
        node_public_key=public,
        expected_workload_digest=workload,
        trust_policy="lattice",
    )

    result = {
        "ok": True,
        "state": "lattice_attested",
        "checked_at": 123.0,
        "descriptor_digest": "sha256:" + "b" * 64,
    }
    updated = registry.reconcile_endpoint(
        "node-a", "http://127.0.0.1:8111", result
    )

    assert updated["endpoint"] == "http://127.0.0.1:8111"
    assert updated["node_public_key"] == public
    assert updated["expected_workload_digest"] == workload
    assert updated["trust_policy"] == "lattice"
    assert updated["state"] == "lattice_attested"
    assert updated["last_probe"] == result
    assert updated["endpoint_history"][-1] == {
        "previous_endpoint": "http://127.0.0.1:8121",
        "candidate_endpoint": "http://127.0.0.1:8111",
        "changed": True,
        "state": "lattice_attested",
        "descriptor_digest": "sha256:" + "b" * 64,
        "recorded_at": updated["endpoint_history"][-1]["recorded_at"],
    }

    repeated = registry.reconcile_endpoint(
        "node-a", "http://127.0.0.1:8111", {**result, "checked_at": 124.0}
    )
    assert repeated["endpoint"] == "http://127.0.0.1:8111"
    assert repeated["last_probe"]["checked_at"] == 124.0
    assert repeated["endpoint_history"][-1]["changed"] is False


def test_registry_reconcile_endpoint_rolls_back_on_endpoint_conflict(tmp_path):
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    registry.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8121",
        node_public_key=_raw_public_key(),
    )
    registry.register(
        node_id="node-b",
        endpoint="http://127.0.0.1:8111",
        node_public_key=_raw_public_key(),
    )

    with pytest.raises(ValueError, match="already registered"):
        registry.reconcile_endpoint(
            "node-a",
            "http://127.0.0.1:8111",
            {"ok": True, "state": "authenticated_unattested", "checked_at": 123.0},
        )

    unchanged = registry.get("node-a")
    assert unchanged["endpoint"] == "http://127.0.0.1:8121"
    assert unchanged["state"] == "unprobed"
    assert unchanged["last_probe"] == {}
    assert unchanged["endpoint_history"] == []


@pytest.mark.asyncio
async def test_gateway_reconcile_verifies_candidate_before_atomic_update(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    workload = "sha256:" + "c" * 64
    gateway = RemoteCommonsGateway(
        RemoteCommonsRegistry(tmp_path / "nodes.sqlite3"),
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )
    gateway.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8121",
        node_public_key=public,
        expected_workload_digest=workload,
        trust_policy="pinned",
    )
    document = _signed_node_document(key, node_id="node-a", workload=workload)

    async def candidate_request(node, method, target, **kwargs):
        assert node["endpoint"] == "http://127.0.0.1:8111"
        assert method == "GET"
        assert target == "/v1/node"
        assert kwargs["authenticate"] is False
        return httpx.Response(
            200,
            json=document,
            request=httpx.Request("GET", "http://127.0.0.1:8111/v1/node"),
        )

    monkeypatch.setattr(gateway, "_request", candidate_request)
    receipt = await gateway.reconcile_endpoint("node-a", "http://127.0.0.1:8111")

    assert receipt["status"] == "reconciled"
    assert receipt["previous_endpoint"] == "http://127.0.0.1:8121"
    assert receipt["candidate_endpoint"] == "http://127.0.0.1:8111"
    assert receipt["identity_verified"] is True
    assert gateway.registry.get("node-a")["endpoint"] == "http://127.0.0.1:8111"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["wrong_node", "wrong_workload", "malformed"])
async def test_gateway_reconcile_refuses_invalid_identity_without_changing_admission(
    tmp_path, monkeypatch, invalid_kind
):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    workload = "sha256:" + "d" * 64
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )
    gateway.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8121",
        node_public_key=public,
        expected_workload_digest=workload,
        trust_policy="pinned",
    )
    registry.record_probe(
        "node-a",
        state="authenticated_unattested",
        result={"ok": True, "state": "authenticated_unattested", "checked_at": 100.0},
    )
    if invalid_kind == "wrong_node":
        document = _signed_node_document(key, node_id="node-b", workload=workload)
    elif invalid_kind == "wrong_workload":
        document = _signed_node_document(key, node_id="node-a", workload="sha256:" + "e" * 64)
    else:
        document = {"descriptor": {"node_id": "node-a"}}

    async def candidate_request(*_args, **_kwargs):
        return httpx.Response(
            200,
            json=document,
            request=httpx.Request("GET", "http://127.0.0.1:8111/v1/node"),
        )

    monkeypatch.setattr(gateway, "_request", candidate_request)
    receipt = await gateway.reconcile_endpoint("node-a", "http://127.0.0.1:8111")

    assert receipt["status"] == "refused"
    unchanged = registry.get("node-a")
    assert unchanged["endpoint"] == "http://127.0.0.1:8121"
    assert unchanged["state"] == "authenticated_unattested"
    assert unchanged["last_probe"]["checked_at"] == 100.0
    assert unchanged["endpoint_history"][-1]["candidate_endpoint"] == "http://127.0.0.1:8111"
    assert unchanged["endpoint_history"][-1]["state"] == "refused"
    assert unchanged["endpoint_history"][-1]["changed"] is False


@pytest.mark.asyncio
async def test_gateway_reconcile_refuses_unreachable_or_disallowed_candidate(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )
    gateway.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8121",
        node_public_key=public,
        trust_policy="pinned",
    )

    async def unavailable(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(gateway, "_request", unavailable)
    unreachable = await gateway.reconcile_endpoint("node-a", "http://127.0.0.1:8111")
    disallowed = await gateway.reconcile_endpoint("node-a", "http://commons.invalid:8111")

    assert unreachable["status"] == "refused"
    assert disallowed["status"] == "refused"
    assert registry.get("node-a")["endpoint"] == "http://127.0.0.1:8121"


def test_reconcile_route_is_local_operator_only():
    class Gateway:
        async def reconcile_endpoint(self, node_id, candidate_endpoint):
            return {
                "status": "reconciled",
                "node_id": node_id,
                "candidate_endpoint": candidate_endpoint,
            }

    app = FastAPI()
    app.include_router(build_remote_commons_router(Gateway()))
    target = "/edgek/control-plane/commons/remote/nodes/node-a/reconcile"
    with TestClient(app, client=("127.0.0.1", 50000)) as local:
        accepted = local.post(target, json={"candidate_endpoint": "http://127.0.0.1:8111"})
        invalid = local.post(target, json={})
    with TestClient(app, client=("203.0.113.10", 50000)) as remote:
        refused = remote.post(target, json={"candidate_endpoint": "http://127.0.0.1:8111"})

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "reconciled"
    assert invalid.status_code == 422
    assert refused.status_code == 403


def test_remote_commons_topology_contract_generates_compose_ports_from_manifest(tmp_path):
    root = tmp_path / "lab"
    script = Path(__file__).resolve().parents[1] / "scripts" / "provision_remote_commons_lab.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--nodes", "3", "--base-port", "8111"],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads(completed.stdout)
    override_path = Path(manifest["topology"]["compose_override"])
    compose_base = Path(manifest["topology"]["compose_base"])
    rendered = subprocess.run(
        [
            "docker", "compose", "-f", str(compose_base), "-f", str(override_path),
            "config", "--format", "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    compose = json.loads(rendered.stdout)

    assert [node["port"] for node in manifest["nodes"]] == [8111, 8112, 8113]
    assert override_path == root / "docker-compose.ports.yml"
    assert {
        name: [entry["published"] for entry in service["ports"]]
        for name, service in compose["services"].items()
    } == {
        "commons-node-a": ["8111"],
        "commons-node-b": ["8112"],
        "commons-node-c": ["8113"],
    }


def test_remote_commons_base_compose_keeps_standalone_lab_reachable():
    compose_base = Path(__file__).resolve().parents[1] / "docker-compose.commons-lab.yml"
    rendered = subprocess.run(
        ["docker", "compose", "-f", str(compose_base), "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    compose = json.loads(rendered.stdout)
    assert {
        name: [entry["published"] for entry in service["ports"]]
        for name, service in compose["services"].items()
    } == {
        "commons-node-a": ["8111"],
        "commons-node-b": ["8112"],
        "commons-node-c": ["8113"],
    }


def test_remote_route_registration_is_unique():
    from app.main import app

    remote_routes = [
        (str(getattr(route, "path", "")), method)
        for route in app.routes
        if str(getattr(route, "path", "")).startswith("/edgek/control-plane/commons/remote")
        for method in (getattr(route, "methods", None) or set())
    ]
    assert len(remote_routes) == len(set(remote_routes))


@pytest.mark.asyncio
async def test_remote_commons_fabric_health_classifies_fresh_stale_expired_and_refused(tmp_path):
    now = time.time()
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    for suffix, state, checked_at, valid_until in (
        ("fresh", "authenticated_unattested", now, now + 120),
        ("stale", "authenticated_unattested", now - 301, now + 120),
        ("expired", "authenticated_unattested", now, now - 1),
        ("refused", "refused", now, now + 120),
    ):
        registry.register(
            node_id=f"node-{suffix}",
            endpoint=f"http://127.0.0.1:{8200 + len(registry.list())}",
            node_public_key=_raw_public_key(),
            trust_policy="pinned",
        )
        registry.record_probe(
            f"node-{suffix}",
            state=state,
            result={
                "ok": state != "refused",
                "state": state,
                "checked_at": checked_at,
                "admission_valid_until": valid_until,
                "workload_digest": "sha256:" + "a" * 64,
            },
        )
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )

    health = await gateway.health(now=now)
    statuses = {node["node_id"]: node["status"] for node in health["nodes"]}
    assert health["status"] == "degraded"
    assert health["healthy_count"] == 1
    assert statuses == {
        "node-expired": "trust_expired",
        "node-fresh": "healthy",
        "node-refused": "refused",
        "node-stale": "stale",
    }


@pytest.mark.asyncio
async def test_remote_commons_health_refresh_failure_preserves_last_admission(tmp_path, monkeypatch):
    now = time.time()
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )
    gateway.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8111",
        node_public_key=_raw_public_key(),
        trust_policy="pinned",
    )
    admitted = {
        "ok": True,
        "state": "authenticated_unattested",
        "checked_at": now,
        "admission_valid_until": now + 120,
    }
    registry.record_probe("node-a", state="authenticated_unattested", result=admitted)

    async def unavailable(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(gateway, "_request", unavailable)
    health = await gateway.health(refresh=True, now=now)

    assert health["status"] == "degraded"
    assert health["nodes"][0]["status"] == "probe_failed"
    assert registry.get("node-a")["state"] == "authenticated_unattested"
    assert registry.get("node-a")["last_probe"] == admitted


@pytest.mark.asyncio
async def test_remote_commons_health_refresh_all_healthy_then_partial_network_failure(tmp_path, monkeypatch):
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )
    workload = "sha256:" + "a" * 64
    documents = {}
    for index, node_id in enumerate(("node-a", "node-b", "node-c")):
        key = Ed25519PrivateKey.generate()
        endpoint = f"http://127.0.0.1:{8111 + index}"
        gateway.register(
            node_id=node_id,
            endpoint=endpoint,
            node_public_key=base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii"),
            expected_workload_digest=workload,
            trust_policy="pinned",
        )
        documents[endpoint] = _signed_node_document(key, node_id=node_id, workload=workload)
    offline: set[str] = set()

    async def fake_request(node, *_args, **_kwargs):
        endpoint = str(node["endpoint"])
        if endpoint in offline:
            raise httpx.ConnectError("offline")
        return httpx.Response(
            200, json=documents[endpoint], request=httpx.Request("GET", endpoint + "/v1/node")
        )

    monkeypatch.setattr(gateway, "_request", fake_request)
    healthy = await gateway.health(refresh=True)
    assert healthy["status"] == "healthy"
    assert healthy["authority"] == "verify_only"
    assert healthy["healthy_count"] == healthy["node_count"] == 3
    assert all(row["descriptor_digest"] for row in healthy["nodes"])
    admitted_b = registry.get("node-b")

    offline.add("http://127.0.0.1:8112")
    partial = await gateway.health(refresh=True)
    statuses = {row["node_id"]: row["status"] for row in partial["nodes"]}
    assert partial["status"] == "degraded"
    assert partial["healthy_count"] == 2
    assert statuses == {"node-a": "healthy", "node-b": "probe_failed", "node-c": "healthy"}
    assert registry.get("node-b")["endpoint"] == admitted_b["endpoint"]
    assert registry.get("node-b")["state"] == admitted_b["state"]
    assert registry.get("node-b")["last_probe"] == admitted_b["last_probe"]


@pytest.mark.asyncio
async def test_remote_commons_health_refresh_refuses_wrong_node_signature_without_erasing_admission(
    tmp_path, monkeypatch
):
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
    )
    workload = "sha256:" + "a" * 64
    key = Ed25519PrivateKey.generate()
    gateway.register(
        node_id="node-a",
        endpoint="http://127.0.0.1:8111",
        node_public_key=base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii"),
        expected_workload_digest=workload,
        trust_policy="pinned",
    )
    document = _signed_node_document(key, node_id="node-a", workload=workload)

    async def fake_request(*_args, **_kwargs):
        return httpx.Response(
            200, json=document, request=httpx.Request("GET", "http://127.0.0.1:8111/v1/node")
        )

    monkeypatch.setattr(gateway, "_request", fake_request)
    assert (await gateway.health(refresh=True))["status"] == "healthy"
    admitted = registry.get("node-a")

    document = _signed_node_document(key, node_id="node-b", workload=workload)
    refused = await gateway.health(refresh=True)
    assert refused["status"] == "degraded"
    assert refused["nodes"][0]["status"] == "probe_failed"
    assert registry.get("node-a")["last_probe"] == admitted["last_probe"]
    assert registry.get("node-a")["endpoint"] == admitted["endpoint"]


def test_remote_commons_health_refresh_route_is_local_operator_only():
    class Gateway:
        async def health(self, refresh=False):
            return {"status": "healthy", "refresh": refresh}

    app = FastAPI()
    app.include_router(build_remote_commons_router(Gateway()))
    target = "/edgek/control-plane/commons/remote/health"
    with TestClient(app, client=("127.0.0.1", 50000)) as local:
        snapshot = local.get(target)
        refreshed = local.post(target)
    with TestClient(app, client=("203.0.113.10", 50000)) as remote:
        refused = remote.post(target)

    assert snapshot.json() == {"status": "healthy", "refresh": False}
    assert refreshed.json() == {"status": "healthy", "refresh": True}
    assert refused.status_code == 403


def test_gate_of_night_only_allows_https_or_explicit_loopback():
    gate = CommonsEgressGate(allowed_hosts=("commons.example.org", "127.0.0.1"), allow_insecure_loopback=True)
    assert gate.validate_base_url("https://commons.example.org") == "https://commons.example.org"
    assert gate.validate_base_url("http://127.0.0.1:8101") == "http://127.0.0.1:8101"
    with pytest.raises(PermissionError):
        gate.validate_base_url("http://commons.example.org")
    with pytest.raises(PermissionError):
        gate.validate_base_url("http://169.254.169.254")
    with pytest.raises(ValueError):
        gate.validate_base_url("https://commons.example.org/admin")


def test_replay_ledger_allows_bounded_network_reordering_but_not_replay(tmp_path):
    key = Ed25519PrivateKey.generate()
    signer = CommonsRequestSigner(key, node_id="beast", key_id="key-1")
    verifier = CommonsRequestVerifier(
        CommonsClientTrustStore([
            TrustedClient("beast", "key-1", key.public_key(), frozenset({"bucket:write"}))
        ]),
        SqliteReplayLedger(tmp_path / "replay.sqlite3"),
    )
    first = signer.headers(method="POST", target="/one", body=b"one")
    second = signer.headers(method="POST", target="/two", body=b"two")
    assert verifier.verify(method="POST", target="/two", body=b"two", headers=second, required_scope="bucket:write")
    assert verifier.verify(method="POST", target="/one", body=b"one", headers=first, required_scope="bucket:write")
    with pytest.raises(PermissionError, match="replay"):
        verifier.verify(method="POST", target="/one", body=b"one", headers=first, required_scope="bucket:write")


@pytest.mark.asyncio
async def test_gateway_probes_pinned_node_signature_before_admission(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    registry = RemoteCommonsRegistry(tmp_path / "nodes.sqlite3")
    gateway = RemoteCommonsGateway(
        registry,
        CommonsEgressGate(allowed_hosts=("commons.example.org",)),
    )
    gateway.register(
        node_id="node-a", endpoint="https://commons.example.org", node_public_key=public,
        expected_workload_digest="sha256:" + "c" * 64, require_arda=False,
        expected_policy_generation="",
    )
    subject = {
        "node_id": "node-a",
        "workload_digest": "sha256:" + "c" * 64,
        "node_public_key": public,
        "protocol": "beast-commons-http-signature-v1",
        "capabilities": CAPABILITIES,
        "maximum_authority": "verify_only",
    }
    descriptor = {
        "beast_object_type": "remote_commons_node_descriptor",
        "schema_version": "1.0",
        **subject,
        "attestation_subject_digest": sha256_bytes(canonical_json(subject)),
        "arda_appraisal": {},
        "storage": {"buckets": 0},
    }
    document = {
        "descriptor": descriptor,
        "descriptor_digest": sha256_bytes(canonical_json(descriptor)),
        "node_signature": base64.b64encode(key.sign(canonical_json(descriptor))).decode("ascii"),
    }

    async def fake_request(*_args, **_kwargs):
        return httpx.Response(200, json=document, request=httpx.Request("GET", "https://commons.example.org/v1/node"))

    monkeypatch.setattr(gateway, "_request", fake_request)
    result = await gateway.probe("node-a")
    assert result["ok"] is True
    assert result["state"] == "authenticated_unattested"
    assert registry.get("node-a")["state"] == "authenticated_unattested"

    document["descriptor"] = {**descriptor, "workload_digest": "sha256:" + "d" * 64}
    rejected = await gateway.probe("node-a")
    assert rejected["ok"] is False
    assert registry.get("node-a")["state"] == "refused"


@pytest.mark.asyncio
async def test_gateway_requires_signed_arda_appraisal_over_exact_node_subject(tmp_path, monkeypatch):
    node_key = Ed25519PrivateKey.generate()
    arda_key = Ed25519PrivateKey.generate()
    public = base64.b64encode(node_key.public_key().public_bytes_raw()).decode("ascii")
    subject = {
        "node_id": "node-attested",
        "workload_digest": "sha256:" + "e" * 64,
        "node_public_key": public,
        "protocol": "beast-commons-http-signature-v1",
        "capabilities": CAPABILITIES,
        "maximum_authority": "verify_only",
    }
    subject_digest = sha256_bytes(canonical_json(subject))
    appraisal = {
        "appraisal_ref": "arda:commons-node:1",
        "authority": "arda",
        "audience": "beast-commons-node",
        "policy_generation": "policy-remote-1",
        "state": "verified",
        "expires_at": 9_999_999_999,
        "request_digest": subject_digest,
        "nonce": "nonce-remote-1",
        "key_id": "arda-key-1",
        "evidence_digest": "sha256:" + "f" * 64,
    }
    appraisal["signature"] = base64.b64encode(arda_key.sign(signed_appraisal_body(appraisal))).decode("ascii")
    descriptor = {
        "beast_object_type": "remote_commons_node_descriptor",
        "schema_version": "1.0",
        **subject,
        "attestation_subject_digest": subject_digest,
        "arda_appraisal": appraisal,
        "storage": {},
    }
    document = {
        "descriptor": descriptor,
        "descriptor_digest": sha256_bytes(canonical_json(descriptor)),
        "node_signature": base64.b64encode(node_key.sign(canonical_json(descriptor))).decode("ascii"),
    }
    gateway = RemoteCommonsGateway(
        RemoteCommonsRegistry(tmp_path / "nodes.sqlite3"),
        CommonsEgressGate(allowed_hosts=("commons.example.org",)),
        arda_public_key=arda_key.public_key(),
    )
    gateway.register(
        node_id="node-attested", endpoint="https://commons.example.org", node_public_key=public,
        expected_workload_digest=subject["workload_digest"], require_arda=True,
        expected_policy_generation="policy-remote-1",
    )

    async def fake_request(*_args, **_kwargs):
        return httpx.Response(200, json=document, request=httpx.Request("GET", "https://commons.example.org/v1/node"))

    monkeypatch.setattr(gateway, "_request", fake_request)
    result = await gateway.probe("node-attested")
    assert result["state"] == "hardware_attested"
    assert result["arda_appraisal_verified"] is True
