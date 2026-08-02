from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Protocol

from .x7_contracts import X7Approval, X7LaneResult, X7Preflight, X7Receipt, X7Refusal


class ProductionNICBackend(Protocol):
    def inspect(self, approval: X7Approval) -> X7Preflight: ...
    def attach(self, approval: X7Approval) -> int | None: ...
    def run_af_xdp(self, approval: X7Approval, object_path: Path) -> X7LaneResult: ...
    def detach_and_restore(self, approval: X7Approval, prior_program_id: int | None) -> tuple[bool, bool]: ...
    def run_socket_shadow(self, approval: X7Approval, object_path: Path) -> X7LaneResult: ...


class X7ProductionCanary:
    def __init__(self, backend: ProductionNICBackend):
        self.backend = backend

    def run(self, approval: X7Approval, object_path: Path, receipt_path: Path | None = None) -> X7Receipt:
        approval.validate()
        if not object_path.is_file():
            raise X7Refusal("object file missing")
        from hashlib import sha256
        actual = "sha256:" + sha256(object_path.read_bytes()).hexdigest()
        if actual != approval.object_digest:
            raise X7Refusal("object root does not match approval")
        preflight = self.backend.inspect(approval)
        preflight.validate()
        prior = preflight.existing_xdp_program_id
        attached = False
        af_result: X7LaneResult | None = None
        detached = restored = False
        try:
            self.backend.attach(approval)
            attached = True
            af_result = self.backend.run_af_xdp(approval, object_path)
            if af_result.packets > approval.max_packets or af_result.bytes_sent > approval.max_bytes:
                raise X7Refusal("AF_XDP canary exceeded approved budget")
        finally:
            if attached:
                detached, restored = self.backend.detach_and_restore(approval, prior)
        if af_result is None:
            raise X7Refusal("AF_XDP canary produced no result")
        af_result = X7LaneResult(**{**asdict(af_result), "detached": detached, "rollback_verified": restored})
        shadow = self.backend.run_socket_shadow(approval, object_path)
        receipt = X7Receipt.build(approval, af_result, shadow, restored)
        if not receipt.valid:
            raise X7Refusal("X7 closure invariants failed")
        if receipt_path is not None:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n")
        return receipt
