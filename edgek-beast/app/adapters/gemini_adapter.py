"""
Gemini-compatible adapter for EdgeK BEAST Gateway.
Normalizes Google generateContent requests into EdgeK IR and returns a
Gemini-shaped response after the PREC cycle.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.context.economizer import ContextEconomizer
from app.kernel.crystallize import crystallizer
from app.kernel.execute import executor
from app.kernel.perceive import ProviderType, perceiver
from app.kernel.reason import GovernanceDecision, reasoner


logger = logging.getLogger(__name__)
gemini_router = APIRouter()
context_economizer = ContextEconomizer(reasoner.policies)


def _with_model(body: Dict[str, Any], model: str) -> Dict[str, Any]:
    payload = dict(body or {})
    payload.setdefault("model", model)
    return payload


@gemini_router.post("/v1beta/models/{model}:generateContent")
@gemini_router.post("/v1/models/{model}:generateContent")
async def generate_content(model: str, request: Request):
    """Handle Gemini generateContent requests through PREC governance."""
    session_id = "default"
    original_request: Dict[str, Any] = {}
    try:
        body = _with_model(await request.json(), model)
        original_request = body.copy()
        ir = perceiver.perceive(body, ProviderType.GEMINI)
        economy_result = context_economizer.economize(ir)
        ir = economy_result.ir
        governance_result = reasoner.reason(ir, session_id)

        if governance_result.decision == GovernanceDecision.DENY:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": 403,
                        "message": governance_result.reason,
                        "status": "PERMISSION_DENIED",
                    }
                },
            )
        if governance_result.decision == GovernanceDecision.DEFER:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(governance_result.retry_after_seconds or 1)},
                content={
                    "error": {
                        "code": 429,
                        "message": governance_result.reason,
                        "status": "RESOURCE_EXHAUSTED",
                        "retry_after_seconds": governance_result.retry_after_seconds,
                        "reset_at": governance_result.reset_at,
                    }
                },
            )

        effective_ir = governance_result.modified_ir or ir
        provider_response = await executor.execute(effective_ir, governance_result)
        reasoner.record_usage(effective_ir, session_id, governance_result.budget_impact)
        await crystallizer.crystallize(
            original_request=original_request,
            ir=ir,
            governance_result=governance_result,
            provider_response=provider_response,
            session_id=session_id,
            provider_type="gemini",
        )
        return JSONResponse(provider_response)
    except Exception as exc:
        logger.error("Error in Gemini generateContent: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
