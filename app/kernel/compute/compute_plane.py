"""Production composition root for governed BEAST computation.

Every online compute lane is owned here.  Importable experimental modules are
not thereby online: the reachability report names them explicitly.
"""
from __future__ import annotations

import os
import base64
import hashlib
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
from app.kernel.compute.capability_learning import CapabilityLearningLedger
from app.kernel.compute.capability_composition import CapabilityCompositionPlane
from app.kernel.compute.cross_modal_composition import CrossModalCompositionPlane
from app.kernel.compute.proof_first_cross_modal import compile_restart_risk_proof_first
from app.kernel.compute.visual_capability_composition import VisualCapabilityCompositionPlane
from app.kernel.compute.proof_graph import (
    CanonicalProofGraph,
    ProofClaimStatus,
    ProofGraphClaim,
    TextProofView,
    VisualProofPrimitive,
    VisualProofView,
)
from app.kernel.compute.displacement_economics import DisplacementEconomics, PairedOccurrence
from app.kernel.compute.displacement_observatory import DisplacementObservatory
from app.kernel.compute.generation_provider_adapters import (
    GenerationModality,
    GenerationProviderAdapterRegistry,
    GenerationProviderRequest,
    ProviderMode,
)
from app.kernel.compute.distributed_forge_scheduler import DistributedForgeScheduler
from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest
from app.kernel.compute.forge_supervisor import ForgeSupervisor
from app.kernel.compute.evidence_job_supervisor import EvidenceJobSupervisor
from app.kernel.compute.module_dispositions import disposition_report, OFFLINE_LIBRARY, SUPERVISED_EVIDENCE
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.operator_language import MeaningResolutionState, realize_answer_frame
from app.kernel.compute.operator_language_plane import (
    OperatorLanguagePlane,
    OperatorLanguageReceipt,
    OperatorLanguageRequest,
    OperatorLanguageResponse,
)
from app.kernel.compute.residual_candidate import ResidualCandidate
from app.kernel.compute.residual_compute_governor import ResidualComputeGovernor
from app.kernel.compute.residual_compute_plane import RouteExecutionResult
from app.kernel.compute.residual_contracts import (
    ApplicabilityState,
    ResidualAuthority,
    ResidualRoute,
    VerificationState,
    sha256_digest,
    utc_now_iso,
    validate_digest,
)
from app.kernel.compute.scene_synthesis import (
    AssetKind,
    AssetRef,
    CanvasContract,
    DeterministicSceneCompositor,
    SceneCapsule,
    SceneCompositionReceipt,
    SceneCrystal,
    SceneOpcode,
    SceneOpcodeKind,
    SignedAssetManifest,
    default_beast_asset_manifest,
)
from app.kernel.compute.semantic_generalizer import (
    SemanticCrystalRecord,
    SemanticCrystalRegistry,
    SemanticEpisode,
    SemanticGeneralizer,
    SemanticReuseKey,
    normalize_utterance,
    semantic_intent_fingerprint,
)
from app.kernel.compute.visual_residuals import (
    RegionMask,
    SupervisedCPUVisualResidualWorker,
    VisualRegionFeatureEmbedding,
    VisualResidualBudget,
    VisualPromptIntent,
    VisualResidualReceipt,
    VisualResidualRequest,
    build_visual_region_feature_embedding,
    evaluate_visual_region_equivalence,
    evaluate_visual_region_perceptual,
    evaluate_visual_region_intent,
    evaluate_visual_region_quality,
    extract_visual_prompt_intent,
    verify_visual_residual_output,
    verify_visual_residual_receipt,
)
from app.kernel.compute.forge_kv_ml_kem_transport import (
    FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY,
    validate_ml_kem_bound_transport_receipt,
)
from app.kernel.networking.commons_spaces import validate_reduction_receipt
from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate, PhysicalCrystalPromotionRegistry, RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory, ReplayLaboratoryReceipt
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR, TypedCrystalNode
from app.kernel.compute.streaming_interceptor import StreamingComputeInterceptor, StreamingInterceptionEngine
from app.kernel.compute.synthesis_plane import SynthesisPlane, SynthesisReceiptStore
from app.kernel.compute.synthesis_contracts import SynthesisMode, SynthesisRequest
from app.kernel.observability.telemetry_outbox import TelemetryOutbox
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


@dataclass(frozen=True)
class SceneCapsuleRuntimeResult:
    svg: str
    composition_receipt: SceneCompositionReceipt
    capsule: SceneCapsule
    evidence_node_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "scene_capsule_result",
            "version": "1.0",
            "svg": self.svg,
            "composition_receipt": {
                **asdict(self.composition_receipt),
                "receipt_digest": self.composition_receipt.receipt_digest,
            },
            "capsule": {
                **asdict(self.capsule),
                "capsule_digest": self.capsule.capsule_digest,
            },
            "evidence_node_id": self.evidence_node_id,
        }


@dataclass(frozen=True)
class VisualResidualRuntimeResult:
    output: bytes
    request: VisualResidualRequest
    receipt: VisualResidualReceipt
    scene_capsule: SceneCapsule
    evidence_node_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "visual_residual_result",
            "version": "1.0",
            "output_base64": base64.b64encode(self.output).decode("ascii"),
            "request_digest": self.request.request_digest,
            "scene_capsule": {
                **asdict(self.scene_capsule),
                "capsule_digest": self.scene_capsule.capsule_digest,
            },
            "receipt": {
                **asdict(self.receipt),
                "receipt_digest": self.receipt.receipt_digest,
            },
            "evidence_node_id": self.evidence_node_id,
        }


@dataclass(frozen=True)
class VisualProviderFallbackReceipt:
    request_digest: str
    scene_digest: str
    scene_capsule_digest: str
    mask_digest: str
    provider: str
    fallback_reason: str
    approval_receipt_digest: str
    output_digest: str
    output_size_bytes: int
    execution_latency_ms: float
    provider_call_witness: Mapping[str, int]
    evidence_node_id: str
    verified: bool
    final_status: str
    response_digest: str = ""

    def sealed(self) -> "VisualProviderFallbackReceipt":
        from dataclasses import replace
        value = asdict(self)
        value.pop("response_digest", None)
        return replace(self, response_digest=content_hash(value))


@dataclass(frozen=True)
class VisualProviderFallbackRuntimeResult:
    output: bytes
    request: VisualResidualRequest
    receipt: VisualProviderFallbackReceipt
    scene_capsule: SceneCapsule
    evidence_node_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "visual_provider_fallback_result",
            "version": "1.0",
            "output_base64": base64.b64encode(self.output).decode("ascii"),
            "request_digest": self.request.request_digest,
            "scene_capsule": {
                **asdict(self.scene_capsule),
                "capsule_digest": self.scene_capsule.capsule_digest,
            },
            "receipt": {
                **asdict(self.receipt),
                "receipt_digest": self.receipt.response_digest,
            },
            "evidence_node_id": self.evidence_node_id,
        }


@dataclass(frozen=True)
class VisualPromotedAssetRecord:
    promotion_key: str
    asset: AssetRef
    source_path: str
    scene_capsule_digest: str
    mask_digest: str
    prompt_digest: str
    seed: int
    output_digest: str
    output_size_bytes: int
    observation_count: int
    provenance_receipts: tuple[str, ...]
    source_lanes: tuple[str, ...]
    evidence_node_id: str
    created_at: str
    quality_receipt_digest: str = ""
    intent_receipt_digest: str = ""
    perceptual_receipt_digest: str = ""
    feature_embedding_digest: str = ""
    equivalence_receipt_digest: str = ""

    @property
    def record_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "promotion_key": self.promotion_key,
            "asset": {
                **asdict(self.asset),
                "kind": self.asset.kind.value,
            },
            "source_path": self.source_path,
            "scene_capsule_digest": self.scene_capsule_digest,
            "mask_digest": self.mask_digest,
            "prompt_digest": self.prompt_digest,
            "seed": self.seed,
            "output_digest": self.output_digest,
            "output_size_bytes": self.output_size_bytes,
            "observation_count": self.observation_count,
            "provenance_receipts": list(self.provenance_receipts),
            "source_lanes": list(self.source_lanes),
            "quality_receipt_digest": self.quality_receipt_digest,
            "intent_receipt_digest": self.intent_receipt_digest,
            "perceptual_receipt_digest": self.perceptual_receipt_digest,
            "feature_embedding_digest": self.feature_embedding_digest,
            "equivalence_receipt_digest": self.equivalence_receipt_digest,
            "evidence_node_id": self.evidence_node_id,
            "created_at": self.created_at,
            "record_digest": self.record_digest,
        }


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


