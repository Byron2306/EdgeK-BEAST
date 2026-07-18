from typing import Any, Dict, Optional
from app.kernel.registry.provider_registry import ProviderRegistry

class LocalComputeCascade:
    def __init__(
        self,
        reuse_gateway: Any,
        engine_fabric: Any,
        passport_policy: Any,
        telemetry_outbox: Any,
        litellm_gateway: Optional[Any] = None,
        quality_cascade: Optional[Any] = None,
        enterprise_manager: Optional[Any] = None,
        provider_registry: Optional[ProviderRegistry] = None,
    ):
        self.reuse_gateway = reuse_gateway
        self.engine_fabric = engine_fabric
        self.passport_policy = passport_policy
        self.telemetry_outbox = telemetry_outbox
        self.litellm_gateway = litellm_gateway
        self.quality_cascade = quality_cascade
        self.enterprise_manager = enterprise_manager
        self.provider_registry = provider_registry or ProviderRegistry()

    def run(self, request: Any, caller: Any):
        # 1. Authorize local task
        self.passport_policy.authorize(
            caller=caller,
            target="spiffe://beast.local/compute/cascade",
            action="run",
        )

        # 2. Try reuse
        decision = self.reuse_gateway.decide(request)
        if decision.action in {
            "reuse_answer",
            "reuse_semantic_credit",
            "reuse_kv_prefill",
        }:
            self.telemetry_outbox.enqueue_decision(decision)
            return {
                "route": decision.action,
                "source": decision.source,
                "response": decision.payload,
                "decision": decision.to_dict(),
            }

        # 3. Try local CPU
        selector = getattr(self.engine_fabric, "select_cpu_engine", None)
        engine_id = selector(
            request.task_class, request.model,
            int(request.parameters.get("max_latency_ms", 0)),
            int(request.parameters.get("context_tokens", 0)),
        ) if callable(selector) else (request.preferred_engine or "ollama")
        local = self.engine_fabric.generate(
            engine_id,
            model=request.model,
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            max_tokens=int(request.parameters.get("max_tokens", 512)),
        )

        # 4. Quality gate
        quality = (
            self.quality_cascade.evaluate(request, local)
            if self.quality_cascade
            else {"approved": True, "reason": "no_quality_cascade_configured"}
        )

        if quality.get("approved"):
            receipt = self.reuse_gateway.record_execution_response(
                request,
                local["response"],
                route="local_cpu",
                engine=local.get("engine_id", "ollama"),
                verified=True,
                avoided_tokens_estimate=int(local.get("total_tokens") or local.get("output_tokens") or 0),
                evidence={
                    "route": "local_cpu",
                    "engine": local.get("engine_id", "ollama"),
                    "quality": quality,
                    "latency_ms": local.get("latency_ms") or 0,
                    "usage": {
                        "total_tokens": local.get("total_tokens") or 0,
                        "prompt_tokens": local.get("prompt_tokens") or 0,
                        "output_tokens": local.get("output_tokens") or 0,
                    },
                },
            )
            self.telemetry_outbox.enqueue_execution(request, local, receipt)
            return {
                "route": "local_cpu",
                "response": local["response"],
                "execution": local,
                "receipt": receipt,
            }

        # 5. Escalate only with passport facts
        self.passport_policy.authorize(
            caller="spiffe://beast.local/runtime-governor",
            target="spiffe://beast.local/provider/cloud",
            action="call",
            facts={"quality_cascade": quality},
        )

        # 6. LiteLLM cloud fallback
        if self.litellm_gateway is None:
            raise RuntimeError("cloud fallback is not configured for the local compute cascade")
        cloud = self.litellm_gateway.complete(request)
        cloud_response = str(cloud.get("response") or "")
        cloud_receipt = self.reuse_gateway.record_execution_response(
            request,
            cloud_response,
            route="litellm_cloud",
            engine=str(cloud.get("engine_id") or cloud.get("model") or request.model),
            cost_usd=cloud.get("cost_usd"),
            verified=bool(cloud_response.strip()),
            avoided_tokens_estimate=int(cloud.get("total_tokens") or 0),
            evidence={
                "route": "litellm_cloud",
                "quality": quality,
                "latency_ms": cloud.get("latency_ms") or 0,
                "usage": {
                    "total_tokens": cloud.get("total_tokens") or 0,
                    "prompt_tokens": cloud.get("prompt_tokens") or 0,
                    "output_tokens": cloud.get("output_tokens") or 0,
                },
            },
        )
        self.telemetry_outbox.enqueue_execution(request, cloud, cloud_receipt)
        return {
            "route": "litellm_cloud",
            "response": cloud["response"],
            "execution": cloud,
            "receipt": cloud_receipt,
        }
