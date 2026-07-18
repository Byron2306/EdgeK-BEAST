"""Deterministic daemon for grading public benchmark packets.

This daemon is intentionally synchronous and deterministic. It watches a public
benchmark packet directory, derives provisional grades from objective verifier
outcomes, and emits a provisional verdict plus service-state receipts.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmarks import public_economic_thesis_harness as harness


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


@dataclass
class DeterministicGradingPolicy:
    require_blind_packet: bool = True
    require_cost_accounting: bool = True
    require_key: bool = True


class PublicBenchmarkGradingDaemon:
    """Generate deterministic provisional grades and verdicts for a packet dir."""

    def __init__(self, packet_dir: str | Path, *, policy: Optional[DeterministicGradingPolicy] = None) -> None:
        self.packet_dir = Path(packet_dir).expanduser().resolve()
        self.policy = policy or DeterministicGradingPolicy()
        self.packet_dir.mkdir(parents=True, exist_ok=True)

    def run_once(self) -> Dict[str, Any]:
        readiness = self._readiness_gate()
        created_at = _utc_now()
        if not readiness["ready"]:
            receipt = {
                "beast_object_type": "public_benchmark_grading_daemon_run",
                "version": "1.0",
                "packet_dir": str(self.packet_dir),
                "ready": False,
                "policy": self.policy.__dict__,
                "reason": readiness["reason"],
                "created_at": created_at,
            }
            receipt["receipt_hash"] = _stable_hash(receipt)
            self._write_json("grading_daemon_run.json", receipt)
            self._write_service_state(running=False, last_run=receipt)
            return receipt

        provisional_info = harness.write_provisional_grades_from_verification(self.packet_dir)
        verdict = harness.build_verdict(self.packet_dir, [provisional_info["path"]])
        verdict["claim_status_basis"] = "provisional_verification_grades"
        verdict["rationale"] = (
            verdict["rationale"]
            + " This verdict is preliminary because passes_task was seeded from objective verification outcomes rather than independent blind human grading."
        )
        verdict_info = harness.write_verdict(self.packet_dir, verdict, basename="provisional_verdict")
        structural_info = harness.write_structural_grades(self.packet_dir)
        structural_verdict = harness.build_verdict(self.packet_dir, [structural_info["path"]])
        structural_verdict["claim_status_basis"] = "deterministic_structure_grade"
        structural_verdict["rationale"] = (
            structural_verdict["rationale"]
            + " This verdict is based on deterministic scoring of patch structure, verification planning, and observed verifier outcomes."
        )
        structural_verdict_info = harness.write_verdict(self.packet_dir, structural_verdict, basename="structural_verdict")
        blind_rows = harness.load_jsonl(self.packet_dir / "blind_grading.jsonl")
        receipt = {
            "beast_object_type": "public_benchmark_grading_daemon_run",
            "version": "1.0",
            "packet_dir": str(self.packet_dir),
            "ready": True,
            "policy": self.policy.__dict__,
            "blind_row_count": len(blind_rows),
            "provisional_grades_path": provisional_info["path"],
            "provisional_grade_count": provisional_info["count"],
            "verdict_path": verdict_info["path"],
            "verdict_summary_path": verdict_info["summary_path"],
            "claim_status": verdict.get("claim_status"),
            "structural_grades_path": structural_info["path"],
            "structural_grade_count": structural_info["count"],
            "structural_verdict_path": structural_verdict_info["path"],
            "structural_verdict_summary_path": structural_verdict_info["summary_path"],
            "structural_claim_status": structural_verdict.get("claim_status"),
            "created_at": created_at,
        }
        receipt["receipt_hash"] = _stable_hash(receipt)
        self._write_json("grading_daemon_run.json", receipt)
        self._write_service_state(running=False, last_run=receipt)
        return receipt

    def run_loop(self, *, interval_seconds: float = 60.0, max_cycles: Optional[int] = None) -> Dict[str, Any]:
        cycles: List[Dict[str, Any]] = []
        cycle = 0
        while max_cycles is None or cycle < max_cycles:
            cycle += 1
            run = self.run_once()
            cycles.append({
                "cycle": cycle,
                "claim_status": run.get("claim_status"),
                "ready": run.get("ready"),
                "receipt_hash": run.get("receipt_hash"),
                "created_at": run.get("created_at"),
            })
            self._write_service_state(running=max_cycles is None or cycle < max_cycles, last_run=run, cycles=cycles)
            if max_cycles is not None and cycle >= max_cycles:
                break
            time.sleep(max(0.0, float(interval_seconds)))
        state = {
            "beast_object_type": "public_benchmark_grading_daemon_service_run",
            "version": "1.0",
            "packet_dir": str(self.packet_dir),
            "cycle_count": len(cycles),
            "cycles": cycles,
            "bounded": max_cycles is not None,
            "interval_seconds": float(interval_seconds),
            "created_at": _utc_now(),
        }
        state["receipt_hash"] = _stable_hash(state)
        self._write_json("grading_daemon_service_run.json", state)
        self._write_service_state(running=False, last_run=cycles[-1] if cycles else {}, cycles=cycles)
        return state

    def _readiness_gate(self) -> Dict[str, Any]:
        required = []
        if self.policy.require_blind_packet:
            required.append(self.packet_dir / "blind_grading.jsonl")
        if self.policy.require_cost_accounting:
            required.append(self.packet_dir / "cost_accounting.json")
        if self.policy.require_key:
            required.append(self.packet_dir / "blind_grading_key.json")
        missing = [str(path.name) for path in required if not path.exists()]
        return {
            "ready": not missing,
            "reason": "ok" if not missing else "missing:" + ",".join(missing),
        }

    def _write_service_state(self, *, running: bool, last_run: Dict[str, Any], cycles: Optional[List[Dict[str, Any]]] = None) -> None:
        state = {
            "beast_object_type": "public_benchmark_grading_daemon_service_state",
            "version": "1.0",
            "packet_dir": str(self.packet_dir),
            "running": bool(running),
            "cycle_count": len(cycles or []),
            "last_run": last_run,
            "updated_at": _utc_now(),
        }
        state["state_hash"] = _stable_hash(state)
        self._write_json("grading_daemon_service_state.json", state)

    def _write_json(self, name: str, payload: Dict[str, Any]) -> None:
        path = self.packet_dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
