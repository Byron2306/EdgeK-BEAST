from __future__ import annotations
from typing import Any, Callable, Mapping
from .grand_closure_g2 import G2LiveComposition
from .grand_closure_g3 import G3ReachabilityAuditor, mount_g3


def create_g3_audit_router(composition: G2LiveComposition):
    try:
        from fastapi import APIRouter
    except Exception as exc:
        raise RuntimeError("FastAPI is required to create the G3 router") from exc
    router = APIRouter(prefix="/edgek/compute", tags=["BEAST Grand Closure G3"])

    @router.get("/grand-closure/contract-audit")
    def contract_audit():
        receipt = G3ReachabilityAuditor(composition, mounted=True).audit()
        return {"receipt_digest": receipt.receipt_digest, **receipt.__dict__}

    return router


def mount_g3_routes(app: Any, composition: G2LiveComposition, decode_request: Callable[[Mapping[str, Any]], Any]):
    receipt = mount_g3(app, composition, decode_request)
    app.include_router(create_g3_audit_router(composition))
    return receipt
