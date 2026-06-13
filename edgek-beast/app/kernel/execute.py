"""
EdgeK BEAST Gateway - Execute Phase of PREC Cycle
Responsible for routing the governed request to the appropriate provider/model
"""

import os
import json
import httpx
import asyncio
from typing import Dict, Any, Optional
from dataclasses import asdict
import logging

from .perceive import EdgeKIR, ProviderType
from .reason import GovernanceDecision, GovernanceResult
from .providers import ProviderFactory, OpenAIProvider, AnthropicProvider
from .runtime import runtime_governor

logger = logging.getLogger(__name__)


class Executor:
    """Executes the governed request by routing to appropriate provider"""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=120.0)
        self._providers = {}
    
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
        provider_name = "google" if provider_type == ProviderType.GEMINI else provider_type.value
        admission = runtime_governor.begin_execution(
            provider=provider_name,
            model=ir.model,
            session_id=ir.metadata.get("session_id", "default"),
            metadata={"stream": ir.stream}
        )
        if not admission.allowed:
            return self._create_error_response(
                "RUNTIME_DEFERRED",
                admission.reason,
                status_code=429 if admission.retry_after_seconds else 503,
                extra={
                    "attempt_id": admission.attempt_id,
                    "retry_after_seconds": admission.retry_after_seconds,
                }
            )

        try:
            response = await asyncio.wait_for(
                self._route_to_provider(provider_type, ir),
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
            if isinstance(response, dict):
                response.setdefault("edgek_runtime", {
                    "attempt_id": admission.attempt_id,
                    "provider": provider_name,
                    "timeout_seconds": admission.timeout_seconds,
                })
            return response
        except asyncio.TimeoutError:
            runtime_governor.complete_execution(
                attempt_id=admission.attempt_id,
                provider=provider_name,
                success=False,
                error_type="timeout",
                error_message=f"Provider execution timed out after {admission.timeout_seconds}s",
            )
            return self._create_error_response(
                "RUNTIME_TIMEOUT",
                f"Provider execution timed out after {admission.timeout_seconds}s",
                status_code=504,
                extra={"attempt_id": admission.attempt_id}
            )
        except Exception as e:
            runtime_governor.complete_execution(
                attempt_id=admission.attempt_id,
                provider=provider_name,
                success=False,
                error_type="runtime_exception",
                error_message=str(e),
            )
            return self._create_error_response(
                "RUNTIME_ERROR",
                str(e),
                status_code=500,
                extra={"attempt_id": admission.attempt_id}
            )

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
        return await self._execute_openai(ir)
    
    def _determine_provider_type(self, ir: EdgeKIR) -> ProviderType:
        """Determine which provider to route to based on the IR"""
        provider_from_metadata = ir.metadata.get("provider")
        if provider_from_metadata:
            try:
                return ProviderType(provider_from_metadata)
            except ValueError:
                pass
        
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
        
        # Default to OpenAI for compatibility
        return ProviderType.OPENAI
    
    async def _execute_openai(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute request against OpenAI API"""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
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
            logger.error("%s API error: %s - %s", provider_label, e.response.status_code, e.response.text[:500])
            return self._create_error_response(
                "PROVIDER_ERROR",
                f"{provider_label} API error: {e.response.status_code}",
                status_code=e.response.status_code,
                extra={"provider": provider_label},
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
