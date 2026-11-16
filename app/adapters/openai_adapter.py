"""
OpenAI Adapter for EdgeK BEAST Gateway
Phase 1: Minimal Gateway Implementation
Provides OpenAI-compatible API endpoints with full PREC cycle integration
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import json
import logging

from app.kernel.compute.container import container
from app.kernel.compute.perceive import ProviderType
from app.kernel.governance.reason import GovernanceDecision

logger = logging.getLogger(__name__)

# Create router for OpenAI endpoints
openai_router = APIRouter()

def get_orchestrator():
    return container.get("prec_orchestrator")

@openai_router.get("/v1/models")
async def list_models():
    """List models actually installed on the local Ollama server.

    This inventory is not an assertion that the PREC chat-completions
    route supports every listed model. Cloud providers are never silently
    represented as locally installed models.
    """
    import asyncio
    import os
    import urllib.error
    import urllib.request
    from fastapi import HTTPException

    raw_host = (os.environ.get("BEAST_OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip()
    host = raw_host if raw_host.startswith(("http://", "https://")) else "http://" + raw_host
    url = host.rstrip("/") + "/api/tags"

    def fetch_models():
        with urllib.request.urlopen(url, timeout=3) as response:
            result = json.load(response)
        if not isinstance(result, dict) or not isinstance(result.get("models"), list):
            raise ValueError("Ollama tags response is malformed")
        return result["models"]

    try:
        installed = await asyncio.to_thread(fetch_models)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        logger.warning("Local Ollama model inventory unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Local Ollama model inventory unavailable") from exc

    models = []
    seen = set()
    for item in installed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        models.append({"id": name, "object": "model", "created": 0, "owned_by": "ollama"})
    return {"object": "list", "data": models}

@openai_router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Handle chat completions (OpenAI-compatible) with full PREC cycle"""
    session_id = "default"  # Would come from auth/session management
    
    try:
        body = await request.json()
        logger.info(f"OpenAI chat completion request: {body.get('model', 'unknown')}")
        
        # === PREC CYCLE ===
        orchestrator = get_orchestrator()
        governance_result, provider_response, ir = await orchestrator.execute_cycle(
            body, ProviderType.OPENAI, session_id
        )
        
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
    
    try:
        body = await request.json()
        logger.info(f"OpenAI completion request: {body.get('model', 'unknown')}")
        
        # === PREC CYCLE ===
        orchestrator = get_orchestrator()
        governance_result, provider_response, ir = await orchestrator.execute_cycle(
            body, ProviderType.OPENAI, session_id
        )
        
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
        
        # === END PREC CYCLE ===
        
        return JSONResponse(provider_response)
            
    except Exception as e:
        logger.error(f"Error in OpenAI completion: {e}")
        raise HTTPException(status_code=500, detail=str(e))
