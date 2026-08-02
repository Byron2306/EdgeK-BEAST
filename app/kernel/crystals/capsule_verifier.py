from __future__ import annotations
import fcntl, os, stat, time
from typing import Callable
from .sealed_capsule import REQUIRED_SEALS
from .capsule_contracts import CapsuleStatus, CapsuleVerificationReceipt, canonical_json, sha256_digest
from .capsule_codec import CapsuleCodec

class CapsuleVerifier:
    def __init__(self, signature_verifier): self.signature_verifier = signature_verifier

    def verify(self, fd: int, *, expected_workspace: str, expected_privacy_domain: str,
               expected_audience: str, active_policy_digest: str,
               active_source_state_digest: str, promotion_is_valid: Callable[[str], bool],
               now: float | None = None) -> CapsuleVerificationReceipt:
        now = time.time() if now is None else now
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode): return self._r(CapsuleStatus.REJECTED_INCOMPATIBLE, reason="descriptor is not a regular anonymous file")
            seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
            if seals & REQUIRED_SEALS != REQUIRED_SEALS:
                return self._r(CapsuleStatus.REJECTED_INTEGRITY, seal_bitmap=seals, reason="required kernel seals missing")
            if st.st_size <= 0: return self._r(CapsuleStatus.REJECTED_INTEGRITY, seal_bitmap=seals, reason="empty capsule")
            payload = os.pread(fd, st.st_size, 0)
            if len(payload) != st.st_size: return self._r(CapsuleStatus.REJECTED_INTEGRITY, seal_bitmap=seals, reason="short capsule read")
            digest = sha256_digest(payload)
            env = CapsuleCodec.decode(payload)
            sig = env.get("signature_block", {})
            unsigned = CapsuleCodec.reconstruct_unsigned(env)
            if sig.get("signed_digest") != sha256_digest(unsigned):
                return self._r(CapsuleStatus.REJECTED_SIGNATURE, digest, seal_bitmap=seals, reason="signed digest mismatch")
            self.signature_verifier.verify(sig.get("signer_id", ""), bytes.fromhex(sig.get("signature", "")), unsigned)
            m = env["manifest"]
            if m["artifact_digest"] != sha256_digest(canonical_json(env["canonical_ir"])):
                return self._r(CapsuleStatus.REJECTED_INTEGRITY, digest, m.get("crystal_id",""), sig.get("signer_id",""), seals, "IR digest mismatch")
            if m["workspace_id"] != expected_workspace or m["privacy_domain"] != expected_privacy_domain or m["audience_class"] != expected_audience:
                return self._r(CapsuleStatus.REJECTED_SCOPE, digest, m["crystal_id"], sig["signer_id"], seals, "scope or audience mismatch")
            if m["policy_digest"] != active_policy_digest:
                return self._r(CapsuleStatus.REJECTED_POLICY, digest, m["crystal_id"], sig["signer_id"], seals, "policy drift")
            if m["source_state_digest"] != active_source_state_digest:
                return self._r(CapsuleStatus.REJECTED_INCOMPATIBLE, digest, m["crystal_id"], sig["signer_id"], seals, "source-state drift")
            if m["expires_at"] and now >= float(m["expires_at"]):
                return self._r(CapsuleStatus.REJECTED_EXPIRED, digest, m["crystal_id"], sig["signer_id"], seals, "capsule expired")
            if not promotion_is_valid(m["promotion_digest"]):
                return self._r(CapsuleStatus.REJECTED_REVOKED, digest, m["crystal_id"], sig["signer_id"], seals, "promotion revoked or unknown")
            return self._r(CapsuleStatus.VERIFIED_ARTIFACT, digest, m["crystal_id"], sig["signer_id"], seals, details={"authority_granted": False, "required_capability": m["required_capability"], "one_use_required": m["one_use_required"]})
        except ValueError as exc:
            status = CapsuleStatus.REJECTED_SIGNATURE if "sign" in str(exc).lower() or "trusted" in str(exc).lower() else CapsuleStatus.REJECTED_INTEGRITY
            return self._r(status, reason=str(exc))
        except Exception as exc:
            return self._r(CapsuleStatus.REJECTED_INTEGRITY, reason=f"verification failed: {exc}")

    @staticmethod
    def _r(status, capsule_digest="", crystal_id="", signer_id="", seal_bitmap=0, reason="", details=None):
        return CapsuleVerificationReceipt(status, capsule_digest, crystal_id, signer_id, seal_bitmap, reason, details=details)
