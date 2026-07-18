"""Learn and replay the bounded disk-pressure cleanup domain."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory, ReplayVariant
from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest, execute_cleanup
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime


class SensoriumDiskCleanupExperiment:
    TASK_FAMILY = "disk_pressure_diagnosis_and_governed_cleanup"

    def __init__(self, root: Path):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.runtime = SensoriumRuntime(export_root=self.root / "outbox", journal_path=self.root / "sensorium.jsonl")

    @staticmethod
    def _policy(*, cache_root: str = "cache/build", max_bytes: int = 8192) -> bytes:
        return (json.dumps({"version": "beast.disk-cleanup.v1", "cache_roots": [cache_root],
            "min_age_seconds": 0, "max_files": 8, "max_bytes": max_bytes,
            "approval_threshold_bytes": 4096}, sort_keys=True) + "\n").encode()

    def _episode(self, index: int, *, negative: bool = False) -> Any:
        mission = f"disk-{'negative' if negative else 'positive'}-{index}"
        workspace_id = f"disk-natural-{index}"
        workspace = self.root / "natural" / workspace_id; workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "cleanup-policy.json").write_bytes(self._policy(cache_root=".git/objects" if negative else "cache/build"))
        cache = workspace / "cache/build"; cache.mkdir(parents=True, exist_ok=True)
        (cache / f"stale-{index}.bin").write_bytes(bytes([65 + index]) * (31 + index))
        approval = f"approval:disk-standard:natural-{index}"
        approval_digest = content_hash(approval)
        try:
            manifest, observation = build_cleanup_manifest(workspace)
            effect = execute_cleanup(workspace, manifest, approval_receipt=approval)
            manifest_digest, branch, result = manifest.manifest_digest, "quarantine_and_purge", "success"
        except (ValueError, PermissionError):
            manifest_digest, branch, result = content_hash({"refused": mission}), "request_operator_approval", "refused"
            observation, effect = {"selected_files": 0}, {"verified": False, "refused": True}
        descriptor = f"workspace:{workspace_id}"
        common = {"mission_id": mission, "workspace_id": descriptor}
        self.runtime.observe_physical(event_type="disk.pressure_inspected", source="beast_disk_pressure_adapter",
            payload_schema="beast.sensor.disk-pressure.v1", operation="disk.inspect_pressure", phase="observation",
            subject=descriptor, result="success" if not negative else "refused",
            payload={"reads":[f"cleanup_manifest:{manifest_digest}","disk_state"],"produces":["pressure_state"],"descriptor_refs":[descriptor]}, **common)
        self.runtime.observe_physical(event_type="disk.cleanup_planned", source="beast_disk_cleanup_planner",
            payload_schema="beast.sensor.disk-cleanup-plan.v1", operation="disk.plan_cleanup", phase="decision",
            subject=descriptor, result="success" if not negative else "refused",
            payload={"requires":["pressure_state"],"produces":["cleanup_plan"],"descriptor_refs":[descriptor],"branch":branch}, **common)
        self.runtime.observe_physical(event_type="disk.cleanup_executed", source="beast_disk_cleanup_actuator",
            payload_schema="beast.sensor.disk-cleanup-effect.v1", operation="disk.quarantine_cleanup", phase="actuation",
            subject=descriptor, result=result,
            payload={"requires":["cleanup_plan",f"approval:{approval_digest}"],"writes":["cache_state"],"descriptor_refs":[descriptor],"branch":branch,
                     "state_transition":{"resource":"cache_state","from":"pressured","to":"clean" if not negative else "unchanged"}}, **common)
        self.runtime.observe_physical(event_type="disk.cleanup_verified", source="beast_disk_cleanup_verifier",
            payload_schema="beast.sensor.disk-cleanup-verify.v1", operation="disk.verify_cleanup", phase="verification",
            subject=descriptor, result=result,
            payload={"requires":["cache_state"],"descriptor_refs":[descriptor],"branch":branch}, **common)
        return self.runtime.close_episode(mission, objective_hash=content_hash({"objective":self.TASK_FAMILY}),
            workspace_identity=descriptor, initial_state_hash=content_hash({"files":1,"bytes":31+index}),
            outcome={"status":"refused" if negative else "verified_success","effect_hash":content_hash(effect)},
            resources={"bytes_selected":float(observation.get("selected_bytes") or 0)})

    def _variant(self, name: str, payload: bytes, *, negative: bool = False, empty: bool = False) -> ReplayVariant:
        approval = f"approval:disk-standard:{name}"
        files = {"cleanup-policy.json": self._policy()}
        if not empty:
            files[f"cache/build/{name}.bin"] = payload
        return ReplayVariant(name, {"workspace_identity": name,
            "cleanup_manifest_digest": "sha256:" + "0" * 64 if negative else "AUTO",
            "approval_receipt_digest": content_hash(approval)}, {"workspace":(f"workspace:{name}",)},
            {"workspace_files":files,"cleanup_approval_receipt":approval},
            {"branch":"request_operator_approval" if negative or empty else "quarantine_and_purge"},
            negative or empty, ("stale_or_empty_manifest",) if negative or empty else (), {"sentinel":"unchanged"})

    def run(self) -> dict[str, Any]:
        positives = [self._episode(index) for index in range(3)]
        negatives = [self._episode(10 + index, negative=True) for index in range(2)]
        mission_ids = [item.mission_id for item in (*positives, *negatives)]
        candidate, generalization = self.runtime.generalize_episodes(mission_ids,
            identity="crystal:sensorium-disk-cleanup:v1", task_family=[self.TASK_FAMILY])
        crystal = self.runtime.compile_candidate(candidate, capability_lease="capability-template:disk-cleanup:v1")
        replay_root = self.root / "replay"; replay_root.mkdir(exist_ok=True)
        replay = CrystalReplayLaboratory(self.runtime.typed_ir_compiler.registry, root=replay_root).run(crystal, [
            self._variant("delta", b"d" * 127), self._variant("epsilon", b"e" * 511),
            self._variant("zeta", b"z" * 1023), self._variant("wrong-manifest", b"w" * 41, negative=True),
            self._variant("empty-cache", b"", empty=True),
        ])
        isolation = {"private_disposable_workspaces": all(row.isolation.get("filesystem") == "private_temporary_directory" for row in replay.variant_receipts),
                     "cgroup_capsule_established": all(row.isolation.get("cgroup_capsule_established") is True for row in replay.variant_receipts),
                     "namespace_isolation_established": all(row.isolation.get("process_namespace") != "not_established" for row in replay.variant_receipts)}
        packet = {"schema":"beast.sensorium.disk-cleanup-evidence.v1","experiment_id":"disk-cleanup:"+uuid.uuid4().hex,
            "claim":"learned_bounded_disk_cleanup_candidate","generalization":generalization.to_dict(),
            "crystal":crystal.to_dict(self.runtime.typed_ir_compiler.registry),"replay":asdict(replay),
            "safety":{"protected_parts":[".git",".beast",".ssh","secrets","credentials","source"],
                      "manifest_identity_fields":["device","inode","size","mtime_ns","sha256"],
                      "approval_thresholds":True,"quarantine_before_purge":True},
            "isolation":isolation,"promotion_eligible_by_replay":replay.promotion_eligible,
            "production_promotion_allowed":bool(replay.promotion_eligible and isolation["cgroup_capsule_established"] and isolation["namespace_isolation_established"]),
            "promotion_blocker":"destructive replay worker not yet born inside delegated cgroup+namespace capsule"}
        packet["evidence_digest"] = content_hash(packet)
        return packet


def write_packet(path: Path, packet: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(packet, indent=2, sort_keys=True)+"\n"); os.chmod(path,0o600)
