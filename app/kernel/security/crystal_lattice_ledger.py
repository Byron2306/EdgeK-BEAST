"""Append-only lattice checkpoints for crystallized compute matrices.

The Phase 7 trainer can overwrite `*_latest` artifacts for operator
convenience.  This ledger gives those moving heads an append-only history:
every vector/matrix checkpoint is committed by hash, and defragging creates a
compact snapshot without deleting or rewriting prior checkpoints.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LatticeLedgerVerification:
    valid: bool
    checkpoint_count: int
    head_hash: str
    errors: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "crystal_lattice_ledger_verification",
            "version": "1.0",
            "valid": self.valid,
            "checkpoint_count": self.checkpoint_count,
            "head_hash": self.head_hash,
            "errors": self.errors,
            "claim_boundary": "append_only_hash_history_for_lattice_metadata_not_model_weight_authority",
        }


class CrystalLatticeLedger:
    GENESIS_PREVIOUS_HASH = "sha256:" + "0" * 64

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or Path("benchmarks/results/crystal_lattice_ledger"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "lattice_checkpoints.jsonl"
        self.defrag_path = self.root / "lattice_defrag_latest.json"

    def append_latest(
        self,
        *,
        distillation_root: Optional[Path] = None,
        event_type: str = "lattice_checkpoint",
    ) -> Dict[str, Any]:
        source = Path(distillation_root or Path("benchmarks/results/crystal_to_adapter_distillation"))
        lattice = self._read_json(source / "capability_lattice_latest.json")
        vectorization = self._read_json(source / "crystal_lattice_vectorization_latest.json")
        training = self._read_json(source / "crystal_lora_lattice_training_latest.json")
        matrix_path = Path(str(training.get("weights_path") or source / "crystal_lora_lattice_weights_latest.npz"))
        vector_path = Path(str(vectorization.get("npz_path") or source / "crystal_lattice_vectors_latest.npz"))
        artifacts = {
            "capability_lattice_hash": str(lattice.get("lattice_hash") or ""),
            "vector_lattice_hash": str(vectorization.get("vector_lattice_hash") or ""),
            "matrix_training_hash": _sha256_payload(training) if training else "",
            "matrix_file_hash": _sha256_file(matrix_path) if matrix_path.is_file() else "",
            "vector_file_hash": _sha256_file(vector_path) if vector_path.is_file() else "",
        }
        payload = {
            "beast_object_type": "crystal_lattice_checkpoint_payload",
            "version": "1.0",
            "event_type": event_type,
            "created_at": _utc_now(),
            "source_root": str(source),
            "signal_count": int(lattice.get("signal_count") or training.get("row_count") or 0),
            "task_family_count": len(lattice.get("nodes") or []),
            "dimension": int(training.get("dimension") or vectorization.get("dimension") or 0),
            "rank": int(training.get("rank") or 0),
            "matrix_shapes": training.get("matrix_shapes") or {},
            "training_accuracy": training.get("training_accuracy"),
            "artifacts": artifacts,
            "authority": "append_only_lattice_metadata_checkpoint",
        }
        return self.append(payload)

    def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        checkpoints = self.checkpoints()
        verification = self.verify()
        if not verification.valid:
            raise ValueError("crystal lattice ledger verification failed before append")
        index = len(checkpoints)
        previous_hash = checkpoints[-1]["checkpoint_hash"] if checkpoints else self.GENESIS_PREVIOUS_HASH
        safe_payload = json.loads(_canonical(payload).decode("utf-8"))
        header = {
            "index": index,
            "previous_hash": previous_hash,
            "payload_hash": _sha256_payload(safe_payload),
            "timestamp": _utc_now(),
        }
        checkpoint = {
            "beast_object_type": "crystal_lattice_checkpoint",
            "version": "1.0",
            **header,
            "checkpoint_hash": _sha256_payload(header),
            "payload": safe_payload,
        }
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")) + "\n")
        return checkpoint

    def checkpoints(self) -> List[Dict[str, Any]]:
        if not self.ledger_path.is_file():
            return []
        rows = []
        for line_number, line in enumerate(self.ledger_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                rows.append({"_parse_error": str(exc), "_line": line_number})
        return rows

    def verify(self) -> LatticeLedgerVerification:
        rows = self.checkpoints()
        errors: List[Dict[str, Any]] = []
        previous = self.GENESIS_PREVIOUS_HASH
        for expected_index, row in enumerate(rows):
            if "_parse_error" in row:
                errors.append({"index": expected_index, "reason": "invalid_json"})
                continue
            header = {key: row.get(key) for key in ("index", "previous_hash", "payload_hash", "timestamp")}
            checks = {
                "index": row.get("index") == expected_index,
                "previous_hash": row.get("previous_hash") == previous,
                "payload_hash": row.get("payload_hash") == _sha256_payload(row.get("payload") or {}),
                "checkpoint_hash": row.get("checkpoint_hash") == _sha256_payload(header),
            }
            for name, passed in checks.items():
                if not passed:
                    errors.append({"index": expected_index, "reason": f"{name}_mismatch"})
            previous = str(row.get("checkpoint_hash") or previous)
        return LatticeLedgerVerification(not errors, len(rows), previous if rows else self.GENESIS_PREVIOUS_HASH, errors)

    def defrag(self) -> Dict[str, Any]:
        """Create a compact latest-head index without rewriting checkpoint history."""
        verification = self.verify()
        checkpoints = [item for item in self.checkpoints() if "_parse_error" not in item]
        latest_by_lattice: Dict[str, Dict[str, Any]] = {}
        for checkpoint in checkpoints:
            payload = checkpoint.get("payload") or {}
            artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
            key = str(artifacts.get("capability_lattice_hash") or checkpoint.get("checkpoint_hash"))
            latest_by_lattice[key] = {
                "checkpoint_hash": checkpoint.get("checkpoint_hash"),
                "index": checkpoint.get("index"),
                "matrix_file_hash": artifacts.get("matrix_file_hash"),
                "vector_file_hash": artifacts.get("vector_file_hash"),
                "dimension": payload.get("dimension"),
                "rank": payload.get("rank"),
                "training_accuracy": payload.get("training_accuracy"),
            }
        snapshot_core = {
            "checkpoint_count": len(checkpoints),
            "ledger_head_hash": verification.head_hash,
            "latest_by_lattice": latest_by_lattice,
        }
        snapshot = {
            "beast_object_type": "crystal_lattice_defrag_snapshot",
            "version": "1.0",
            "created_at": _utc_now(),
            "valid": verification.valid,
            **snapshot_core,
            "snapshot_hash": _sha256_payload(snapshot_core),
            "claim_boundary": "defrag_snapshot_indexes_latest_heads_only_no_history_rewrite",
        }
        self.defrag_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        return snapshot

    def state(self) -> Dict[str, Any]:
        verification = self.verify()
        defrag = self._read_json(self.defrag_path)
        return {
            "beast_object_type": "crystal_lattice_ledger_state",
            "version": "1.0",
            "root": str(self.root),
            "ledger_path": str(self.ledger_path),
            "verification": verification.to_dict(),
            "latest_defrag": defrag,
        }

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
