from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Callable

from .context_transfer_manifest import ContextCompatibilityEnvelope, ContextTransferManifest
from .native_context_restore_verifier import RestoreObservation
from .native_context_transfer_lab import NativeContextTransferLab, TransferLabReceipt


def _digest(value: Any) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class PrismR7Closure:
    lab_receipt: TransferLabReceipt
    source_native_context_exported: bool
    production_registry_updated: bool
    transfer_authority: str
    closure_digest: str


class PrismR7TransferPlane:
    def __init__(self, lab: NativeContextTransferLab | None = None) -> None:
        self.lab = lab or NativeContextTransferLab()

    def evaluate_transfer(
        self,
        *,
        manifest: ContextTransferManifest,
        receiver_node_id: str,
        receiver_envelope: ContextCompatibilityEnvelope,
        baseline_runner: Callable[[], RestoreObservation],
        restore_runner: Callable[[ContextTransferManifest], RestoreObservation],
        equivalence=None,
    ) -> PrismR7Closure:
        receipt = self.lab.run(
            manifest=manifest,
            receiver_node_id=receiver_node_id,
            receiver_envelope=receiver_envelope,
            baseline_runner=baseline_runner,
            restore_runner=restore_runner,
            equivalence=equivalence,
        )
        body = {
            "lab_receipt": asdict(receipt),
            "source_native_context_exported": True,
            "production_registry_updated": False,
            "transfer_authority": "laboratory_verify_only",
        }
        return PrismR7Closure(
            lab_receipt=receipt,
            source_native_context_exported=True,
            production_registry_updated=False,
            transfer_authority="laboratory_verify_only",
            closure_digest=_digest(body),
        )
