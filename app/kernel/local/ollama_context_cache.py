"""LRU Context Cache for OllamaKVManager.

Caches Ollama context blocks by (model, prompt_prefix_hash, system_prompt_hash)
to avoid re-running the prefix prompt on every lookup.
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
from typing import Optional, Tuple

from app.kernel.local.ollama_kv_manager import OllamaContextBlock


class OllamaContextCache:
    """Simple LRU cache for Ollama context blocks."""

    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._cache: OrderedDict[Tuple[str, str, str], OllamaContextBlock] = OrderedDict()

    def _make_key(self, model: str, prompt_prefix: str, system_prompt: str) -> Tuple[str, str, str]:
        return (
            model,
            hashlib.sha256(prompt_prefix.encode()).hexdigest(),
            hashlib.sha256(system_prompt.encode()).hexdigest(),
        )

    def get(self, model: str, prompt_prefix: str, system_prompt: str) -> Optional[OllamaContextBlock]:
        key = self._make_key(model, prompt_prefix, system_prompt)
        if key not in self._cache:
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, block: OllamaContextBlock) -> None:
        key = self._make_key(block.model, block.prompt_prefix, block.system_prompt)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = block
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)  # Remove least recently used

    def evict(self, model: str, prompt_prefix: str, system_prompt: str) -> bool:
        key = self._make_key(model, prompt_prefix, system_prompt)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)
