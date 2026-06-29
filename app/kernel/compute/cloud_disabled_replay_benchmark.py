"""Cloud-disabled replay benchmark for BEAST crystallized compute."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.kernel.compute.crystal_autopromotion_daemon import CrystalAutopromotionDaemon
from app.kernel.compute.crystallized_compute_proof import (
    CodeRepairCloudExecutor,
    CrystallizedCodeRepairMegaGauntlet,
    CrystallizedOpusNIMGatewayMegaGauntlet,
)
from app.kernel.compute.unified_evidence_packet import stable_packet_hash


class CloudDisabledReplayBenchmark:
    """Run a closed-loop local replay proof with cloud disabled."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        task_runs = self._run_tasks()
        daemon = CrystalAutopromotionDaemon(self.root)
        daemon_receipt = daemon.run_once([Path(item["artifact_path"]) for item in task_runs])
        negative_cases = [case for item in task_runs for case in item.get("negative_cases", [])]
        blocked = sum(1 for item in negative_cases if item.get("blocked") is True)
        task_count = len(task_runs)
        local_successes = sum(1 for item in task_runs if item.get("gauntlet_passed"))
        verified_successes = sum(1 for item in task_runs if item.get("verified"))
        initial_cloud_calls = sum(int(item.get("initial_cloud_calls") or 0) for item in task_runs)
        completion_cloud_calls = sum(int(item.get("completion_cloud_calls") or 0) for item in task_runs)
        receipt = {
            "beast_object_type": "cloud_disabled_replay_benchmark",
            "version": "2.0",
            "cloud_disabled": True,
            "task_count": task_count,
            "tasks": task_runs,
            "initial_cloud_calls": initial_cloud_calls,
            "autopromoted_crystals": daemon_receipt.get("promoted_count"),
            "external_teacher_calls_after_promotion": completion_cloud_calls,
            "local_completion_rate": round(local_successes / task_count, 4),
            "verified_success_rate": round(verified_successes / task_count, 4),
            "blocked_unsafe_reuse": blocked,
            "negative_case_count": len(negative_cases),
            "unsafe_reuse_block_rate": round(blocked / max(1, len(negative_cases)), 4),
            "runtime_engine": task_runs[0].get("runtime_engine") if task_runs else "",
            "teacher_engine": task_runs[0].get("teacher_engine") if task_runs else "",
            "route_optimizer_choice": task_runs[0].get("route_optimizer_choice") if task_runs else "",
            "unified_packet_hashes": [item.get("unified_packet_hash") for item in task_runs],
            "unified_packet_hash": task_runs[0].get("unified_packet_hash") if task_runs else "",
            "daemon_receipt_hash": daemon_receipt.get("receipt_hash"),
            "artifact_paths": {
                "gauntlets": [item["artifact_path"] for item in task_runs],
                "unified_evidence_packets": [item["unified_packet_path"] for item in task_runs],
                "autopromotion": str(self.root / "crystal_autopromotion_daemon_run.json"),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt["receipt_hash"] = stable_packet_hash(receipt)
        (self.root / "cloud_disabled_replay_benchmark.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return receipt

    def _run_tasks(self) -> List[Dict[str, Any]]:
        specs = [
            (
                "opus_nim_gateway",
                self.root / "opus_local_only",
                lambda root: CrystallizedOpusNIMGatewayMegaGauntlet(root, local_only=True).run(),
                "crystallized_opus_nim_gateway_mega_gauntlet.json",
            ),
            (
                "bounded_code_repair",
                self.root / "code_repair_local_only",
                self._run_local_code_repair,
                "crystallized_code_repair_mega_gauntlet.json",
            ),
        ]
        runs = []
        for task_name, root, runner, artifact_name in specs:
            gauntlet = runner(root)
            proof = gauntlet["crystallized_compute_proof"]
            verification = gauntlet.get("skill_verification") or {}
            runs.append({
                "task_name": task_name,
                "artifact_path": str(root / artifact_name),
                "unified_packet_path": str(root / "unified_evidence_packet.json"),
                "unified_packet_hash": gauntlet.get("unified_evidence_packet", {}).get("packet_hash"),
                "gauntlet_passed": bool(gauntlet.get("gauntlet_passed")),
                "verified": bool(verification.get("tests_passed") or verification.get("tests_passed") is True),
                "initial_cloud_calls": int(proof.get("training_cloud_calls") or 0),
                "completion_cloud_calls": int(proof.get("completion", {}).get("cloud_calls_during_completion") or 0),
                "runtime_engine": proof.get("execution_lineage", {}).get("runtime_engine"),
                "teacher_engine": proof.get("execution_lineage", {}).get("teacher_engine"),
                "route_optimizer_choice": proof.get("route_optimizer_choice"),
                "negative_cases": list(gauntlet.get("negative_cases") or []),
                "bridge_receipt_hash": gauntlet.get("crystal_evidence_bridge_receipt", {}).get("residue_seal", {}).get("message_sha256"),
            })
        return runs

    @staticmethod
    def _run_local_code_repair(root: Path) -> Dict[str, Any]:
        gauntlet = CrystallizedCodeRepairMegaGauntlet(root, cloud_executor=LocalCodeRepairExecutor())
        gauntlet.config.cloud_used_for_training = False
        return gauntlet.run()


class LocalCodeRepairExecutor(CodeRepairCloudExecutor):
    """Use the code-repair teacher recipe without counting it as cloud."""

    counts_as_cloud = False
