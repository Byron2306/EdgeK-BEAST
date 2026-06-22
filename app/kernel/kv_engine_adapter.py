"""Runtime KV engine adapter wrappers for Phase 7 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.kernel.kv_cache_transport import (
    CacheEngine,
    CacheLocation,
    CrossEngineKVCacheTransport,
)


@dataclass(frozen=True)
class KVEngineAdapterResult:
    adapter: str
    engine: str
    block_id: str
    registered: bool
    looked_up: bool
    payload_round_tripped: bool
    storage_persisted: bool
    network_manifest_ready: bool
    operations_logged: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "kv_engine_adapter_result",
            "version": "1.0",
            "adapter": self.adapter,
            "engine": self.engine,
            "block_id": self.block_id,
            "registered": self.registered,
            "looked_up": self.looked_up,
            "payload_round_tripped": self.payload_round_tripped,
            "storage_persisted": self.storage_persisted,
            "network_manifest_ready": self.network_manifest_ready,
            "operations_logged": self.operations_logged,
        }


class LocalKVEngineAdapter:
    """Live adapter boundary over the CPU KV transport implementation."""

    def __init__(self, transport: CrossEngineKVCacheTransport, engine: CacheEngine = CacheEngine.VLLM) -> None:
        self.transport = transport
        self.engine = engine

    def prepare_prefill(
        self,
        *,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        tensor_payload: bytes,
        tensor_format: str = "safetensors",
    ) -> KVEngineAdapterResult:
        block = self.transport.register_block(
            model=model,
            tokenizer=tokenizer,
            prompt_prefix=prompt_prefix,
            system_prompt=system_prompt,
            engine=self.engine,
            location=CacheLocation.CPU,
            precision="fp16",
            num_layers=2,
            num_heads=2,
            head_dim=8,
            seq_len=max(1, len(prompt_prefix.split())),
            size_bytes=len(tensor_payload),
            tensor_payload=tensor_payload,
            tensor_format=tensor_format,
            metadata={"adapter": self.__class__.__name__, "source_node": "local"},
        )
        found = self.transport.lookup(model, tokenizer, prompt_prefix, system_prompt, preferred_engine=self.engine)
        round_trip = self.transport.export_tensor_payload(block.block_id) == tensor_payload
        storage = self.transport.move(block.block_id, CacheLocation.STORAGE)
        network = self.transport.move(block.block_id, CacheLocation.NETWORK)
        manifest = self.transport.storage_dir / f"{block.block_id}.json"
        return KVEngineAdapterResult(
            adapter=self.__class__.__name__,
            engine=self.engine.value,
            block_id=block.block_id,
            registered=True,
            looked_up=found is not None,
            payload_round_tripped=round_trip,
            storage_persisted=storage,
            network_manifest_ready=network and manifest.is_file(),
            operations_logged=len(self.transport.operations),
        )
