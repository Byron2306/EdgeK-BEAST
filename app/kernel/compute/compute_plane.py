"""Production composition root for governed BEAST computation.

Every online compute lane is owned here.  Importable experimental modules are
not thereby online: the reachability report names them explicitly.
"""
from __future__ import annotations

import os
import base64
import json
import threading
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.displacement_economics import DisplacementEconomics, PairedOccurrence
from app.kernel.compute.distributed_forge_scheduler import DistributedForgeScheduler
from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest
from app.kernel.compute.forge_supervisor import ForgeSupervisor
from app.kernel.compute.evidence_job_supervisor import EvidenceJobSupervisor
from app.kernel.compute.module_dispositions import disposition_report, OFFLINE_LIBRARY, SUPERVISED_EVIDENCE
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate, PhysicalCrystalPromotionRegistry, RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory, ReplayLaboratoryReceipt
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR, TypedCrystalNode
from app.kernel.compute.streaming_interceptor import StreamingComputeInterceptor, StreamingInterceptionEngine
from app.kernel.compute.typed_crystal_interpreter import TypedCrystalInterpreter
from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.sensorium.runtime import SensoriumRuntime
from app.kernel.execution.mission_isolation_proof import MissionIsolationProofRunner
from app.kernel.integration.one_use_capability import OneUseCapability, OneUseCapabilityLedger
from app.kernel.integration.signed_decision import signed_appraisal_body
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.storage.outcome_evidence import default_outcome_store


@dataclass
class PlaneAttempt:
    attempt_id: str
    lane: str
    provider: str
    started_at: float
    phases: list[str] = field(default_factory=list)
    gate_id: str = ""
    receipt_id: str = ""
    status: str = "active"


@dataclass(frozen=True)
class ProductionMissionReceipt:
    mission_id: str
    interface: str
    task_family: str
    crystal_id: str
    crystal_digest: str
    promotion_record_digest: str
    applicability_proof_digest: str
    appraisal_ref: str
    capability_id: str
    authorization_receipt_digest: str
    capsule_receipt_id: str
    execution_receipt_digest: str
    evidence_node_id: str
    displacement_evidence_node_id: str
    episode_hash: str
    final_status: str
    provider_calls_avoided: int
    execution_latency_ms: float = 0.0
    node_receipt_digests: tuple[str, ...] = ()
    provider_call_witness: Mapping[str, int] = field(default_factory=dict)
    response_digest: str = ""

    def sealed(self) -> "ProductionMissionReceipt":
        from dataclasses import replace
        value = asdict(self); value.pop("response_digest", None)
        return replace(self, response_digest=content_hash(value))

    def validate(self) -> None:
        value = asdict(self); value.pop("response_digest", None)
        if self.response_digest != content_hash(value):
            raise ValueError("production mission receipt is tampered")
        if self.final_status != "verified_local_recurrence" or not all((
            self.crystal_id, self.applicability_proof_digest, self.appraisal_ref,
            self.capability_id, self.capsule_receipt_id, self.execution_receipt_digest,
            self.evidence_node_id, self.displacement_evidence_node_id, self.episode_hash,
        )):
            raise ValueError("production mission lifecycle is incomplete")
        if self.execution_latency_ms < 0 or len(self.node_receipt_digests) < 3:
            raise ValueError("production mission runtime witnesses are incomplete")
        if int(self.provider_call_witness.get("during_execution", -1)) != 0:
            raise ValueError("local recurrence provider witness is invalid")


@dataclass(frozen=True)
class ProviderFallbackReceipt:
    mission_id: str
    interface: str
    task_family: str
    fallback_reason: str
    provider: str
    execution_latency_ms: float
    provider_call_witness: Mapping[str, int]
    evidence_node_id: str
    final_status: str
    response: Mapping[str, Any]
    response_digest: str = ""

    def sealed(self) -> "ProviderFallbackReceipt":
        from dataclasses import replace
        value = asdict(self); value.pop("response_digest", None)
        return replace(self, response_digest=content_hash(value))


@dataclass(frozen=True)
class DelegatedPhysicalExecutionReceipt:
    final_status: str
    receipt_digest: str
    provider_calls_during_execution: int
    delegate_receipt: Mapping[str, Any]


