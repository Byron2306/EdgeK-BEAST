"""Governed CPU-first Ollama context reuse.

Ollama's legacy ``context`` array is treated as engine-native continuation state,
not as portable raw KV tensors.  Reuse is enabled only when the server actually
returns context tokens.  Every call reports the honest reuse mode and measured
prompt-evaluation metrics.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional

import httpx


class OllamaReuseMode(str, Enum):
    NATIVE_CONTEXT = "native_context"
    WARM_MODEL = "warm_model"
    PREFIX_REPLAY = "prefix_replay"
    MISS = "miss"


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OllamaContextBlock:
    context_id: str
    model: str
    prompt_prefix: str
    system_prompt: str
    ollama_context: List[int]
    model_digest: str = ""
    tokenizer_hint: str = ""
    template_digest: str = ""
    options_digest: str = ""
    num_ctx: int = 0
    created_at: str = ""
    last_used_at: str = ""
    use_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    memfd: Optional[int] = field(default=None, repr=False, compare=False)

    @property
    def native_context_available(self) -> bool:
        return bool(self.ollama_context)

    @property
    def estimated_bytes(self) -> int:
        return len(self.ollama_context) * 8

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "ollama_context_block",
            "version": "2.0",
            "context_id": self.context_id,
            "model": self.model,
            "model_digest": self.model_digest,
            "tokenizer_hint": self.tokenizer_hint,
            "template_digest": self.template_digest,
            "options_digest": self.options_digest,
            "num_ctx": self.num_ctx,
            "prompt_prefix_hash": _digest(self.prompt_prefix),
            "system_prompt_hash": _digest(self.system_prompt),
            "context_length": len(self.ollama_context),
            "estimated_bytes": self.estimated_bytes,
            "native_context_available": self.native_context_available,
            "sealed_memfd": self.memfd is not None,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "metadata": dict(self.metadata),
            "authority": "ollama_context_reuse_only",
            "portable_raw_kv": False,
        }

    def close(self) -> None:
        if self.memfd is not None:
            try:
                os.close(self.memfd)
            except OSError:
                pass
            self.memfd = None


class OllamaKVManager:
    """Bounded Ollama CPU context manager with honest capability reporting."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        *,
        max_contexts: int = 32,
        max_context_bytes: int = 128 * 1024 * 1024,
        pressure_monitor: Any = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.max_contexts = max(1, int(max_contexts))
        self.max_context_bytes = max(1024, int(max_context_bytes))
        self.pressure_monitor = pressure_monitor
        self.contexts: Dict[str, OllamaContextBlock] = {}
        self._session = client or httpx.Client()
        self._stats = {"hits": 0, "misses": 0, "native_hits": 0, "evictions": 0, "errors": 0}

    def close(self) -> None:
        for block in list(self.contexts.values()):
            block.close()
        self.contexts.clear()
        self._session.close()

    def _pressure_high(self) -> bool:
        monitor = self.pressure_monitor
        if monitor is None:
            return False
        try:
            pressure = monitor.get_pressure()
            memory = float(getattr(pressure, "memory", 0.0))
            io = float(getattr(pressure, "io", 0.0))
            return max(memory, io) >= 20.0
        except Exception:
            return False

    def _identity(
        self,
        model: str,
        prompt_prefix: str,
        system_prompt: str,
        *,
        model_digest: str,
        tokenizer_hint: str,
        template: str,
        options: Mapping[str, Any],
        compatibility: Optional[Mapping[str, Any]] = None,
    ) -> str:
        payload = {
            "model": model,
            "model_digest": model_digest,
            "tokenizer_hint": tokenizer_hint,
            "template_digest": _digest(template),
            "prefix_hash": _digest(prompt_prefix),
            "system_hash": _digest(system_prompt),
            "options": dict(options),
            "num_ctx": int(options.get("num_ctx") or 0),
            "compatibility": dict(compatibility or {}),
        }
        return "ollama_ctx_" + _digest(payload).split(":", 1)[1][:24]

    @staticmethod
    def _encode_tokens(tokens: Iterable[int]) -> bytes:
        values = [int(x) for x in tokens]
        return struct.pack(f"<{len(values)}q", *values) if values else b""

    def _seal_tokens(self, block: OllamaContextBlock) -> None:
        if not block.ollama_context or not hasattr(os, "memfd_create"):
            return
        try:
            flags = int(getattr(os, "MFD_CLOEXEC", 0)) | int(getattr(os, "MFD_ALLOW_SEALING", 0))
            fd = os.memfd_create(f"beast-{block.context_id}", flags)
            os.write(fd, self._encode_tokens(block.ollama_context))
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                import fcntl
                seals = 0
                for name in ("F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE", "F_SEAL_SEAL"):
                    seals |= int(getattr(fcntl, name, 0))
                if seals and hasattr(fcntl, "F_ADD_SEALS"):
                    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
            except (ImportError, OSError):
                pass
            block.memfd = fd
        except OSError:
            block.memfd = None

    def _evict_if_needed(self, incoming_bytes: int = 0) -> None:
        def total_bytes() -> int:
            return sum(block.estimated_bytes for block in self.contexts.values())
        while self.contexts and (
            len(self.contexts) >= self.max_contexts
            or total_bytes() + max(0, incoming_bytes) > self.max_context_bytes
            or self._pressure_high()
        ):
            victim = min(self.contexts.values(), key=lambda b: (b.last_used_at or b.created_at, b.use_count))
            victim.close()
            self.contexts.pop(victim.context_id, None)
            self._stats["evictions"] += 1
            if self._pressure_high() and not self.contexts:
                break

    def get_or_create_context(
        self,
        model: str,
        prompt_prefix: str,
        system_prompt: str,
        *,
        model_digest: str = "",
        tokenizer_hint: str = "",
        template: str = "",
        options: Optional[Mapping[str, Any]] = None,
        keep_alive: str = "5m",
        compatibility: Optional[Mapping[str, Any]] = None,
    ) -> OllamaContextBlock:
        options_dict = dict(options or {})
        ctx_id = self._identity(
            model, prompt_prefix, system_prompt,
            model_digest=model_digest, tokenizer_hint=tokenizer_hint,
            template=template, options=options_dict,
            compatibility=compatibility,
        )
        existing = self.contexts.get(ctx_id)
        if existing is not None:
            existing.last_used_at = _now()
            existing.use_count += 1
            self._stats["hits"] += 1
            if existing.native_context_available:
                self._stats["native_hits"] += 1
            return existing

        self._stats["misses"] += 1
        now = _now()
        metadata: Dict[str, Any] = {"created_via": "ollama_generate", "reuse_mode": OllamaReuseMode.MISS.value, "compatibility": dict(compatibility or {})}
        context_tokens: List[int] = []
        if not self._pressure_high():
            try:
                response = self._session.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": f"{system_prompt}\n\n{prompt_prefix}".strip(),
                        "stream": False,
                        "keep_alive": keep_alive,
                        "options": {**options_dict, "num_predict": 1},
                    },
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
                raw_context = data.get("context")
                if isinstance(raw_context, list) and all(isinstance(x, int) for x in raw_context):
                    context_tokens = list(raw_context)
                    metadata["reuse_mode"] = OllamaReuseMode.NATIVE_CONTEXT.value
                else:
                    metadata["reuse_mode"] = OllamaReuseMode.WARM_MODEL.value
                for key in ("load_duration", "prompt_eval_count", "prompt_eval_duration", "total_duration"):
                    metadata[key] = data.get(key)
            except Exception as exc:
                self._stats["errors"] += 1
                metadata.update({"error": str(exc), "reuse_mode": OllamaReuseMode.MISS.value})
        else:
            metadata.update({"creation_skipped": "system_pressure", "reuse_mode": OllamaReuseMode.MISS.value})

        block = OllamaContextBlock(
            context_id=ctx_id,
            model=model,
            prompt_prefix=prompt_prefix,
            system_prompt=system_prompt,
            ollama_context=context_tokens,
            model_digest=model_digest,
            tokenizer_hint=tokenizer_hint,
            template_digest=_digest(template),
            options_digest=_digest(options_dict),
            num_ctx=int(options_dict.get("num_ctx") or 0),
            created_at=now,
            last_used_at=now,
            use_count=1,
            metadata=metadata,
        )
        self._evict_if_needed(block.estimated_bytes)
        self._seal_tokens(block)
        self.contexts[ctx_id] = block
        return block

    def generate_with_context(
        self,
        context_block: OllamaContextBlock,
        prompt: str,
        max_tokens: int = 256,
        *,
        options: Optional[Mapping[str, Any]] = None,
        keep_alive: str = "5m",
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        supplied_native = context_block.native_context_available
        payload: Dict[str, Any] = {
            "model": context_block.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {**dict(options or {}), "num_predict": max(1, int(max_tokens))},
        }
        if supplied_native:
            payload["context"] = list(context_block.ollama_context)
        try:
            response = self._session.post(f"{self.ollama_url}/api/generate", json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            returned = data.get("context")
            returned_native = isinstance(returned, list) and all(isinstance(x, int) for x in returned)
            if returned_native:
                context_block.close()
                context_block.ollama_context = list(returned)
                self._seal_tokens(context_block)
            context_block.last_used_at = _now()
            context_block.use_count += 1
            prompt_eval_count = data.get("prompt_eval_count")
            if supplied_native:
                mode = OllamaReuseMode.NATIVE_CONTEXT
            elif context_block.metadata.get("reuse_mode") == OllamaReuseMode.WARM_MODEL.value:
                mode = OllamaReuseMode.WARM_MODEL
            else:
                mode = OllamaReuseMode.PREFIX_REPLAY
            return {
                "response": data.get("response", ""),
                "done": data.get("done", True),
                "reuse_mode": mode.value,
                "used_real_context": supplied_native,
                "native_context_supplied": supplied_native,
                "native_context_returned": returned_native,
                "portable_raw_kv": False,
                "prompt_eval_count": prompt_eval_count,
                "prompt_eval_duration": data.get("prompt_eval_duration"),
                "eval_count": data.get("eval_count"),
                "eval_duration": data.get("eval_duration"),
                "load_duration": data.get("load_duration"),
                "total_duration": data.get("total_duration"),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except Exception as exc:
            self._stats["errors"] += 1
            return {
                "response": "",
                "done": True,
                "error": str(exc),
                "reuse_mode": OllamaReuseMode.MISS.value,
                "used_real_context": False,
                "native_context_supplied": supplied_native,
                "native_context_returned": False,
                "portable_raw_kv": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

    def find_context(self, model: str, prompt_prefix: str, system_prompt: str) -> Optional[OllamaContextBlock]:
        """Find a native continuation without triggering another prefill."""
        for block in self.contexts.values():
            if block.model == model and block.prompt_prefix == prompt_prefix and block.system_prompt == system_prompt:
                return block
        return None

    def list_contexts(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in sorted(self.contexts.values(), key=lambda x: x.last_used_at, reverse=True)]

    def evict_context(self, context_id: str) -> bool:
        block = self.contexts.pop(context_id, None)
        if block is None:
            return False
        block.close()
        self._stats["evictions"] += 1
        return True

    def invalidate_all(self, *, reason: str = "workspace_changed") -> int:
        """Drop all engine-native state when its source context is no longer true."""
        removed = 0
        for context_id in list(self.contexts):
            if self.evict_context(context_id):
                removed += 1
        self._stats["last_invalidation_reason"] = reason
        self._stats["invalidations"] = int(self._stats.get("invalidations", 0)) + removed
        return removed

    def get_stats(self) -> Dict[str, Any]:
        total_bytes = sum(block.estimated_bytes for block in self.contexts.values())
        return {
            "beast_object_type": "ollama_kv_manager_stats",
            "version": "2.0",
            "total_contexts": len(self.contexts),
            "real_kv_contexts": sum(1 for block in self.contexts.values() if block.native_context_available),
            "sealed_memfd_contexts": sum(1 for block in self.contexts.values() if block.memfd is not None),
            "estimated_context_bytes": total_bytes,
            "max_context_bytes": self.max_context_bytes,
            "max_contexts": self.max_contexts,
            "total_uses": sum(block.use_count for block in self.contexts.values()),
            **self._stats,
            "ollama_url": self.ollama_url,
            "cpu_only": True,
            "portable_raw_kv": False,
            "native_context_is_engine_specific": True,
        }
