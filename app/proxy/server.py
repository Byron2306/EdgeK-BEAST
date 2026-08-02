"""EdgeK BEAST proxy lane.

This router mounts provider-compatible HTTP surfaces under /proxy/* while keeping
BEAST governance in the provider adapters themselves.
"""

import asyncio
import json
import os
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.adapters.anthropic_adapter import anthropic_router
from app.adapters.gemini_adapter import gemini_router
from app.adapters.huggingface_adapter import _run_prec, huggingface_router
from app.adapters.openai_adapter import openai_router
from app.kernel.adapters.provider_adapters import ProviderAdapterRegistry
from app.kernel.registry.provider_registry import ProviderRegistry

proxy_router = APIRouter(tags=["proxy"])


@proxy_router.get("/health")
async def proxy_health():
    registry = ProviderRegistry().records(include_disabled=False)
    return {
        "status": "healthy",
        "service": "edgek-beast-proxy",
        "base_url": "http://127.0.0.1:8000/proxy",
        "governance": "BEAST proxy remains in front of native, OpenAI-compatible, LiteLLM, and Ollama lanes.",
        "providers": [record.provider_id for record in registry],
        "backend_classes": sorted(ProviderRegistry.BACKENDS),
        "lanes": {
            "compatibility": "/v1/*",
            "provider_explicit": "/proxy/<provider>/*",
            "mcp_governance": "stdio beast mcp or HTTP /mcp/*",
        },
    }


proxy_router.include_router(anthropic_router, prefix="/anthropic")
proxy_router.include_router(openai_router, prefix="/openai")
proxy_router.include_router(gemini_router, prefix="/gemini")
proxy_router.include_router(huggingface_router, prefix="/huggingface")


async def _registry_chat(provider: str, request: Request):
    provider = provider.replace("-", "_")
    try:
        adapter_plan = ProviderAdapterRegistry().adapter_for(provider).plan_chat()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider registry entry: {provider}")
    if adapter_plan.backend.startswith("native_"):
        raise HTTPException(
            status_code=404,
            detail=f"Provider {provider} uses native route {adapter_plan.proxy_path}; call that adapter path directly.",
        )
    body: Dict[str, Any] = await request.json()
    body = dict(body)
    adapter_plan = ProviderAdapterRegistry().adapter_for(provider).plan_chat(str(body.get("model") or ""))
    body["model"] = adapter_plan.model
    body.setdefault("metadata", {})
    if isinstance(body["metadata"], dict):
        body["metadata"]["edgek_provider"] = provider
        body["metadata"]["edgek_provider_backend"] = adapter_plan.backend
        body["metadata"]["route_provider"] = adapter_plan.route_provider
        body["metadata"]["provider_config"] = adapter_plan.to_dict()
    if _should_render_governed_sse(body, adapter_plan.to_dict()):
        # Do not send a compatibility stream around the governed executor.
        # That used to bypass reuse, the compute governor, crystallization and
        # stream interception whenever BEAST_PROXY_DIRECT_PROVIDER_SSE was on.
        # Keep SSE framing for clients, but produce it from the governed,
        # intercepted response.
        body.setdefault("metadata", {})
        if isinstance(body["metadata"], dict):
            # Structured IDE Action IR is an all-or-nothing edit contract.
            # It must reach the validator as one coherent object.  The
            # generic stream interceptor is valuable for conversational,
            # governed objects, but it deliberately cancels upstream output
            # as soon as it sees JSON-like content.  Enabling that behaviour
            # here caused compatible providers to lose the tail of an Action
            # IR patch and left the resolver with stale/partial anchors.
            #
            # We still render the completed governed result as SSE for the
            # desktop UI; only early upstream cancellation is disabled for
            # this exact structured-output lane.
            action_ir_turn = body["metadata"].get("edgek_action_ir_required") is True
            body["metadata"]["stream_interception_enabled"] = not action_ir_turn
            if action_ir_turn:
                body["metadata"]["stream_interception_bypass_reason"] = "action_ir_requires_complete_response"
            body["metadata"]["stream_ingress"] = "proxy_openai_compatible"
        return StreamingResponse(
            _governed_openai_sse_live(
                body,
                provider=adapter_plan.provider_id,
                relay_action_ir=action_ir_turn,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-EdgeK-Provider": adapter_plan.provider_id,
                "X-EdgeK-Stream-Path": "registry_governed_stream_interception",
            },
        )
    return await _run_prec(body, provider=adapter_plan.provider_id)


def _should_render_governed_sse(body: Dict[str, Any], adapter_plan: Dict[str, Any]) -> bool:
    """Select compatibility SSE framing without permitting an upstream bypass."""
    enabled = os.environ.get(
        "BEAST_PROXY_GOVERNED_SSE", os.environ.get("BEAST_PROXY_DIRECT_PROVIDER_SSE", "1")
    ).strip().lower() not in {"0", "false", "no", "off"}
    if not enabled or body.get("stream") is not True:
        return False
    backend = str(adapter_plan.get("backend") or "")
    provider_id = str(adapter_plan.get("provider_id") or "")
    if backend not in {"openai_compatible", "ollama"} and not (backend == "litellm" and provider_id == "cerebras"):
        return False
    env_names = adapter_plan.get("env") if isinstance(adapter_plan.get("env"), list) else []
    if backend == "ollama":
        return bool(adapter_plan.get("base_url"))
    if not env_names:
        return False
    return bool(os.environ.get(str(env_names[0])))


