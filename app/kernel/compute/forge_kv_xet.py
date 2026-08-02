"""Content-defined chunk manifests for export-safe Forge proof datasets.

The chunker uses a deterministic rolling buzhash boundary rule. It transports
bytes only and grants no verification, adoption, or execution authority.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Iterable

_TABLE = tuple(int.from_bytes(hashlib.sha256(f"beast-xet-{i}".encode()).digest()[:8], "big") for i in range(256))
_MASK64 = (1 << 64) - 1


def _rol(value: int, shift: int) -> int:
    shift %= 64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


@dataclass(frozen=True)
class XetChunk:
    index: int
    offset: int
    size: int
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _boundaries(payload: bytes, *, min_size: int, avg_size: int, max_size: int, window: int = 64) -> Iterable[tuple[int, int]]:
    if not payload:
        return
    mask_bits = max(8, (avg_size - 1).bit_length() - 1)
    boundary_mask = (1 << mask_bits) - 1
    start = 0
    rolling = 0
    ring = bytearray(window)
    for index, byte in enumerate(payload):
        slot = index % window
        outgoing = ring[slot]
        ring[slot] = byte
        rolling = _rol(rolling, 1) ^ _TABLE[byte] ^ _rol(_TABLE[outgoing], window)
        length = index + 1 - start
        should_cut = length >= min_size and ((rolling & boundary_mask) == 0 or length >= max_size)
        if should_cut:
            yield start, index + 1
            start = index + 1
            rolling = 0
            ring = bytearray(window)
    if start < len(payload):
        yield start, len(payload)


def chunk_bytes(
    payload: bytes,
    *,
    min_size: int = 64 * 1024,
    avg_size: int = 256 * 1024,
    max_size: int = 1024 * 1024,
    max_bytes: int = 256 * 1024 * 1024,
    chunk_size: int | None = None,
) -> dict[str, Any]:
    if len(payload) > max_bytes:
        raise ValueError("payload exceeds bounded Xet staging limit")
    if chunk_size is not None:
        if chunk_size < 4096:
            raise ValueError("chunk_size too small")
        min_size = avg_size = max_size = int(chunk_size)
        chunks = []
        for idx, start in enumerate(range(0, len(payload), chunk_size)):
            part = payload[start:start + chunk_size]
            chunks.append(XetChunk(idx, start, len(part), "sha256:" + hashlib.sha256(part).hexdigest()))
        root_body = "|".join(f"{c.index}:{c.offset}:{c.size}:{c.digest}" for c in chunks).encode()
        return {"beast_object_type":"xet_chunk_manifest","version":"2.0","algorithm":"fixed_v1_compatibility_mode","parameters":{"chunk_size":chunk_size},"total_bytes":len(payload),"chunk_count":len(chunks),"chunks":[c.to_dict() for c in chunks],"root_digest":"sha256:"+hashlib.sha256(root_body).hexdigest(),"authority":"data_transport_only","native_kv_portability_claimed":False}
    if not (4096 <= min_size <= avg_size <= max_size):
        raise ValueError("chunk sizes must satisfy 4096 <= min <= avg <= max")
    chunks: list[XetChunk] = []
    for idx, (start, end) in enumerate(_boundaries(payload, min_size=min_size, avg_size=avg_size, max_size=max_size)):
        part = payload[start:end]
        chunks.append(XetChunk(idx, start, len(part), "sha256:" + hashlib.sha256(part).hexdigest()))
    root_body = "|".join(f"{c.index}:{c.offset}:{c.size}:{c.digest}" for c in chunks).encode()
    return {
        "beast_object_type": "xet_chunk_manifest",
        "version": "2.0",
        "algorithm": "beast_buzhash_cdc_v1",
        "parameters": {"min_size": min_size, "avg_size": avg_size, "max_size": max_size},
        "total_bytes": len(payload),
        "chunk_count": len(chunks),
        "chunks": [chunk.to_dict() for chunk in chunks],
        "root_digest": "sha256:" + hashlib.sha256(root_body).hexdigest(),
        "authority": "data_transport_only",
        "native_kv_portability_claimed": False,
    }
