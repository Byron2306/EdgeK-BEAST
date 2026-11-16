"""Proof-first deterministic cross-modal intelligence for BEAST.

This module is deliberately self-contained and standard-library-only so the
ultimate gauntlet can run as an auditable contract test even when extracted as
an evidence/patch bundle.  It implements the proof order required by C4-X:

    verified substrate -> canonical proof graph -> sibling text/scene views
    -> deterministic text/SVG artifacts -> joined verification receipt

Neither modality is allowed to generate, interpret, or repair the other.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import html
import json
import re
from typing import Any, Iterable, Mapping, Sequence


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonical(item) for item in value)
    if isinstance(value, bytes):
        return {"bytes_digest": sha256_bytes(value), "bytes_length": len(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value is not canonically serializable: {type(value)!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def require_digest(value: str, *, field_name: str) -> None:
    if not DIGEST_RE.fullmatch(str(value)):
        raise ValueError(f"{field_name} must be a sha256 digest")


class Family(str, Enum):
    RESTART_RISK = "restart_risk"
    TRAFFIC_SHIFT = "traffic_shift"
    DEPLOYMENT_SAFETY = "deployment_safety"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    REFUTED = "refuted"
    RESIDUAL_REQUIRED = "residual_required"


class JoinedStatus(str, Enum):
    COMPOSED = "composed"
    PARTIAL = "partial"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class CapabilityFact:
    fact_id: str
    fact_type: str
    subject: str
    predicate: str
    object: str = ""
    value: Any = None
    evidence_digest: str = ""
    observed_at: str = ""
    freshness_seconds: int = 300

    def __post_init__(self) -> None:
        if not all((self.fact_id.strip(), self.fact_type.strip(), self.subject.strip(), self.predicate.strip())):
            raise ValueError("capability facts require id, type, subject, and predicate")
        if self.evidence_digest:
            require_digest(self.evidence_digest, field_name="evidence_digest")
        canonical_json(self.value)

    @property
    def fact_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CausalRule:
    rule_id: str
    family: Family
    predicate: str
    parameters: Mapping[str, Any]
    authority: str = "verified_rule"

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.predicate.strip():
            raise ValueError("causal rules require rule_id and predicate")
        if not isinstance(self.family, Family):
            object.__setattr__(self, "family", Family(self.family))
        canonical_json(self.parameters)

    @property
    def rule_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class PolicyConstraint:
    policy_id: str
    family: Family
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy requires policy_id")
        if not isinstance(self.family, Family):
            object.__setattr__(self, "family", Family(self.family))
        canonical_json(self.parameters)

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    family: Family
    question: str
    source: str
    target: str
    facts: tuple[CapabilityFact, ...]
    rules: tuple[CausalRule, ...]
    policies: tuple[PolicyConstraint, ...]
    visual_assets: Mapping[str, str] = field(default_factory=dict)
    canvas_width: int = 960
    canvas_height: int = 540
    force_layout_overflow: bool = False
    provider_policy: str = "residual_only"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.question.strip() or not self.source.strip() or not self.target.strip():
            raise ValueError("scenario requires id, question, source, and target")
        if not isinstance(self.family, Family):
            object.__setattr__(self, "family", Family(self.family))
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            raise ValueError("canvas dimensions must be positive")
        for digest in self.visual_assets.values():
            require_digest(digest, field_name="visual_asset_digest")
        canonical_json(self.metadata)

    @property
    def request_digest(self) -> str:
        return sha256_digest({
            "scenario_id": self.scenario_id,
            "family": self.family.value,
            "question": self.question,
            "source": self.source,
            "target": self.target,
            "metadata": self.metadata,
        })


@dataclass(frozen=True, slots=True)
class ProofClaim:
    claim_id: str
    claim_type: str
    subject: str
    predicate: str
    object: str
    status: ClaimStatus
    confidence_class: str
    fact_refs: tuple[str, ...]
    rule_ref: str = ""
    policy_ref: str = ""
    snapshot_ref: str = ""
    current_claim_allowed: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all((self.claim_id.strip(), self.claim_type.strip(), self.subject.strip(), self.predicate.strip())):
            raise ValueError("proof claim missing required identity")
        if not isinstance(self.status, ClaimStatus):
            object.__setattr__(self, "status", ClaimStatus(self.status))
        if not self.fact_refs:
            raise ValueError("proof claim requires fact refs")
        canonical_json(self.metadata)

    @property
    def claim_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CanonicalProofGraph:
    graph_id: str
    family: Family
    request_digest: str
    claims: tuple[ProofClaim, ...]
    world_snapshot_digest: str
    policy_digests: tuple[str, ...]
    fact_digests: tuple[str, ...]
    rule_digests: tuple[str, ...]
    compile_sequence: int = 1
    compiler_id: str = "beast.proof-first-compiler.v1"

    def __post_init__(self) -> None:
        if not self.graph_id.strip() or not self.claims:
            raise ValueError("proof graph requires id and claims")
        if not isinstance(self.family, Family):
            object.__setattr__(self, "family", Family(self.family))
        for name in ("request_digest", "world_snapshot_digest"):
            require_digest(getattr(self, name), field_name=name)
        for digest in (*self.policy_digests, *self.fact_digests, *self.rule_digests):
            require_digest(digest, field_name="proof_component_digest")
        ids = [claim.claim_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim ids must be unique")
        if self.compile_sequence != 1:
            raise ValueError("canonical proof graph must be phase one")

    @property
    def graph_digest(self) -> str:
        return sha256_digest(self)

    def claim(self, claim_id: str) -> ProofClaim:
        for claim in self.claims:
            if claim.claim_id == claim_id:
                return claim
        raise KeyError(claim_id)

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(claim.claim_id for claim in self.claims)

    @property
    def conclusion_claim(self) -> ProofClaim:
        return self.claims[-1]


@dataclass(frozen=True, slots=True)
class ResidualPacket:
    residual_id: str
    residual_scope: str
    unresolved_fields: tuple[str, ...]
    allowed_output_fields: tuple[str, ...]
    forbidden_output_fields: tuple[str, ...]
    proof_graph_digest: str
    claim_ref: str
    max_output_bytes: int = 512

    def __post_init__(self) -> None:
        require_digest(self.proof_graph_digest, field_name="proof_graph_digest")
        if not self.unresolved_fields or not self.allowed_output_fields:
            raise ValueError("residual packet must identify unresolved and allowed fields")

    @property
    def packet_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class TextFrame:
    frame_id: str
    family: Family
    graph_digest: str
    claim_refs: tuple[str, ...]
    conclusion_claim_ref: str
    epistemic_status: ClaimStatus
    headline: str
    summary_fields: Mapping[str, Any]
    current_conclusion_allowed: bool
    residual_refs: tuple[str, ...] = ()
    realize_sequence: int = 2
    renderer_id: str = "beast.structured-text-frame.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.family, Family):
            object.__setattr__(self, "family", Family(self.family))
        if not isinstance(self.epistemic_status, ClaimStatus):
            object.__setattr__(self, "epistemic_status", ClaimStatus(self.epistemic_status))
        require_digest(self.graph_digest, field_name="graph_digest")
        if not self.claim_refs or self.conclusion_claim_ref not in self.claim_refs:
            raise ValueError("text frame must reference its conclusion claim")
        if self.realize_sequence <= 1:
            raise ValueError("text frame must be realized after proof compilation")
        canonical_json(self.summary_fields)

    @property
    def frame_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ScenePrimitive:
    primitive_id: str
    primitive_type: str
    claim_ref: str
    evidence_state: ClaimStatus
    x: int
    y: int
    width: int
    height: int
    label: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_state, ClaimStatus):
            object.__setattr__(self, "evidence_state", ClaimStatus(self.evidence_state))
        if not all((self.primitive_id.strip(), self.primitive_type.strip(), self.claim_ref.strip())):
            raise ValueError("scene primitive missing identity")
        canonical_json(self.metadata)

    @property
    def primitive_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ScenePlan:
    plan_id: str
    family: Family
    graph_digest: str
    claim_refs: tuple[str, ...]
    primitives: tuple[ScenePrimitive, ...]
    canvas_width: int
    canvas_height: int
    visual_intent_fulfilled: bool
    unresolved_visual_gaps: tuple[str, ...] = ()
    residual_refs: tuple[str, ...] = ()
    compile_sequence: int = 3
    compiler_id: str = "beast.deterministic-scene-plan.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.family, Family):
            object.__setattr__(self, "family", Family(self.family))
        require_digest(self.graph_digest, field_name="graph_digest")
        if not self.primitives:
            raise ValueError("scene plan requires primitives")
        if self.compile_sequence <= 1:
            raise ValueError("scene plan must be compiled after proof graph")
        if set(self.claim_refs) != {primitive.claim_ref for primitive in self.primitives}:
            raise ValueError("scene plan claim refs must equal primitive claim refs")

    @property
    def plan_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Artifact:
    media_type: str
    content: bytes
    status: str
    render_sequence: int
    failure_class: str = ""

    @property
    def digest(self) -> str:
        return sha256_bytes(self.content)

    @property
    def length(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class CompositionResult:
    scenario: Scenario
    proof_graph: CanonicalProofGraph
    text_frame: TextFrame
    scene_plan: ScenePlan
    text_artifact: Artifact
    visual_artifact: Artifact
    residual_packets: tuple[ResidualPacket, ...]
    joined_receipt: Mapping[str, Any]
    verification: Mapping[str, Any]


class ProofCompiler:
    def compile(self, scenario: Scenario) -> tuple[CanonicalProofGraph, tuple[ResidualPacket, ...]]:
        if scenario.family is Family.RESTART_RISK:
            claims, residual_specs = self._compile_restart(scenario)
        elif scenario.family is Family.TRAFFIC_SHIFT:
            claims, residual_specs = self._compile_traffic(scenario)
        elif scenario.family is Family.DEPLOYMENT_SAFETY:
            claims, residual_specs = self._compile_deployment(scenario)
        else:  # pragma: no cover
            raise ValueError(f"unsupported family: {scenario.family}")

        asset_key = f"{scenario.family.value}:status_badge"
        if asset_key not in scenario.visual_assets:
            residual_specs.append(("visual_metadata_only", ("asset_id", "asset_digest", "asset_class")))

        graph = CanonicalProofGraph(
            graph_id=f"proof:{scenario.family.value}:{scenario.request_digest.removeprefix('sha256:')[:20]}",
            family=scenario.family,
            request_digest=scenario.request_digest,
            claims=tuple(claims),
            world_snapshot_digest=sha256_digest({
                "facts": tuple(fact.fact_digest for fact in scenario.facts),
                "observed": tuple(fact.observed_at for fact in scenario.facts),
            }),
            policy_digests=tuple(policy.policy_digest for policy in scenario.policies),
            fact_digests=tuple(fact.fact_digest for fact in scenario.facts),
            rule_digests=tuple(rule.rule_digest for rule in scenario.rules),
        )
        residuals = tuple(
            ResidualPacket(
                residual_id=f"residual:{scenario.scenario_id}:{index}",
                residual_scope=spec[0],
                unresolved_fields=tuple(spec[1]),
                allowed_output_fields=tuple(spec[1]),
                forbidden_output_fields=(
                    "final_answer", "full_scene", "raw_prompt", "provider_prompt",
                    "new_fact", "new_dependency", "new_policy", "action_authority",
                ),
                proof_graph_digest=graph.graph_digest,
                claim_ref=graph.conclusion_claim.claim_id,
            )
            for index, spec in enumerate(residual_specs, start=1)
        )
        return graph, residuals

    def _compile_restart(self, scenario: Scenario) -> tuple[list[ProofClaim], list[tuple[str, Sequence[str]]]]:
        source_health = _fact(scenario, "service_health", scenario.source)
        target_health = _fact(scenario, "service_health", scenario.target)
        dependency = _relation_fact(scenario, "dependency_topology", scenario.target, scenario.source)
        policy_fact = _fact(scenario, "restart_policy", scenario.source)
        evidence = _fact(scenario, "current_evidence", "runtime")
        rule = _rule(scenario, "restart_destabilization")
        stale = _scenario_stale(scenario)
        base = [
            _direct_claim(scenario, "source-health", source_health, status=_status_for_fact(source_health, stale)),
            _direct_claim(scenario, "target-health", target_health, status=_status_for_fact(target_health, stale)),
            _direct_claim(scenario, "dependency", dependency, status=_status_for_fact(dependency, False)),
            _direct_claim(scenario, "restart-policy", policy_fact, status=_status_for_fact(policy_fact, False)),
        ]
        refs = tuple(claim.claim_digest for claim in base)
        residuals: list[tuple[str, Sequence[str]]] = []
        if stale:
            status = ClaimStatus.STALE
            allowed = False
            risk_class = "unknown_current_state"
            confidence = "temporally_invalid"
        elif any(item is None for item in (source_health, target_health, dependency, policy_fact, evidence)):
            status = ClaimStatus.UNSUPPORTED
            allowed = False
            risk_class = "unsupported"
            confidence = "missing_verified_fact"
        elif rule is None:
            status = ClaimStatus.RESIDUAL_REQUIRED
            allowed = False
            risk_class = "unsupported_without_causal_rule"
            confidence = "causal_rule_missing"
            residuals.append(("causal_fields_only", ("risk_class", "causal_label", "confidence_class")))
        else:
            source_state = str(_value(source_health).get("state", "unknown"))
            target_state = str(_value(target_health).get("state", "unknown"))
            mode = str(_value(policy_fact).get("mode", ""))
            dependency_kind = str(_value(dependency).get("relation", ""))
            low = source_state == "healthy" and target_state == "healthy" and mode in {"rolling_with_healthcheck", "blue_green"}
            status = ClaimStatus.SUPPORTED
            allowed = True
            risk_class = "low" if low else "elevated"
            confidence = "rule_proven"
            if dependency_kind not in {"depends_on", "routes_through"}:
                risk_class = "unknown_dependency_semantics"
                status = ClaimStatus.UNSUPPORTED
                allowed = False
                confidence = "dependency_semantics_missing"
        conclusion = ProofClaim(
            claim_id=f"claim:{scenario.scenario_id}:restart-risk",
            claim_type="conditional_causal",
            subject=scenario.source,
            predicate="restart_destabilization_risk",
            object=scenario.target,
            status=status,
            confidence_class=confidence,
            fact_refs=refs or (scenario.request_digest,),
            rule_ref=rule.rule_digest if rule is not None else "",
            policy_ref=scenario.policies[0].policy_digest if scenario.policies else (policy_fact.fact_digest if policy_fact else ""),
            snapshot_ref=evidence.fact_digest if evidence is not None else scenario.request_digest,
            current_claim_allowed=allowed,
            metadata={"risk_class": risk_class, "family": scenario.family.value},
        )
        return [*base, conclusion], residuals

    def _compile_traffic(self, scenario: Scenario) -> tuple[list[ProofClaim], list[tuple[str, Sequence[str]]]]:
        source_capacity = _fact(scenario, "capacity_state", scenario.source)
        target_capacity = _fact(scenario, "capacity_state", scenario.target)
        route = _relation_fact(scenario, "traffic_route", scenario.source, scenario.target)
        evidence = _fact(scenario, "current_evidence", "runtime")
        rule = _rule(scenario, "traffic_shift_capacity")
        policy = scenario.policies[0] if scenario.policies else None
        stale = _scenario_stale(scenario)
        base = [
            _direct_claim(scenario, "source-capacity", source_capacity, status=_status_for_fact(source_capacity, stale)),
            _direct_claim(scenario, "target-capacity", target_capacity, status=_status_for_fact(target_capacity, stale)),
            _direct_claim(scenario, "route", route, status=_status_for_fact(route, False)),
        ]
        refs = tuple(claim.claim_digest for claim in base)
        residuals: list[tuple[str, Sequence[str]]] = []
        if stale:
            status, allowed, shift_class, confidence = ClaimStatus.STALE, False, "unknown_current_state", "temporally_invalid"
        elif any(item is None for item in (source_capacity, target_capacity, route, evidence, policy)):
            status, allowed, shift_class, confidence = ClaimStatus.UNSUPPORTED, False, "unsupported", "missing_verified_fact"
        elif rule is None:
            status, allowed, shift_class, confidence = ClaimStatus.RESIDUAL_REQUIRED, False, "unsupported_without_capacity_rule", "capacity_rule_missing"
            residuals.append(("capacity_fields_only", ("shift_class", "capacity_label", "confidence_class")))
        else:
            target_spare = float(_value(target_capacity).get("spare_percent", 0))
            shift = float(scenario.metadata.get("shift_percent", 0))
            reserve = float(policy.parameters.get("minimum_reserve_percent", 0))
            route_state = str(_value(route).get("state", "unknown"))
            safe = route_state == "healthy" and target_spare >= shift + reserve
            status, allowed = ClaimStatus.SUPPORTED, True
            shift_class, confidence = ("safe", "threshold_proven") if safe else ("unsafe", "threshold_refuted")
        conclusion = ProofClaim(
            claim_id=f"claim:{scenario.scenario_id}:traffic-shift",
            claim_type="quantitative_threshold",
            subject=scenario.source,
            predicate="traffic_shift_safety",
            object=scenario.target,
            status=status,
            confidence_class=confidence,
            fact_refs=refs or (scenario.request_digest,),
            rule_ref=rule.rule_digest if rule else "",
            policy_ref=policy.policy_digest if policy else "",
            snapshot_ref=evidence.fact_digest if evidence else scenario.request_digest,
            current_claim_allowed=allowed,
            metadata={
                "shift_class": shift_class,
                "shift_percent": float(scenario.metadata.get("shift_percent", 0)),
                "target_spare_percent": float(_value(target_capacity).get("spare_percent", 0)) if target_capacity else None,
                "minimum_reserve_percent": float(policy.parameters.get("minimum_reserve_percent", 0)) if policy else None,
                "family": scenario.family.value,
            },
        )
        return [*base, conclusion], residuals

    def _compile_deployment(self, scenario: Scenario) -> tuple[list[ProofClaim], list[tuple[str, Sequence[str]]]]:
        stage = _fact(scenario, "deployment_stage", scenario.source)
        health_gate = _fact(scenario, "health_gate", scenario.source)
        rollback = _fact(scenario, "rollback_state", scenario.source)
        target_health = _fact(scenario, "service_health", scenario.target)
        evidence = _fact(scenario, "current_evidence", "runtime")
        rule = _rule(scenario, "deployment_rollout_safety")
        policy = scenario.policies[0] if scenario.policies else None
        stale = _scenario_stale(scenario)
        base = [
            _direct_claim(scenario, "deployment-stage", stage, status=_status_for_fact(stage, False)),
            _direct_claim(scenario, "health-gate", health_gate, status=_status_for_fact(health_gate, stale)),
            _direct_claim(scenario, "rollback", rollback, status=_status_for_fact(rollback, False)),
            _direct_claim(scenario, "target-health", target_health, status=_status_for_fact(target_health, stale)),
        ]
        refs = tuple(claim.claim_digest for claim in base)
        residuals: list[tuple[str, Sequence[str]]] = []
        if stale:
            status, allowed, deployment_class, confidence = ClaimStatus.STALE, False, "unknown_current_state", "temporally_invalid"
        elif any(item is None for item in (stage, health_gate, rollback, target_health, evidence, policy)):
            status, allowed, deployment_class, confidence = ClaimStatus.UNSUPPORTED, False, "unsupported", "missing_verified_fact"
        elif rule is None:
            status, allowed, deployment_class, confidence = ClaimStatus.RESIDUAL_REQUIRED, False, "unsupported_without_rollout_rule", "rollout_rule_missing"
            residuals.append(("deployment_fields_only", ("deployment_class", "gate_label", "confidence_class")))
        else:
            gate_passed = bool(_value(health_gate).get("passed"))
            rollback_ready = bool(_value(rollback).get("ready"))
            target_state = str(_value(target_health).get("state", "unknown"))
            max_error = float(policy.parameters.get("max_error_rate_percent", 100))
            observed_error = float(_value(health_gate).get("error_rate_percent", 100))
            safe = gate_passed and rollback_ready and target_state == "healthy" and observed_error <= max_error
            status, allowed = ClaimStatus.SUPPORTED, True
            deployment_class, confidence = ("safe_to_continue", "gate_proven") if safe else ("halt_or_rollback", "gate_refuted")
        conclusion = ProofClaim(
            claim_id=f"claim:{scenario.scenario_id}:deployment-safety",
            claim_type="staged_policy_gate",
            subject=scenario.source,
            predicate="deployment_safety",
            object=scenario.target,
            status=status,
            confidence_class=confidence,
            fact_refs=refs or (scenario.request_digest,),
            rule_ref=rule.rule_digest if rule else "",
            policy_ref=policy.policy_digest if policy else "",
            snapshot_ref=evidence.fact_digest if evidence else scenario.request_digest,
            current_claim_allowed=allowed,
            metadata={"deployment_class": deployment_class, "family": scenario.family.value},
        )
        return [*base, conclusion], residuals


class TextRealizer:
    def realize(self, graph: CanonicalProofGraph, residuals: Sequence[ResidualPacket]) -> TextFrame:
        conclusion = graph.conclusion_claim
        if graph.family is Family.RESTART_RISK:
            value = str(conclusion.metadata.get("risk_class", "unsupported"))
            headline = "Restart-risk assessment"
            fields = {"risk_class": value, "source": conclusion.subject, "target": conclusion.object}
        elif graph.family is Family.TRAFFIC_SHIFT:
            value = str(conclusion.metadata.get("shift_class", "unsupported"))
            headline = "Traffic-shift assessment"
            fields = {
                "shift_class": value,
                "source": conclusion.subject,
                "target": conclusion.object,
                "shift_percent": conclusion.metadata.get("shift_percent"),
                "target_spare_percent": conclusion.metadata.get("target_spare_percent"),
                "minimum_reserve_percent": conclusion.metadata.get("minimum_reserve_percent"),
            }
        else:
            value = str(conclusion.metadata.get("deployment_class", "unsupported"))
            headline = "Deployment-safety assessment"
            fields = {"deployment_class": value, "source": conclusion.subject, "target": conclusion.object}
        return TextFrame(
            frame_id=f"text-frame:{graph.graph_id}",
            family=graph.family,
            graph_digest=graph.graph_digest,
            claim_refs=tuple(claim.claim_id for claim in graph.claims),
            conclusion_claim_ref=conclusion.claim_id,
            epistemic_status=conclusion.status,
            headline=headline,
            summary_fields=fields,
            current_conclusion_allowed=conclusion.current_claim_allowed,
            residual_refs=tuple(packet.packet_digest for packet in residuals if packet.claim_ref == conclusion.claim_id),
        )

    def render(self, frame: TextFrame) -> Artifact:
        fields = dict(frame.summary_fields)
        source = str(fields.get("source", "source"))
        target = str(fields.get("target", "target"))
        status = frame.epistemic_status
        if status is ClaimStatus.STALE:
            body = (
                f"{frame.headline}: the verified topology and policy remain available, but current safety "
                f"for {source} relative to {target} cannot be established because the health/capacity evidence is stale."
            )
        elif status is ClaimStatus.RESIDUAL_REQUIRED:
            body = (
                f"{frame.headline}: BEAST refuses a current causal conclusion for {source} relative to {target}. "
                "A bounded residual request has been emitted only for the missing typed fields."
            )
        elif status is ClaimStatus.UNSUPPORTED:
            body = (
                f"{frame.headline}: BEAST refuses the conclusion for {source} relative to {target} because the "
                "verified substrate is incomplete."
            )
        elif frame.family is Family.RESTART_RISK:
            risk = str(fields["risk_class"])
            body = (
                f"{frame.headline}: restarting {source} has {risk} demonstrated destabilization risk for {target} "
                "under the verified dependency, health, restart-policy, and causal-rule substrate."
            )
        elif frame.family is Family.TRAFFIC_SHIFT:
            shift_class = str(fields["shift_class"])
            body = (
                f"{frame.headline}: shifting {fields['shift_percent']:.0f}% traffic from {source} to {target} is "
                f"{shift_class}; target spare capacity is {fields['target_spare_percent']:.0f}% with a required "
                f"reserve of {fields['minimum_reserve_percent']:.0f}%."
            )
        else:
            deployment_class = str(fields["deployment_class"]).replace("_", " ")
            body = (
                f"{frame.headline}: the rollout from {source} toward {target} is classified as {deployment_class} "
                "under the verified stage, health-gate, rollback, target-health, and policy substrate."
            )
        payload = {
            "headline": frame.headline,
            "body": body,
            "epistemic_status": status.value,
            "current_conclusion_allowed": frame.current_conclusion_allowed,
            "claim_refs": frame.claim_refs,
            "graph_digest": frame.graph_digest,
        }
        return Artifact(
            media_type="application/vnd.beast.structured-answer+json",
            content=(json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8"),
            status="rendered",
            render_sequence=4,
        )


class SceneCompiler:
    def compile(self, scenario: Scenario, graph: CanonicalProofGraph, residuals: Sequence[ResidualPacket]) -> ScenePlan:
        claims = {claim.predicate: claim for claim in graph.claims}
        conclusion = graph.conclusion_claim
        primitives: list[ScenePrimitive] = []
        if graph.family is Family.RESTART_RISK:
            primitives.extend([
                _primitive("source-node", "service_node", _claim_by_suffix(graph, "source-health").claim_id, _claim_by_suffix(graph, "source-health").status, 80, 170, 190, 100, scenario.source),
                _primitive("target-node", "service_node", _claim_by_suffix(graph, "target-health").claim_id, _claim_by_suffix(graph, "target-health").status, 680, 170, 190, 100, scenario.target),
                _primitive("dependency-edge", "dependency_edge", _claim_by_suffix(graph, "dependency").claim_id, _claim_by_suffix(graph, "dependency").status, 290, 205, 370, 30, "depends on"),
                _primitive("restart-policy", "policy_gate", _claim_by_suffix(graph, "restart-policy").claim_id, _claim_by_suffix(graph, "restart-policy").status, 330, 70, 300, 70, "restart policy"),
                _primitive("risk-badge", "risk_badge", conclusion.claim_id, conclusion.status, 350, 330, 260, 80, str(conclusion.metadata.get("risk_class", conclusion.status.value))),
            ])
        elif graph.family is Family.TRAFFIC_SHIFT:
            source_claim = _claim_by_suffix(graph, "source-capacity")
            target_claim = _claim_by_suffix(graph, "target-capacity")
            route_claim = _claim_by_suffix(graph, "route")
            primitives.extend([
                _primitive("source-capacity", "capacity_bar", source_claim.claim_id, source_claim.status, 70, 150, 220, 120, scenario.source),
                _primitive("target-capacity", "capacity_bar", target_claim.claim_id, target_claim.status, 670, 150, 220, 120, scenario.target),
                _primitive("traffic-arrow", "traffic_shift_arrow", route_claim.claim_id, route_claim.status, 310, 195, 340, 40, f"shift {conclusion.metadata.get('shift_percent', 0):.0f}%"),
                _primitive("reserve-threshold", "policy_threshold", conclusion.claim_id, conclusion.status, 330, 70, 300, 70, f"reserve {conclusion.metadata.get('minimum_reserve_percent', 0):.0f}%"),
                _primitive("shift-badge", "status_badge", conclusion.claim_id, conclusion.status, 350, 330, 260, 80, str(conclusion.metadata.get("shift_class", conclusion.status.value))),
            ])
        else:
            stage_claim = _claim_by_suffix(graph, "deployment-stage")
            gate_claim = _claim_by_suffix(graph, "health-gate")
            rollback_claim = _claim_by_suffix(graph, "rollback")
            target_claim = _claim_by_suffix(graph, "target-health")
            primitives.extend([
                _primitive("stage", "deployment_stage", stage_claim.claim_id, stage_claim.status, 70, 170, 190, 100, scenario.source),
                _primitive("health-gate", "health_gate", gate_claim.claim_id, gate_claim.status, 330, 70, 300, 70, "health gate"),
                _primitive("rollout-arrow", "rollout_arrow", conclusion.claim_id, conclusion.status, 280, 205, 380, 40, "rollout path"),
                _primitive("target", "service_node", target_claim.claim_id, target_claim.status, 690, 170, 190, 100, scenario.target),
                _primitive("rollback", "rollback_edge", rollback_claim.claim_id, rollback_claim.status, 280, 310, 380, 40, "rollback path"),
                _primitive("deployment-badge", "risk_badge", conclusion.claim_id, conclusion.status, 350, 390, 260, 70, str(conclusion.metadata.get("deployment_class", conclusion.status.value))),
            ])

        visual_gaps: list[str] = []
        asset_key = f"{graph.family.value}:status_badge"
        if asset_key not in scenario.visual_assets:
            visual_gaps.append("missing_status_asset_metadata")
            primitives.append(_primitive(
                "asset-placeholder", "unsupported_marker", conclusion.claim_id, ClaimStatus.UNSUPPORTED,
                730, 390 if graph.family is not Family.DEPLOYMENT_SAFETY else 430, 180, 55,
                "asset unsupported", {"requested_asset_key": asset_key},
            ))
        if conclusion.status in {ClaimStatus.UNSUPPORTED, ClaimStatus.RESIDUAL_REQUIRED, ClaimStatus.STALE}:
            primitives.append(_primitive(
                "epistemic-marker", "unsupported_marker" if conclusion.status is not ClaimStatus.STALE else "stale_marker",
                conclusion.claim_id, conclusion.status, 70, 430, 300, 55,
                "unsupported" if conclusion.status is not ClaimStatus.STALE else "stale evidence",
            ))
        if scenario.force_layout_overflow:
            primitives.append(_primitive(
                "forced-overflow", "layout_probe", conclusion.claim_id, conclusion.status,
                scenario.canvas_width - 10, scenario.canvas_height - 10, 160, 80, "overflow probe",
            ))

        return ScenePlan(
            plan_id=f"scene-plan:{graph.graph_id}",
            family=graph.family,
            graph_digest=graph.graph_digest,
            claim_refs=tuple(sorted({primitive.claim_ref for primitive in primitives})),
            primitives=tuple(primitives),
            canvas_width=scenario.canvas_width,
            canvas_height=scenario.canvas_height,
            visual_intent_fulfilled=not visual_gaps,
            unresolved_visual_gaps=tuple(visual_gaps),
            residual_refs=tuple(packet.packet_digest for packet in residuals if packet.residual_scope.endswith("visual_metadata_only")),
        )


class SvgRenderer:
    def render(self, graph: CanonicalProofGraph, plan: ScenePlan) -> Artifact:
        failures = _layout_failures(plan)
        if failures:
            return Artifact(
                media_type="image/svg+xml",
                content=b"",
                status="refused",
                render_sequence=5,
                failure_class="layout_overflow:" + ",".join(failures),
            )
        elements = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{plan.canvas_width}" height="{plan.canvas_height}" viewBox="0 0 {plan.canvas_width} {plan.canvas_height}">',
            '<rect width="100%" height="100%" fill="#081018"/>',
            f'<text x="28" y="34" fill="#d8e8ef" font-family="monospace" font-size="20">BEAST C4-X · {html.escape(graph.family.value)}</text>',
            f'<text x="28" y="58" fill="#78f0c8" font-family="monospace" font-size="12">proof {html.escape(graph.graph_digest)}</text>',
        ]
        for primitive in plan.primitives:
            elements.extend(_svg_primitive(primitive))
        elements.append('</svg>')
        return Artifact(
            media_type="image/svg+xml",
            content=("\n".join(elements) + "\n").encode("utf-8"),
            status="rendered" if plan.visual_intent_fulfilled else "placeholder_rendered",
            render_sequence=5,
        )


class JoinedVerifier:
    def verify(
        self,
        scenario: Scenario,
        graph: CanonicalProofGraph,
        text_frame: TextFrame,
        scene_plan: ScenePlan,
        text_artifact: Artifact,
        visual_artifact: Artifact,
        residuals: Sequence[ResidualPacket],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        failures: list[str] = []
        graph_claim_ids = {claim.claim_id for claim in graph.claims}
        proof_first = graph.compile_sequence < text_frame.realize_sequence < text_artifact.render_sequence
        proof_first = proof_first and graph.compile_sequence < scene_plan.compile_sequence < visual_artifact.render_sequence
        if not proof_first:
            failures.append("proof_not_compiled_first")
        if graph.request_digest != scenario.request_digest:
            failures.append("request_digest_mismatch")
        if text_frame.graph_digest != graph.graph_digest or scene_plan.graph_digest != graph.graph_digest:
            failures.append("view_graph_digest_mismatch")
        if not set(text_frame.claim_refs).issubset(graph_claim_ids):
            failures.append("text_unknown_claim_ref")
        if not set(scene_plan.claim_refs).issubset(graph_claim_ids):
            failures.append("visual_unknown_claim_ref")
        conclusion = graph.conclusion_claim
        if text_frame.epistemic_status is not conclusion.status:
            failures.append("text_epistemic_status_mismatch")
        if text_frame.current_conclusion_allowed != conclusion.current_claim_allowed:
            failures.append("text_current_claim_authority_mismatch")
        for primitive in scene_plan.primitives:
            if primitive.claim_ref not in graph_claim_ids:
                failures.append(f"primitive_unknown_claim:{primitive.primitive_id}")
                continue
            claim = graph.claim(primitive.claim_ref)
            if primitive.primitive_type not in {"unsupported_marker", "asset_placeholder"} and primitive.evidence_state is not claim.status:
                failures.append(f"primitive_state_mismatch:{primitive.primitive_id}")
        expected_text = TextRealizer().render(text_frame)
        text_bytes_valid = expected_text.content == text_artifact.content
        if not text_bytes_valid:
            failures.append("text_artifact_tamper_or_semantic_drift")
        expected_visual = SvgRenderer().render(graph, scene_plan)
        visual_bytes_valid = expected_visual.content == visual_artifact.content and expected_visual.status == visual_artifact.status
        if not visual_bytes_valid:
            failures.append("visual_artifact_tamper_or_semantic_drift")
        layout_valid = not _layout_failures(scene_plan)
        if layout_valid and visual_artifact.status == "refused":
            failures.append("valid_layout_reported_refused")
        if not layout_valid and visual_artifact.status != "refused":
            failures.append("layout_failure_reported_as_render")
        stale_language_valid = True
        if conclusion.status is ClaimStatus.STALE:
            payload = _decode_json_artifact(text_artifact)
            body = str(payload.get("body", "")).lower()
            stale_language_valid = (
                "cannot be established" in body and "stale" in body
                and not re.search(r"\b(is|has) (safe|low|stable|healthy)\b", body)
            )
            if not stale_language_valid:
                failures.append("stale_claim_presented_as_current")
        residual_provenance_valid = True
        if conclusion.status is ClaimStatus.RESIDUAL_REQUIRED:
            residual_provenance_valid = not conclusion.rule_ref and conclusion.confidence_class.endswith("missing")
            if not residual_provenance_valid:
                failures.append("residual_claim_masquerades_as_rule_proven")
        visual_intent_valid = scene_plan.visual_intent_fulfilled
        scene_semantically_valid = not any(item.startswith("primitive_") or item == "visual_unknown_claim_ref" for item in failures)
        scene_render_valid = visual_bytes_valid and layout_valid and visual_artifact.status in {"rendered", "placeholder_rendered"}
        current_claim_valid = conclusion.current_claim_allowed and conclusion.status is ClaimStatus.SUPPORTED
        joined = not failures
        if joined and current_claim_valid and scene_render_valid and visual_intent_valid:
            joined_status = JoinedStatus.COMPOSED
        elif text_bytes_valid or scene_semantically_valid:
            joined_status = JoinedStatus.PARTIAL
        else:
            joined_status = JoinedStatus.REFUSED
        receipt_core = {
            "beast_object_type": "deterministic_cross_modal_joined_receipt",
            "version": "1.0",
            "scenario_id": scenario.scenario_id,
            "family": graph.family.value,
            "request_digest": scenario.request_digest,
            "proof_graph_digest": graph.graph_digest,
            "text_frame_digest": text_frame.frame_digest,
            "scene_plan_digest": scene_plan.plan_digest,
            "text_artifact_digest": text_artifact.digest,
            "text_artifact_media_type": text_artifact.media_type,
            "text_artifact_bytes": text_artifact.length,
            "rendered_artifact_digest": visual_artifact.digest,
            "rendered_artifact_media_type": visual_artifact.media_type,
            "rendered_artifact_bytes": visual_artifact.length,
            "visual_render_status": visual_artifact.status,
            "visual_failure_class": visual_artifact.failure_class,
            "residual_packet_digests": tuple(packet.packet_digest for packet in residuals),
            "provider_calls_used": 0,
            "provider_policy": scenario.provider_policy,
            "phase_trace": (
                "proof_graph_compiled", "text_frame_realized", "scene_plan_compiled",
                "text_artifact_rendered", "visual_artifact_rendered", "joined_verified",
            ),
            "proof_first": proof_first,
            "proof_graph_valid": not any("claim_ref" in item or "graph_digest" in item for item in failures),
            "text_semantically_valid": text_bytes_valid and stale_language_valid,
            "scene_semantically_valid": scene_semantically_valid,
            "scene_render_valid": scene_render_valid,
            "visual_intent_fulfilled": visual_intent_valid,
            "current_claim_valid": current_claim_valid,
            "residual_provenance_valid": residual_provenance_valid,
            "joined_verification": joined,
            "status": joined_status.value,
            "failure_classes": tuple(failures),
            "claim_boundary": (
                "This receipt proves bounded deterministic composition only for the supplied verified facts, "
                "rules, policies, temporal evidence, structured text frame, deterministic scene plan, and exact "
                "artifact bytes. It grants no execution authority and makes no unsupported causal claim."
            ),
        }
        receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
        verification = {
            "proof_first": proof_first,
            "text_bytes_valid": text_bytes_valid,
            "visual_bytes_valid": visual_bytes_valid,
            "layout_valid": layout_valid,
            "stale_language_valid": stale_language_valid,
            "residual_provenance_valid": residual_provenance_valid,
            "scene_semantically_valid": scene_semantically_valid,
            "scene_render_valid": scene_render_valid,
            "joined_verification": joined,
            "failure_classes": tuple(failures),
            "verification_digest": sha256_digest({
                "scenario_id": scenario.scenario_id,
                "proof_graph_digest": graph.graph_digest,
                "receipt_digest": receipt["receipt_digest"],
                "failures": tuple(failures),
            }),
        }
        return receipt, verification


class DeterministicIntelligenceEngine:
    def __init__(self) -> None:
        self.proof_compiler = ProofCompiler()
        self.text_realizer = TextRealizer()
        self.scene_compiler = SceneCompiler()
        self.svg_renderer = SvgRenderer()
        self.verifier = JoinedVerifier()

    def compose(self, scenario: Scenario) -> CompositionResult:
        graph, residuals = self.proof_compiler.compile(scenario)
        text_frame = self.text_realizer.realize(graph, residuals)
        scene_plan = self.scene_compiler.compile(scenario, graph, residuals)
        text_artifact = self.text_realizer.render(text_frame)
        visual_artifact = self.svg_renderer.render(graph, scene_plan)
        receipt, verification = self.verifier.verify(
            scenario, graph, text_frame, scene_plan, text_artifact, visual_artifact, residuals,
        )
        return CompositionResult(
            scenario=scenario,
            proof_graph=graph,
            text_frame=text_frame,
            scene_plan=scene_plan,
            text_artifact=text_artifact,
            visual_artifact=visual_artifact,
            residual_packets=residuals,
            joined_receipt=receipt,
            verification=verification,
        )

    def verify_artifacts(
        self,
        result: CompositionResult,
        *,
        text_bytes: bytes | None = None,
        visual_bytes: bytes | None = None,
    ) -> Mapping[str, Any]:
        text = replace(result.text_artifact, content=result.text_artifact.content if text_bytes is None else text_bytes)
        visual = replace(result.visual_artifact, content=result.visual_artifact.content if visual_bytes is None else visual_bytes)
        _, verification = self.verifier.verify(
            result.scenario,
            result.proof_graph,
            result.text_frame,
            result.scene_plan,
            text,
            visual,
            result.residual_packets,
        )
        return verification


def validate_residual_response(packet: ResidualPacket, response: Mapping[str, Any]) -> dict[str, Any]:
    encoded = canonical_json(response).encode("utf-8")
    present = {str(key) for key in response}
    forbidden = sorted(present.intersection(packet.forbidden_output_fields))
    unknown = sorted(present.difference(packet.allowed_output_fields))
    missing = sorted(set(packet.unresolved_fields).difference(present))
    oversize = len(encoded) > packet.max_output_bytes
    accepted = not forbidden and not unknown and not missing and not oversize
    return {
        "beast_object_type": "residual_scope_validation",
        "residual_id": packet.residual_id,
        "packet_digest": packet.packet_digest,
        "accepted": accepted,
        "forbidden_fields": tuple(forbidden),
        "unknown_fields": tuple(unknown),
        "missing_fields": tuple(missing),
        "oversize": oversize,
        "response_digest": sha256_digest(response),
        "validation_digest": sha256_digest({
            "packet_digest": packet.packet_digest,
            "accepted": accepted,
            "forbidden": forbidden,
            "unknown": unknown,
            "missing": missing,
            "oversize": oversize,
        }),
    }


def result_to_dict(result: CompositionResult, *, include_artifact_text: bool = False) -> dict[str, Any]:
    payload = {
        "scenario": _canonical(result.scenario),
        "proof_graph": {**_canonical(result.proof_graph), "graph_digest": result.proof_graph.graph_digest},
        "text_frame": {**_canonical(result.text_frame), "frame_digest": result.text_frame.frame_digest},
        "scene_plan": {**_canonical(result.scene_plan), "plan_digest": result.scene_plan.plan_digest},
        "text_artifact": {
            "media_type": result.text_artifact.media_type,
            "digest": result.text_artifact.digest,
            "bytes": result.text_artifact.length,
            "status": result.text_artifact.status,
        },
        "visual_artifact": {
            "media_type": result.visual_artifact.media_type,
            "digest": result.visual_artifact.digest,
            "bytes": result.visual_artifact.length,
            "status": result.visual_artifact.status,
            "failure_class": result.visual_artifact.failure_class,
        },
        "residual_packets": [
            {**_canonical(packet), "packet_digest": packet.packet_digest}
            for packet in result.residual_packets
        ],
        "joined_receipt": dict(result.joined_receipt),
        "verification": dict(result.verification),
    }
    if include_artifact_text:
        payload["text_artifact"]["content"] = result.text_artifact.content.decode("utf-8")
        payload["visual_artifact"]["content"] = result.visual_artifact.content.decode("utf-8")
    return payload


def _fact(scenario: Scenario, fact_type: str, subject: str) -> CapabilityFact | None:
    for fact in scenario.facts:
        if fact.fact_type == fact_type and fact.subject == subject:
            return fact
    return None


def _relation_fact(scenario: Scenario, fact_type: str, subject: str, object_: str) -> CapabilityFact | None:
    for fact in scenario.facts:
        if fact.fact_type == fact_type and fact.subject == subject and fact.object == object_:
            return fact
    return None


def _rule(scenario: Scenario, predicate: str) -> CausalRule | None:
    for rule in scenario.rules:
        if rule.family is scenario.family and rule.predicate == predicate:
            return rule
    return None


def _value(fact: CapabilityFact | None) -> Mapping[str, Any]:
    if fact is None or not isinstance(fact.value, Mapping):
        return {}
    return fact.value


def _scenario_stale(scenario: Scenario) -> bool:
    return bool(scenario.metadata.get("temporal_state") == "stale")


def _status_for_fact(fact: CapabilityFact | None, stale: bool) -> ClaimStatus:
    if fact is None:
        return ClaimStatus.UNSUPPORTED
    return ClaimStatus.STALE if stale else ClaimStatus.SUPPORTED


def _direct_claim(scenario: Scenario, suffix: str, fact: CapabilityFact | None, *, status: ClaimStatus) -> ProofClaim:
    return ProofClaim(
        claim_id=f"claim:{scenario.scenario_id}:{suffix}",
        claim_type="observed_fact",
        subject=fact.subject if fact else scenario.source,
        predicate=fact.predicate if fact else suffix,
        object=fact.object if fact else "",
        status=status,
        confidence_class="observed" if fact is not None else "missing_verified_fact",
        fact_refs=(fact.fact_digest,) if fact is not None else (scenario.request_digest,),
        snapshot_ref=fact.evidence_digest if fact and fact.evidence_digest else scenario.request_digest,
        current_claim_allowed=status is ClaimStatus.SUPPORTED,
        metadata={"fact_type": fact.fact_type if fact else "missing"},
    )


def _claim_by_suffix(graph: CanonicalProofGraph, suffix: str) -> ProofClaim:
    tail = ":" + suffix
    for claim in graph.claims:
        if claim.claim_id.endswith(tail):
            return claim
    raise KeyError(suffix)


def _primitive(
    primitive_id: str,
    primitive_type: str,
    claim_ref: str,
    evidence_state: ClaimStatus,
    x: int,
    y: int,
    width: int,
    height: int,
    label: str,
    metadata: Mapping[str, Any] | None = None,
) -> ScenePrimitive:
    return ScenePrimitive(
        primitive_id=primitive_id,
        primitive_type=primitive_type,
        claim_ref=claim_ref,
        evidence_state=evidence_state,
        x=x,
        y=y,
        width=width,
        height=height,
        label=label,
        metadata=dict(metadata or {}),
    )


def _layout_failures(plan: ScenePlan) -> tuple[str, ...]:
    failures: list[str] = []
    for primitive in plan.primitives:
        if primitive.x < 0 or primitive.y < 0 or primitive.width <= 0 or primitive.height <= 0:
            failures.append(primitive.primitive_id + ":invalid_geometry")
        elif primitive.x + primitive.width > plan.canvas_width or primitive.y + primitive.height > plan.canvas_height:
            failures.append(primitive.primitive_id + ":out_of_bounds")
    return tuple(failures)


def _svg_primitive(primitive: ScenePrimitive) -> list[str]:
    state = primitive.evidence_state.value
    if state == ClaimStatus.SUPPORTED.value:
        stroke, fill = "#4df0b5", "#102b2a"
    elif state == ClaimStatus.STALE.value:
        stroke, fill = "#f4c95d", "#312a18"
    elif state in {ClaimStatus.UNSUPPORTED.value, ClaimStatus.RESIDUAL_REQUIRED.value}:
        stroke, fill = "#ff8d7a", "#301b1e"
    else:
        stroke, fill = "#ff5f6d", "#35151b"
    dash = ' stroke-dasharray="8 6"' if state in {ClaimStatus.UNSUPPORTED.value, ClaimStatus.RESIDUAL_REQUIRED.value, ClaimStatus.STALE.value} else ""
    label = html.escape(primitive.label)
    claim = html.escape(primitive.claim_ref)
    return [
        f'<g id="{html.escape(primitive.primitive_id)}" data-claim-ref="{claim}" data-evidence-state="{state}">',
        f'<rect x="{primitive.x}" y="{primitive.y}" width="{primitive.width}" height="{primitive.height}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>',
        f'<text x="{primitive.x + 12}" y="{primitive.y + 28}" fill="#eef8fa" font-family="monospace" font-size="14">{label}</text>',
        f'<text x="{primitive.x + 12}" y="{primitive.y + 49}" fill="{stroke}" font-family="monospace" font-size="10">{html.escape(primitive.primitive_type)} · {state}</text>',
        '</g>',
    ]


def _decode_json_artifact(artifact: Artifact) -> Mapping[str, Any]:
    try:
        value = json.loads(artifact.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def make_fact(fact_type: str, subject: str, predicate: str, value: Mapping[str, Any], *, object: str = "") -> CapabilityFact:
    seed = {"fact_type": fact_type, "subject": subject, "predicate": predicate, "object": object, "value": value}
    return CapabilityFact(
        fact_id=f"fact:{fact_type}:{subject}:{predicate}:{object}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        value=dict(value),
        evidence_digest=sha256_digest(seed),
        observed_at="2026-08-03T15:30:00+00:00",
    )


def make_rule(family: Family, predicate: str, parameters: Mapping[str, Any] | None = None) -> CausalRule:
    return CausalRule(
        rule_id=f"rule:{family.value}:{predicate}:v1",
        family=family,
        predicate=predicate,
        parameters=dict(parameters or {}),
    )


def make_policy(family: Family, parameters: Mapping[str, Any]) -> PolicyConstraint:
    return PolicyConstraint(
        policy_id=f"policy:{family.value}:v1",
        family=family,
        parameters=dict(parameters),
    )


def default_visual_assets() -> dict[str, str]:
    return {
        f"{family.value}:status_badge": sha256_digest({"promoted_asset": family.value, "version": 1})
        for family in Family
    }
