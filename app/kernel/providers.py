"""
EdgeK BEAST Gateway - Provider Implementations
Real API integrations for OpenAI and Anthropic
"""

import os
import json
import httpx
from typing import Dict, Any, Optional, AsyncIterator
from abc import ABC, abstractmethod
import logging

from .perceive import EdgeKIR, ProviderType

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Abstract base class for provider implementations"""
    
    @abstractmethod
    async def complete(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute a completion request"""
        pass
    
    @abstractmethod
    async def complete_stream(self, ir: EdgeKIR) -> AsyncIterator[Dict[str, Any]]:
        """Execute a streaming completion request"""
        pass


class OpenAIProvider(BaseProvider):
    """OpenAI API provider implementation"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(timeout=120.0)
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def complete(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute a non-streaming completion"""
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": ir.model,
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
        
        logger.info(f"OpenAI request to {url}")
        
        response = await self.client.post(
            url,
            headers=self._build_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def complete_stream(self, ir: EdgeKIR) -> AsyncIterator[Dict[str, Any]]:
        """Execute a streaming completion"""
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": ir.model,
            "messages": ir.messages,
            "stream": True,
        }
        
        if ir.max_tokens:
            payload["max_tokens"] = ir.max_tokens
        if ir.temperature is not None:
            payload["temperature"] = ir.temperature
        if ir.top_p is not None:
            payload["top_p"] = ir.top_p
        
        async with self.client.stream(
            "POST",
            url,
            headers=self._build_headers(),
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield json.loads(data)
    
    async def list_models(self) -> Dict[str, Any]:
        """List available OpenAI models"""
        url = f"{self.base_url}/models"
        response = await self.client.get(url, headers=self._build_headers())
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class AnthropicProvider(BaseProvider):
    """Anthropic API provider implementation"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = base_url or "https://api.anthropic.com"
        self.client = httpx.AsyncClient(timeout=120.0)
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true"
        }
    
    def _convert_messages(self, messages: list) -> tuple:
        """Convert OpenAI-style messages to Anthropic format"""
        system = ""
        anthropic_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        return system, anthropic_messages
    
    async def complete(self, ir: EdgeKIR) -> Dict[str, Any]:
        """Execute a non-streaming completion"""
        url = f"{self.base_url}/v1/messages"
        
        system, messages = self._convert_messages(ir.messages)
        
        payload = {
            "model": ir.model,
            "messages": messages,
            "max_tokens": ir.max_tokens or 1024,
        }
        
        if system:
            payload["system"] = system
        if ir.temperature is not None:
            payload["temperature"] = ir.temperature
        if ir.top_p is not None:
            payload["top_p"] = ir.top_p
        if ir.stop:
            payload["stop_sequences"] = ir.stop if isinstance(ir.stop, list) else [ir.stop]
        
        logger.info(f"Anthropic request to {url}")
        
        response = await self.client.post(
            url,
            headers=self._build_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def complete_stream(self, ir: EdgeKIR) -> AsyncIterator[Dict[str, Any]]:
        """Execute a streaming completion"""
        url = f"{self.base_url}/v1/messages"
        
        system, messages = self._convert_messages(ir.messages)
        
        payload = {
            "model": ir.model,
            "messages": messages,
            "max_tokens": ir.max_tokens or 1024,
            "stream": True,
        }
        
        if system:
            payload["system"] = system
        if ir.temperature is not None:
            payload["temperature"] = ir.temperature
        
        async with self.client.stream(
            "POST",
            url,
            headers=self._build_headers(),
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield json.loads(data)
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class ProviderFactory:
    """Factory for creating provider instances"""
    
    _providers = {
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.ANTHROPIC: AnthropicProvider,
    }
    
    @classmethod
    def create(cls, provider_type: ProviderType, **kwargs) -> BaseProvider:
        """Create a provider instance"""
        provider_class = cls._providers.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {provider_type}")
        return provider_class(**kwargs)
    
    @classmethod
    def register(cls, provider_type: ProviderType, provider_class: type):
        """Register a new provider type"""
        cls._providers[provider_type] = provider_class