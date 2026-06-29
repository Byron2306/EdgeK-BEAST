"""Daemon-style autopromotion loop for crystallized compute evidence."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.compute.crystal_promotion_evidence_sources import CrystalPromotionEvidenceSources
from app.kernel.compute.unified_evidence_packet import UnifiedEvidencePacketBuilder, stable_packet_hash


@dataclass
class AutopromotionPolicy:
    min_training_observations: int = 3
    min_confidence: float = 0.80
    require_local_completion: bool = True
    require_zero_completion_cloud_calls: bool = True
    require_memory_sidecar: bool = True
    require_negative_cases: bool = True
    min_source_evidence_score: float = 0.0


class CrystalAutopromotionDaemon:
    """Promote verified repeated compute episodes from receipts into packets.

    This is intentionally synchronous and deterministic. A production daemon can
    call the same `run_once` method on a timer.
    """

    def __init__(self, root: Path, *, policy: Optional[AutopromotionPolicy] = None) -> None:
        self.root = Path(root)
        self.policy = policy or AutopromotionPolicy()
        self.packet_dir = self.root / "autopromotion_packets"
        self.packet_dir.mkdir(parents=True, exist_ok=True)

    def run_once(self, receipt_paths: Optional[Iterable[Path]] = None) -> Dict[str, Any]:
        paths = list(receipt_paths) if receipt_paths is not None else self._discover_receipts()
        promoted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        for path in paths:
            loaded = self._load_receipt(Path(path))
            if not loaded:
                rejected.append({"path": str(path), "reason": "unreadable_or_not_json"})
                continue
            proof = loaded.get("crystallized_compute_proof") if isinstance(loaded.get("crystallized_compute_proof"), dict) else loaded
            packet = loaded.get("unified_evidence_packet")
            if not isinstance(packet, dict):
                packet = UnifiedEvidencePacketBuilder.from_proof(proof, gauntlet=loaded, artifact_path=Path(path))
            source_evidence = self._source_evidence(packet, loaded)
            if source_evidence:
                packet = dict(packet)
                packet["promotion_evidence_sources"] = source_evidence
            gate = self._promotion_gate(packet)
            if gate["promotable"]:
                packet_path = self.packet_dir / f"{packet['packet_hash'].removeprefix('sha256:')}.json"
                UnifiedEvidencePacketBuilder.write(packet, packet_path)
                promoted.append({
                    "path": str(path),
                    "packet_path": str(packet_path),
                    "packet_hash": packet["packet_hash"],
                    "task_class": packet.get("task_class"),
                    "runtime_engine": (packet.get("runtime") or {}).get("engine"),
                    "teacher_engine": (packet.get("teacher") or {}).get("engine"),
                    "source_evidence_score": (source_evidence or {}).get("score"),
                })
            else:
                rejected.append({"path": str(path), "reason": gate["reason"], "gate": gate})
        receipt = {
            "beast_object_type": "crystal_autopromotion_daemon_run",
            "version": "1.0",
            "root": str(self.root),
            "scanned": len(paths),
            "promoted_count": len(promoted),
            "rejected_count": len(rejected),
            "promoted": promoted,
            "rejected": rejected,
            "policy": self.policy.__dict__,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt["receipt_hash"] = stable_packet_hash(receipt)
        (self.root / "crystal_autopromotion_daemon_run.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return receipt

    def run_loop(
        self,
        *,
        receipt_paths: Optional[Iterable[Path]] = None,
        interval_seconds: float = 60.0,
        max_cycles: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run autopromotion repeatedly.

        `max_cycles` keeps tests and supervised service invocations bounded. A
        production wrapper can pass `None` and manage process lifecycle outside
        this deterministic loop.
        """

        cycles: List[Dict[str, Any]] = []
        cycle = 0
        while max_cycles is None or cycle < max_cycles:
            cycle += 1
            run = self.run_once(receipt_paths)
            cycles.append({
                "cycle": cycle,
                "receipt_hash": run.get("receipt_hash"),
                "scanned": run.get("scanned"),
                "promoted_count": run.get("promoted_count"),
                "rejected_count": run.get("rejected_count"),
                "created_at": run.get("created_at"),
            })
            self._write_service_state(cycles, running=max_cycles is None or cycle < max_cycles)
            if max_cycles is not None and cycle >= max_cycles:
                break
            time.sleep(max(0.0, float(interval_seconds)))
        state = {
            "beast_object_type": "crystal_autopromotion_daemon_service_run",
            "version": "1.0",
            "root": str(self.root),
            "cycle_count": len(cycles),
            "cycles": cycles,
            "bounded": max_cycles is not None,
            "interval_seconds": float(interval_seconds),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        state["receipt_hash"] = stable_packet_hash(state)
        (self.root / "crystal_autopromotion_daemon_service_run.json").write_text(
            json.dumps(state, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        self._write_service_state(cycles, running=False)
        return state

    def _write_service_state(self, cycles: List[Dict[str, Any]], *, running: bool) -> None:
        state = {
            "beast_object_type": "crystal_autopromotion_daemon_service_state",
            "version": "1.0",
            "running": bool(running),
            "root": str(self.root),
            "cycle_count": len(cycles),
            "last_cycle": cycles[-1] if cycles else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        state["state_hash"] = stable_packet_hash(state)
        (self.root / "crystal_autopromotion_daemon_service_state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    def _discover_receipts(self) -> List[Path]:
        names = {
            "crystallized_opus_nim_gateway_mega_gauntlet.json",
            "crystallized_code_repair_mega_gauntlet.json",
            "crystallized_compute_proof.json",
        }
        return sorted(path for path in self.root.rglob("*.json") if path.name in names)

    @staticmethod
    def _load_receipt(path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _promotion_gate(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        teacher = packet.get("teacher") if isinstance(packet.get("teacher"), dict) else {}
        runtime = packet.get("runtime") if isinstance(packet.get("runtime"), dict) else {}
        semantic_credit = packet.get("semantic_credit") if isinstance(packet.get("semantic_credit"), dict) else {}
        memory = packet.get("memory_hull") if isinstance(packet.get("memory_hull"), dict) else {}
        replay = packet.get("replay") if isinstance(packet.get("replay"), dict) else {}
        negative_cases = packet.get("negative_cases") if isinstance(packet.get("negative_cases"), list) else []
        source_evidence = packet.get("promotion_evidence_sources") if isinstance(packet.get("promotion_evidence_sources"), dict) else {}
        observations = int(teacher.get("training_observations") or 0)
        confidence = float(semantic_credit.get("confidence") or 0.0)
        completion_cloud_calls = int(replay.get("cloud_calls_during_completion") or 0)
        residue = ((memory.get("sections") or {}).get("residue") or {}) if isinstance(memory.get("sections"), dict) else {}

        failures = []
        if observations < self.policy.min_training_observations:
            failures.append("insufficient_training_observations")
        if confidence < self.policy.min_confidence:
            failures.append("confidence_below_policy")
        if self.policy.require_local_completion and replay.get("completed_locally") is not True:
            failures.append("completion_not_local")
        if self.policy.require_zero_completion_cloud_calls and completion_cloud_calls != 0:
            failures.append("completion_used_cloud")
        if self.policy.require_memory_sidecar and int(residue.get("sidecars") or 0) < 1:
            failures.append("missing_memory_hull_sidecar")
        if self.policy.require_negative_cases and negative_cases and not all(item.get("blocked") is True for item in negative_cases):
            failures.append("negative_case_not_blocked")
        if float(source_evidence.get("score") or 0.0) < self.policy.min_source_evidence_score:
            failures.append("source_evidence_score_below_policy")
        return {
            "promotable": not failures,
            "reason": "ok" if not failures else ",".join(failures),
            "observations": observations,
            "confidence": confidence,
            "completion_cloud_calls": completion_cloud_calls,
            "residue_sidecars": int(residue.get("sidecars") or 0),
            "negative_cases": len(negative_cases),
            "source_evidence_score": float(source_evidence.get("score") or 0.0),
        }

    @staticmethod
    def _source_evidence(packet: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        receipts = loaded.get("promotion_source_receipts")
        if not isinstance(receipts, dict):
            receipts = loaded.get("beast_evidence_sources")
        if not isinstance(receipts, dict):
            receipts = {}
        if not receipts and not any(packet.get(key) for key in ("tools", "skills", "route_optimizer", "forge")):
            return {}
        return CrystalPromotionEvidenceSources().from_packet_and_receipts(packet, receipts)
