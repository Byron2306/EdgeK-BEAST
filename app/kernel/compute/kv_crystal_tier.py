"""Crystal-backed STORAGE tier for the cross-engine KV cache transport.

``CrossEngineKVCacheTransport`` already moves KV blocks between CPU, storage,
network and (theoretically) GPU.  Its storage tier was the weak link: it wrote
``<block_id>.bin`` plus a JSON sidecar with no content addressing, no chunk
deduplication, no digest verification on read and no revocation path.

This module replaces that tier with :class:`CrystalKVIndex` — the durable,
position-aligned, fingerprint-bound CAS introduced for crystal-as-KV.  The
transport keeps its public behaviour; only the persistence substrate changes.

Honesty contract
----------------
``CrystalKVIndex`` refuses approximate reuse across engines, dtypes, quants,
kernels or RoPE configurations.  When a caller cannot supply a real weights or
RoPE digest, this adapter derives a *stable identity* digest from the block's
declared model/precision/topology and labels the derivation in the manifest
metadata.  It never claims engine-native portability:

* ``authority`` stays ``cache_only``
* ``native_kv_portability_claimed`` stays ``False``
* ``cross_engine_portable`` stays ``False``
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.crystal_kv_index import (
    CrystalKVIndex,
    KVManifest,
    KVModelFingerprint,
    KVTokenSpan,
)

CRYSTAL_TIER_DEFAULT_BLOCK_SIZE_TOKENS = 16
CRYSTAL_TIER_MIN_BLOCK_BYTES = 4096
CRYSTAL_TIER_AUTHORITY = "cache_only_storage_tier"


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _largest_token_block(seq_len: int, *, preferred: int, ceiling: int = 128) -> int:
    """Pick the largest token block that divides ``seq_len``.

    ``KVManifest`` requires ``span.length % block_size_tokens == 0`` and the
    payload to split into that many equal byte blocks, so the block size has to
    divide the sequence length exactly.  Larger blocks mean fewer manifests and
    better deduplication granularity trade-offs; we prefer ``preferred`` when it
    divides, otherwise the largest divisor up to ``ceiling``.
    """
    if seq_len <= 0:
        raise ValueError("seq_len must be positive")
    if preferred > 0 and seq_len % preferred == 0:
        return preferred
    for candidate in range(min(ceiling, seq_len), 0, -1):
        if seq_len % candidate == 0:
            return candidate
    return 1


@dataclass(frozen=True, slots=True)
class CrystalTierReceipt:
    """Durable record of one storage-tier transition."""

    operation: str
    ok: bool
    block_id: str
    crystal_id: str = ""
    payload_bytes: int = 0
    stored_bytes: int = 0
    dedup_bytes_saved: int = 0
    fingerprint_digest: str = ""
    token_span: tuple[int, int] | None = None
    reason: str = ""
    authority: str = CRYSTAL_TIER_AUTHORITY

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "kv_crystal_tier_receipt",
            "version": "1.0",
            "operation": self.operation,
            "ok": self.ok,
            "block_id": self.block_id,
            "crystal_id": self.crystal_id,
            "payload_bytes": self.payload_bytes,
            "stored_bytes": self.stored_bytes,
            "dedup_bytes_saved": self.dedup_bytes_saved,
            "fingerprint_digest": self.fingerprint_digest,
            "token_span": list(self.token_span) if self.token_span else None,
            "reason": self.reason,
            "authority": self.authority,
            "native_kv_portability_claimed": False,
            "cross_engine_portable": False,
        }


class CrystalKVTier:
    """Durable crystal substrate for a transport's ``STORAGE`` tier."""

    def __init__(
        self,
        root: Path | str,
        *,
        privacy_domain: str = "local_kv_storage",
        block_size_tokens: int = CRYSTAL_TIER_DEFAULT_BLOCK_SIZE_TOKENS,
        ttl_seconds: float | None = 86400.0,
        max_entries: int = 8192,
    ):
        if not str(privacy_domain).strip():
            raise ValueError("privacy_domain cannot be empty")
        self.root = Path(root)
        self.privacy_domain = str(privacy_domain)
        self.block_size_tokens = int(block_size_tokens)
        self.ttl_seconds = ttl_seconds
        self.index = CrystalKVIndex(self.root, max_entries=max_entries)
        self._receipts: list[CrystalTierReceipt] = []

    # -- identity mapping -------------------------------------------------
    def fingerprint_for(self, block: Any) -> KVModelFingerprint:
        """Map a transport block onto an exact-match, digest-keyed fingerprint."""

        metadata: Mapping[str, Any] = getattr(block, "metadata", {}) or {}
        model = str(getattr(block, "model", ""))
        if not model:
            raise ValueError("kv block has no model identity")
        weights_digest = metadata.get("weights_digest")
        if not _is_digest(weights_digest):
            weights_digest = _digest(
                {
                    "derivation": "model_identity_v1",
                    "model": model,
                    "precision": str(getattr(block, "precision", "")),
                    "num_layers": int(getattr(block, "num_layers", 0)),
                    "num_heads": int(getattr(block, "num_heads", 0)),
                    "head_dim": int(getattr(block, "head_dim", 0)),
                }
            )
        tokenizer_digest = metadata.get("tokenizer_digest")
        if not _is_digest(tokenizer_digest):
            tokenizer_digest = _digest(
                {"derivation": "tokenizer_identity_v1", "tokenizer": str(getattr(block, "tokenizer", ""))}
            )
        rope_digest = metadata.get("rope_config_digest")
        if not _is_digest(rope_digest):
            rope_digest = _digest({"derivation": "rope_unspecified_v1", "model": model})
        engine = getattr(getattr(block, "engine", None), "value", None)
        engine = str(engine or metadata.get("engine") or "unknown")
        engine_version = str(metadata.get("engine_version") or "unspecified")
        dtype = str(getattr(block, "precision", "") or metadata.get("dtype") or "unknown")
        token_block = _largest_token_block(
            int(getattr(block, "seq_len", 0)),
            preferred=self.block_size_tokens,
        )
        # Prompt tokens change the KV bytes.  ``token_span`` alone cannot tell
        # two same-length prompts apart, so bind the block's own prompt and
        # system hashes into the identity.  Without this, two prompts would
        # collide on one crystal and silently overwrite each other.
        prompt_digest = metadata.get("prompt_digest")
        if not _is_digest(prompt_digest):
            prefix_hash = str(getattr(block, "prompt_prefix_hash", "") or "")
            system_hash = str(getattr(block, "system_prompt_hash", "") or "")
            if prefix_hash or system_hash:
                prompt_digest = _digest(
                    {
                        "derivation": "prompt_identity_v1",
                        "prompt_prefix_hash": prefix_hash,
                        "system_prompt_hash": system_hash,
                    }
                )
            else:
                prompt_digest = ""
        return KVModelFingerprint(
            weights_digest=str(weights_digest),
            tokenizer_digest=str(tokenizer_digest),
            engine=engine,
            engine_version=engine_version,
            dtype=dtype,
            block_size_tokens=token_block,
            rope_config_digest=str(rope_digest),
            prompt_digest=str(prompt_digest),
        )

    def _layer_range(self, block: Any) -> tuple[int, int]:
        layers = int(getattr(block, "num_layers", 0))
        if layers <= 0:
            raise ValueError("kv block has no layer topology")
        return (0, layers - 1)

    def _privacy_domain_for(self, block: Any) -> str:
        metadata: Mapping[str, Any] = getattr(block, "metadata", {}) or {}
        declared = str(metadata.get("privacy_domain") or "").strip()
        return declared or self.privacy_domain

    # -- tier transitions -------------------------------------------------
    def persist(self, block: Any, payload: bytes) -> CrystalTierReceipt:
        """Write exact KV bytes into the crystal CAS and return a receipt."""

        block_id = str(getattr(block, "block_id", ""))
        if not payload:
            return CrystalTierReceipt(operation="persist", ok=False, block_id=block_id, reason="empty payload")
        try:
            fingerprint = self.fingerprint_for(block)
            seq_len = int(getattr(block, "seq_len", 0))
            span = KVTokenSpan(0, seq_len)
            token_blocks = seq_len // fingerprint.block_size_tokens
            if token_blocks <= 0:
                raise ValueError("sequence shorter than the token block")
            if len(payload) % token_blocks != 0:
                raise ValueError("payload cannot split into equal token blocks")
            block_bytes = len(payload) // token_blocks
            if block_bytes < CRYSTAL_TIER_MIN_BLOCK_BYTES:
                raise ValueError(
                    f"payload too small for crystal transport: {block_bytes} bytes per token block "
                    f"(floor {CRYSTAL_TIER_MIN_BLOCK_BYTES})"
                )
            before = self.index.stats()
            manifest = self.index.put(
                fingerprint,
                span,
                payload,
                block_bytes=block_bytes,
                layer_range=self._layer_range(block),
                privacy_domain=self._privacy_domain_for(block),
                ttl_seconds=self.ttl_seconds,
                pinned=bool(getattr(block, "pinned", False)),
            )
            after = self.index.stats()
            stored = int(after["unique_chunk_bytes"]) - int(before["unique_chunk_bytes"])
            stored = max(0, stored)
            receipt = CrystalTierReceipt(
                operation="persist",
                ok=True,
                block_id=block_id,
                crystal_id=manifest.crystal_id,
                payload_bytes=len(payload),
                stored_bytes=stored,
                dedup_bytes_saved=max(0, len(payload) - stored),
                fingerprint_digest=manifest.fingerprint_digest(),
                token_span=(span.start, span.end),
            )
        except Exception as error:  # noqa: BLE001 - receipt carries the reason
            receipt = CrystalTierReceipt(operation="persist", ok=False, block_id=block_id, reason=str(error))
        self._receipts.append(receipt)
        return receipt

    def restore(self, block: Any) -> tuple[bytes | None, CrystalTierReceipt]:
        """Read exact KV bytes back, verifying the payload digest."""

        block_id = str(getattr(block, "block_id", ""))
        try:
            fingerprint = self.fingerprint_for(block)
            seq_len = int(getattr(block, "seq_len", 0))
            span = KVTokenSpan(0, seq_len)
            lookup = self.index.get(
                fingerprint,
                span,
                layer_range=self._layer_range(block),
                privacy_domain=self._privacy_domain_for(block),
            )
            reason = "" if lookup.hit else lookup.receipt.reason or lookup.receipt.status.value
            receipt = CrystalTierReceipt(
                operation="restore",
                ok=bool(lookup.hit),
                block_id=block_id,
                crystal_id=lookup.receipt.crystal_id,
                payload_bytes=lookup.receipt.bytes_served,
                stored_bytes=0,
                fingerprint_digest=fingerprint.digest(),
                token_span=(span.start, span.end),
                reason=reason,
            )
            payload = lookup.payload if lookup.hit else None
        except Exception as error:  # noqa: BLE001
            payload = None
            receipt = CrystalTierReceipt(operation="restore", ok=False, block_id=block_id, reason=str(error))
        self._receipts.append(receipt)
        return payload, receipt

    def discard(self, block: Any) -> CrystalTierReceipt:
        """Evict this block's manifest and release any now-unreferenced chunks.

        This is ordinary cache cleanup: no tombstone is left, so the same span
        may be cached again later.  Use :meth:`revoke` when the payload must
        never be served again.
        """

        block_id = str(getattr(block, "block_id", ""))
        try:
            fingerprint = self.fingerprint_for(block)
            seq_len = int(getattr(block, "seq_len", 0))
            span = KVTokenSpan(0, seq_len)
            key = (fingerprint.digest(), span.start, span.end, *self._layer_range(block))
            manifest = next((item for item in self.index.manifests() if item.key() == key), None)
            if manifest is None:
                receipt = CrystalTierReceipt(
                    operation="discard", ok=False, block_id=block_id, reason="not resident in the crystal tier"
                )
            else:
                result = self.index.evict(manifest.crystal_id)
                receipt = CrystalTierReceipt(
                    operation="discard",
                    ok=bool(result.get("evicted")),
                    block_id=block_id,
                    crystal_id=manifest.crystal_id,
                    stored_bytes=int(result.get("freed_bytes", 0)),
                    fingerprint_digest=fingerprint.digest(),
                    token_span=(span.start, span.end),
                    reason=str(result.get("reason") or ""),
                )
        except Exception as error:  # noqa: BLE001
            receipt = CrystalTierReceipt(operation="discard", ok=False, block_id=block_id, reason=str(error))
        self._receipts.append(receipt)
        return receipt

    def revoke(self, block: Any, *, reason: str = "") -> CrystalTierReceipt:
        """Permanently tombstone this block so its bytes are never served again."""

        block_id = str(getattr(block, "block_id", ""))
        try:
            fingerprint = self.fingerprint_for(block)
            seq_len = int(getattr(block, "seq_len", 0))
            span = KVTokenSpan(0, seq_len)
            key = (fingerprint.digest(), span.start, span.end, *self._layer_range(block))
            manifest = next((item for item in self.index.manifests() if item.key() == key), None)
            if manifest is None:
                receipt = CrystalTierReceipt(
                    operation="revoke", ok=False, block_id=block_id, reason="not resident in the crystal tier"
                )
            else:
                result = self.index.revoke(manifest.crystal_id, reason=reason or f"transport revoke of {block_id}")
                receipt = CrystalTierReceipt(
                    operation="revoke",
                    ok=bool(result.get("revoked")),
                    block_id=block_id,
                    crystal_id=manifest.crystal_id,
                    fingerprint_digest=fingerprint.digest(),
                    token_span=(span.start, span.end),
                    reason=str(result.get("reason") or ""),
                )
        except Exception as error:  # noqa: BLE001
            receipt = CrystalTierReceipt(operation="revoke", ok=False, block_id=block_id, reason=str(error))
        self._receipts.append(receipt)
        return receipt

    # -- introspection ----------------------------------------------------
    def stats(self) -> dict[str, Any]:
        index_stats = self.index.stats()
        return {
            "beast_object_type": "kv_crystal_tier_stats",
            "version": "1.0",
            "root": str(self.root),
            "authority": CRYSTAL_TIER_AUTHORITY,
            "privacy_domain": self.privacy_domain,
            "block_size_tokens": self.block_size_tokens,
            "ttl_seconds": self.ttl_seconds,
            "manifests": index_stats["manifests"],
            "kv_bytes": index_stats["kv_bytes"],
            "unique_chunks": index_stats["unique_chunks"],
            "unique_chunk_bytes": index_stats["unique_chunk_bytes"],
            "hits": index_stats["hits"],
            "misses": index_stats["misses"],
            "rejections": index_stats["rejections"],
            "puts": index_stats["puts"],
            "recent_receipts": [item.as_dict() for item in self._receipts[-8:]],
            "native_kv_portability_claimed": False,
            "cross_engine_portable": False,
        }

    def reclaim(self, pressure_level: str) -> dict[str, Any] | None:
        """Evict a bounded fraction of the tier under PSI pressure."""

        reclaimable = int(self.index.stats()["kv_bytes"])
        eviction = self.index.reclaim_for_pressure(pressure_level, reclaimable_bytes=reclaimable)
        return eviction.as_dict() if eviction is not None else None

    def manifests(self) -> tuple[KVManifest, ...]:
        return self.index.manifests()
