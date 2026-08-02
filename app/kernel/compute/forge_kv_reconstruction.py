"""Remote chunk reconstruction and sovereign local verification."""
from __future__ import annotations

from typing import Any, Callable, Mapping
from app.kernel.compute.forge_kv_bucket import sha256_bytes


def reconstruct(manifest: Mapping[str,Any], fetch_chunk: Callable[[str],bytes]) -> tuple[bytes,dict[str,Any]]:
    chunks=manifest.get("chunks") or []
    ordered=[]
    for expected_index,item in enumerate(chunks):
        if int(item.get("index",-1)) != expected_index: raise ValueError("chunk order is invalid")
        payload=fetch_chunk(str(item["digest"]))
        if len(payload) != int(item["size"]) or sha256_bytes(payload) != item["digest"]: raise ValueError("chunk verification failed")
        ordered.append(payload)
    reconstructed=b"".join(ordered)
    if len(reconstructed) != int(manifest.get("total_bytes",-1)): raise ValueError("reconstructed size mismatch")
    return reconstructed,{"beast_object_type":"forge_kv_reconstruction_receipt","version":"1.0","chunk_count":len(chunks),"total_bytes":len(reconstructed),"verified":True,"authority":"local_verification_only","promotion_granted":False}
