"""DIO Constitutional Extensions.

This module is intentionally a layer above the frozen DIO core.  It does not
change Phase-6.2's deterministic-intelligence claim; it adds machine-readable
constitutional checks for whether a capability may safely keep speaking,
composing, or asking for re-entry.

The first extension slice covers:

* capability/effect containment;
* evidence-strength sufficiency;
* cadence and trusted-time applicability;
* authority-pollution detection;
* dependency-aware revocation;
* counterfactual/minimal-proof receipts;
* lawful re-entry after refusal.

Hybrid post-quantum signatures and full formal Commons liveness are recorded as
explicit deferred extensions so this module cannot launder future work into a
current green receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.kernel.compute.deterministic_intelligence import (
    canonical_json,
    require_digest,
    sha256_bytes,
    sha256_digest,
)
from app.kernel.dai.contracts import parse_iso_datetime


CONSTITUTIONAL_EXTENSIONS_VERSION = "2026-08-04.phase6.4.constitutional-extensions.v1"
CONSTITUTIONAL_EXTENSIONS_IMPLEMENTATION_DIGEST = sha256_bytes(Path(__file__).read_bytes())


class EvidenceMode(str, Enum):
    MAPPING_ONLY = "MAPPING_ONLY"
    SYNTHETIC_AUDIT = "SYNTHETIC_AUDIT"
    CORRELATION = "CORRELATION"
    DEDUCTIVE_PREVENTION = "DEDUCTIVE_PREVENTION"
    KERNEL_DENIAL = "KERNEL_DENIAL"
    LAB_PCAP = "LAB_PCAP"
    DIRECT_DETECTION = "DIRECT_DETECTION"
    DIRECT_OBSERVED = "DIRECT_OBSERVED"
    PRODUCTION_PCAP = "PRODUCTION_PCAP"


EVIDENCE_STRENGTH: dict[EvidenceMode, int] = {
    EvidenceMode.MAPPING_ONLY: 10,
    EvidenceMode.SYNTHETIC_AUDIT: 20,
    EvidenceMode.CORRELATION: 30,
    EvidenceMode.DEDUCTIVE_PREVENTION: 40,
    EvidenceMode.KERNEL_DENIAL: 50,
    EvidenceMode.LAB_PCAP: 60,
    EvidenceMode.DIRECT_DETECTION: 70,
    EvidenceMode.DIRECT_OBSERVED: 80,
    EvidenceMode.PRODUCTION_PCAP: 90,
}


class ApplicabilityAction(str, Enum):
    ANSWER = "answer"
    REFUSE = "refuse"
    REOBSERVE = "reobserve"


class AuthorityLevel(str, Enum):
    NONE = "none"
    RHETORICAL = "rhetorical"
    MAPPING = "mapping"
    SYNTHETIC = "synthetic"
    TEST_ONLY = "test_only"
    DIRECT_EVIDENCE = "direct_evidence"
    QUORUM_WITNESS = "quorum_witness"
    PRODUCTION = "production"


AUTHORITY_RANK: dict[AuthorityLevel, int] = {
    AuthorityLevel.NONE: 0,
    AuthorityLevel.RHETORICAL: 5,
    AuthorityLevel.MAPPING: 10,
    AuthorityLevel.SYNTHETIC: 20,
    AuthorityLevel.TEST_ONLY: 30,
    AuthorityLevel.DIRECT_EVIDENCE: 60,
    AuthorityLevel.QUORUM_WITNESS: 70,
    AuthorityLevel.PRODUCTION: 100,
}


@dataclass(frozen=True, slots=True)
class EffectManifest:
    capability_id: str
    capability_digest: str
    permitted_reads: tuple[str, ...] = ()
    permitted_writes: tuple[str, ...] = ()
    network_destinations: tuple[str, ...] = ()
    syscalls: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    model_calls: tuple[str, ...] = ()
    data_classifications: tuple[str, ...] = ("public_test_artifact",)
    authority_ceiling: str = "test_only_composition"
    resource_limits: Mapping[str, Any] = field(default_factory=dict)
    expected_postconditions: tuple[str, ...] = ()
    production_authority_allowed: bool = False
    execution_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("effect manifest requires capability_id")
        require_digest(self.capability_digest, field_name="capability_digest")
        if self.production_authority_allowed or self.execution_authority_allowed:
            raise ValueError("constitutional extension manifests cannot grant production/execution authority")
        canonical_json(self.resource_limits)

    @property
    def manifest_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class EffectObservation:
    capability_id: str
    observed_reads: tuple[str, ...] = ()
    observed_writes: tuple[str, ...] = ()
    observed_network_destinations: tuple[str, ...] = ()
    observed_syscalls: tuple[str, ...] = ()
    observed_tools: tuple[str, ...] = ()
    observed_model_calls: tuple[str, ...] = ()
    observed_data_classifications: tuple[str, ...] = ("public_test_artifact",)
    observed_authority: str = "test_only_composition"
    resource_usage: Mapping[str, Any] = field(default_factory=dict)
    postconditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("effect observation requires capability_id")
        canonical_json(self.resource_usage)

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    claim_id: str
    required_mode: EvidenceMode
    environment: str
    allow_synthetic: bool = False
    current_required: bool = True

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.environment.strip():
            raise ValueError("evidence requirement needs claim_id and environment")
        if not isinstance(self.required_mode, EvidenceMode):
            object.__setattr__(self, "required_mode", EvidenceMode(self.required_mode))

    @property
    def requirement_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class EvidenceAtom:
    claim_id: str
    evidence_mode: EvidenceMode
    environment: str
    inheritance: str
    synthetic: bool
    freshness: str
    authority_weight: str
    limitations: tuple[str, ...]
    evidence_digest: str
    current: bool = True

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.environment.strip() or not self.inheritance.strip():
            raise ValueError("evidence atom needs claim_id, environment and inheritance")
        if not isinstance(self.evidence_mode, EvidenceMode):
            object.__setattr__(self, "evidence_mode", EvidenceMode(self.evidence_mode))
        require_digest(self.evidence_digest, field_name="evidence_digest")

    @property
    def atom_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CadencePolicy:
    capability_id: str
    observation_recurrence_seconds: int
    corroboration_frequency_seconds: int
    maximum_tolerated_drift_seconds: int
    required_challenge_cadence_seconds: int
    lease_renewal_condition: str
    silence_threshold_seconds: int
    trusted_time_source: str
    expires_at: str
    decay_behavior: str = "unknown_refuse_or_reobserve"

    def __post_init__(self) -> None:
        if not self.capability_id.strip() or not self.trusted_time_source.strip():
            raise ValueError("cadence policy needs capability_id and trusted_time_source")
        for name in (
            "observation_recurrence_seconds",
            "corroboration_frequency_seconds",
            "maximum_tolerated_drift_seconds",
            "required_challenge_cadence_seconds",
            "silence_threshold_seconds",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        parse_iso_datetime(self.expires_at, field_name="expires_at")

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CadenceObservation:
    capability_id: str
    observed_at: str
    last_corroborated_at: str
    last_challenged_at: str
    now: str
    observed_drift_seconds: int = 0
    trusted_time_receipt_digest: str = ""

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("cadence observation needs capability_id")
        parse_iso_datetime(self.observed_at, field_name="observed_at")
        parse_iso_datetime(self.last_corroborated_at, field_name="last_corroborated_at")
        parse_iso_datetime(self.last_challenged_at, field_name="last_challenged_at")
        parse_iso_datetime(self.now, field_name="now")
        if self.trusted_time_receipt_digest:
            require_digest(self.trusted_time_receipt_digest, field_name="trusted_time_receipt_digest")

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class AuthorityVector:
    claim_id: str
    normative_authority: AuthorityLevel
    epistemic_authority: AuthorityLevel
    source_authority: AuthorityLevel
    data_authority: AuthorityLevel
    rhetorical_confidence: AuthorityLevel = AuthorityLevel.NONE
    requested_authority: AuthorityLevel = AuthorityLevel.TEST_ONLY

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ValueError("authority vector needs claim_id")
        for name in (
            "normative_authority",
            "epistemic_authority",
            "source_authority",
            "data_authority",
            "rhetorical_confidence",
            "requested_authority",
        ):
            value = getattr(self, name)
            if not isinstance(value, AuthorityLevel):
                object.__setattr__(self, name, AuthorityLevel(value))

    @property
    def vector_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    graph_id: str
    nodes: Mapping[str, Mapping[str, Any]]
    edges: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.graph_id.strip():
            raise ValueError("dependency graph needs graph_id")
        canonical_json(self.nodes)
        for source, target in self.edges:
            if source not in self.nodes or target not in self.nodes:
                raise ValueError("dependency graph edge references unknown node")

    @property
    def graph_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class RevocationEvent:
    event_id: str
    changed_node_id: str
    reason: str
    observed_at: str
    event_digest: str = ""

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.changed_node_id.strip() or not self.reason.strip():
            raise ValueError("revocation event requires id, changed_node_id and reason")
        parse_iso_datetime(self.observed_at, field_name="observed_at")
        if self.event_digest:
            require_digest(self.event_digest, field_name="event_digest")

    @property
    def computed_event_digest(self) -> str:
        return sha256_digest({
            "event_id": self.event_id,
            "changed_node_id": self.changed_node_id,
            "reason": self.reason,
            "observed_at": self.observed_at,
        })


def verify_effect_containment(manifest: EffectManifest, observation: EffectObservation) -> dict[str, Any]:
    if manifest.capability_id != observation.capability_id:
        raise ValueError("effect observation belongs to a different capability")

    failures = {
        "read_escape": sorted(set(observation.observed_reads) - set(manifest.permitted_reads)),
        "write_escape": sorted(set(observation.observed_writes) - set(manifest.permitted_writes)),
        "network_escape": sorted(set(observation.observed_network_destinations) - set(manifest.network_destinations)),
        "syscall_escape": sorted(set(observation.observed_syscalls) - set(manifest.syscalls)),
        "tool_escape": sorted(set(observation.observed_tools) - set(manifest.tools)),
        "model_call_escape": sorted(set(observation.observed_model_calls) - set(manifest.model_calls)),
        "data_classification_escape": sorted(set(observation.observed_data_classifications) - set(manifest.data_classifications)),
        "postcondition_missing": sorted(set(manifest.expected_postconditions) - set(observation.postconditions)),
    }
    resource_failures = _resource_limit_failures(manifest.resource_limits, observation.resource_usage)
    red_gates = tuple(name for name, values in failures.items() if values) + tuple(resource_failures)
    gates = {
        "capability_digest_valid": True,
        "manifest_production_authority_forbidden": not manifest.production_authority_allowed,
        "manifest_execution_authority_forbidden": not manifest.execution_authority_allowed,
        "static_effect_analysis_model_declared": True,
        "refinement_envelope_declared": True,
        "bounded_model_check_declared": True,
        "runtime_reconciled": not red_gates,
    }
    contained = bool(all(gates.values()) and not red_gates)
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_effect_containment_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "capability_id": manifest.capability_id,
        "manifest_digest": manifest.manifest_digest,
        "observation_digest": observation.observation_digest,
        "manifest": manifest,
        "observation": observation,
        "failures": failures,
        "resource_failures": resource_failures,
        "gates": gates,
        "red_gates": red_gates,
        "contained": contained,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "This receipt proves bounded model/static declaration plus runtime reconciliation "
            "against the declared effect manifest. It is not a full general SMT proof."
        ),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def verify_evidence_sufficiency(requirement: EvidenceRequirement, atoms: Sequence[EvidenceAtom]) -> dict[str, Any]:
    relevant = tuple(atom for atom in atoms if atom.claim_id == requirement.claim_id)
    sufficient_atoms = tuple(
        atom
        for atom in relevant
        if atom.environment == requirement.environment
        and atom.current is True
        and (requirement.allow_synthetic or not atom.synthetic)
        and EVIDENCE_STRENGTH[atom.evidence_mode] >= EVIDENCE_STRENGTH[requirement.required_mode]
    )
    laundering_attempts = tuple(
        {
            "atom_digest": atom.atom_digest,
            "mode": atom.evidence_mode.value,
            "synthetic": atom.synthetic,
            "reason": "below_required_strength_or_synthetic_not_allowed",
        }
        for atom in relevant
        if atom not in sufficient_atoms
    )
    evidence_sufficient = bool(sufficient_atoms)
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_evidence_sufficiency_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "requirement_digest": requirement.requirement_digest,
        "required_mode": requirement.required_mode.value,
        "required_environment": requirement.environment,
        "allow_synthetic": requirement.allow_synthetic,
        "atom_digests": tuple(atom.atom_digest for atom in relevant),
        "sufficient_atom_digests": tuple(atom.atom_digest for atom in sufficient_atoms),
        "laundering_attempts": laundering_attempts,
        "evidence_sufficient": evidence_sufficient,
        "action": ApplicabilityAction.ANSWER.value if evidence_sufficient else ApplicabilityAction.REFUSE.value,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def evaluate_cadence(policy: CadencePolicy, observation: CadenceObservation) -> dict[str, Any]:
    if policy.capability_id != observation.capability_id:
        raise ValueError("cadence observation belongs to a different capability")
    now = parse_iso_datetime(observation.now, field_name="now")
    observed_at = parse_iso_datetime(observation.observed_at, field_name="observed_at")
    corroborated_at = parse_iso_datetime(observation.last_corroborated_at, field_name="last_corroborated_at")
    challenged_at = parse_iso_datetime(observation.last_challenged_at, field_name="last_challenged_at")
    expires_at = parse_iso_datetime(policy.expires_at, field_name="expires_at")

    failures: list[str] = []
    if now >= expires_at:
        failures.append("lease_expired")
    if now - observed_at > timedelta(seconds=policy.observation_recurrence_seconds):
        failures.append("observation_recurrence_missed")
    if now - corroborated_at > timedelta(seconds=policy.corroboration_frequency_seconds):
        failures.append("corroboration_frequency_missed")
    if now - challenged_at > timedelta(seconds=policy.required_challenge_cadence_seconds):
        failures.append("challenge_cadence_missed")
    if now - observed_at > timedelta(seconds=policy.silence_threshold_seconds):
        failures.append("silence_threshold_exceeded")
    if abs(observation.observed_drift_seconds) > policy.maximum_tolerated_drift_seconds:
        failures.append("trusted_time_drift_exceeded")

    action = ApplicabilityAction.ANSWER if not failures else ApplicabilityAction.REOBSERVE
    if "lease_expired" in failures:
        action = ApplicabilityAction.REFUSE
    epistemic_event = {
        "event_type": "cadence_applicability_event",
        "capability_id": policy.capability_id,
        "failures": tuple(failures),
        "current_applicability": "current" if not failures else "unknown",
        "now": observation.now,
        "trusted_time_source": policy.trusted_time_source,
    }
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_cadence_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "policy_digest": policy.policy_digest,
        "observation_digest": observation.observation_digest,
        "failures": tuple(failures),
        "epistemic_event": epistemic_event,
        "epistemic_event_digest": sha256_digest(epistemic_event),
        "current_applicability": "current" if not failures else "unknown",
        "action": action.value,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def detect_authority_pollution(vector: AuthorityVector) -> dict[str, Any]:
    illegal_transitions: list[str] = []
    if _rank(vector.rhetorical_confidence) > _rank(vector.epistemic_authority):
        illegal_transitions.append("rhetorical_confidence_exceeds_epistemic_authority")
    if _rank(vector.source_authority) > _rank(vector.epistemic_authority) and _rank(vector.requested_authority) >= _rank(AuthorityLevel.DIRECT_EVIDENCE):
        illegal_transitions.append("source_identity_laundered_as_claim_correctness")
    if _rank(vector.data_authority) < _rank(vector.requested_authority):
        illegal_transitions.append("data_authority_below_requested_authority")
    if _rank(vector.normative_authority) > _rank(vector.epistemic_authority) and _rank(vector.requested_authority) >= _rank(AuthorityLevel.TEST_ONLY):
        illegal_transitions.append("normative_authority_laundered_as_epistemic_authority")
    clean = not illegal_transitions
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_authority_pollution_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "vector_digest": vector.vector_digest,
        "authority_vector": vector,
        "illegal_transitions": tuple(illegal_transitions),
        "authority_pollution_detected": not clean,
        "admission_allowed": clean,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def propagate_revocation(graph: DependencyGraph, event: RevocationEvent) -> dict[str, Any]:
    if event.changed_node_id not in graph.nodes:
        raise ValueError("revocation event references unknown dependency node")
    affected = _reachable(graph.edges, event.changed_node_id)
    stale_nodes = tuple(sorted(affected))
    revoked_leases = tuple(sorted(node for node in stale_nodes if graph.nodes[node].get("node_type") == "lease"))
    withdrawn_expressions = tuple(sorted(node for node in stale_nodes if graph.nodes[node].get("node_type") == "expression"))
    superseded_quorum_results = tuple(sorted(node for node in stale_nodes if graph.nodes[node].get("node_type") == "quorum"))
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_revocation_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "graph_digest": graph.graph_digest,
        "event_digest": event.event_digest or event.computed_event_digest,
        "changed_node_id": event.changed_node_id,
        "stale_nodes": stale_nodes,
        "revoked_leases": revoked_leases,
        "withdrawn_expressions": withdrawn_expressions,
        "superseded_quorum_results": superseded_quorum_results,
        "reobserve_required": bool(stale_nodes),
        "recompose_required": bool(stale_nodes),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def build_counterfactual_receipt(
    *,
    answer_digest: str,
    minimal_capability_set: Sequence[str],
    minimal_evidence_set: Sequence[str],
    missing_fact_forces_refusal: str,
    contradictory_fact_reverses_result: str,
    organ_constraints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    require_digest(answer_digest, field_name="answer_digest")
    for digest in minimal_capability_set:
        require_digest(str(digest), field_name="minimal_capability_digest")
    for digest in minimal_evidence_set:
        require_digest(str(digest), field_name="minimal_evidence_digest")
    if not missing_fact_forces_refusal.strip() or not contradictory_fact_reverses_result.strip():
        raise ValueError("counterfactual receipt requires refusal and reversal facts")
    canonical_json(organ_constraints)
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_counterfactual_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "answer_digest": answer_digest,
        "minimal_supporting_capability_set": tuple(minimal_capability_set),
        "minimal_evidence_set": tuple(minimal_evidence_set),
        "missing_fact_forces_refusal": missing_fact_forces_refusal,
        "contradictory_fact_reverses_result": contradictory_fact_reverses_result,
        "organ_constraints": organ_constraints,
        "explainability_mode": "minimal_proof_object_not_chain_of_thought",
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def build_lawful_reentry_receipt(
    *,
    refusal_digest: str,
    failed_criterion: str,
    cure_evidence: Sequence[str],
    eligible_evidence_providers: Sequence[str],
    appealable: bool,
    fresh_world_state_required: bool,
    permanent_prohibitions: Sequence[str],
) -> dict[str, Any]:
    require_digest(refusal_digest, field_name="refusal_digest")
    if not failed_criterion.strip():
        raise ValueError("lawful re-entry receipt needs failed_criterion")
    if not cure_evidence:
        raise ValueError("lawful re-entry receipt needs cure evidence")
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_constitutional_lawful_reentry_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "refusal_digest": refusal_digest,
        "failed_criterion": failed_criterion,
        "cure_evidence": tuple(cure_evidence),
        "eligible_evidence_providers": tuple(eligible_evidence_providers),
        "appealable": bool(appealable),
        "fresh_world_state_required": bool(fresh_world_state_required),
        "permanent_prohibitions": tuple(permanent_prohibitions),
        "reentry_steps": (
            "submit cure evidence through the original organ boundary",
            "bind fresh world-state digest",
            "rerun evidence-strength and cadence checks",
            "rerun deterministic composition without bypassing refusal",
        ),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def run_constitutional_extensions_demo(
    *,
    phase6_2_truth_receipt: Mapping[str, Any],
    lineage_policy_verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Run an executable constitutional extension demonstration.

    The demo intentionally includes hostile controls.  Green means the layer
    admitted the clean path and rejected the laundering/escape/staleness paths.
    """

    truth_digest = str(phase6_2_truth_receipt.get("receipt_digest") or "")
    policy_digest = str(lineage_policy_verification.get("policy_digest") or "")
    require_digest(truth_digest, field_name="phase6_2_truth_receipt.receipt_digest")
    require_digest(policy_digest, field_name="lineage_policy_verification.policy_digest")
    if phase6_2_truth_receipt.get("green") is not True:
        raise ValueError("Phase 6.2 truth receipt is not green")
    if lineage_policy_verification.get("verified") is not True:
        raise ValueError("Sophia/Integritas lineage policy verification is not green")

    manifest = EffectManifest(
        capability_id="crystal:phase6.2:mixed-capability-truth-arena",
        capability_digest=truth_digest,
        permitted_reads=(
            "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json",
            "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json",
            "evidence/dai-diode/phase6-sophia-integritas-lineage/sophia_integritas_project_key_policy_verification.json",
        ),
        permitted_writes=("evidence/dai-diode/phase6-constitutional-extensions/dai_phase6_constitutional_extensions_receipt.json",),
        network_destinations=(),
        syscalls=("openat", "read", "write", "close", "fstat"),
        tools=("deterministic_expression", "constitutional_verifier"),
        model_calls=(),
        data_classifications=("public_test_artifact", "education_integrity_metadata"),
        resource_limits={"max_provider_calls": 0, "max_network_destinations": 0, "max_model_calls": 0},
        expected_postconditions=("receipt_written", "production_authority_false", "execution_authority_false"),
    )
    clean_observation = EffectObservation(
        capability_id=manifest.capability_id,
        observed_reads=manifest.permitted_reads,
        observed_writes=manifest.permitted_writes,
        observed_network_destinations=(),
        observed_syscalls=("openat", "read", "write", "close", "fstat"),
        observed_tools=("deterministic_expression", "constitutional_verifier"),
        observed_model_calls=(),
        observed_data_classifications=("public_test_artifact", "education_integrity_metadata"),
        resource_usage={"max_provider_calls": 0, "max_network_destinations": 0, "max_model_calls": 0},
        postconditions=("receipt_written", "production_authority_false", "execution_authority_false"),
    )
    hostile_observation = EffectObservation(
        capability_id=manifest.capability_id,
        observed_reads=manifest.permitted_reads,
        observed_writes=manifest.permitted_writes + ("/tmp/unapproved-write",),
        observed_network_destinations=("gemini.googleapis.com:443",),
        observed_syscalls=("openat", "read", "write", "close", "fstat", "connect"),
        observed_tools=("deterministic_expression", "constitutional_verifier"),
        observed_model_calls=("gemini-chat",),
        observed_data_classifications=("public_test_artifact", "secret_candidate"),
        resource_usage={"max_provider_calls": 1, "max_network_destinations": 1, "max_model_calls": 1},
        postconditions=("receipt_written",),
    )
    containment = verify_effect_containment(manifest, clean_observation)
    hostile_containment = verify_effect_containment(manifest, hostile_observation)

    requirement = EvidenceRequirement(
        claim_id="claim:phase6.2:mixed-policy-restart-answer",
        required_mode=EvidenceMode.DIRECT_OBSERVED,
        environment="beast_local_reproduction",
        allow_synthetic=False,
    )
    direct_atom = EvidenceAtom(
        claim_id=requirement.claim_id,
        evidence_mode=EvidenceMode.DIRECT_OBSERVED,
        environment=requirement.environment,
        inheritance="direct",
        synthetic=False,
        freshness="current",
        authority_weight="direct_evidence",
        limitations=("local_project_pinned_key_not_institutional_identity",),
        evidence_digest=truth_digest,
    )
    mapped_atom = EvidenceAtom(
        claim_id=requirement.claim_id,
        evidence_mode=EvidenceMode.MAPPING_ONLY,
        environment=requirement.environment,
        inheritance="mapped",
        synthetic=True,
        freshness="current",
        authority_weight="mapping_only",
        limitations=("cannot_satisfy_direct_observation_claim",),
        evidence_digest=policy_digest,
    )
    evidence_ok = verify_evidence_sufficiency(requirement, (direct_atom,))
    evidence_laundering = verify_evidence_sufficiency(requirement, (mapped_atom,))

    cadence_policy = CadencePolicy(
        capability_id=manifest.capability_id,
        observation_recurrence_seconds=600,
        corroboration_frequency_seconds=900,
        maximum_tolerated_drift_seconds=5,
        required_challenge_cadence_seconds=1200,
        lease_renewal_condition="same_world_state_digest_and_project_pinned_lineage_policy",
        silence_threshold_seconds=1800,
        trusted_time_source="project_local_utc_clock_test_only",
        expires_at="2026-08-04T23:59:59+00:00",
    )
    cadence_current = evaluate_cadence(
        cadence_policy,
        CadenceObservation(
            capability_id=manifest.capability_id,
            observed_at="2026-08-04T21:55:00+00:00",
            last_corroborated_at="2026-08-04T21:56:00+00:00",
            last_challenged_at="2026-08-04T21:57:00+00:00",
            now="2026-08-04T22:00:00+00:00",
            observed_drift_seconds=1,
            trusted_time_receipt_digest=sha256_digest("phase6.4-local-time-receipt"),
        ),
    )
    cadence_stale = evaluate_cadence(
        cadence_policy,
        CadenceObservation(
            capability_id=manifest.capability_id,
            observed_at="2026-08-04T19:00:00+00:00",
            last_corroborated_at="2026-08-04T19:10:00+00:00",
            last_challenged_at="2026-08-04T19:20:00+00:00",
            now="2026-08-04T22:00:00+00:00",
            observed_drift_seconds=12,
            trusted_time_receipt_digest=sha256_digest("phase6.4-local-time-receipt"),
        ),
    )

    authority_clean = detect_authority_pollution(
        AuthorityVector(
            claim_id=requirement.claim_id,
            normative_authority=AuthorityLevel.TEST_ONLY,
            epistemic_authority=AuthorityLevel.DIRECT_EVIDENCE,
            source_authority=AuthorityLevel.TEST_ONLY,
            data_authority=AuthorityLevel.DIRECT_EVIDENCE,
            rhetorical_confidence=AuthorityLevel.TEST_ONLY,
            requested_authority=AuthorityLevel.TEST_ONLY,
        ),
    )
    authority_polluted = detect_authority_pollution(
        AuthorityVector(
            claim_id="claim:hostile:rhetoric-as-proof",
            normative_authority=AuthorityLevel.PRODUCTION,
            epistemic_authority=AuthorityLevel.MAPPING,
            source_authority=AuthorityLevel.PRODUCTION,
            data_authority=AuthorityLevel.SYNTHETIC,
            rhetorical_confidence=AuthorityLevel.PRODUCTION,
            requested_authority=AuthorityLevel.DIRECT_EVIDENCE,
        ),
    )

    dep_graph = DependencyGraph(
        graph_id="phase6.4:truth-arena-dependency-graph",
        nodes={
            "world:phase6.2:source-support-fact": {"node_type": "world_fact"},
            "claim:phase6.2:mixed-policy-restart-answer": {"node_type": "claim"},
            "expression:phase6.2:text-visual": {"node_type": "expression"},
            "quorum:phase6.2:local-policy-verification": {"node_type": "quorum"},
            "lease:phase6.2:deterministic-expression": {"node_type": "lease"},
        },
        edges=(
            ("world:phase6.2:source-support-fact", "claim:phase6.2:mixed-policy-restart-answer"),
            ("claim:phase6.2:mixed-policy-restart-answer", "expression:phase6.2:text-visual"),
            ("claim:phase6.2:mixed-policy-restart-answer", "quorum:phase6.2:local-policy-verification"),
            ("quorum:phase6.2:local-policy-verification", "lease:phase6.2:deterministic-expression"),
        ),
    )
    revocation = propagate_revocation(
        dep_graph,
        RevocationEvent(
            event_id="phase6.4:source-correction",
            changed_node_id="world:phase6.2:source-support-fact",
            reason="source_correction_or_visibility_boundary_changed",
            observed_at="2026-08-04T22:00:00+00:00",
        ),
    )

    first_case = phase6_2_truth_receipt.get("case_receipts", [{}])[0]
    answer_digest = str(first_case.get("expression_bundle_digest") or truth_digest)
    counterfactual = build_counterfactual_receipt(
        answer_digest=answer_digest,
        minimal_capability_set=(truth_digest, policy_digest),
        minimal_evidence_set=(truth_digest,),
        missing_fact_forces_refusal="visible_source_span_bound=false",
        contradictory_fact_reverses_result="source_contradicts_policy=true",
        organ_constraints={
            "sophia": {"may_supply": ("visible_span", "source_support"), "may_veto": ("source_contradiction",), "may_approve_execution": False},
            "beast": {"may_supply": ("deterministic_composition",), "may_veto": ("semantic_invalidity",), "may_approve_execution": False},
            "commons": {"may_supply": ("bounded_quorum_vote",), "may_veto": ("policy_violation",), "may_approve_execution": False},
        },
    )
    lawful_reentry = build_lawful_reentry_receipt(
        refusal_digest=counterfactual["receipt_digest"],
        failed_criterion="visible_source_span_bound=false",
        cure_evidence=("exact_page_span_locator", "source_digest_recomputed", "fresh_world_state_digest"),
        eligible_evidence_providers=("sophia", "learner_with_source_custody", "commons_witness"),
        appealable=True,
        fresh_world_state_required=True,
        permanent_prohibitions=("bypass_original_refusal", "convert_pedagogical_recommendation_into_disciplinary_judgment"),
    )

    hostile_controls = {
        "effect_escape_rejected": hostile_containment["contained"] is False,
        "mapping_only_direct_claim_rejected": evidence_laundering["evidence_sufficient"] is False,
        "missed_cadence_requires_reobserve": cadence_stale["action"] in {ApplicabilityAction.REOBSERVE.value, ApplicabilityAction.REFUSE.value},
        "authority_pollution_detected": authority_polluted["authority_pollution_detected"] is True,
        "revocation_reaches_expression_quorum_and_lease": bool(
            revocation["withdrawn_expressions"]
            and revocation["superseded_quorum_results"]
            and revocation["revoked_leases"]
        ),
    }
    green = bool(
        containment["contained"]
        and evidence_ok["evidence_sufficient"]
        and cadence_current["action"] == ApplicabilityAction.ANSWER.value
        and authority_clean["admission_allowed"]
        and all(hostile_controls.values())
        and not phase6_2_truth_receipt.get("production_authority_allowed", True)
    )
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_phase6_4_constitutional_extensions_receipt",
        "version": CONSTITUTIONAL_EXTENSIONS_VERSION,
        "implementation_digest": CONSTITUTIONAL_EXTENSIONS_IMPLEMENTATION_DIGEST,
        "phase6_2_truth_receipt_digest": truth_digest,
        "lineage_policy_digest": policy_digest,
        "extension_gates": {
            "mechanically_checked_effect_containment_first_slice": containment["contained"],
            "evidence_strength_lattice_enforced": evidence_ok["evidence_sufficient"] and not evidence_laundering["evidence_sufficient"],
            "cadence_and_trusted_time_applicability_enforced": cadence_current["action"] == "answer" and cadence_stale["action"] == "reobserve",
            "authority_pollution_detector_enforced": authority_clean["admission_allowed"] and authority_polluted["authority_pollution_detected"],
            "dependency_aware_revocation_enforced": hostile_controls["revocation_reaches_expression_quorum_and_lease"],
            "counterfactual_minimal_proof_receipt_emitted": bool(counterfactual["minimal_supporting_capability_set"]),
            "lawful_reentry_receipt_emitted": bool(lawful_reentry["reentry_steps"]),
        },
        "effect_containment_receipt": containment,
        "hostile_effect_containment_receipt": hostile_containment,
        "evidence_sufficiency_receipt": evidence_ok,
        "evidence_laundering_receipt": evidence_laundering,
        "cadence_current_receipt": cadence_current,
        "cadence_stale_receipt": cadence_stale,
        "authority_clean_receipt": authority_clean,
        "authority_pollution_receipt": authority_polluted,
        "revocation_receipt": revocation,
        "counterfactual_receipt": counterfactual,
        "lawful_reentry_receipt": lawful_reentry,
        "hostile_controls": hostile_controls,
        "deferred_extensions_not_claimed_green": (
            "full_bounded_smt_model_checking",
            "hybrid_ed25519_plus_ml_dsa_65_signature_runtime",
            "formal_commons_byzantine_safety_liveness_model",
            "production_sensorium_cadence_tsa_time",
        ),
        "green": green,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "DIO Core remains frozen. This receipt demonstrates first-pass constitutional "
            "extension enforcement for containment, evidence strength, cadence, authority "
            "pollution, revocation, counterfactual explanation and lawful re-entry. It does "
            "not claim full SMT proof, PQ hybrid publication signing or formal Commons consensus."
        ),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _resource_limit_failures(limits: Mapping[str, Any], usage: Mapping[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []
    for key, limit in limits.items():
        if key not in usage:
            continue
        try:
            if float(usage[key]) > float(limit):
                failures.append(f"resource_limit_exceeded:{key}")
        except (TypeError, ValueError):
            if usage[key] != limit:
                failures.append(f"resource_limit_non_numeric_mismatch:{key}")
    return tuple(sorted(failures))


def _rank(level: AuthorityLevel) -> int:
    return AUTHORITY_RANK[AuthorityLevel(level)]


def _reachable(edges: Sequence[tuple[str, str]], start: str) -> set[str]:
    outgoing: dict[str, list[str]] = {}
    for source, target in edges:
        outgoing.setdefault(source, []).append(target)
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for target in outgoing.get(node, ()):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return seen
