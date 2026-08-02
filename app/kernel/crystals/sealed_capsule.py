from __future__ import annotations
from dataclasses import dataclass
import fcntl, os, stat, uuid
from .capsule_contracts import CapsuleCreationReceipt, sha256_digest
from .capsule_codec import CapsuleCodec

REQUIRED_SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL

@dataclass
class SealedCapsuleHandle:
    fd: int
    receipt: CapsuleCreationReceipt
    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd); self.fd = -1
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

class SealedCapsuleFactory:
    def create(self, *, manifest, crystal_ir, verifier_manifest, signer) -> SealedCapsuleHandle:
        if not hasattr(os, "memfd_create"):
            raise OSError("memfd_create is required")
        payload = CapsuleCodec.encode(manifest, crystal_ir, verifier_manifest, signer)
        fd = os.memfd_create(f"beast-crystal-{manifest.crystal_id[:24]}", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        try:
            view = memoryview(payload); written = 0
            while written < len(payload):
                n = os.write(fd, view[written:])
                if n <= 0: raise OSError("short write to memfd")
                written += n
            os.lseek(fd, 0, os.SEEK_SET)
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, REQUIRED_SEALS)
            actual = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
            if actual & REQUIRED_SEALS != REQUIRED_SEALS:
                raise OSError("required seals not present")
            receipt = CapsuleCreationReceipt(
                capsule_id="capsule_" + uuid.uuid4().hex,
                crystal_id=manifest.crystal_id,
                capsule_digest=sha256_digest(payload), payload_size=len(payload), seal_bitmap=actual,
                required_seals_present=True, signer_id=signer.signer_id,
            )
            return SealedCapsuleHandle(fd, receipt)
        except Exception:
            os.close(fd); raise
