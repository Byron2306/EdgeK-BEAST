"""Acceptance tests for the crystal-backed KV transport STORAGE tier.

These encode what the census said the old raw-file tier lacked:

1. storage writes land in the content-addressed crystal store, not raw ``.bin``;
2. the exact bytes round-trip through ``move(STORAGE)`` / ``move(CPU)``;
3. a restart (fresh transport + fresh tier over the same root) restores;
4. duplicate payloads are stored once (chunk dedup accounted in the receipt);
5. a forced cleanup revokes the durable manifest, so it cannot be restored;
6. identity digests are *derived* and labelled, never claimed as native
   cross-engine portability.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.kernel.compute.kv_crystal_tier import CrystalKVTier
from app.kernel.compute.kv_transport import (
    CacheEngine,
    CacheLocation,
    CrossEngineKVCacheTransport,
)

PAYLOAD_BYTES = 16 * 1024


def payload(seed: int = 0) -> bytes:
    return bytes([(seed * 17 + offset) % 251 for offset in range(PAYLOAD_BYTES)])


def make_block(transport: CrossEngineKVCacheTransport, *, seed: int = 0, seq_len: int = 16):
    body = payload(seed)
    return transport.register_block(
        model="qwen2.5-coder:7b",
        tokenizer="qwen2.5-coder:7b",
        prompt_prefix=f"def f{seed}(x):\n    return x\n",
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=28,
        num_heads=28,
        head_dim=128,
        seq_len=seq_len,
        size_bytes=PAYLOAD_BYTES,
        tensor_payload=body,
    ), body


def make_transport(tmp_path: Path, tier: CrystalKVTier | None) -> CrossEngineKVCacheTransport:
    return CrossEngineKVCacheTransport(
        storage_dir=tmp_path / "kv",
        crystal_tier=tier,
    )


def tier_at(tmp_path: Path) -> CrystalKVTier:
    return CrystalKVTier(tmp_path / "crystal", privacy_domain="test_kv", ttl_seconds=3600)


def test_storage_move_writes_crystal_not_raw_payload(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, body = make_block(transport)

    assert transport.move(block.block_id, CacheLocation.STORAGE) is True

    # The raw .bin must not exist: the payload lives in the crystal CAS.
    assert not (tmp_path / "kv" / f"{block.block_id}.bin").exists()
    manifest_file = tmp_path / "kv" / f"{block.block_id}.json"
    assert manifest_file.exists()
    import json

    manifest = json.loads(manifest_file.read_text())
    assert manifest["storage_backend"] == "crystal_kv_index"
    assert manifest["crystal_receipt"]["ok"] is True

    stats = tier.stats()
    assert stats["manifests"] == 1
    assert stats["kv_bytes"] == len(body)
    assert stats["cross_engine_portable"] is False
    assert stats["native_kv_portability_claimed"] is False


def test_storage_then_cpu_round_trips_exact_bytes(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, body = make_block(transport)

    assert transport.move(block.block_id, CacheLocation.STORAGE) is True
    # Drop the in-memory copy the way an eviction would.
    transport.tensor_payloads.pop(block.block_id, None)

    assert transport.move(block.block_id, CacheLocation.CPU) is True
    restored = transport.export_tensor_payload(block.block_id)
    assert restored == body


def test_restart_restores_from_crystal_cas(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, body = make_block(transport)
    assert transport.move(block.block_id, CacheLocation.STORAGE) is True

    # Simulate a process restart: new tier object, new transport, same roots.
    rebooted = make_transport(tmp_path, tier_at(tmp_path))
    # Re-register the same metadata (no payload) so identity matches exactly.
    again = rebooted.register_block(
        model=block.model,
        tokenizer=block.tokenizer,
        prompt_prefix=f"def f0(x):\n    return x\n",
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.STORAGE,
        precision="fp16",
        num_layers=28,
        num_heads=28,
        head_dim=128,
        seq_len=16,
        size_bytes=PAYLOAD_BYTES,
    )
    assert again.block_id == block.block_id
    assert rebooted.move(again.block_id, CacheLocation.CPU) is True
    assert rebooted.export_tensor_payload(again.block_id) == body


def test_duplicate_payload_is_deduped(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block_a, body = make_block(transport, seed=0)
    # Same bytes, different prefix => different block_id, same chunk digests.
    block_b, _ = make_block(transport, seed=0)
    block_b = transport.register_block(
        model="qwen2.5-coder:7b",
        tokenizer="qwen2.5-coder:7b",
        prompt_prefix="different prefix\n",
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=28,
        num_heads=28,
        head_dim=128,
        seq_len=16,
        size_bytes=PAYLOAD_BYTES,
        tensor_payload=body,
    )

    assert transport.move(block_a.block_id, CacheLocation.STORAGE) is True
    first = tier.stats()["unique_chunk_bytes"]
    assert transport.move(block_b.block_id, CacheLocation.STORAGE) is True
    second = tier.stats()["unique_chunk_bytes"]
    assert second == first, "identical bytes must not be stored twice"


def test_forced_cleanup_evicts_storage_and_frees_bytes(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, body = make_block(transport)
    assert transport.move(block.block_id, CacheLocation.STORAGE) is True
    assert tier.stats()["manifests"] == 1
    assert tier.stats()["unique_chunk_bytes"] == len(body)

    revoked = transport.cleanup(force=True)
    assert block.block_id in revoked
    stats = tier.stats()
    assert stats["manifests"] == 0
    assert stats["unique_chunk_bytes"] == 0, "eviction must release chunk files, not just the manifest"

    # A fresh tier over the same root must refuse to serve it.
    rebooted = tier_at(tmp_path)
    assert rebooted.stats()["manifests"] == 0
    restored, receipt = rebooted.restore(block)
    assert restored is None
    assert receipt.ok is False


def test_revoke_leaves_tombstone_that_survives_restart(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, body = make_block(transport)
    assert transport.move(block.block_id, CacheLocation.STORAGE) is True

    receipt = tier.revoke(block, reason="privacy deletion")
    assert receipt.ok is True

    # Bytes are retained (tombstoned), but a fresh tier refuses to serve them.
    rebooted = tier_at(tmp_path)
    restored, lookup = rebooted.restore(block)
    assert restored is None
    assert lookup.ok is False
    assert "revok" in lookup.reason.lower()


def test_derived_identity_is_labelled_not_claimed(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, _ = make_block(transport)
    fingerprint = tier.fingerprint_for(block)
    assert fingerprint.weights_digest.startswith("sha256:")
    receipt = tier.persist(block, payload())
    assert receipt.ok is True
    assert receipt.as_dict()["native_kv_portability_claimed"] is False
    assert receipt.as_dict()["cross_engine_portable"] is False
    stats = tier.stats()
    assert stats["authority"] == "cache_only_storage_tier"


def test_mismatched_model_is_refused(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block, body = make_block(transport)
    assert transport.move(block.block_id, CacheLocation.STORAGE) is True

    other = transport.register_block(
        model="qwen3:4b",
        tokenizer="qwen3:4b",
        prompt_prefix=f"def f0(x):\n    return x\n",
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=28,
        num_heads=28,
        head_dim=128,
        seq_len=16,
        size_bytes=PAYLOAD_BYTES,
        tensor_payload=body,
    )
    restored, receipt = tier.restore(other)
    assert restored is None
    assert receipt.ok is False


def test_payload_under_floor_is_refused_with_reason(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block = transport.register_block(
        model="qwen2.5-coder:7b",
        tokenizer="qwen2.5-coder:7b",
        prompt_prefix="tiny\n",
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=28,
        num_heads=28,
        head_dim=128,
        seq_len=16,
        size_bytes=100,
        tensor_payload=b"x" * 100,
    )
    receipt = tier.persist(block, b"x" * 100)
    assert receipt.ok is False
    assert "4096" in receipt.reason


def test_stats_report_storage_backend(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    stats = transport.get_stats()
    assert stats["storage_backend"] == "crystal_kv_index"
    assert stats["crystal_storage_tier"]["manifests"] == 0

    legacy = make_transport(tmp_path / "legacy", None)
    legacy_stats = legacy.get_stats()
    assert legacy_stats["storage_backend"] == "raw_files"
    assert legacy_stats["crystal_storage_tier"] is None


def test_two_prompts_do_not_collide_or_overwrite(tmp_path: Path) -> None:
    """Transport regression: different prompts, same model and seq_len.

    Both blocks must be restorable after a restart, each to its own bytes.
    """
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block_a, body_a = make_block(transport, seed=0)
    block_b, _ = make_block(transport, seed=1)

    assert transport.move(block_a.block_id, CacheLocation.STORAGE) is True
    assert transport.move(block_b.block_id, CacheLocation.STORAGE) is True
    assert tier.stats()["manifests"] == 2, "different prompts must not share one crystal"

    rebooted_tier = tier_at(tmp_path)
    rebooted = make_transport(tmp_path, rebooted_tier)
    for block, expected in ((block_a, body_a), (block_b, payload(1))):
        restored, receipt = rebooted_tier.restore(block)
        assert receipt.ok is True, receipt.reason
        assert restored == expected


def test_prompt_digest_binds_to_fingerprint(tmp_path: Path) -> None:
    tier = tier_at(tmp_path)
    transport = make_transport(tmp_path, tier)
    block_a, _ = make_block(transport, seed=0)
    block_b, _ = make_block(transport, seed=1)
    fp_a = tier.fingerprint_for(block_a)
    fp_b = tier.fingerprint_for(block_b)
    assert fp_a.prompt_digest
    assert fp_a.prompt_digest != fp_b.prompt_digest
    assert fp_a.digest() != fp_b.digest()
