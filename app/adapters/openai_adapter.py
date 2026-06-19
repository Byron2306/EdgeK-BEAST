"""
OpenAI Adapter for EdgeK BEAST Gateway
Phase 1: Minimal Gateway Implementation
Provides OpenAI-compatible API endpoints with full PREC cycle integration
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import json
import logging

# Import PREC cycle kernel modules
from app.context.economizer import ContextEconomizer
from app.kernel.perceive import ProviderType, perceiver
from app.kernel.reason import GovernanceDecision, reasoner
from app.kernel.execute import executor
from app.kernel.crystallize import crystallizer

logger = logging.getLogger(__name__)

# Create router for OpenAI endpoints
openai_router = APIRouter()
context_economizer = ContextEconomizer(reasoner.policies)

@openai_router.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)"""
    return {
        "object": "list",
        "data": [
            {
                "id": "gpt-3.5-turbo",
                "object": "model",
                "created": 1677610602,
                "owned_by": "edgek-beast"
            },
            {
                "id": "gpt-4",
                "object": "model", 
                "created": 1677610602,
                "owned_by": "edgek-beast"
            }
        ]
    }

@openai_router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Handle chat completions (OpenAI-compatible) with full PREC cycle"""
    session_id = "default"  # Would come from auth/session management
    original_request = {}
    
    try:
        body = await request.json()
        original_request = body.copy()
        logger.info(f"OpenAI chat completion request: {body.get('model', 'unknown')}")
        
        # === PREC CYCLE ===
        
        # PERCEIVE: Normalize request to EdgeK IR
        ir = perceiver.perceive(body, ProviderType.OPENAI)
        logger.info(f"PREC[PERCEIVE]: Normalized to EdgeK IR for model {ir.model}")

        # ECONOMIZE: Reduce oversized context before governance
        economy_result = context_economizer.economize(ir)
        ir = economy_result.ir
        if economy_result.changed:
            logger.info(
                "PREC[ECONOMIZE]: Context reduced from %s to %s estimated tokens",
                economy_result.original_tokens,
                economy_result.final_tokens
            )
        
        # REASON: Apply governance policies
        governance_result = reasoner.reason(ir, session_id)
        logger.info(f"PREC[REASON]: Decision={governance_result.decision.value}, "
                   f"Reason={governance_result.reason}")
        
        # If governance denied, return error
        if governance_result.decision == GovernanceDecision.DENY:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "message": governance_result.reason,
                        "type": "governance_error",
                        "code": "REQUEST_DENIED"
                    }
                }
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
                        "reset_at": governance_result.reset_at
                    }
                }
            )
        
        # EXECUTE: Route to provider (use modified IR if policy changed it)
        effective_ir = governance_result.modified_ir or ir
        provider_response = await executor.execute(effective_ir, governance_result)
        reasoner.record_usage(effective_ir, session_id, governance_result.budget_impact)
        logger.info(f"PREC[EXECUTE]: Response received")
        
        # CRYSTALLIZE: Archive trace and emit telemetry
        crystallize_result = await crystallizer.crystallize(
            original_request=original_request,
            ir=ir,
            governance_result=governance_result,
            provider_response=provider_response,
            session_id=session_id,
            provider_type="openai"
        )
        logger.info(f"PREC[CRYSTALLIZE]: Trace {crystallize_result['trace_id']} archived")
        
        # === END PREC CYCLE ===
        
        model = ir.model
        stream = ir.stream
        
        if stream:
            async def generate_stream():
                # Simulate streaming response
                content = provider_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                for i in range(0, len(content), 10):
                    chunk = {
                        "id": provider_response.get("id", "chatcmpl-stream"),
                        "object": "chat.completion.chunk",
                        "created": provider_response.get("created", 1234567890),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": content[i:i+10]},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                # Send final chunk
                final_chunk = {
                    "id": provider_response.get("id", "chatcmpl-stream"),
                    "object": "chat.completion.chunk",
                    "created": provider_response.get("created", 1234567890),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate_stream(), media_type="text/plain")
        else:
            return JSONResponse(provider_response)
            
    except Exception as e:
        logger.error(f"Error in OpenAI chat completion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@openai_router.post("/v1/completions")
async def completions(request: Request):
    """Handle completions (OpenAI-compatible) with full PREC cycle"""
    session_id = "default"
    original_request = {}
    
    try:
        body = await request.json()
        original_request = body.copy()
        logger.info(f"OpenAI completion request: {body.get('model', 'unknown')}")
        
        # === PREC CYCLE ===
        
        # PERCEIVE: Normalize request to EdgeK IR
        ir = perceiver.perceive(body, ProviderType.OPENAI)
        logger.info(f"PREC[PERCEIVE]: Normalized to EdgeK IR for model {ir.model}")

        # ECONOMIZE: Reduce oversized context before governance
        economy_result = context_economizer.economize(ir)
        ir = economy_result.ir
        if economy_result.changed:
            logger.info(
                "PREC[ECONOMIZE]: Context reduced from %s to %s estimated tokens",
                economy_result.original_tokens,
                economy_result.final_tokens
            )
        
        # REASON: Apply governance policies
        governance_result = reasoner.reason(ir, session_id)
        logger.info(f"PREC[REASON]: Decision={governance_result.decision.value}, "
                   f"Reason={governance_result.reason}")
        
        # If governance denied, return error
        if governance_result.decision == GovernanceDecision.DENY:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "message": governance_result.reason,
                        "type": "governance_error",
                        "code": "REQUEST_DENIED"
                    }
                }
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
                        "reset_at": governance_result.reset_at
                    }
                }
            )
        
        # EXECUTE: Route to provider
        effective_ir = governance_result.modified_ir or ir
        provider_response = await executor.execute(effective_ir, governance_result)
        reasoner.record_usage(effective_ir, session_id, governance_result.budget_impact)
        logger.info(f"PREC[EXECUTE]: Response received")
        
        # CRYSTALLIZE: Archive trace and emit telemetry
        crystallize_result = await crystallizer.crystallize(
            original_request=original_request,
            ir=ir,
            governance_result=governance_result,
            provider_response=provider_response,
            session_id=session_id,
            provider_type="openai"
        )
        logger.info(f"PREC[CRYSTALLIZE]: Trace {crystallize_result['trace_id']} archived")
        
        # === END PREC CYCLE ===
        
        return JSONResponse(provider_response)
            
    except Exception as e:
        logger.error(f"Error in OpenAI completion: {e}")
        raise HTTPException(status_code=500, detail=str(e))
