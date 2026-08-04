import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient
import pytest

from app.commons_node_main import RemoteCommonsNodeConfig, build_remote_commons_app
from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.remote_protocol import (
    CommonsClientTrustStore,
    CommonsRequestSigner,
    TrustedClient,
    canonical_json,
    sha256_bytes,
)
from app.kernel.commons.ml_kem import (
    challenge_confirmation_body,
    confirmation_mac,
    encapsulate,
)


def _signed(signer, method, target, body=b""):
    return signer.headers(method=method, target=target, body=body)


@pytest.mark.asyncio
async def test_remote_commons_bucket_blob_revision_and_signed_receipt(tmp_path):
    node_key = Ed25519PrivateKey.generate()
    client_key = Ed25519PrivateKey.generate()
    signer = CommonsRequestSigner(client_key, node_id="beast-control-plane", key_id="client-v1")
    trust = CommonsClientTrustStore([
        TrustedClient(
            "beast-control-plane",
            "client-v1",
            client_key.public_key(),
            frozenset({"bucket:read", "bucket:write", "blob:write"}),
        )
    ])
    app = build_remote_commons_app(RemoteCommonsNodeConfig(
        root=tmp_path,
        node_id="commons-node-a",
        signing_key=node_key,
        trust_store=trust,
        workload_digest="sha256:" + "a" * 64,
        arda_appraisal={},
    ))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://commons") as client:
        node_response = await client.get("/v1/node")
        node_document = node_response.json()
        descriptor = node_document["descriptor"]
        node_key.public_key().verify(
            base64.b64decode(node_document["node_signature"]),
            canonical_json(descriptor),
        )
        nonce = "discovery-nonce-" + "x" * 32
        challenge = await client.post("/v1/discovery/challenge", json={
            "nonce": nonce,
            "descriptor_digest": node_document["descriptor_digest"],
        })
        assert challenge.status_code == 200
        proof = challenge.json()
        assert proof["proof"]["nonce"] == nonce
        node_key.public_key().verify(base64.b64decode(proof["node_signature"]), canonical_json(proof["proof"]))

        bucket_body = canonical_json({
            "owner": "edgek", "name": "proof-crystals", "visibility": "private",
            "description": "Proof carrying artifacts",
        })
        bucket_headers = _signed(signer, "POST", "/v1/buckets", bucket_body)
        bucket = await client.post("/v1/buckets", content=bucket_body, headers={**bucket_headers, "Content-Type": "application/json"})
        assert bucket.status_code == 201

        blob = b"verified reusable crystal"
        blob_digest = sha256_bytes(blob)
        blob_target = f"/v1/blobs/{blob_digest}"
        upload = await client.put(
            blob_target,
            content=blob,
            headers={**_signed(signer, "PUT", blob_target, blob), "Content-Type": "application/octet-stream"},
        )
        assert upload.status_code == 201 and upload.json()["digest"] == blob_digest

        revision_target = "/v1/buckets/edgek/proof-crystals/revisions/main"
        revision_body = canonical_json({
            "manifest": {
                "authority": "remote_hypothesis",
                "maximum_authority": "verify_only",
                "files": [{"path": "crystal.json", "digest": blob_digest, "size": len(blob)}],
                "metadata": {"kind": "proof_carrying_crystal"},
            },
            "replace": False,
        })
        revision = await client.put(
            revision_target,
            content=revision_body,
            headers={**_signed(signer, "PUT", revision_target, revision_body), "Content-Type": "application/json"},
        )
        assert revision.status_code == 201
        receipt = revision.json()
        assert receipt["receipt"]["maximum_authority"] == "verify_only"
        node_key.public_key().verify(
            base64.b64decode(receipt["node_signature"]),
            canonical_json(receipt["receipt"]),
        )

        fetched_revision = await client.get(
            revision_target,
            headers=_signed(signer, "GET", revision_target),
        )
        assert fetched_revision.status_code == 200
        fetched_blob = await client.get(
            blob_target,
            headers=_signed(signer, "GET", blob_target),
        )
        assert fetched_blob.status_code == 200 and fetched_blob.content == blob

        local_plane = CommonsEnterprisePlane(tmp_path / "local-plane")
        admission, _evidence = local_plane.admit_remote_revision(
            "commons-node-a",
            fetched_revision.json(),
            {blob_digest: fetched_blob.content},
            workspace_id="workspace-test",
        )
        assert admission["status"] == "quarantined_hypothesis"
        assert admission["local_reproduction_required"] is True
        assert local_plane.vault.get(blob_digest) == blob

        list_target = "/v1/buckets?limit=100"
        listed = await client.get(list_target, headers=_signed(signer, "GET", list_target))
        assert listed.status_code == 200
        assert listed.json()["buckets"][0]["bucket_id"] == "edgek/proof-crystals"


