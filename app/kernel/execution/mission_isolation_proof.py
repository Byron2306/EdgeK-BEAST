"""Aggregate proof receipt for a destructive held-out mission capsule."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from app.kernel.execution.cgroup_capsule import CgroupAuthorization, CgroupMissionCapsule
from app.kernel.execution.race_free_cgroup_launcher import (
    NativeCgroupLauncherCompiler, RaceFreeCgroupLauncher, RaceFreeLaunchAuthorization,
)
from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class MissionIsolationProof:
    mission_id: str
    cgroup_path: str
    limits_requested: Mapping[str, str]
    limits_observed: Mapping[str, str]
    controllers: tuple[str, ...]
    pressure: Mapping[str, str]
    resource_stats: Mapping[str, Mapping[str, int]]
    initial_events: Mapping[str, int]
    final_events: Mapping[str, int]
    namespace_receipt_digest: str
    freeze_observed: bool
    clone3_supported: bool
    placement_boundary: str
    fault_receipts: Mapping[str, Mapping[str, Any]]
    descendant_containment: bool
    descriptor_cleanup: bool
    timeout_observed: bool
    oom_observed: bool
    bus_peer_death_observed: bool
    rollback_observed: bool
    populated_zero_observed: bool
    no_orphans: bool
    cleanup_confirmed: bool
    full_isolation_proven: bool
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_digest", None); return value

    def sealed(self) -> "MissionIsolationProof":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("mission isolation proof is tampered")
        complete = bool(
            self.clone3_supported and self.placement_boundary == "clone3_into_cgroup"
            and self.namespace_receipt_digest and self.freeze_observed and self.descendant_containment
            and self.descriptor_cleanup and self.timeout_observed and self.oom_observed
            and self.bus_peer_death_observed and self.rollback_observed
            and self.populated_zero_observed and self.no_orphans
            and {"cpu", "memory", "pids", "io"} <= set(self.controllers)
            and {"cpu", "memory", "io"} <= set(self.pressure)
            and self.cleanup_confirmed
        )
        if self.full_isolation_proven != complete:
            raise ValueError("complete mission isolation claim is missing physical evidence")


class MissionIsolationProofRunner:
    """Runs reviewed native negative cases inside an already delegated capsule."""

    MODES = {"timeout": 1, "oom": 2, "bus_peer_death": 3, "rollback": 4, "descendant": 5}

    def __init__(self, capsule: CgroupMissionCapsule, launcher: Path, build_root: Path):
        self.capsule = capsule
        self.launcher = Path(launcher)
        self.build_root = Path(build_root)

    def run(self, *, limits: Mapping[str, str]) -> MissionIsolationProof:
        mission = self.capsule.mission_id
        configured = self.capsule.configure_resources(dict(limits), self._auth("configure"))
        initial = self.capsule.events()
        pressure = self.capsule.pressure()
        compiler = NativeCgroupLauncherCompiler()
        runner = RaceFreeCgroupLauncher(self.launcher)
        isolated_worker = compiler.compile_worker(self.build_root / "isolated-worker")
        isolated = runner.launch(
            mission, self.capsule.path, isolated_worker,
            RaceFreeLaunchAuthorization(
                mission, str(self.capsule.path), runner._digest(isolated_worker), "mission-proof-runner",
                f"approval:{mission}:namespaces", "namespace and isolated service-registry fixture",
            ), timeout_seconds=8,
        )
        if not isolated.combined_cgroup_namespace_proven or not isolated.filesystem_secret_isolation_proven:
            raise RuntimeError("combined namespace, network, and secret isolation was not proven")
        freeze = self.capsule.freeze(True, self._auth("freeze"))
        thaw = self.capsule.freeze(False, self._auth("thaw"))
        freeze_observed = bool(freeze["confirmed"] and thaw["confirmed"])
        faults: dict[str, Mapping[str, Any]] = {}
        for name, mode in self.MODES.items():
            worker = compiler.compile_fault_worker(self.build_root / f"worker-{name}", mode)
            authority = RaceFreeLaunchAuthorization(
                mission, str(self.capsule.path), runner._digest(worker), "mission-proof-runner",
                f"approval:{mission}:{name}", f"held-out {name} negative case",
            )
            receipt = runner.launch(mission, self.capsule.path, worker, authority, timeout_seconds=8)
            faults[name] = {
                "receipt_digest": receipt.receipt_digest,
                "exit_code": receipt.child_exit_code,
                "worker_evidence": receipt.worker_evidence,
                "member_gone": not Path(f"/proc/{receipt.child_pid}").exists(),
            }
        final = self.capsule.events()
        memory_events = self._numeric_file("memory.events")
        stats = {name: self._numeric_file(name) for name in ("cpu.stat", "memory.events", "pids.events") if (self.capsule.path / name).exists()}
        if (self.capsule.path / "io.stat").exists():
            stats["io.stat"] = {"rows": len((self.capsule.path / "io.stat").read_text(encoding="utf-8").splitlines())}
        orphan = self.capsule.orphan_state(())
        empty = self.capsule.empty()
        controllers = tuple(
            name for name, control in (("cpu", "cpu.max"), ("memory", "memory.max"),
                                       ("pids", "pids.max"), ("io", "io.max"))
            if (self.capsule.path / control).exists()
        )
        # Cleanup is allowed only after all kernel state has been captured.
        cleanup = self.capsule.cleanup(self._auth("cleanup")) if empty else {"confirmed": False}
        claims = dict(
            descendant_containment=self._fault_ok(faults, "descendant"),
            descriptor_cleanup=all(bool(item["member_gone"]) for item in faults.values()),
            timeout_observed=int(faults["timeout"]["exit_code"]) == 128 + 14,
            oom_observed=int(faults["oom"]["exit_code"]) in {137, 128 + 9} and int(memory_events.get("oom_kill", 0)) > 0,
            bus_peer_death_observed=self._fault_ok(faults, "bus_peer_death"),
            rollback_observed=self._fault_ok(faults, "rollback"),
            populated_zero_observed=empty,
            no_orphans=orphan["orphaned"] is False and not orphan["members"],
            cleanup_confirmed=bool(cleanup.get("confirmed")),
        )
        full = bool(
            freeze_observed and {"cpu", "memory", "pids", "io"} <= set(controllers)
            and {"cpu", "memory", "io"} <= set(pressure) and all(claims.values())
        )
        proof = MissionIsolationProof(
            mission, str(self.capsule.path), dict(limits), configured["details"]["observed_limits"],
            controllers,
            pressure, stats, initial, final, isolated.receipt_digest, freeze_observed, True, "clone3_into_cgroup", faults,
            **claims, full_isolation_proven=full,
        ).sealed()
        proof.validate()
        return proof

    def _numeric_file(self, name: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in (self.capsule.path / name).read_text(encoding="utf-8").splitlines():
            key, _, raw = row.partition(" ")
            try: result[key] = int(raw)
            except ValueError: pass
        return result

    @staticmethod
    def _fault_ok(faults: Mapping[str, Mapping[str, Any]], name: str) -> bool:
        value = faults[name]
        return bool(value["worker_evidence"].get("verified") is True and int(value["exit_code"]) == 0)

    def _auth(self, action: str) -> CgroupAuthorization:
        return CgroupAuthorization(action, self.capsule.mission_id, "mission-proof-runner", f"approval:{action}", "bounded held-out proof")
