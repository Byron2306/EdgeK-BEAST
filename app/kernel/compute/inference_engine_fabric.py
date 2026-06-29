"""CPU-first inference execution inventory and health probes.

BEAST governs requests; external servers execute them.  This module does not
reimplement token schedulers or pretend unavailable GPU engines are active.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import httpx


@dataclass(frozen=True)
class InferenceEngineProfile:
    engine_id: str
    role: str
    endpoint: str = ""
    cpu_supported: bool = False
    configured: bool = False
    openai_compatible: bool = False
    capabilities: Dict[str, bool] = field(default_factory=dict)
    orchestrator: str = "standalone"
    claim_boundary: str = "capability declaration; live probe required"

    def to_dict(self) -> Dict[str, Any]:
        return {"beast_object_type": "inference_engine_profile", "version": "1.0", **asdict(self)}


ENGINE_CATALOG: Dict[str, Dict[str, Any]] = {
    "ollama": {
        "role": "cpu_local_default", "cpu_supported": True, "openai_compatible": True,
        "capabilities": {"streaming": True, "context_reuse": True, "continuous_batching": False},
    },
    "llama_cpp": {
        "role": "cpu_edge_advanced", "cpu_supported": True, "openai_compatible": True,
        "capabilities": {"streaming": True, "context_reuse": True, "kv_quantization": True},
    },
    "vllm": {
        "role": "gpu_throughput", "cpu_supported": False, "openai_compatible": True,
        "capabilities": {"streaming": True, "continuous_batching": True, "paged_attention": True, "prefix_cache": True, "tensor_parallelism": True, "distributed_tracing": True},
    },
    "sglang": {
        "role": "gpu_structured_serving", "cpu_supported": False, "openai_compatible": True,
        "capabilities": {"streaming": True, "continuous_batching": True, "prefix_cache": True, "tensor_parallelism": True},
    },
    "tgi": {
        "role": "compatibility_only", "cpu_supported": True, "openai_compatible": True,
        "capabilities": {"streaming": True, "continuous_batching": True, "flash_attention": True, "paged_attention": True, "tensor_parallelism": True, "distributed_tracing": True},
    },
    "tensorrt_llm": {
        "role": "nvidia_optimized", "cpu_supported": False, "openai_compatible": True,
        "capabilities": {"streaming": True, "continuous_batching": True, "tensor_parallelism": True},
    },
}

ORCHESTRATOR_CATALOG: Dict[str, Dict[str, Any]] = {
    "standalone": {"cpu_supported": True, "role": "single_node"},
    "ray_serve": {"cpu_supported": True, "role": "distributed_serving"},
    "nvidia_dynamo": {"cpu_supported": False, "role": "gpu_disaggregated_serving"},
    "llm_d": {"cpu_supported": False, "role": "kubernetes_inference_routing"},
}

CACHE_BACKEND_CATALOG: Dict[str, Dict[str, Any]] = {
    "local_semantic_cache": {"cpu_supported": True, "configured": True, "role": "sqlite_verified_semantic_answer_reuse"},
    "local_prefix_kv_store": {"cpu_supported": True, "configured": True, "role": "beast_kv_transport_compatibility_guard"},
    "local_execution_gateway": {"cpu_supported": True, "configured": True, "role": "ollama_llama_cpp_cpu_first_routing"},
    "local_trace_ledger": {"cpu_supported": True, "configured": True, "role": "sqlite_jsonl_trace_observation_cost_ledger"},
    "local_route_optimizer": {"cpu_supported": True, "configured": True, "role": "sqlite_route_feedback_optimizer"},
    "local_eval_gate": {"cpu_supported": True, "configured": True, "role": "json_yaml_assertion_promotion_gate"},
    "compute_forge": {"cpu_supported": True, "configured": True, "role": "idle_cpu_inference_preparation"},
}


class LocalCPUFabric:
    engines = ["ollama", "llama_cpp"]

class AcceleratorFabric:
    engines = ["vllm", "sglang", "tgi", "tensorrt_llm"]

class CloudGatewayFabric:
    engines = ["litellm"]


class InferenceEngineFabric:
    ENV_ENDPOINTS = {
        "ollama": ("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "llama_cpp": ("LLAMA_CPP_BASE_URL", ""),
        "vllm": ("VLLM_BASE_URL", ""),
        "sglang": ("SGLANG_BASE_URL", ""),
        "tgi": ("TGI_BASE_URL", ""),
        "tensorrt_llm": ("TENSORRT_LLM_BASE_URL", ""),
        "litellm": ("BEAST_LITELLM_BASE_URL", "http://127.0.0.1:4000"),
    }

    def select_cpu_engine(self, task_class: str, model_hint: str, max_latency_ms: int, context_tokens: int) -> str:
        # TODO: Implement sophisticated selection logic based on requirements
        if "llama" in model_hint.lower():
            return "llama_cpp"
        return "ollama"

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self.client = client or httpx.Client()

    def profiles(self) -> List[InferenceEngineProfile]:
        profiles = []
        for engine_id, spec in ENGINE_CATALOG.items():
            env_name, default = self.ENV_ENDPOINTS[engine_id]
            endpoint = os.environ.get(env_name, default).rstrip("/")
            configured = bool(endpoint) and (engine_id == "ollama" or env_name in os.environ)
            profiles.append(InferenceEngineProfile(
                engine_id=engine_id,
                role=spec["role"],
                endpoint=endpoint,
                cpu_supported=bool(spec["cpu_supported"]),
                configured=configured,
                openai_compatible=bool(spec["openai_compatible"]),
                capabilities=dict(spec["capabilities"]),
            ))
        return profiles

    def cpu_candidates(self) -> List[InferenceEngineProfile]:
        return [item for item in self.profiles() if item.cpu_supported and item.configured]

    def probe(self, engine_id: str, *, timeout_seconds: float = 1.5) -> Dict[str, Any]:
        profile = next((item for item in self.profiles() if item.engine_id == engine_id), None)
        if profile is None:
            return {"engine_id": engine_id, "ready": False, "reason": "unknown_engine"}
        if not profile.configured:
            return {**profile.to_dict(), "ready": False, "reason": "endpoint_not_configured"}
        path = "/api/tags" if engine_id == "ollama" else "/v1/models"
        started = time.perf_counter()
        try:
            response = self.client.get(profile.endpoint + path, timeout=timeout_seconds)
            response.raise_for_status()
            body = response.json()
            return {
                **profile.to_dict(), "ready": True, "reason": "live_probe_passed",
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "model_count": len(body.get("models") or body.get("data") or []),
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                **profile.to_dict(), "ready": False, "reason": type(exc).__name__,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }

    def generate(
        self,
        engine_id: str,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 128,
        timeout_seconds: float = 60.0,
    ) -> Dict[str, Any]:
        """Execute against a configured CPU-capable server using its real HTTP API."""
        profile = next((item for item in self.profiles() if item.engine_id == engine_id), None)
        if profile is None:
            raise ValueError("unknown inference engine")
        if not profile.cpu_supported:
            raise ValueError(f"{engine_id} is unavailable under the CPU-only host policy")
        if not profile.configured:
            raise ValueError(f"{engine_id} endpoint is not configured")
        started = time.perf_counter()
        if engine_id == "ollama":
            response = self.client.post(
                profile.endpoint + "/api/generate",
                json={
                    "model": model, "prompt": prompt, "system": system_prompt,
                    "stream": False, "options": {"num_predict": max(1, int(max_tokens))},
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            text = str(body.get("response") or "")
            prompt_tokens = int(body.get("prompt_eval_count") or 0)
            output_tokens = int(body.get("eval_count") or 0)
        else:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.post(
                profile.endpoint + "/v1/chat/completions",
                json={"model": model, "messages": messages, "max_tokens": max(1, int(max_tokens)), "stream": False},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") or []
            text = str(((choices[0] if choices else {}).get("message") or {}).get("content") or "")
            usage = body.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        return {
            "beast_object_type": "inference_engine_execution", "version": "1.0",
            "engine_id": engine_id, "model": model, "status": "succeeded",
            "response": text, "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "host_policy": "cpu_first_capability_gated",
        }
    def inventory(self, *, probe: bool = False) -> Dict[str, Any]:
        engines = [self.probe(item.engine_id) if probe else item.to_dict() for item in self.profiles()]
        return {
            "beast_object_type": "inference_engine_fabric",
            "version": "1.0",
            "host_policy": "cpu_first_capability_gated",
            "engines": engines,
            "orchestrators": [
                {"orchestrator_id": key, **value} for key, value in ORCHESTRATOR_CATALOG.items()
            ],
            "cache_backends": [
                {"cache_backend_id": key, **value} for key, value in CACHE_BACKEND_CATALOG.items()
            ],
            "selection_rule": "governor selects; orchestrator schedules; engine executes",
        }
