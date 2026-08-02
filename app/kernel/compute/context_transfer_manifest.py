from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canon(value)).hexdigest()


@dataclass(frozen=True)
class ContextCompatibilityEnvelope:
    engine: str
    engine_version: str
    model_digest: str
    tokenizer_digest: str
    architecture: str
    template_digest: str
    system_digest: str
    options_digest: str
    num_ctx: int
    cpu_architecture: str
    workspace_id: str
    privacy_domain: str
    source_state_digest: str

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name == "num_ctx":
                if not isinstance(value, int) or value <= 0:
                    raise ValueError("num_ctx must be positive")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")

    @property
    def digest(self) -> str:
        return _digest(asdict(self))

    def compare(self, other: "ContextCompatibilityEnvelope") -> tuple[bool, tuple[str, ...]]:
        mismatches = tuple(
            name for name in asdict(self)
            if getattr(self, name) != getattr(other, name)
        )
        return (not mismatches, mismatches)


@dataclass(frozen=True)
class ContextTransferManifest:
    transfer_id: str
    source_node_id: str
    context_digest: str
    context_size_bytes: int
    context_token_count: int
    envelope: ContextCompatibilityEnvelope
    representation: str = "ollama_context_tokens"
    portable: bool = False
    engine_native: bool = True
    authority: str = "context_only"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.transfer_id or not self.source_node_id:
            raise ValueError("transfer and source node IDs are required")
        if not self.context_digest.startswith("sha256:"):
            raise ValueError("context_digest must be sha256")
        if self.context_size_bytes <= 0 or self.context_token_count <= 0:
            raise ValueError("context size and token count must be positive")
        if self.representation != "ollama_context_tokens":
            raise ValueError("R7 only supports Ollama-native token contexts")
        if self.portable:
            raise ValueError("production portability must remain false in R7")
        if not self.engine_native or self.authority != "context_only":
            raise ValueError("invalid representation or authority")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["envelope_digest"] = self.envelope.digest
        return _digest(payload)
