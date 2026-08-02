"""Bounded threaded coordinator for Forge-managed Ollama context reuse.

Small work descriptors travel through a bounded queue. Native context arrays stay
inside OllamaKVManager and its sealed memfd-backed blocks. This module grants no
execution authority and performs no speculative background prefill in Level 1.
"""
from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional

from app.kernel.compute.forge_kv_economics import economics_from_result
from app.kernel.compute.forge_kv_proof_status import claim_status
from app.kernel.compute.forge_kv_registry import ForgeKVRegistry
from app.kernel.local.ollama_kv_manager import OllamaKVManager
from app.kernel.compute.kv_cache_transport import CacheEngine, CrossEngineKVCacheTransport


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PrefixParts:
    stable_prefix: str
    task_suffix: str
    repair_suffix: str = ""

    @property
    def prefix_hash(self) -> str:
        return _digest(self.stable_prefix)


@dataclass(frozen=True)
class ForgeKVRoute:
    stage: str
    action: str
    prefix_hash: str
    prefix_chars: int
    suffix_chars: int
    provider_prompt: str
    provider_called: bool
    injectable: bool
    reason: str
    block_id: str = ""
    engine: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"beast_object_type": "forge_kv_route", "version": "1.0", **self.__dict__}


@dataclass(frozen=True)
class ForgeKVRequest:
    task_class: str
    model: str
    prompt: str
    prompt_prefix: str = ""
    system_prompt: str = ""
    model_digest: str = ""
    tokenizer_hint: str = ""
    template: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)
    workspace_id: str = ""
    privacy_domain: str = "local"
    mission_id: str = ""
    max_tokens: int = 128
    runtime_version: str = ""
    architecture: str = ""
    quantization: str = ""
    rope_settings: str = ""
    policy_generation: str = ""
    repository_fingerprint: str = ""
    request_id: str = ""

    def sealed(self) -> "ForgeKVRequest":
        if self.request_id:
            return self
        object.__setattr__(self, "request_id", "forge_kv_" + uuid.uuid4().hex)
        return self


@dataclass
class _QueuedJob:
    request: ForgeKVRequest
    future: Future


