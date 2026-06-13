"""
EdgeK BEAST Gateway - Perceive Phase of PREC Cycle
Responsible for normalizing incoming requests to EdgeK Internal Representation (IR)
"""

import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ProviderType(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    HUGGINGFACE = "huggingface"
    TGI = "tgi"
    LITELLM = "litellm"
    EDGEK_IR = "edgek_ir"


@dataclass
class EdgeKIR:
    """EdgeK Internal Representation of a request"""
    messages: list
    model: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: bool = False
    tools: Optional[list] = None
    tool_choice: Optional[str] = None
    stop: Optional[Any] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Perceiver:
    """Normalizes various provider formats to EdgeK IR"""
    
    def __init__(self):
        self.provider_parsers = {
            ProviderType.OPENAI: self._parse_openai,
            ProviderType.ANTHROPIC: self._parse_anthropic,
            ProviderType.GEMINI: self._parse_gemini,
        }
    
    def perceive(self, raw_request: Dict[Any, Any], provider_type: ProviderType) -> EdgeKIR:
        """
        Convert provider-specific request to EdgeK IR
        
        Args:
            raw_request: The raw request from the provider
            provider_type: The type of provider (openai, anthropic, etc.)
            
        Returns:
            EdgeKIR: Normalized internal representation
        """
        if provider_type in self.provider_parsers:
            return self.provider_parsers[provider_type](raw_request)
        else:
            # Assume it's already in EdgeK IR format
            return self._parse_edgek_ir(raw_request)
    
    def _parse_openai(self, request: Dict[Any, Any]) -> EdgeKIR:
        """Parse OpenAI format request to EdgeK IR"""
        messages = request.get("messages", [])
        # Handle completion format as well
        if not messages and "prompt" in request:
            messages = [{"role": "user", "content": request["prompt"]}]
        
        return EdgeKIR(
            messages=messages,
            model=request.get("model", "gpt-3.5-turbo"),
            max_tokens=request.get("max_tokens"),
            temperature=request.get("temperature"),
            top_p=request.get("top_p"),
            stream=request.get("stream", False),
            tools=request.get("tools"),
            tool_choice=request.get("tool_choice"),
            stop=request.get("stop"),
            metadata={
                "provider": "openai",
                "original_request": request
            }
        )
    
    def _parse_anthropic(self, request: Dict[Any, Any]) -> EdgeKIR:
        """Parse Anthropic format request to EdgeK IR"""
        messages = request.get("messages", [])
        # Handle legacy format
        if not messages and "prompt" in request:
            # Anthropic legacy format: \n\nHuman: ...\n\nAssistant:
            prompt = request["prompt"]
            if prompt.startswith("\n\nHuman: ") and "\n\nAssistant:" in prompt:
                parts = prompt.split("\n\nAssistant:", 1)
                human_part = parts[0][4:]  # Remove "\n\nHuman: "
                assistant_part = parts[1] if len(parts) > 1 else ""
                messages = [
                    {"role": "user", "content": human_part},
                    {"role": "assistant", "content": assistant_part}
                ]
            else:
                messages = [{"role": "user", "content": prompt}]
        
        return EdgeKIR(
            messages=messages,
            model=request.get("model", "claude-3-haiku-20240307"),
            max_tokens=request.get("max_tokens"),
            temperature=request.get("temperature"),
            top_p=request.get("top_p"),
            stream=request.get("stream", False),
            tools=request.get("tools"),
            tool_choice=request.get("tool_choice"),
            stop=request.get("stop_sequences") or request.get("stop"),
            metadata={
                "provider": "anthropic",
                "original_request": request
            }
        )

    def _parse_gemini(self, request: Dict[Any, Any]) -> EdgeKIR:
        """Parse Gemini generateContent format to EdgeK IR."""
        messages = []
        for item in request.get("contents", []):
            role = item.get("role", "user")
            normalized_role = "assistant" if role == "model" else role
            parts = item.get("parts", [])
            content_parts = []
            for part in parts:
                if "text" in part:
                    content_parts.append(str(part.get("text", "")))
                else:
                    content_parts.append(json.dumps(part, separators=(",", ":")))
            messages.append({
                "role": normalized_role,
                "content": "\n".join(content_parts),
            })
        if not messages and "prompt" in request:
            messages = [{"role": "user", "content": str(request["prompt"])}]

        generation = request.get("generationConfig", {})
        return EdgeKIR(
            messages=messages,
            model=request.get("model", "gemini-2.5-flash"),
            max_tokens=generation.get("maxOutputTokens") or request.get("max_tokens"),
            temperature=generation.get("temperature") or request.get("temperature"),
            top_p=generation.get("topP") or request.get("top_p"),
            stream=request.get("stream", False),
            tools=request.get("tools"),
            tool_choice=request.get("tool_choice"),
            stop=generation.get("stopSequences") or request.get("stop"),
            metadata={
                "provider": "gemini",
                "original_request": request
            }
        )
    
    def _parse_edgek_ir(self, request: Dict[Any, Any]) -> EdgeKIR:
        """Parse request that's already in EdgeK IR format"""
        return EdgeKIR(
            messages=request.get("messages", []),
            model=request.get("model", "edgek-default"),
            max_tokens=request.get("max_tokens"),
            temperature=request.get("temperature"),
            top_p=request.get("top_p"),
            stream=request.get("stream", False),
            tools=request.get("tools"),
            tool_choice=request.get("tool_choice"),
            stop=request.get("stop"),
            metadata=request.get("metadata", {})
        )


# Global perceiver instance
perceiver = Perceiver()
