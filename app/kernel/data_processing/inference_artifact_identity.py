"""Canonical identity for reusable inference state.

This module deliberately contains no engine code.  Ollama contexts, durable
prefill records, engine-native KV blocks, Forge qualification and Commons
descriptors all use the same fail-closed identity contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class InferenceArtifactIdentity:
    model: str
    tokenizer: str
    prompt_prefix_hash: str
    system_prompt_hash: str
    engine: str = "unknown"
    engine_version: str = "unknown"
    model_revision: str = "unknown"
    tokenizer_revision: str = "unknown"
    precision: str = "unknown"
    quantization: str = "unknown"
    attention_backend: str = "unknown"
    tensor_parallel_size: int = 1
    rope_config_hash: str = "unknown"
    policy_fingerprint: str = "unknown"
    tool_schema_fingerprint: str = "unknown"
    skill_tree_fingerprint: str = "unknown"
    repository_fingerprint: str = "unknown"
    tenant_privacy_class: str = "local_private"

    @classmethod
    def from_prompts(
        cls,
        *,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        **compatibility: Any,
    ) -> "InferenceArtifactIdentity":
        allowed = set(cls.__dataclass_fields__) - {
            "model", "tokenizer", "prompt_prefix_hash", "system_prompt_hash"
        }
        clean = {key: value for key, value in compatibility.items() if key in allowed}
        return cls(
            model=str(model),
            tokenizer=str(tokenizer),
            prompt_prefix_hash=_digest(prompt_prefix),
            system_prompt_hash=_digest(system_prompt),
            **clean,
        )

    @property
    def identity_hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def compatible_with(self, other: "InferenceArtifactIdentity") -> bool:
        """Require exact compatibility; unknown values are values, not wildcards."""
        return self.identity_hash == other.identity_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "inference_artifact_identity",
            "version": "1.0",
            **asdict(self),
            "identity_hash": self.identity_hash,
        }

