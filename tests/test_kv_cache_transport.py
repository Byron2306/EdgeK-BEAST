"""Tests for Phase 7: Cross-Engine KV Cache Transport functionality."""

import pytest

from app.kernel.kv_cache_transport import (
    CrossEngineKVCacheTransport,
    CacheEngine,
    CacheLocation,
    KVCacheBlock,
)
from app.kernel.kv_engine_adapter import LocalKVEngineAdapter


def test_register_block_creates_cache_entry():
    """Test that registering a KV cache block creates an entry."""
    transport = CrossEngineKVCacheTransport()
    
    block = transport.register_block(
        model="llama-3-8b",
        tokenizer="tiktoken",
        prompt_prefix="system: You are helpful",
        system_prompt="You are helpful",
        engine=CacheEngine.VLLM,
        location=CacheLocation.GPU,
        precision="fp16",
        num_layers=32,
        num_heads=32,
        head_dim=128,
        seq_len=2048,
        size_bytes=1024 * 1024 * 100,  # 100MB
    )
    
    assert block.block_id.startswith("kv_")
    assert block.model == "llama-3-8b"
    assert block.engine == CacheEngine.VLLM
    assert block.pinned is False


def test_lookup_finds_matching_block():
    """Test that lookup finds a block with matching parameters."""
    transport = CrossEngineKVCacheTransport()
    
    transport.register_block(
        model="llama-3-8b",
        tokenizer="tiktoken",
        prompt_prefix="system: You are helpful",
        system_prompt="You are helpful",
        engine=CacheEngine.VLLM,
        location=CacheLocation.GPU,
        precision="fp16",
        num_layers=32,
        num_heads=32,
        head_dim=128,
        seq_len=2048,
        size_bytes=1024 * 1024 * 100,
    )
    
    found = transport.lookup(
        model="llama-3-8b",
        tokenizer="tiktoken",
        prompt_prefix="system: You are helpful",
        system_prompt="You are helpful",
    )
    
    assert found is not None
    assert found.access_count == 1  # Incremented on lookup


def test_lookup_returns_none_for_mismatch():
    """Test that lookup returns None when parameters don't match."""
    transport = CrossEngineKVCacheTransport()
    
    transport.register_block(
        model="llama-3-8b",
        tokenizer="tiktoken",
        prompt_prefix="system: You are helpful",
        system_prompt="You are helpful",
        engine=CacheEngine.VLLM,
        location=CacheLocation.GPU,
        precision="fp16",
        num_layers=32,
        num_heads=32,
        head_dim=128,
        seq_len=2048,
        size_bytes=1024 * 1024 * 100,
    )
    
    found = transport.lookup(
        model="mistral-7b",  # Different model
        tokenizer="tiktoken",
        prompt_prefix="system: You are helpful",
        system_prompt="You are helpful",
    )
    
    assert found is None


def test_pin_and_unpin():
    """Test pinning prevents eviction and unpinning allows it."""
    transport = CrossEngineKVCacheTransport(max_memory_bytes=1024)
    
    block = transport.register_block(
        model="test",
        tokenizer="test",
        prompt_prefix="pre",
        system_prompt="sys",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=8,
        num_heads=8,
        head_dim=64,
        seq_len=128,
        size_bytes=512,
    )
    
    assert transport.pin(block.block_id) is True
    assert transport.blocks[block.block_id].pinned is True
    
    assert transport.unpin(block.block_id) is True
    assert transport.blocks[block.block_id].pinned is False


def test_move_transports_block():
    """Test that move changes block location."""
    transport = CrossEngineKVCacheTransport()
    
    block = transport.register_block(
        model="test",
        tokenizer="test",
        prompt_prefix="pre",
        system_prompt="sys",
        engine=CacheEngine.VLLM,
        location=CacheLocation.GPU,
        precision="fp16",
        num_layers=8,
        num_heads=8,
        head_dim=64,
        seq_len=128,
        size_bytes=512,
    )
    
    assert transport.move(block.block_id, CacheLocation.CPU, CacheEngine.SGLANG) is True
    updated = transport.blocks[block.block_id]
    assert updated.location == CacheLocation.CPU
    assert updated.engine == CacheEngine.SGLANG


def test_compress_reduces_effective_size():
    """Test that compression marks the block and records ratio."""
    transport = CrossEngineKVCacheTransport()
    
    block = transport.register_block(
        model="test",
        tokenizer="test",
        prompt_prefix="pre",
        system_prompt="sys",
        engine=CacheEngine.VLLM,
        location=CacheLocation.GPU,
        precision="fp16",
        num_layers=8,
        num_heads=8,
        head_dim=64,
        seq_len=128,
        size_bytes=1024,
    )
    
    assert transport.compress(block.block_id, target_ratio=0.5) is True
    updated = transport.blocks[block.block_id]
    assert updated.compressed is True
    assert updated.compression_ratio == 0.5


