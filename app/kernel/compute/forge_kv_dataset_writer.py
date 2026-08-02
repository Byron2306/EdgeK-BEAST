"""Offline Hugging Face-style dataset layout for Forge proof contributions."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.forge_kv_xet import chunk_bytes


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


class ForgeKVDatasetWriter:
    """Create an offline dataset repository without network or publication authority."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def write(self, *, manifest: Mapping[str, Any], economics: Mapping[str, Any], attestation: Mapping[str, Any], proof_payload: bytes = b"") -> dict[str, Any]:
        if manifest.get("export_authority") not in {"verify_only", "local_only"}:
            raise ValueError("unsupported export authority")
        if manifest.get("payload_present"):
            raise ValueError("native context payload may not enter dataset layout")
        artifact_id = str(manifest.get("artifact_id") or "")
        if not artifact_id:
            raise ValueError("artifact_id is required")
        row = {"artifact": dict(manifest), "economics": dict(economics), "attestation": dict(attestation)}
        row_bytes = (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
        chunks = chunk_bytes(proof_payload or row_bytes)
        _atomic_write(self.root / "data" / "train-00000-of-00001.jsonl", row_bytes)
        _atomic_write(self.root / "manifests" / f"{artifact_id.replace(':', '_')}.json", json.dumps(manifest, sort_keys=True, indent=2).encode() + b"\n")
        _atomic_write(self.root / "xet" / "chunk-index.json", json.dumps(chunks, sort_keys=True, indent=2).encode() + b"\n")
        card = "---\nlicense: other\ntask_categories:\n- other\npretty_name: BEAST Forge KV Proof Dataset\n---\n\n# BEAST Forge KV Proof Dataset\n\nExport-safe manifests and measured proof metadata. Native KV state and execution authority are excluded.\n"
        _atomic_write(self.root / "README.md", card.encode())
        root_digest = "sha256:" + hashlib.sha256(row_bytes + chunks["root_digest"].encode()).hexdigest()
        return {"beast_object_type": "forge_kv_offline_dataset_receipt", "version": "1.0", "root": str(self.root), "artifact_id": artifact_id, "row_count": 1, "chunk_count": chunks["chunk_count"], "dataset_root_digest": root_digest, "online_published": False, "authority": "offline_staging_only"}
