"""Deployable remote BEAST Commons bucket/Space node.

Run with ``uvicorn app.commons_node_main:app``.  This entry point intentionally
does not import ``app.main`` so a remote storage node has no execution, provider
or host-control authority.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.kernel.commons.remote_protocol import (
    AuthenticatedRequest,
    CommonsClientTrustStore,
    CommonsRequestVerifier,
    SqliteReplayLedger,
    canonical_json,
    sha256_bytes,
)
from app.kernel.commons.remote_store import CommonsBucketStore


class BucketCreate(BaseModel):
    owner: str
    name: str
    visibility: str = "private"
    description: str = ""


class RevisionCommit(BaseModel):
    manifest: dict[str, Any]
    replace: bool = False


class DiscoveryChallenge(BaseModel):
    nonce: str = Field(min_length=32, max_length=256)
    descriptor_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class RemoteCommonsNodeConfig:
    root: Path
    node_id: str
    signing_key: Ed25519PrivateKey
    trust_store: CommonsClientTrustStore
    workload_digest: str
    arda_appraisal: Mapping[str, Any]
    trust_evidence: tuple[Mapping[str, Any], ...] = ()
    trust_evidence_path: Path | None = None
    maximum_blob_bytes: int = 4 * 1024**3


def _target(request: Request) -> str:
    query = request.url.query
    return request.url.path + (f"?{query}" if query else "")


def _load_private_key(path: str | Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("BEAST Commons node signing key must be Ed25519")
    return key


def _default_config() -> RemoteCommonsNodeConfig:
    root = Path(os.environ.get("BEAST_COMMONS_NODE_ROOT", os.environ.get("BEAST_COMMONS_ROOT", ".beast/remote-commons-node"))).expanduser()
    node_id = os.environ.get("BEAST_COMMONS_NODE_ID", os.environ.get("BEAST_NODE_ID", "commons-node-unconfigured")).strip()
    signing_path = os.environ.get("BEAST_COMMONS_NODE_SIGNING_KEY", "").strip()
    trust_path = os.environ.get("BEAST_COMMONS_CLIENT_TRUST_STORE", "").strip()
    if signing_path:
        key = _load_private_key(signing_path)
    elif os.environ.get("BEAST_COMMONS_ALLOW_EPHEMERAL_IDENTITY") == "1":
        key = Ed25519PrivateKey.generate()
    else:
        raise RuntimeError("BEAST_COMMONS_NODE_SIGNING_KEY is required (or explicitly allow an ephemeral development identity)")
    trust = CommonsClientTrustStore.from_file(trust_path) if trust_path else CommonsClientTrustStore(())
    appraisal_path = os.environ.get("BEAST_COMMONS_ARDA_APPRAISAL", "").strip()
    appraisal = json.loads(Path(appraisal_path).expanduser().read_text(encoding="utf-8")) if appraisal_path else {}
    evidence_path_value = os.environ.get("BEAST_COMMONS_TRUST_EVIDENCE", "").strip()
    workload_digest = os.environ.get("BEAST_COMMONS_WORKLOAD_DIGEST", "").strip()
    if not workload_digest:
        workload_digest = sha256_bytes(Path(__file__).read_bytes())
    return RemoteCommonsNodeConfig(
        root=root,
        node_id=node_id,
        signing_key=key,
        trust_store=trust,
        workload_digest=workload_digest,
        arda_appraisal=appraisal,
        trust_evidence=(),
        trust_evidence_path=Path(evidence_path_value).expanduser() if evidence_path_value else None,
        maximum_blob_bytes=int(os.environ.get("BEAST_COMMONS_MAX_BLOB_BYTES", str(4 * 1024**3))),
    )


def build_remote_commons_app(config: RemoteCommonsNodeConfig) -> FastAPI:
    if not config.node_id:
        raise ValueError("remote Commons node_id is required")
    if not config.workload_digest.startswith("sha256:"):
        raise ValueError("remote Commons workload identity must be a sha256 digest")
    store = CommonsBucketStore(config.root / "store", maximum_blob_bytes=config.maximum_blob_bytes)
    verifier = CommonsRequestVerifier(
        config.trust_store,
        SqliteReplayLedger(config.root / "trust" / "request-replay.sqlite3"),
    )
    public_key = base64.b64encode(config.signing_key.public_key().public_bytes_raw()).decode("ascii")
    application = FastAPI(
        title="BEAST Remote Commons Node",
        version="1.0.0",
        docs_url="/docs" if os.environ.get("BEAST_COMMONS_ENABLE_DOCS") == "1" else None,
        redoc_url=None,
    )

    async def authenticate(request: Request, scope: str) -> AuthenticatedRequest:
        body = await request.body()
        try:
            return verifier.verify(
                method=request.method,
                target=_target(request),
                body=body,
                headers=request.headers,
                required_scope=scope,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def current_trust_evidence() -> list[Mapping[str, Any]]:
        evidence = [dict(item) for item in config.trust_evidence]
        if config.trust_evidence_path:
            try:
                loaded = json.loads(config.trust_evidence_path.read_text(encoding="utf-8"))
                rows = loaded.get("trust_evidence") if isinstance(loaded, Mapping) else loaded
                if isinstance(rows, list):
                    evidence.extend(dict(item) for item in rows if isinstance(item, Mapping))
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        if config.arda_appraisal:
            evidence.append(dict(config.arda_appraisal))
        return evidence

    def signed_node_document() -> dict[str, Any]:
        attestation_subject = {
            "node_id": config.node_id,
            "workload_digest": config.workload_digest,
            "node_public_key": public_key,
            "protocol": "beast-commons-http-signature-v1",
            "capabilities": ["bucket_registry", "immutable_blobs", "signed_revisions", "replay_resistant_requests"],
            "maximum_authority": "verify_only",
        }
        descriptor = {
            "beast_object_type": "remote_commons_node_descriptor",
            "schema_version": "1.0",
            **attestation_subject,
            "attestation_subject_digest": sha256_bytes(canonical_json(attestation_subject)),
            "trust_evidence": current_trust_evidence(),
            "arda_appraisal": dict(config.arda_appraisal),
            "storage": store.stats(),
        }
        descriptor_digest = sha256_bytes(canonical_json(descriptor))
        return {
            "descriptor": descriptor,
            "descriptor_digest": descriptor_digest,
            "signature_algorithm": "ed25519",
            "node_signature": base64.b64encode(config.signing_key.sign(canonical_json(descriptor))).decode("ascii"),
        }

    def signed_revision_result(result: Mapping[str, Any], *, owner: str, name: str, revision: str) -> dict[str, Any]:
        receipt = {
            "beast_object_type": "remote_commons_revision_receipt",
            "node_id": config.node_id,
            "bucket_id": f"{owner}/{name}",
            "revision": revision,
            "manifest_digest": result["manifest_digest"],
            "committed_by": result["committed_by"],
            "committed_at": result["committed_at"],
            "maximum_authority": "verify_only",
        }
        return {
            **dict(result),
            "receipt": receipt,
            "receipt_digest": sha256_bytes(canonical_json(receipt)),
            "node_signature": base64.b64encode(config.signing_key.sign(canonical_json(receipt))).decode("ascii"),
        }

    @application.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "beast-remote-commons-node", "node_id": config.node_id, "storage": store.stats()}

    @application.get("/v1/node")
    async def node_descriptor() -> dict[str, Any]:
        return signed_node_document()

    @application.get("/.well-known/beast-commons.json")
    async def discovery_document() -> dict[str, Any]:
        return {
            "discovery_protocol": "beast-trust-commons-discovery-v1",
            "source_independent": True,
            "transport_profiles": ["https-json-v1", "signed-content-addressed-buckets-v1"],
            "api_base": "/v1",
            "node": signed_node_document(),
            "admission_boundary": "discovery_is_a_candidate_not_trust",
        }

    @application.post("/v1/discovery/challenge")
    async def discovery_challenge(payload: DiscoveryChallenge) -> dict[str, Any]:
        current = signed_node_document()
        if payload.descriptor_digest != current["descriptor_digest"]:
            raise HTTPException(status_code=409, detail="descriptor changed; refresh discovery document")
        proof = {
            "beast_object_type": "commons_discovery_endpoint_proof",
            "schema_version": "1.0",
            "node_id": config.node_id,
            "nonce": payload.nonce,
            "descriptor_digest": payload.descriptor_digest,
            "issued_at": time.time(),
            "maximum_authority": "endpoint_possession_only",
        }
        return {
            "proof": proof,
            "signature_algorithm": "ed25519",
            "node_signature": base64.b64encode(config.signing_key.sign(canonical_json(proof))).decode("ascii"),
        }

    @application.get("/v1/buckets")
    async def list_buckets(request: Request, limit: int = 100) -> dict[str, Any]:
        authenticated = False
        if request.headers.get("x-commons-signature"):
            await authenticate(request, "bucket:read")
            authenticated = True
        return {"buckets": store.list_buckets(include_private=authenticated, limit=limit), "authenticated": authenticated}

    @application.post("/v1/buckets", status_code=201)
    async def create_bucket(request: Request, payload: BucketCreate) -> dict[str, Any]:
        actor = await authenticate(request, "bucket:write")
        try:
            bucket = store.create_bucket(
                owner=payload.owner, name=payload.name, visibility=payload.visibility,
                description=payload.description, actor=actor.node_id,
            )
            return {"status": "created", "bucket": bucket}
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/v1/buckets/{owner}/{name}")
    async def get_bucket(owner: str, name: str, request: Request) -> dict[str, Any]:
        try:
            return {"bucket": store.get_bucket(owner, name, include_private=False)}
        except FileNotFoundError:
            await authenticate(request, "bucket:read")
            try:
                return {"bucket": store.get_bucket(owner, name, include_private=True)}
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.put("/v1/blobs/{digest}", status_code=201)
    async def put_blob(digest: str, request: Request) -> dict[str, Any]:
        actor = await authenticate(request, "blob:write")
        body = await request.body()
        try:
            return store.put_blob(body, expected_digest=digest, actor=actor.node_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.head("/v1/blobs/{digest}")
    async def head_blob(digest: str, request: Request) -> Response:
        await authenticate(request, "bucket:read")
        if not store.has_blob(digest):
            raise HTTPException(status_code=404, detail="Commons blob not found")
        payload = store.get_blob(digest)
        return Response(status_code=200, headers={"Content-Length": str(len(payload)), "ETag": digest})

    @application.get("/v1/blobs/{digest}")
    async def get_blob(digest: str, request: Request) -> Response:
        await authenticate(request, "bucket:read")
        try:
            payload = store.get_blob(digest)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Commons blob not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(payload, media_type="application/octet-stream", headers={"ETag": digest})

    @application.get("/v1/buckets/{owner}/{name}/revisions")
    async def list_revisions(owner: str, name: str, request: Request) -> dict[str, Any]:
        try:
            rows = store.list_revisions(owner, name, include_private=False)
        except FileNotFoundError:
            await authenticate(request, "bucket:read")
            try:
                rows = store.list_revisions(owner, name, include_private=True)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"bucket_id": f"{owner}/{name}", "revisions": rows}

    @application.put("/v1/buckets/{owner}/{name}/revisions/{revision}", status_code=201)
    async def commit_revision(owner: str, name: str, revision: str, request: Request, payload: RevisionCommit) -> dict[str, Any]:
        actor = await authenticate(request, "bucket:write")
        try:
            result = store.commit_revision(
                owner=owner, name=name, revision=revision, manifest=payload.manifest,
                actor=actor.node_id, replace=payload.replace,
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=424, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"status": "committed", **signed_revision_result(
            {**result, "committed_by": actor.node_id}, owner=owner, name=name, revision=revision,
        )}

    @application.get("/v1/buckets/{owner}/{name}/revisions/{revision}")
    async def get_revision(owner: str, name: str, revision: str, request: Request) -> dict[str, Any]:
        try:
            result = store.get_revision(owner, name, revision, include_private=False)
        except FileNotFoundError:
            await authenticate(request, "bucket:read")
            try:
                result = store.get_revision(owner, name, revision, include_private=True)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        return signed_revision_result(result, owner=owner, name=name, revision=revision)

    application.state.commons_store = store
    application.state.request_verifier = verifier
    application.state.node_config = config
    return application


def _configuration_error_app(error: Exception) -> FastAPI:
    application = FastAPI(title="BEAST Remote Commons Node (configuration required)")

    @application.get("/health", status_code=503)
    async def health() -> dict[str, Any]:
        return {"ok": False, "service": "beast-remote-commons-node", "status": "configuration_required", "detail": str(error)}

    return application


try:
    app = build_remote_commons_app(_default_config())
except Exception as _startup_error:  # Keep deployment health visible without opening storage routes.
    app = _configuration_error_app(_startup_error)
