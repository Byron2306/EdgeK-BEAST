"""EdgeK BEAST proxy lane.

This router mounts provider-compatible HTTP surfaces under /proxy/* while keeping
BEAST governance in the provider adapters themselves.
"""

import json
import os
from typing import Any, AsyncIterator, Dict

import httpx
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
    requested_model = str(body.get("model") or "").strip()
    adapter_plan = ProviderAdapterRegistry().adapter_for(provider).plan_chat(str(body.get("model") or ""))
    body["model"] = adapter_plan.model
    body.setdefault("metadata", {})
    if isinstance(body["metadata"], dict):
        body["metadata"]["edgek_provider"] = provider
        body["metadata"]["edgek_provider_backend"] = adapter_plan.backend
        body["metadata"]["route_provider"] = adapter_plan.route_provider
        body["metadata"]["provider_config"] = adapter_plan.to_dict()
    if _should_direct_sse(body, adapter_plan.to_dict()):
        # LiteLLM adapter names include its internal transport prefix.  A
        # direct provider SSE call must receive the upstream model id instead.
        body["model"] = _direct_upstream_model(provider, requested_model, adapter_plan.to_dict())
        return StreamingResponse(
            _openai_compatible_sse(body, adapter_plan.to_dict()),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-EdgeK-Provider": adapter_plan.provider_id,
                "X-EdgeK-Stream-Path": "registry_openai_compatible_direct_sse",
            },
        )
    return await _run_prec(body, provider=adapter_plan.provider_id)


def _should_direct_sse(body: Dict[str, Any], adapter_plan: Dict[str, Any]) -> bool:
    enabled = os.environ.get("BEAST_PROXY_DIRECT_PROVIDER_SSE", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled or body.get("stream") is not True:
        return False
    backend = str(adapter_plan.get("backend") or "")
    provider_id = str(adapter_plan.get("provider_id") or "")
    # Cerebras is OpenAI-SSE compatible but is represented as a LiteLLM
    # provider for the managed sidecar.  When its credential is loaded in the
    # gateway, use the native-compatible stream instead of an unconfigured
    # sidecar that cannot see the gateway's secret vault.
    # Ollama exposes a standards-compatible /v1/chat/completions SSE endpoint
    # locally. Sending a local coding request through the non-streaming PREC
    # compatibility path makes the renderer wait for the whole completion and
    # is the source of multi-minute "no safe result" failures.
    if backend not in {"openai_compatible", "ollama"} and not (backend == "litellm" and provider_id == "cerebras"):
        return False
    env_names = adapter_plan.get("env") if isinstance(adapter_plan.get("env"), list) else []
    if backend == "ollama":
        return bool(adapter_plan.get("base_url"))
    if not env_names:
        return False
    return bool(os.environ.get(str(env_names[0])))


def _direct_upstream_model(provider_id: str, requested_model: str, adapter_plan: Dict[str, Any]) -> str:
    model = requested_model or str(adapter_plan.get("model") or "")
    for prefix in ("litellm/", f"{provider_id}/"):
        if model.startswith(prefix):
            model = model[len(prefix):]
    return model


async def _openai_compatible_sse(body: Dict[str, Any], adapter_plan: Dict[str, Any]) -> AsyncIterator[str]:
    provider_id = str(adapter_plan.get("provider_id") or "openai_compatible")
    env_names = adapter_plan.get("env") if isinstance(adapter_plan.get("env"), list) else []
    api_key = os.environ.get(str(env_names[0])) if env_names else ""
    base_url = str(adapter_plan.get("base_url") or "").rstrip("/")
    backend = str(adapter_plan.get("backend") or "")
    if (backend != "ollama" and not api_key) or not base_url:
        yield _sse_error(provider_id, "Provider credentials/base URL are not loaded for direct SSE.")
        return

    payload = dict(body)
    # Provider routing metadata is for the BEAST boundary only.  Do not leak
    # it across an OpenAI-compatible upstream contract; several providers
    # (including Cerebras) reject unknown top-level fields.
    payload.pop("metadata", None)
    payload["stream"] = True
    # `_registry_chat` has already normalized this to the upstream provider
    # model id.  Do not reapply the LiteLLM transport prefix here.
    payload["model"] = str(payload.get("model") or adapter_plan.get("model") or "")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    timeout = httpx.Timeout(connect=15.0, read=None, write=60.0, pool=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    body_bytes = await response.aread()
                    detail = body_bytes.decode("utf-8", errors="replace")[:1200]
                    yield _sse_error(provider_id, f"HTTP {response.status_code}: {detail}")
                    return
                async for line in response.aiter_lines():
                    if line is None:
                        continue
                    stripped = line.strip()
                    if not stripped:
                        yield "\n"
                        continue
                    if stripped.startswith("data:"):
                        yield f"{stripped}\n\n"
                    else:
                        yield f"data: {stripped}\n\n"
    except Exception as exc:
        yield _sse_error(provider_id, str(exc)[:1200])


def _sse_error(provider_id: str, message: str) -> str:
    payload = {
        "error": {
            "message": message,
            "type": "provider_stream_error",
            "provider": provider_id,
        }
    }
    return "data: " + json.dumps(payload, separators=(",", ":")) + "\n\n"


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