async def _governed_openai_sse(response) -> AsyncIterator[str]:
    """Render a completed governed response as standard OpenAI SSE chunks."""
    payload = json.loads(response.body)
    content = str(
        ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        or payload.get("text")
        or ""
    )
    response_id = str(payload.get("id") or "chatcmpl-governed-stream")
    model = str(payload.get("model") or "")
    for offset in range(0, len(content), 256):
        yield "data: " + json.dumps({
            "id": response_id, "object": "chat.completion.chunk", "model": model,
            "choices": [{"index": 0, "delta": {"content": content[offset:offset + 256]}, "finish_reason": None}],
        }, separators=(",", ":")) + "\n\n"
    finish_reason = str(((payload.get("choices") or [{}])[0].get("finish_reason") or "stop"))
    yield "data: " + json.dumps({
        "id": response_id, "object": "chat.completion.chunk", "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    }, separators=(",", ":")) + "\n\n"
    yield "data: [DONE]\n\n"


async def _governed_openai_sse_live(
    body: Dict[str, Any] | Any, *, provider: str, relay_action_ir: bool = False
) -> AsyncIterator[str]:
    """Open SSE immediately and relay governed Action IR deltas when available.

    PREC still owns the complete response, receipts, and crystallization. For
    a structured Action IR turn, its executor additionally invokes the local
    callback for each upstream delta. Those deltas are real provider output,
    not synthetic content, and the complete response remains the only object
    accepted by SourcePlan validation.
    """
    deltas: asyncio.Queue[str] = asyncio.Queue()

    async def relay_delta(text: str) -> None:
        if text:
            await deltas.put(text)

    # Accept an awaitable response too so this transport helper remains useful
    # in focused unit tests and for legacy internal callers.
    response_awaitable = (
        _run_prec(body, provider=provider, stream_callback=relay_delta if relay_action_ir else None)
        if isinstance(body, dict)
        else body
    )
    task = asyncio.create_task(response_awaitable)
    elapsed_seconds = 0
    emitted_live_delta = False
    try:
        yield "event: edgek_status\n" + "data: " + json.dumps({
            "phase": "governed_execution",
            "provider": provider,
            "message": f"{provider} is preparing a governed response",
            "elapsed_seconds": elapsed_seconds,
        }, separators=(",", ":")) + "\n\n"
        while not task.done() or not deltas.empty():
            try:
                text = await asyncio.wait_for(deltas.get(), timeout=2.0)
                emitted_live_delta = True
                yield _openai_sse_delta(text, provider=provider)
            except asyncio.TimeoutError:
                if task.done():
                    continue
                elapsed_seconds += 2
                yield "event: edgek_status\n" + "data: " + json.dumps({
                    "phase": "governed_execution",
                    "provider": provider,
                    "message": f"{provider} is still generating through BEAST governance",
                    "elapsed_seconds": elapsed_seconds,
                }, separators=(",", ":")) + "\n\n"
        response = await task
        if response.status_code >= 400:
            yield "event: edgek_error\n" + "data: " + response.body.decode("utf-8", errors="replace") + "\n\n"
            yield "data: [DONE]\n\n"
            return
        # PREC can deliberately defer or reject a request while preserving a
        # 200 transport response for compatibility callers.  An SSE client
        # must not mistake that governed error envelope for a successful,
        # empty model completion: surface it as an explicit retryable event so
        # the Pair Programmer can retain its context/evidence and follow its
        # normal recovery path.
        try:
            completed_payload = json.loads(response.body)
        except (TypeError, ValueError, json.JSONDecodeError):
            completed_payload = {}
        if isinstance(completed_payload, dict) and completed_payload.get("error"):
            yield "event: edgek_error\n" + "data: " + json.dumps(
                completed_payload, separators=(",", ":")
            ) + "\n\n"
            yield "data: [DONE]\n\n"
            return
        if emitted_live_delta:
            payload = json.loads(response.body)
            response_id = str(payload.get("id") or "chatcmpl-governed-stream")
            model = str(payload.get("model") or "")
            finish_reason = str(((payload.get("choices") or [{}])[0].get("finish_reason") or "stop"))
            yield "data: " + json.dumps({
                "id": response_id, "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            }, separators=(",", ":")) + "\n\n"
            yield "data: [DONE]\n\n"
        else:
            async for frame in _governed_openai_sse(response):
                yield frame
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def _openai_sse_delta(text: str, *, provider: str) -> str:
    return "data: " + json.dumps({
        "id": f"{provider}-governed-stream", "object": "chat.completion.chunk", "model": "",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }, separators=(",", ":")) + "\n\n"


@proxy_router.post("/v1/chat/completions")
async def proxy_compat_chat_completions(request: Request):
    """Compatibility lane under /proxy/v1 that still enters BEAST governance."""
    provider = request.headers.get("X-EdgeK-Provider") or request.query_params.get("provider") or "litellm"
    return await _registry_chat(str(provider), request)


@proxy_router.post("/{provider}/v1/chat/completions")
async def proxy_provider_chat_completions(provider: str, request: Request):
    """Registry-backed provider-explicit OpenAI-compatible chat lane."""
    return await _registry_chat(provider, request)

__all__ = ["proxy_router"]
