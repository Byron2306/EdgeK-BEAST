from __future__ import annotations
from typing import Any, Callable, Mapping
from .grand_closure_g2 import G2LiveComposition
from .residual_compute_governor import ResidualComputeRequest


def create_g2_router(composition: G2LiveComposition, decode_request: Callable[[Mapping[str, Any]], ResidualComputeRequest]):
    try:
        from fastapi import APIRouter, HTTPException
    except Exception as exc:
        raise RuntimeError("FastAPI is required to create the G2 router") from exc
    router = APIRouter(prefix="/edgek/compute", tags=["BEAST Grand Closure G2"])

    @router.get("/grand-closure/reachability")
    def reachability():
        receipt = composition.reachability()
        return {"receipt_digest": receipt.receipt_digest, **receipt.__dict__}

    @router.post("/residual-decisions/live")
    def run_live(body: Mapping[str, Any]):
        try:
            request = decode_request(body)
            output, closure = composition.run(request)
            return {"output": output, "closure": closure.__dict__, "closure_digest": closure.closure_digest}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    return router
