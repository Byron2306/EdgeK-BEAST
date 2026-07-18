"""Phase 7: Cross-Engine KV Cache Transport — computed attention state as a transportable compute asset.

This implements the LMCache-style layer described in the roadmap:

"LMCache... stores and shares KV caches across vLLM and SGLang engines, with control APIs for
pinning, lookup, cleanup, movement, and compression across GPU, CPU, storage, and network layers.

That is basically: computed attention state becomes a transportable resource."

Key insight: KV caches are model-specific, tokenizer-specific, prompt-prefix-specific, precision-specific,
often engine-specific, large in memory, and sensitive to tiny prompt changes. So BEAST treats verified
semantic artifacts as the real durable currency, but still supports KV cache as a transportable asset
when the constraints can be met.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import mmap
import zlib
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import httpx

from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity


class CacheLocation(str, Enum):
    """Where a KV cache block resides."""
    GPU = "gpu"
    CPU = "cpu"
    STORAGE = "storage"
    NETWORK = "network"


class CacheEngine(str, Enum):
    """Supported inference engines."""
    VLLM = "vllm"
    SGLANG = "sglang"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class KVCacheBlock:
    """A pinned KV cache block with metadata for transport."""
    block_id: str
    model: str
    tokenizer: str
    prompt_prefix_hash: str  # SHA256 of the prompt prefix this cache was built for
    system_prompt_hash: str
    engine: CacheEngine
    location: CacheLocation
    precision: str  # "fp16", "bf16", "fp8", "int8"
    num_layers: int
    num_heads: int
    head_dim: int
    seq_len: int
    size_bytes: int
    pinned: bool = False
    compressed: bool = False
    compression_ratio: float = 1.0
    created_at: str = ""
    last_accessed_at: str = ""
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "kv_cache_block",
            "version": "1.0",
            "block_id": self.block_id,
            "model": self.model,
            "tokenizer": self.tokenizer,
            "prompt_prefix_hash": self.prompt_prefix_hash,
            "system_prompt_hash": self.system_prompt_hash,
            "engine": self.engine.value,
            "location": self.location.value,
            "precision": self.precision,
            "num_layers": self.num_layers,
            "num_heads": self.num_heads,
            "head_dim": self.head_dim,
            "seq_len": self.seq_len,
            "size_bytes": self.size_bytes,
            "pinned": self.pinned,
            "compressed": self.compressed,
            "compression_ratio": self.compression_ratio,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }

    def can_reuse_for(
        self,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
    ) -> bool:
        """Check if this cache block can be reused for a new request."""
        if self.model != model or self.tokenizer != tokenizer:
            return False
        prefix_hash = hashlib.sha256(prompt_prefix.encode()).hexdigest()
        sys_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
        return (
            self.prompt_prefix_hash == prefix_hash and
            self.system_prompt_hash == sys_hash
        )


@dataclass(frozen=True)
class KVCacheTransportOperation:
    """A transport operation (pin, move, compress, cleanup) on a cache block."""
    operation_id: str
    operation: str  # "pin" | "unpin" | "move" | "compress" | "decompress" | "cleanup" | "lookup"
    block_id: str
    source_location: Optional[CacheLocation] = None
    target_location: Optional[CacheLocation] = None
    source_engine: Optional[CacheEngine] = None
    target_engine: Optional[CacheEngine] = None
    bytes_moved: int = 0
    compression_ratio: float = 1.0
    success: bool = True
    error: Optional[str] = None
    timestamp: str = ""


class CrossEngineKVCacheTransport:
    """LMCache-style cross-engine KV cache transport layer.
    
    Provides control APIs for:
    - Pinning: keep a cache block resident (prevent eviction)
    - Lookup: find a cache block by (model, tokenizer, prompt_prefix, system_prompt)
    - Cleanup: evict unpinned blocks
    - Movement: migrate blocks across GPU/CPU/storage/network
    - Compression: reduce memory footprint
    
    Supports multiple engines: vLLM, SGLang, Ollama, LM Studio.
    """

    def __init__(
        self,
        max_memory_bytes: int = 8 * 1024 * 1024 * 1024,
        storage_dir: Optional[Path] = None,
    ):
        self.max_memory_bytes = max_memory_bytes
        self.storage_dir = storage_dir or Path(__file__).resolve().parents[2] / "data" / "kv_cache"
        self.blocks: Dict[str, KVCacheBlock] = {}
        self.tensor_payloads: Dict[str, bytes] = {}
        self.network_senders: Dict[str, Callable[[Dict[str, Any], bytes], Dict[str, Any]]] = {}
        self.operations: List[KVCacheTransportOperation] = []
        self._current_memory_bytes = 0

    def register_network_sender(
        self,
        endpoint: str,
        sender: Callable[[Dict[str, Any], bytes], Dict[str, Any]],
    ) -> None:
        """Register a real, authenticated byte-transfer implementation."""
        if not str(endpoint).strip():
            raise ValueError("network endpoint is required")
        self.network_senders[str(endpoint)] = sender

    def register_http_sender(self, endpoint: str, *, token: str, timeout_seconds: float = 10.0) -> None:
        """Register an authenticated HTTP peer that implements BEAST's receive contract."""
        target = str(endpoint).rstrip("/")
        if not target.startswith(("http://", "https://")):
            raise ValueError("KV HTTP transport endpoint must be an http(s) URL")
        if not token:
            raise ValueError("KV HTTP transport requires a non-empty peer token")

        def sender(manifest: Dict[str, Any], payload: bytes) -> Dict[str, Any]:
            response = httpx.post(
                target,
                json={"manifest": manifest, "payload_base64": base64.b64encode(payload).decode("ascii")},
                headers={"X-BEAST-KV-Token": token},
                timeout=max(0.1, min(float(timeout_seconds), 60.0)),
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("KV HTTP peer returned a non-object acknowledgement")
            return result

        self.register_network_sender(target, sender)

    def receive_network_transfer(self, manifest: Dict[str, Any], payload: bytes, *, max_bytes: int = 64 * 1024 * 1024) -> Dict[str, Any]:
        """Verify and durably accept one authenticated network transfer.

        Authentication is enforced by the hosting route. This method validates
        payload identity and dimensions before making a received block reusable.
        """
        if not isinstance(manifest, dict):
            raise ValueError("KV transfer manifest must be an object")
        payload = bytes(payload)
        if not payload or len(payload) > max(1, int(max_bytes)):
            raise ValueError("KV transfer payload is empty or exceeds the configured limit")
        checksum = "sha256:" + hashlib.sha256(payload).hexdigest()
        if manifest.get("beast_object_type") != "kv_cache_network_manifest":
            raise ValueError("unrecognized KV transfer manifest")
        if str(manifest.get("tensor_payload_sha256") or manifest.get("checksum_sha256") or "") != checksum:
            raise ValueError("KV transfer payload checksum mismatch")
        block_id = str(manifest.get("block_id") or "")
        if not block_id.startswith("kv_") or len(block_id) > 128:
            raise ValueError("invalid KV transfer block id")
        try:
            engine = CacheEngine(str(manifest.get("target_engine") or manifest.get("engine") or CacheEngine.UNKNOWN.value))
        except ValueError as exc:
            raise ValueError("invalid KV transfer engine") from exc
        required = ("model", "tokenizer", "prompt_prefix_hash", "system_prompt_hash", "precision")
        if any(not str(manifest.get(field) or "") for field in required):
            raise ValueError("KV transfer manifest is missing identity fields")
        existing = self.blocks.get(block_id)
        if existing and (
            existing.model != str(manifest["model"])
            or existing.prompt_prefix_hash != str(manifest["prompt_prefix_hash"])
            or existing.system_prompt_hash != str(manifest["system_prompt_hash"])
        ):
            raise ValueError("KV transfer block id conflicts with an existing identity")
        now = datetime.now(timezone.utc).isoformat()
        block = KVCacheBlock(
            block_id=block_id,
            model=str(manifest["model"]),
            tokenizer=str(manifest["tokenizer"]),
            prompt_prefix_hash=str(manifest["prompt_prefix_hash"]),
            system_prompt_hash=str(manifest["system_prompt_hash"]),
            engine=engine,
            location=CacheLocation.CPU,
            precision=str(manifest["precision"]),
            num_layers=max(0, int(manifest.get("num_layers") or 0)),
            num_heads=max(0, int(manifest.get("num_heads") or 0)),
            head_dim=max(0, int(manifest.get("head_dim") or 0)),
            seq_len=max(0, int(manifest.get("seq_len") or 0)),
            size_bytes=len(payload),
            pinned=bool(manifest.get("pinned", False)),
            created_at=str(manifest.get("created_at") or now),
            last_accessed_at=now,
            metadata={
                "tensor_payload_sha256": checksum,
                "tensor_payload_bytes": len(payload),
                "tensor_payload_format": str(manifest.get("tensor_payload_format") or "raw"),
                "engine_native_tensor_payload": True,
                "received_from_network": True,
                "source_node": str(manifest.get("source_node") or "unknown"),
                "source_transfer_id": str(manifest.get("transfer_id") or ""),
            },
        )
        self._current_memory_bytes += len(payload) - (existing.size_bytes if existing else 0)
        self.blocks[block_id] = block
        self.tensor_payloads[block_id] = payload
        if not self.move(block_id, CacheLocation.STORAGE):
            self.blocks.pop(block_id, None)
            self.tensor_payloads.pop(block_id, None)
            self._current_memory_bytes -= len(payload) - (existing.size_bytes if existing else 0)
            if existing is not None:
                self.blocks[block_id] = existing
            raise RuntimeError("received KV payload could not be persisted")
        self._record_operation(operation="receive_network", block_id=block_id, target_location=CacheLocation.STORAGE, target_engine=engine, bytes_moved=len(payload))
        return {"accepted": True, "block_id": block_id, "transfer_id": manifest.get("transfer_id"), "tensor_payload_sha256": checksum, "stored_location": CacheLocation.STORAGE.value}

    def has_reusable_payload(self, block_id: str) -> bool:
        """Return true only for blocks with verified engine-native bytes."""
        block = self.blocks.get(block_id)
        return bool(block and block.metadata.get("engine_native_tensor_payload") and self.export_tensor_payload(block_id) is not None)

    def _compute_block_id(
        self,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        engine: CacheEngine,
        precision: str,
    ) -> str:
        """Compute a stable block ID from cache parameters."""
        key = f"{model}:{tokenizer}:{prompt_prefix}:{system_prompt}:{engine.value}:{precision}"
        return "kv_" + hashlib.sha256(key.encode()).hexdigest()[:20]

    def register_block(
        self,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        engine: CacheEngine,
        location: CacheLocation,
        precision: str,
        num_layers: int,
        num_heads: int,
        head_dim: int,
        seq_len: int,
        size_bytes: int,
        metadata: Optional[Dict[str, Any]] = None,
        tensor_payload: Optional[bytes] = None,
        tensor_format: str = "raw",
    ) -> KVCacheBlock:
        """Register a new KV cache block with the transport layer."""
        block_id = self._compute_block_id(
            model, tokenizer, prompt_prefix, system_prompt, engine, precision
        )
        
        now = datetime.now(timezone.utc).isoformat()
        prefix_hash = hashlib.sha256(prompt_prefix.encode()).hexdigest()
        sys_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
        
        payload_metadata: Dict[str, Any] = {}
        if tensor_payload is not None:
            payload_metadata = {
                "tensor_payload_sha256": "sha256:" + hashlib.sha256(tensor_payload).hexdigest(),
                "tensor_payload_bytes": len(tensor_payload),
                "tensor_payload_format": tensor_format,
                "engine_native_tensor_payload": True,
            }
            size_bytes = len(tensor_payload)

        source_metadata = dict(metadata or {})
        identity = InferenceArtifactIdentity.from_prompts(
            model=model, tokenizer=tokenizer, prompt_prefix=prompt_prefix,
            system_prompt=system_prompt, engine=engine.value,
            engine_version=str(source_metadata.get("engine_version") or "unknown"),
            model_revision=str(source_metadata.get("model_revision") or "unknown"),
            tokenizer_revision=str(source_metadata.get("tokenizer_revision") or "unknown"),
            precision=precision,
            quantization=str(source_metadata.get("quantization") or "unknown"),
            attention_backend=str(source_metadata.get("attention_backend") or "unknown"),
            tensor_parallel_size=int(source_metadata.get("tensor_parallel_size") or 1),
            rope_config_hash=str(source_metadata.get("rope_config_hash") or "unknown"),
            policy_fingerprint=str(source_metadata.get("policy_fingerprint") or "unknown"),
            tool_schema_fingerprint=str(source_metadata.get("tool_schema_fingerprint") or "unknown"),
            skill_tree_fingerprint=str(source_metadata.get("skill_tree_fingerprint") or "unknown"),
            repository_fingerprint=str(source_metadata.get("repository_fingerprint") or "unknown"),
            tenant_privacy_class=str(source_metadata.get("tenant_privacy_class") or "local_private"),
        )
        block = KVCacheBlock(
            block_id=block_id,
            model=model,
            tokenizer=tokenizer,
            prompt_prefix_hash=prefix_hash,
            system_prompt_hash=sys_hash,
            engine=engine,
            location=location,
            precision=precision,
            num_layers=num_layers,
            num_heads=num_heads,
            head_dim=head_dim,
            seq_len=seq_len,
            size_bytes=size_bytes,
            created_at=now,
            last_accessed_at=now,
            metadata={
                **source_metadata, **payload_metadata,
                "inference_artifact_identity": identity.to_dict(),
                "inference_artifact_identity_hash": identity.identity_hash,
            },
        )
        
        self.blocks[block_id] = block
        if tensor_payload is not None:
            self.tensor_payloads[block_id] = bytes(tensor_payload)
        self._current_memory_bytes += size_bytes
        
        self._record_operation(
            operation="register",
            block_id=block_id,
            target_location=location,
            target_engine=engine,
            bytes_moved=size_bytes,
        )
        
        return block

    def export_tensor_payload(self, block_id: str) -> Optional[bytes]:
        """Return the exact engine-native tensor payload for a block, loading from storage if needed."""
        if block_id in self.tensor_payloads:
            return self._decode_payload(block_id, self.tensor_payloads[block_id])
        block_file = self.storage_dir / f"{block_id}.bin"
        if not block_file.is_file():
            return None
        try:
            payload = block_file.read_bytes()
        except OSError:
            return None
        block = self.blocks.get(block_id)
        decoded = self._decode_payload(block_id, payload)
        if decoded is None:
            return None
        expected = (block.metadata.get("tensor_payload_sha256") if block else None)
        if expected:
            actual = "sha256:" + hashlib.sha256(decoded).hexdigest()
            if actual != expected:
                return None
        self.tensor_payloads[block_id] = payload
        self._record_operation(operation="export_tensor", block_id=block_id, bytes_moved=len(payload))
        return decoded

    def _decode_payload(self, block_id: str, payload: bytes) -> Optional[bytes]:
        block = self.blocks.get(block_id)
        if block is None:
            return None
        if str(block.metadata.get("payload_compression") or "") != "zlib":
            return payload
        try:
            return zlib.decompress(payload)
        except zlib.error:
            self._record_operation(operation="export_tensor", block_id=block_id, error="zlib payload decompression failed")
            return None

    def get_mmap_buffer(self, block_id: str) -> Optional[Tuple[mmap.mmap, Any]]:
        """Return a memory-mapped buffer for the engine to read tensors directly."""
        block_file = self.storage_dir / f"{block_id}.bin"
        if not block_file.is_file():
            return None
        try:
            f = open(block_file, "rb")
            buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            self._record_operation(operation="mmap_buffer", block_id=block_id)
            return buf, f
        except Exception as e:
            logger.error(f"Failed to mmap block {block_id}: {e}")
            return None

    def import_tensor_payload(
        self,
        block_id: str,
        payload: bytes,
        *,
        tensor_format: str = "raw",
    ) -> bool:
        """Attach or replace the engine-native tensor payload for an existing block."""
        block = self.blocks.get(block_id)
        if not block:
            return False
        payload = bytes(payload)
        self.tensor_payloads[block_id] = payload
        metadata = {
            **block.metadata,
            "tensor_payload_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "tensor_payload_bytes": len(payload),
            "tensor_payload_format": tensor_format,
            "engine_native_tensor_payload": True,
        }
        updated = KVCacheBlock(
            block_id=block.block_id,
            model=block.model,
            tokenizer=block.tokenizer,
            prompt_prefix_hash=block.prompt_prefix_hash,
            system_prompt_hash=block.system_prompt_hash,
            engine=block.engine,
            location=block.location,
            precision=block.precision,
            num_layers=block.num_layers,
            num_heads=block.num_heads,
            head_dim=block.head_dim,
            seq_len=block.seq_len,
            size_bytes=len(payload),
            pinned=block.pinned,
            compressed=block.compressed,
            compression_ratio=block.compression_ratio,
            created_at=block.created_at,
            last_accessed_at=datetime.now(timezone.utc).isoformat(),
            access_count=block.access_count,
            metadata=metadata,
        )
        self._current_memory_bytes += len(payload) - block.size_bytes
        self.blocks[block_id] = updated
        self._record_operation(operation="import_tensor", block_id=block_id, bytes_moved=len(payload))
        return True

    def lookup(
        self,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        preferred_engine: Optional[CacheEngine] = None,
        preferred_location: Optional[CacheLocation] = None,
        identity_hash: Optional[str] = None,
    ) -> Optional[KVCacheBlock]:
        """Look up a reusable KV cache block.
        
        Returns the best match (pinned > compressed > recently used) or None.
        """
        prefix_hash = hashlib.sha256(prompt_prefix.encode()).hexdigest()
        sys_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
        
        candidates = [
            b for b in self.blocks.values()
            if b.model == model
            and b.tokenizer == tokenizer
            and b.prompt_prefix_hash == prefix_hash
            and b.system_prompt_hash == sys_hash
        ]
        
        if not candidates:
            return None
        
        # Filter by engine/location if specified
        if preferred_engine:
            candidates = [c for c in candidates if c.engine == preferred_engine]
        if preferred_location:
            candidates = [c for c in candidates if c.location == preferred_location]
        if identity_hash:
            candidates = [c for c in candidates if c.metadata.get("inference_artifact_identity_hash") == identity_hash]
        
        if not candidates:
            return None
        
        # Prefer pinned, then recently accessed, then least compressed
        candidates.sort(key=lambda b: (
            not b.pinned,  # pinned first
            -b.access_count,  # higher access count first
            b.compression_ratio,  # less compressed first
        ))
        
        best = candidates[0]
        
        # Update access stats (immutable update)
        updated = KVCacheBlock(
            block_id=best.block_id,
            model=best.model,
            tokenizer=best.tokenizer,
            prompt_prefix_hash=best.prompt_prefix_hash,
            system_prompt_hash=best.system_prompt_hash,
            engine=best.engine,
            location=best.location,
            precision=best.precision,
            num_layers=best.num_layers,
            num_heads=best.num_heads,
            head_dim=best.head_dim,
            seq_len=best.seq_len,
            size_bytes=best.size_bytes,
            pinned=best.pinned,
            compressed=best.compressed,
            compression_ratio=best.compression_ratio,
            created_at=best.created_at,
            last_accessed_at=datetime.now(timezone.utc).isoformat(),
            access_count=best.access_count + 1,
            metadata=best.metadata,
        )
        self.blocks[best.block_id] = updated
        
        self._record_operation(
            operation="lookup",
            block_id=best.block_id,
            target_location=best.location,
            target_engine=best.engine,
        )
        
        return updated

    def pin(self, block_id: str) -> bool:
        """Pin a cache block to prevent eviction."""
        block = self.blocks.get(block_id)
        if not block:
            return False
        
        if block.pinned:
            return True  # Already pinned
        
        updated = KVCacheBlock(
            block_id=block.block_id,
            model=block.model,
            tokenizer=block.tokenizer,
            prompt_prefix_hash=block.prompt_prefix_hash,
            system_prompt_hash=block.system_prompt_hash,
            engine=block.engine,
            location=block.location,
            precision=block.precision,
            num_layers=block.num_layers,
            num_heads=block.num_heads,
            head_dim=block.head_dim,
            seq_len=block.seq_len,
            size_bytes=block.size_bytes,
            pinned=True,
            compressed=block.compressed,
            compression_ratio=block.compression_ratio,
            created_at=block.created_at,
            last_accessed_at=block.last_accessed_at,
            access_count=block.access_count,
            metadata=block.metadata,
        )
        self.blocks[block_id] = updated
        
        self._record_operation(operation="pin", block_id=block_id)
        return True

    def unpin(self, block_id: str) -> bool:
        """Unpin a cache block, making it eligible for cleanup."""
        block = self.blocks.get(block_id)
        if not block:
            return False
        
        if not block.pinned:
            return True
        
        updated = KVCacheBlock(
            block_id=block.block_id,
            model=block.model,
            tokenizer=block.tokenizer,
            prompt_prefix_hash=block.prompt_prefix_hash,
            system_prompt_hash=block.system_prompt_hash,
            engine=block.engine,
            location=block.location,
            precision=block.precision,
            num_layers=block.num_layers,
            num_heads=block.num_heads,
            head_dim=block.head_dim,
            seq_len=block.seq_len,
            size_bytes=block.size_bytes,
            pinned=False,
            compressed=block.compressed,
            compression_ratio=block.compression_ratio,
            created_at=block.created_at,
            last_accessed_at=block.last_accessed_at,
            access_count=block.access_count,
            metadata=block.metadata,
        )
        self.blocks[block_id] = updated
        
        self._record_operation(operation="unpin", block_id=block_id)
        return True

    def move(
        self,
        block_id: str,
        target_location: CacheLocation,
        target_engine: Optional[CacheEngine] = None,
    ) -> bool:
        """Move a cache block to a different location (CPU-first implementation).
        
        Since this system runs on CPU-only hosts (no GPU), movement is between:
        - CPU (in-memory dict)
        - STORAGE (serialized to disk under data/kv_cache/)
        - NETWORK (registered authenticated sender plus transfer receipt)
        
        This is a real data movement on CPU, not a simulation.
        GPU↔CPU transfers are explicitly out of scope on this host.
        """
        block = self.blocks.get(block_id)
        if not block:
            return False
        
        if block.location == target_location and (target_engine is None or block.engine == target_engine):
            return True  # Already there
        
        new_engine = target_engine or block.engine
        tensor_payload = self.tensor_payloads.get(block_id)
        bytes_moved = len(tensor_payload or b"")
        
        # Real CPU movement
        storage_dir = self.storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        block_file = storage_dir / f"{block_id}.bin"
        manifest_file = storage_dir / f"{block_id}.json"
        
        try:
            if target_location == CacheLocation.STORAGE:
                if tensor_payload is None:
                    tensor_payload = self.export_tensor_payload(block_id)
                if tensor_payload is None:
                    raise ValueError("cannot persist a KV block without exact engine-native tensor payload")
                payload = {
                    "block": block.to_dict(),
                    "payload_size": len(tensor_payload),
                    "note": "Engine-native KV tensor payload persisted to disk",
                }
                manifest_file.write_text(json.dumps(payload, indent=2))
                block_file.write_bytes(tensor_payload)
                bytes_moved = len(tensor_payload)
            elif target_location == CacheLocation.CPU:
                if block_file.exists() and block_id not in self.tensor_payloads:
                    loaded = block_file.read_bytes()
                    decoded = self._decode_payload(block_id, loaded)
                    if decoded is None:
                        raise ValueError("stored tensor payload could not be decoded")
                    if block.metadata.get("tensor_payload_sha256"):
                        actual = "sha256:" + hashlib.sha256(decoded).hexdigest()
                        if actual != block.metadata.get("tensor_payload_sha256"):
                            raise ValueError("stored tensor payload checksum mismatch")
                    self.tensor_payloads[block_id] = loaded
            elif target_location == CacheLocation.NETWORK:
                endpoint = str(block.metadata.get("target_endpoint") or "")
                sender = self.network_senders.get(endpoint)
                if not endpoint or sender is None:
                    raise ValueError("no registered network sender for KV transfer endpoint")
                if tensor_payload is None:
                    tensor_payload = self.export_tensor_payload(block_id)
                if tensor_payload is None:
                    raise ValueError("cannot transfer a KV block without exact engine-native tensor payload")
                checksum = "sha256:" + hashlib.sha256(tensor_payload).hexdigest()
                manifest = {
                    "beast_object_type": "kv_cache_network_manifest",
                    "version": "1.0",
                    "block_id": block_id,
                    "model": block.model,
                    "tokenizer": block.tokenizer,
                    "prompt_prefix_hash": block.prompt_prefix_hash,
                    "system_prompt_hash": block.system_prompt_hash,
                    "engine": block.engine.value,
                    "target_engine": new_engine.value,
                    "precision": block.precision,
                    "num_layers": block.num_layers,
                    "num_heads": block.num_heads,
                    "head_dim": block.head_dim,
                    "seq_len": block.seq_len,
                    "size_bytes": len(tensor_payload),
                    "compressed": block.compressed,
                    "compression_ratio": block.compression_ratio,
                    "pinned": block.pinned,
                    "created_at": block.created_at,
                    "last_accessed_at": block.last_accessed_at,
                    "access_count": block.access_count,
                    "source_node": block.metadata.get("source_node", "unknown"),
                    "target_endpoint": endpoint,
                    "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
                    "checksum_sha256": checksum,
                    "tensor_payload_sha256": checksum,
                    "tensor_payload_format": block.metadata.get("tensor_payload_format", "raw"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "transfer_pending",
                }
                acknowledgement = sender(dict(manifest), tensor_payload)
                if not isinstance(acknowledgement, dict) or not acknowledgement.get("accepted"):
                    raise ValueError("network sender did not acknowledge KV transfer")
                if str(acknowledgement.get("tensor_payload_sha256") or "") != checksum:
                    raise ValueError("network sender acknowledgement checksum mismatch")
                manifest["status"] = "transferred"
                manifest["acknowledgement"] = acknowledgement
                manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True))
                bytes_moved = len(tensor_payload)
        except Exception as e:
            self._record_operation(
                operation="move",
                block_id=block_id,
                source_location=block.location,
                target_location=target_location,
                source_engine=block.engine,
                target_engine=new_engine,
                bytes_moved=0,
                error=str(e),
            )
            return False
        
        updated = KVCacheBlock(
            block_id=block.block_id,
            model=block.model,
            tokenizer=block.tokenizer,
            prompt_prefix_hash=block.prompt_prefix_hash,
            system_prompt_hash=block.system_prompt_hash,
            engine=new_engine,
            location=target_location,
            precision=block.precision,
            num_layers=block.num_layers,
            num_heads=block.num_heads,
            head_dim=block.head_dim,
            seq_len=block.seq_len,
            size_bytes=block.size_bytes,
            pinned=block.pinned,
            compressed=block.compressed,
            compression_ratio=block.compression_ratio,
            created_at=block.created_at,
            last_accessed_at=datetime.now(timezone.utc).isoformat(),
            access_count=block.access_count,
            metadata={
                **block.metadata,
                "moved_from": block.location.value,
                "cpu_movement": True,
                "moved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.blocks[block_id] = updated
        
        self._record_operation(
            operation="move",
            block_id=block_id,
            source_location=block.location,
            target_location=target_location,
            source_engine=block.engine,
            target_engine=new_engine,
            bytes_moved=bytes_moved,
        )
        return True

    def compress(self, block_id: str, target_ratio: float = 0.5) -> bool:
        """Losslessly compress exact KV bytes for storage transport.

        This is not fake quantization: the original engine-native payload is
        restored by :meth:`export_tensor_payload` before it can be reused.
        """
        block = self.blocks.get(block_id)
        if not block or block.compressed:
            return False
        payload = self.export_tensor_payload(block_id)
        if payload is None:
            self._record_operation(operation="compress", block_id=block_id, error="no exact tensor payload available")
            return False
        compressed_payload = zlib.compress(payload)
        if len(compressed_payload) >= len(payload):
            self._record_operation(operation="compress", block_id=block_id, error="zlib produced no storage reduction")
            return False
        self.tensor_payloads[block_id] = compressed_payload
        compressed_size = len(compressed_payload)
        achieved_ratio = compressed_size / len(payload)
        
        updated = KVCacheBlock(
            block_id=block.block_id,
            model=block.model,
            tokenizer=block.tokenizer,
            prompt_prefix_hash=block.prompt_prefix_hash,
            system_prompt_hash=block.system_prompt_hash,
            engine=block.engine,
            location=block.location,
            precision=block.precision,
            num_layers=block.num_layers,
            num_heads=block.num_heads,
            head_dim=block.head_dim,
            seq_len=block.seq_len,
            size_bytes=block.size_bytes,
            pinned=block.pinned,
            compressed=True,
            compression_ratio=round(achieved_ratio, 4),
            created_at=block.created_at,
            last_accessed_at=datetime.now(timezone.utc).isoformat(),
            access_count=block.access_count,
            metadata={
                **block.metadata,
                "compressed_size_bytes": compressed_size,
                "payload_compression": "zlib",
                "uncompressed_payload_bytes": len(payload),
            },
        )
        self.blocks[block_id] = updated
        
        self._record_operation(
            operation="compress",
            block_id=block_id,
            compression_ratio=achieved_ratio,
            bytes_moved=block.size_bytes - compressed_size,
        )
        return True

    def cleanup(self, force: bool = False) -> List[str]:
        """Evict unpinned blocks to free memory. Returns list of evicted block IDs."""
        if not force and self._current_memory_bytes <= self.max_memory_bytes:
            return []
        
        # Evict unpinned blocks, oldest first
        candidates = [
            (bid, b) for bid, b in self.blocks.items()
            if not b.pinned
        ]
        candidates.sort(key=lambda x: x[1].last_accessed_at)
        
        evicted: List[str] = []
        for bid, block in candidates:
            if force or self._current_memory_bytes > self.max_memory_bytes:
                self._current_memory_bytes -= block.size_bytes
                del self.blocks[bid]
                evicted.append(bid)
                self._record_operation(operation="cleanup", block_id=bid, bytes_moved=block.size_bytes)
        
        return evicted

    def get_stats(self) -> Dict[str, Any]:
        """Return transport layer statistics."""
        total_blocks = len(self.blocks)
        pinned = sum(1 for b in self.blocks.values() if b.pinned)
        compressed = sum(1 for b in self.blocks.values() if b.compressed)
        reusable = sum(1 for block_id in self.blocks if self.has_reusable_payload(block_id))
        total_bytes = sum(b.size_bytes for b in self.blocks.values())
        compressed_bytes = sum(
            int(b.size_bytes * b.compression_ratio) for b in self.blocks.values() if b.compressed
        )
        
        by_location: Dict[str, int] = {}
        by_engine: Dict[str, int] = {}
        for b in self.blocks.values():
            by_location[b.location.value] = by_location.get(b.location.value, 0) + 1
            by_engine[b.engine.value] = by_engine.get(b.engine.value, 0) + 1
        
        return {
            "beast_object_type": "kv_cache_transport_stats",
            "version": "1.0",
            "total_blocks": total_blocks,
            "pinned_blocks": pinned,
            "compressed_blocks": compressed,
            "reusable_blocks": reusable,
            "metadata_only_blocks": total_blocks - reusable,
            "total_size_bytes": total_bytes,
            "compressed_size_bytes": compressed_bytes,
            "memory_utilization": total_bytes / self.max_memory_bytes if self.max_memory_bytes > 0 else 0.0,
            "blocks_by_location": by_location,
            "blocks_by_engine": by_engine,
            "operations_logged": len(self.operations),
            "max_memory_bytes": self.max_memory_bytes,
            "storage_dir": str(self.storage_dir),
            "network_sender_count": len(self.network_senders),
        }

    def _record_operation(
        self,
        operation: str,
        block_id: str,
        source_location: Optional[CacheLocation] = None,
        target_location: Optional[CacheLocation] = None,
        source_engine: Optional[CacheEngine] = None,
        target_engine: Optional[CacheEngine] = None,
        bytes_moved: int = 0,
        compression_ratio: float = 1.0,
        error: Optional[str] = None,
    ) -> None:
        """Record a transport operation for audit/logging."""
        op = KVCacheTransportOperation(
            operation_id=f"op_{len(self.operations):06d}",
            operation=operation,
            block_id=block_id,
            source_location=source_location,
            target_location=target_location,
            source_engine=source_engine,
            target_engine=target_engine,
            bytes_moved=bytes_moved,
            compression_ratio=compression_ratio,
            error=error,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.operations.append(op)
        
        # Keep only last 1000 operations
        if len(self.operations) > 1000:
            self.operations = self.operations[-1000:]
