"""
EdgeK BEAST Gateway - Execute Phase of PREC Cycle
Responsible for routing the governed request to the appropriate provider/model
"""

import os
import json
import hashlib
import httpx
import asyncio
from typing import Awaitable, Callable, Dict, Any, Optional
from dataclasses import asdict
import logging
from pathlib import Path

from app.kernel.compute.perceive import EdgeKIR, ProviderType
from app.kernel.governance.reason import GovernanceDecision, GovernanceResult
from app.kernel.adapters.providers import ProviderFactory, OpenAIProvider, AnthropicProvider
from app.kernel.governance.runtime import runtime_governor
from app.kernel.compute.compute_plane import get_compute_plane
from app.kernel.compute.streaming_interceptor import StreamingComputeInterceptor, StreamingInterceptionEngine
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.compute.adaptive_dispatcher import AdaptiveDispatcher
from app.kernel.compute.crystal_runtime_boundary import CrystalRuntimeBoundary
from app.kernel.compute.integration_harness import BeastHarnessRequest
from app.kernel.registry.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)

compute_plane = get_compute_plane()
compute_interceptor = compute_plane
streaming_compute_interceptor = compute_plane.streaming_interceptor


class Executor:
    """Executes the governed request by routing to appropriate provider"""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=120.0)
        self._providers = {}
        self.dispatcher = AdaptiveDispatcher()
        self.crystal_runtime_boundary = CrystalRuntimeBoundary()
        self.integration_harness = None

    def bind_runtime_services(self, *, crystal_gateway=None, integration_harness=None) -> None:
        """Bind the process-wide governed services used by live gateway routes.

        The executor is imported before the application composition root.  This
        late binding makes provider execution use the same durable reuse,
        KV-transport, trace, and promotion services exposed by the gateway,
        instead of silently creating a parallel crystal-runtime state root.
        """
        if crystal_gateway is not None:
            self.crystal_runtime_boundary.gateway = crystal_gateway
        if integration_harness is not None:
            self.integration_harness = integration_harness
    
    def _get_provider(self, provider_type: ProviderType):
        """Get or create a provider instance"""
        if provider_type not in self._providers:
            self._providers[provider_type] = ProviderFactory.create(provider_type)
        return self._providers[provider_type]
    
    async def execute(self, ir: EdgeKIR, governance_result: GovernanceResult) -> Dict[str, Any]:
        """
        Execute the request by routing to the appropriate provider
        
        Args:
            ir: The EdgeK Internal Representation (possibly modified by governance)
            governance_result: Result from the reasoning phase
            
        Returns:
            Dict[str, Any]: The provider's response
        """
        # If governance denied the request, return an error response
        if governance_result.decision == GovernanceDecision.DENY:
            return self._create_error_response(
                "REQUEST_DENIED", 
                governance_result.reason,
                status_code=403
            )
        
        # Determine the target provider
        provider_type = self._determine_provider_type(ir)
        
        # New Adaptive Routing Hook
        adaptive_route = await self.dispatcher.route(ir)
        if adaptive_route:
            logger.info(f"Adaptive routing selected: {adaptive_route['model_ref']}")
            ir.metadata["adaptive_route"] = adaptive_route
            if adaptive_route.get("execution_mode") == "local_specialist_adapter":
                model_ref = str(adaptive_route.get("model_ref") or "")
                if not model_ref.startswith("ollama://"):
                    return self._create_error_response(
                        "ADAPTIVE_ROUTE_REJECTED",
                        "Adaptive specialist route is not an approved local Ollama target.",
                        status_code=409,
                    )
                ir.model = model_ref.removeprefix("ollama://")
                ir.metadata["adaptive_route_executed"] = True
                ir.metadata["provider_candidates"] = [{
                    "provider": "ollama", "model": ir.model,
                    "local": True, "confidence": adaptive_route.get("confidence_score", 0.0),
                }]
                provider_type = ProviderType.OLLAMA

        provider_name = "google" if provider_type == ProviderType.GEMINI else provider_type.value
        compute = compute_interceptor.begin(ir, provider_name)
        compute_route = compute_interceptor.execution_route(compute)

        if compute_route == "deterministic":
            response = compute_interceptor.deterministic_response(compute)
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                status="deterministic_succeeded",
                provider_execution_requested=False,
                behavior_preserved=True,
            )
            response["edgek_compute"] = self._compute_summary(compute, receipt)
            response["edgek_runtime"] = {
                "attempt_id": "",
                "provider": "deterministic_transform",
                "timeout_seconds": 0,
            }
            return response
        if compute_route == "reuse":
            response = compute_interceptor.reuse_response(compute)
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                status="reuse_succeeded",
                provider_execution_requested=False,
                behavior_preserved=True,
            )
            response["edgek_compute"] = self._compute_summary(compute, receipt)
            response["edgek_runtime"] = {
                "attempt_id": "",
                "provider": "verified_reuse",
                "timeout_seconds": 0,
            }
            return response
        if compute_route == "approval":
            receipt = compute_interceptor.complete(
                compute,
                status="approval_required",
                provider_execution_requested=False,
                error_type="approval_required",
            )
            return self._create_error_response(
                "APPROVAL_REQUIRED",
                compute.gate.reason,
                status_code=409,
                extra={"compute": self._compute_summary(compute, receipt)},
            )
        if compute_route == "escalate":
            receipt = compute_interceptor.complete(
                compute,
                status="compute_escalated",
                provider_execution_requested=False,
                error_type="compute_escalated",
            )
            return self._create_error_response(
                "COMPUTE_ESCALATED",
                compute.gate.reason,
                status_code=409,
                extra={"compute": self._compute_summary(compute, receipt)},
            )
        if compute_route == "local":
            response = compute_interceptor.local_inference_response(compute)
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                status="local_inference_selected",
                provider_execution_requested=False,
                behavior_preserved=None,
            )
            response["edgek_compute"] = self._compute_summary(compute, receipt)
            response["edgek_runtime"] = {
                "attempt_id": "",
                "provider": "local_inference",
                "timeout_seconds": 0,
            }
            return response
        durable_replay = self._durable_inference_replay(ir)
        if durable_replay is not None:
            response = {
                "object": "beast.durable_inference_replay",
                "replay": durable_replay.to_dict(),
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            if durable_replay.replay_type == "cached_answer":
                response["text"] = durable_replay.payload.get("response", "")
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                status="durable_replay_succeeded",
                provider_execution_requested=False,
                behavior_preserved=True,
            )
            response["edgek_compute"] = self._compute_summary(compute, receipt)
            response["edgek_runtime"] = {
                "attempt_id": "",
                "provider": "durable_inference_storage",
                "timeout_seconds": 0,
            }
            return response
        crystal_boundary = self.crystal_runtime_boundary.decide_for_ir(ir, provider_name)
        crystal_request = crystal_boundary.get("request")
        crystal_decision = crystal_boundary.get("decision")
        if crystal_boundary.get("enabled") and not crystal_boundary.get("should_execute_provider") and crystal_decision is not None:
            response = self.crystal_runtime_boundary.response_from_decision(ir, crystal_decision)
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                status="crystal_runtime_reuse_succeeded",
                provider_execution_requested=False,
                behavior_preserved=True,
            )
            harness_receipt = self.crystal_runtime_boundary.harness_reuse_receipt(
                request=crystal_request,
                decision=crystal_decision,
                proof_local=crystal_boundary.get("proof_local") or {},
                staleness=crystal_boundary.get("staleness") or {},
                compute_receipt=receipt.to_dict() if hasattr(receipt, "to_dict") else asdict(receipt),
            )
            response["edgek_compute"] = self._compute_summary(compute, receipt)
            response.setdefault("edgek_crystal_runtime", {})
            response["edgek_crystal_runtime"]["proof_local"] = crystal_boundary.get("proof_local") or {}
            response["edgek_crystal_runtime"]["harness_receipt"] = harness_receipt
            response["edgek_runtime"] = {
                "attempt_id": "",
                "provider": "beast_crystal_runtime",
                "timeout_seconds": 0,
                "crystal_boundary": {
                    "reason": crystal_boundary.get("reason"),
                    "staleness": crystal_boundary.get("staleness") or {},
                    "proof_local": crystal_boundary.get("proof_local") or {},
                },
            }
            return response
        if self.integration_harness is not None and crystal_request is not None:
            harness_receipt = self.integration_harness.run(
                BeastHarnessRequest(
                    prompt=crystal_request.prompt,
                    model=crystal_request.model,
                    parameters=crystal_request.parameters,
                    provider=crystal_request.provider or provider_name,
                    task_class=crystal_request.task_class,
                    repo_fingerprint=crystal_request.repo_fingerprint,
                    policy_version=crystal_request.policy_version,
                    system_prompt=crystal_request.system_prompt,
                    tokenizer=crystal_request.tokenizer,
                    prompt_prefix=crystal_request.prompt_prefix,
                    preferred_engine=crystal_request.preferred_engine,
                    metadata={
                        **(crystal_request.metadata or {}),
                        "trace_id": crystal_request.metadata.get("trace_id") or compute.plan.plan_id,
                        "compute_plan_id": compute.plan.plan_id,
                        "compute_gate_id": compute.gate.gate_id,
                    },
                )
            )
            provider_result = harness_receipt.get("provider_result") if isinstance(harness_receipt.get("provider_result"), dict) else {}
            text = str(provider_result.get("response") or "")
            response = self._openai_text_response(
                ir,
                text,
                provider="beast_integration_harness",
                extra={"edgek_integration_harness_receipt": harness_receipt},
            )
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                status="integration_harness_succeeded" if harness_receipt.get("verification", {}).get("verified") else "integration_harness_unverified",
                provider_execution_requested=bool(provider_result.get("called")),
                behavior_preserved=bool(harness_receipt.get("verification", {}).get("verified")),
            )
            response["edgek_compute"] = self._compute_summary(compute, receipt)
            response["edgek_runtime"] = {
                "attempt_id": "",
                "provider": "beast_integration_harness",
                "timeout_seconds": 0,
                "crystal_boundary": {
                    "reason": crystal_boundary.get("reason"),
                    "staleness": crystal_boundary.get("staleness") or {},
                    "proof_local": crystal_boundary.get("proof_local") or {},
                },
            }
            return response
        admission = runtime_governor.begin_execution(
            provider=provider_name,
            model=ir.model,
            session_id=ir.metadata.get("session_id", "default"),
            metadata={
                "stream": ir.stream,
                "compute_plan_id": compute.plan.plan_id,
                "compute_gate_id": compute.gate.gate_id,
                "compute_mode": compute.plan.mode,
                "compute_recommended_rung": compute.gate.recommended_rung,
            }
        )
        if not admission.allowed:
            receipt = compute_interceptor.complete(
                compute,
                runtime_attempt_id=admission.attempt_id,
                status="runtime_rejected",
                provider_execution_requested=False,
                error_type="runtime_admission",
            )
            return self._create_error_response(
                "RUNTIME_DEFERRED",
                admission.reason,
                status_code=429 if admission.retry_after_seconds else 503,
                extra={
                    "attempt_id": admission.attempt_id,
                    "retry_after_seconds": admission.retry_after_seconds,
                    "compute": self._compute_summary(compute, receipt),
                }
            )

        try:
            if self._should_intercept_stream(ir):
                response = await asyncio.wait_for(
                    self._execute_intercepted_stream(provider_type, ir, compute),
                    timeout=admission.timeout_seconds,
                )
                success = "error" not in response
                runtime_governor.complete_execution(
                    attempt_id=admission.attempt_id,
                    provider=provider_name,
                    success=success,
                    error_type=response.get("error", {}).get("type", "") if not success else "",
                    error_message=response.get("error", {}).get("message", "") if not success else "",
                )
                stream_report = response.pop("_edgek_stream_interception_report", None)
                receipt = compute_interceptor.complete(
                    compute,
                    response=response,
                    runtime_attempt_id=admission.attempt_id,
                    status="stream_intercepted" if success else "stream_interception_error",
                    provider_execution_requested=True,
                    error_type=response.get("error", {}).get("type", "") if not success else "",
                    stream_report=stream_report,
                )
                if isinstance(response, dict):
                    response.setdefault("edgek_runtime", {
                        "attempt_id": admission.attempt_id,
                        "provider": provider_name,
                        "timeout_seconds": admission.timeout_seconds,
                    })
                    response.setdefault("edgek_compute", self._compute_summary(compute, receipt))
                    crystal_record = None
                    if success and crystal_request is not None:
                        crystal_record = self.crystal_runtime_boundary.record_provider_result(
                            crystal_request,
                            response,
                            route=provider_name,
                            engine=ir.model,
                            verified=True,
                            evidence={
                                "runtime_attempt_id": admission.attempt_id,
                                "compute_plan_id": compute.plan.plan_id,
                                "compute_gate_id": compute.gate.gate_id,
                                "stream_interception": stream_report.to_dict() if stream_report is not None else {},
                            },
                        )
                    if crystal_record is not None:
                        response.setdefault("edgek_crystal_record", crystal_record)
                return response
            response = await asyncio.wait_for(
                self._route_to_provider_with_live_relay(provider_type, ir),
                timeout=admission.timeout_seconds,
            )
            success = "error" not in response
            runtime_governor.complete_execution(
                attempt_id=admission.attempt_id,
                provider=provider_name,
                success=success,
                error_type=response.get("error", {}).get("type", "") if not success else "",
                error_message=response.get("error", {}).get("message", "") if not success else "",
            )
            receipt = compute_interceptor.complete(
                compute,
                response=response,
                runtime_attempt_id=admission.attempt_id,
                status="succeeded" if success else "provider_error",
                provider_execution_requested=True,
                error_type=response.get("error", {}).get("type", "") if not success else "",
            )
            crystal_record = None
            if success and crystal_request is not None:
                crystal_record = self.crystal_runtime_boundary.record_provider_result(
                    crystal_request,
                    response,
                    route=provider_name,
                    engine=ir.model,
                    verified=True,
                    evidence={
                        "runtime_attempt_id": admission.attempt_id,
                        "compute_plan_id": compute.plan.plan_id,
                        "compute_gate_id": compute.gate.gate_id,
                    },
                )
            if isinstance(response, dict):
                response.setdefault("edgek_runtime", {
                    "attempt_id": admission.attempt_id,
                    "provider": provider_name,
                    "timeout_seconds": admission.timeout_seconds,
                })
                response.setdefault("edgek_compute", self._compute_summary(compute, receipt))
                if crystal_record is not None:
                    response.setdefault("edgek_crystal_record", crystal_record)
            return response
        except asyncio.TimeoutError:
            runtime_governor.complete_execution(
                attempt_id=admission.attempt_id,
                provider=provider_name,
                success=False,
                error_type="timeout",
                error_message=f"Provider execution timed out after {admission.timeout_seconds}s",
            )
            receipt = compute_interceptor.complete(
                compute,
                runtime_attempt_id=admission.attempt_id,
                status="timeout",
                provider_execution_requested=True,
                error_type="timeout",
            )
            return self._create_error_response(
                "RUNTIME_TIMEOUT",
                f"Provider execution timed out after {admission.timeout_seconds}s",
                status_code=504,
                extra={"attempt_id": admission.attempt_id, "compute": self._compute_summary(compute, receipt)}
            )
        except Exception as e:
            runtime_governor.complete_execution(
                attempt_id=admission.attempt_id,
                provider=provider_name,
                success=False,
                error_type="runtime_exception",
                error_message=str(e),
            )
            receipt = compute_interceptor.complete(
                compute,
                runtime_attempt_id=admission.attempt_id,
                status="runtime_exception",
                provider_execution_requested=True,
                error_type="runtime_exception",
            )
            return self._create_error_response(
                "RUNTIME_ERROR",
                str(e),
                status_code=500,
                extra={"attempt_id": admission.attempt_id, "compute": self._compute_summary(compute, receipt)}
            )

    @staticmethod
    def _compute_summary(compute, receipt) -> Dict[str, Any]:
        return {
            "mode": compute.plan.mode,
            "enforced": compute.gate.enforced,
            "plan_id": compute.plan.plan_id,
            "gate_id": compute.gate.gate_id,
            "receipt_id": receipt.receipt_id,
            "selected_rung": compute.gate.selected_rung,
            "recommended_rung": compute.gate.recommended_rung,
            "predicted_avoidable_work": compute.gate.predicted_avoidable_work,
            "deterministic_shadow": {
                "attempts": receipt.deterministic_shadow_attempts,
                "verified": receipt.deterministic_shadow_verified,
                "calibrated": receipt.deterministic_shadow_calibrated,
                "agreements": receipt.deterministic_shadow_agreements,
            },
            "verified_reuse": {
                "decision": (compute.verified_reuse_decision or {}).get("decision"),
                "matched_capability": (compute.verified_reuse_decision or {}).get("matched_capability"),
                "confidence": (compute.verified_reuse_decision or {}).get("confidence"),
            },
            "adaptive_routing": {
                "decision": getattr(compute.adaptive_routing, "decision", None),
                "route": getattr(compute.adaptive_routing, "route", None),
                "requires_approval": getattr(compute.adaptive_routing, "requires_approval", None),
                "violations": getattr(getattr(compute.adaptive_routing, "budget_check", None), "violations", None),
            },
            "streaming": {
                "early_stopped": receipt.early_stopped,
                "stop_reason": receipt.stream_stop_reason,
                "tokens_saved": receipt.stream_tokens_saved,
                "repair_action": receipt.stream_repair_action,
                "upstream_cancel_requested": receipt.upstream_cancel_requested,
            },
        }

    def _should_intercept_stream(self, ir: EdgeKIR) -> bool:
        metadata = ir.metadata or {}
        # Never early-cancel structured source-edit output.  This is a
        # defence in depth guard for callers other than the proxy registry.
        # Action IR is validated only after its complete JSON object arrives;
        # a partial object is worse than no result because it can contain a
        # stale anchor or an incomplete replacement.
        if metadata.get("edgek_action_ir_required") is True:
            return False
        return bool(ir.stream and metadata.get("stream_interception_enabled") is True)

    def _durable_inference_replay(self, ir: EdgeKIR):
        metadata = ir.metadata or {}
        if metadata.get("durable_inference_replay_enabled") is not True:
            return None
        storage_path = metadata.get("durable_inference_storage_path")
        storage = DurableInferenceStorage(Path(storage_path)) if storage_path else DurableInferenceStorage()
        parameters = metadata.get("durable_parameters")
        if parameters is None:
            parameters = {
                "temperature": getattr(ir, "temperature", None),
                "max_tokens": getattr(ir, "max_tokens", None),
            }
        prompt_hash = metadata.get("prompt_hash") or metadata.get("durable_prompt_hash")
        if not prompt_hash:
            prompt_hash = "sha256:" + hashlib.sha256(
                json.dumps(getattr(ir, "messages", []) or [], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        replay = storage.runtime_lookup_replay(
            task_class=metadata.get("task_class"),
            repo_fingerprint=metadata.get("repo_fingerprint"),
            prompt_hash=prompt_hash,
            model=getattr(ir, "model", None),
            parameters=parameters if isinstance(parameters, dict) else {},
            tokenizer=metadata.get("tokenizer"),
            prompt_prefix=metadata.get("prompt_prefix"),
            system_prompt=metadata.get("system_prompt"),
        )
        measured = metadata.get("measured_reuse_tokens_saved")
        if replay is not None and measured is not None:
            storage.replay_credit(replay.credit_id, measured_tokens_saved=self._optional_int(measured) or 0)
        return replay

    async def _execute_intercepted_stream(self, provider_type: ProviderType, ir: EdgeKIR, compute) -> Dict[str, Any]:
        metadata = ir.metadata or {}
        schema = metadata.get("stream_schema_contract") or metadata.get("governed_schema")
        max_tokens = self._optional_int(metadata.get("stream_max_output_tokens")) or ir.max_tokens
        baseline = self._optional_int(metadata.get("stream_baseline_output_tokens")) or ir.max_tokens
        interceptor = streaming_compute_interceptor
        if schema:
            interceptor = compute_plane.streaming_for(max_tokens=max_tokens or 4096, schema=schema)
        provider_stream = self._route_to_provider_stream(provider_type, ir)
        report = await interceptor.intercept_provider_stream(
            provider_stream,
            max_tokens=max_tokens,
            baseline_output_tokens=baseline,
            compute_gate=compute.gate,
        )
        content = "".join(report.emitted_chunks)
        response = self._openai_text_response(
            ir,
            content,
            provider="stream_interception",
            extra={
                "edgek_stream_interception": report.to_dict(),
                "_edgek_stream_interception_report": report,
            },
        )
        response["usage"]["completion_tokens"] = report.savings.emitted_tokens
        response["usage"]["total_tokens"] = response["usage"]["prompt_tokens"] + report.savings.emitted_tokens
        response["choices"][0]["finish_reason"] = report.final_state.stop_reason or "stop"
        return response

    async def _route_to_provider_stream(self, provider_type: ProviderType, ir: EdgeKIR):
        if provider_type == ProviderType.OPENAI:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key or api_key.startswith("sk-test") or "test" in api_key.lower():
                async for item in self._simulate_openai_stream(ir):
                    yield item
                return
            provider = OpenAIProvider(api_key=api_key)
            try:
                async for item in provider.complete_stream(ir):
                    yield item
            finally:
                await provider.close()
            return
        if provider_type == ProviderType.OPENAI_COMPATIBLE:
            config = self._openai_compatible_config(ir)
            provider_label = str(config.get("provider_id") or "openai_compatible")
            env_names = config.get("env") or []
            api_key_env = str(env_names[0] if env_names else f"{provider_label.upper()}_API_KEY")
            api_key = os.environ.get(api_key_env, "")
            if not api_key:
                # Preserve the selected provider in the refusal/simulation
                # response; never silently claim that an OpenAI key is needed
                # for a NIM route.
                text = self._simulate_openai_compatible_response(ir, provider_label)["choices"][0]["message"]["content"]
                for chunk in self._stream_text_chunks(text):
                    yield {"choices": [{"delta": {"content": chunk}}]}
                yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
                return
            provider = OpenAIProvider(
                api_key=api_key,
                base_url=str(config.get("base_url") or "").rstrip("/"),
            )
            try:
                async for item in provider.complete_stream(ir):
                    yield item
            finally:
                await provider.close()
            return
        if provider_type == ProviderType.ANTHROPIC:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                async for item in self._simulate_anthropic_stream(ir):
                    yield item
                return
            provider = AnthropicProvider(api_key=api_key)
            try:
                async for item in provider.complete_stream(ir):
                    yield item
            finally:
                await provider.close()
            return
        async for item in self._simulate_openai_stream(ir):
            yield item

    async def _route_to_provider_with_live_relay(self, provider_type: ProviderType, ir: EdgeKIR) -> Dict[str, Any]:
        """Relay provider deltas to an in-process observer while preserving PREC.

        Only callers that explicitly install the callback take this route. The
        normal executor lifecycle (compute admission, runtime governor,
        crystallization caller, receipts, and final response) remains intact;
        the callback merely gives a compatible SSE boundary immediate access to
        already-governed upstream deltas.
        """
        callback = (ir.metadata or {}).get("edgek_live_token_callback")
        if callback is None:
            return await self._route_to_provider(provider_type, ir)

        parts: list[str] = []
        finish_reason = "stop"
        async for event in self._route_to_provider_stream(provider_type, ir):
            text = self._stream_event_text(event)
            if text:
                parts.append(text)
                result = callback(text)
                if hasattr(result, "__await__"):
                    await result
            if isinstance(event, dict):
                choices = event.get("choices")
                if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                    finish_reason = str(choices[0].get("finish_reason") or finish_reason)
        response = self._openai_text_response(
            ir,
            "".join(parts),
            provider=str((ir.metadata or {}).get("edgek_provider") or provider_type.value),
        )
        response["choices"][0]["finish_reason"] = finish_reason
        response["edgek_live_token_relay"] = True
        return response

    @staticmethod
    def _stream_event_text(event: Any) -> str:
        if isinstance(event, str):
            return event
        if not isinstance(event, dict):
            return ""
        choices = event.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            first = choices[0]
            delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
            message = first.get("message") if isinstance(first.get("message"), dict) else {}
            return str(delta.get("content") or message.get("content") or first.get("text") or "")
        delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
        return str(event.get("text") or event.get("completion") or delta.get("text") or "")

    async def _simulate_openai_stream(self, ir: EdgeKIR):
        text = str((ir.metadata or {}).get("simulated_stream_text") or self._simulate_openai_response(ir)["choices"][0]["message"]["content"])
        for chunk in self._stream_text_chunks(text):
            yield {"choices": [{"delta": {"content": chunk}}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    async def _simulate_anthropic_stream(self, ir: EdgeKIR):
        content = self._simulate_anthropic_response(ir)["content"][0]["text"]
        text = str((ir.metadata or {}).get("simulated_stream_text") or content)
        for chunk in self._stream_text_chunks(text):
            yield {"type": "content_block_delta", "delta": {"type": "text_delta", "text": chunk}}
        yield {"type": "message_delta", "stop_reason": "end_turn"}

    @staticmethod
    def _stream_text_chunks(text: str):
        size = 24
        for index in range(0, len(text), size):
            yield text[index:index + size]

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return None

    async def _route_to_provider(self, provider_type: ProviderType, ir: EdgeKIR) -> Dict[str, Any]:
        """Route to the appropriate provider implementation."""
        if provider_type == ProviderType.OPENAI:
            return await self._execute_openai(ir)
        if provider_type == ProviderType.ANTHROPIC:
            return await self._execute_anthropic(ir)
        if provider_type == ProviderType.GEMINI:
            return await self._execute_gemini(ir)
        if provider_type == ProviderType.HUGGINGFACE:
            return await self._execute_openai_compatible(
                ir,
                provider_label="huggingface",
                api_key_env="HF_TOKEN",
                base_url=os.environ.get("HF_INFERENCE_BASE_URL", "https://router.huggingface.co/v1"),
                missing_key_response=self._simulate_huggingface_response,
            )
        if provider_type == ProviderType.TGI:
            return await self._execute_tgi(ir)
        if provider_type == ProviderType.LITELLM:
            return await self._execute_openai_compatible(
                ir,
                provider_label="litellm",
                api_key_env="LITELLM_API_KEY",
                base_url=os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1"),
                allow_missing_key=True,
                missing_key_response=self._simulate_litellm_response,
            )
        if provider_type == ProviderType.OPENAI_COMPATIBLE:
            config = self._openai_compatible_config(ir)
            provider_label = str(config.get("provider_id") or ir.metadata.get("edgek_provider") or "openai_compatible")
            env_names = config.get("env") or []
            api_key_env = env_names[0] if env_names else f"{provider_label.upper()}_API_KEY"
            return await self._execute_openai_compatible(
                ir,
                provider_label=provider_label,
                api_key_env=str(api_key_env),
                base_url=str(config.get("base_url") or "http://127.0.0.1:4000/v1"),
                missing_key_response=lambda request_ir: self._simulate_openai_compatible_response(request_ir, provider_label),
            )
        if provider_type == ProviderType.OLLAMA:
            return await self._execute_openai_compatible(
                ir,
                provider_label="ollama",
                api_key_env="OLLAMA_API_KEY",
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
                allow_missing_key=True,
                missing_key_response=lambda request_ir: self._simulate_openai_compatible_response(request_ir, "ollama"),
            )
        return await self._execute_openai(ir)

    @staticmethod
    def _openai_compatible_config(ir: EdgeKIR) -> Dict[str, Any]:
        """Resolve the selected registry lane into an executable endpoint.

        The gateway's provider registry is authoritative for NIM credentials
        and base URLs.  Without this bridge, a ``nvidia_nim`` metadata value
        was not an enum member and incorrectly fell through to OpenAI.
        """
        metadata = ir.metadata or {}
        config = dict(metadata.get("provider_config") or {})
        provider_id = str(
            config.get("provider_id")
            or metadata.get("route_provider")
            or metadata.get("provider")
            or metadata.get("edgek_provider")
            or ""
        ).strip()
        if provider_id:
            record = next(
                (item for item in ProviderRegistry().records(include_disabled=True) if item.provider_id == provider_id),
                None,
            )
            if record and record.openai_compatible:
                config = {**record.to_dict(), **config}
        return config
    
    def _determine_provider_type(self, ir: EdgeKIR) -> ProviderType:
        """Determine which provider to route to based on the IR"""
        provider_from_metadata = ir.metadata.get("route_provider") or ir.metadata.get("provider")
        if provider_from_metadata:
            try:
                return ProviderType(provider_from_metadata)
            except ValueError:
                pass
        if provider_from_metadata:
            record = next(
                (item for item in ProviderRegistry().records(include_disabled=True) if item.provider_id == provider_from_metadata),
                None,
            )
            if record:
                backend_routes = {
                    "native_anthropic": ProviderType.ANTHROPIC,
                    "native_gemini": ProviderType.GEMINI,
                    "native_huggingface": ProviderType.HUGGINGFACE,
                    "litellm": ProviderType.LITELLM,
                    "ollama": ProviderType.OLLAMA,
                }
                if record.openai_compatible or record.backend == "openai_compatible":
                    return ProviderType.OPENAI_COMPATIBLE
                if record.backend in backend_routes:
                    return backend_routes[record.backend]
        
        # Infer from model name
        if ir.model.startswith("gpt"):
            return ProviderType.OPENAI
        elif ir.model.startswith("claude"):
            return ProviderType.ANTHROPIC
        elif ir.model.startswith("gemini"):
            return ProviderType.GEMINI
        elif ir.model.startswith("hf/") or ir.model.startswith("huggingface/"):
            return ProviderType.HUGGINGFACE
        elif ir.model.startswith("tgi/") or ir.model.startswith("llamacpp/"):
            return ProviderType.TGI
        elif ir.model.startswith("litellm/"):
            return ProviderType.LITELLM
        elif provider_from_metadata == "openai_compatible":
            return ProviderType.OPENAI_COMPATIBLE
        elif provider_from_metadata == "ollama":
            return ProviderType.OLLAMA
        
        # Default to OpenAI for compatibility
        return ProviderType.OPENAI
    
    async def _execute_openai(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute request against OpenAI API"""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or api_key.startswith("sk-test") or "test" in api_key.lower():
            logger.warning("OPENAI_API_KEY not set, returning simulated response")
            return self._simulate_openai_response(ir)
        
        try:
            provider = OpenAIProvider(api_key=api_key)
            response = await provider.complete(ir)
            await provider.close()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            return self._create_error_response(
                "PROVIDER_ERROR",
                f"OpenAI API error: {e.response.status_code}",
                status_code=e.response.status_code
            )
        except Exception as e:
            logger.error(f"OpenAI request failed: {e}")
            return self._create_error_response(
                "PROVIDER_ERROR",
                str(e),
                status_code=500
            )

    async def _execute_openai_compatible(
        self,
        ir: EdgeKIR,
        *,
        provider_label: str,
        api_key_env: str,
        base_url: str,
        allow_missing_key: bool = False,
        missing_key_response=None,
    ) -> Dict[str, Any]:
        """Execute against an OpenAI-compatible chat/completions endpoint."""
        api_key = os.environ.get(api_key_env, "")
        if not api_key and not allow_missing_key:
            logger.warning("%s not set, returning simulated %s response", api_key_env, provider_label)
            return missing_key_response(ir) if missing_key_response else self._simulate_openai_response(ir)
        url = f"{base_url.rstrip('/')}/chat/completions"
        model = self._provider_model_name(ir.model, provider_label)
        payload = self._openai_chat_payload(ir, model)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if provider_label == "huggingface":
            headers["X-Wait-For-Model"] = "true"
        try:
            response = await self.http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                data.setdefault("edgek_provider", provider_label)
            return data
        except httpx.HTTPStatusError as e:
            detail = self._provider_error_detail(e.response.text)
            logger.error("%s API error: %s - %s", provider_label, e.response.status_code, detail[:500])
            return self._create_error_response(
                "PROVIDER_ERROR",
                f"{provider_label} API error: {e.response.status_code}: {detail}",
                status_code=e.response.status_code,
                extra={"provider": provider_label, "upstream_error": detail[:1200], "model": model},
            )
        except Exception as e:
            logger.error("%s request failed: %s", provider_label, e)
            return self._create_error_response(
                "PROVIDER_ERROR",
                str(e),
                status_code=500,
                extra={"provider": provider_label},
            )

    async def _execute_tgi(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute against local/remote Text Generation Inference, including llama.cpp backend."""
        base_url = os.environ.get("TGI_BASE_URL", "http://127.0.0.1:3000")
        model = self._provider_model_name(ir.model, "tgi")
        api_key = os.environ.get("HF_TOKEN", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        # Modern TGI exposes OpenAI-compatible routes; fall back to /generate for older deployments.
        chat_url = f"{base_url.rstrip('/')}/v1/chat/completions"
        payload = self._openai_chat_payload(ir, model)
        try:
            response = await self.http_client.post(chat_url, headers=headers, json=payload)
            if response.status_code == 404:
                return await self._execute_tgi_generate(ir, base_url, headers)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                data.setdefault("edgek_provider", "tgi")
                data.setdefault("edgek_tgi_backend", os.environ.get("TGI_BACKEND", "llamacpp"))
            return data
        except httpx.HTTPStatusError as e:
            logger.error("TGI API error: %s - %s", e.response.status_code, e.response.text[:500])
            return self._create_error_response(
                "PROVIDER_ERROR",
                f"TGI API error: {e.response.status_code}",
                status_code=e.response.status_code,
                extra={"provider": "tgi"},
            )
        except Exception as e:
            logger.error("TGI request failed: %s", e)
            return self._create_error_response(
                "PROVIDER_ERROR",
                str(e),
                status_code=500,
                extra={"provider": "tgi"},
            )

    async def _execute_tgi_generate(self, ir: EdgeKIR, base_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        prompt = self._messages_to_prompt(ir.messages)
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": ir.max_tokens or 256,
                "temperature": ir.temperature if ir.temperature is not None else 0.7,
                "top_p": ir.top_p if ir.top_p is not None else 0.95,
                "stop": ir.stop if isinstance(ir.stop, list) else ([ir.stop] if ir.stop else []),
            },
        }
        response = await self.http_client.post(f"{base_url.rstrip('/')}/generate", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        text = data.get("generated_text") or data.get("details", {}).get("generated_text") or str(data)
        return self._openai_text_response(ir, text, provider="tgi", extra={"raw_tgi": data})

    async def _execute_gemini(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute a live Google AI Studio Gemini generateContent request."""
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY/GOOGLE_API_KEY not set, returning simulated response")
            return self._simulate_gemini_response(ir)
        base_url = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
        model = self._provider_model_name(ir.model, "gemini")
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        payload = self._gemini_payload(ir)
        try:
            response = await self.http_client.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                data.setdefault("edgek_provider", "gemini")
            return data
        except httpx.HTTPStatusError as e:
            logger.error("Gemini API error: %s - %s", e.response.status_code, e.response.text[:500])
            return self._create_error_response(
                "PROVIDER_ERROR",
                f"Gemini API error: {e.response.status_code}",
                status_code=e.response.status_code,
                extra={"provider": "gemini"},
            )
        except Exception as e:
            logger.error("Gemini request failed: %s", e)
            return self._create_error_response(
                "PROVIDER_ERROR",
                str(e),
                status_code=500,
                extra={"provider": "gemini"},
            )

    def _openai_chat_payload(self, ir: EdgeKIR, model: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": ir.messages,
        }
        if ir.max_tokens:
            payload["max_tokens"] = ir.max_tokens
        if ir.temperature is not None:
            payload["temperature"] = ir.temperature
        if ir.top_p is not None:
            payload["top_p"] = ir.top_p
        if ir.tools:
            payload["tools"] = ir.tools
        if ir.tool_choice:
            payload["tool_choice"] = ir.tool_choice
        if ir.stop:
            payload["stop"] = ir.stop
        return payload

    def _gemini_payload(self, ir: EdgeKIR) -> Dict[str, Any]:
        contents = []
        system_parts = []
        for msg in ir.messages:
            role = msg.get("role", "user")
            content = str(msg.get("content", ""))
            if role == "system":
                system_parts.append({"text": content})
                continue
            contents.append({
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}],
            })
        payload: Dict[str, Any] = {"contents": contents or [{"role": "user", "parts": [{"text": ""}]}]}
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        generation: Dict[str, Any] = {}
        if ir.max_tokens:
            generation["maxOutputTokens"] = ir.max_tokens
        if ir.temperature is not None:
            generation["temperature"] = ir.temperature
        if ir.top_p is not None:
            generation["topP"] = ir.top_p
        if ir.stop:
            generation["stopSequences"] = ir.stop if isinstance(ir.stop, list) else [ir.stop]
        if generation:
            payload["generationConfig"] = generation
        return payload

    def _provider_model_name(self, model: str, provider: str) -> str:
        prefixes = {
            "huggingface": ("hf/", "huggingface/"),
            "tgi": ("tgi/", "llamacpp/"),
            "litellm": ("litellm/",),
            "gemini": ("gemini/",),
        }.get(provider, ())
        for prefix in prefixes:
            if model.startswith(prefix):
                return model[len(prefix):]
        return model

    def _messages_to_prompt(self, messages: list) -> str:
        return "\n".join(f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in messages)

    def _provider_error_detail(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "upstream returned an empty error body"
        try:
            data = json.loads(text)
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                return str(error.get("message") or error.get("provider_specific_fields", {}).get("error") or error)[:1200]
            if isinstance(data, dict) and data.get("message"):
                return str(data.get("message"))[:1200]
        except Exception:
            pass
        return text[:1200]

    def _openai_text_response(
        self,
        ir: EdgeKIR,
        text: str,
        *,
        provider: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = {
            "id": f"{provider}-cmpl-{hash(text) % 1000000}",
            "object": "chat.completion",
            "created": 1234567890,
            "model": ir.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(str(ir.messages)) // 4,
                "completion_tokens": len(text) // 4,
                "total_tokens": (len(str(ir.messages)) + len(text)) // 4,
            },
            "edgek_provider": provider,
        }
        if extra:
            response.update(extra)
        return response
    
    async def _execute_anthropic(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute request against Anthropic API"""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, returning simulated response")
            return self._simulate_anthropic_response(ir)
        
        try:
            provider = AnthropicProvider(api_key=api_key)
            response = await provider.complete(ir)
            await provider.close()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text}")
            return self._create_error_response(
                "PROVIDER_ERROR",
                f"Anthropic API error: {e.response.status_code}",
                status_code=e.response.status_code
            )
        except Exception as e:
            logger.error(f"Anthropic request failed: {e}")
            return self._create_error_response(
                "PROVIDER_ERROR",
                str(e),
                status_code=500
            )
    
    def _simulate_openai_response(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Return a simulated response when API key is not available"""
        return {
            "id": f"chatcmpl-simulated-{hash(str(ir.messages)) % 1000000}",
            "object": "chat.completion",
            "created": 1234567890,
            "model": ir.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[SIMULATED] EdgeK BEAST Gateway would execute request for model {ir.model}. "
                                 f"Set OPENAI_API_KEY environment variable for real API calls.",
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(str(ir.messages)) // 4,
                "completion_tokens": 20,
                "total_tokens": (len(str(ir.messages)) // 4) + 20
            }
        }
    
    def _simulate_anthropic_response(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Return a simulated response when API key is not available"""
        return {
            "id": f"msg_simulated_{hash(str(ir.messages)) % 1000000}",
            "type": "message",
            "role": "assistant",
            "model": ir.model,
            "content": [
                {
                    "type": "text",
                    "text": f"[SIMULATED] EdgeK BEAST Gateway would execute request for model {ir.model}. "
                          f"Set ANTHROPIC_API_KEY environment variable for real API calls."
                }
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": len(str(ir.messages)) // 4,
                "output_tokens": 20
            }
        }

    def _simulate_gemini_response(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Return a simulated Gemini response when no live Google adapter is configured."""
        prompt_tokens = len(str(ir.messages)) // 4
        return {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "text": (
                                    f"[SIMULATED] EdgeK BEAST Gateway would execute Gemini request "
                                    f"for model {ir.model}. Configure a Google/OpenAI-compatible "
                                    f"backend for live Gemini calls."
                                )
                            }
                        ],
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": 28,
                "totalTokenCount": prompt_tokens + 28,
            },
        }

    def _simulate_huggingface_response(self, ir: EdgeKIR) -> Dict[str, Any]:
        return self._openai_text_response(
            ir,
            f"[SIMULATED] EdgeK BEAST would execute Hugging Face request for model {ir.model}. "
            "Set HF_TOKEN for live Hugging Face router or TGI calls.",
            provider="huggingface",
        )

    def _simulate_litellm_response(self, ir: EdgeKIR) -> Dict[str, Any]:
        return self._openai_text_response(
            ir,
            f"[SIMULATED] EdgeK BEAST would execute LiteLLM request for model {ir.model}. "
            "Start LiteLLM at LITELLM_BASE_URL for live proxy calls.",
            provider="litellm",
        )

    def _simulate_openai_compatible_response(self, ir: EdgeKIR, provider: str) -> Dict[str, Any]:
        return self._openai_text_response(
            ir,
            f"[SIMULATED] EdgeK BEAST would execute {provider} OpenAI-compatible request for model {ir.model}. "
            "Set provider credentials/base URL for live calls.",
            provider=provider,
        )
    
    def _create_error_response(
        self,
        error_type: str,
        message: str,
        status_code: int = 400,
        extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create an error response in OpenAI format for compatibility"""
        error = {
            "error": {
                "message": message,
                "type": error_type,
                "code": error_type.lower(),
                "param": None,
                "status": status_code
            }
        }
        if extra:
            error["error"].update(extra)
        return error
    
    async def close(self):
        """Close the HTTP client and providers"""
        await self.http_client.aclose()
        for provider in self._providers.values():
            if hasattr(provider, 'close'):
                await provider.close()


# Global executor instance
executor = Executor()
