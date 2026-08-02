from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Callable, Mapping

from .context_transfer_manifest import ContextCompatibilityEnvelope, ContextTransferManifest
from .native_context_restore_verifier import (
    NativeContextRestoreVerifier,
    RestoreObservation,
    RestoreVerificationReceipt,
)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + sha256(raw).hexdigest()


@dataclass(frozen=True)
class TransferLabReceipt:
    status: str
    transfer_id: str
    manifest_digest: str
    source_node_id: str
    receiver_node_id: str
    compatibility_ok: bool
    mismatches: tuple[str, ...]
    restore_receipt: RestoreVerificationReceipt | None
    production_portable: bool
    receiver_authority: str
    refusal_code: str | None
    receipt_digest: str


class NativeContextTransferLab:
    """Experimental same-engine transfer. Never grants production portability."""

    def __init__(self, verifier: NativeContextRestoreVerifier | None = None) -> None:
        self.verifier = verifier or NativeContextRestoreVerifier()

    def run(
        self,
        *,
        manifest: ContextTransferManifest,
        receiver_node_id: str,
        receiver_envelope: ContextCompatibilityEnvelope,
        baseline_runner: Callable[[], RestoreObservation],
        restore_runner: Callable[[ContextTransferManifest], RestoreObservation],
        equivalence: Callable[[str, str], bool] | None = None,
    ) -> TransferLabReceipt:
        compatible, mismatches = manifest.envelope.compare(receiver_envelope)
        refusal: str | None = None
        restore_receipt: RestoreVerificationReceipt | None = None
        status = "rejected_incompatible"
        if compatible:
            baseline = baseline_runner()
            restored = restore_runner(manifest)
            restore_receipt = self.verifier.verify(
                source_context_digest=manifest.context_digest,
                baseline=baseline,
                restored=restored,
                equivalence=equivalence,
            )
            if restore_receipt.prefill_displaced and restore_receipt.continuation_equivalent:
                status = "lab_verified"
            else:
                status = "restore_verification_failed"
                refusal = restore_receipt.refusal_reason or "verification_failed"
        else:
            refusal = "rejected_incompatible"
        body = {
            "status": status,
            "transfer_id": manifest.transfer_id,
            "manifest_digest": manifest.digest,
            "source_node_id": manifest.source_node_id,
            "receiver_node_id": receiver_node_id,
            "compatibility_ok": compatible,
            "mismatches": mismatches,
            "restore_receipt": asdict(restore_receipt) if restore_receipt else None,
            "production_portable": False,
            "receiver_authority": "local_verification_only",
            "refusal_code": refusal,
        }
        return TransferLabReceipt(
            status=status,
            transfer_id=manifest.transfer_id,
            manifest_digest=manifest.digest,
            source_node_id=manifest.source_node_id,
            receiver_node_id=receiver_node_id,
            compatibility_ok=compatible,
            mismatches=mismatches,
            restore_receipt=restore_receipt,
            production_portable=False,
            receiver_authority="local_verification_only",
            refusal_code=refusal,
            receipt_digest=_digest(body),
        )
