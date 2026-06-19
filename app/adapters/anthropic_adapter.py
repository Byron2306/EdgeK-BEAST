"""
Anthropic Adapter for EdgeK BEAST Gateway
Phase 1: Minimal Gateway Implementation
Provides Anthropic-compatible API endpoints with full PREC cycle integration
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

# Create router for Anthropic endpoints
anthropic_router = APIRouter()
context_economizer = ContextEconomizer(reasoner.policies)

@anthropic_router.post("/v1/messages")
async def create_message(request: Request):
    """Handle message creation (Anthropic-compatible) with full PREC cycle"""
    session_id = "default"
    original_request = {}
    
    try:
        body = await request.json()
        original_request = body.copy()
        logger.info(f"Anthropic message request: {body.get('model', 'unknown')}")
        
        # === PREC CYCLE ===
        
        # PERCEIVE: Normalize request to EdgeK IR
        ir = perceiver.perceive(body, ProviderType.ANTHROPIC)
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
                        "type": "authentication_error",
                        "message": governance_result.reason
                    }
                }
            )
        if governance_result.decision == GovernanceDecision.DEFER:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(governance_result.retry_after_seconds or 1)},
                content={
                    "error": {
                        "type": "rate_limit_error",
                        "message": governance_result.reason,
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
            provider_type="anthropic"
        )
        logger.info(f"PREC[CRYSTALLIZE]: Trace {crystallize_result['trace_id']} archived")
        
        # === END PREC CYCLE ===
        
        model = ir.model
        stream = body.get("stream", False)
        
        if stream:
            async def generate_stream():
                # Extract content from provider response
                content = provider_response.get("content", [{}])[0].get("text", "")
                
                # Anthropic streaming format
                yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': provider_response.get('id', 'msg_stream'), 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}})}\n\n"
                
                # Content block start
                yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
                
                # Stream content in chunks
                for i in range(0, len(content), 20):
                    yield f"data: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': content[i:i+20]}})}\n\n"
                
                # Content block stop
                yield f"data: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                
                # Message stop
                yield f"data: {json.dumps({'type': 'message_stop', 'usage': {'input_tokens': 10, 'output_tokens': len(content.split())}})}\n\n"
                
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate_stream(), media_type="text/plain")
        else:
            return JSONResponse(provider_response)
            
    except Exception as e:
        logger.error(f"Error in Anthropic message creation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
