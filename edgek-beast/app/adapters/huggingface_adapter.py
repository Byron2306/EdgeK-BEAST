"""
Hugging Face and TGI adapters for EdgeK BEAST Gateway.

These endpoints normalize Hugging Face router/OpenAI-compatible chat requests
and local TGI/llama.cpp requests into EdgeK IR, then run the full PREC cycle.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request  # pyright: reportMissingImports=false
from fastapi.responses import JSONResponse

from app.context.economizer import ContextEconomizer
from app.kernel.crystallize import crystallizer
from app.kernel.execute import executor
from app.kernel.perceive import ProviderType, perceiver
from app.kernel.reason import GovernanceDecision, reasoner


logger = logging.getLogger(__name__)
huggingface_router = APIRouter()
context_economizer = ContextEconomizer(reasoner.policies)


async def _run_prec(body: Dict[str, Any], provider: str, session_id: str = "default") -> JSONResponse:
    original_request = body.copy()
    ir = perceiver.perceive(body, ProviderType.OPENAI)
    ir.metadata["provider"] = provider
    economy_result = context_economizer.economize(ir)
    ir = economy_result.ir
    governance_result = reasoner.reason(ir, session_id)

    if governance_result.decision == GovernanceDecision.DENY:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "message": governance_result.reason,
                    "type": "governance_error",
                    "code": "REQUEST_DENIED",
                }
            },
        )
    if governance_result.decision == GovernanceDecision.DEFER:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(governance_result.retry_after_seconds or 1)},
            content={
                "error": {
                    "message": governance_result.reason,
                    "type": "governance_defer",
                    "code": "REQUEST_DEFERRED",
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
        provider_type=provider,
    )
    return JSONResponse(provider_response)


@huggingface_router.post("/hf/v1/chat/completions")
@huggingface_router.post("/huggingface/v1/chat/completions")
async def huggingface_chat_completions(request: Request):
    """Run a Hugging Face router/OpenAI-compatible chat request through BEAST."""
    try:
        body = await request.json()
        body.setdefault("model", "hf/openai/gpt-oss-120b")
        return await _run_prec(body, provider="huggingface")
    except Exception as exc:
        logger.error("Error in Hugging Face adapter: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@huggingface_router.post("/tgi/v1/chat/completions")
@huggingface_router.post("/llamacpp/v1/chat/completions")
async def tgi_chat_completions(request: Request):
    """Run a local/remote TGI, including llama.cpp backend, through BEAST."""
    try:
        body = await request.json()
        body.setdefault("model", "tgi/Qwen/Qwen2.5-3B-Instruct")
        return await _run_prec(body, provider="tgi")
    except Exception as exc:
        logger.error("Error in TGI adapter: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@huggingface_router.post("/litellm/v1/chat/completions")
async def litellm_chat_completions(request: Request):
    """Run a LiteLLM upstream chat request through BEAST governance."""
    try:
        body = await request.json()
        body.setdefault("model", "litellm/gpt-3.5-turbo")
        return await _run_prec(body, provider="litellm")
    except Exception as exc:
        logger.error("Error in LiteLLM adapter: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
