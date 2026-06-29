import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict

def digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class LocalKVCompatibilityProfile:
    model: str
    tokenizer: str
    engine: str
    quantization: str
    prompt_prefix_hash: str
    system_prompt_hash: str
    repo_fingerprint: str
    cache_format: str = "beast_local_kv_v1"

    def to_dict(self):
        return asdict(self)

    def compatible_with(self, other: "LocalKVCompatibilityProfile") -> bool:
        return self.to_dict() == other.to_dict()

class LocalPrefixKVStore:
    def __init__(self, gateway):
        self.gateway = gateway

    def profile_for_request(self, request, *, engine: str, quantization: str = "q4") -> LocalKVCompatibilityProfile:
        return LocalKVCompatibilityProfile(
            model=request.model,
            tokenizer=request.tokenizer,
            engine=engine,
            quantization=quantization,
            prompt_prefix_hash=digest_text(request.effective_prompt_prefix),
            system_prompt_hash=digest_text(request.system_prompt or ""),
            repo_fingerprint=request.repo_fingerprint or "",
        )

    def register_prefill(self, request, *, engine: str, metadata: Dict[str, Any]):
        profile = self.profile_for_request(request, engine=engine)
        return self.gateway.register_prefill_crystal(
            request,
            kv_cache_metadata={
                "engine": engine,
                "local_cpu": True,
                "metadata": {
                    **(metadata or {}),
                    "local_kv_compatibility_profile": profile.to_dict(),
                },
            },
            compatibility={
                "engine": profile.engine,
                "quantization": profile.quantization,
                "repository_fingerprint": profile.repo_fingerprint or "unknown",
            },
        )

    def register_block(self, request, *, engine: str, tensor_payload: bytes | None = None, metadata: Dict[str, Any] | None = None):
        profile = self.profile_for_request(request, engine=engine)
        return self.gateway.register_kv_block(
            request,
            engine=engine,
            location="cpu",
            precision="q4",
            metadata={
                "compatibility": profile.to_dict(),
                **(metadata or {}),
            },
            tensor_payload=tensor_payload,
        )
