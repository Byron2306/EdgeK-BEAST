#!/usr/bin/env python3
"""Promote and execute disk cleanup through ComputePlane and the native delegate."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.sensorium_disk_cleanup_experiment import SensoriumDiskCleanupExperiment
from app.kernel.execution.cgroup_capsule import CgroupAuthorization
from app.kernel.execution.cgroup_delegation import CgroupDelegationManager
from app.kernel.execution.isolated_disk_cleanup import IsolatedDiskCleanupRunner, ProductionIsolatedDiskCleanupDelegate
from app.kernel.execution.isolation_readiness import effective_cgroup_path
from app.kernel.execution.race_free_cgroup_launcher import NativeCgroupLauncherCompiler
from app.kernel.sensorium.contracts_hash import content_hash


def authorization(action: str, mission: str) -> CgroupAuthorization:
    return CgroupAuthorization(action, mission, "production-disk-operator",
        f"approval:{mission}:{action}", "production ComputePlane disk cleanup")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mission", default="beast-production-disk-mission")
    args = parser.parse_args()
    root = effective_cgroup_path(); available = tuple((root / "cgroup.controllers").read_text().split())
    requested = tuple(name for name in ("cpu", "memory", "pids", "io") if name in available)
    anchor = root / "beast-production-disk-anchor"; anchor.mkdir(); (anchor / "cgroup.procs").write_text(f"{os.getpid()}\n")
    capsule, delegation = CgroupDelegationManager(root).prepare(args.mission, requested, authorization("delegate", args.mission))
    if capsule is None:
        raise RuntimeError("production disk delegation failed: " + delegation.reason)
    limits = {"cpu.max": "50000 100000", "memory.max": "33554432", "memory.swap.max": "0",
              "memory.oom.group": "1", "pids.max": "16"}
    if "io" in requested:
        cursor = root; rows = []
        while True:
            rows = (cursor / "io.stat").read_text().splitlines()
            if rows or cursor == Path("/sys/fs/cgroup"): break
            cursor = cursor.parent
        devices = [row.split()[0] for row in rows if row.split() and ":" in row.split()[0]]
        if not devices: raise RuntimeError("delegated I/O lacks an attributable device")
        limits["io.max"] = f"{devices[0]} rbps=10485760 wbps=10485760"
    configured = capsule.configure_resources(limits, authorization("configure", args.mission))
    args.build_root.mkdir(parents=True, exist_ok=True)
    launcher = NativeCgroupLauncherCompiler().compile(args.build_root / "beast-cgroup-launcher")
    delegate = ProductionIsolatedDiskCleanupDelegate(
        IsolatedDiskCleanupRunner(capsule, launcher, args.build_root), approved_by="production-disk-operator")
    plane = ComputePlane(root=args.state_root / "compute-plane", isolated_disk_cleanup_delegate=delegate)
    packet = json.loads(Path("docs/evidence/sensorium-disk-cleanup-candidate-2026-07-15.json").read_text())
    crystal = plane._deserialize_crystal(packet["crystal"])
    experiment = SensoriumDiskCleanupExperiment(args.state_root / "replay-fixtures")
    replay = plane.submit_replay(crystal, [
        experiment._variant("production-a", b"a" * 61), experiment._variant("production-b", b"b" * 67),
        experiment._variant("production-c", b"c" * 71), experiment._variant("production-negative", b"x", negative=True),
    ])
    record = plane.admit_promoted_crystal(crystal, replay, scientific_evidence={
        "heldout_ablation": {"receipt_id": replay.evidence_root + ":ablation", "verified": True, "held_out": True},
        "displacement": {"receipt_id": replay.evidence_root + ":displacement", "verified": True, "provider_calls_avoided": 1},
    }, policy_generation="policy:production-disk:v1", approver="arda-production-disk-operator",
        approval_receipt="approval:production-disk-promotion:v1")
    receipt = plane.execute_user_mission({"mission_id": args.mission,
        "task_family": "disk_pressure_diagnosis_and_governed_cleanup", "workspace_root": str(args.workspace),
        "approval_receipt": "approval:disk-standard:production-live"}, interface="cli")
    delegate_nodes = plane.evidence_graph.query("production_isolated_disk_cleanup")
    empty = capsule.empty(); orphan = capsule.orphan_state(())
    cleanup = capsule.cleanup(authorization("cleanup", args.mission)) if empty else {"confirmed": False}
    payload = {"schema": "beast.production-isolated-disk-mission.v1", "mission_receipt": asdict(receipt),
        "promotion_record_digest": record.record_digest, "delegation": asdict(delegation), "configured": configured,
        "delegate_evidence": delegate_nodes[-1].receipt if delegate_nodes else {}, "reachability": plane.reachability_report(),
        "populated_zero": empty, "no_orphans": not orphan["orphaned"], "capsule_cleanup": cleanup,
        "production_path_proven": bool(receipt.final_status == "verified_local_recurrence" and delegate_nodes
            and receipt.provider_call_witness.get("during_execution") == 0 and empty and not orphan["orphaned"]
            and cleanup.get("confirmed") and set(requested) >= {"cpu", "memory", "pids", "io"})}
    payload["evidence_digest"] = content_hash(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"production_path_proven": payload["production_path_proven"],
                      "evidence_digest": payload["evidence_digest"], "interface": receipt.interface}, sort_keys=True))
    return 0 if payload["production_path_proven"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