def test_cleanup_evicts_unpinned_blocks():
    """Test that cleanup evicts unpinned blocks when over memory limit."""
    transport = CrossEngineKVCacheTransport(max_memory_bytes=1000)
    
    # Register 3 blocks of 400 bytes each (total 1200 > 1000)
    blocks = []
    for i in range(3):
        b = transport.register_block(
            model=f"m{i}",
            tokenizer="t",
            prompt_prefix=f"p{i}",
            system_prompt="s",
            engine=CacheEngine.OLLAMA,
            location=CacheLocation.CPU,
            precision="fp16",
            num_layers=4,
            num_heads=4,
            head_dim=32,
            seq_len=64,
            size_bytes=400,
        )
        blocks.append(b)
    
    # Pin the first one
    transport.pin(blocks[0].block_id)
    
    # Cleanup should evict unpinned blocks
    evicted = transport.cleanup()
    
    assert len(evicted) >= 1
    assert blocks[0].block_id not in evicted  # Pinned block not evicted


def test_stats_track_blocks_and_memory():
    """Test that stats correctly aggregate block counts and memory."""
    transport = CrossEngineKVCacheTransport(max_memory_bytes=10_000)
    
    transport.register_block(
        model="m1",
        tokenizer="t",
        prompt_prefix="p",
        system_prompt="s",
        engine=CacheEngine.VLLM,
        location=CacheLocation.GPU,
        precision="fp16",
        num_layers=8,
        num_heads=8,
        head_dim=64,
        seq_len=128,
        size_bytes=1024,
    )
    
    transport.register_block(
        model="m2",
        tokenizer="t",
        prompt_prefix="p",
        system_prompt="s",
        engine=CacheEngine.SGLANG,
        location=CacheLocation.CPU,
        precision="bf16",
        num_layers=8,
        num_heads=8,
        head_dim=64,
        seq_len=128,
        size_bytes=2048,
    )
    
    stats = transport.get_stats()
    
    assert stats["total_blocks"] == 2
    assert stats["total_size_bytes"] == 1024 + 2048
    assert "vllm" in stats["blocks_by_engine"]
    assert "sglang" in stats["blocks_by_engine"]
    assert stats["blocks_by_location"]["gpu"] == 1
    assert stats["blocks_by_location"]["cpu"] == 1


def test_engine_native_tensor_payload_round_trips_through_storage(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path)
    tensor = b"engine-native-kv-tensor-bytes"

    block = transport.register_block(
        model="llama",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
        engine=CacheEngine.VLLM,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=2,
        num_heads=2,
        head_dim=8,
        seq_len=16,
        size_bytes=999,
        tensor_payload=tensor,
        tensor_format="torch.save",
    )

    assert block.size_bytes == len(tensor)
    assert block.metadata["engine_native_tensor_payload"] is True
    assert transport.export_tensor_payload(block.block_id) == tensor
    assert transport.move(block.block_id, CacheLocation.STORAGE) is True
    assert (tmp_path / f"{block.block_id}.bin").read_bytes() == tensor

    transport.tensor_payloads.clear()
    assert transport.move(block.block_id, CacheLocation.CPU) is True
    assert transport.export_tensor_payload(block.block_id) == tensor


def test_import_tensor_payload_updates_existing_block_and_network_manifest(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path)
    block = transport.register_block(
        model="llama",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
        engine=CacheEngine.SGLANG,
        location=CacheLocation.CPU,
        precision="bf16",
        num_layers=2,
        num_heads=2,
        head_dim=8,
        seq_len=16,
        size_bytes=10,
    )

    assert transport.import_tensor_payload(block.block_id, b"payload", tensor_format="safetensors") is True
    assert transport.blocks[block.block_id].size_bytes == len(b"payload")
    assert transport.move(block.block_id, CacheLocation.NETWORK) is True
    manifest = (tmp_path / f"{block.block_id}.json").read_text()
    assert "tensor_payload_sha256" in manifest
    assert "transfer_" in manifest


def test_local_kv_engine_adapter_prepares_live_transport_payload(tmp_path):
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path)
    adapter = LocalKVEngineAdapter(transport, engine=CacheEngine.VLLM)

    result = adapter.prepare_prefill(
        model="llama",
        tokenizer="tok",
        prompt_prefix="prefix",
        system_prompt="system",
        tensor_payload=b"live-engine-kv",
    )

    payload = result.to_dict()
    assert payload["registered"] is True
    assert payload["looked_up"] is True
    assert payload["payload_round_tripped"] is True
    assert payload["storage_persisted"] is True
    assert payload["network_manifest_ready"] is True
    assert transport.get_stats()["operations_logged"] >= 4
