"""Position-aligned KV cache keyed by a crystal manifest.

This is the "crystal as a KV/XET memory system" primitive.  It does not claim
that KV bytes are portable between engines.  It claims something narrower and
checkable:

* KV is content-addressed at a **fixed block stride**, because KV blocks are
  position-baked: a block computed for tokens ``[0, 16)`` is not valid at
  ``[16, 32)`` and must not be served there.
* Every KV slab is described by a ``kv_manifest`` crystal that carries the
  model fingerprint, absolute token span, layer range, privacy domain, and
  lineage.  The bytes are chunks; the crystal is the passport.
* A lookup verifies fingerprint, span, expiry, revocation, privacy domain and
  chunk digests **before** any byte is handed back.

Authority is ``cache_only``.  A hit is a latency optimization, never a truth
claim, never a weight, and never an execution grant.  The bytes can carry
prompt content, so callers must treat them as ``privacy_domain`` material.

The measured basis (see ``docs/BEAST_PHYSICAL_STACK_CENSUS.md``):

* block-aligned CAS dedups 44.44% on aligned KV vs 43.88% for CDC;
* CDC only wins when alignment is lost, and lost alignment is not reusable
  for serving.  So serving uses fixed block alignment, and CDC stays in the
  transport layer (``forge_kv_xet``).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping

from app.kernel.commons.chunk_store import ChunkManifest, ChunkStore
from app.kernel.compute.forge_kv_xet import chunk_bytes

KV_MANIFEST_KIND = "kv_manifest"
KV_MANIFEST_VERSION = 1
KV_AUTHORITY = "cache_only"
KV_PRESSURE_TARGETS = {
    "low": 0.0,
    "rising": 0.0,
    "unknown": 0.0,
    "high": 0.15,
    "critical": 0.35,
}
_DIGEST_RE = r"^sha256:[a-f0-9]{64}$"

_SAFE_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        c in "0123456789abcdef" for c in value[7:]
    )


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value


class KVLookupStatus(str, Enum):
    HIT = "hit"
    MISS = "miss"
    REJECTED_FINGERPRINT = "rejected_fingerprint"
    REJECTED_SPAN = "rejected_span"
    REJECTED_ALIGNMENT = "rejected_alignment"
    REJECTED_PRIVACY = "rejected_privacy"
    REJECTED_EXPIRED = "rejected_expired"
    REJECTED_REVOKED = "rejected_revoked"
    REJECTED_INTEGRITY = "rejected_integrity"


@dataclass(frozen=True, slots=True)
class KVModelFingerprint:
    """Everything that can change the bytes of a KV block.

    A fingerprint is exact-match only.  Approximate reuse across engines,
    dtypes, quants, kernels or RoPE configurations is refused, not averaged.
    """

    weights_digest: str
    tokenizer_digest: str
    engine: str
    engine_version: str
    dtype: str
    block_size_tokens: int
    rope_config_digest: str
    # Prompt tokens change the KV bytes as surely as weights do.  Two prompts
    # of the same length are indistinguishable by ``token_span`` alone, so the
    # span owner supplies a digest of the exact token prefix.  Empty means
    # "unspecified" and preserves the legacy identity; the transport tier always
    # sets it from the block's prompt/system hashes.
    prompt_digest: str = ""

    def __post_init__(self) -> None:
        for name in ("weights_digest", "tokenizer_digest", "rope_config_digest"):
            if not _is_digest(getattr(self, name)):
                raise ValueError(f"{name} must be a sha256 digest")
        if self.prompt_digest and not _is_digest(self.prompt_digest):
            raise ValueError("prompt_digest must be a sha256 digest when supplied")
        for name in ("engine", "engine_version", "dtype"):
            _require_text(getattr(self, name), name)
        if not 1 <= int(self.block_size_tokens) <= 4096:
            raise ValueError("block_size_tokens outside policy")

    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "weights_digest": self.weights_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "dtype": self.dtype,
            "block_size_tokens": int(self.block_size_tokens),
            "rope_config_digest": self.rope_config_digest,
            "prompt_digest": self.prompt_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "KVModelFingerprint":
        return cls(
            weights_digest=str(value["weights_digest"]),
            tokenizer_digest=str(value["tokenizer_digest"]),
            engine=str(value["engine"]),
            engine_version=str(value["engine_version"]),
            dtype=str(value["dtype"]),
            block_size_tokens=int(value["block_size_tokens"]),
            rope_config_digest=str(value["rope_config_digest"]),
            prompt_digest=str(value.get("prompt_digest") or ""),
        )


@dataclass(frozen=True, slots=True)
class KVTokenSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if int(self.start) < 0:
            raise ValueError("span start cannot be negative")
        if int(self.end) <= int(self.start):
            raise ValueError("span end must be greater than start")

    @property
    def length(self) -> int:
        return int(self.end) - int(self.start)

    def aligned(self, block_size_tokens: int) -> bool:
        return self.start % block_size_tokens == 0 and self.length % block_size_tokens == 0

    def as_dict(self) -> dict[str, int]:
        return {"start": int(self.start), "end": int(self.end)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "KVTokenSpan":
        return cls(int(value["start"]), int(value["end"]))


@dataclass(frozen=True, slots=True)
class KVManifest:
    """A ``kv_manifest`` crystal: passport for a position-baked KV slab."""

    crystal_id: str
    model_fingerprint: KVModelFingerprint
    token_span: KVTokenSpan
    layer_range: tuple[int, int]
    block_size_tokens: int
    block_bytes: int
    kv_bytes: int
    chunk_manifest: Mapping[str, Any]
    privacy_domain: str
    parent_crystal_id: str
    created_at: float
    expires_at: float
    pinned: bool = False
    authority: str = KV_AUTHORITY
    kind: str = KV_MANIFEST_KIND
    version: int = KV_MANIFEST_VERSION

    def __post_init__(self) -> None:
        _require_text(self.crystal_id, "crystal_id")
        if self.kind != KV_MANIFEST_KIND:
            raise ValueError("manifest kind must be kv_manifest")
        if self.version != KV_MANIFEST_VERSION:
            raise ValueError("unsupported kv_manifest version")
        if self.authority != KV_AUTHORITY:
            raise ValueError("kv_manifest cannot carry execution or truth authority")
        first, last = int(self.layer_range[0]), int(self.layer_range[1])
        if first < 0 or last < first:
            raise ValueError("invalid layer range")
        if not self.token_span.aligned(int(self.block_size_tokens)):
            raise ValueError("token span is not block aligned")
        blocks = self.token_span.length // int(self.block_size_tokens)
        if int(self.block_bytes) <= 0 or int(self.kv_bytes) != blocks * int(self.block_bytes):
            raise ValueError("kv_bytes does not match aligned block layout")
        if not _is_digest(str(self.chunk_manifest.get("root_digest", ""))):
            raise ValueError("chunk manifest root digest is invalid")
        if not _is_digest(str(self.chunk_manifest.get("payload_digest", ""))):
            raise ValueError("chunk manifest payload digest is invalid")
        if len(self.chunk_manifest.get("chunks", ())) != blocks:
            raise ValueError("chunk count does not match token blocks")
        _require_text(self.privacy_domain, "privacy_domain")

    def fingerprint_digest(self) -> str:
        return self.model_fingerprint.digest()

    def key(self) -> tuple[str, int, int, int, int]:
        first, last = self.layer_range
        return (self.fingerprint_digest(), self.token_span.start, self.token_span.end, int(first), int(last))

    def span_key(self) -> tuple[int, int, int, int]:
        first, last = self.layer_range
        return (self.token_span.start, self.token_span.end, int(first), int(last))

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": KV_MANIFEST_KIND,
            "version": self.version,
            "kind": self.kind,
            "crystal_id": self.crystal_id,
            "model_fingerprint": self.model_fingerprint.as_dict(),
            "fingerprint_digest": self.fingerprint_digest(),
            "token_span": self.token_span.as_dict(),
            "layer_range": [int(self.layer_range[0]), int(self.layer_range[1])],
            "block_size_tokens": int(self.block_size_tokens),
            "block_bytes": int(self.block_bytes),
            "kv_bytes": int(self.kv_bytes),
            "chunk_manifest": dict(self.chunk_manifest),
            "privacy_domain": self.privacy_domain,
            "parent_crystal_id": self.parent_crystal_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "pinned": self.pinned,
            "authority": self.authority,
            "native_kv_portability_claimed": False,
            "cross_engine_portable": False,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "KVManifest":
        return cls(
            crystal_id=str(value["crystal_id"]),
            model_fingerprint=KVModelFingerprint.from_dict(value["model_fingerprint"]),
            token_span=KVTokenSpan.from_dict(value["token_span"]),
            layer_range=(int(value["layer_range"][0]), int(value["layer_range"][1])),
            block_size_tokens=int(value["block_size_tokens"]),
            block_bytes=int(value["block_bytes"]),
            kv_bytes=int(value["kv_bytes"]),
            chunk_manifest=dict(value["chunk_manifest"]),
            privacy_domain=str(value["privacy_domain"]),
            parent_crystal_id=str(value.get("parent_crystal_id", "")),
            created_at=float(value["created_at"]),
            expires_at=float(value["expires_at"]),
            pinned=bool(value.get("pinned", False)),
            authority=str(value.get("authority", KV_AUTHORITY)),
            kind=str(value.get("kind", KV_MANIFEST_KIND)),
            version=int(value.get("version", KV_MANIFEST_VERSION)),
        )


@dataclass(frozen=True, slots=True)
class KVLookupReceipt:
    status: KVLookupStatus
    crystal_id: str = ""
    fingerprint_digest: str = ""
    token_span: tuple[int, int] | None = None
    layer_range: tuple[int, int] | None = None
    bytes_served: int = 0
    chunks_served: int = 0
    reason: str = ""
    authority: str = KV_AUTHORITY
    native_kv_portability_claimed: bool = False

    @property
    def hit(self) -> bool:
        return self.status is KVLookupStatus.HIT

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "kv_lookup_receipt",
            "version": "1.0",
            "status": self.status.value,
            "crystal_id": self.crystal_id,
            "fingerprint_digest": self.fingerprint_digest,
            "token_span": list(self.token_span) if self.token_span else None,
            "layer_range": list(self.layer_range) if self.layer_range else None,
            "bytes_served": self.bytes_served,
            "chunks_served": self.chunks_served,
            "reason": self.reason,
            "authority": self.authority,
            "native_kv_portability_claimed": self.native_kv_portability_claimed,
        }


@dataclass(frozen=True, slots=True)
class KVLookup:
    receipt: KVLookupReceipt
    payload: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def hit(self) -> bool:
        return self.receipt.hit


@dataclass(frozen=True, slots=True)
class KVEvictionReceipt:
    requested_bytes: int
    evicted: tuple[str, ...]
    freed_bytes: int
    retained_pinned: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "kv_eviction_receipt",
            "version": "1.0",
            "requested_bytes": self.requested_bytes,
            "evicted": list(self.evicted),
            "freed_bytes": self.freed_bytes,
            "retained_pinned": list(self.retained_pinned),
            "read_only_after": True,
        }


class CrystalKVIndex:
    """Durable, position-aligned, crystal-keyed KV cache."""

    def __init__(
        self,
        root: Path | str,
        *,
        clock: Callable[[], float] = time.time,
        max_entries: int = 4096,
    ):
        if int(max_entries) <= 0:
            raise ValueError("max_entries must be positive")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_dir = self.root / "manifests"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.revoked_dir = self.root / "revoked"
        self.revoked_dir.mkdir(parents=True, exist_ok=True)
        self.revoked_fingerprint_dir = self.root / "revoked-fingerprints"
        self.revoked_fingerprint_dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._max_entries = int(max_entries)
        self._by_key: dict[tuple[str, int, int, int, int], KVManifest] = {}
        self._by_span: dict[tuple[int, int, int, int], list[KVManifest]] = {}
        self._last_used: dict[str, int] = {}
        self._stores: dict[int, ChunkStore] = {}
        self._counters = {"hits": 0, "misses": 0, "rejections": 0, "puts": 0}
        self._load()

    # -- persistence -----------------------------------------------------
    def _load(self) -> None:
        for path in sorted(self.manifest_dir.glob("*.json")):
            try:
                manifest = KVManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError):
                continue
            self._index(manifest)

    def _index(self, manifest: KVManifest) -> None:
        self._by_key[manifest.key()] = manifest
        self._by_span.setdefault(manifest.span_key(), [])
        bucket = self._by_span[manifest.span_key()]
        bucket[:] = [item for item in bucket if item.key() != manifest.key()]
        bucket.append(manifest)
        self._last_used[manifest.crystal_id] = time.monotonic_ns()
        # Rehydrate the chunk-store handle so stats() and GC see the files a
        # previous process wrote.  Without this a restart reports zero unique
        # bytes and orphan chunks are never reclaimed.
        self._store_for(int(manifest.block_bytes))

    def _write_manifest(self, manifest: KVManifest) -> None:
        target = self.manifest_dir / f"{manifest.crystal_id}.json"
        if target.exists():
            return
        descriptor, temp_name = tempfile.mkstemp(prefix=".kv-", suffix=".tmp", dir=self.manifest_dir)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(manifest.to_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _store_for(self, block_bytes: int) -> ChunkStore:
        store = self._stores.get(block_bytes)
        if store is None:
            store = ChunkStore(self.root / "chunks" / f"b{block_bytes}", chunk_size=block_bytes)
            self._stores[block_bytes] = store
        return store

    # -- write -----------------------------------------------------------
    def put(
        self,
        fingerprint: KVModelFingerprint,
        span: KVTokenSpan,
        kv_bytes: bytes,
        *,
        block_bytes: int,
        layer_range: tuple[int, int],
        privacy_domain: str,
        parent_crystal_id: str = "",
        ttl_seconds: float | None = 3600.0,
        pinned: bool = False,
    ) -> KVManifest:
        if not isinstance(kv_bytes, (bytes, bytearray, memoryview)) or not kv_bytes:
            raise ValueError("kv payload cannot be empty")
        payload = bytes(kv_bytes)
        block_size_tokens = int(fingerprint.block_size_tokens)
        if not span.aligned(block_size_tokens):
            raise ValueError("span is not block aligned; a shifted span is not reusable KV")
        if int(block_bytes) < 4096:
            raise ValueError("block_bytes below the 4096-byte transport floor")
        blocks = span.length // block_size_tokens
        if int(block_bytes) * blocks != len(payload):
            raise ValueError("payload size does not match block_size_tokens x block_bytes")
        chunks = chunk_bytes(payload, chunk_size=int(block_bytes))
        if chunks["chunk_count"] != blocks:
            raise ValueError("chunker produced an unexpected block count")
        chunks = dict(chunks)
        chunks["payload_digest"] = "sha256:" + hashlib.sha256(payload).hexdigest()
        store = self._store_for(int(block_bytes))
        now = self._clock()
        expires_at = now + float(ttl_seconds) if ttl_seconds is not None else float("inf")
        body = {
            "fingerprint": fingerprint.as_dict(),
            "span": span.as_dict(),
            "layer_range": [int(layer_range[0]), int(layer_range[1])],
            "block_bytes": int(block_bytes),
            "root_digest": chunks["root_digest"],
            "privacy_domain": privacy_domain,
            "parent_crystal_id": parent_crystal_id,
        }
        crystal_id = "kv_" + hashlib.sha256(_canonical(body)).hexdigest()[:32]
        manifest = KVManifest(
            crystal_id=crystal_id,
            model_fingerprint=fingerprint,
            token_span=span,
            layer_range=(int(layer_range[0]), int(layer_range[1])),
            block_size_tokens=block_size_tokens,
            block_bytes=int(block_bytes),
            kv_bytes=len(payload),
            chunk_manifest=chunks,
            privacy_domain=privacy_domain,
            parent_crystal_id=parent_crystal_id,
            created_at=now,
            expires_at=expires_at,
            pinned=bool(pinned),
        )
        # The lookup key is (fingerprint, span, layers).  Two different byte
        # payloads can only share that key if the caller's identity is not exact
        # enough.  Overwriting would silently make one prompt's KV unreadable,
        # so refuse and say why.  An identical re-put is idempotent.
        existing = self._by_key.get(manifest.key())
        if existing is not None and existing.crystal_id != crystal_id:
            raise ValueError(
                "identity collision: this fingerprint/span is already bound to different KV bytes; "
                "supply an exact prompt_digest or a distinct span"
            )
        if existing is not None:
            return existing
        stored = store.put(payload)
        if list(stored.chunks) != [chunk["digest"] for chunk in chunks["chunks"]]:
            raise ValueError("chunk store disagrees with chunk manifest")
        if stored.artifact_digest != chunks["payload_digest"]:
            raise ValueError("chunk store payload digest disagrees with chunk manifest")
        self._write_manifest(manifest)
        self._index(manifest)
        self._counters["puts"] += 1
        self._enforce_capacity()
        return manifest

    # -- read ------------------------------------------------------------
    def get(
        self,
        fingerprint: KVModelFingerprint,
        span: KVTokenSpan,
        *,
        layer_range: tuple[int, int],
        privacy_domain: str,
    ) -> KVLookup:
        span_key = (span.start, span.end, int(layer_range[0]), int(layer_range[1]))
        key = (fingerprint.digest(), span.start, span.end, int(layer_range[0]), int(layer_range[1]))
        manifest = self._by_key.get(key)
        if manifest is None:
            alternate = self._by_span.get(span_key, ())
            if alternate:
                self._counters["rejections"] += 1
                return KVLookup(receipt=self._reject(
                    KVLookupStatus.REJECTED_FINGERPRINT,
                    alternate[0],
                    "span is cached only for a different model fingerprint",
                    span=span,
                    layer_range=layer_range,
                    fingerprint_digest=fingerprint.digest(),
                ))
            self._counters["misses"] += 1
            return KVLookup(receipt=KVLookupReceipt(
                status=KVLookupStatus.MISS,
                fingerprint_digest=fingerprint.digest(),
                token_span=(span.start, span.end),
                layer_range=(int(layer_range[0]), int(layer_range[1])),
                reason="no cached KV for this aligned span",
            ))
        return self._serve(manifest, fingerprint, span, layer_range, privacy_domain)

    def _serve(
        self,
        manifest: KVManifest,
        fingerprint: KVModelFingerprint,
        span: KVTokenSpan,
        layer_range: tuple[int, int],
        privacy_domain: str,
    ) -> KVLookup:
        now = self._clock()
        if manifest.expires_at <= now:
            return KVLookup(receipt=self._reject(
                KVLookupStatus.REJECTED_EXPIRED, manifest, "kv manifest expired",
                span=span, layer_range=layer_range, fingerprint_digest=fingerprint.digest(),
            ))
        if self._is_revoked(manifest):
            return KVLookup(receipt=self._reject(
                KVLookupStatus.REJECTED_REVOKED, manifest, "kv crystal or fingerprint is revoked",
                span=span, layer_range=layer_range, fingerprint_digest=fingerprint.digest(),
            ))
        if manifest.privacy_domain != privacy_domain:
            return KVLookup(receipt=self._reject(
                KVLookupStatus.REJECTED_PRIVACY, manifest,
                "privacy domain mismatch; KV may carry prompt content",
                span=span, layer_range=layer_range, fingerprint_digest=fingerprint.digest(),
            ))
        if manifest.model_fingerprint != fingerprint:
            return KVLookup(receipt=self._reject(
                KVLookupStatus.REJECTED_FINGERPRINT, manifest, "model fingerprint mismatch",
                span=span, layer_range=layer_range, fingerprint_digest=fingerprint.digest(),
            ))
        if manifest.token_span != span or tuple(manifest.layer_range) != (int(layer_range[0]), int(layer_range[1])):
            return KVLookup(receipt=self._reject(
                KVLookupStatus.REJECTED_SPAN, manifest, "token span or layer range mismatch",
                span=span, layer_range=layer_range, fingerprint_digest=fingerprint.digest(),
            ))
        store = self._store_for(manifest.block_bytes)
        chunk_manifest = ChunkManifest(
            artifact_digest=manifest.chunk_manifest["payload_digest"],
            chunk_size=manifest.block_bytes,
            chunks=tuple(chunk["digest"] for chunk in manifest.chunk_manifest["chunks"]),
            artifact_size=manifest.kv_bytes,
        )
        try:
            payload = store.get(chunk_manifest)
        except (FileNotFoundError, ValueError, OSError):
            return KVLookup(receipt=self._reject(
                KVLookupStatus.REJECTED_INTEGRITY, manifest,
                "chunk digest verification failed; nothing was served",
                span=span, layer_range=layer_range, fingerprint_digest=fingerprint.digest(),
            ))
        self._last_used[manifest.crystal_id] = time.monotonic_ns()
        self._counters["hits"] += 1
        return KVLookup(
            receipt=KVLookupReceipt(
                status=KVLookupStatus.HIT,
                crystal_id=manifest.crystal_id,
                fingerprint_digest=manifest.fingerprint_digest(),
                token_span=(span.start, span.end),
                layer_range=manifest.layer_range,
                bytes_served=len(payload),
                chunks_served=len(chunk_manifest.chunks),
                reason="verified aligned hit",
            ),
            payload=payload,
        )

    @staticmethod
    def _reject(
        status: KVLookupStatus,
        manifest: KVManifest,
        reason: str,
        *,
        span: KVTokenSpan,
        layer_range: tuple[int, int],
        fingerprint_digest: str,
    ) -> KVLookupReceipt:
        return KVLookupReceipt(
            status=status,
            crystal_id=manifest.crystal_id,
            fingerprint_digest=fingerprint_digest,
            token_span=(span.start, span.end),
            layer_range=(int(layer_range[0]), int(layer_range[1])),
            reason=reason,
        )

    # -- revocation / retention -----------------------------------------
    def revoke(self, crystal_id: str, *, reason: str = "") -> dict[str, Any]:
        _require_text(crystal_id, "crystal_id")
        marker = self.revoked_dir / crystal_id
        marker.write_text(json.dumps({"reason": reason, "revoked_at": self._clock()}), encoding="utf-8")
        return {
            "beast_object_type": "kv_revocation_receipt",
            "version": "1.0",
            "crystal_id": crystal_id,
            "reason": reason,
            "revoked": True,
        }

    def revoke_fingerprint(self, fingerprint_digest: str, *, reason: str = "") -> dict[str, Any]:
        if not _is_digest(fingerprint_digest):
            raise ValueError("fingerprint digest is invalid")
        marker = self.revoked_fingerprint_dir / fingerprint_digest.replace(":", "-")
        marker.write_text(json.dumps({"reason": reason, "revoked_at": self._clock()}), encoding="utf-8")
        return {
            "beast_object_type": "kv_fingerprint_revocation_receipt",
            "version": "1.0",
            "fingerprint_digest": fingerprint_digest,
            "reason": reason,
            "revoked": True,
        }

    def _is_revoked(self, manifest: KVManifest) -> bool:
        if (self.revoked_dir / manifest.crystal_id).exists():
            return True
        marker = self.revoked_fingerprint_dir / manifest.fingerprint_digest().replace(":", "-")
        return marker.exists()

    def evict_lru(self, target_free_bytes: int) -> KVEvictionReceipt:
        """Free at least ``target_free_bytes`` newest-use-last, never evicting pinned.

        ``freed_bytes`` is the *physical* storage delta, not the sum of the
        evicted manifests' declared sizes: chunks shared with surviving
        manifests are not released, so reporting declared bytes would overstate
        what the reclaim policy actually recovered.
        """
        target = int(target_free_bytes)
        if target < 0:
            raise ValueError("target_free_bytes cannot be negative")
        ordered = sorted(
            self._by_key.values(),
            key=lambda item: self._last_used.get(item.crystal_id, 0),
        )
        evicted: list[str] = []
        retained: list[str] = [item.crystal_id for item in ordered if item.pinned]
        candidates = [item for item in ordered if not item.pinned]
        freed = 0
        # Keep evicting until the *physical* target is met.  Summing declared
        # sizes would stop early whenever a candidate shares chunks with a
        # pinned survivor, and the caller would believe it reclaimed bytes it
        # did not.
        while candidates and freed < target:
            manifest = candidates.pop(0)
            before = self._chunk_bytes_total()
            self._forget(manifest)
            self._gc_chunks()
            freed += max(0, before - self._chunk_bytes_total())
            evicted.append(manifest.crystal_id)
        return KVEvictionReceipt(
            requested_bytes=target,
            evicted=tuple(evicted),
            freed_bytes=freed,
            retained_pinned=tuple(retained),
        )

    def evict(self, crystal_id: str) -> dict[str, Any]:
        """Drop one crystal and release any chunks no surviving manifest uses.

        Unlike :meth:`revoke`, this leaves no tombstone, so the same span may be
        cached again later.  Use it for ordinary cache cleanup; use
        :meth:`revoke` when the payload must never be served again.
        """
        _require_text(crystal_id, "crystal_id")
        target = next(
            (item for item in self._by_key.values() if item.crystal_id == crystal_id),
            None,
        )
        if target is None:
            return {
                "beast_object_type": "kv_eviction_receipt",
                "version": "1.0",
                "crystal_id": crystal_id,
                "evicted": False,
                "freed_bytes": 0,
                "reason": "not resident",
            }
        before = self._chunk_bytes_total()
        self._forget(target)
        self._gc_chunks()
        freed = max(0, before - self._chunk_bytes_total())
        return {
            "beast_object_type": "kv_eviction_receipt",
            "version": "1.0",
            "crystal_id": crystal_id,
            "evicted": True,
            "declared_bytes": target.kv_bytes,
            "freed_bytes": freed,
            "reason": "",
        }

    def _referenced_chunks(self) -> set[tuple[int, str]]:
        referenced: set[tuple[int, str]] = set()
        for manifest in self._by_key.values():
            for chunk in manifest.chunk_manifest.get("chunks", ()):
                # chunk entries are dicts (``{"digest": "sha256:..."}``) from
                # the Xet chunker; tolerate plain digests too so a future
                # manifest format cannot silently make GC delete live chunks.
                digest = chunk.get("digest") if isinstance(chunk, dict) else chunk
                if isinstance(digest, str) and digest:
                    referenced.add((int(manifest.block_bytes), digest))
        return referenced

    def _chunk_bytes_total(self) -> int:
        return sum(int(store.stats()["bytes"]) for store in self._stores.values())

    def _gc_chunks(self) -> int:
        """Delete chunk files that no live manifest references.

        Returns the number of files removed.  The chunk store is content
        addressed, so an unreferenced file can never become valid again and a
        tombstoned manifest keeps its files (its digests stay referenced).
        """
        referenced = self._referenced_chunks()
        removed = 0
        chunks_root = self.root / "chunks"
        if not chunks_root.is_dir():
            return 0
        for store_dir in chunks_root.iterdir():
            if not store_dir.is_dir() or not store_dir.name.startswith("b"):
                continue
            try:
                block_bytes = int(store_dir.name[1:])
            except ValueError:
                continue
            for path in store_dir.iterdir():
                if not path.is_file() or path.name.endswith(".tmp"):
                    continue
                digest = "sha256:" + path.name
                if (block_bytes, digest) in referenced:
                    continue
                try:
                    path.unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
        return removed

    def reclaim_for_pressure(
        self,
        pressure_level: str,
        *,
        reclaimable_bytes: int,
    ) -> KVEvictionReceipt | None:
        """Map a PSI pressure level onto a bounded KV eviction target.

        This is the binding the census said was missing: the pressure governor
        already knows when the host is ``high`` or ``critical``, but it had
        nothing to tell a KV cache to do.  The target is a fraction of the
        cache's own reclaimable bytes, never a fraction of host RAM, so a
        large host cannot cause an unbounded eviction.
        """
        level = str(pressure_level).strip().lower()
        if level not in KV_PRESSURE_TARGETS:
            raise ValueError(f"unknown pressure level: {pressure_level}")
        if int(reclaimable_bytes) < 0:
            raise ValueError("reclaimable_bytes cannot be negative")
        fraction = KV_PRESSURE_TARGETS[level]
        if fraction <= 0:
            return None
        return self.evict_lru(int(round(int(reclaimable_bytes) * fraction)))

    def _forget(self, manifest: KVManifest) -> None:
        self._by_key.pop(manifest.key(), None)
        bucket = self._by_span.get(manifest.span_key())
        if bucket is not None:
            bucket[:] = [item for item in bucket if item.crystal_id != manifest.crystal_id]
            if not bucket:
                self._by_span.pop(manifest.span_key(), None)
        self._last_used.pop(manifest.crystal_id, None)
        path = self.manifest_dir / f"{manifest.crystal_id}.json"
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _enforce_capacity(self) -> None:
        while len(self._by_key) > self._max_entries:
            self.evict_lru(1 << 62)

    # -- introspection ---------------------------------------------------
    def manifest(self, crystal_id: str) -> KVManifest | None:
        for item in self._by_key.values():
            if item.crystal_id == crystal_id:
                return item
        return None

    def manifests(self) -> tuple[KVManifest, ...]:
        return tuple(sorted(self._by_key.values(), key=lambda item: item.crystal_id))

    def stats(self) -> dict[str, Any]:
        chunks = 0
        chunk_bytes_total = 0
        for store in self._stores.values():
            value = store.stats()
            chunks += value["chunks"]
            chunk_bytes_total += value["bytes"]
        return {
            "beast_object_type": "crystal_kv_index_stats",
            "version": "1.0",
            "root": str(self.root),
            "manifests": len(self._by_key),
            "kv_bytes": sum(item.kv_bytes for item in self._by_key.values()),
            "unique_chunks": chunks,
            "unique_chunk_bytes": chunk_bytes_total,
            "hits": self._counters["hits"],
            "misses": self._counters["misses"],
            "rejections": self._counters["rejections"],
            "puts": self._counters["puts"],
            "authority": KV_AUTHORITY,
            "native_kv_portability_claimed": False,
        }


def kv_manifest_kind(value: Mapping[str, Any]) -> bool:
    """Cheap discriminator for streams that mix crystal kinds."""
    return value.get("kind") == KV_MANIFEST_KIND and value.get("authority") == KV_AUTHORITY


__all__ = [
    "CrystalKVIndex",
    "KV_AUTHORITY",
    "KV_PRESSURE_TARGETS",
    "KVEvictionReceipt",
    "KVLookup",
    "KVLookupReceipt",
    "KVLookupStatus",
    "KVManifest",
    "KVModelFingerprint",
    "KVTokenSpan",
    "kv_manifest_kind",
]
