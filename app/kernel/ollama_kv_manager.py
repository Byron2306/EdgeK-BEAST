"""CPU-first Real KV Cache Management via Ollama.

Since we have no GPU, we use Ollama's native context reuse (the `context` parameter)
to achieve real KV cache reuse on CPU. This is not a simulation — Ollama actually
maintains KV state across calls when you pass the same `context` array.

This gives us real engine hooks on CPU without needing vLLM/SGLang tensor extraction.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class OllamaContextBlock:
    """A real Ollama context (KV cache) block."""
    context_id: str
    model: str
    prompt_prefix: str
    system_prompt: str
    ollama_context: List[int]  # The actual context array returned by Ollama
    created_at: str = ""
    last_used_at: str = ""
    use_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "ollama_context_block",
            "version": "1.0",
            "context_id": self.context_id,
            "model": self.model,
            "prompt_prefix": self.prompt_prefix,
            "system_prompt": self.system_prompt,
            "context_length": len(self.ollama_context),
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "metadata": self.metadata,
        }


class OllamaKVManager:
    """Real KV cache management for Ollama on CPU.

    Uses Ollama's native `context` parameter to reuse KV state.
    This is a genuine engine hook — Ollama actually reuses the attention cache.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self.contexts: Dict[str, OllamaContextBlock] = {}
        self._session = httpx.Client()

    def _compute_context_id(self, model: str, prompt_prefix: str, system_prompt: str) -> str:
        key = f"{model}:{prompt_prefix}:{system_prompt}"
        return "ollama_ctx_" + hashlib.sha256(key.encode()).hexdigest()[:16]

    def get_or_create_context(
        self,
        model: str,
        prompt_prefix: str,
        system_prompt: str,
    ) -> OllamaContextBlock:
        """Get an existing context or create a new one by running the prefix once."""
        ctx_id = self._compute_context_id(model, prompt_prefix, system_prompt)
        
        if ctx_id in self.contexts:
            ctx = self.contexts[ctx_id]
            ctx.last_used_at = datetime.now(timezone.utc).isoformat()
            ctx.use_count += 1
            return ctx

        # Create new context by running the system + prefix prompt
        full_prompt = f"{system_prompt}\n\n{prompt_prefix}"
        
        try:
            resp = self._session.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"num_predict": 1},  # Minimal generation, we only want the context
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Ollama returns the context array we can reuse
            ollama_context = data.get("context", [])
            
            if not ollama_context:
                # Fallback: some Ollama versions don't return context on first call
                # Try a second call or use empty context
                ollama_context = []
            
            block = OllamaContextBlock(
                context_id=ctx_id,
                model=model,
                prompt_prefix=prompt_prefix,
                system_prompt=system_prompt,
                ollama_context=ollama_context,
                created_at=datetime.now(timezone.utc).isoformat(),
                last_used_at=datetime.now(timezone.utc).isoformat(),
                use_count=1,
                metadata={"created_via": "ollama_generate"},
            )
            
            self.contexts[ctx_id] = block
            return block
            
        except Exception as e:
            # If Ollama fails, create a placeholder block (still usable, just no real KV reuse)
            block = OllamaContextBlock(
                context_id=ctx_id,
                model=model,
                prompt_prefix=prompt_prefix,
                system_prompt=system_prompt,
                ollama_context=[],
                created_at=datetime.now(timezone.utc).isoformat(),
                last_used_at=datetime.now(timezone.utc).isoformat(),
                use_count=1,
                metadata={"error": str(e), "real_kv": False},
            )
            self.contexts[ctx_id] = block
            return block

    def generate_with_context(
        self,
        context_block: OllamaContextBlock,
        prompt: str,
        max_tokens: int = 256,
    ) -> Dict[str, Any]:
        """Generate using a real Ollama context block for KV reuse."""
        start = time.perf_counter()
        
        payload = {
            "model": context_block.model,
            "prompt": prompt,
            "stream": False,
            "context": context_block.ollama_context,
            "options": {"num_predict": max_tokens},
        }
        
        try:
            resp = self._session.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            
            latency_ms = (time.perf_counter() - start) * 1000
            
            # Update context if Ollama returned a new one (it may have extended it)
            if "context" in data and data["context"]:
                context_block.ollama_context = data["context"]
            
            context_block.last_used_at = datetime.now(timezone.utc).isoformat()
            context_block.use_count += 1
            
            return {
                "response": data.get("response", ""),
                "done": data.get("done", True),
                "total_duration": data.get("total_duration"),
                "load_duration": data.get("load_duration"),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
                "latency_ms": round(latency_ms, 2),
                "used_real_context": len(context_block.ollama_context) > 0,
            }
            
        except Exception as e:
            return {
                "response": f"[Ollama error: {e}]",
                "done": True,
                "error": str(e),
                "latency_ms": (time.perf_counter() - start) * 1000,
                "used_real_context": False,
            }

    def list_contexts(self) -> List[Dict[str, Any]]:
        """List all managed context blocks."""
        return [ctx.to_dict() for ctx in self.contexts.values()]

    def evict_context(self, context_id: str) -> bool:
        """Remove a context block (Ollama will eventually GC it)."""
        if context_id in self.contexts:
            del self.contexts[context_id]
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return manager statistics."""
        total = len(self.contexts)
        total_uses = sum(c.use_count for c in self.contexts.values())
        real_contexts = sum(1 for c in self.contexts.values() if len(c.ollama_context) > 0)
        
        return {
            "beast_object_type": "ollama_kv_manager_stats",
            "version": "1.0",
            "total_contexts": total,
            "real_kv_contexts": real_contexts,
            "total_uses": total_uses,
            "ollama_url": self.ollama_url,
            "cpu_only": True,
        }
