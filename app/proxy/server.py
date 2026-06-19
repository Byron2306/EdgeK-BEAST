"""EdgeK BEAST proxy lane.

This router mounts provider-compatible HTTP surfaces under /proxy/* while keeping
BEAST governance in the provider adapters themselves.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.adapters.anthropic_adapter import anthropic_router
from app.adapters.gemini_adapter import gemini_router
from app.adapters.huggingface_adapter import _run_prec, huggingface_router
from app.adapters.openai_adapter import openai_router
from app.kernel.provider_adapters import ProviderAdapterRegistry
from app.kernel.provider_registry import ProviderRegistry

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
    return await _run_prec(body, provider=adapter_plan.provider_id)


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
