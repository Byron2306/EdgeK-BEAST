"""Single source of truth for BEAST provider lanes and backend classes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProviderRecord:
    provider_id: str
    enabled: bool
    backend: str
    env: List[str]
    proxy_path: str
    litellm_model_prefix: str = ""
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    risk_level: str = "medium"
    requires_approval: bool = False
    gateway_lane: str = "provider_explicit"
    managed_by: str = "beast"
    native_adapter: bool = False
    openai_compatible: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProviderRegistry:
    """Normalize provider policy into gateway/proxy/deployment records."""

    BACKENDS = {
        "native_anthropic",
        "native_gemini",
        "native_huggingface",
        "native_replicate",
        "openai_compatible",
        "litellm",
        "ollama",
    }

    DEFAULTS: Dict[str, Dict[str, Any]] = {
        "openai": {
            "backend": "openai_compatible",
            "env": ["OPENAI_API_KEY"],
            "proxy_path": "/proxy/openai",
            "litellm_model_prefix": "openai/",
            "default_model": "gpt-4o-mini",
            "native_adapter": True,
            "openai_compatible": True,
        },
        "codex": {
            "backend": "openai_compatible",
            "env": ["OPENAI_API_KEY"],
            "proxy_path": "/proxy/codex",
            "litellm_model_prefix": "openai/",
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-5-codex",
            "risk_level": "high",
            "openai_compatible": True,
            "metadata": {
                "coding_agent": True,
                "provider_alias_of": "openai",
            },
        },
        "anthropic": {
            "backend": "native_anthropic",
            "env": ["ANTHROPIC_API_KEY"],
            "proxy_path": "/proxy/anthropic",
            "litellm_model_prefix": "anthropic/",
            "native_adapter": True,
        },
        "google": {
            "backend": "native_gemini",
            "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "proxy_path": "/proxy/gemini",
            "litellm_model_prefix": "gemini/",
            "native_adapter": True,
        },
        "huggingface": {
            "backend": "native_huggingface",
            "env": ["HF_TOKEN", "HUGGINGFACE_API_KEY"],
            "proxy_path": "/proxy/huggingface",
            "litellm_model_prefix": "huggingface/",
            "native_adapter": True,
        },
        "tgi": {
            "backend": "openai_compatible",
            "env": ["TGI_BASE_URL", "HF_TOKEN"],
            "proxy_path": "/proxy/huggingface/tgi",
            "litellm_model_prefix": "openai/",
            "openai_compatible": True,
            "metadata": {"serving_engine": "tgi", "cpu_supported": True, "lifecycle": "maintenance_compatibility"},
        },
        "llama_cpp": {
            "backend": "openai_compatible", "env": ["LLAMA_CPP_BASE_URL"],
            "proxy_path": "/proxy/llama-cpp", "litellm_model_prefix": "openai/",
            "openai_compatible": True, "risk_level": "local",
            "metadata": {"serving_engine": "llama_cpp", "cpu_supported": True},
        },
        "vllm": {
            "backend": "openai_compatible", "env": ["VLLM_BASE_URL"],
            "proxy_path": "/proxy/vllm", "litellm_model_prefix": "openai/",
            "openai_compatible": True,
            "metadata": {"serving_engine": "vllm", "cpu_supported": False, "capability_gated": True},
        },
        "sglang": {
            "backend": "openai_compatible", "env": ["SGLANG_BASE_URL"],
            "proxy_path": "/proxy/sglang", "litellm_model_prefix": "openai/",
            "openai_compatible": True,
            "metadata": {"serving_engine": "sglang", "cpu_supported": False, "capability_gated": True},
        },
        "tensorrt_llm": {
            "backend": "openai_compatible", "env": ["TENSORRT_LLM_BASE_URL"],
            "proxy_path": "/proxy/tensorrt-llm", "litellm_model_prefix": "openai/",
            "openai_compatible": True,
            "metadata": {"serving_engine": "tensorrt_llm", "cpu_supported": False, "capability_gated": True},
        },
        "litellm": {
            "backend": "litellm",
            "env": ["LITELLM_API_KEY", "LITELLM_BASE_URL"],
            "proxy_path": "/proxy/huggingface/litellm",
            "litellm_model_prefix": "",
            "default_model": "ollama",
            "openai_compatible": True,
            "managed_by": "beast_managed_backend_lane",
        },
        "openrouter": {
            "backend": "litellm",
            "env": ["OPENROUTER_API_KEY"],
            "proxy_path": "/proxy/openrouter",
            "litellm_model_prefix": "openrouter/",
            "default_model": "openrouter/auto",
            "openai_compatible": True,
        },
        "groq": {
            "backend": "litellm",
            "env": ["GROQ_API_KEY"],
            "proxy_path": "/proxy/groq",
            "litellm_model_prefix": "groq/",
            "openai_compatible": True,
        },
        "cerebras": {
            "backend": "litellm",
            "env": ["CEREBRAS_API_KEY"],
            "proxy_path": "/proxy/cerebras",
            "litellm_model_prefix": "cerebras/",
            "openai_compatible": True,
        },
        "cohere": {
            "backend": "litellm",
            "env": ["COHERE_API_KEY"],
            "proxy_path": "/proxy/cohere",
            "litellm_model_prefix": "cohere/",
        },
        "deepinfra": {
            "backend": "litellm",
            "env": ["DEEPINFRA_API_KEY"],
            "proxy_path": "/proxy/deepinfra",
            "litellm_model_prefix": "deepinfra/",
            "openai_compatible": True,
        },
        "featherless": {
            "backend": "litellm",
            "env": ["FEATHERLESS_API_KEY"],
            "proxy_path": "/proxy/featherless",
            "litellm_model_prefix": "featherless_ai/",
            "openai_compatible": True,
        },
        "novita": {
            "backend": "litellm",
            "env": ["NOVITA_API_KEY"],
            "proxy_path": "/proxy/novita",
            "litellm_model_prefix": "novita/",
            "openai_compatible": True,
        },
        "xai": {
            "backend": "openai_compatible",
            "env": ["XAI_API_KEY"],
            "proxy_path": "/proxy/xai",
            "litellm_model_prefix": "openai/",
            "base_url": "https://api.x.ai/v1",
            "default_model": "grok-build-0.1",
            "openai_compatible": True,
            "metadata": {"coding_model": True, "model_alias": "grok-code-fast-1"},
        },
        "replicate": {
            "backend": "native_replicate",
            "env": ["REPLICATE_API_TOKEN", "REPLICATE_API_KEY"],
            "proxy_path": "/proxy/replicate",
            "default_model": "meta/meta-llama-3-70b-instruct",
            "openai_compatible": False,
            "metadata": {
                "native_prediction_api": True,
                "prediction_path": "/v1/models/{owner}/{model}/predictions",
            },
        },
        "nvidia_nim": {
            "backend": "openai_compatible",
            "env": ["NVIDIA_API_KEY"],
            "proxy_path": "/proxy/nvidia-nim",
            "litellm_model_prefix": "openai/",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "nvidia/nemotron-3-super-120b-a12b",
            "openai_compatible": True,
        },
        "local_nim": {
            "backend": "openai_compatible",
            "env": ["LOCAL_NIM_BASE_URL", "LOCAL_NIM_API_KEY"],
            "proxy_path": "/proxy/local-nim",
            "litellm_model_prefix": "openai/",
            "base_url": "http://127.0.0.1:8000/v1",
            "default_model": "local-nim-model",
            "risk_level": "local",
            "requires_approval": False,
            "openai_compatible": True,
            "metadata": {
                "nim": True,
                "local_endpoint_env": "LOCAL_NIM_BASE_URL",
            },
        },
        "ollama": {
            "backend": "ollama",
            "env": ["OLLAMA_BASE_URL"],
            "proxy_path": "/proxy/ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "default_model": "llama3.2:3b",
            "risk_level": "local",
            "requires_approval": False,
        },
        "fal": {"backend": "litellm", "env": ["FAL_KEY"], "proxy_path": "/proxy/fal", "litellm_model_prefix": "fal/"},
        "hyperbolic": {"backend": "litellm", "env": ["HYPERBOLIC_API_KEY"], "proxy_path": "/proxy/hyperbolic", "litellm_model_prefix": "hyperbolic/"},
        "nscale": {"backend": "litellm", "env": ["NSCALE_API_KEY"], "proxy_path": "/proxy/nscale", "litellm_model_prefix": "nscale/"},
        "ovhcloud": {"backend": "litellm", "env": ["OVHCLOUD_APP_KEY", "OVHCLOUD_APP_SECRET", "OVHCLOUD_CONSUMER_KEY"], "proxy_path": "/proxy/ovhcloud", "litellm_model_prefix": "ovhcloud/"},
    }

    def __init__(self, policies: Optional[Dict[str, Any]] = None):
        self.policies = policies or {}

    def records(self, include_disabled: bool = True) -> List[ProviderRecord]:
        providers = dict(self.DEFAULTS)
        for name, config in (self.policies.get("providers") or {}).items():
            providers[name] = {**providers.get(name, {}), **(config or {})}
        records = [self._record(name, config) for name, config in sorted(providers.items())]
        if not include_disabled:
            records = [record for record in records if record.enabled]
        return records

    def inventory(self) -> Dict[str, Any]:
        records = self.records(include_disabled=True)
        return {
            "beast_object_type": "provider_registry",
            "version": "1.0",
            "governance": {
                "beast_in_front_of_litellm": True,
                "litellm_role": "managed_backend_lane",
                "compatibility_lane": "/v1/* -> BEAST governance -> provider resolver",
                "provider_explicit_lane": "/proxy/<provider>/* -> BEAST governance",
                "mcp_governance_lane": "stdio beast mcp or HTTP /mcp/*",
            },
            "backend_classes": sorted(self.BACKENDS),
            "providers": [record.to_dict() for record in records],
        }

    def _record(self, name: str, config: Dict[str, Any]) -> ProviderRecord:
        env = config.get("env") or config.get("env_vars") or config.get("secret_envs") or []
        if isinstance(env, str):
            env = [env]
        backend = config.get("backend") or "litellm"
        if backend not in self.BACKENDS:
            backend = self._normalize_backend(str(backend))
        return ProviderRecord(
            provider_id=name,
            enabled=bool(config.get("enabled", True)),
            backend=backend,
            env=list(env or self.DEFAULTS.get(name, {}).get("env", [])),
            proxy_path=str(config.get("proxy_path") or self.DEFAULTS.get(name, {}).get("proxy_path") or f"/proxy/{name}"),
            litellm_model_prefix=str(config.get("litellm_model_prefix") or self.DEFAULTS.get(name, {}).get("litellm_model_prefix") or ""),
            base_url=config.get("base_url") or self.DEFAULTS.get(name, {}).get("base_url"),
            default_model=config.get("default_model") or config.get("model") or self.DEFAULTS.get(name, {}).get("default_model") or name,
            risk_level=str(config.get("risk_level") or self.DEFAULTS.get(name, {}).get("risk_level") or "medium"),
            requires_approval=bool(config.get("requires_approval", self.DEFAULTS.get(name, {}).get("requires_approval", False))),
            managed_by=str(config.get("managed_by") or self.DEFAULTS.get(name, {}).get("managed_by") or "beast"),
            native_adapter=bool(config.get("native_adapter", self.DEFAULTS.get(name, {}).get("native_adapter", False))),
            openai_compatible=bool(config.get("openai_compatible", self.DEFAULTS.get(name, {}).get("openai_compatible", backend in {"openai_compatible", "litellm"}))),
            metadata={
                **dict(self.DEFAULTS.get(name, {}).get("metadata") or {}),
                **dict(config.get("metadata") or {}),
                "policy": {key: value for key, value in config.items() if key not in {"env", "env_vars", "secret_envs", "metadata"}},
            },
        )

    def _normalize_backend(self, backend: str) -> str:
        if backend in {"anthropic"}:
            return "native_anthropic"
        if backend in {"google", "gemini"}:
            return "native_gemini"
        if backend in {"huggingface", "hf"}:
            return "native_huggingface"
        if backend in {"openai", "openai-compatible", "openai_compat"}:
            return "openai_compatible"
        if backend == "ollama":
            return "ollama"
        return "litellm"
