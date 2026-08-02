"""Provider adapter contracts backed by the provider registry."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.kernel.local.ollama_config import ollama_base_url, ollama_model
from app.kernel.compute.ollama_cpu_profile import request_options

from app.kernel.registry.provider_registry import ProviderRecord, ProviderRegistry


@dataclass
class ProviderAdapterPlan:
    provider_id: str
    backend: str
    adapter_class: str
    route_provider: str
    model: str
    env: List[str]
    base_url: Optional[str]
    proxy_path: str
    governed_by_beast: bool = True
    request_policy: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProviderAdapter:
    adapter_class = "provider_adapter"

    def __init__(self, record: ProviderRecord):
        self.record = record

    def _requested_model(self, requested_model: str = "") -> str:
        requested = str(requested_model or "").strip()
        return "" if requested in {"beast-auto", "beast_auto", "auto"} else requested

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        requested_model = self._requested_model(requested_model)
        return ProviderAdapterPlan(
            provider_id=self.record.provider_id,
            backend=self.record.backend,
            adapter_class=self.adapter_class,
            route_provider=self.record.backend,
            model=requested_model or self.record.default_model or self.record.provider_id,
            env=list(self.record.env),
            base_url=self.record.base_url,
            proxy_path=self.record.proxy_path,
        )


class NativeAnthropicAdapter(ProviderAdapter):
    adapter_class = "native_anthropic"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        plan.route_provider = "anthropic"
        return plan


class NativeGeminiAdapter(ProviderAdapter):
    adapter_class = "native_gemini"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        plan.route_provider = "gemini"
        return plan


class NativeHuggingFaceAdapter(ProviderAdapter):
    adapter_class = "native_huggingface"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        plan.route_provider = "huggingface"
        model = plan.model
        plan.model = model if model.startswith(("hf/", "huggingface/")) else f"hf/{model}"
        return plan


class NativeReplicateAdapter(ProviderAdapter):
    adapter_class = "native_replicate"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        plan.route_provider = "replicate_prediction"
        return plan


class OpenAICompatibleAdapter(ProviderAdapter):
    adapter_class = "openai_compatible"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        plan.route_provider = "openai_compatible"
        return plan


class LiteLLMAdapter(ProviderAdapter):
    adapter_class = "litellm"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        requested = self._requested_model(requested_model)
        model = requested or self.record.default_model or self.record.provider_id
        prefix = self.record.litellm_model_prefix or ""
        # Requested models are public LiteLLM proxy aliases (for example
        # "ollama"). Do not force the registry's upstream provider prefix onto
        # them, or the sidecar sees invalid names like "openai/beast-auto".
        if not requested and prefix and not model.startswith(prefix):
            model = f"{prefix}{model}"
        plan.model = model if model.startswith("litellm/") else f"litellm/{model}"
        plan.route_provider = "litellm"
        return plan


class OllamaAdapter(ProviderAdapter):
    adapter_class = "ollama"

    def plan_chat(self, requested_model: str = "") -> ProviderAdapterPlan:
        plan = super().plan_chat(requested_model)
        plan.route_provider = "ollama"
        requested = self._requested_model(requested_model)
        # A concrete policy model remains authoritative, while the built-in
        # default follows the live workstation override.
        plan.model = (requested or ollama_model()) if plan.model == "qwen2.5:0.5b" else (requested or plan.model)
        plan.base_url = ollama_base_url(plan.base_url or "")
        plan.request_policy = {
            "engine": "ollama_native",
            "api": "/api/generate",
            "stream": False,
            "num_ctx": int(os.environ.get("BEAST_OLLAMA_NUM_CTX", "2048")),
            "num_predict": int(os.environ.get("BEAST_OLLAMA_NUM_PREDICT", "48")),
            **request_options(),
            "keep_alive": os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "5m"),
            "portable_kv": False,
            "prompt_cache": "runner_local",
        }
        return plan


class ProviderAdapterRegistry:
    ADAPTERS = {
        "native_anthropic": NativeAnthropicAdapter,
        "native_gemini": NativeGeminiAdapter,
        "native_huggingface": NativeHuggingFaceAdapter,
        "native_replicate": NativeReplicateAdapter,
        "openai_compatible": OpenAICompatibleAdapter,
        "litellm": LiteLLMAdapter,
        "ollama": OllamaAdapter,
    }

    def __init__(self, policies: Optional[Dict[str, Any]] = None):
        self.provider_registry = ProviderRegistry(policies)

    def records(self) -> List[ProviderRecord]:
        return self.provider_registry.records(include_disabled=False)

    def adapter_for(self, provider_id: str) -> ProviderAdapter:
        for record in self.records():
            if record.provider_id == provider_id:
                adapter_cls = self.ADAPTERS.get(record.backend, ProviderAdapter)
                return adapter_cls(record)
        raise KeyError(provider_id)

    def inventory(self) -> Dict[str, Any]:
        adapters = []
        for record in self.records():
            adapters.append(self.ADAPTERS.get(record.backend, ProviderAdapter)(record).plan_chat().to_dict())
        return {
            "beast_object_type": "provider_adapter_inventory",
            "version": "1.0",
            "count": len(adapters),
            "adapters": adapters,
        }
