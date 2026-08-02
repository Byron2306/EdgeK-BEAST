from __future__ import annotations
from typing import Any, Mapping
from .capsule_contracts import MAGIC, canonical_json, sha256_digest, SealedCrystalCapsuleManifest, ExecutionBounds

class CapsuleCodec:
    @staticmethod
    def unsigned_envelope(manifest: SealedCrystalCapsuleManifest, crystal_ir: Mapping[str, Any], verifier_manifest: Mapping[str, Any]) -> dict[str, Any]:
        ir = dict(crystal_ir)
        ir_digest = sha256_digest(canonical_json(ir))
        if ir_digest != manifest.artifact_digest:
            raise ValueError("manifest artifact_digest does not match canonical Crystal IR")
        return {
            "magic": MAGIC,
            "capsule_version": manifest.capsule_version,
            "manifest": manifest.as_dict(),
            "canonical_ir": ir,
            "verifier_manifest": dict(verifier_manifest),
        }

    @classmethod
    def encode(cls, manifest, crystal_ir, verifier_manifest, signer) -> bytes:
        unsigned = cls.unsigned_envelope(manifest, crystal_ir, verifier_manifest)
        signed_bytes = canonical_json(unsigned)
        signature = signer.sign(signed_bytes)
        envelope = dict(unsigned)
        envelope["signature_block"] = {
            "algorithm": signer.algorithm,
            "signer_id": signer.signer_id,
            "signed_digest": sha256_digest(signed_bytes),
            "signature": signature.hex(),
        }
        return canonical_json(envelope)

    @staticmethod
    def decode(payload: bytes) -> dict[str, Any]:
        import json
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict) or value.get("magic") != MAGIC:
            raise ValueError("invalid capsule magic")
        if value.get("capsule_version") != 1:
            raise ValueError("unsupported capsule version")
        if canonical_json(value) != payload:
            raise ValueError("capsule is not canonically encoded")
        return value

    @staticmethod
    def reconstruct_unsigned(envelope: Mapping[str, Any]) -> bytes:
        unsigned = {k: envelope[k] for k in ("magic", "capsule_version", "manifest", "canonical_ir", "verifier_manifest")}
        return canonical_json(unsigned)
