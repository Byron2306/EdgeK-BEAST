"""Capability-gated Crystal Tongue v3 vector bridge.

The default Ollama API accepts text, not externally supplied hidden states or
KV tensors. This module therefore creates an explicit vector artifact and only
permits injection through a runtime adapter that declares the exact capability.
The built-in encoder is a deterministic feature-hash representation, not a
semantic model embedding; it is useful for identity and transport tests only.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from app.kernel.compute.crystal_tongue import CrystalTongueIR
from app.kernel.compute.crystal_tongue_codebook import CrystalTongueCodebook


VECTOR_VERSION = "V1"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CrystalVector:
    values: tuple[float, ...]
    dimensions: int
    dtype: str
    model: str
    tokenizer: str
    source_digest: str
    encoder: str = "feature_hash_not_semantic_embedding"

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "crystal_vector",
            "version": VECTOR_VERSION,
            "dimensions": self.dimensions,
            "dtype": self.dtype,
            "model": self.model,
            "tokenizer": self.tokenizer,
            "source_digest": self.source_digest,
            "encoder": self.encoder,
            "values": list(self.values),
            "portable_hidden_state": False,
        }


class CrystalVectorEncoder:
    """Create reproducible identity vectors without claiming learned semantics."""

    def __init__(self, dimensions: int = 64):
        if int(dimensions) < 8:
            raise ValueError("vector dimensions must be at least 8")
        self.dimensions = int(dimensions)

    def encode(self, ir: CrystalTongueIR, *, model: str, tokenizer: str) -> CrystalVector:
        source = "|".join((ir.encode(), model, tokenizer))
        values = [0.0] * self.dimensions
        for index in range(0, len(source), 2):
            digest = hashlib.sha256(f"{source}:{index}".encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            values[bucket] += sign * (1.0 + digest[5] / 255.0)
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return CrystalVector(tuple(round(value / norm, 8) for value in values), self.dimensions, "fp32", model, tokenizer, _digest(source))


@dataclass(frozen=True)
class VectorRuntimeCapability:
    runtime: str
    accepts_external_vectors: bool
    model: str
    tokenizer: str
    adapter_version: str
    reason: str


@dataclass(frozen=True)
class VectorRoute:
    mode: str
    injectable: bool
    reason: str
    vector_digest: str
    runtime: str
    fallback: str = "crystal_tongue_v2_text"

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "crystal_vector_route", "version": VECTOR_VERSION, **self.__dict__}


class CrystalVectorBridge:
    """Validate vector/runtime compatibility before any injection attempt."""

    def __init__(self, *, encoder: Optional[CrystalVectorEncoder] = None, injector: Optional[Callable[[CrystalVector], Mapping[str, Any]]] = None):
        self.encoder = encoder or CrystalVectorEncoder()
        self.injector = injector

    def prepare(
        self,
        ir: CrystalTongueIR,
        *,
        model: str,
        tokenizer: str,
        capability: Optional[VectorRuntimeCapability] = None,
    ) -> tuple[CrystalVector, VectorRoute]:
        vector = self.encoder.encode(ir, model=model, tokenizer=tokenizer)
        if capability is None:
            return vector, VectorRoute("text_fallback", False, "runtime_capability_not_declared", _digest(repr(vector.values)), "ollama")
        if not capability.accepts_external_vectors:
            return vector, VectorRoute("text_fallback", False, capability.reason or "runtime_rejects_external_vectors", _digest(repr(vector.values)), capability.runtime)
        if capability.model != model or capability.tokenizer != tokenizer:
            return vector, VectorRoute("text_fallback", False, "model_or_tokenizer_identity_mismatch", _digest(repr(vector.values)), capability.runtime)
        if self.injector is None:
            return vector, VectorRoute("text_fallback", False, "injector_not_configured", _digest(repr(vector.values)), capability.runtime)
        return vector, VectorRoute("vector_injection", True, "runtime_adapter_attested", _digest(repr(vector.values)), capability.runtime)

    def inject(self, vector: CrystalVector, route: VectorRoute) -> Mapping[str, Any]:
        if not route.injectable or self.injector is None:
            raise PermissionError("Crystal vector injection is not authorized by the runtime capability")
        result = self.injector(vector)
        if not isinstance(result, Mapping):
            raise TypeError("vector injector must return a mapping receipt")
        return {"status": "injected", "vector_digest": route.vector_digest, "runtime_receipt": dict(result)}


class LlamaCppVectorInjector:
    """Adapter for a BEAST-enabled llama.cpp runner, never stock Ollama.

    The endpoint is deliberately explicit because upstream llama.cpp and
    Ollama do not accept arbitrary hidden-state vectors. A custom runner must
    attest the model/tokenizer identity and return an injection receipt.
    """

    def __init__(self, endpoint: str | None = None, *, timeout_seconds: float = 5.0):
        self.endpoint = str(endpoint or os.environ.get("BEAST_LLAMA_CPP_VECTOR_ENDPOINT") or "").strip().rstrip("/")
        self.timeout_seconds = max(0.5, float(timeout_seconds))

    def capability(self, *, model: str, tokenizer: str) -> VectorRuntimeCapability:
        if not self.endpoint:
            return VectorRuntimeCapability("llama.cpp", False, model, tokenizer, "none", "custom vector endpoint not configured")
        return VectorRuntimeCapability("llama.cpp", True, model, tokenizer, "beast-vector-v1", "custom runner endpoint configured")

    def __call__(self, vector: CrystalVector) -> Mapping[str, Any]:
        if not self.endpoint:
            raise PermissionError("BEAST_LLAMA_CPP_VECTOR_ENDPOINT is not configured")
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(vector.to_dict(), separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-BEAST-Vector-Version": VECTOR_VERSION},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        if not isinstance(body, Mapping) or body.get("accepted") is not True:
            raise PermissionError("custom llama.cpp runner did not attest vector acceptance")
        return dict(body)
