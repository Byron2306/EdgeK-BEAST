"""Executable KV restore harness for BEAST crystal reuse."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from app.kernel.compute.kv_cache_transport import CacheEngine, CacheLocation, CrossEngineKVCacheTransport


class KVRestoreHarness:
    """Move a small engine-native KV payload through lookup, storage, and restore."""

    def __init__(self, transport: CrossEngineKVCacheTransport):
        self.transport = transport

    def run(self, *, model: str = "beast-kv-smoke", tokenizer: str = "beast-tokenizer") -> Dict[str, Any]:
        prompt_prefix = "BEAST restore harness prefix"
        system_prompt = "BEAST governed local restore"
        tensor_payload = b"BEAST_KV_TENSOR_PAYLOAD_V1"
        block = self.transport.register_block(
            model=model,
            tokenizer=tokenizer,
            prompt_prefix=prompt_prefix,
            system_prompt=system_prompt,
            engine=CacheEngine.OLLAMA,
            location=CacheLocation.CPU,
            precision="fp16",
            num_layers=1,
            num_heads=1,
            head_dim=8,
            seq_len=4,
            size_bytes=len(tensor_payload),
            metadata={"harness": "kv_restore", "engine_version": "local-smoke"},
            tensor_payload=tensor_payload,
            tensor_format="beast-smoke",
        )
        moved_to_storage = self.transport.move(block.block_id, CacheLocation.STORAGE)
        exported = self.transport.export_tensor_payload(block.block_id) or b""
        restored_to_cpu = self.transport.move(block.block_id, CacheLocation.CPU)
        restored = self.transport.lookup(
            model=model,
            tokenizer=tokenizer,
            prompt_prefix=prompt_prefix,
            system_prompt=system_prompt,
            preferred_engine=CacheEngine.OLLAMA,
        )
        engine_checks = {
            "ollama": {
                "status": "restored" if restored and exported == tensor_payload else "blocked",
                "block_id": block.block_id,
                "payload_sha256": "sha256:" + hashlib.sha256(exported).hexdigest() if exported else "",
            },
            "vllm": self._engine_config_status("VLLM_BASE_URL"),
            "sglang": self._engine_config_status("SGLANG_BASE_URL"),
        }
        receipt = {
            "beast_object_type": "beast_kv_restore_harness_receipt",
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "moved_to_storage": moved_to_storage,
            "restored_to_cpu": restored_to_cpu,
            "lookup_hit": bool(restored),
            "restored_block": restored.to_dict() if restored else None,
            "engine_checks": engine_checks,
            "transport_stats": self.transport.get_stats(),
            "claim_boundary": "This validates BEAST KV identity and tensor movement locally; live vLLM/SGLang restore requires configured engines.",
        }
        receipt["receipt_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(receipt, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return receipt

    @staticmethod
    def _engine_config_status(env_name: str) -> Dict[str, Any]:
        endpoint = os.environ.get(env_name, "")
        return {
            "status": "configured_pending_live_restore" if endpoint else "not_configured",
            "env": env_name,
            "endpoint_present": bool(endpoint),
            "endpoint": endpoint[:160],
        }
