"""Sealed memfd crystal payloads with a portable file-backed test fallback."""
from __future__ import annotations

import os
import fcntl
import base64
import time
import json
from dataclasses import dataclass

from app.kernel.crystals.capsule_codec import CapsuleCodec
from app.kernel.crystals.capsule_contracts import (
    ExecutionBounds,
    SealedCrystalCapsuleManifest,
    canonical_json as capsule_canonical_json,
    sha256_digest as capsule_sha256_digest,
)


@dataclass(frozen=True)
class SealedCrystal:
    fd: int
    digest: str
    size: int
    sealed: bool
    signature: str = ""
    authority_ref: str = "beast.local/crystal-forge"
    audience: str = "beast-crystal-executor"
    expires_at: float = 0.0
    capability_ref: str = ""
    appraisal_ref: str = ""
    payload_digest: str = ""
    payload_type: str = "opaque-crystal-ir"
    envelope_version: str = "BEAST_CRYSTAL_CAPSULE/v1"

    def signed_envelope(self) -> bytes:
        return json.dumps(
            {
                "appraisal_ref": self.appraisal_ref,
                "audience": self.audience,
                "authority_ref": self.authority_ref,
                "capability_ref": self.capability_ref,
                "envelope_version": self.envelope_version,
                "expires_at": self.expires_at,
                "payload_digest": self.digest,
                "raw_payload_digest": self.payload_digest,
                "payload_type": self.payload_type,
                "size": self.size,
                "version": "beast.sealed-crystal.v1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class CrystalCapsule:
    def create(self, payload: bytes, *, signer=None, authority_ref: str = "beast.local/crystal-forge", audience: str = "beast-crystal-executor", expires_at: float = 0.0, capability_ref: str = "", appraisal_ref: str = "") -> SealedCrystal:
        if not payload:
            raise ValueError("crystal payload cannot be empty")
        if not hasattr(os, "memfd_create"):
            raise OSError("memfd_create is required for crystal capsules")
        raw_digest = capsule_sha256_digest(payload)
        crystal_ir = {
            "payload_b64": base64.b64encode(payload).decode("ascii"),
            "payload_digest": raw_digest,
            "payload_type": "opaque-crystal-ir",
        }
        artifact_digest = capsule_sha256_digest(capsule_canonical_json(crystal_ir))
        policy_digest = capsule_sha256_digest(capsule_canonical_json({"policy": "legacy-compute-capsule-v1"}))
        signer_id = authority_ref or "beast.local/crystal-forge"
        manifest_expires_at = expires_at or 4102444800.0
        manifest = SealedCrystalCapsuleManifest(
            crystal_id="legacy:" + raw_digest.removeprefix("sha256:")[:24],
            crystal_ir_version=1,
            artifact_digest=artifact_digest,
            promotion_digest=appraisal_ref or raw_digest,
            policy_digest=policy_digest,
            source_state_digest=raw_digest,
            workspace_id="legacy",
            privacy_domain="operator",
            task_class="crystal_capsule",
            audience_class=audience,
            required_capability=capability_ref or "read_verified",
            one_use_required=bool(capability_ref),
            expires_at=manifest_expires_at,
            verifier_id=signer_id,
            rollback_contract_digest=policy_digest,
            signer_id=signer_id,
            execution_bounds=ExecutionBounds(
                max_runtime_ms=1000,
                max_memory_bytes=max(len(payload) * 4, 1),
                max_output_bytes=max(len(payload), 1),
            ),
        )
        unsigned = CapsuleCodec.unsigned_envelope(manifest, crystal_ir, {"verifier_id": signer_id})
        signed_bytes = capsule_canonical_json(unsigned)
        signature_bytes = signer.sign(signed_bytes) if signer else b""
        envelope = dict(unsigned)
        envelope["signature_block"] = {
            "algorithm": "ed25519" if signer else "none",
            "signer_id": signer_id,
            "signed_digest": capsule_sha256_digest(signed_bytes),
            "signature": signature_bytes.hex(),
        }
        envelope_payload = capsule_canonical_json(envelope)
        fd = os.memfd_create("beast-crystal", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        os.write(fd, envelope_payload)
        os.lseek(fd, 0, os.SEEK_SET)
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        digest = capsule_sha256_digest(envelope_payload)
        signature = base64.b64encode(signature_bytes).decode("ascii") if signer else ""
        return SealedCrystal(
            fd, digest, len(envelope_payload), True, signature, authority_ref,
            audience, expires_at, capability_ref, appraisal_ref, raw_digest,
        )

    def verify(self, capsule: SealedCrystal, *, verifier=None, expected_authority: str | None = None, expected_audience: str | None = None, capability_ref: str | None = None, appraisal_ref: str | None = None, now: float | None = None) -> bool:
        if expected_authority is not None and capsule.authority_ref != expected_authority:
            return False
        if not capsule.authority_ref:
            return False
        if expected_audience is not None and capsule.audience != expected_audience:
            return False
        if capsule.expires_at and (time.time() if now is None else now) >= capsule.expires_at:
            return False
        if capability_ref is not None and capsule.capability_ref != capability_ref:
            return False
        if appraisal_ref is not None and capsule.appraisal_ref != appraisal_ref:
            return False
        try:
            seals = fcntl.fcntl(capsule.fd, fcntl.F_GET_SEALS)
            required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
            if seals & required != required:
                return False
        except (AttributeError, OSError):
            return False
        if capsule.size <= 0:
            return False
        stat = os.fstat(capsule.fd)
        if stat.st_size != capsule.size:
            return False
        payload = os.pread(capsule.fd, capsule.size, 0)
        if capsule_sha256_digest(payload) != capsule.digest:
            return False
        try:
            envelope = CapsuleCodec.decode(payload)
            manifest = envelope["manifest"]
            canonical_ir = envelope["canonical_ir"]
            signature_block = envelope.get("signature_block", {})
            unsigned = CapsuleCodec.reconstruct_unsigned(envelope)
            if signature_block.get("signed_digest") != capsule_sha256_digest(unsigned):
                return False
            if manifest.get("audience_class") != capsule.audience:
                return False
            if manifest.get("signer_id") != capsule.authority_ref:
                return False
            if manifest.get("required_capability") != (capsule.capability_ref or "read_verified"):
                return False
            if manifest.get("promotion_digest") != (capsule.appraisal_ref or capsule.payload_digest):
                return False
            if manifest.get("artifact_digest") != capsule_sha256_digest(capsule_canonical_json(canonical_ir)):
                return False
            if canonical_ir.get("payload_digest") != capsule.payload_digest:
                return False
            if canonical_ir.get("payload_type") != capsule.payload_type:
                return False
            if verifier is not None:
                signature_hex = str(signature_block.get("signature") or "")
                if not signature_hex or not capsule.signature:
                    return False
                signature_bytes = bytes.fromhex(signature_hex)
                if base64.b64encode(signature_bytes).decode("ascii") != capsule.signature:
                    return False
                verifier.verify(signature_bytes, unsigned)
        except Exception:
            return False
        return True
