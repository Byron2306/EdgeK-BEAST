from __future__ import annotations
from typing import Any, Mapping
from dataclasses import asdict
from .grand_closure_g4 import G4ReadOnlyCanary


def create_g4_router(canary: G4ReadOnlyCanary):
    try:
        from fastapi import APIRouter, HTTPException
    except ImportError as exc:
        raise RuntimeError("FastAPI is required to mount the G4 router") from exc
    router = APIRouter(prefix="/edgek/compute/grand-closure", tags=["grand-closure"])

    @router.post("/g4/read-only-canary")
    def run_g4(payload: Mapping[str, Any]):
        try:
            receipt = canary.run(
                repository_root=str(payload["repository_root"]),
                workspace_id=str(payload["workspace_id"]),
                privacy_domain=str(payload["privacy_domain"]),
                policy_digest=str(payload["policy_digest"]),
                source_state_digest=str(payload["source_state_digest"]),
                arda_ref=str(payload.get("arda_ref", "arda:g4-read-only-approved")),
                max_entries=int(payload.get("max_entries", 10_000)),
            )
            return {**asdict(receipt)}
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
