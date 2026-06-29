"""Append-only, tamper-evident ledger for crystallized-compute lifecycle events.

This is blockchain-style local evidence: every block commits to its payload and
the previous block.  It is not a decentralized consensus network or financial
cryptocurrency, and the API reports that boundary explicitly.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


@dataclass(frozen=True)
class CrystalChainVerification:
    valid: bool
    block_count: int
    head_hash: str
    errors: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_chain_verification", "version": "1.0",
            "valid": self.valid, "block_count": self.block_count,
            "head_hash": self.head_hash, "errors": self.errors,
            "consensus": "local_hash_chain_no_distributed_consensus",
        }


class CrystalChainLedger:
    GENESIS_PREVIOUS_HASH = "sha256:" + "0" * 64

    def __init__(self, path: Optional[Path] = None, *, node_id: str = "local-beast") -> None:
        self.path = path or Path(__file__).resolve().parents[2] / "data" / "crystal_chain" / "blocks.jsonl"
        self.node_id = node_id

    @staticmethod
    def _payload_hash(payload: Dict[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()

    @staticmethod
    def _block_hash(header: Dict[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(_canonical(header)).hexdigest()

    def _read_locked(self, handle) -> List[Dict[str, Any]]:
        handle.seek(0)
        blocks = []
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                blocks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                blocks.append({"_parse_error": str(exc), "_line": line_number})
        return blocks

    def append(self, event_type: str, artifact_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            blocks = self._read_locked(handle)
            verification = self._verify_blocks(blocks)
            if not verification.valid:
                raise ValueError("crystal chain verification failed before append")
            index = len(blocks)
            previous_hash = blocks[-1]["block_hash"] if blocks else self.GENESIS_PREVIOUS_HASH
            safe_payload = json.loads(_canonical(payload).decode("utf-8"))
            header = {
                "index": index,
                "previous_hash": previous_hash,
                "payload_hash": self._payload_hash(safe_payload),
                "event_type": str(event_type),
                "artifact_id": str(artifact_id),
                "node_id": self.node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            block = {
                "beast_object_type": "crystallized_compute_block",
                "version": "1.0",
                **header,
                "block_hash": self._block_hash(header),
                "payload": safe_payload,
            }
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(block, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return block

    def blocks(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            blocks = self._read_locked(handle)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return blocks

    def verify(self) -> CrystalChainVerification:
        return self._verify_blocks(self.blocks())

    def _verify_blocks(self, blocks: Iterable[Dict[str, Any]]) -> CrystalChainVerification:
        rows = list(blocks)
        errors: List[Dict[str, Any]] = []
        previous = self.GENESIS_PREVIOUS_HASH
        for expected_index, block in enumerate(rows):
            if "_parse_error" in block:
                errors.append({"index": expected_index, "reason": "invalid_json"})
                continue
            header = {
                key: block.get(key) for key in (
                    "index", "previous_hash", "payload_hash", "event_type",
                    "artifact_id", "node_id", "timestamp",
                )
            }
            checks = {
                "index": block.get("index") == expected_index,
                "previous_hash": block.get("previous_hash") == previous,
                "payload_hash": block.get("payload_hash") == self._payload_hash(block.get("payload") or {}),
                "block_hash": block.get("block_hash") == self._block_hash(header),
            }
            for name, passed in checks.items():
                if not passed:
                    errors.append({"index": expected_index, "reason": f"{name}_mismatch"})
            previous = str(block.get("block_hash") or previous)
        return CrystalChainVerification(not errors, len(rows), previous if rows else self.GENESIS_PREVIOUS_HASH, errors)

    def state(self) -> Dict[str, Any]:
        verification = self.verify()
        return {
            **verification.to_dict(),
            "path": str(self.path),
            "authority": "tamper_evident_local_ledger",
            "financial_asset": False,
            "immutable_claim": "append-only hash chain; filesystem administrator can replace the entire chain",
        }