class ScientificPromotionGate:
    """Reject promotion unless independent efficacy and displacement exist."""

    REQUIRED = ("heldout_ablation", "displacement")

    @classmethod
    def require(cls, evidence: Mapping[str, Any]) -> dict[str, str]:
        bound: dict[str, str] = {}
        for kind in cls.REQUIRED:
            receipt = evidence.get(kind)
            if not isinstance(receipt, Mapping):
                raise PermissionError(f"promotion requires {kind} receipt")
            receipt_id = str(receipt.get("receipt_id") or receipt.get("receipt_hash") or "")
            if not receipt_id or receipt.get("verified") is not True:
                raise PermissionError(f"promotion requires verified {kind} receipt")
            if kind == "heldout_ablation" and receipt.get("held_out") is not True:
                raise PermissionError("ablation evidence must be held out")
            if kind == "displacement" and int(receipt.get("provider_calls_avoided") or 0) < 1:
                raise PermissionError("displacement must measure avoided provider calls")
            bound[kind] = receipt_id
        if len(set(bound.values())) != len(bound):
            raise PermissionError("promotion receipts must be independently identified")
        return bound


class ComputePlane:
    """One observable owner for authorization, execution and proof."""

    REQUIRED_COMPONENTS = (
        "governor", "inference_interceptor", "streaming_interceptor",
        "forge_scheduler", "forge_supervisor", "isolation_verifier", "physical_registry",
        "physical_interpreter", "evidence_graph", "sensorium",
        "promotion_gate",
        "mission_isolation_runner_type",
        "evidence_job_supervisor",
        "episode_generalizer", "crystal_compiler", "replay_laboratory",
        "capability_ledger", "capsule_admission", "promoted_artifacts",
        "displacement_economics",
        "production_routing_mode",
        "isolated_disk_cleanup_delegate",
    )
    OFFLINE_ONLY_MODULES = tuple(sorted(SUPERVISED_EVIDENCE | OFFLINE_LIBRARY))

    def __init__(self, *, root: Path | None = None, governor: ComputeGovernor | None = None,
                 provider_fallback: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                 production_routing_mode: str = "explicit_enforce",
                 isolated_disk_cleanup_delegate: Callable[..., Mapping[str, Any]] | None = None):
        if root is None:
            configured = os.environ.get("BEAST_COMPUTE_PLANE_ROOT", "").strip()
            state_root = os.environ.get("BEAST_STATE_ROOT", "").strip()
            xdg_state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
            root = Path(configured).expanduser() if configured else (
                Path(state_root).expanduser() / "compute_plane" if state_root
                else xdg_state / "beast" / "compute_plane"
            )
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.governor = governor or ComputeGovernor()
        if production_routing_mode not in {"explicit_enforce", "disabled"}:
            raise ValueError("production routing mode must be explicit_enforce or disabled")
        self.production_routing_mode = production_routing_mode
        self.isolated_disk_cleanup_delegate = (
            isolated_disk_cleanup_delegate or self._unconfigured_disk_cleanup_delegate
        )
        self.ledger = ComputeLedger(str(self.root / "compute_ledger.db"))
        self.inference_interceptor = InferenceComputeInterceptor(
            governor=self.governor, ledger=self.ledger, outcome_store=default_outcome_store()
        )
        self.streaming_interceptor = StreamingComputeInterceptor(governor=self.governor)
        self.isolation_verifier = self._verify_isolation
        self.forge_scheduler = DistributedForgeScheduler(
            self.root / "forge_scheduler", strict_isolation=True,
            node_admission_verifier=self.isolation_verifier,
        )
        self.forge_supervisor = ForgeSupervisor(isolation_verifier=self.isolation_verifier)
        self.evidence_graph = ControlEvidenceGraph(self.root / "evidence.jsonl")
        self.sensorium = SensoriumRuntime(
            export_root=self.root / "sensorium_outbox", journal_path=self.root / "sensorium.jsonl"
        )
        opcode_registry = self.sensorium.typed_ir_compiler.registry
        self.episode_generalizer = self.sensorium.generalizer
        self.crystal_compiler = self.sensorium.typed_ir_compiler
        replay_root = self.root / "replay_lab"; replay_root.mkdir(parents=True, exist_ok=True)
        self.replay_laboratory = CrystalReplayLaboratory(opcode_registry, root=replay_root)
        self._appraisal_signer, self._appraisal_verifier = self._load_or_create_runtime_authority()
        self.capability_ledger = OneUseCapabilityLedger(
            verifier={"arda": self._appraisal_verifier}, path=self.root / "one_use_authority.sqlite",
        )
        self.capsule_admission = self._admit_capsule
        self.physical_registry = PhysicalCrystalPromotionRegistry(
            appraisal_verifier=self._verify_appraisal, path=self.root / "physical_registry.json", require_scientific_evidence=True
        )
        self.physical_applicability = PhysicalApplicabilityGate(
            self.physical_registry, opcode_registry, appraisal_verifier=self._verify_appraisal,
            process_freshness=lambda value: bool(value.lease_id),
            socket_freshness=lambda value: bool(value.identity),
            port_lease_freshness=lambda value: bool(value.get("lease_id")),
            proof_ttl_ns=5_000_000_000,
        )
        self.physical_interpreter = TypedCrystalInterpreter(
            opcode_registry, self.physical_applicability, evidence=self.evidence_graph,
            provider_call_counter=lambda: self._counters["provider.execute"],
        )
        self.promotion_gate = ScientificPromotionGate()
        self.displacement_economics = DisplacementEconomics()
        self.mission_isolation_runner_type = MissionIsolationProofRunner
        self.evidence_job_supervisor = EvidenceJobSupervisor()
        self._attempts: dict[str, PlaneAttempt] = {}
        self._interception_attempts: dict[int, str] = {}
        self._counters: Counter[str] = Counter()
        self._last_receipts: dict[str, str] = {}
        self._bypasses: Counter[str] = Counter()
        self._lock = threading.RLock()
        self.provider_fallback = provider_fallback
        self.promoted_artifacts: dict[str, ExecutableCrystalIR] = {}
        self._appraisals: dict[str, dict[str, Any]] = {}
        self._load_promoted_artifacts()
        self.assert_production_composition()

    def _load_or_create_runtime_authority(self) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
        key_path = self.root / "authority" / "arda-runtime-ed25519.pem"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            signer = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            if not isinstance(signer, Ed25519PrivateKey):
                raise RuntimeError("runtime appraisal key has the wrong type")
        else:
            signer = Ed25519PrivateKey.generate()
            temporary = key_path.with_suffix(".tmp")
            temporary.write_bytes(signer.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            os.chmod(temporary, 0o600); os.replace(temporary, key_path)
        return signer, signer.public_key()

    def _verify_appraisal(self, value: Mapping[str, Any]) -> bool:
        try:
            binding = {"artifact_digest": value["artifact_digest"], "evidence_root": value["evidence_root"],
                       "policy_generation": value["policy_generation"]}
            if value["evidence_digest"] != content_hash(binding) or value["request_digest"] != content_hash(binding):
                return False
            self._appraisal_verifier.verify(base64.b64decode(str(value["signature"]), validate=True), signed_appraisal_body(value))
            return True
        except Exception:
            return False

    def _issue_appraisal(self, crystal: ExecutableCrystalIR, replay: ReplayLaboratoryReceipt,
                         policy_generation: str, now: float) -> dict[str, Any]:
        binding = {"artifact_digest": crystal.artifact_digest, "evidence_root": replay.evidence_root,
                   "policy_generation": policy_generation}
        evidence_digest = content_hash(binding)
        value: dict[str, Any] = {
            "appraisal_ref": "arda:production:" + evidence_digest.removeprefix("sha256:"),
            "authority": "arda", "audience": "beast-physical-crystal", "state": "verified",
            "expires_at": now + 86400 * 30, "request_digest": content_hash(binding),
            "nonce": uuid.uuid4().hex, "key_id": "arda-production-runtime-v1",
            "evidence_digest": evidence_digest, **binding,
        }
        value["signature"] = base64.b64encode(self._appraisal_signer.sign(signed_appraisal_body(value))).decode()
        return value

    def admit_promoted_crystal(self, crystal: ExecutableCrystalIR, replay: ReplayLaboratoryReceipt, *,
                               scientific_evidence: Mapping[str, Any], policy_generation: str,
                               approver: str, approval_receipt: str) -> Any:
        """Production admission boundary used by operators, never by recurrence callers."""
        crystal.validate(self.crystal_compiler.registry)
        self.promotion_gate.require(scientific_evidence)
        now = time.time()
        appraisal = self._issue_appraisal(crystal, replay, policy_generation, now)
        record = self.physical_registry.promote(
            crystal, replay, appraisal=appraisal, policy_generation=policy_generation,
            approver=approver, approval_receipt=approval_receipt, now=now,
            scientific_evidence=scientific_evidence,
        )
        self.promoted_artifacts[crystal.identity] = crystal
        self._appraisals[crystal.identity] = appraisal
        self._persist_promoted_artifact(crystal, appraisal)
        node = self.evidence_graph.add("production_crystal_admission", {
            "crystal_id": crystal.identity, "artifact_digest": crystal.artifact_digest,
            "replay_evidence_root": replay.evidence_root, "promotion_record_digest": record.record_digest,
            "appraisal_ref": record.appraisal_ref, "approval_receipt": approval_receipt,
        })
        self._last_receipts["promotion"] = node.node_id
        self._counters["promotion.complete"] += 1
        return record

    def submit_replay(self, crystal: ExecutableCrystalIR, variants: list[Any]) -> ReplayLaboratoryReceipt:
        self._counters["replay.submit"] += 1
        receipt = self.replay_laboratory.run(crystal, variants)
        self._last_receipts["replay"] = receipt.evidence_root
        return receipt

    def admit_displacement_economics(self, crystal_id: str, occurrences: list[PairedOccurrence], **costs: Any) -> dict[str, Any]:
        """Bind paired net economics to the production Control Evidence Graph."""
        if crystal_id not in self.promoted_artifacts:
            raise PermissionError("economics requires an active promoted crystal")
        self.physical_registry.require_active(crystal_id)
        receipt = self.displacement_economics.evaluate(occurrences, **costs)
        self.displacement_economics.validate(receipt)
        node = self.evidence_graph.add("verified_displacement_economics", {
            **receipt, "crystal_id": crystal_id,
        })
        feedback = self.evidence_graph.add("capability_impact_economics_feedback", {
            "crystal_id": crystal_id, **receipt["impact_feedback"],
            "routing_economics": {
                "net_positive": receipt["net_positive"],
                "break_even_occurrences_cost": receipt["break_even_occurrences_cost"],
                "break_even_occurrences_latency": receipt["break_even_occurrences_latency"],
            },
        })
        self.evidence_graph.link(node, "PRODUCES", feedback)
        result = {**receipt, "evidence_node_id": node.node_id, "feedback_node_id": feedback.node_id}
        self._last_receipts["verified_displacement_economics"] = node.node_id
        self._counters["displacement.economics.admitted"] += 1
        return result

    def ingest_sensor_event(self, **event: Any) -> Any:
        """Production-owned Sensorium ingestion boundary."""
        self._counters["sensorium.ingest"] += 1
        return self.sensorium.observe_owned(**event)

    def close_sensor_episode(self, mission_id: str, **closure: Any) -> Any:
        self._counters["sensorium.episode.close"] += 1
        return self.sensorium.close_episode(mission_id, **closure)

    def generalize_and_compile(self, mission_ids: list[str], *, identity: str,
                               task_family: list[str], capability_lease: str = "") -> tuple[Any, Any, ExecutableCrystalIR]:
        candidate, generalization = self.sensorium.generalize_episodes(
            mission_ids, identity=identity, task_family=task_family,
        )
        compiled = self.sensorium.compile_candidate(candidate, capability_lease=capability_lease)
        self._counters["crystal.generalize"] += 1; self._counters["crystal.compile"] += 1
        self._last_receipts["generalization"] = generalization.family_hash
        return candidate, generalization, compiled

    def execute_user_mission(self, payload: Mapping[str, Any], *, interface: str = "api") -> ProductionMissionReceipt | ProviderFallbackReceipt:
        """Normal product boundary for selecting and executing a promoted recurrence."""
        self.assert_production_composition()
        if interface not in {"api", "cli", "ide"}:
            raise ValueError("mission interface is not a reviewed production entry point")
        mission_id = str(payload.get("mission_id") or "mission:" + uuid.uuid4().hex)
        task_family = str(payload.get("task_family") or "")
        workspace_root = Path(str(payload.get("workspace_root") or "")).expanduser()
        if not task_family or not workspace_root.is_dir() or workspace_root.is_symlink():
            raise ValueError("mission requires a task_family and safe workspace_root")
        candidates = [item for item in self.promoted_artifacts.values() if task_family in item.task_family]
        if not candidates and payload.get("allow_provider_fallback") is True and self.provider_fallback is not None:
            return self._execute_provider_fallback(payload, mission_id=mission_id, task_family=task_family, interface=interface)
        if len(candidates) != 1:
            raise PermissionError("mission did not select exactly one eligible promoted crystal")
        if self.production_routing_mode != "explicit_enforce":
            raise PermissionError("applicable crystal routing is not explicitly enforced")
        crystal = candidates[0]
        record = self.physical_registry.require_active(crystal.identity)
        appraisal = self._appraisals.get(crystal.identity)
        if appraisal is None or not self._verify_appraisal(appraisal):
            raise PermissionError("current production appraisal is unavailable")
        workspace_identity = str(payload.get("workspace_identity") or "workspace:" + content_hash(str(workspace_root.resolve())).removeprefix("sha256:")[:24])
        parameters = dict(payload.get("parameters") or {})
        if "workspace_identity" in crystal.parameters:
            parameters["workspace_identity"] = workspace_identity.removeprefix("workspace:")
        cleanup_manifest = None
        cleanup_approval = ""
        if task_family == "disk_pressure_diagnosis_and_governed_cleanup":
            cleanup_manifest, _cleanup_observation = build_cleanup_manifest(workspace_root)
            cleanup_approval = str(payload.get("approval_receipt") or "")
            if not cleanup_approval:
                raise PermissionError("isolated disk cleanup requires an explicit approval receipt")
            parameters["cleanup_manifest_digest"] = cleanup_manifest.manifest_digest
            parameters["approval_receipt_digest"] = content_hash(cleanup_approval)
        initial_state = content_hash({"workspace_root": str(workspace_root.resolve()), "entries": sorted(p.name for p in workspace_root.iterdir())})
        self.ingest_sensor_event(event_type="mission.user_submitted", source=f"beast_{interface}_interface",
            payload_schema="beast.mission.user-submitted.v1", payload={"task_family": task_family, "workspace_identity": workspace_identity},
            mission_id=mission_id, workspace_id=workspace_identity)
        recurrence = RecurrenceContext(parameters, (), (), (), workspace_identity,
            content_hash({"workspace": workspace_identity}), record.policy_generation, appraisal,
            workspace_root=str(workspace_root.resolve()))
        decision = self.physical_applicability.evaluate(crystal, recurrence)
        if not decision.allowed or decision.proof is None:
            raise PermissionError("crystal applicability refused: " + decision.reason)
        proof = decision.proof
        capability = self.issue_execution_capability(proof)
        capability_id = str(capability["capability_id"])
        authorization = consume_execution_authority(proof, capability, self.capability_ledger,
            authority="arda", audience="beast-runtime")
        capsule = self.capsule_admission(mission_id, crystal, workspace_root)
        provider_before = int(self._counters["provider.execute"])
        execution_started = time.perf_counter_ns()
        def execute_selected() -> Any:
            if cleanup_manifest is None:
                return self.physical_interpreter.execute(
                    crystal, proof, authorization, recurrence, execution_state={}
                )
            delegated = dict(self.isolated_disk_cleanup_delegate(
                mission_id=mission_id, workspace=workspace_root, manifest=cleanup_manifest,
                approval_receipt=cleanup_approval, applicability_proof=proof,
                execution_authorization=authorization,
            ))
            if delegated.get("verified") is not True:
                raise RuntimeError("isolated disk cleanup delegate did not verify")
            required = ("receipt_digest", "launch_receipt_digest", "worker_digest", "cgroup_path")
            if any(not delegated.get(key) for key in required):
                raise RuntimeError("isolated disk cleanup delegate receipt is incomplete")
            delegate_body = dict(delegated); supplied_digest = str(delegate_body.pop("receipt_digest"))
            if supplied_digest != content_hash(delegate_body):
                raise RuntimeError("isolated disk cleanup delegate receipt is tampered")
            if (delegated.get("mission_id") != mission_id
                    or delegated.get("manifest_digest") != cleanup_manifest.manifest_digest
                    or delegated.get("targets_absent") is not True
                    or delegated.get("clone3_into_cgroup") is not True
                    or delegated.get("namespace_isolation") is not True
                    or delegated.get("filesystem_secret_isolation") is not True
                    or delegated.get("ambient_network_denied") is not True
                    or delegated.get("root_cleanup_confirmed") is not True):
                raise RuntimeError("isolated disk cleanup delegate violated production proof contract")
            return DelegatedPhysicalExecutionReceipt(
                "verified_local_recurrence", supplied_digest, 0, delegated,
            )

        execution = self.execute_operation(lane="physical_crystal", provider="local-crystal",
            authorize=lambda: capsule["admitted"],
            execute=execute_selected,
            verify=lambda value: value.final_status == "verified_local_recurrence")
        execution_latency_ms = (time.perf_counter_ns() - execution_started) / 1_000_000
        provider_after = int(self._counters["provider.execute"])
        provider_witness = {"before": provider_before, "after": provider_after,
                            "during_execution": provider_after - provider_before}
        self.ingest_sensor_event(event_type="mission.crystal_verified", source="beast_compute_plane",
            payload_schema="beast.mission.crystal-verified.v1",
            payload={"crystal_id": crystal.identity, "execution_receipt": execution.receipt_digest,
                     "capsule_receipt": capsule["receipt_id"], "provider_calls": execution.provider_calls_during_execution},
            mission_id=mission_id, workspace_id=workspace_identity)
        episode = self.close_sensor_episode(mission_id, objective_hash=content_hash({"task_family": task_family}),
            workspace_identity=workspace_identity, initial_state_hash=initial_state,
            outcome={"status": "verified_success", "effect_hash": execution.receipt_digest},
            resources={"provider_calls": float(execution.provider_calls_during_execution or 0)})
        displacement = self.evidence_graph.add("production_displacement_observation", {
            "mission_id": mission_id, "crystal_id": crystal.identity,
            "provider_calls_during_execution": execution.provider_calls_during_execution,
            "counterfactual_provider_route_calls": 1, "provider_calls_avoided": 1,
            "claim_level": "route-counter-observation/not-net-economics",
        })
        delegate_node = None
        if isinstance(execution, DelegatedPhysicalExecutionReceipt):
            delegate_node = self.evidence_graph.add("production_isolated_disk_cleanup", {
                "mission_id": mission_id, "crystal_id": crystal.identity,
                "applicability_proof_digest": proof.proof_digest,
                "authorization_receipt_digest": authorization.receipt_digest,
                **dict(execution.delegate_receipt),
            })
        mission_node = self.evidence_graph.add("production_user_mission", {
            "mission_id": mission_id, "interface": interface, "task_family": task_family,
            "routing_mode": self.production_routing_mode,
            "promotion_record_digest": record.record_digest, "applicability_proof_digest": proof.proof_digest,
            "appraisal_ref": proof.appraisal_ref, "capability_id": capability_id,
            "authorization_receipt_digest": authorization.receipt_digest,
            "capsule_receipt_id": capsule["receipt_id"], "execution_receipt_digest": execution.receipt_digest,
            "episode_hash": episode.episode_hash, "displacement_node": displacement.node_id,
            "execution_latency_ms": execution_latency_ms,
            "provider_call_witness": provider_witness,
            "delegated_isolation_node": delegate_node.node_id if delegate_node else "",
        })
        receipt = ProductionMissionReceipt(
            mission_id=mission_id, interface=interface, task_family=task_family, crystal_id=crystal.identity,
            crystal_digest=crystal.artifact_digest, promotion_record_digest=record.record_digest,
            applicability_proof_digest=proof.proof_digest, appraisal_ref=proof.appraisal_ref,
            capability_id=capability_id, authorization_receipt_digest=authorization.receipt_digest,
            capsule_receipt_id=capsule["receipt_id"], execution_receipt_digest=execution.receipt_digest,
            evidence_node_id=mission_node.node_id, displacement_evidence_node_id=displacement.node_id,
            episode_hash=episode.episode_hash, final_status=execution.final_status, provider_calls_avoided=1,
            execution_latency_ms=execution_latency_ms,
            node_receipt_digests=(capsule["receipt_id"], execution.receipt_digest, episode.episode_hash,
                                  displacement.node_id, mission_node.node_id),
            provider_call_witness=provider_witness,
        ).sealed()
        receipt.validate(); self._last_receipts["user_mission"] = receipt.response_digest
        self._counters[f"interface.{interface}.mission.complete"] += 1
        return receipt

    @staticmethod
    def _unconfigured_disk_cleanup_delegate(**_values: Any) -> Mapping[str, Any]:
        raise PermissionError("production isolated disk cleanup delegate is not configured")

    def issue_execution_capability(self, proof: Any) -> dict[str, Any]:
        """Issue a short-lived, proof-bound capability; its ledger enforces one use."""
        item = OneUseCapability("capability:" + uuid.uuid4().hex, proof.execution_request_digest,
            "arda", time.time() + 120, uuid.uuid4().hex, "", "beast-runtime",
            proof.policy_generation, proof.appraisal_ref, "arda-production-runtime-v1")
        return {**asdict(item), "signature": base64.b64encode(self._appraisal_signer.sign(item.body())).decode()}

    def _execute_provider_fallback(self, payload: Mapping[str, Any], *, mission_id: str,
                                   task_family: str, interface: str) -> ProviderFallbackReceipt:
        """Governed fallback used only when explicitly requested and configured."""
        provider = str(payload.get("fallback_provider") or "configured-provider")
        before = int(self._counters["provider.execute"])
        started = time.perf_counter_ns()
        def execute() -> Mapping[str, Any]:
            self._counters["provider.execute"] += 1
            assert self.provider_fallback is not None
            return self.provider_fallback(payload)
        result = self.execute_operation(lane="provider_fallback", provider=provider,
            authorize=lambda: payload.get("allow_provider_fallback") is True,
            execute=execute, verify=lambda value: isinstance(value, Mapping) and value.get("verified") is True)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        after = int(self._counters["provider.execute"])
        witness = {"before": before, "after": after, "during_execution": after - before}
        node = self.evidence_graph.add("production_provider_fallback", {
            "mission_id": mission_id, "task_family": task_family, "provider": provider,
            "reason": "no_eligible_promoted_crystal", "provider_call_witness": witness,
            "execution_latency_ms": elapsed, "response_digest": content_hash(result),
        })
        self._counters[f"interface.{interface}.mission.complete"] += 1
        return ProviderFallbackReceipt(mission_id, interface, task_family,
            "no_eligible_promoted_crystal", provider, elapsed, witness, node.node_id,
            "verified_provider_fallback", dict(result)).sealed()

    def _admit_capsule(self, mission_id: str, crystal: ExecutableCrystalIR, root: Path) -> dict[str, Any]:
        resolved = root.resolve()
        admitted = root.is_dir() and not root.is_symlink() and crystal.maximum_authority in {"verify_only", "bounded_execute"}
        node = self.evidence_graph.add("mission_capsule_admission", {
            "mission_id": mission_id, "crystal_id": crystal.identity, "workspace_root_digest": content_hash(str(resolved)),
            "mode": "descriptor-bound-workspace", "ambient_network": False,
            "authority": crystal.maximum_authority, "admitted": admitted,
        })
        return {"admitted": admitted, "receipt_id": node.node_id, "mode": "descriptor-bound-workspace"}

    def _persist_promoted_artifact(self, crystal: ExecutableCrystalIR, appraisal: Mapping[str, Any]) -> None:
        directory = self.root / "promoted_artifacts"; directory.mkdir(parents=True, exist_ok=True)
        payload = {"crystal": crystal.to_dict(self.crystal_compiler.registry), "appraisal": dict(appraisal)}
        target = directory / (crystal.identity.replace(":", "_") + ".json")
        temporary = target.with_suffix(".tmp"); temporary.write_text(json.dumps(payload, sort_keys=True) + "\n")
        os.chmod(temporary, 0o600); os.replace(temporary, target)

    def _load_promoted_artifacts(self) -> None:
        directory = self.root / "promoted_artifacts"
        if not directory.exists():
            return
        for path in directory.glob("*.json"):
            payload = json.loads(path.read_text())
            crystal = self._deserialize_crystal(payload["crystal"])
            crystal.validate(self.crystal_compiler.registry)
            if self.physical_registry.get(crystal.identity) is None:
                raise RuntimeError("promoted artifact has no lifecycle record")
            self.promoted_artifacts[crystal.identity] = crystal
            self._appraisals[crystal.identity] = dict(payload["appraisal"])

    @staticmethod
    def _deserialize_crystal(value: Mapping[str, Any]) -> ExecutableCrystalIR:
        fields = ExecutableCrystalIR.__dataclass_fields__
        body = {key: value[key] for key in fields if key in value}
        body["nodes"] = tuple(TypedCrystalNode(**item) for item in value["nodes"])
        for name in ("task_family", "preconditions", "postconditions", "negative_conditions", "evidence"):
            body[name] = tuple(body[name])
        body["edges"] = tuple(tuple(item) for item in body["edges"])
        return ExecutableCrystalIR(**body)

    def begin(self, ir: Any, provider: str, *, lane: str = "provider") -> Any:
        interception = self.inference_interceptor.begin(ir, provider)
        attempt = PlaneAttempt(str(uuid.uuid4()), lane, provider, time.time(), ["begin", "authorize"],
                               str(getattr(interception.gate, "gate_id", "")))
        with self._lock:
            self._attempts[attempt.attempt_id] = attempt
            self._interception_attempts[id(interception)] = attempt.attempt_id
            self._counters[f"{lane}.begin"] += 1
            self._counters[f"{lane}.authorize"] += 1
        return interception

    def complete(self, interception: Any, **kwargs: Any) -> Any:
        receipt = self.inference_interceptor.complete(interception, **kwargs)
        with self._lock:
            attempt = self._attempts[self._interception_attempts.pop(id(interception))]
            attempt.phases.extend(("execute", "verify", "complete"))
            attempt.status = str(kwargs.get("status") or "complete")
            attempt.receipt_id = str(getattr(receipt, "receipt_id", ""))
            for phase in ("execute", "verify", "complete"):
                self._counters[f"{attempt.lane}.{phase}"] += 1
            self._last_receipts[attempt.lane] = attempt.receipt_id
        return receipt

    def __getattr__(self, name: str) -> Any:
        interceptor = self.__dict__.get("inference_interceptor")
        if interceptor is not None and hasattr(interceptor, name):
            return getattr(interceptor, name)
        raise AttributeError(name)

    def streaming_for(self, *, max_tokens: int = 4096, schema: Mapping[str, Any] | None = None) -> StreamingComputeInterceptor:
        return StreamingComputeInterceptor(
            StreamingInterceptionEngine(max_output_tokens=max_tokens, schema_contract=schema),
            governor=self.governor,
        )

    @staticmethod
    def _verify_isolation(attestation: Mapping[str, Any]) -> bool:
        from app.kernel.compute.forge_isolation import ForgeIsolationAttestation, forge_work_isolation_admitted
        try:
            fields = ForgeIsolationAttestation.__dataclass_fields__
            value = ForgeIsolationAttestation(**{key: item for key, item in attestation.items() if key in fields})
            value.validate()
            return bool(
                value.attested_at > 0
                and value.attested_at <= time.time()
                and value.expires_at > time.time()
                and forge_work_isolation_admitted({"requires_isolation": True}, attestation)
            )
        except (TypeError, ValueError):
            return False

    def record_bypass(self, lane: str, reason: str) -> None:
        self._bypasses[f"{lane}:{reason}"] += 1

    def execute_operation(
        self, *, lane: str, provider: str, authorize: Callable[[], bool],
        execute: Callable[[], Any], verify: Callable[[Any], bool],
    ) -> Any:
        """Common lifecycle for non-IR lanes such as Forge workers."""
        attempt = PlaneAttempt(str(uuid.uuid4()), lane, provider, time.time(), ["begin"])
        with self._lock:
            self._attempts[attempt.attempt_id] = attempt
            self._counters[f"{lane}.begin"] += 1
        allowed = bool(authorize())
        attempt.phases.append("authorize")
        self._counters[f"{lane}.authorize"] += 1
        if not allowed:
            attempt.status = "denied"
            raise PermissionError(f"{lane} operation was not authorized")
        result = execute()
        attempt.phases.append("execute")
        self._counters[f"{lane}.execute"] += 1
        if not verify(result):
            attempt.status = "verification_failed"
            self._counters[f"{lane}.verify"] += 1
            raise RuntimeError(f"{lane} operation failed verification")
        attempt.phases.extend(("verify", "complete"))
        attempt.status = "complete"
        attempt.receipt_id = "plane:" + uuid.uuid4().hex
        self._counters[f"{lane}.verify"] += 1
        self._counters[f"{lane}.complete"] += 1
        self._last_receipts[lane] = attempt.receipt_id
        return result

    def assert_production_composition(self) -> None:
        absent = [name for name in self.REQUIRED_COMPONENTS if getattr(self, name, None) is None]
        if absent:
            raise RuntimeError("production compute enforcement absent: " + ", ".join(absent))
        if self.streaming_interceptor.governor is not self.governor:
            raise RuntimeError("streaming interceptor is not bound to the production governor")
        if self.production_routing_mode not in {"explicit_enforce", "disabled"}:
            raise RuntimeError("production routing mode was tampered")

    def reachability_report(self) -> dict[str, Any]:
        self.assert_production_composition()
        return {
            "beast_object_type": "compute_plane_reachability",
            "version": "1.0",
            "read_only": True,
            "mode": self.governor.mode,
            "production_routing_mode": self.production_routing_mode,
            "components": {name: type(getattr(self, name)).__name__ for name in self.REQUIRED_COMPONENTS},
            "call_counters": dict(sorted(self._counters.items())),
            "last_receipt_ids": dict(sorted(self._last_receipts.items())),
            "bypass_counters": dict(sorted(self._bypasses.items())),
            "offline_only_modules": list(self.OFFLINE_ONLY_MODULES),
            "module_dispositions": disposition_report(),
            "active_attempts": sum(1 for item in self._attempts.values() if item.status == "active"),
            "promoted_crystals": sorted(self.promoted_artifacts),
        }


_plane: ComputePlane | None = None
_plane_lock = threading.Lock()


def get_compute_plane() -> ComputePlane:
    global _plane
    if _plane is None:
        with _plane_lock:
            if _plane is None:
                _plane = ComputePlane()
    return _plane