def _visual_treatment_for_claim_status(status: ProofClaimStatus) -> str:
    if status is ProofClaimStatus.SUPPORTED:
        return "solid_edge_with_rule_badge"
    if status is ProofClaimStatus.RESIDUAL_SUPPORTED:
        return "dashed_residual_advisory_edge"
    if status is ProofClaimStatus.UNSUPPORTED:
        return "dashed_interruption_with_explicit_unsupported_label"
    if status is ProofClaimStatus.REFUTED:
        return "blocked_or_crossed_relation"
    if status is ProofClaimStatus.STALE:
        return "clock_badge_and_faded_status"
    return "unknown_proof_state"


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
        "displacement_observatory",
        "production_routing_mode",
        "isolated_disk_cleanup_delegate",
        "synthesis_receipt_store", "synthesis_plane",
        "operator_language_plane",
        "semantic_generalizer", "semantic_crystal_registry",
        "scene_compositor", "visual_residual_worker", "promoted_visual_assets",
        "capability_learning_ledger",
        "capability_composition_plane",
        "cross_modal_composition_plane",
        "visual_capability_composition_plane",
        "generation_provider_adapters",
    )
    OFFLINE_ONLY_MODULES = tuple(sorted(SUPERVISED_EVIDENCE | OFFLINE_LIBRARY))

    def __init__(self, *, root: Path | None = None, governor: ComputeGovernor | None = None,
                 provider_fallback: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                 production_routing_mode: str = "explicit_enforce",
                 isolated_disk_cleanup_delegate: Callable[..., Mapping[str, Any]] | None = None):
        configured_root = root is not None or bool(os.environ.get("BEAST_COMPUTE_PLANE_ROOT", "").strip())
        if root is None:
            configured = os.environ.get("BEAST_COMPUTE_PLANE_ROOT", "").strip()
            state_root = os.environ.get("BEAST_STATE_ROOT", "").strip()
            xdg_state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
            root = Path(configured).expanduser() if configured else (
                Path(state_root).expanduser() / "compute_plane" if state_root
                else xdg_state / "beast" / "compute_plane"
            )
        self.root = Path(root)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            # Directory existence is not sufficient in managed sandboxes;
            # verify that the scheduler can create its lock/state files.
            probe = self.root / ".beast-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            if configured_root:
                raise
            # Some managed IDE/test sandboxes expose the user's XDG state path
            # as read-only. Keep durable compute state in the repository-owned
            # BEAST area rather than failing during import or leaving a phantom
            # scheduler-lock diagnosis behind.
            fallback = Path(__file__).resolve().parents[3] / ".beast" / "state" / "compute_plane"
            fallback.mkdir(parents=True, exist_ok=True)
            self.root = fallback
        self.governor = governor or ComputeGovernor()
        if production_routing_mode not in {"explicit_enforce", "disabled"}:
            raise ValueError("production routing mode must be explicit_enforce or disabled")
        self.production_routing_mode = production_routing_mode
        self.isolated_disk_cleanup_delegate = (
            isolated_disk_cleanup_delegate or self._unconfigured_disk_cleanup_delegate
        )
        self.ledger = ComputeLedger(str(self.root / "compute_ledger.db"))
        self.telemetry_outbox = TelemetryOutbox(self.root / "telemetry_outbox")
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
        self.synthesis_receipt_store = SynthesisReceiptStore(self.root / "synthesis_receipts.jsonl")
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
        self.displacement_observatory = DisplacementObservatory()
        self.semantic_generalizer = SemanticGeneralizer()
        self.semantic_crystal_registry = SemanticCrystalRegistry(self.root / "semantic_crystals.jsonl")
        self.capability_learning_ledger = CapabilityLearningLedger(self.root / "capability_learning.jsonl")
        self.capability_composition_plane = CapabilityCompositionPlane()
        self.cross_modal_composition_plane = CrossModalCompositionPlane()
        self.visual_capability_composition_plane = VisualCapabilityCompositionPlane()
        self.generation_provider_adapters = GenerationProviderAdapterRegistry()
        self.operator_language_plane = OperatorLanguagePlane(
            registry_path=Path(__file__).resolve().parents[3] / ".byron" / "services.yaml"
        )
        self.scene_compositor = DeterministicSceneCompositor()
        self.visual_residual_worker = SupervisedCPUVisualResidualWorker()
        self.mission_isolation_runner_type = MissionIsolationProofRunner
        self.evidence_job_supervisor = EvidenceJobSupervisor()
        self.synthesis_plane = self._build_synthesis_plane()
        self._attempts: dict[str, PlaneAttempt] = {}
        self._interception_attempts: dict[int, str] = {}
        self._counters: Counter[str] = Counter()
        self._last_receipts: dict[str, str] = {}
        self._bypasses: Counter[str] = Counter()
        self._lock = threading.RLock()
        self.provider_fallback = provider_fallback
        self.promoted_artifacts: dict[str, ExecutableCrystalIR] = {}
        self.promoted_visual_assets: dict[str, VisualPromotedAssetRecord] = {}
        self._visual_asset_observations: Counter[str] = Counter()
        self._visual_asset_observation_digests: dict[str, str] = {}
        self._visual_asset_observation_embeddings: dict[str, VisualRegionFeatureEmbedding] = {}
        self._visual_asset_observation_receipts: dict[str, list[str]] = {}
        self._visual_asset_observation_equivalence_receipts: dict[str, list[str]] = {}
        self._visual_asset_observation_lanes: dict[str, set[str]] = {}
        self._appraisals: dict[str, dict[str, Any]] = {}
        self.semantic_crystal_registry.load()
        self._load_promoted_artifacts()
        self._load_promoted_visual_assets()
        self.assert_production_composition()

    def _record_capability_learning(
        self,
        *,
        event_type: str,
        capability_type: str,
        capability_id: str,
        lifecycle_state: str,
        authority: str,
        evidence_digest: str,
        receipt_digest: str,
        provider_calls_used: int = 0,
        provider_calls_avoided: int = 0,
        fresh_work_units: int = 0,
        reuse_hits: int = 0,
        refusal_reason: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.capability_learning_ledger.record(
            event_type=event_type,
            capability_type=capability_type,
            capability_id=capability_id,
            lifecycle_state=lifecycle_state,
            authority=authority,
            evidence_digest=evidence_digest,
            receipt_digest=receipt_digest,
            provider_calls_used=int(provider_calls_used),
            provider_calls_avoided=int(provider_calls_avoided),
            fresh_work_units=int(fresh_work_units),
            reuse_hits=int(reuse_hits),
            refusal_reason=refusal_reason,
            metadata=dict(metadata or {}),
        )

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
            "observed_at": utc_now_iso(), **receipt, "crystal_id": crystal_id,
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

    def _record_synthesis_event(self, event: Mapping[str, Any]) -> str:
        node = self.evidence_graph.add("synthesis_route_completed", dict(event))
        self._last_receipts["synthesis"] = node.node_id
        self._counters["synthesis.complete"] += 1
        return node.node_id

    def _build_synthesis_plane(self) -> SynthesisPlane:
        return SynthesisPlane(
            ResidualComputeGovernor({
                "operator_language_semantic": self._operator_language_semantic_candidates,
            }),
            {
                ResidualRoute.SEMANTIC_RESULT: self._execute_operator_language_semantic,
            },
            receipt_store=self.synthesis_receipt_store,
            sensorium_sink=self._record_synthesis_event,
        )

    def _operator_language_semantic_candidates(self, request: Any) -> tuple[ResidualCandidate, ...]:
        if getattr(request, "task_class", "") != "beast.operator_language":
            return ()
        payload = dict((getattr(request, "payload", {}) or {}).get("synthesis_payload") or {})
        utterance = str(payload.get("utterance") or payload.get("prompt") or "").strip()
        if not utterance:
            return ()
        evidence_digest = str((getattr(request, "payload", {}) or {}).get("evidence_digest") or "")
        if not evidence_digest:
            evidence_digest = sha256_digest({"source": "operator_language_plane", "utterance_digest": sha256_digest(utterance)})
        return (
            ResidualCandidate(
                candidate_id="candidate:operator-language:semantic:" + request.request_digest.removeprefix("sha256:")[:24],
                route=ResidualRoute.SEMANTIC_RESULT,
                applicability=ApplicabilityState.APPLICABLE,
                verification=VerificationState.VERIFIED,
                authority=ResidualAuthority.READ_VERIFIED,
                predicted_latency_ms=2.0,
                predicted_cpu_ms=2.0,
                predicted_memory_bytes=64 * 1024,
                predicted_monetary_cost=0.0,
                confidence=1.0,
                expected_quality=1.0,
                failure_probability=0.0,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                evidence_digest=evidence_digest,
                metadata={"task_family": "beast.operator_language", "executor": "OperatorLanguagePlane.answer"},
            ),
        )

    def _execute_operator_language_semantic(self, request: Any, decision_digest: str) -> RouteExecutionResult:
        if request.task_class != "beast.operator_language":
            raise RuntimeError("semantic synthesis executor only handles operator language")
        payload = dict((request.payload or {}).get("synthesis_payload") or {})
        operator_request = OperatorLanguageRequest(
            utterance=str(payload.get("utterance") or payload.get("prompt") or ""),
            tone=str(payload.get("tone") or "concise"),
            workspace_id=str(payload.get("workspace_id") or "operator"),
            privacy_domain=str(payload.get("privacy_domain") or "operator"),
            discourse_digest=str(payload.get("discourse_digest") or ""),
            policy_digest=str(payload.get("policy_digest") or ""),
        )
        replay = self._replay_operator_language_semantic(operator_request)
        response = replay[0] if replay is not None else self.operator_language_plane.answer(payload)
        verified = not response.receipt.provider_called and not response.receipt.action_taken
        execution_payload: dict[str, Any] = {
            "decision_digest": decision_digest,
            "operator_language_receipt": response.receipt.receipt_digest,
        }
        if replay is not None:
            execution_payload["semantic_replay_receipt"] = replay[1]
        return RouteExecutionResult(
            route=ResidualRoute.SEMANTIC_RESULT,
            authority_used=ResidualAuthority.READ_VERIFIED,
            output=response,
            verified=verified,
            execution_digest=sha256_digest(execution_payload),
            actual_latency_ms=2.0,
            actual_cpu_ms=2.0,
            provider_calls=0,
            local_inference_calls=0,
            physical_effects=0,
        )

    def promote_operator_language_semantic_crystal(
        self,
        utterances: list[str] | tuple[str, ...],
        *,
        crystal_id: str | None = None,
        verifier_id: str = "compute-plane.operator-language.semantic",
        tone: str = "concise",
        workspace_id: str = "operator",
        privacy_domain: str = "operator",
        expires_at: str | None = None,
    ) -> SemanticCrystalRecord:
        if len(tuple(utterances)) < self.semantic_generalizer.minimum_verified_episodes:
            raise ValueError("semantic promotion requires repeated verified utterances")
        episodes: list[SemanticEpisode] = []
        for index, utterance in enumerate(utterances, start=1):
            request = OperatorLanguageRequest(
                utterance=utterance,
                tone=tone,
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
            )
            response = self.operator_language_plane.answer(request)
            episodes.append(self._semantic_episode_from_operator_response(
                request=request,
                response=response,
                episode_id=f"operator-language-semantic:{index}",
            ))
        record = self.semantic_generalizer.promote_record(
            episodes,
            crystal_id=crystal_id or self._operator_language_semantic_crystal_id(episodes[0]),
            verifier_id=verifier_id,
            expires_at=expires_at,
        )
        self.semantic_crystal_registry.promote(record)
        self._counters["operator_language.semantic_promoted"] += 1
        self._last_receipts["semantic_promotion"] = record.promotion_receipt_digest
        self._record_capability_learning(
            event_type="promoted",
            capability_type="semantic_crystal",
            capability_id=record.crystal.crystal_id,
            lifecycle_state=record.lifecycle_state.value,
            authority="read_verified",
            evidence_digest=record.promotion_receipt.verification_evidence_digest,
            receipt_digest=record.promotion_receipt_digest,
            fresh_work_units=len(episodes),
            metadata={
                "semantic_key_digest": record.semantic_key_digest,
                "intent": record.crystal.meaning.intent,
                "domain": record.crystal.meaning.domain.value,
            },
        )
        return record

    def _semantic_episode_from_operator_response(
        self,
        *,
        request: OperatorLanguageRequest,
        response: OperatorLanguageResponse,
        episode_id: str,
    ) -> SemanticEpisode:
        if response.receipt.provider_called or response.receipt.action_taken:
            raise ValueError("semantic promotion requires provider-free read-only operator responses")
        if response.receipt.state is not MeaningResolutionState.RESOLVED:
            raise ValueError("semantic promotion requires resolved operator responses")
        if len(response.candidates) != 1 or response.answer_frame is None:
            raise ValueError("semantic promotion requires one resolved meaning and answer frame")
        meaning = response.candidates[0]
        evidence = meaning.evidence
        if not evidence:
            raise ValueError("semantic promotion requires evidence-bound meaning")
        return SemanticEpisode(
            episode_id=episode_id,
            utterance=request.utterance,
            meaning=meaning,
            answer_frame=response.answer_frame,
            schema_digest=self._operator_language_schema_digest(response),
            discourse_digest=request.discourse_digest or self._operator_language_discourse_digest(response),
            world_digest=sha256_digest(tuple(item.world_digest for item in evidence)),
            capability_digest=self._operator_language_capability_digest(response),
            evidence_digest=sha256_digest(tuple(item.evidence_digest for item in evidence)),
            policy_digest=sha256_digest(tuple(item.policy_digest for item in evidence)),
            temporal_scope_digest=sha256_digest(tuple(item.temporal_scope_digest for item in evidence)),
            verification_evidence_digest=sha256_digest({
                "operator_language_receipt": response.receipt.receipt_digest,
                "evidence_bindings": tuple(item.binding_digest for item in evidence),
            }),
            verified=True,
            provider_calls=0,
        )

    def _replay_operator_language_semantic(
        self,
        request: OperatorLanguageRequest,
    ) -> tuple[OperatorLanguageResponse, str] | None:
        for record in self.semantic_crystal_registry.records():
            request_key = self._semantic_request_key_for_record(request, record)
            if request_key is None:
                continue
            outcome = self.semantic_generalizer.replay_record(
                record,
                request_key,
                provider_enabled=False,
            )
            if not outcome.reused or outcome.answer_frame is None:
                continue
            output = realize_answer_frame(outcome.answer_frame, tone=request.tone)
            meaning = record.crystal.meaning
            receipt = OperatorLanguageReceipt(
                utterance_digest=sha256_digest(request.utterance),
                normalized_utterance=normalize_utterance(request.utterance),
                domain=meaning.domain,
                state=MeaningResolutionState.RESOLVED,
                intent=meaning.intent,
                bound_names=self._operator_language_replayed_names(record),
                service_names=self._operator_language_replayed_names(record),
                registry_digest=record.semantic_reuse_key.world_digest,
                evidence_digests=tuple(record.crystal.answer_frame.evidence_digests),
                provider_called=False,
                action_taken=False,
                reason="semantic crystal replay: " + record.crystal.crystal_id,
                created_at=utc_now_iso(),
            )
            self._counters["operator_language.semantic_reused"] += 1
            node = self.evidence_graph.add("semantic_crystal_replayed", {
                "observed_at": receipt.created_at,
                "crystal_id": record.crystal.crystal_id,
                "semantic_replay_receipt_digest": outcome.receipt_digest,
                "operator_language_receipt_digest": receipt.receipt_digest,
                "provider_calls_avoided": 1,
                "provider_called": False,
                "action_taken": False,
                "intent": receipt.intent,
                "domain": receipt.domain.value,
            })
            self._last_receipts["semantic_replay"] = node.node_id
            self._record_capability_learning(
                event_type="reused",
                capability_type="semantic_crystal",
                capability_id=record.crystal.crystal_id,
                lifecycle_state=record.lifecycle_state.value,
                authority="read_verified",
                evidence_digest=node.node_id,
                receipt_digest=outcome.receipt_digest,
                provider_calls_avoided=1,
                reuse_hits=1,
                metadata={
                    "semantic_key_digest": record.semantic_key_digest,
                    "operator_language_receipt_digest": receipt.receipt_digest,
                    "intent": receipt.intent,
                    "domain": receipt.domain.value,
                },
            )
            return (
                OperatorLanguageResponse(
                    output=output,
                    receipt=receipt,
                    candidates=(meaning,),
                    answer_frame=outcome.answer_frame,
                ),
                outcome.receipt_digest,
            )
        return None

    def _semantic_request_key_for_record(
        self,
        request: OperatorLanguageRequest,
        record: SemanticCrystalRecord,
    ) -> SemanticReuseKey | None:
        meaning = record.crystal.meaning
        if meaning.domain.value != "service":
            return None
        registry = self.operator_language_plane.world_binder.registry()
        evidence = self.operator_language_plane._evidence(registry=registry, request=request)
        return SemanticReuseKey(
            semantic_fingerprint_digest=sha256_digest(semantic_intent_fingerprint(request.utterance)),
            normalized_utterance_digest=sha256_digest(normalize_utterance(request.utterance)),
            schema_digest=record.semantic_reuse_key.schema_digest,
            discourse_digest=record.semantic_reuse_key.discourse_digest,
            world_digest=sha256_digest(tuple(item.world_digest for item in evidence)),
            capability_digest=record.semantic_reuse_key.capability_digest,
            evidence_digest=sha256_digest(tuple(item.evidence_digest for item in evidence)),
            policy_digest=sha256_digest(tuple(item.policy_digest for item in evidence)),
            temporal_scope_digest=sha256_digest(tuple(item.temporal_scope_digest for item in evidence)),
        )

    @staticmethod
    def _operator_language_schema_digest(response: OperatorLanguageResponse) -> str:
        return sha256_digest({
            "schema": "operator-language-v1",
            "domain": response.receipt.domain.value,
            "intent": response.receipt.intent,
            "template_id": response.answer_frame.template_id if response.answer_frame else "",
        })

    @staticmethod
    def _operator_language_discourse_digest(response: OperatorLanguageResponse) -> str:
        return sha256_digest({
            "operator_language_discourse": response.receipt.domain.value,
            "intent": response.receipt.intent,
            "bound_names": response.receipt.bound_names,
        })

    @staticmethod
    def _operator_language_capability_digest(response: OperatorLanguageResponse) -> str:
        return sha256_digest({
            "capability": "operator_language.read_only",
            "domain": response.receipt.domain.value,
            "intent": response.receipt.intent,
        })

    @staticmethod
    def _operator_language_replayed_names(record: SemanticCrystalRecord) -> tuple[str, ...]:
        slots = record.crystal.meaning.slots
        value = slots.get("name") or slots.get("service") or slots.get("provider") or slots.get("path") or slots.get("space_id")
        if value is None:
            return ()
        if isinstance(value, (tuple, list)):
            return tuple(str(item) for item in value)
        return (str(value),)

    @staticmethod
    def _operator_language_semantic_crystal_id(episode: SemanticEpisode) -> str:
        return "meaning-crystal:operator-language:" + episode.reuse_key.semantic_match_digest.removeprefix("sha256:")[:24]

    def compose_scene_capsule(
        self,
        scene: SceneCrystal | Mapping[str, Any],
        *,
        manifest: SignedAssetManifest | None = None,
        capsule_id: str | None = None,
        interface: str = "api",
    ) -> SceneCapsuleRuntimeResult:
        """Compose a deterministic scene through the production custody boundary."""
        self.assert_production_composition()
        asset_manifest = manifest or default_beast_asset_manifest()
        scene_crystal = scene if isinstance(scene, SceneCrystal) else self._scene_crystal_from_payload(scene, asset_manifest)
        before = int(self._counters["provider.execute"])
        svg, receipt, capsule = self.scene_compositor.compose_capsule(
            scene_crystal,
            asset_manifest,
            capsule_id=capsule_id,
        )
        after = int(self._counters["provider.execute"])
        if after != before:
            raise RuntimeError("scene capsule composition violated provider-free contract")
        node = self.evidence_graph.add("scene_capsule_composed", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "scene_id": scene_crystal.scene_id,
            "scene_digest": scene_crystal.scene_digest,
            "manifest_digest": asset_manifest.manifest_digest,
            "composition_receipt_digest": receipt.receipt_digest,
            "capsule_digest": capsule.capsule_digest,
            "output_digest": receipt.output_digest,
            "policy_digest": scene_crystal.policy_digest,
            "authority": capsule.authority,
            "maximum_authority": capsule.maximum_authority,
            "network_scope": capsule.network_scope,
            "provider_scope": capsule.provider_scope,
            "physical_scope": capsule.physical_scope,
            "provider_call_witness": {"before": before, "after": after, "during_execution": after - before},
        })
        self._last_receipts["scene_capsule"] = node.node_id
        self._counters["scene_capsule.composed"] += 1
        return SceneCapsuleRuntimeResult(svg, receipt, capsule, node.node_id)

    @staticmethod
    def _scene_crystal_from_payload(payload: Mapping[str, Any], manifest: SignedAssetManifest) -> SceneCrystal:
        canvas_payload = dict(payload.get("canvas") or {})
        canvas = CanvasContract(
            width=int(canvas_payload.get("width") or payload.get("width") or 320),
            height=int(canvas_payload.get("height") or payload.get("height") or 160),
            background=str(canvas_payload.get("background") or payload.get("background") or "#07110d"),
        )
        opcodes_payload = payload.get("opcodes") or ()
        if not isinstance(opcodes_payload, (list, tuple)):
            raise ValueError("scene opcodes must be a list")
        opcodes = tuple(
            SceneOpcode(
                SceneOpcodeKind(str(item.get("kind") or item.get("opcode") or "")),
                dict(item.get("args") or {}),
            )
            for item in opcodes_payload
            if isinstance(item, Mapping)
        )
        if len(opcodes) != len(opcodes_payload):
            raise ValueError("scene opcodes must be objects")
        policy_digest = str(payload.get("policy_digest") or "")
        if not policy_digest:
            policy_digest = sha256_digest({
                "policy": "deterministic-scene-runtime.v1",
                "manifest_digest": manifest.manifest_digest,
            })
        manifest_digest = str(payload.get("manifest_digest") or manifest.manifest_digest)
        if manifest_digest != manifest.manifest_digest:
            raise ValueError("scene manifest_digest must match the selected asset manifest")
        return SceneCrystal(
            scene_id=str(payload.get("scene_id") or "scene:runtime"),
            manifest_digest=manifest_digest,
            canvas=canvas,
            opcodes=opcodes,
            policy_digest=policy_digest,
            verifier_id=str(payload.get("verifier_id") or "compute-plane.scene-capsule"),
            output_format=str(payload.get("output_format") or "image/svg+xml"),
        )

    def run_visual_residual(
        self,
        scene: SceneCrystal | Mapping[str, Any],
        *,
        mask: Mapping[str, Any],
        prompt: str,
        seed: int = 0,
        manifest: SignedAssetManifest | None = None,
        budget: VisualResidualBudget | Mapping[str, Any] | None = None,
        capsule_id: str | None = None,
        interface: str = "api",
    ) -> VisualResidualRuntimeResult:
        """Fill one unresolved visual region bound to a Scene Capsule."""
        self.assert_production_composition()
        if not str(prompt or "").strip():
            raise ValueError("visual residual prompt is required")
        asset_manifest = manifest or default_beast_asset_manifest()
        scene_crystal = scene if isinstance(scene, SceneCrystal) else self._scene_crystal_from_payload(scene, asset_manifest)
        scene_result = self.compose_scene_capsule(
            scene_crystal,
            manifest=asset_manifest,
            capsule_id=capsule_id,
            interface=interface,
        )
        region = self._region_mask_from_payload(mask, scene_crystal.canvas, scene_result.capsule)
        residual_budget = self._visual_residual_budget_from_payload(budget, region)
        prompt_digest = sha256_digest({"prompt": str(prompt)})
        visual_intent = extract_visual_prompt_intent(prompt)
        promotion_key = self._visual_promotion_key(
            scene_result.capsule.capsule_digest,
            region.mask_digest,
            prompt_digest,
            int(seed),
        )
        promoted = self.promoted_visual_assets.get(promotion_key)
        if promoted is not None:
            return self._run_promoted_visual_asset_reuse(
                scene_crystal,
                base_scene_capsule=scene_result,
                manifest=asset_manifest,
                region=region,
                prompt_digest=prompt_digest,
                visual_intent=visual_intent,
                seed=int(seed),
                budget=residual_budget,
                promotion_key=promotion_key,
                record=promoted,
                interface=interface,
            )
        sealed_input_digest = sha256_digest({
            "scene_capsule_digest": scene_result.capsule.capsule_digest,
            "mask_digest": region.mask_digest,
            "prompt_digest": prompt_digest,
            "visual_intent_digest": visual_intent.intent_digest,
            "seed": int(seed),
            "budget": residual_budget,
            "lane": "local_visual_residual",
        })
        request = VisualResidualRequest(
            request_id="visual-residual:" + sealed_input_digest.removeprefix("sha256:")[:32],
            scene_digest=scene_crystal.scene_digest,
            scene_capsule_digest=scene_result.capsule.capsule_digest,
            mask=region,
            unresolved_region_prompt_digest=prompt_digest,
            engine_digest=self.visual_residual_worker.engine_digest,
            model_digest=self.visual_residual_worker.model_digest,
            seed=int(seed),
            budget=residual_budget,
            sealed_input_digest=sealed_input_digest,
            visual_intent=visual_intent,
        )
        before = int(self._counters["provider.execute"])
        output, receipt = self.visual_residual_worker.run(request)
        after = int(self._counters["provider.execute"])
        if after != before or receipt.network_used:
            raise RuntimeError("visual residual worker violated local no-network/provider-free contract")
        if not verify_visual_residual_output(request, receipt, output):
            raise RuntimeError("visual residual receipt failed verification")
        node = self.evidence_graph.add("visual_residual_local_region", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "scene_digest": scene_crystal.scene_digest,
            "scene_capsule_digest": scene_result.capsule.capsule_digest,
            "scene_capsule_evidence_node": scene_result.evidence_node_id,
            "mask_digest": region.mask_digest,
            "request_digest": request.request_digest,
            "receipt_digest": receipt.receipt_digest,
            "output_digest": receipt.output_digest,
            "output_size_bytes": receipt.output_size_bytes,
            "engine_digest": receipt.engine_digest,
            "model_digest": receipt.model_digest,
            "seed": receipt.seed,
            "region_only": True,
            "network_used": receipt.network_used,
            "provider_call_witness": {"before": before, "after": after, "during_execution": after - before},
        })
        self._last_receipts["visual_residual"] = node.node_id
        self._counters["visual_residual.local_region"] += 1
        self._record_visual_asset_observation(
            promotion_key=promotion_key,
            output=output,
            scene_capsule=scene_result.capsule,
            region=region,
            prompt_digest=prompt_digest,
            visual_intent=visual_intent,
            seed=int(seed),
            receipt_digest=receipt.receipt_digest,
            source_lane="local_residual",
        )
        return VisualResidualRuntimeResult(output, request, receipt, scene_result.capsule, node.node_id)

    def run_visual_provider_fallback(
        self,
        scene: SceneCrystal | Mapping[str, Any],
        *,
        mask: Mapping[str, Any],
        prompt: str,
        allow_provider_fallback: bool,
        operator_approval: str,
        provider: str = "configured-image-provider",
        seed: int = 0,
        manifest: SignedAssetManifest | None = None,
        budget: VisualResidualBudget | Mapping[str, Any] | None = None,
        capsule_id: str | None = None,
        interface: str = "api",
    ) -> VisualProviderFallbackRuntimeResult:
        """Explicit provider boundary for unresolved visual regions.

        This is not a default route.  It exists so image-provider use is
        governed, counted, and paired against later local/promotion evidence.
        """
        self.assert_production_composition()
        if self.provider_fallback is None:
            raise PermissionError("visual provider fallback is not configured")
        if allow_provider_fallback is not True:
            raise PermissionError("visual provider fallback requires explicit allow_provider_fallback")
        if not str(operator_approval or "").strip():
            raise PermissionError("visual provider fallback requires an operator approval receipt")
        if not str(prompt or "").strip():
            raise ValueError("visual residual prompt is required")
        asset_manifest = manifest or default_beast_asset_manifest()
        scene_crystal = scene if isinstance(scene, SceneCrystal) else self._scene_crystal_from_payload(scene, asset_manifest)
        scene_result = self.compose_scene_capsule(
            scene_crystal,
            manifest=asset_manifest,
            capsule_id=capsule_id,
            interface=interface,
        )
        region = self._region_mask_from_payload(mask, scene_crystal.canvas, scene_result.capsule)
        residual_budget = self._visual_residual_budget_from_payload(budget, region)
        provider_name = str(provider or "configured-image-provider")
        prompt_digest = sha256_digest({"prompt": str(prompt)})
        visual_intent = extract_visual_prompt_intent(prompt)
        promotion_key = self._visual_promotion_key(
            scene_result.capsule.capsule_digest,
            region.mask_digest,
            prompt_digest,
            int(seed),
        )
        if promotion_key in self.promoted_visual_assets:
            raise PermissionError("promoted visual asset already exists for this region; use local visual residual route")
        approval_receipt_digest = content_hash({"operator_approval": str(operator_approval)})
        sealed_input_digest = sha256_digest({
            "scene_capsule_digest": scene_result.capsule.capsule_digest,
            "mask_digest": region.mask_digest,
            "prompt_digest": prompt_digest,
            "visual_intent_digest": visual_intent.intent_digest,
            "seed": int(seed),
            "budget": residual_budget,
            "provider": provider_name,
            "approval_receipt_digest": approval_receipt_digest,
            "lane": "visual_provider_fallback",
        })
        request = VisualResidualRequest(
            request_id="visual-provider-fallback:" + sealed_input_digest.removeprefix("sha256:")[:32],
            scene_digest=scene_crystal.scene_digest,
            scene_capsule_digest=scene_result.capsule.capsule_digest,
            mask=region,
            unresolved_region_prompt_digest=prompt_digest,
            engine_digest=sha256_digest({"engine": "provider_visual_fallback_boundary", "provider": provider_name}),
            model_digest=sha256_digest({"model": "external_provider_region", "provider": provider_name}),
            seed=int(seed),
            budget=residual_budget,
            sealed_input_digest=sealed_input_digest,
            visual_intent=visual_intent,
        )
        fallback_payload = {
            "task_family": "visual_image_region_generation",
            "scene_digest": request.scene_digest,
            "scene_capsule_digest": request.scene_capsule_digest,
            "mask_digest": region.mask_digest,
            "mask": {
                "mask_id": region.mask_id,
                "x": region.x,
                "y": region.y,
                "width": region.width,
                "height": region.height,
            },
            "prompt": str(prompt),
            "prompt_digest": prompt_digest,
            "visual_intent_digest": visual_intent.intent_digest,
            "request_digest": request.request_digest,
            "provider": provider_name,
            "seed": int(seed),
            "approval_receipt_digest": approval_receipt_digest,
            "network_scope": ("provider_only",),
        }
        before = int(self._counters["provider.execute"])
        started = time.perf_counter_ns()

        def execute() -> Mapping[str, Any]:
            self._counters["provider.execute"] += 1
            assert self.provider_fallback is not None
            return self.provider_fallback(fallback_payload)

        result = self.execute_operation(
            lane="visual_provider_fallback",
            provider=provider_name,
            authorize=lambda: allow_provider_fallback is True and bool(approval_receipt_digest),
            execute=execute,
            verify=lambda value: isinstance(value, Mapping) and value.get("verified") is True,
        )
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        after = int(self._counters["provider.execute"])
        output = self._visual_provider_output_bytes(result)
        expected_size = region.width * region.height * 4
        if len(output) != expected_size:
            raise RuntimeError("visual provider fallback returned bytes outside the requested region boundary")
        output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
        supplied_digest = str(result.get("output_digest") or output_digest)
        if supplied_digest != output_digest:
            raise RuntimeError("visual provider fallback output digest mismatch")
        witness = {"before": before, "after": after, "during_execution": after - before}
        node = self.evidence_graph.add("visual_residual_provider_fallback", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "scene_digest": scene_crystal.scene_digest,
            "scene_capsule_digest": scene_result.capsule.capsule_digest,
            "scene_capsule_evidence_node": scene_result.evidence_node_id,
            "mask_digest": region.mask_digest,
            "request_digest": request.request_digest,
            "provider": provider_name,
            "fallback_reason": "local_region_unresolved",
            "approval_receipt_digest": approval_receipt_digest,
            "output_digest": output_digest,
            "output_size_bytes": len(output),
            "provider_call_witness": witness,
            "execution_latency_ms": elapsed,
            "verified_region_boundary": True,
        })
        receipt = VisualProviderFallbackReceipt(
            request_digest=request.request_digest,
            scene_digest=scene_crystal.scene_digest,
            scene_capsule_digest=scene_result.capsule.capsule_digest,
            mask_digest=region.mask_digest,
            provider=provider_name,
            fallback_reason="local_region_unresolved",
            approval_receipt_digest=approval_receipt_digest,
            output_digest=output_digest,
            output_size_bytes=len(output),
            execution_latency_ms=elapsed,
            provider_call_witness=witness,
            evidence_node_id=node.node_id,
            verified=True,
            final_status="verified_visual_provider_fallback",
        ).sealed()
        self._last_receipts["visual_provider_fallback"] = node.node_id
        self._counters["visual_residual.provider_fallback"] += 1
        self._record_visual_asset_observation(
            promotion_key=promotion_key,
            output=output,
            scene_capsule=scene_result.capsule,
            region=region,
            prompt_digest=prompt_digest,
            visual_intent=visual_intent,
            seed=int(seed),
            receipt_digest=receipt.response_digest,
            source_lane="provider_fallback",
        )
        return VisualProviderFallbackRuntimeResult(output, request, receipt, scene_result.capsule, node.node_id)

    @staticmethod
    def _visual_provider_output_bytes(result: Mapping[str, Any]) -> bytes:
        if isinstance(result.get("output"), bytes):
            return bytes(result["output"])
        encoded = result.get("output_base64")
        if isinstance(encoded, str) and encoded:
            return base64.b64decode(encoded.encode("ascii"), validate=True)
        raise RuntimeError("visual provider fallback must return output_base64 bytes and verified=true")

    @staticmethod
    def _visual_promotion_key(
        scene_capsule_digest: str,
        mask_digest: str,
        prompt_digest: str,
        seed: int,
    ) -> str:
        return sha256_digest({
            "visual_promotion": "scene-capsule-region-v1",
            "scene_capsule_digest": scene_capsule_digest,
            "mask_digest": mask_digest,
            "prompt_digest": prompt_digest,
            "seed": int(seed),
        })

    def _run_promoted_visual_asset_reuse(
        self,
        scene: SceneCrystal,
        *,
        base_scene_capsule: SceneCapsuleRuntimeResult,
        manifest: SignedAssetManifest,
        region: RegionMask,
        prompt_digest: str,
        visual_intent: VisualPromptIntent,
        seed: int,
        budget: VisualResidualBudget,
        promotion_key: str,
        record: VisualPromotedAssetRecord,
        interface: str,
    ) -> VisualResidualRuntimeResult:
        output = self._read_promoted_visual_asset_bytes(record)
        asset_manifest = self._manifest_with_visual_asset(manifest, record.asset)
        promoted_scene = SceneCrystal(
            scene_id=scene.scene_id + ":promoted-visual:" + promotion_key.removeprefix("sha256:")[:16],
            manifest_digest=asset_manifest.manifest_digest,
            canvas=scene.canvas,
            opcodes=scene.opcodes + (
                SceneOpcode(
                    SceneOpcodeKind.PLACE_ASSET,
                    {
                        "asset_id": record.asset.asset_id,
                        "x": region.x,
                        "y": region.y,
                        "width": region.width,
                        "height": region.height,
                    },
                ),
            ),
            policy_digest=sha256_digest({
                "policy": "promoted-visual-asset-reuse.v1",
                "base_policy_digest": scene.policy_digest,
                "promotion_key": promotion_key,
            }),
            verifier_id="compute-plane.promoted-visual-asset",
            output_format=scene.output_format,
        )
        promoted_capsule = self.compose_scene_capsule(
            promoted_scene,
            manifest=asset_manifest,
            capsule_id="scene-capsule:promoted-visual:" + promotion_key.removeprefix("sha256:")[:24],
            interface=interface,
        )
        engine_digest = sha256_digest({
            "engine": "promoted_visual_asset_manifest",
            "asset_digest": record.asset.digest,
        })
        model_digest = sha256_digest({
            "model": "signed_visual_region_asset_reuse",
            "asset_id": record.asset.asset_id,
        })
        sealed_input_digest = sha256_digest({
            "scene_capsule_digest": promoted_capsule.capsule.capsule_digest,
            "base_scene_capsule_digest": base_scene_capsule.capsule.capsule_digest,
            "mask_digest": region.mask_digest,
            "prompt_digest": prompt_digest,
            "visual_intent_digest": visual_intent.intent_digest,
            "seed": int(seed),
            "budget": budget,
            "promotion_key": promotion_key,
            "asset_id": record.asset.asset_id,
            "lane": "promoted_visual_asset_reuse",
        })
        request = VisualResidualRequest(
            request_id="visual-promoted-asset:" + sealed_input_digest.removeprefix("sha256:")[:32],
            scene_digest=promoted_scene.scene_digest,
            scene_capsule_digest=promoted_capsule.capsule.capsule_digest,
            mask=region,
            unresolved_region_prompt_digest=prompt_digest,
            engine_digest=engine_digest,
            model_digest=model_digest,
            seed=int(seed),
            budget=budget,
            sealed_input_digest=sealed_input_digest,
            visual_intent=visual_intent,
        )
        before = int(self._counters["provider.execute"])
        receipt = VisualResidualReceipt(
            request_digest=request.request_digest,
            scene_digest=request.scene_digest,
            scene_capsule_digest=request.scene_capsule_digest,
            mask_digest=region.mask_digest,
            engine_digest=engine_digest,
            model_digest=model_digest,
            seed=int(seed),
            output_digest=record.output_digest,
            output_size_bytes=len(output),
            runtime_ms=0,
            memory_bytes=len(output),
            network_used=False,
            sealed_input_digest=sealed_input_digest,
            sealed_output_digest=sha256_digest({"output": record.output_digest, "mask": region.mask_digest}),
            provenance_digest=region.provenance_digest,
            verified=True,
            details={
                "worker": "promoted_visual_asset_reuse",
                "asset_id": record.asset.asset_id,
                "asset_digest": record.asset.digest,
                "promotion_key": promotion_key,
                "visual_intent": {
                    "color_name": visual_intent.color_name,
                    "object_hint": visual_intent.object_hint,
                    "intent_digest": visual_intent.intent_digest,
                    "intent_receipt_digest": record.intent_receipt_digest,
                    "perceptual_receipt_digest": record.perceptual_receipt_digest,
                    "feature_embedding_digest": record.feature_embedding_digest,
                    "equivalence_receipt_digest": record.equivalence_receipt_digest,
                },
                "base_scene_capsule_digest": base_scene_capsule.capsule.capsule_digest,
                "promoted_scene_capsule_digest": promoted_capsule.capsule.capsule_digest,
                "region_only": True,
            },
        )
        after = int(self._counters["provider.execute"])
        if after != before:
            raise RuntimeError("promoted visual asset reuse violated provider-free contract")
        if not verify_visual_residual_output(request, receipt, output):
            raise RuntimeError("promoted visual asset reuse failed verification")
        node = self.evidence_graph.add("visual_residual_promoted_asset_reuse", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "promotion_key": promotion_key,
            "asset_id": record.asset.asset_id,
            "asset_digest": record.asset.digest,
            "record_digest": record.record_digest,
            "base_scene_capsule_digest": base_scene_capsule.capsule.capsule_digest,
            "promoted_scene_capsule_digest": promoted_capsule.capsule.capsule_digest,
            "mask_digest": region.mask_digest,
            "request_digest": request.request_digest,
            "receipt_digest": receipt.receipt_digest,
            "output_digest": receipt.output_digest,
            "region_only": True,
            "local_residual_calls_avoided": 1,
            "provider_call_witness": {"before": before, "after": after, "during_execution": after - before},
        })
        self._last_receipts["visual_promoted_asset_reuse"] = node.node_id
        self._counters["visual_residual.promoted_asset_reuse"] += 1
        self._record_capability_learning(
            event_type="reused",
            capability_type="visual_asset",
            capability_id=record.asset.asset_id,
            lifecycle_state=record.asset.state,
            authority="render_only",
            evidence_digest=node.node_id,
            receipt_digest=receipt.receipt_digest,
            provider_calls_avoided=1,
            reuse_hits=1,
            metadata={
                "promotion_key": promotion_key,
                "asset_digest": record.asset.digest,
                "local_residual_calls_avoided": 1,
                "equivalence_receipt_digest": record.equivalence_receipt_digest,
            },
        )
        return VisualResidualRuntimeResult(output, request, receipt, promoted_capsule.capsule, node.node_id)

    def _record_visual_asset_observation(
        self,
        *,
        promotion_key: str,
        output: bytes,
        scene_capsule: SceneCapsule,
        region: RegionMask,
        prompt_digest: str,
        visual_intent: VisualPromptIntent,
        seed: int,
        receipt_digest: str,
        source_lane: str,
    ) -> None:
        if promotion_key in self.promoted_visual_assets:
            return
        output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
        quality = evaluate_visual_region_quality(region, output)
        intent_receipt = evaluate_visual_region_intent(region, output, visual_intent)
        perceptual = evaluate_visual_region_perceptual(region, output, visual_intent)
        feature_embedding = build_visual_region_feature_embedding(region, output, visual_intent)
        if not quality.passed:
            node = self.evidence_graph.add("visual_asset_candidate_refused", {
                "observed_at": utc_now_iso(),
                "promotion_key": promotion_key,
                "scene_capsule_digest": scene_capsule.capsule_digest,
                "mask_digest": region.mask_digest,
                "prompt_digest": prompt_digest,
                "seed": int(seed),
                "output_digest": output_digest,
                "receipt_digest": receipt_digest,
                "source_lane": source_lane,
                "reason": "quality_gate_failed",
                "quality_receipt": asdict(quality),
                "quality_receipt_digest": quality.receipt_digest,
                "intent_receipt": asdict(intent_receipt),
                "intent_receipt_digest": intent_receipt.receipt_digest,
                "perceptual_receipt": asdict(perceptual),
                "perceptual_receipt_digest": perceptual.receipt_digest,
                "feature_embedding_digest": feature_embedding.embedding_digest,
            })
            self._last_receipts["visual_asset_refusal"] = quality.receipt_digest
            self._counters["visual_asset.refused"] += 1
            self._record_capability_learning(
                event_type="refused",
                capability_type="visual_asset_candidate",
                capability_id=promotion_key,
                lifecycle_state="refused",
                authority="render_only",
                evidence_digest=node.node_id,
                receipt_digest=quality.receipt_digest,
                provider_calls_used=1 if source_lane == "provider_fallback" else 0,
                fresh_work_units=1,
                refusal_reason="quality_gate_failed",
                metadata={"source_lane": source_lane, "output_digest": output_digest},
            )
            return
        if not intent_receipt.passed:
            node = self.evidence_graph.add("visual_asset_candidate_refused", {
                "observed_at": utc_now_iso(),
                "promotion_key": promotion_key,
                "scene_capsule_digest": scene_capsule.capsule_digest,
                "mask_digest": region.mask_digest,
                "prompt_digest": prompt_digest,
                "visual_intent_digest": visual_intent.intent_digest,
                "seed": int(seed),
                "output_digest": output_digest,
                "receipt_digest": receipt_digest,
                "source_lane": source_lane,
                "reason": "intent_gate_failed",
                "quality_receipt_digest": quality.receipt_digest,
                "intent_receipt": asdict(intent_receipt),
                "intent_receipt_digest": intent_receipt.receipt_digest,
                "perceptual_receipt": asdict(perceptual),
                "perceptual_receipt_digest": perceptual.receipt_digest,
                "feature_embedding_digest": feature_embedding.embedding_digest,
            })
            self._last_receipts["visual_asset_refusal"] = intent_receipt.receipt_digest
            self._counters["visual_asset.refused"] += 1
            self._record_capability_learning(
                event_type="refused",
                capability_type="visual_asset_candidate",
                capability_id=promotion_key,
                lifecycle_state="refused",
                authority="render_only",
                evidence_digest=node.node_id,
                receipt_digest=intent_receipt.receipt_digest,
                provider_calls_used=1 if source_lane == "provider_fallback" else 0,
                fresh_work_units=1,
                refusal_reason="intent_gate_failed",
                metadata={"source_lane": source_lane, "output_digest": output_digest},
            )
            return
        if not perceptual.passed:
            node = self.evidence_graph.add("visual_asset_candidate_refused", {
                "observed_at": utc_now_iso(),
                "promotion_key": promotion_key,
                "scene_capsule_digest": scene_capsule.capsule_digest,
                "mask_digest": region.mask_digest,
                "prompt_digest": prompt_digest,
                "visual_intent_digest": visual_intent.intent_digest,
                "seed": int(seed),
                "output_digest": output_digest,
                "receipt_digest": receipt_digest,
                "source_lane": source_lane,
                "reason": "perceptual_gate_failed",
                "quality_receipt_digest": quality.receipt_digest,
                "intent_receipt_digest": intent_receipt.receipt_digest,
                "perceptual_receipt": asdict(perceptual),
                "perceptual_receipt_digest": perceptual.receipt_digest,
                "feature_embedding_digest": feature_embedding.embedding_digest,
            })
            self._last_receipts["visual_asset_refusal"] = perceptual.receipt_digest
            self._counters["visual_asset.refused"] += 1
            self._record_capability_learning(
                event_type="refused",
                capability_type="visual_asset_candidate",
                capability_id=promotion_key,
                lifecycle_state="refused",
                authority="render_only",
                evidence_digest=node.node_id,
                receipt_digest=perceptual.receipt_digest,
                provider_calls_used=1 if source_lane == "provider_fallback" else 0,
                fresh_work_units=1,
                refusal_reason="perceptual_gate_failed",
                metadata={"source_lane": source_lane, "output_digest": output_digest},
            )
            return
        previous_digest = self._visual_asset_observation_digests.get(promotion_key)
        equivalence_receipt_digest = ""
        if previous_digest and previous_digest != output_digest:
            previous_embedding = self._visual_asset_observation_embeddings.get(promotion_key)
            equivalence = (
                evaluate_visual_region_equivalence(previous_embedding, feature_embedding)
                if previous_embedding is not None
                else None
            )
            if equivalence is None or not equivalence.equivalent:
                node = self.evidence_graph.add("visual_asset_candidate_refused", {
                    "observed_at": utc_now_iso(),
                    "promotion_key": promotion_key,
                    "scene_capsule_digest": scene_capsule.capsule_digest,
                    "mask_digest": region.mask_digest,
                    "prompt_digest": prompt_digest,
                    "seed": int(seed),
                    "previous_output_digest": previous_digest,
                    "new_output_digest": output_digest,
                    "reason": "unstable_region_output",
                    "quality_receipt_digest": quality.receipt_digest,
                    "intent_receipt_digest": intent_receipt.receipt_digest,
                    "perceptual_receipt_digest": perceptual.receipt_digest,
                    "feature_embedding_digest": feature_embedding.embedding_digest,
                    "equivalence_receipt": asdict(equivalence) if equivalence is not None else None,
                    "equivalence_receipt_digest": equivalence.receipt_digest if equivalence is not None else "",
                })
                self._last_receipts["visual_asset_refusal"] = (
                    equivalence.receipt_digest if equivalence is not None else perceptual.receipt_digest
                )
                self._counters["visual_asset.refused"] += 1
                self._record_capability_learning(
                    event_type="refused",
                    capability_type="visual_asset_candidate",
                    capability_id=promotion_key,
                    lifecycle_state="refused",
                    authority="render_only",
                    evidence_digest=node.node_id,
                    receipt_digest=equivalence.receipt_digest if equivalence is not None else perceptual.receipt_digest,
                    provider_calls_used=1 if source_lane == "provider_fallback" else 0,
                    fresh_work_units=1,
                    refusal_reason="unstable_region_output",
                    metadata={"source_lane": source_lane, "output_digest": output_digest},
                )
                self._visual_asset_observations[promotion_key] = 1
                self._visual_asset_observation_receipts[promotion_key] = [receipt_digest]
                self._visual_asset_observation_equivalence_receipts[promotion_key] = []
                self._visual_asset_observation_lanes[promotion_key] = {source_lane}
                self._visual_asset_observation_digests[promotion_key] = output_digest
                self._visual_asset_observation_embeddings[promotion_key] = feature_embedding
                return
            equivalence_receipt_digest = equivalence.receipt_digest
            self._visual_asset_observation_equivalence_receipts.setdefault(promotion_key, []).append(equivalence.receipt_digest)
            self.evidence_graph.add("visual_asset_candidate_equivalent", {
                "observed_at": utc_now_iso(),
                "promotion_key": promotion_key,
                "scene_capsule_digest": scene_capsule.capsule_digest,
                "mask_digest": region.mask_digest,
                "prompt_digest": prompt_digest,
                "seed": int(seed),
                "previous_output_digest": previous_digest,
                "new_output_digest": output_digest,
                "equivalence_receipt": asdict(equivalence),
                "equivalence_receipt_digest": equivalence.receipt_digest,
                "feature_embedding_digest": feature_embedding.embedding_digest,
            })
        self._visual_asset_observation_digests[promotion_key] = output_digest
        self._visual_asset_observation_embeddings[promotion_key] = feature_embedding
        self._visual_asset_observations[promotion_key] += 1
        self._visual_asset_observation_receipts.setdefault(promotion_key, []).append(receipt_digest)
        self._visual_asset_observation_lanes.setdefault(promotion_key, set()).add(source_lane)
        if self._visual_asset_observations[promotion_key] < 2:
            return
        asset_id = "beast.visual.region." + promotion_key.removeprefix("sha256:")[:24]
        asset_path = self._promoted_visual_asset_path(asset_id)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = asset_path.with_name(asset_path.name + ".tmp")
        temporary.write_bytes(output)
        os.replace(temporary, asset_path)
        asset = AssetRef(
            asset_id=asset_id,
            kind=AssetKind.VISUAL_REGION,
            digest=output_digest,
            media_type="application/beast-rgba-region",
            width=region.width,
            height=region.height,
            source="beast://visual-assets/" + asset_path.name,
            state="promoted",
        )
        receipts = tuple(sorted(set(self._visual_asset_observation_receipts.get(promotion_key, []))))
        equivalence_receipts = tuple(sorted(set(self._visual_asset_observation_equivalence_receipts.get(promotion_key, []))))
        lanes = tuple(sorted(self._visual_asset_observation_lanes.get(promotion_key, {source_lane})))
        node = self.evidence_graph.add("visual_asset_promoted", {
            "observed_at": utc_now_iso(),
            "promotion_key": promotion_key,
            "asset": {
                **asdict(asset),
                "kind": asset.kind.value,
            },
            "scene_capsule_digest": scene_capsule.capsule_digest,
            "mask_digest": region.mask_digest,
            "prompt_digest": prompt_digest,
            "visual_intent_digest": visual_intent.intent_digest,
            "seed": int(seed),
            "output_digest": output_digest,
            "output_size_bytes": len(output),
            "observation_count": int(self._visual_asset_observations[promotion_key]),
            "provenance_receipts": receipts,
            "source_lanes": lanes,
            "quality_receipt": asdict(quality),
            "quality_receipt_digest": quality.receipt_digest,
            "intent_receipt": asdict(intent_receipt),
            "intent_receipt_digest": intent_receipt.receipt_digest,
            "perceptual_receipt": asdict(perceptual),
            "perceptual_receipt_digest": perceptual.receipt_digest,
            "feature_embedding": asdict(feature_embedding),
            "feature_embedding_digest": feature_embedding.embedding_digest,
            "equivalence_receipt_digest": equivalence_receipt_digest,
            "equivalence_receipts": equivalence_receipts,
            "promotion_equivalence": "exact_digest" if not equivalence_receipts else "visual_feature_embedding",
            "promotion_threshold": 2,
            "maximum_authority": "render_only",
            "network_scope": "none",
            "provider_scope": "none",
        })
        record = VisualPromotedAssetRecord(
            promotion_key=promotion_key,
            asset=asset,
            source_path=str(asset_path),
            scene_capsule_digest=scene_capsule.capsule_digest,
            mask_digest=region.mask_digest,
            prompt_digest=prompt_digest,
            seed=int(seed),
            output_digest=output_digest,
            output_size_bytes=len(output),
            observation_count=int(self._visual_asset_observations[promotion_key]),
            provenance_receipts=receipts,
            source_lanes=lanes,
            evidence_node_id=node.node_id,
            created_at=utc_now_iso(),
            quality_receipt_digest=quality.receipt_digest,
            intent_receipt_digest=intent_receipt.receipt_digest,
            perceptual_receipt_digest=perceptual.receipt_digest,
            feature_embedding_digest=feature_embedding.embedding_digest,
            equivalence_receipt_digest=equivalence_receipt_digest,
        )
        self.promoted_visual_assets[promotion_key] = record
        self._last_receipts["visual_asset_promotion"] = node.node_id
        self._counters["visual_asset.promoted"] += 1
        self._record_capability_learning(
            event_type="promoted",
            capability_type="visual_asset",
            capability_id=asset.asset_id,
            lifecycle_state=asset.state,
            authority="render_only",
            evidence_digest=node.node_id,
            receipt_digest=node.node_id,
            provider_calls_used=sum(1 for lane in self._visual_asset_observation_lanes.get(promotion_key, ()) if lane == "provider_fallback"),
            fresh_work_units=int(self._visual_asset_observations[promotion_key]),
            metadata={
                "promotion_key": promotion_key,
                "asset_digest": asset.digest,
                "promotion_equivalence": "exact_digest" if not equivalence_receipts else "visual_feature_embedding",
                "equivalence_receipts": equivalence_receipts,
            },
        )
        self._persist_promoted_visual_assets()

    def _read_promoted_visual_asset_bytes(self, record: VisualPromotedAssetRecord) -> bytes:
        path = Path(record.source_path)
        if not path.is_file():
            raise RuntimeError("promoted visual asset bytes are missing")
        output = path.read_bytes()
        output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
        if output_digest != record.output_digest or output_digest != record.asset.digest:
            raise RuntimeError("promoted visual asset bytes failed digest verification")
        if len(output) != record.output_size_bytes:
            raise RuntimeError("promoted visual asset size failed verification")
        return output

    @staticmethod
    def _manifest_with_visual_asset(manifest: SignedAssetManifest, asset: AssetRef) -> SignedAssetManifest:
        for existing in manifest.assets:
            if existing.asset_id == asset.asset_id:
                if existing.digest != asset.digest:
                    raise ValueError("promoted visual asset id collides with a different digest")
                return manifest
        return SignedAssetManifest(
            manifest_id=manifest.manifest_id + "+visual:" + asset.asset_id.rsplit(".", 1)[-1],
            assets=manifest.assets + (asset,),
            signer_id=manifest.signer_id,
            signature=manifest.signature,
        )

    def _promoted_visual_asset_path(self, asset_id: str) -> Path:
        return self.root / "visual_assets" / (asset_id.replace(":", "_") + ".rgba")

    def _promoted_visual_asset_index_path(self) -> Path:
        return self.root / "visual_assets" / "index.json"

    def _persist_promoted_visual_assets(self) -> None:
        path = self._promoted_visual_asset_index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [record.to_dict() for record in sorted(self.promoted_visual_assets.values(), key=lambda item: item.promotion_key)]
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def _load_promoted_visual_assets(self) -> None:
        path = self._promoted_visual_asset_index_path()
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("promoted visual asset index is not a list")
        for item in payload:
            if not isinstance(item, Mapping):
                raise RuntimeError("promoted visual asset index contains a non-object")
            asset_payload = dict(item.get("asset") or {})
            asset = AssetRef(
                asset_id=str(asset_payload.get("asset_id") or ""),
                kind=AssetKind(str(asset_payload.get("kind") or "")),
                digest=str(asset_payload.get("digest") or ""),
                media_type=str(asset_payload.get("media_type") or ""),
                width=int(asset_payload.get("width") or 0),
                height=int(asset_payload.get("height") or 0),
                source=str(asset_payload.get("source") or ""),
                state=str(asset_payload.get("state") or ""),
            )
            record = VisualPromotedAssetRecord(
                promotion_key=str(item.get("promotion_key") or ""),
                asset=asset,
                source_path=str(item.get("source_path") or ""),
                scene_capsule_digest=str(item.get("scene_capsule_digest") or ""),
                mask_digest=str(item.get("mask_digest") or ""),
                prompt_digest=str(item.get("prompt_digest") or ""),
                seed=int(item.get("seed") or 0),
                output_digest=str(item.get("output_digest") or ""),
                output_size_bytes=int(item.get("output_size_bytes") or 0),
                observation_count=int(item.get("observation_count") or 0),
                provenance_receipts=tuple(str(value) for value in (item.get("provenance_receipts") or ())),
                source_lanes=tuple(str(value) for value in (item.get("source_lanes") or ())),
                evidence_node_id=str(item.get("evidence_node_id") or ""),
                created_at=str(item.get("created_at") or ""),
                quality_receipt_digest=str(item.get("quality_receipt_digest") or ""),
                intent_receipt_digest=str(item.get("intent_receipt_digest") or ""),
                perceptual_receipt_digest=str(item.get("perceptual_receipt_digest") or ""),
                feature_embedding_digest=str(item.get("feature_embedding_digest") or ""),
                equivalence_receipt_digest=str(item.get("equivalence_receipt_digest") or ""),
            )
            validate_digest(record.promotion_key, field_name="promotion_key")
            validate_digest(record.output_digest, field_name="output_digest")
            self.promoted_visual_assets[record.promotion_key] = record
            self._visual_asset_observations[record.promotion_key] = max(2, record.observation_count)
            self._visual_asset_observation_digests[record.promotion_key] = record.output_digest
            self._visual_asset_observation_receipts[record.promotion_key] = list(record.provenance_receipts)
            self._visual_asset_observation_equivalence_receipts[record.promotion_key] = [
                record.equivalence_receipt_digest
            ] if record.equivalence_receipt_digest else []
            self._visual_asset_observation_lanes[record.promotion_key] = set(record.source_lanes)

    @staticmethod
    def _region_mask_from_payload(payload: Mapping[str, Any], canvas: CanvasContract, capsule: SceneCapsule) -> RegionMask:
        x = int(payload.get("x") or 0)
        y = int(payload.get("y") or 0)
        width = int(payload.get("width") or 0)
        height = int(payload.get("height") or 0)
        mask_identity = {
            "scene_capsule_digest": capsule.capsule_digest,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
        return RegionMask(
            mask_id=str(payload.get("mask_id") or "mask:" + sha256_digest(mask_identity).removeprefix("sha256:")[:24]),
            x=x,
            y=y,
            width=width,
            height=height,
            canvas=canvas,
            provenance_digest=sha256_digest(mask_identity),
        )

    @staticmethod
    def _visual_residual_budget_from_payload(
        payload: VisualResidualBudget | Mapping[str, Any] | None,
        mask: RegionMask,
    ) -> VisualResidualBudget:
        if isinstance(payload, VisualResidualBudget):
            return payload
        values = dict(payload or {})
        return VisualResidualBudget(
            max_runtime_ms=int(values.get("max_runtime_ms") or 1000),
            max_memory_bytes=int(values.get("max_memory_bytes") or 16 * 1024 * 1024),
            max_output_bytes=int(values.get("max_output_bytes") or mask.width * mask.height * 4),
        )

    def answer_operator_prompt(
        self, utterance: str | Mapping[str, Any], *, interface: str = "api",
    ) -> OperatorLanguageResponse:
        """Resolve bounded operator language against the local BEAST world model."""
        self.assert_production_composition()
        payload = {"utterance": utterance} if isinstance(utterance, str) else dict(utterance)
        payload.setdefault("tone", "concise")
        mode_value = str(payload.pop("synthesis_mode", payload.pop("mode", SynthesisMode.REALIZE.value)) or SynthesisMode.REALIZE.value)
        request = OperatorLanguageRequest(
            utterance=str(payload.get("utterance") or payload.get("prompt") or ""),
            tone=str(payload.get("tone") or "concise"),
            workspace_id=str(payload.get("workspace_id") or "operator"),
            privacy_domain=str(payload.get("privacy_domain") or "operator"),
            discourse_digest=str(payload.get("discourse_digest") or ""),
            policy_digest=str(payload.get("policy_digest") or ""),
        )
        synthesis_request = SynthesisRequest(
            request_id="operator-language:" + uuid.uuid4().hex,
            workspace_id=request.workspace_id,
            privacy_domain=request.privacy_domain,
            task_class="beast.operator_language",
            mode=SynthesisMode(mode_value),
            payload={
                "utterance": request.utterance,
                "tone": request.tone,
                "workspace_id": request.workspace_id,
                "privacy_domain": request.privacy_domain,
                "discourse_digest": request.discourse_digest,
                "policy_digest": request.policy_digest,
            },
            evidence_digest=sha256_digest({"operator_language_request": request.utterance}),
            policy_digest=request.policy_digest or None,
        )
        before = int(self._counters["provider.execute"])
        output, synthesis_receipt = self.synthesis_plane.run(synthesis_request)
        if not isinstance(output, OperatorLanguageResponse):
            raise RuntimeError("operator language synthesis did not return an operator response")
        response = output
        after = int(self._counters["provider.execute"])
        if after != before or response.receipt.provider_called or response.receipt.action_taken:
            raise RuntimeError("operator language plane violated read-only provider-free contract")
        node = self.evidence_graph.add("operator_language_answer", {
            "interface": interface,
            "receipt_digest": response.receipt.receipt_digest,
            "synthesis_receipt_digest": synthesis_receipt.receipt_digest,
            "synthesis_mode": synthesis_receipt.mode.value,
            "synthesis_route": synthesis_receipt.selected_route.value if synthesis_receipt.selected_route else "",
            "domain": response.receipt.domain.value,
            "state": response.receipt.state.value,
            "intent": response.receipt.intent,
            "bound_names": list(response.receipt.bound_names),
            "service_names": list(response.receipt.service_names),
            "registry_digest": response.receipt.registry_digest,
            "provider_call_witness": {"before": before, "after": after, "during_execution": after - before},
        })
        self._last_receipts["operator_language"] = node.node_id
        self._counters[f"operator_language.{response.receipt.state.value}"] += 1
        return response

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
        reuse_witness = self.physical_registry.record_verified_reuse(
            crystal.identity, proof_digest=proof.proof_digest, execution_digest=execution.receipt_digest,
        )
        displacement = self.evidence_graph.add("production_displacement_observation", {
            "observed_at": utc_now_iso(),
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
            "verified_reuse_receipt": reuse_witness["receipt_digest"],
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
            "observed_at": utc_now_iso(),
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
        self.telemetry_outbox.enqueue_compute_receipt(receipt)
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

    def provider_reduction_scorecard(self) -> dict[str, Any]:
        self.assert_production_composition()
        return self.displacement_observatory.build(
            counters=dict(self._counters),
            evidence_graph=self.evidence_graph,
        ).to_dict()

    def visual_asset_registry_report(self) -> dict[str, Any]:
        self.assert_production_composition()
        assets = [record.to_dict() for record in sorted(self.promoted_visual_assets.values(), key=lambda item: item.promotion_key)]
        return {
            "beast_object_type": "visual_asset_registry",
            "version": "1.0",
            "count": len(assets),
            "assets": assets,
            "registry_digest": sha256_digest(tuple(item["record_digest"] for item in assets)),
        }

    def capability_learning_report(self, *, limit: int = 50) -> dict[str, Any]:
        self.assert_production_composition()
        return self.capability_learning_ledger.report(limit=limit)

    def _record_capability_composition_result(self, receipt: Mapping[str, Any], *, interface: str, family: str) -> dict[str, Any]:
        node = self.evidence_graph.add("capability_composition_executed", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "family": family,
            "question_digest": receipt["question"]["question_digest"],
            "receipt_digest": receipt["receipt_digest"],
            "status": receipt["status"],
            "component_fact_digests": receipt["component_fact_digests"],
            "unsupported_causal_gaps": receipt["unsupported_causal_gaps"],
            "residual_used": receipt["residual_used"],
        })
        event_type = "composed" if receipt["composed"] else "refused"
        self._record_capability_learning(
            event_type=event_type,
            capability_type="capability_composition",
            capability_id=f"{family}:" + receipt["question"]["question_digest"].removeprefix("sha256:")[:24],
            lifecycle_state=str(receipt["status"]),
            authority="read_verified_composition",
            evidence_digest=node.node_id,
            receipt_digest=str(receipt["receipt_digest"]),
            provider_calls_used=0,
            provider_calls_avoided=0,
            fresh_work_units=0,
            reuse_hits=len(receipt["component_fact_digests"]),
            refusal_reason=";".join(receipt["unsupported_causal_gaps"]) if not receipt["composed"] else "",
            metadata={
                "family": family,
                "question_type": str(receipt["question"].get("question_type") or ""),
                "component_count": len(receipt["component_fact_digests"]),
                "residual_used": bool(receipt["residual_used"]),
                "unsupported_causal_gaps": tuple(receipt["unsupported_causal_gaps"]),
            },
        )
        self._last_receipts["capability_composition"] = node.node_id
        self._counters["capability_composition.executed"] += 1
        self._counters[f"capability_composition.{family}"] += 1
        return {**dict(receipt), "evidence_node_id": node.node_id}

    def compose_restart_destabilization_risk(
        self,
        payload: Mapping[str, Any],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        receipt = self.capability_composition_plane.compose_restart_destabilization(
            payload.get("question") if isinstance(payload.get("question"), Mapping) else {},
            tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping)),
            residual_worker=residual_worker,
        )
        return self._record_capability_composition_result(receipt, interface=interface, family="restart-destabilization")

    def compose_traffic_shift_safety(
        self,
        payload: Mapping[str, Any],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        receipt = self.capability_composition_plane.compose_traffic_shift_safety(
            payload.get("question") if isinstance(payload.get("question"), Mapping) else {},
            tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping)),
            residual_worker=residual_worker,
        )
        return self._record_capability_composition_result(receipt, interface=interface, family="traffic-shift")

    def compose_deployment_safety(
        self,
        payload: Mapping[str, Any],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        receipt = self.capability_composition_plane.compose_deployment_safety(
            payload.get("question") if isinstance(payload.get("question"), Mapping) else {},
            tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping)),
            residual_worker=residual_worker,
        )
        return self._record_capability_composition_result(receipt, interface=interface, family="deployment-safety")

    def _record_visual_capability_composition_result(self, receipt: Mapping[str, Any], *, interface: str, family: str) -> dict[str, Any]:
        node = self.evidence_graph.add("visual_capability_composition_executed", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "family": family,
            "question_digest": receipt["question"]["question_digest"],
            "receipt_digest": receipt["receipt_digest"],
            "status": receipt["status"],
            "component_fact_digests": receipt["component_fact_digests"],
            "unsupported_visual_gaps": receipt["unsupported_visual_gaps"],
            "residual_used": receipt["residual_used"],
            "render_authority": receipt["render_authority"],
        })
        event_type = "composed" if receipt["composed"] else "refused"
        self._record_capability_learning(
            event_type=event_type,
            capability_type="visual_composition",
            capability_id=f"{family}:" + receipt["question"]["question_digest"].removeprefix("sha256:")[:24],
            lifecycle_state=str(receipt["status"]),
            authority="render_only_composition",
            evidence_digest=node.node_id,
            receipt_digest=str(receipt["receipt_digest"]),
            provider_calls_used=0,
            provider_calls_avoided=0,
            fresh_work_units=0,
            reuse_hits=len(receipt["component_fact_digests"]),
            refusal_reason=";".join(receipt["unsupported_visual_gaps"]) if not receipt["composed"] else "",
            metadata={
                "family": family,
                "question_type": str(receipt["question"].get("question_type") or ""),
                "component_count": len(receipt["component_fact_digests"]),
                "residual_used": bool(receipt["residual_used"]),
                "unsupported_visual_gaps": tuple(receipt["unsupported_visual_gaps"]),
                "render_authority": receipt["render_authority"],
            },
        )
        self._last_receipts["visual_capability_composition"] = node.node_id
        self._counters["visual_capability_composition.executed"] += 1
        self._counters[f"visual_capability_composition.{family}"] += 1
        return {**dict(receipt), "evidence_node_id": node.node_id}

    def compose_visual_status_card(
        self,
        payload: Mapping[str, Any],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        receipt = self.visual_capability_composition_plane.compose_status_card(
            payload.get("question") if isinstance(payload.get("question"), Mapping) else {},
            tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping)),
            residual_worker=residual_worker,
        )
        return self._record_visual_capability_composition_result(receipt, interface=interface, family="status-card")

    def compose_visual_promoted_region_reuse(
        self,
        payload: Mapping[str, Any],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        receipt = self.visual_capability_composition_plane.compose_promoted_region_reuse(
            payload.get("question") if isinstance(payload.get("question"), Mapping) else {},
            tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping)),
            residual_worker=residual_worker,
        )
        return self._record_visual_capability_composition_result(receipt, interface=interface, family="promoted-region-reuse")

    def compose_visual_layout_safety(
        self,
        payload: Mapping[str, Any],
        *,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        receipt = self.visual_capability_composition_plane.compose_layout_safety(
            payload.get("question") if isinstance(payload.get("question"), Mapping) else {},
            tuple(item for item in (payload.get("facts") or ()) if isinstance(item, Mapping)),
        )
        return self._record_visual_capability_composition_result(receipt, interface=interface, family="layout-safety")

    def compose_cross_modal_restart_risk_visual(
        self,
        payload: Mapping[str, Any],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        visual_residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        interface: str = "api",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        proof_first = compile_restart_risk_proof_first(payload)
        text_payload = payload.get("text") if isinstance(payload.get("text"), Mapping) else {}
        visual_payload = payload.get("visual") if isinstance(payload.get("visual"), Mapping) else {}
        status_payload = visual_payload.get("status_card") if isinstance(visual_payload.get("status_card"), Mapping) else {}
        reuse_payload = visual_payload.get("promoted_region_reuse") if isinstance(visual_payload.get("promoted_region_reuse"), Mapping) else {}
        layout_payload = visual_payload.get("layout_safety") if isinstance(visual_payload.get("layout_safety"), Mapping) else {}
        text_receipt = self.compose_restart_destabilization_risk(
            text_payload,
            residual_worker=residual_worker,
            interface=interface + ".text",
        )
        status_receipt = self.compose_visual_status_card(
            status_payload,
            residual_worker=visual_residual_worker,
            interface=interface + ".visual.status-card",
        )
        reuse_receipt = self.compose_visual_promoted_region_reuse(
            reuse_payload,
            residual_worker=visual_residual_worker,
            interface=interface + ".visual.reuse",
        )
        layout_receipt = self.compose_visual_layout_safety(
            layout_payload,
            interface=interface + ".visual.layout",
        )
        cross_question = payload.get("question") if isinstance(payload.get("question"), Mapping) else {
            "question_id": "cross-modal:restart-risk-visual",
            "text_question_digest": text_receipt["question"]["question_digest"],
            "visual_question_digest": status_receipt["question"]["question_digest"],
            "operator_goal": "answer restart-risk and render a visual explanation",
            "family": "restart_risk_visual_explanation",
        }
        receipt = self.cross_modal_composition_plane.compose_restart_risk_visual(
            cross_question,
            text_receipt=text_receipt,
            visual_receipts={
                "status_card": status_receipt,
                "promoted_region_reuse": reuse_receipt,
                "layout_safety": layout_receipt,
            },
            proof_graph=proof_first["proof_graph"],
            text_view=proof_first["text_view"],
            visual_view=proof_first["visual_view"],
            proof_first_realization=proof_first,
            expected_text_output_digest=str(proof_first["text_artifact_digest"]),
            expected_rendered_visual_digest=str(proof_first["rendered_artifact_digest"]),
        )
        node = self.evidence_graph.add("cross_modal_composition_executed", {
            "observed_at": utc_now_iso(),
            "interface": interface,
            "question_digest": receipt["question"]["question_digest"],
            "receipt_digest": receipt["receipt_digest"],
            "status": receipt["status"],
            "text_receipt_digest": receipt["text_receipt_digest"],
            "visual_receipt_digests": receipt["visual_receipt_digests"],
            "unsupported_causal_gaps": receipt["unsupported_causal_gaps"],
            "unsupported_visual_gaps": receipt["unsupported_visual_gaps"],
            "residual_scopes": receipt["residual_scopes"],
            "provider_calls_used": receipt["provider_calls_used"],
            "proof_graph_digest": receipt["proof_graph_digest"],
            "joined_verification": receipt["joined_verification"],
            "current_claim_valid": receipt["current_claim_valid"],
            "temporal_valid": receipt["temporal_valid"],
            "proof_graph_compiled_before_outputs": receipt["proof_first"].get("proof_graph_compiled_before_outputs") is True,
            "text_semantic_entailment_valid": receipt["text_semantic_entailment_valid"],
            "scene_plan_digest": receipt["scene_plan_digest"],
            "rendered_artifact_digest": receipt["rendered_artifact_digest"],
            "scene_render_valid": receipt["scene_render_valid"],
            "failure_class": receipt["failure_class"],
        })
        self._record_capability_learning(
            event_type="composed" if receipt["composed"] else "refused",
            capability_type="cross_modal_composition",
            capability_id="restart-risk-visual:" + receipt["question"]["question_digest"].removeprefix("sha256:")[:24],
            lifecycle_state=str(receipt["status"]),
            authority="read_verified_render_only_join",
            evidence_digest=node.node_id,
            receipt_digest=str(receipt["receipt_digest"]),
            provider_calls_used=int(receipt["provider_calls_used"]),
            provider_calls_avoided=0,
            fresh_work_units=0,
            reuse_hits=1 + len(receipt["visual_receipt_digests"]),
            refusal_reason=";".join(tuple(receipt["unsupported_causal_gaps"]) + tuple(receipt["unsupported_visual_gaps"])) if not receipt["composed"] else "",
            metadata={
                "family": str(receipt["question"].get("family") or ""),
                "text_status": receipt["text_status"],
                "visual_statuses": dict(receipt["visual_statuses"]),
                "residual_scopes": tuple(receipt["residual_scopes"]),
                "render_authority": receipt["render_authority"],
                "proof_graph_digest": receipt["proof_graph_digest"],
                "joined_verification": bool(receipt["joined_verification"]),
                "current_claim_valid": bool(receipt["current_claim_valid"]),
                "temporal_valid": bool(receipt["temporal_valid"]),
                "failure_class": receipt["failure_class"],
            },
        )
        self._last_receipts["cross_modal_composition"] = node.node_id
        self._counters["cross_modal_composition.executed"] += 1
        return {**receipt, "evidence_node_id": node.node_id}

    def _cross_modal_proof_artifacts(
        self,
        payload: Mapping[str, Any],
        *,
        text_receipt: Mapping[str, Any],
        visual_receipts: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        provided = payload.get("proof") if isinstance(payload.get("proof"), Mapping) else {}
        if provided:
            return {
                "proof_graph": provided.get("proof_graph"),
                "text_view": provided.get("text_view"),
                "visual_view": provided.get("visual_view"),
            }
        claim_status = ProofClaimStatus.SUPPORTED
        if text_receipt.get("unsupported_causal_gaps"):
            claim_status = ProofClaimStatus.UNSUPPORTED
        elif text_receipt.get("status") == "refuted":
            claim_status = ProofClaimStatus.REFUTED
        if str((payload.get("temporal_evidence") if isinstance(payload.get("temporal_evidence"), Mapping) else {}).get("state") or "") == "stale":
            claim_status = ProofClaimStatus.STALE
        claim_id = "claim:restart-risk:" + text_receipt["question"]["question_digest"].removeprefix("sha256:")[:16]
        component_fact_digests = tuple(
            sorted(
                str(digest)
                for digest in dict(text_receipt.get("component_fact_digests") or {}).values()
            )
        )
        visual_receipt_digests = {
            name: str(receipt.get("receipt_digest") or sha256_digest(receipt))
            for name, receipt in visual_receipts.items()
        }
        visual_digest = sha256_digest({"visual_receipt_digests": visual_receipt_digests})
        graph = CanonicalProofGraph(
            graph_id="proof-graph:restart-risk-visual:" + text_receipt["question"]["question_digest"].removeprefix("sha256:")[:16],
            claims=(
                ProofGraphClaim(
                    claim_id=claim_id,
                    claim_type="conditional_causal",
                    subject=str(text_receipt["question"].get("source_service") or "source_service"),
                    predicate="restart_destabilization_risk",
                    object=str(text_receipt["question"].get("target_service") or "target_service"),
                    status=claim_status,
                    confidence_class="rule_proven" if claim_status is ProofClaimStatus.SUPPORTED else claim_status.value,
                    fact_refs=component_fact_digests or (text_receipt["receipt_digest"],),
                    rule_ref=str(dict(text_receipt.get("component_fact_digests") or {}).get("causal_rule") or ""),
                    policy_ref=str(dict(text_receipt.get("component_fact_digests") or {}).get("restart_policy") or ""),
                    snapshot_ref=str(sha256_digest(tuple(text_receipt.get("component_evidence_digests") or ()))),
                    metadata={
                        "text_receipt_digest": text_receipt["receipt_digest"],
                        "visual_receipt_digests": visual_receipt_digests,
                        "residual_scopes": tuple(
                            str(payload.get("residual_scope") or "")
                            for payload in [
                                text_receipt.get("residual_payload") or {},
                                *(receipt.get("residual_payload") or {} for receipt in visual_receipts.values()),
                            ]
                            if payload
                        ),
                    },
                ),
            ),
            world_snapshot_digest=sha256_digest({
                "text_evidence": tuple(text_receipt.get("component_evidence_digests") or ()),
                "visual_receipts": visual_receipt_digests,
                "temporal_evidence": dict(payload.get("temporal_evidence") or {}) if isinstance(payload.get("temporal_evidence"), Mapping) else {},
            }),
            policy_digest=sha256_digest({
                "cross_modal_policy": "sibling_views_from_proof_graph_v1",
                "render_authority": "render_only",
                "provider_policy": "residual_only",
            }),
            capability_fact_digests=component_fact_digests,
            causal_rule_digests=tuple(
                digest for name, digest in dict(text_receipt.get("component_fact_digests") or {}).items()
                if "rule" in str(name)
            ),
        )
        text_view = TextProofView(
            view_id="text-view:restart-risk:" + text_receipt["receipt_digest"].removeprefix("sha256:")[:16],
            text_output_digest=sha256_digest(text_receipt.get("answer") or {}),
            claim_refs=(claim_id,),
        )
        visual_view = VisualProofView(
            view_id="visual-view:restart-risk:" + visual_digest.removeprefix("sha256:")[:16],
            scene_capsule_digest=str(dict(visual_receipts.get("status_card", {}).get("component_fact_digests") or {}).get("scene_capsule") or visual_digest),
            rendered_visual_digest=visual_digest,
            asset_manifest_digest=str(dict(visual_receipts.get("status_card", {}).get("component_fact_digests") or {}).get("asset_manifest") or visual_digest),
            layout_engine_digest=sha256_digest({"engine": "beast.visual-layout-proof-view.v1"}),
            primitives=(
                VisualProofPrimitive(
                    primitive_id="primitive:risk-edge:" + claim_id.rsplit(":", 1)[-1],
                    primitive="risk_edge",
                    claim_ref=claim_id,
                    evidence_state=claim_status,
                    metadata={"visual_treatment": _visual_treatment_for_claim_status(claim_status)},
                ),
            ),
        )
        return {"proof_graph": graph, "text_view": text_view, "visual_view": visual_view}

    def generation_provider_adapter_report(self, *, approval_receipt: str = "") -> dict[str, Any]:
        self.assert_production_composition()
        return self.generation_provider_adapters.inventory(approval_receipt=approval_receipt)

    def execute_generation_provider(
        self,
        *,
        provider_id: str,
        modality: str,
        mode: str,
        prompt: str,
        model: str = "",
        approval_receipt: str = "",
        metadata: Mapping[str, Any] | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        self.assert_production_composition()
        if not str(prompt or "").strip():
            raise ValueError("generation provider execution requires prompt")
        active_modality = GenerationModality(modality)
        active_mode = ProviderMode(mode)
        prompt_digest = sha256_digest({"prompt": str(prompt)})
        request = GenerationProviderRequest(
            request_id=request_id or "generation-provider:" + prompt_digest.removeprefix("sha256:")[:24],
            modality=active_modality,
            provider_id=str(provider_id or "").strip(),
            mode=active_mode,
            prompt_digest=prompt_digest,
            model=str(model or ""),
            approval_receipt=str(approval_receipt or ""),
            metadata={**dict(metadata or {}), "prompt": str(prompt)},
        )
        result = self.generation_provider_adapters.execute(request).to_dict()
        if active_modality is GenerationModality.TEXT:
            result["output_text"] = base64.b64decode(result["output_base64"]).decode("utf-8", errors="replace")
        return result

    def revoke_operator_language_semantic_crystal(self, crystal_id: str, *, reason: str) -> SemanticCrystalRecord:
        self.assert_production_composition()
        record = self.semantic_crystal_registry.revoke(crystal_id, reason=reason)
        receipt_digest = sha256_digest({
            "event": "semantic_crystal_revoked",
            "crystal_id": record.crystal.crystal_id,
            "reason": reason,
            "record_digest": record.record_digest,
        })
        self._record_capability_learning(
            event_type="revoked",
            capability_type="semantic_crystal",
            capability_id=record.crystal.crystal_id,
            lifecycle_state=record.lifecycle_state.value,
            authority="read_verified",
            evidence_digest=record.record_digest,
            receipt_digest=receipt_digest,
            refusal_reason=reason,
            metadata={"semantic_key_digest": record.semantic_key_digest},
        )
        return record

    def demote_visual_asset(self, asset_id: str, *, reason: str) -> VisualPromotedAssetRecord:
        self.assert_production_composition()
        if not str(asset_id or "").strip() or not str(reason or "").strip():
            raise ValueError("visual asset demotion requires asset_id and reason")
        selected_key = ""
        selected: VisualPromotedAssetRecord | None = None
        for promotion_key, record in self.promoted_visual_assets.items():
            if record.asset.asset_id == asset_id:
                selected_key = promotion_key
                selected = record
                break
        if selected is None:
            raise KeyError(f"unknown visual asset: {asset_id}")
        del self.promoted_visual_assets[selected_key]
        self._visual_asset_observations.pop(selected_key, None)
        self._visual_asset_observation_digests.pop(selected_key, None)
        self._visual_asset_observation_embeddings.pop(selected_key, None)
        self._visual_asset_observation_receipts.pop(selected_key, None)
        self._visual_asset_observation_equivalence_receipts.pop(selected_key, None)
        self._visual_asset_observation_lanes.pop(selected_key, None)
        self._persist_promoted_visual_assets()
        receipt_digest = sha256_digest({
            "event": "visual_asset_demoted",
            "asset_id": selected.asset.asset_id,
            "promotion_key": selected.promotion_key,
            "reason": reason,
            "record_digest": selected.record_digest,
        })
        node = self.evidence_graph.add("visual_asset_demoted", {
            "observed_at": utc_now_iso(),
            "asset_id": selected.asset.asset_id,
            "promotion_key": selected.promotion_key,
            "record_digest": selected.record_digest,
            "reason": reason,
            "receipt_digest": receipt_digest,
        })
        self._record_capability_learning(
            event_type="demoted",
            capability_type="visual_asset",
            capability_id=selected.asset.asset_id,
            lifecycle_state="demoted",
            authority="render_only",
            evidence_digest=node.node_id,
            receipt_digest=receipt_digest,
            refusal_reason=reason,
            metadata={"promotion_key": selected.promotion_key, "asset_digest": selected.asset.digest},
        )
        return selected

    def ingest_reduction_evidence(
        self,
        source_system: str,
        receipt: Mapping[str, Any],
        *,
        interface: str = "api",
        claim_class: str | None = None,
    ) -> dict[str, Any]:
        """Normalize external reduction evidence into the production scorecard.

        The raw receipt is content-digested but not copied into the evidence
        graph.  Only a bounded projection is stored so Sensorium/Commons/G9
        inputs do not accidentally publish prompt or workspace payloads.
        """
        self.assert_production_composition()
        source = str(source_system or receipt.get("source_system") or "").strip()
        if not source:
            raise ValueError("source_system is required")
        raw = dict(receipt)
        self._reject_unbounded_reduction_payload(raw)
        projection = self._normalize_reduction_evidence(source, raw, claim_class=claim_class)
        existing = self._existing_normalized_reduction_node(projection["projection_digest"])
        if existing is not None:
            return {**projection, "evidence_node_id": existing.node_id, "duplicate": True}
        node = self.evidence_graph.add("normalized_reduction_evidence", {
            "ingested_at": utc_now_iso(),
            "interface": interface,
            **projection,
        })
        result = {**projection, "evidence_node_id": node.node_id, "duplicate": False}
        self._record_normalized_reduction_capability_learning(result, raw)
        self._last_receipts["normalized_reduction_evidence"] = node.node_id
        self._counters[f"reduction_evidence.{source}.ingested"] += 1
        return result

    def discover_reduction_evidence(
        self,
        *,
        paths: tuple[str | Path, ...] | None = None,
        max_files: int = 200,
        max_bytes: int = 2 * 1024 * 1024,
        interface: str = "api",
    ) -> dict[str, Any]:
        """Discover repo-local JSON evidence and ingest recognized receipts."""
        self.assert_production_composition()
        if max_files <= 0 or max_files > 2000:
            raise ValueError("max_files must be between 1 and 2000")
        if max_bytes <= 0 or max_bytes > 10 * 1024 * 1024:
            raise ValueError("max_bytes must be between 1 and 10485760")
        roots = self._reduction_discovery_roots(paths)
        candidates = self._reduction_discovery_candidates(roots, max_files=max_files)
        ingested: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        source_counts: Counter[str] = Counter()
        duplicate_count = 0
        for path in candidates:
            rel = self._display_path(path)
            try:
                stat = path.stat()
                if stat.st_size > max_bytes:
                    skipped.append({"path": rel, "reason": "file_too_large", "size_bytes": stat.st_size})
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, Mapping):
                    skipped.append({"path": rel, "reason": "json_root_not_object"})
                    continue
                source = self._detect_reduction_evidence_source(path, data)
                if source is None:
                    skipped.append({"path": rel, "reason": "unrecognized_reduction_evidence"})
                    continue
                result = self.ingest_reduction_evidence(source, data, interface=interface)
                duplicate = bool(result.get("duplicate"))
                duplicate_count += int(duplicate)
                source_counts[str(result["source_system"])] += int(not duplicate)
                ingested.append({
                    "path": rel,
                    "source_system": result["source_system"],
                    "claim_class": result["claim_class"],
                    "verified": result["verified"],
                    "projection_digest": result["projection_digest"],
                    "evidence_node_id": result["evidence_node_id"],
                    "duplicate": duplicate,
                })
            except (PermissionError, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                skipped.append({"path": rel, "reason": type(exc).__name__, "detail": str(exc)[:240]})
        self._counters["reduction_evidence.discovery_runs"] += 1
        report = {
            "beast_object_type": "reduction_evidence_discovery_report",
            "version": "1.0",
            "roots": [self._display_path(root) for root in roots],
            "files_considered": len(candidates),
            "ingested": ingested,
            "ingested_count": sum(1 for item in ingested if not item["duplicate"]),
            "duplicate_count": duplicate_count,
            "skipped": skipped,
            "skipped_count": len(skipped),
            "source_counts": dict(sorted(source_counts.items())),
            "max_files": max_files,
            "max_bytes": max_bytes,
        }
        report["report_digest"] = sha256_digest(report)
        return report

    @staticmethod
    def _reject_unbounded_reduction_payload(value: Mapping[str, Any]) -> None:
        forbidden: list[str] = []

        def walk(item: Any, path: str) -> None:
            if isinstance(item, Mapping):
                for key, child in item.items():
                    lowered = str(key).lower()
                    if lowered in {
                        "raw_prompt", "raw_prompts", "prompt_text",
                        "secret", "shared_secret", "secret_key", "private_key", "capability_secret",
                        "payload_base64", "raw_payload", "tensor_payload",
                    }:
                        forbidden.append(f"{path}.{key}")
                    if "private_key" in lowered or "capability_secret" in lowered or "shared_secret" in lowered:
                        forbidden.append(f"{path}.{key}")
                    walk(child, f"{path}.{key}")
            elif isinstance(item, (list, tuple)):
                for index, child in enumerate(item):
                    walk(child, f"{path}[{index}]")

        walk(value, "$")
        if forbidden:
            raise PermissionError("reduction evidence contains forbidden raw/private fields: " + ", ".join(sorted(set(forbidden))))

    def _reduction_discovery_roots(self, paths: tuple[str | Path, ...] | None) -> tuple[Path, ...]:
        repo_root = Path(__file__).resolve().parents[3].resolve()
        allowed_bases = (repo_root, self.root.resolve())
        requested = paths or (
            repo_root / "evidence",
            repo_root / "docs" / "evidence",
            self.root / "evidence",
        )
        roots: list[Path] = []
        for item in requested:
            raw = Path(item)
            path = (repo_root / raw).resolve() if not raw.is_absolute() else raw.resolve()
            if not any(path == base or base in path.parents for base in allowed_bases):
                raise PermissionError("reduction evidence discovery paths must stay inside the BEAST workspace or compute-plane state root")
            if path.exists():
                roots.append(path)
        return tuple(dict.fromkeys(roots))

    @staticmethod
    def _reduction_discovery_candidates(roots: tuple[Path, ...], *, max_files: int) -> tuple[Path, ...]:
        candidates: list[Path] = []
        for root in roots:
            if root.is_symlink():
                continue
            if root.is_file() and root.suffix == ".json":
                candidates.append(root)
            elif root.is_dir():
                candidates.extend(path for path in root.rglob("*.json") if path.is_file() and not path.is_symlink())
        return tuple(sorted(dict.fromkeys(candidates), key=lambda item: str(item))[:max_files])

    @staticmethod
    def _detect_reduction_evidence_source(path: Path, data: Mapping[str, Any]) -> str | None:
        object_type = str(data.get("beast_object_type") or "").lower()
        path_text = str(path).lower()
        if object_type == "normalized_reduction_evidence":
            return None
        if (
            "grand_closure_g9" in object_type
            or "grand-closure-g9" in path.name.lower()
            or ("grand_closure" in path_text and isinstance(data.get("validation"), Mapping))
        ):
            return "grand_closure"
        if (
            object_type == "compute_reduction_receipt"
            or (isinstance(data.get("local_seal"), Mapping) and isinstance(data.get("displacement"), Mapping))
        ):
            return "commons_spaces"
        if (
            object_type == "forge_kv_episode_economics"
            or object_type.startswith("forge_kv_")
            or ("prefill_displaced" in data and "source_context_digest" in data and "observed_context_digest" in data)
            or "forge_kv" in path_text and "prompt_tokens_avoided" in data
            or "forge_kv" in path_text and data.get("validated") is True
        ):
            return "forge_kv_prompt_cache"
        if (
            "sensorium" in object_type and ("episode_hash" in data or "mission_id" in data)
            or str(data.get("schema") or "").startswith("beast.sensorium.")
            or str(data.get("claim") or "").startswith("learned_bounded_disk_cleanup")
            or isinstance(data.get("crystal"), Mapping) and str(data.get("claim") or "").startswith("learned_bounded_")
        ):
            return "sensorium"
        return None

    def _existing_normalized_reduction_node(self, projection_digest: str) -> Any | None:
        for node in self.evidence_graph.query("normalized_reduction_evidence"):
            if node.receipt.get("projection_digest") == projection_digest:
                return node
        return None

    @staticmethod
    def _display_path(path: Path) -> str:
        repo_root = Path(__file__).resolve().parents[3].resolve()
        try:
            return str(path.resolve().relative_to(repo_root))
        except ValueError:
            return str(path)

    def _normalize_reduction_evidence(
        self,
        source_system: str,
        receipt: Mapping[str, Any],
        *,
        claim_class: str | None,
    ) -> dict[str, Any]:
        allowed = {"observed", "estimated", "route_selection_only", "hypothesis"}
        requested = str(claim_class or receipt.get("claim_class") or "").strip()
        if requested and requested not in allowed:
            raise ValueError("claim_class must be observed, estimated, route_selection_only, or hypothesis")
        source = self._canonical_reduction_source(source_system)
        if source == "forge_kv_prompt_cache":
            return self._normalize_forge_kv_reduction(receipt, requested)
        if source == "commons_spaces":
            return self._normalize_commons_space_reduction(receipt, requested)
        if source == "grand_closure":
            return self._normalize_grand_closure_reduction(receipt, requested)
        if source == "sensorium":
            return self._normalize_sensorium_reduction(receipt, requested)
        selected = requested or "hypothesis"
        return self._reduction_projection(
            source_system=source,
            original_receipt_digest=sha256_digest(receipt),
            claim_class=selected,
            verified=False,
            provider_calls_avoided=0,
            tokens_avoided_observed=0,
            notes=("unrecognized source_system ingested as hypothesis unless a source-specific verifier is added",),
        )

    @staticmethod
    def _canonical_reduction_source(source_system: str) -> str:
        normalized = source_system.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "forge_kv": "forge_kv_prompt_cache",
            "forge_kv_cache": "forge_kv_prompt_cache",
            "forge_kv_prompt_cache": "forge_kv_prompt_cache",
            "commons": "commons_spaces",
            "commons_space": "commons_spaces",
            "compute_space": "commons_spaces",
            "commons_spaces": "commons_spaces",
            "g9": "grand_closure",
            "grand_closure_g9": "grand_closure",
            "grand_closure": "grand_closure",
            "sensorium": "sensorium",
            "sensorium_physical_crystal": "sensorium",
            "sensorium_disk_pressure": "sensorium",
            "sensorium_disk_cleanup": "sensorium",
        }
        return aliases.get(normalized, normalized)

    def _normalize_forge_kv_reduction(self, receipt: Mapping[str, Any], requested: str) -> dict[str, Any]:
        object_type = str(receipt.get("beast_object_type") or "")
        if object_type == "forge_kv_ml_kem_transport_receipt":
            validation = validate_ml_kem_bound_transport_receipt(receipt)
            verified = bool(validation.get("valid"))
            selected = requested or ("route_selection_only" if verified else "hypothesis")
            if selected == "observed":
                selected = "route_selection_only"
            kv_transfer = receipt.get("kv_transfer") if isinstance(receipt.get("kv_transfer"), Mapping) else {}
            ml_kem = receipt.get("ml_kem") if isinstance(receipt.get("ml_kem"), Mapping) else {}
            return self._reduction_projection(
                source_system="forge_kv_prompt_cache",
                original_receipt_digest=sha256_digest(receipt),
                claim_class=selected,
                verified=verified,
                provider_calls_avoided=0,
                tokens_avoided_observed=0,
                engine_specific_proof=False,
                portable_raw_kv=False,
                forge_kv_boundary="ml_kem_bound_network_transport",
                authority=FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY,
                transport_verified=verified,
                bytes_transferred_verified=int(receipt.get("bytes_transferred_verified") or 0) if verified else 0,
                payload_kind=str(receipt.get("payload_kind") or ""),
                block_id=str(kv_transfer.get("block_id") or ""),
                transfer_id=str(kv_transfer.get("transfer_id") or ""),
                engine=str(kv_transfer.get("engine") or ""),
                target_engine=str(kv_transfer.get("target_engine") or ""),
                tensor_payload_sha256=str(kv_transfer.get("tensor_payload_sha256") or ""),
                tensor_payload_format=str(kv_transfer.get("tensor_payload_format") or ""),
                ml_kem_algorithm=str(ml_kem.get("algorithm") or ""),
                ml_kem_node_count=int(ml_kem.get("node_count") or 0),
                ml_kem_confirmed_count=int(ml_kem.get("confirmed_count") or 0),
                ml_kem_pairwise_transcript_edges=int(ml_kem.get("pairwise_transcript_edges") or 0),
                validation_errors=tuple(validation.get("errors") or ()),
                notes=(
                    "ML-KEM-confirmed peer session plus checksum-bound engine-native KV transfer verified; no token savings, portable KV reuse, or provider-call avoidance is counted",
                ),
            )
        if object_type == "forge_kv_llamacpp_prompt_cache_proof":
            trials = tuple(item for item in (receipt.get("trials") or ()) if isinstance(item, Mapping))
            token_savings: list[int] = []
            latency_savings_ms: list[float] = []
            for trial in trials:
                baseline = trial.get("baseline") if isinstance(trial.get("baseline"), Mapping) else {}
                cached = trial.get("cached") if isinstance(trial.get("cached"), Mapping) else {}
                token_savings.append(max(0, int(baseline.get("prompt_n") or 0) - int(cached.get("prompt_n") or 0)))
                latency_savings_ms.append(max(0.0, float(baseline.get("prompt_ms") or 0.0) - float(cached.get("prompt_ms") or 0.0)))
            verified = bool(receipt.get("validated") is True and trials and all(value > 0 for value in token_savings))
            selected = requested or ("observed" if verified else "hypothesis")
            tokens = sum(token_savings) if selected == "observed" and verified else 0
            return self._reduction_projection(
                source_system="forge_kv_prompt_cache",
                original_receipt_digest=sha256_digest(receipt),
                claim_class=selected if verified or selected != "observed" else "hypothesis",
                verified=verified,
                provider_calls_avoided=0,
                tokens_avoided_observed=tokens,
                engine_specific_proof=verified,
                portable_raw_kv=bool(receipt.get("portable_raw_kv")),
                forge_kv_boundary="engine_local_prompt_cache",
                engine=str(receipt.get("engine") or "llama.cpp"),
                prefix_digest=str(receipt.get("prefix_digest") or ""),
                trial_count=len(trials),
                prompt_eval_ms_avoided_observed=sum(latency_savings_ms) if selected == "observed" and verified else 0.0,
                notes=(
                    "Local llama.cpp prompt-cache proof counted as engine-local prefill work avoided; no raw KV export, portable KV transport, or provider-call avoidance is claimed",
                ),
            )
        if object_type == "forge_kv_llamacpp_restart_boundary_proof":
            before = receipt.get("before_restart") if isinstance(receipt.get("before_restart"), Mapping) else {}
            baseline = before.get("baseline") if isinstance(before.get("baseline"), Mapping) else {}
            warm = before.get("warm_cache") if isinstance(before.get("warm_cache"), Mapping) else {}
            after = receipt.get("after_restart") if isinstance(receipt.get("after_restart"), Mapping) else {}
            warm_tokens_saved = max(0, int(baseline.get("prompt_n") or 0) - int(warm.get("prompt_n") or 0))
            restart_reset = "cache_n" in after and int(after.get("cache_n") or 0) == 0
            verified = bool(receipt.get("validated") is True and warm_tokens_saved > 0 and restart_reset)
            selected = requested or "route_selection_only"
            if selected == "observed":
                selected = "route_selection_only"
            return self._reduction_projection(
                source_system="forge_kv_prompt_cache",
                original_receipt_digest=sha256_digest(receipt),
                claim_class=selected,
                verified=verified,
                provider_calls_avoided=0,
                tokens_avoided_observed=0,
                engine_specific_proof=verified,
                portable_raw_kv=bool(receipt.get("portable_raw_kv")),
                forge_kv_boundary="engine_local_restart_resets_prompt_cache",
                engine=str(receipt.get("engine") or "llama.cpp"),
                prefix_digest=str(receipt.get("prefix_digest") or ""),
                warm_tokens_saved_before_restart=warm_tokens_saved,
                restart_cache_reset=restart_reset,
                notes=(
                    "Restart-boundary proof teaches cache invalidation/staleness; savings are not counted as durable or cross-node without native restore proof",
                ),
            )
        tokens = int(receipt.get("prompt_tokens_avoided") or 0)
        ns_avoided = int(receipt.get("prompt_eval_ns_avoided") or 0)
        verified_restore = (
            receipt.get("prefill_displaced") is True
            and receipt.get("continuation_equivalent") is True
            and receipt.get("restored") is True
            and str(receipt.get("authority") or "") == "verify_only"
            and bool(str(receipt.get("verifier_id") or "").strip())
            and str(receipt.get("source_context_digest") or "") == str(receipt.get("observed_context_digest") or "")
            and tokens > 0
            and ns_avoided > 0
        )
        metadata_only = (
            str(receipt.get("beast_object_type") or "") == "forge_kv_episode_economics"
            and receipt.get("paired_baseline_present") is True
            and str(receipt.get("authority") or "") == "observation_only"
        )
        selected = requested or ("observed" if verified_restore else "route_selection_only" if metadata_only else "hypothesis")
        observed_tokens = tokens if selected == "observed" and verified_restore else 0
        return self._reduction_projection(
            source_system="forge_kv_prompt_cache",
            original_receipt_digest=sha256_digest(receipt),
            claim_class=selected if selected != "observed" or verified_restore else "route_selection_only",
            verified=verified_restore,
            provider_calls_avoided=0,
            tokens_avoided_observed=observed_tokens,
            engine_specific_proof=verified_restore,
            notes=(
                "Native context restore verifier proved prompt prefill displacement"
                if verified_restore
                else "Forge KV metadata retained as route-selection/observation evidence; no token savings counted without native restore proof"
            ,),
        )

    def _normalize_commons_space_reduction(self, receipt: Mapping[str, Any], requested: str) -> dict[str, Any]:
        validation = validate_reduction_receipt(dict(receipt)) if receipt.get("local_seal") else {
            "valid": bool(receipt.get("receipt_validation", {}).get("valid")),
        }
        verifier = receipt.get("verifier") if isinstance(receipt.get("verifier"), Mapping) else {}
        provenance = receipt.get("provenance") if isinstance(receipt.get("provenance"), Mapping) else {}
        optimized = receipt.get("optimized_route") if isinstance(receipt.get("optimized_route"), Mapping) else {}
        displacement = receipt.get("displacement") if isinstance(receipt.get("displacement"), Mapping) else {}
        local_reproduction = any((
            receipt.get("local_reproduction_verified") is True,
            provenance.get("local_reproduction_verified") is True,
            optimized.get("local_reproduction_verified") is True,
            optimized.get("reproduced_locally") is True,
        ))
        promoted = any((
            receipt.get("promotion_verified") is True,
            provenance.get("promotion_verified") is True,
            optimized.get("promotion_verified") is True,
        ))
        verified = bool(validation.get("valid") and verifier.get("passed") is True and (local_reproduction or promoted))
        selected = requested or ("observed" if verified else "hypothesis")
        calls = int(displacement.get("provider_calls_avoided") or receipt.get("provider_calls_avoided") or 0)
        tokens = int(displacement.get("provider_tokens_avoided") or receipt.get("provider_tokens_avoided") or 0)
        if selected != "observed" or not verified:
            calls = 0
            tokens = 0
            selected = "hypothesis" if selected == "observed" else selected
        return self._reduction_projection(
            source_system="commons_spaces",
            original_receipt_digest=sha256_digest(receipt),
            claim_class=selected,
            verified=verified,
            provider_calls_avoided=calls,
            tokens_avoided_observed=tokens,
            local_reproduction_verified=local_reproduction,
            promotion_verified=promoted,
            notes=(
                "Commons Space counted only after local reproduction/promotion and receipt seal verification"
                if verified
                else "Commons Space retained as hypothesis until local reproduction or promotion verifies it"
            ,),
        )

    def _normalize_grand_closure_reduction(self, receipt: Mapping[str, Any], requested: str) -> dict[str, Any]:
        validation = receipt.get("validation") if isinstance(receipt.get("validation"), Mapping) else {}
        required = tuple(str(item) for item in (validation.get("required_gates") or receipt.get("required_gates") or ()))
        present = tuple(str(item) for item in (validation.get("present_gates") or receipt.get("present_gates") or ()))
        missing = tuple(str(item) for item in (validation.get("missing_gates") or receipt.get("missing_gates") or ()))
        valid = bool(validation.get("valid") if validation else receipt.get("bundle_valid"))
        selected = requested or "route_selection_only"
        if selected == "observed":
            selected = "route_selection_only"
        return self._reduction_projection(
            source_system="grand_closure",
            original_receipt_digest=sha256_digest(receipt),
            claim_class=selected,
            verified=valid,
            provider_calls_avoided=0,
            tokens_avoided_observed=0,
            g9_bundle_health={
                "required_gates": required,
                "present_gates": present,
                "missing_gates": missing,
                "valid": valid,
            },
            notes=("Grand Closure is lifecycle/economics evidence; it does not count as provider execution savings without paired execution evidence",),
        )

    def _normalize_sensorium_reduction(self, receipt: Mapping[str, Any], requested: str) -> dict[str, Any]:
        schema = str(receipt.get("schema") or "")
        claim = str(receipt.get("claim") or "")
        crystal = receipt.get("crystal") if isinstance(receipt.get("crystal"), Mapping) else {}
        generalization = receipt.get("generalization") if isinstance(receipt.get("generalization"), Mapping) else {}
        replay = receipt.get("replay") if isinstance(receipt.get("replay"), Mapping) else {}
        safety = receipt.get("safety") if isinstance(receipt.get("safety"), Mapping) else {}
        is_disk_pressure = (
            schema == "beast.sensorium.disk-cleanup-evidence.v1"
            or claim == "learned_bounded_disk_cleanup_candidate"
            or crystal.get("identity") == "crystal:sensorium-disk-cleanup:v1"
        )
        if is_disk_pressure:
            replay_verified = bool(
                replay.get("promotion_eligible") is True
                and int(replay.get("verified_variants") or 0) == len(replay.get("variant_receipts") or ())
                and all(bool(item.get("verified")) for item in (replay.get("variant_receipts") or ()) if isinstance(item, Mapping))
            )
            production_allowed = bool(receipt.get("production_promotion_allowed") is True)
            verified = replay_verified and bool(crystal.get("artifact_digest"))
            selected = requested or "route_selection_only"
            if selected == "observed":
                selected = "route_selection_only"
            return self._reduction_projection(
                source_system="sensorium",
                original_receipt_digest=sha256_digest(receipt),
                claim_class=selected,
                verified=verified,
                provider_calls_avoided=0,
                tokens_avoided_observed=0,
                sensorium_capability="disk_pressure_governed_cleanup",
                crystal_id=str(crystal.get("identity") or generalization.get("candidate_id") or "crystal:sensorium-disk-cleanup:v1"),
                typed_artifact_digest=str(crystal.get("artifact_digest") or ""),
                replay_verified_variants=int(replay.get("verified_variants") or 0),
                replay_promotion_eligible=bool(replay.get("promotion_eligible")),
                production_promotion_allowed=production_allowed,
                manifest_identity_fields=tuple(str(item) for item in (safety.get("manifest_identity_fields") or ())),
                notes=(
                    "Sensorium disk-pressure proof is resource-governance learning; replay eligibility is counted, but destructive cleanup remains non-production until explicit isolation/approval gates allow it",
                ),
            )
        verified = bool(receipt.get("verified") is True and receipt.get("episode_hash"))
        selected = requested or ("route_selection_only" if verified else "hypothesis")
        if selected == "observed":
            selected = "route_selection_only"
        return self._reduction_projection(
            source_system="sensorium",
            original_receipt_digest=sha256_digest(receipt),
            claim_class=selected,
            verified=verified,
            provider_calls_avoided=0,
            tokens_avoided_observed=0,
            notes=("Sensorium evidence describes recurrence/provenance; production mission displacement receipts count execution savings separately",),
        )

    def _record_normalized_reduction_capability_learning(
        self,
        projection: Mapping[str, Any],
        raw_receipt: Mapping[str, Any],
    ) -> None:
        source = str(projection.get("source_system") or "")
        evidence_digest = str(projection.get("evidence_node_id") or "")
        receipt_digest = str(projection.get("projection_digest") or "")
        if not evidence_digest.startswith("sha256:") or not receipt_digest.startswith("sha256:"):
            return
        if source == "sensorium":
            capability = str(projection.get("sensorium_capability") or "")
            if capability == "disk_pressure_governed_cleanup":
                state = (
                    "promotion_blocked_destructive"
                    if projection.get("production_promotion_allowed") is False
                    else "replay_eligible"
                    if projection.get("replay_promotion_eligible") is True
                    else "observed"
                )
                self._record_capability_learning(
                    event_type="blocked" if state == "promotion_blocked_destructive" else "observed",
                    capability_type="sensorium_physical_crystal",
                    capability_id=str(projection.get("crystal_id") or "crystal:sensorium-disk-cleanup:v1"),
                    lifecycle_state=state,
                    authority="resource_governance_only",
                    evidence_digest=evidence_digest,
                    receipt_digest=receipt_digest,
                    fresh_work_units=int(projection.get("replay_verified_variants") or 0),
                    refusal_reason="destructive_cleanup_requires_explicit_production_gate" if state == "promotion_blocked_destructive" else "",
                    metadata={
                        "sensorium_capability": capability,
                        "typed_artifact_digest": str(projection.get("typed_artifact_digest") or ""),
                        "claim_class": str(projection.get("claim_class") or ""),
                        "manifest_identity_fields": tuple(projection.get("manifest_identity_fields") or ()),
                    },
                )
            return
        if source == "forge_kv_prompt_cache":
            object_type = str(raw_receipt.get("beast_object_type") or "")
            prefix = str(projection.get("prefix_digest") or raw_receipt.get("prefix_digest") or "")
            boundary = str(projection.get("forge_kv_boundary") or "native_context_restore")
            if boundary == "ml_kem_bound_network_transport":
                transfer_id = str(projection.get("transfer_id") or "")
                block_id = str(projection.get("block_id") or "")
                capability_id = "forge-kv-mlkem:" + (
                    transfer_id[:24]
                    if transfer_id
                    else block_id[:24]
                    if block_id
                    else sha256_digest(raw_receipt).removeprefix("sha256:")[:24]
                )
                state = "transport_verified" if projection.get("verified") is True else "transport_hypothesis"
                event_type = "observed"
                refusal = "" if projection.get("verified") is True else "ml_kem_transport_validation_failed"
                authority = FORGE_KV_ML_KEM_TRANSPORT_AUTHORITY
            else:
                capability_id = "forge-kv:" + (prefix.removeprefix("sha256:")[:24] if prefix.startswith("sha256:") else sha256_digest(raw_receipt).removeprefix("sha256:")[:24])
                authority = "engine_local_prompt_cache_only"
            if boundary == "engine_local_restart_resets_prompt_cache":
                state = "restart_boundary_observed"
                event_type = "blocked"
                refusal = "prompt_cache_not_durable_across_restart_without_native_restore"
            elif boundary == "ml_kem_bound_network_transport":
                pass
            elif projection.get("claim_class") == "observed":
                state = "observed_engine_local"
                event_type = "observed"
                refusal = ""
            else:
                state = "hypothesis"
                event_type = "observed"
                refusal = ""
            self._record_capability_learning(
                event_type=event_type,
                capability_type="forge_kv_node",
                capability_id=capability_id,
                lifecycle_state=state,
                authority=authority,
                evidence_digest=evidence_digest,
                receipt_digest=receipt_digest,
                provider_calls_used=0,
                provider_calls_avoided=0,
                fresh_work_units=int(projection.get("trial_count") or 1),
                reuse_hits=int(projection.get("trial_count") or 0) if projection.get("claim_class") == "observed" else 0,
                refusal_reason=refusal,
                metadata={
                    "object_type": object_type,
                    "engine": str(projection.get("engine") or raw_receipt.get("engine") or ""),
                    "prefix_digest": prefix,
                    "boundary": boundary,
                    "tokens_avoided_observed": int(projection.get("tokens_avoided_observed") or 0),
                    "portable_raw_kv": bool(projection.get("portable_raw_kv")),
                    "claim_class": str(projection.get("claim_class") or ""),
                    "bytes_transferred_verified": int(projection.get("bytes_transferred_verified") or 0),
                    "transport_verified": bool(projection.get("transport_verified")),
                    "ml_kem_algorithm": str(projection.get("ml_kem_algorithm") or ""),
                    "ml_kem_node_count": int(projection.get("ml_kem_node_count") or 0),
                    "ml_kem_confirmed_count": int(projection.get("ml_kem_confirmed_count") or 0),
                },
            )

    @staticmethod
    def _reduction_projection(
        *,
        source_system: str,
        original_receipt_digest: str,
        claim_class: str,
        verified: bool,
        provider_calls_avoided: int,
        tokens_avoided_observed: int,
        notes: tuple[str, ...],
        **extra: Any,
    ) -> dict[str, Any]:
        if claim_class not in {"observed", "estimated", "route_selection_only", "hypothesis"}:
            raise ValueError("invalid normalized reduction claim_class")
        projection = {
            "beast_object_type": "normalized_reduction_evidence",
            "version": "1.0",
            "source_system": source_system,
            "original_receipt_digest": original_receipt_digest,
            "claim_class": claim_class,
            "verified": bool(verified),
            "provider_calls_avoided": max(0, int(provider_calls_avoided)) if claim_class == "observed" else 0,
            "tokens_avoided_observed": max(0, int(tokens_avoided_observed)) if claim_class == "observed" else 0,
            "notes": notes,
            **extra,
        }
        projection["projection_digest"] = sha256_digest(projection)
        return projection


_plane: ComputePlane | None = None
_plane_lock = threading.Lock()


def get_compute_plane() -> ComputePlane:
    global _plane
    if _plane is None:
        with _plane_lock:
            if _plane is None:
                _plane = ComputePlane()
    return _plane
