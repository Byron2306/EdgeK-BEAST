"""Acceptance tests for the crystal-keyed, position-aligned KV cache.

These encode the four properties the census said were missing:

1. exact aligned hit returns the exact bytes;
2. a shifted span is a miss, because KV blocks are position-baked;
3. a different model fingerprint is refused, not approximated;
4. tampering, expiry, privacy mismatch and revocation are refused with a
   reason and zero bytes served.
"""
from __future__ import annotations

import json

import pytest

from app.kernel.compute.crystal_kv_index import (
    KV_MANIFEST_KIND,
    CrystalKVIndex,
    KVLookupStatus,
    KVManifest,
    KVModelFingerprint,
    KVTokenSpan,
    kv_manifest_kind,
)

BLOCK_TOKENS = 16
BLOCK_BYTES = 4096  # transport floor; deliberately not a token multiple
LAYERS = (0, 35)
PRIVACY = "workspace:edgek"


def fingerprint(**overrides) -> KVModelFingerprint:
    values = {
        "weights_digest": "sha256:" + "a" * 64,
        "tokenizer_digest": "sha256:" + "b" * 64,
        "engine": "ollama",
        "engine_version": "0.6.2",
        "dtype": "fp16",
        "block_size_tokens": BLOCK_TOKENS,
        "rope_config_digest": "sha256:" + "c" * 64,
    }
    values.update(overrides)
    return KVModelFingerprint(**values)


def kv_payload(blocks: int, *, seed: int = 0) -> bytes:
    out = bytearray()
    for index in range(blocks):
        block = bytes([(seed * 31 + index * 7 + offset) % 251 for offset in range(BLOCK_BYTES)])
        out.extend(block)
    return bytes(out)


def put(index: CrystalKVIndex, *, fp=None, start=0, blocks=4, seed=0, **kwargs):
    fp = fp or fingerprint()
    span = KVTokenSpan(start, start + blocks * BLOCK_TOKENS)
    return index.put(
        fp,
        span,
        kv_payload(blocks, seed=seed),
        block_bytes=BLOCK_BYTES,
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
        **kwargs,
    )


