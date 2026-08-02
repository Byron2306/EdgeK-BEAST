from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from .residual_compute_governor import ResidualComputeRequest


def create_prism_r8_router(plane: Any, decode_request: Callable[[dict[str, Any]], ResidualComputeRequest]):
    try:
        from fastapi import APIRouter, HTTPException
    except ImportError as exc:  # optional dependency
        raise RuntimeError("FastAPI is required to construct the PRISM R8 router") from exc

    router = APIRouter(prefix="/edgek/compute", tags=["PRISM R8"])

    @router.get("/residual-state")
    def residual_state() -> dict[str, Any]:
        return {"beast_object_type": "prism_r8_state", "reachable": True, "authority": "read_only"}

    @router.post("/residual-decisions")
    def residual_decision(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = decode_request(payload)
            output, receipt = plane.run(request)
            return {"output": output, "closure": asdict(receipt), "closure_digest": receipt.closure_digest}
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
