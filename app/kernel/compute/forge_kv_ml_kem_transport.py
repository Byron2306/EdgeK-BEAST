"""ML-KEM-bound Forge KV transport receipts.

This module proves a narrow claim:

* a Commons peer decapsulation challenge was confirmed with ML-KEM;
* an authenticated KV transfer manifest was acknowledged and checksum-bound;
* no shared secret or tensor payload bytes are serialized into the receipt.

It does not claim model-quality equivalence, portable raw-KV compatibility, or
provider-call avoidance. Those require separate execution/reuse evidence.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.kernel.commons.ml_kem import ML_KEM_ALGORITHM
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso


FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY = "ml_kem_confirmed_checksum_bound_transfer_only"


def build_ml_kem_bound_transport_receipt(
    *,
    kv_manifest: Mapping[str, Any],
    ml_kem_receipt: Mapping[str, Any],
    payload_kind: str = "engine_native",
) -> dict[str, Any]:
    """Build a bounded receipt from a KV transfer manifest and ML-KEM receipt."""
    _reject_private_material(kv_manifest)
    _reject_private_material(ml_kem_receipt)
    if kv_manifest.get("beast_object_type") != "kv_cache_network_manifest":
        raise ValueError("kv_manifest must be a kv_cache_network_manifest")
    if ml_kem_receipt.get("beast_object_type") != "commons_ml_kem_gauntlet_receipt":
        raise ValueError("ml_kem_receipt must be a commons_ml_kem_gauntlet_receipt")

    acknowledgement = kv_manifest.get("acknowledgement") if isinstance(kv_manifest.get("acknowledgement"), Mapping) else {}
    checksum = str(kv_manifest.get("tensor_payload_sha256") or kv_manifest.get("checksum_sha256") or "")
    accepted = bool(acknowledgement.get("accepted") is True)
    checksum_ack = str(acknowledgement.get("tensor_payload_sha256") or "")
    engine_native = bool(kv_manifest.get("engine_native_tensor_payload") is True)
    nodes = tuple(item for item in (ml_kem_receipt.get("nodes") or ()) if isinstance(item, Mapping))
    confirmed_nodes = tuple(item for item in nodes if item.get("confirmed") is True and item.get("secret_exported") is False)
    pairwise = tuple(item for item in (ml_kem_receipt.get("pairwise_transcript_matrix") or ()) if isinstance(item, Mapping))
    ml_kem_passed = (
        ml_kem_receipt.get("status") == "passed"
        and str(ml_kem_receipt.get("algorithm") or "") == ML_KEM_ALGORITHM
        and bool(nodes)
        and len(confirmed_nodes) == len(nodes)
        and str(ml_kem_receipt.get("secret_storage_policy") or "") == "shared_secret_bytes_never_serialized"
    )
    kv_passed = (
        str(kv_manifest.get("status") or "") == "transferred"
        and accepted
        and checksum.startswith("sha256:")
        and checksum_ack == checksum
        and int(kv_manifest.get("size_bytes") or 0) > 0
        and engine_native
    )
    verified = bool(ml_kem_passed and kv_passed and payload_kind == "engine_native")
    kv_transfer = {
        "block_id": str(kv_manifest.get("block_id") or ""),
        "transfer_id": str(kv_manifest.get("transfer_id") or ""),
        "source_node": str(kv_manifest.get("source_node") or "unknown"),
        "target_endpoint_digest": sha256_digest(str(kv_manifest.get("target_endpoint") or "")),
        "engine": str(kv_manifest.get("engine") or ""),
        "target_engine": str(kv_manifest.get("target_engine") or ""),
        "tensor_payload_sha256": checksum,
        "tensor_payload_size_bytes": int(kv_manifest.get("size_bytes") or 0),
        "tensor_payload_format": str(kv_manifest.get("tensor_payload_format") or ""),
        "engine_native_tensor_payload": engine_native,
        "manifest_digest": sha256_digest(kv_manifest),
        "acknowledgement_digest": sha256_digest(acknowledgement) if acknowledgement else "",
        "accepted": accepted,
        "stored_location": str(acknowledgement.get("stored_location") or ""),
    }
    ml_kem = {
        "algorithm": str(ml_kem_receipt.get("algorithm") or ""),
        "status": str(ml_kem_receipt.get("status") or ""),
        "node_count": len(nodes),
        "confirmed_count": len(confirmed_nodes),
        "pairwise_transcript_edges": len(pairwise),
        "node_ids": tuple(str(item.get("node_id") or "") for item in nodes),
        "public_key_digests": tuple(str(item.get("public_key_digest") or "") for item in nodes),
        "ciphertext_digests": tuple(str(item.get("ciphertext_digest") or "") for item in nodes),
        "transcript_digests": tuple(str(item.get("transcript_digest") or "") for item in nodes),
        "secret_storage_policy": str(ml_kem_receipt.get("secret_storage_policy") or ""),
        "secret_exported": any(item.get("secret_exported") is True for item in nodes),
        "receipt_digest": str(ml_kem_receipt.get("receipt_digest") or sha256_digest(ml_kem_receipt)),
    }
    receipt = {
        "beast_object_type": "forge_kv_ml_kem_transport_receipt",
        "version": "1.0",
        "status": "passed" if verified else "failed",
        "verified": verified,
        "transport_verified": verified,
        "observed_at": utc_now_iso(),
        "authority": FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY,
        "claim_boundary": (
            "ML-KEM peer confirmation plus checksum-bound KV transfer only; "
            "no provider-call avoidance, model-quality equivalence, or portable raw-KV reuse is claimed"
        ),
        "payload_kind": payload_kind,
        "kv_transfer": kv_transfer,
        "ml_kem": ml_kem,
        "bytes_transferred_verified": kv_transfer["tensor_payload_size_bytes"] if verified else 0,
        "provider_calls_avoided": 0,
        "tokens_avoided_observed": 0,
        "promotion_granted": False,
        "secret_material_serialized": False,
        "tensor_payload_serialized": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def validate_ml_kem_bound_transport_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return a conservative validation report for a transport receipt."""
    errors: list[str] = []
    if receipt.get("beast_object_type") != "forge_kv_ml_kem_transport_receipt":
        errors.append("unexpected object type")
    if receipt.get("authority") != FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY:
        errors.append("unexpected authority")
    if receipt.get("secret_material_serialized") is not False:
        errors.append("secret material serialization was not explicitly false")
    if receipt.get("tensor_payload_serialized") is not False:
        errors.append("tensor payload serialization was not explicitly false")
    kv_transfer = receipt.get("kv_transfer") if isinstance(receipt.get("kv_transfer"), Mapping) else {}
    ml_kem = receipt.get("ml_kem") if isinstance(receipt.get("ml_kem"), Mapping) else {}
    if str(ml_kem.get("algorithm") or "") != ML_KEM_ALGORITHM:
        errors.append("ML-KEM algorithm is not ML-KEM-768")
    if ml_kem.get("status") != "passed":
        errors.append("ML-KEM gauntlet did not pass")
    if int(ml_kem.get("confirmed_count") or 0) != int(ml_kem.get("node_count") or -1):
        errors.append("not all ML-KEM nodes confirmed")
    if ml_kem.get("secret_exported") is not False:
        errors.append("ML-KEM node exported a secret")
    if kv_transfer.get("accepted") is not True:
        errors.append("KV transfer was not accepted")
    if kv_transfer.get("engine_native_tensor_payload") is not True:
        errors.append("KV payload was not marked engine-native")
    if int(kv_transfer.get("tensor_payload_size_bytes") or 0) <= 0:
        errors.append("KV payload size was empty")
    if not str(kv_transfer.get("tensor_payload_sha256") or "").startswith("sha256:"):
        errors.append("KV payload digest is missing")
    valid = not errors and receipt.get("transport_verified") is True and receipt.get("status") == "passed"
    return {
        "beast_object_type": "forge_kv_ml_kem_transport_validation",
        "version": "1.0",
        "valid": valid,
        "errors": tuple(errors),
        "receipt_digest": str(receipt.get("receipt_digest") or sha256_digest(receipt)),
    }


def _reject_private_material(value: Mapping[str, Any]) -> None:
    forbidden: list[str] = []

    def walk(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                lowered = str(key).lower()
                if lowered in {"shared_secret", "secret_key", "private_key", "payload_base64", "raw_payload", "tensor_payload"}:
                    forbidden.append(f"{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")

    walk(value, "$")
    if forbidden:
        raise PermissionError("Forge KV ML-KEM transport receipt input contains private/raw fields: " + ", ".join(sorted(set(forbidden))))