def test_aligned_hit_returns_exact_bytes(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    payload = kv_payload(4)
    manifest = index.put(
        fingerprint(),
        KVTokenSpan(0, 4 * BLOCK_TOKENS),
        payload,
        block_bytes=BLOCK_BYTES,
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert manifest.kind == KV_MANIFEST_KIND
    assert manifest.authority == "cache_only"
    assert manifest.as_dict()["native_kv_portability_claimed"] is False

    lookup = index.get(
        fingerprint(),
        KVTokenSpan(0, 4 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert lookup.hit is True
    assert lookup.receipt.status is KVLookupStatus.HIT
    assert lookup.receipt.bytes_served == len(payload)
    assert lookup.payload == payload


def test_shifted_span_is_a_miss_not_a_guess(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=4)

    shifted = index.get(
        fingerprint(),
        KVTokenSpan(BLOCK_TOKENS, 5 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert shifted.hit is False
    assert shifted.receipt.status is KVLookupStatus.MISS
    assert shifted.payload is None


def test_misaligned_put_is_refused(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    with pytest.raises(ValueError, match="block aligned"):
        index.put(
            fingerprint(),
            KVTokenSpan(1, 1 + 4 * BLOCK_TOKENS),
            kv_payload(4),
            block_bytes=BLOCK_BYTES,
            layer_range=LAYERS,
            privacy_domain=PRIVACY,
        )


def test_cross_fingerprint_is_rejected_with_a_reason(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=4)

    other = fingerprint(rope_config_digest="sha256:" + "d" * 64)
    lookup = index.get(
        other,
        KVTokenSpan(0, 4 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert lookup.hit is False
    assert lookup.receipt.status is KVLookupStatus.REJECTED_FINGERPRINT
    assert "different model fingerprint" in lookup.receipt.reason
    assert lookup.receipt.bytes_served == 0


def test_tampered_chunk_serves_nothing(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=2)

    chunk_dir = tmp_path / "kv" / "chunks" / f"b{BLOCK_BYTES}"
    victim = sorted(path for path in chunk_dir.iterdir() if path.is_file())[0]
    victim.write_bytes(b"\x00" * BLOCK_BYTES)

    lookup = index.get(
        fingerprint(),
        KVTokenSpan(0, 2 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert lookup.hit is False
    assert lookup.receipt.status is KVLookupStatus.REJECTED_INTEGRITY
    assert lookup.payload is None
    assert lookup.receipt.bytes_served == 0


def test_expiry_is_enforced(tmp_path):
    now = [1000.0]
    index = CrystalKVIndex(tmp_path / "kv", clock=lambda: now[0])
    put(index, start=0, blocks=1, ttl_seconds=10.0)

    now[0] = 1011.0
    lookup = index.get(
        fingerprint(),
        KVTokenSpan(0, BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert lookup.receipt.status is KVLookupStatus.REJECTED_EXPIRED


def test_privacy_domain_is_enforced(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=1)

    lookup = index.get(
        fingerprint(),
        KVTokenSpan(0, BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain="workspace:other",
    )

    assert lookup.receipt.status is KVLookupStatus.REJECTED_PRIVACY
    assert "prompt content" in lookup.receipt.reason


def test_crystal_revocation_blocks_lookup(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    manifest = put(index, start=0, blocks=1)
    index.revoke(manifest.crystal_id, reason="superseded")

    lookup = index.get(
        fingerprint(),
        KVTokenSpan(0, BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert lookup.receipt.status is KVLookupStatus.REJECTED_REVOKED


def test_fingerprint_revocation_blocks_every_span(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=1)
    put(index, start=BLOCK_TOKENS, blocks=1)
    index.revoke_fingerprint(fingerprint().digest(), reason="weights rolled")

    for start in (0, BLOCK_TOKENS):
        lookup = index.get(
            fingerprint(),
            KVTokenSpan(start, start + BLOCK_TOKENS),
            layer_range=LAYERS,
            privacy_domain=PRIVACY,
        )
        assert lookup.receipt.status is KVLookupStatus.REJECTED_REVOKED


def test_shared_prefix_dedups_on_disk(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=8, seed=0)
    first = index.stats()
    put(index, start=0, blocks=8, seed=0)
    second = index.stats()

    # Same bytes at the same span is one manifest and one chunk set.
    assert first["manifests"] == second["manifests"] == 1
    assert first["unique_chunk_bytes"] == second["unique_chunk_bytes"] == 8 * BLOCK_BYTES

    tail = put(index, start=0, blocks=12, seed=0)
    third = index.stats()
    # The 12-block slab shares its first 8 blocks and adds 4 new ones.
    assert tail.kv_bytes == 12 * BLOCK_BYTES
    assert third["unique_chunk_bytes"] == 12 * BLOCK_BYTES


def test_capacity_eviction_never_touches_pinned(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv", max_entries=4)
    pinned = put(index, start=0, blocks=1, seed=1, pinned=True)
    for block in range(1, 6):
        put(index, start=block * BLOCK_TOKENS, blocks=1, seed=block)

    remaining = {manifest.crystal_id for manifest in index.manifests()}
    assert pinned.crystal_id in remaining
    assert len(remaining) <= 4

    receipt = index.evict_lru(10**9)
    assert receipt.freed_bytes >= 0
    assert pinned.crystal_id not in receipt.evicted
    assert pinned.crystal_id in receipt.retained_pinned


def test_index_reloads_from_disk(tmp_path):
    root = tmp_path / "kv"
    first = CrystalKVIndex(root)
    put(first, start=0, blocks=3)

    second = CrystalKVIndex(root)
    lookup = second.get(
        fingerprint(),
        KVTokenSpan(0, 3 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )

    assert lookup.hit is True
    assert lookup.payload == kv_payload(3)


def test_manifest_round_trips_through_json(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    manifest = put(index, start=0, blocks=2)
    restored = KVManifest.from_dict(json.loads(manifest.to_json()))

    assert restored == manifest
    assert kv_manifest_kind(restored.as_dict()) is True


def test_manifest_refuses_truth_or_execution_authority(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    manifest = put(index, start=0, blocks=1)
    values = manifest.as_dict()
    values["authority"] = "execution"
    with pytest.raises(ValueError, match="authority"):
        KVManifest.from_dict(values)


def test_pressure_binding_evicts_a_bounded_fraction(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    pinned = put(index, start=0, blocks=1, seed=1, pinned=True)
    for block in range(1, 11):
        put(index, start=block * BLOCK_TOKENS, blocks=1, seed=block)

    quiet = index.reclaim_for_pressure("low", reclaimable_bytes=10 * BLOCK_BYTES)
    assert quiet is None

    receipt = index.reclaim_for_pressure("high", reclaimable_bytes=10 * BLOCK_BYTES)
    assert receipt is not None
    assert receipt.requested_bytes == int(round(10 * BLOCK_BYTES * 0.15))
    assert receipt.freed_bytes >= receipt.requested_bytes
    assert pinned.crystal_id not in receipt.evicted
    assert index.manifest(pinned.crystal_id) is not None


def test_pressure_binding_rejects_unknown_levels(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    with pytest.raises(ValueError, match="unknown pressure level"):
        index.reclaim_for_pressure("apocalyptic", reclaimable_bytes=1)


def test_manifest_and_receipts_validate_against_canon(tmp_path):
    from app.kernel.registry.canon_registry import CanonRegistry

    index = CrystalKVIndex(tmp_path / "kv")
    manifest = put(index, start=0, blocks=2)
    lookup = index.get(
        fingerprint(),
        KVTokenSpan(0, 2 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )
    eviction = index.evict_lru(0)
    canon = CanonRegistry()

    for obj in (manifest.as_dict(), lookup.receipt.as_dict(), eviction.as_dict(), index.stats()):
        report = canon.validate_object(obj)
        assert report["valid"] is True, report["errors"]


def test_eviction_keeps_chunks_referenced_by_surviving_manifests(tmp_path):
    """GC must be reference-counted: evicting A cannot delete B's chunks.

    Regression for a GC that compared chunk *dicts* against digest strings, so
    the reference set was empty and every eviction wiped every live chunk.
    """
    index = CrystalKVIndex(tmp_path / "kv")
    first = put(index, start=0, blocks=2, seed=1)
    second = put(index, start=2 * BLOCK_TOKENS, blocks=2, seed=2)
    total = index.stats()["unique_chunk_bytes"]
    assert total == 4 * BLOCK_BYTES

    eviction = index.evict(first.crystal_id)
    assert eviction["evicted"] is True
    assert eviction["freed_bytes"] == 2 * BLOCK_BYTES
    assert index.stats()["unique_chunk_bytes"] == 2 * BLOCK_BYTES

    survivor = index.get(
        fingerprint(),
        KVTokenSpan(2 * BLOCK_TOKENS, 4 * BLOCK_TOKENS),
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )
    assert survivor.hit is True
    assert survivor.payload == kv_payload(2, seed=2)


def test_deduped_chunks_survive_partial_eviction(tmp_path):
    """Two manifests sharing identical bytes: evicting one keeps the shared chunk."""
    index = CrystalKVIndex(tmp_path / "kv")
    put(index, start=0, blocks=2, seed=5)
    # Different span, identical bytes => same chunk digests.
    put(index, start=2 * BLOCK_TOKENS, blocks=2, seed=5)
    assert index.stats()["unique_chunk_bytes"] == 2 * BLOCK_BYTES

    manifests = index.manifests()
    first = index.evict(manifests[0].crystal_id)
    assert first["freed_bytes"] == 0, "shared chunks must not be released"
    assert index.stats()["unique_chunk_bytes"] == 2 * BLOCK_BYTES

    survivor = index.get(
        fingerprint(),
        manifests[1].token_span,
        layer_range=LAYERS,
        privacy_domain=PRIVACY,
    )
    assert survivor.hit is True


def test_identity_collision_is_refused_not_overwritten(tmp_path):
    """Same fingerprint+span, different bytes => refuse, never silently replace.

    Two same-length prompts are indistinguishable by token_span alone; without
    a prompt_digest the second put used to replace the first in the index and
    make one prompt's KV unreachable.
    """
    index = CrystalKVIndex(tmp_path / "kv")
    span = KVTokenSpan(0, 4 * BLOCK_TOKENS)
    put(index, start=0, blocks=4, seed=1)
    with pytest.raises(ValueError, match="identity collision"):
        index.put(
            fingerprint(),
            span,
            kv_payload(4, seed=2),
            block_bytes=BLOCK_BYTES,
            layer_range=LAYERS,
            privacy_domain=PRIVACY,
        )
    # The original bytes must still be served.
    lookup = index.get(fingerprint(), span, layer_range=LAYERS, privacy_domain=PRIVACY)
    assert lookup.hit is True
    assert lookup.payload == kv_payload(4, seed=1)


def test_prompt_digest_distinguishes_same_length_prompts(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    span = KVTokenSpan(0, 2 * BLOCK_TOKENS)
    fp_a = fingerprint(prompt_digest="sha256:" + "1" * 64)
    fp_b = fingerprint(prompt_digest="sha256:" + "2" * 64)
    assert fp_a.digest() != fp_b.digest()

    index.put(fp_a, span, kv_payload(2, seed=1), block_bytes=BLOCK_BYTES, layer_range=LAYERS, privacy_domain=PRIVACY)
    index.put(fp_b, span, kv_payload(2, seed=2), block_bytes=BLOCK_BYTES, layer_range=LAYERS, privacy_domain=PRIVACY)
    assert index.stats()["manifests"] == 2

    for fp, seed in ((fp_a, 1), (fp_b, 2)):
        lookup = index.get(fp, span, layer_range=LAYERS, privacy_domain=PRIVACY)
        assert lookup.hit is True
        assert lookup.payload == kv_payload(2, seed=seed)


def test_identical_reput_is_idempotent(tmp_path):
    index = CrystalKVIndex(tmp_path / "kv")
    span = KVTokenSpan(0, 2 * BLOCK_TOKENS)
    first = index.put(fingerprint(), span, kv_payload(2, seed=1), block_bytes=BLOCK_BYTES, layer_range=LAYERS, privacy_domain=PRIVACY)
    second = index.put(fingerprint(), span, kv_payload(2, seed=1), block_bytes=BLOCK_BYTES, layer_range=LAYERS, privacy_domain=PRIVACY)
    assert first.crystal_id == second.crystal_id
    assert index.stats()["manifests"] == 1
    assert index.stats()["unique_chunk_bytes"] == 2 * BLOCK_BYTES
