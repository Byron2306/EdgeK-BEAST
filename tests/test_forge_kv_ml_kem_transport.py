import pytest

from app.kernel.commons.ml_kem import ML_KEM_ALGORITHM
from app.kernel.compute.forge_kv_ml_kem_transport import (
    FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY,
    build_ml_kem_bound_transport_receipt,
    validate_ml_kem_bound_transport_receipt,
)


def test_forge_kv_ml_kem_transport_receipt_verifies_narrow_transport_claim():
    receipt = build_ml_kem_bound_transport_receipt(
        kv_manifest=_kv_manifest(),
        ml_kem_receipt=_ml_kem_receipt(),
    )
    validation = validate_ml_kem_bound_transport_receipt(receipt)

    assert receipt["beast_object_type"] == "forge_kv_ml_kem_transport_receipt"
    assert receipt["status"] == "passed"
    assert receipt["verified"] is True
    assert receipt["authority"] == FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY
    assert receipt["bytes_transferred_verified"] == 18
    assert receipt["provider_calls_avoided"] == 0
    assert receipt["tokens_avoided_observed"] == 0
    assert receipt["secret_material_serialized"] is False
    assert receipt["tensor_payload_serialized"] is False
    assert validation["valid"] is True


def test_forge_kv_ml_kem_transport_receipt_rejects_private_or_raw_material():
    manifest = {**_kv_manifest(), "payload_base64": "not allowed"}

    with pytest.raises(PermissionError, match="private/raw"):
        build_ml_kem_bound_transport_receipt(
            kv_manifest=manifest,
            ml_kem_receipt=_ml_kem_receipt(),
        )


def test_forge_kv_ml_kem_transport_receipt_does_not_verify_synthetic_payload_kind():
    receipt = build_ml_kem_bound_transport_receipt(
        kv_manifest=_kv_manifest(),
        ml_kem_receipt=_ml_kem_receipt(),
        payload_kind="test_oracle",
    )
    validation = validate_ml_kem_bound_transport_receipt(receipt)

    assert receipt["status"] == "failed"
    assert receipt["verified"] is False
    assert receipt["bytes_transferred_verified"] == 0
    assert validation["valid"] is False


def _kv_manifest() -> dict:
    checksum = "sha256:" + "a" * 64
    return {
        "beast_object_type": "kv_cache_network_manifest",
        "version": "1.0",
        "status": "transferred",
        "block_id": "kv_mlkem_test",
        "transfer_id": "transfer_mlkem_test",
        "model": "llama",
        "tokenizer": "tok",
        "prompt_prefix_hash": "sha256:" + "b" * 64,
        "system_prompt_hash": "sha256:" + "c" * 64,
        "engine": "sglang",
        "target_engine": "sglang",
        "precision": "bf16",
        "num_layers": 2,
        "num_heads": 2,
        "head_dim": 8,
        "seq_len": 16,
        "size_bytes": 18,
        "source_node": "commons-a",
        "target_endpoint": "https://commons-b.example/edgek/kv-cache/receive",
        "checksum_sha256": checksum,
        "tensor_payload_sha256": checksum,
        "tensor_payload_format": "safetensors",
        "engine_native_tensor_payload": True,
        "acknowledgement": {
            "accepted": True,
            "block_id": "kv_mlkem_test",
            "transfer_id": "transfer_mlkem_test",
            "tensor_payload_sha256": checksum,
            "stored_location": "storage",
        },
    }


def _ml_kem_receipt() -> dict:
    nodes = [
        {
            "node_id": "commons-a",
            "confirmed": True,
            "secret_exported": False,
            "public_key_digest": "sha256:" + "d" * 64,
            "ciphertext_digest": "sha256:" + "e" * 64,
            "transcript_digest": "sha256:" + "f" * 64,
        },
        {
            "node_id": "commons-b",
            "confirmed": True,
            "secret_exported": False,
            "public_key_digest": "sha256:" + "1" * 64,
            "ciphertext_digest": "sha256:" + "2" * 64,
            "transcript_digest": "sha256:" + "3" * 64,
        },
    ]
    return {
        "beast_object_type": "commons_ml_kem_gauntlet_receipt",
        "version": "1.0",
        "status": "passed",
        "algorithm": ML_KEM_ALGORITHM,
        "nodes": nodes,
        "pairwise_transcript_matrix": [
            {"source": "commons-a", "target": "commons-b", "transcript_digest": "sha256:" + "4" * 64}
        ],
        "secret_storage_policy": "shared_secret_bytes_never_serialized",
        "receipt_digest": "sha256:" + "5" * 64,
    }
