"""BEAST control-plane proxy for registered remote Commons nodes."""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.kernel.commons.remote_client import RemoteCommonsGateway


def build_remote_commons_router(gateway: RemoteCommonsGateway, enterprise_plane: Any = None) -> APIRouter:
    router = APIRouter(prefix="/edgek/control-plane/commons/remote", tags=["Remote Commons"])

    def require_local_operator(request: Request) -> None:
        host = str(request.client.host if request.client else "")
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="remote Commons management is restricted to the local BEAST operator boundary")

    @router.get("")
    async def snapshot() -> dict[str, Any]:
        return gateway.snapshot()

    @router.post("/nodes", status_code=201)
    async def register_node(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        require_local_operator(request)
        payload = payload or {}
        try:
            node = gateway.register(
                node_id=str(payload.get("node_id") or ""),
                endpoint=str(payload.get("endpoint") or ""),
                node_public_key=str(payload.get("node_public_key") or ""),
                expected_workload_digest=str(payload.get("expected_workload_digest") or ""),
                require_arda=bool(payload.get("require_arda", False)),
                trust_policy=str(payload.get("trust_policy") or "lattice"),
                expected_policy_generation=str(payload.get("expected_policy_generation") or ""),
            )
            return {"status": "registered", "node": node, "next": "probe"}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/discovery")
    async def discovery_snapshot() -> dict[str, Any]:
        if gateway.discovery_catalog is None:
            raise HTTPException(status_code=503, detail="Commons discovery catalog is not configured")
        return gateway.discovery_catalog.snapshot()

    @router.post("/discovery")
    async def discover_nodes(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        require_local_operator(request)
        payload = payload or {}
        origins = payload.get("origins") or []
        if isinstance(origins, str):
            origins = [origins]
        if not isinstance(origins, list) or not origins or len(origins) > 50:
            raise HTTPException(status_code=422, detail="origins must contain 1 to 50 endpoint origins")
        try:
            return await gateway.discover_origins(
                tuple(str(item) for item in origins),
                source=str(payload.get("source") or "well_known"),
                auto_register=bool(payload.get("auto_register", True)),
            )
        except (PermissionError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/nodes/{node_id}/probe")
    async def probe_node(node_id: str, request: Request) -> dict[str, Any]:
        require_local_operator(request)
        try:
            result = await gateway.probe(node_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not result.get("ok"):
            raise HTTPException(status_code=424, detail=result)
        return result

    @router.get("/nodes/{node_id}/buckets")
    async def list_buckets(node_id: str) -> dict[str, Any]:
        try:
            return await gateway.list_buckets(node_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/nodes/{node_id}/buckets", status_code=201)
    async def create_bucket(node_id: str, request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        require_local_operator(request)
        try:
            return await gateway.create_bucket(node_id, payload or {})
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/nodes/{node_id}/buckets/{owner}/{name}/revisions")
    async def list_revisions(node_id: str, owner: str, name: str) -> dict[str, Any]:
        try:
            return await gateway.list_revisions(node_id, owner=owner, name=name)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/nodes/{node_id}/buckets/{owner}/{name}/revisions/{revision}/import")
    async def import_revision(node_id: str, owner: str, name: str, revision: str, request: Request) -> dict[str, Any]:
        require_local_operator(request)
        if enterprise_plane is None:
            raise HTTPException(status_code=503, detail="local Commons quarantine plane is not configured")
        try:
            remote, blobs = await gateway.pull_revision(
                node_id, owner=owner, name=name, revision=revision,
            )
            admission, evidence = enterprise_plane.admit_remote_revision(
                node_id,
                remote,
                blobs,
                workspace_id=request.headers.get("x-beast-workspace-identity", ""),
            )
            return {
                "status": "quarantined_hypothesis",
                "admission": admission,
                "evidence_node_id": evidence.node_id,
                "next": "run node-local held-out reproduction before promotion",
            }
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/nodes/{node_id}/blobs", status_code=201)
    async def put_blob(node_id: str, request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        require_local_operator(request)
        payload = payload or {}
        try:
            raw = base64.b64decode(str(payload.get("content_b64") or ""), validate=True)
            if not raw or len(raw) > 3 * 1024 * 1024:
                raise ValueError("desktop Commons blob bridge accepts 1 byte to 3 MiB per request")
            return await gateway.put_blob(node_id, raw)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.put("/nodes/{node_id}/buckets/{owner}/{name}/revisions/{revision}", status_code=201)
    async def commit_revision(
        node_id: str, owner: str, name: str, revision: str,
        request: Request, payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        require_local_operator(request)
        payload = payload or {}
        try:
            return await gateway.commit_revision(
                node_id,
                owner=owner,
                name=name,
                revision=revision,
                manifest=dict(payload.get("manifest") or {}),
                replace=bool(payload.get("replace", False)),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router