@pytest.mark.asyncio
async def test_remote_commons_rejects_replayed_signed_write(tmp_path):
    node_key = Ed25519PrivateKey.generate()
    client_key = Ed25519PrivateKey.generate()
    signer = CommonsRequestSigner(client_key, node_id="beast", key_id="key-1")
    trust = CommonsClientTrustStore([
        TrustedClient("beast", "key-1", client_key.public_key(), frozenset({"bucket:write"}))
    ])
    app = build_remote_commons_app(RemoteCommonsNodeConfig(
        root=tmp_path,
        node_id="node",
        signing_key=node_key,
        trust_store=trust,
        workload_digest="sha256:" + hashlib.sha256(b"node").hexdigest(),
        arda_appraisal={},
    ))
    body = canonical_json({"owner": "edgek", "name": "one", "visibility": "public", "description": ""})
    headers = {**_signed(signer, "POST", "/v1/buckets", body), "Content-Type": "application/json"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://commons") as client:
        first = await client.post("/v1/buckets", content=body, headers=headers)
        replay = await client.post("/v1/buckets", content=body, headers=headers)
    assert first.status_code == 201
    assert replay.status_code == 401
    assert "replay" in replay.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remote_commons_public_listing_does_not_expose_private_bucket(tmp_path):
    node_key = Ed25519PrivateKey.generate()
    client_key = Ed25519PrivateKey.generate()
    signer = CommonsRequestSigner(client_key, node_id="beast", key_id="key-1")
    trust = CommonsClientTrustStore([
        TrustedClient("beast", "key-1", client_key.public_key(), frozenset({"bucket:write"}))
    ])
    app = build_remote_commons_app(RemoteCommonsNodeConfig(
        root=tmp_path, node_id="node", signing_key=node_key, trust_store=trust,
        workload_digest="sha256:" + "b" * 64, arda_appraisal={},
    ))
    body = canonical_json({"owner": "edgek", "name": "private", "visibility": "private", "description": ""})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://commons") as client:
        created = await client.post(
            "/v1/buckets", content=body,
            headers={**_signed(signer, "POST", "/v1/buckets", body), "Content-Type": "application/json"},
        )
        public = await client.get("/v1/buckets")
    assert created.status_code == 201
    assert public.json()["buckets"] == []


@pytest.mark.asyncio
async def test_remote_commons_ml_kem_challenge_confirms_decapsulation_without_secret_export(tmp_path):
    node_key = Ed25519PrivateKey.generate()
    app = build_remote_commons_app(RemoteCommonsNodeConfig(
        root=tmp_path,
        node_id="commons-node-mlkem",
        signing_key=node_key,
        trust_store=CommonsClientTrustStore(()),
        workload_digest="sha256:" + "c" * 64,
        arda_appraisal={},
    ))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://commons") as client:
        key_response = await client.get("/v1/ml-kem/key")
        assert key_response.status_code == 200
        key_payload = key_response.json()
        document = key_payload["document"]
        assert document["algorithm"] == "ML-KEM-768"
        assert document["secret_exported"] is False
        node_key.public_key().verify(
            base64.b64decode(key_payload["node_signature"]),
            canonical_json(document),
        )

        ciphertext, shared_secret = encapsulate(base64.b64decode(document["public_key_b64"]))
        nonce = "ml-kem-nonce-" + "x" * 32
        transcript_digest = sha256_bytes(canonical_json({
            "node_id": document["node_id"],
            "algorithm": document["algorithm"],
            "public_key_digest": document["public_key_digest"],
        }))
        challenge = await client.post("/v1/ml-kem/challenge", json={
            "public_key_digest": document["public_key_digest"],
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "challenge_nonce": nonce,
            "transcript_digest": transcript_digest,
        })
        assert challenge.status_code == 200
        proof = challenge.json()
        confirmation = proof["confirmation"]
        body = challenge_confirmation_body(
            node_id=document["node_id"],
            algorithm=document["algorithm"],
            public_key_digest=document["public_key_digest"],
            ciphertext_digest=sha256_bytes(ciphertext),
            challenge_nonce=nonce,
            transcript_digest=transcript_digest,
        )
        assert confirmation["confirmation_mac_b64"] == confirmation_mac(shared_secret, body)
        assert "shared_secret" not in canonical_json(proof).decode("utf-8")
        node_key.public_key().verify(
            base64.b64decode(proof["node_signature"]),
            canonical_json(confirmation),
        )
