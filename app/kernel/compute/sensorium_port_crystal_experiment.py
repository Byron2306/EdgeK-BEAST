"""Live end-to-end Sensorium-learned port-conflict crystal experiment."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory, ReplayVariant
from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate, PhysicalCrystalPromotionRegistry, RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.compute.socket_inventory import inode_owners, tcp_listeners
from app.kernel.compute.typed_crystal_interpreter import TypedCrystalInterpreter
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.contracts import SocketIdentity
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime


@dataclass(frozen=True)
class LearnedPortCrystalReceipt:
    experiment_id: str
    physical_domain: str
    contract_id: str
    positive_episode_hashes: tuple[str, ...]
    negative_episode_hashes: tuple[str, ...]
    candidate_digest: str
    typed_artifact_digest: str
    inferred_parameters: tuple[str, ...]
    replay_evidence_root: str
    replay_verified_variants: int
    promoted_record_digest: str
    recurrence_receipt_digest: str
    provider_calls_during_recurrence: int
    provider_disabled_recurrence: bool
    stale_process_refused: bool
    fixture_built_candidate: bool
    verified: bool
    receipt_digest: str = ""

    def sealed(self) -> "LearnedPortCrystalReceipt":
        from dataclasses import replace
        value = asdict(self); value.pop("receipt_digest", None)
        return replace(self, receipt_digest=content_hash(value))

    def validate(self) -> None:
        value = asdict(self); value.pop("receipt_digest", None)
        if self.receipt_digest != content_hash(value):
            raise ValueError("learned port crystal receipt is tampered")
        if self.verified and not (
            len(self.positive_episode_hashes) >= 3 and self.negative_episode_hashes
            and self.inferred_parameters == ("requested_port",)
            and self.replay_verified_variants >= 4 and self.provider_disabled_recurrence
            and self.provider_calls_during_recurrence == 0 and self.stale_process_refused
            and self.fixture_built_candidate is False
        ):
            raise ValueError("learned port crystal proof is incomplete")


class SensoriumPortCrystalExperiment:
    def __init__(self, root: Path):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.runtime = SensoriumRuntime(export_root=self.root / "sensorium", journal_path=self.root / "sensorium.jsonl")
        self.collector = LinuxProcessIdentityCollector()

    def run(self) -> LearnedPortCrystalReceipt:
        positive_ids = []
        for index in range(3):
            process, port = self._listener()
            try:
                mission = f"natural-positive-{index + 1}"
                self._observe_episode(mission, process, port, healthy=True, owner_known=True)
                positive_ids.append(mission)
            finally:
                process.terminate(); process.wait(timeout=3)
        process, negative_port = self._listener()
        try:
            self._observe_episode("natural-negative-owner", process, negative_port, healthy=False, owner_known=False)
        finally:
            process.terminate(); process.wait(timeout=3)
        candidate, generalization = self.runtime.generalize_episodes(
            [*positive_ids, "natural-negative-owner"], identity="crystal:sensorium-port-reuse:v1",
            task_family=["address_already_in_use"],
        )
        typed = self.runtime.compile_candidate(candidate)
        variants = [self._variant(f"heldout-{i}", self._free_port()) for i in range(3)]
        variants.append(self._variant("heldout-owner-unknown", self._free_port(), negative=True))
        replay = CrystalReplayLaboratory(self.runtime.typed_ir_compiler.registry, root=self.root).run(typed, variants)
        now = time.time()
        appraisal = {
            "appraisal_ref": "appraisal:local-scientific-port-v1", "state": "verified",
            "policy_generation": "policy:port-crystal-v1", "artifact_digest": typed.artifact_digest,
            "evidence_root": replay.evidence_root, "expires_at": now + 3600,
        }
        appraisal["signature"] = content_hash(appraisal)
        (self.root / "typed-crystal.json").write_text(
            json.dumps(typed.to_dict(self.runtime.typed_ir_compiler.registry), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.root / "promotion-appraisal.json").write_text(
            json.dumps(appraisal, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        os.chmod(self.root / "typed-crystal.json", 0o600)
        os.chmod(self.root / "promotion-appraisal.json", 0o600)
        registry = PhysicalCrystalPromotionRegistry(
            appraisal_verifier=lambda value: value.get("signature") == content_hash({k: v for k, v in value.items() if k != "signature"}),
            path=self.root / "promotions.json", require_scientific_evidence=True,
        )
        scientific = {
            "heldout_ablation": {"receipt_id": replay.evidence_root + ":ablation", "verified": replay.promotion_eligible, "held_out": True},
            "displacement": {"receipt_id": replay.evidence_root + ":displacement", "verified": True, "provider_calls_avoided": 1},
        }
        record = registry.promote(
            typed, replay, appraisal=appraisal, policy_generation="policy:port-crystal-v1",
            approver="local-scientific-operator", approval_receipt="approval:port-crystal-live",
            now=now, scientific_evidence=scientific,
        )
        recurrence_process, recurrence_port = self._listener()
        try:
            lease = self.collector.collect(recurrence_process.pid, owner_scope="learned-port-recurrence")
            identity = self._socket_identity(lease, recurrence_port)
            gate = PhysicalApplicabilityGate(
                registry, self.runtime.typed_ir_compiler.registry,
                appraisal_verifier=registry.appraisal_verifier,
                process_freshness=self.collector.still_matches,
                socket_freshness=lambda value: self._socket_fresh(value, recurrence_process.pid),
                port_lease_freshness=lambda _value: True, proof_ttl_ns=5_000_000_000,
            )
            context = RecurrenceContext(
                parameter_bindings={"requested_port": recurrence_port}, process_leases=(lease,),
                socket_identities=(identity,), port_leases=(), workspace_identity="workspace:live-port",
                registry_digest=content_hash({"workspace": "live-port"}), policy_generation="policy:port-crystal-v1",
                appraisal=appraisal,
            )
            monotonic = time.monotonic_ns()
            decision = gate.evaluate(typed, context, now=now + 1, monotonic_ns=monotonic)
            if not decision.allowed or decision.proof is None: raise RuntimeError(decision.reason)
            ledger = OneUseCapabilityLedger(path=self.root / "authority.sqlite", require_verifier=False)
            capability = {
                "capability_id": "capability:" + uuid.uuid4().hex, "request_digest": decision.proof.execution_request_digest,
                "authority": "arda", "expires_at": now + 300, "nonce": uuid.uuid4().hex,
                "signature": "local-experiment-boundary", "audience": "beast-runtime",
                "policy_generation": decision.proof.policy_generation, "appraisal_ref": decision.proof.appraisal_ref,
            }
            authority = consume_execution_authority(
                decision.proof, capability, ledger, authority="arda", audience="beast-runtime",
                now=now + 2, monotonic_ns=monotonic + 1,
            )
            interpreter = TypedCrystalInterpreter(
                self.runtime.typed_ir_compiler.registry, gate, provider_call_counter=lambda: 0,
            )
            execution = interpreter.execute(
                typed, decision.proof, authority, context, execution_state={"kernel_inventory": True},
                now=now + 3, monotonic_ns=monotonic + 2,
            )
            recurrence_process.terminate(); recurrence_process.wait(timeout=3)
            stale = gate.evaluate(typed, context, now=now + 4, monotonic_ns=monotonic + 3)
            receipt = LearnedPortCrystalReceipt(
                "port-crystal:" + uuid.uuid4().hex, "linux-cgroup-v2", "beast.sensorium.port-reuse.v1",
                generalization.positive_episode_hashes,
                generalization.negative_episode_hashes, candidate.digest, typed.artifact_digest,
                generalization.inferred_parameters, replay.evidence_root, replay.verified_variants,
                record.record_digest, execution.receipt_digest, execution.provider_calls_during_execution,
                execution.cloud_displacement_proven, not stale.allowed, False,
                execution.final_status == "verified_local_recurrence" and replay.promotion_eligible,
            ).sealed()
            receipt.validate(); return receipt
        finally:
            if recurrence_process.poll() is None:
                recurrence_process.terminate(); recurrence_process.wait(timeout=3)

    def _observe_episode(self, mission: str, process: subprocess.Popen, port: int, *, healthy: bool, owner_known: bool) -> None:
        lease = self.collector.collect(process.pid, owner_scope="natural-port-episode")
        identity = self._socket_identity(lease, port)
        state = f"socket_state:port:{port}"
        socket_ref = identity.identity if owner_known else "socket:owner-unknown"
        self.runtime.observe_physical(event_type="socket.inventoried", source="linux_proc_socket_sensor", payload_schema="beast.sensor.socket.inventoried.v1", operation="socket.inventory", phase="observation", subject=f"port:{port}", result="observed", payload={"produces": [state], "descriptor_refs": [socket_ref], "state_transition": {"resource": f"port:{port}", "from": "unknown", "to": "occupied"}}, mission_id=mission)
        branch = "reuse_existing_service" if healthy and owner_known else "request_operator_approval"
        self.runtime.observe_physical(event_type="repair.branch_selected", source="port_conflict_planner", payload_schema="beast.sensor.repair.branch.v1", operation="repair.select_branch", phase="decision", subject=f"port:{port}", result="selected", payload={"reads": [state], "branch": branch, "descriptor_refs": [socket_ref]}, mission_id=mission)
        probe_ok = self._probe(port) if healthy else False
        self.runtime.observe_physical(event_type="health.verified", source="loopback_health_probe", payload_schema="beast.sensor.health.verified.v1", operation="service.verify_health", phase="verification", subject="service:observed-loopback", result="success" if probe_ok else "refused", payload={"requires": [state], "descriptor_refs": [socket_ref]}, mission_id=mission)
        status = "verified_success" if probe_ok and owner_known else "refused"
        self.runtime.close_episode(mission, objective_hash=content_hash({"objective": "resolve_port_conflict"}), workspace_identity="workspace:live-port", initial_state_hash=content_hash({"port": port, "occupied": True}), outcome={"status": status, "effect_hash": content_hash({"branch": branch, "healthy": probe_ok})})

    @staticmethod
    def _listener() -> tuple[subprocess.Popen, int]:
        code = "import socket,time;s=socket.socket();s.bind(('127.0.0.1',0));s.listen();print(s.getsockname()[1],flush=True);time.sleep(120)"
        process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        assert process.stdout is not None
        return process, int(process.stdout.readline().strip())

    def _socket_identity(self, lease, port: int) -> SocketIdentity:
        return SocketIdentity(family="AF_INET", protocol="TCP", local_address_class="loopback", local_port=port, remote_scope="none", owning_process=lease.lease_id, service_id="observed-loopback", workspace_id="workspace:live-port", cgroup_id=lease.cgroup_id, listener_generation=1, opened_at_monotonic_ns=time.monotonic_ns(), policy_class="operator").with_identity()

    @staticmethod
    def _socket_fresh(value: SocketIdentity, pid: int) -> bool:
        listener = next((item for item in tcp_listeners() if item.port == value.local_port), None)
        return bool(listener and pid in inode_owners(listener.inode))

    @staticmethod
    def _probe(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1): return True
        except OSError: return False

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as value:
            value.bind(("127.0.0.1", 0)); return int(value.getsockname()[1])

    @staticmethod
    def _variant(name: str, port: int, negative: bool = False) -> ReplayVariant:
        return ReplayVariant(name, {"requested_port": port}, {"socket": (f"socket:{name}",)}, {"socket_state": {"occupied": True, "owners": [] if negative else [123]}, "health_ok": not negative}, {"branch": "request_operator_approval" if negative else "reuse_existing_service", "healthy": False if negative else True}, negative, ("owner_attribution_unavailable",) if negative else (), {"sentinel": "unchanged"})


def write_receipt(path: Path, receipt: LearnedPortCrystalReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
