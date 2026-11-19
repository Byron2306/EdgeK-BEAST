from __future__ import annotations

from pathlib import Path

from app.kernel.compute.kv_transport import (
    CacheEngine,
    CacheLocation,
    CrossEngineKVCacheTransport,
    bind_default_transport,
    default_transport,
)


def test_plan_path_module_registers_and_reuses_ollama_prefix(tmp_path: Path) -> None:
    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    bind_default_transport(transport)
    prefix = "def increment(value, step=1):\n    return value + step\n"
    first = transport.register_block(
        model="qwen2.5:3b",
        tokenizer="qwen2.5:3b",
        prompt_prefix=prefix,
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=0,
        num_heads=0,
        head_dim=0,
        seq_len=16,
        size_bytes=len(prefix),
    )
    assert first.block_id
    hit = default_transport().lookup(
        "qwen2.5:3b",
        "qwen2.5:3b",
        prefix,
        "beast-agent-coder",
        preferred_engine=CacheEngine.OLLAMA,
    )
    assert hit is not None
    assert hit.block_id == first.block_id
    assert hit.prompt_prefix_hash == first.prompt_prefix_hash
    assert hit.access_count >= 1
    assert default_transport() is transport


def test_kv_cache_transport_alias_reexports_plan_path() -> None:
    from app.kernel.compute import kv_cache_transport as alias
    from app.kernel.compute import kv_transport as plan

    assert alias.CrossEngineKVCacheTransport is plan.CrossEngineKVCacheTransport
