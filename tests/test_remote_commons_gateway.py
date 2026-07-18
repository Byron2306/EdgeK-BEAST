import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import httpx
import pytest

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


CAPABILITIES = ["bucket_registry", "immutable_blobs", "signed_revisions", "replay_resistant_requests"]


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