class ForgeKVCoordinator:
    """Small fixed worker set with reliable bounded work admission."""

    def __init__(
        self,
        manager: OllamaKVManager,
        *,
        workers: int = 2,
        queue_capacity: int = 256,
        event_sink: Optional[Callable[[str, Dict[str, Any], ForgeKVRequest], None]] = None,
        transport: Optional[CrossEngineKVCacheTransport] = None,
        crystal_lookup: Optional[Callable[[Mapping[str, Any]], bool]] = None,
    ) -> None:
        self.manager = manager
        self.registry = ForgeKVRegistry()
        self.event_sink = event_sink
        self.transport = transport
        self.crystal_lookup = crystal_lookup
        self._queue: queue.Queue[Optional[_QueuedJob]] = queue.Queue(maxsize=max(1, int(queue_capacity)))
        self._threads: list[threading.Thread] = []
        self._closed = False
        self._metrics = {"submitted": 0, "completed": 0, "failed": 0, "queue_rejected": 0}
        self._metrics_lock = threading.Lock()
        for index in range(max(1, int(workers))):
            thread = threading.Thread(target=self._worker, name=f"beast-forge-kv-{index + 1}", daemon=True)
            thread.start()
            self._threads.append(thread)

    @staticmethod
    def split_packet(model_input: Mapping[str, Any]) -> PrefixParts:
        """Separate immutable task context from the changing repair suffix."""
        contract = model_input.get("residual_contract") if isinstance(model_input.get("residual_contract"), Mapping) else {}
        stable = {key: model_input.get(key) for key in ("task", "file", "symbol", "current_body", "residual_contract", "allowed_response")}
        suffix = {key: model_input.get(key) for key in ("unresolved_fields", "verified_patterns")}
        return PrefixParts(
            stable_prefix=json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str),
            task_suffix=json.dumps(suffix, sort_keys=True, separators=(",", ":"), default=str),
            repair_suffix=str(model_input.get("failure") or ""),
        )

    def prepare(
        self,
        model_input: Mapping[str, Any],
        *,
        model: str,
        tokenizer: str = "ollama-native",
        system_prompt: str = "You are a bounded residual solver. Return only declared fields.",
        exact_crystal: bool = False,
        larger_model_available: bool = False,
    ) -> ForgeKVRoute:
        parts = self.split_packet(model_input)
        if exact_crystal or (self.crystal_lookup is not None and self.crystal_lookup(model_input)):
            return ForgeKVRoute("crystal", "reuse_effect", parts.prefix_hash, len(parts.stable_prefix), 0, "", False, True, "verified_effect_reuse")
        context = self.manager.find_context(model, parts.stable_prefix, system_prompt)
        if context is not None and context.native_context_available:
            suffix = parts.task_suffix + parts.repair_suffix
            return ForgeKVRoute("kv_prefix", "restore_prefix", parts.prefix_hash, len(parts.stable_prefix), len(suffix), suffix, True, True, "ollama_native_context_restore", context.context_id, "ollama")
        if self.transport is not None:
            block = self.transport.lookup(model, tokenizer, parts.stable_prefix, system_prompt, preferred_engine=CacheEngine.OLLAMA)
            if block is not None:
                return ForgeKVRoute("kv_prefix", "restore_prefix", parts.prefix_hash, len(parts.stable_prefix), len(parts.task_suffix) + len(parts.repair_suffix), parts.task_suffix + parts.repair_suffix, True, False, "portable_kv_requires_runtime_injector", block.block_id, block.engine.value)
        return ForgeKVRoute("larger_model" if larger_model_available else "cold_ollama", "escalate" if larger_model_available else "cold_prefill", parts.prefix_hash, len(parts.stable_prefix), len(parts.task_suffix) + len(parts.repair_suffix), parts.stable_prefix + "\n" + parts.task_suffix + parts.repair_suffix, True, False, "no_compatible_prefix_state")

    def _emit(self, event_type: str, payload: Dict[str, Any], request: ForgeKVRequest) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event_type, dict(payload), request)
        except Exception:
            # Observability failure must not alter inference outcome.
            pass

    def submit(self, request: ForgeKVRequest, *, block: bool = False, timeout: float = 0.0) -> Future:
        if self._closed:
            raise RuntimeError("ForgeKVCoordinator is closed")
        request = request.sealed()
        future: Future = Future()
        job = _QueuedJob(request=request, future=future)
        try:
            self._queue.put(job, block=block, timeout=max(0.0, timeout) if block else None)
        except queue.Full as exc:
            with self._metrics_lock:
                self._metrics["queue_rejected"] += 1
            self._emit("forge.kv_queue_rejected", {"reason": "queue_full"}, request)
            future.set_exception(exc)
            return future
        with self._metrics_lock:
            self._metrics["submitted"] += 1
        self._emit("forge.kv_queued", {"queue_depth": self._queue.qsize()}, request)
        return future

    def run(self, request: ForgeKVRequest, *, timeout: float = 180.0) -> Dict[str, Any]:
        return self.submit(request, block=True, timeout=min(timeout, 5.0)).result(timeout=timeout)

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                if job.future.set_running_or_notify_cancel():
                    try:
                        result = self._execute(job.request)
                    except Exception as exc:
                        with self._metrics_lock:
                            self._metrics["failed"] += 1
                        self._emit("forge.kv_failed", {"error": str(exc)}, job.request)
                        job.future.set_exception(exc)
                    else:
                        with self._metrics_lock:
                            self._metrics["completed"] += 1
                        job.future.set_result(result)
            finally:
                self._queue.task_done()

    def _execute(self, request: ForgeKVRequest) -> Dict[str, Any]:
        identity_payload = {
            "model": request.model,
            "model_digest": request.model_digest,
            "tokenizer_hint": request.tokenizer_hint,
            "template": request.template,
            "prefix": request.prompt_prefix,
            "system": request.system_prompt,
            "options": dict(request.options),
            "workspace_id": request.workspace_id,
            "privacy_domain": request.privacy_domain,
            "runtime_version": request.runtime_version,
            "architecture": request.architecture,
            "quantization": request.quantization,
            "rope_settings": request.rope_settings,
            "policy_generation": request.policy_generation,
            "repository_fingerprint": request.repository_fingerprint,
        }
        reservation_id = _digest(identity_payload)
        owner = self.registry.reserve(reservation_id)
        if not owner:
            self.registry.wait(reservation_id, timeout=60.0)

        self._emit("forge.kv_lookup_started", {"cache_identity": reservation_id}, request)
        lookup_started = time.perf_counter()
        try:
            block = self.manager.get_or_create_context(
                request.model,
                request.prompt_prefix,
                request.system_prompt,
                model_digest=request.model_digest,
                tokenizer_hint=request.tokenizer_hint,
                template=request.template,
                options=request.options,
                compatibility={
                    "runtime_version": request.runtime_version,
                    "architecture": request.architecture,
                    "quantization": request.quantization,
                    "rope_settings": request.rope_settings,
                    "policy_generation": request.policy_generation,
                    "repository_fingerprint": request.repository_fingerprint,
                },
            )
            lookup_ms = (time.perf_counter() - lookup_started) * 1000.0
            self.registry.complete(reservation_id)
        except Exception as exc:
            self.registry.complete(reservation_id, error=str(exc))
            raise

        self._emit(
            "forge.kv_lookup_completed",
            {
                "cache_identity": reservation_id,
                "context_id": block.context_id,
                "native_context_available": block.native_context_available,
                "estimated_context_bytes": block.estimated_bytes,
                "lookup_ms": round(lookup_ms, 3),
            },
            request,
        )
        result = self.manager.generate_with_context(
            block,
            request.prompt,
            max_tokens=request.max_tokens,
            options=request.options,
        )
        economics = economics_from_result(result, lookup_ms=lookup_ms, context_bytes=block.estimated_bytes)
        payload = {
            "beast_object_type": "forge_kv_execution_result",
            "version": "1.0",
            "request_id": request.request_id,
            "task_class": request.task_class,
            "model": request.model,
            "cache_identity": reservation_id,
            "context": block.to_dict(),
            "inference": dict(result),
            "economics": economics.to_dict(),
            "workspace_id": request.workspace_id,
            "privacy_domain": request.privacy_domain,
            "authority": "context_only",
            "speculative_prefill": False,
            "route": {
                "stage": "kv_prefix" if result.get("native_context_supplied") else "warm_ollama" if result.get("reuse_mode") == "warm_model" else "cold_ollama",
                "action": "restore_prefix" if result.get("native_context_supplied") else "append_suffix" if result.get("reuse_mode") == "warm_model" else "cold_prefill",
                "prefix_chars": len(request.prompt_prefix),
                "suffix_chars": len(request.prompt),
                "suffix_only": bool(result.get("native_context_supplied")),
            },
            "performance_claims": claim_status(
                engine="ollama_api_generate_context",
                native_context_supplied=bool(result.get("native_context_supplied")),
            ),
        }
        self._emit("forge.kv_inference_completed", payload["economics"], request)
        return payload

    def state(self) -> Dict[str, Any]:
        with self._metrics_lock:
            metrics = dict(self._metrics)
        return {
            "beast_object_type": "forge_kv_coordinator_state",
            "version": "1.0",
            "workers": len(self._threads),
            "queue_capacity": self._queue.maxsize,
            "queue_depth": self._queue.qsize(),
            "metrics": metrics,
            "registry": self.registry.state(),
            "manager": self.manager.get_stats(),
            "authority": "context_coordination_only",
        }

    def close(self, *, wait: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        for _ in self._threads:
            self._queue.put(None)
        if wait:
            for thread in self._threads:
                thread.join(timeout=5.0)
