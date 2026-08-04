"""Verified capability composition for bounded operational questions.

This is the bridge between replay and inference-through-components.  The
module grows by narrow question families:

    "Could restarting service A destabilize service B?"
    "Can traffic be shifted from service A to service B safely?"
    "Is deploying service A safe under current rollback/SLO evidence?"

It composes typed, digest-bound learned facts and refuses unsupported gaps.
If a bounded residual worker is supplied, only explicitly unresolved fields are
sent to that worker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


class CapabilityFactType(str, Enum):
    SERVICE_HEALTH = "service_health"
    DEPENDENCY_TOPOLOGY = "dependency_topology"
    RESTART_POLICY = "restart_policy"
    CURRENT_EVIDENCE = "current_evidence"
    RESTART_CAUSAL_RULE = "restart_causal_rule"
    TRAFFIC_ROUTE = "traffic_route"
    TRAFFIC_SHIFT_POLICY = "traffic_shift_policy"
    RESOURCE_HEADROOM = "resource_headroom"
    DEPLOYMENT_POLICY = "deployment_policy"
    ROLLBACK_POLICY = "rollback_policy"
    SLO_BUDGET = "slo_budget"
    DEPLOYMENT_CAUSAL_RULE = "deployment_causal_rule"


class CompositionStatus(str, Enum):
    COMPOSED = "composed"
    RESIDUAL_COMPOSED = "residual_composed"
    UNSUPPORTED = "unsupported"
    REFUTED = "refuted"


@dataclass(frozen=True, slots=True)
class LearnedCapabilityFact:
    fact_id: str
    fact_type: CapabilityFactType
    subject: str
    predicate: str
    value: Any
    evidence_digest: str
    object: str = ""
    authority: str = "read_verified"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fact_id.strip() or not self.subject.strip() or not self.predicate.strip():
            raise ValueError("learned capability facts require fact_id, subject, and predicate")
        if not isinstance(self.fact_type, CapabilityFactType):
            object.__setattr__(self, "fact_type", CapabilityFactType(self.fact_type))
        validate_digest(self.evidence_digest, field_name="evidence_digest")
        canonical_json(self.value)
        canonical_json(self.metadata)

    @property
    def fact_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fact_type": self.fact_type.value, "fact_digest": self.fact_digest}


@dataclass(frozen=True, slots=True)
class CompositionQuestion:
    question_id: str
    source_service: str
    target_service: str
    utterance: str = ""
    question_type: str = "restart_destabilization_risk"

    def __post_init__(self) -> None:
        if not self.question_id.strip() or not self.source_service.strip() or not self.target_service.strip():
            raise ValueError("composition question requires id, source_service, and target_service")

    @property
    def question_digest(self) -> str:
        return sha256_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "question_digest": self.question_digest}


class CapabilityCompositionPlane:
    """Compose verified capability facts into bounded operational answers."""

    def compose_restart_destabilization(
        self,
        question: CompositionQuestion | Mapping[str, Any],
        facts: tuple[LearnedCapabilityFact, ...] | list[LearnedCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        q = _coerce_question(question)
        learned = _coerce_facts(facts)
        dependency_path = _dependency_path(learned, source=q.source_service, target=q.target_service)
        components = _select_restart_components(q, learned)
        if components["dependency"] is None and dependency_path:
            components = dict(components)
            for index, edge in enumerate(dependency_path):
                components[f"dependency_edge_{index}"] = edge
        missing = _missing_components_for(components, ("source_health", "target_health", "restart_policy", "current_evidence"))
        unsupported: list[str] = []
        residual_payload: dict[str, Any] | None = None
        residual_receipt: dict[str, Any] | None = None
        residual_used = False
        answer: dict[str, Any] = {}
        status = CompositionStatus.UNSUPPORTED

        if missing:
            unsupported.extend(missing)
        elif components["dependency"] is None and not dependency_path:
            status = CompositionStatus.REFUTED
            answer = {
                "risk_class": "low",
                "summary": f"No dependency evidence says {q.target_service} depends on {q.source_service}.",
                "causal_claim": "no_dependency_path_found",
            }
        else:
            causal_rule = components.get("causal_rule")
            if causal_rule is None:
                unsupported.append("restart_destabilization_causal_rule")
                residual_payload = _residual_payload(
                    q,
                    components,
                    task_family="capability_composition.restart_destabilization",
                    unresolved_fields=("destabilization_risk_class", "causal_rationale"),
                    allowed_output={
                        "destabilization_risk_class": ("low", "elevated", "unknown"),
                        "causal_rationale": "string",
                    },
                    residual_scope="causal_gap_only",
                    forbidden_claims=("new_dependencies", "actions_taken", "unstated_evidence", "provider_savings"),
                )
                if residual_worker is not None:
                    residual_result = dict(residual_worker(residual_payload))
                    residual_receipt = _validate_residual_result(
                        residual_payload,
                        residual_result,
                        allowed_fields=("destabilization_risk_class", "causal_rationale"),
                        class_field="destabilization_risk_class",
                        rationale_field="causal_rationale",
                    )
                    answer = {
                        "risk_class": residual_result["destabilization_risk_class"],
                        "summary": residual_result["causal_rationale"],
                        "causal_claim": "bounded_residual_filled_missing_causal_rule",
                    }
                    status = CompositionStatus.RESIDUAL_COMPOSED
                    residual_used = True
                    unsupported.clear()
                else:
                    status = CompositionStatus.UNSUPPORTED
            else:
                risk_class, summary = _compose_restart_with_causal_rule(q, components)
                answer = {
                    "risk_class": risk_class,
                    "summary": summary,
                    "causal_claim": str(_value_mapping(causal_rule).get("rule") or causal_rule.value),
                }
                status = CompositionStatus.COMPOSED

        return _composition_receipt(
            q,
            status=status,
            answer=answer,
            components=components,
            unsupported=unsupported,
            residual_payload=residual_payload,
            residual_receipt=residual_receipt,
            residual_used=residual_used,
            claim_boundary=(
                "Bounded restart-risk composition only. The receipt may infer risk from verified health, "
                "dependency topology, restart policy, current evidence, and an explicit causal rule; "
                "otherwise it must refuse or route only declared unresolved causal fields to a residual worker."
            ),
        )

    def compose_traffic_shift_safety(
        self,
        question: CompositionQuestion | Mapping[str, Any],
        facts: tuple[LearnedCapabilityFact, ...] | list[LearnedCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        q = _coerce_question(question)
        learned = _coerce_facts(facts)
        components = _select_traffic_shift_components(q, learned)
        missing = _missing_components_for(components, ("source_health", "target_health", "traffic_route", "target_headroom", "current_evidence"))
        unsupported: list[str] = list(missing)
        residual_payload: dict[str, Any] | None = None
        residual_receipt: dict[str, Any] | None = None
        residual_used = False
        status = CompositionStatus.UNSUPPORTED
        answer: dict[str, Any] = {}

        if not missing and components["shift_policy"] is None:
            unsupported.append("traffic_shift_capacity_rule")
            residual_payload = _residual_payload(
                q,
                components,
                task_family="capability_composition.traffic_shift_safety",
                unresolved_fields=("capacity_risk_class", "capacity_rationale"),
                allowed_output={"capacity_risk_class": ("low", "elevated", "unknown"), "capacity_rationale": "string"},
                residual_scope="capacity_gap_only",
                forbidden_claims=("new_routes", "actions_taken", "unstated_capacity", "provider_savings"),
            )
            if residual_worker is not None:
                residual_result = dict(residual_worker(residual_payload))
                residual_receipt = _validate_residual_result(
                    residual_payload,
                    residual_result,
                    allowed_fields=("capacity_risk_class", "capacity_rationale"),
                    class_field="capacity_risk_class",
                    rationale_field="capacity_rationale",
                )
                answer = {
                    "risk_class": residual_result["capacity_risk_class"],
                    "summary": residual_result["capacity_rationale"],
                    "causal_claim": "bounded_residual_filled_missing_capacity_rule",
                }
                status = CompositionStatus.RESIDUAL_COMPOSED
                residual_used = True
                unsupported.clear()
        elif not missing:
            risk_class, summary = _compose_traffic_shift_with_policy(q, components)
            answer = {"risk_class": risk_class, "summary": summary, "causal_claim": "traffic_shift_capacity_composed"}
            status = CompositionStatus.COMPOSED

        return _composition_receipt(
            q,
            status=status,
            answer=answer,
            components=components,
            unsupported=unsupported,
            residual_payload=residual_payload,
            residual_receipt=residual_receipt,
            residual_used=residual_used,
            claim_boundary=(
                "Bounded traffic-shift composition only. The receipt may compare declared route, "
                "target health, headroom, observed shift demand, and shift policy; otherwise it "
                "must refuse or route only declared capacity fields to a residual worker."
            ),
        )

    def compose_deployment_safety(
        self,
        question: CompositionQuestion | Mapping[str, Any],
        facts: tuple[LearnedCapabilityFact, ...] | list[LearnedCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
        *,
        residual_worker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        q = _coerce_question(question)
        learned = _coerce_facts(facts)
        components = _select_deployment_components(q, learned)
        missing = _missing_components_for(
            components,
            ("service_health", "deployment_policy", "rollback_policy", "slo_budget", "current_evidence"),
        )
        unsupported: list[str] = list(missing)
        residual_payload: dict[str, Any] | None = None
        residual_receipt: dict[str, Any] | None = None
        residual_used = False
        status = CompositionStatus.UNSUPPORTED
        answer: dict[str, Any] = {}

        if not missing and components["deployment_causal_rule"] is None:
            unsupported.append("deployment_blast_radius_rule")
            residual_payload = _residual_payload(
                q,
                components,
                task_family="capability_composition.deployment_safety",
                unresolved_fields=("deployment_risk_class", "deployment_rationale"),
                allowed_output={"deployment_risk_class": ("low", "elevated", "unknown"), "deployment_rationale": "string"},
                residual_scope="deployment_gap_only",
                forbidden_claims=("new_dependencies", "actions_taken", "unstated_slo_budget", "provider_savings"),
            )
            if residual_worker is not None:
                residual_result = dict(residual_worker(residual_payload))
                residual_receipt = _validate_residual_result(
                    residual_payload,
                    residual_result,
                    allowed_fields=("deployment_risk_class", "deployment_rationale"),
                    class_field="deployment_risk_class",
                    rationale_field="deployment_rationale",
                )
                answer = {
                    "risk_class": residual_result["deployment_risk_class"],
                    "summary": residual_result["deployment_rationale"],
                    "causal_claim": "bounded_residual_filled_missing_deployment_rule",
                }
                status = CompositionStatus.RESIDUAL_COMPOSED
                residual_used = True
                unsupported.clear()
        elif not missing:
            risk_class, summary = _compose_deployment_with_rule(q, components)
            answer = {"risk_class": risk_class, "summary": summary, "causal_claim": "deployment_safety_composed"}
            status = CompositionStatus.COMPOSED

        return _composition_receipt(
            q,
            status=status,
            answer=answer,
            components=components,
            unsupported=unsupported,
            residual_payload=residual_payload,
            residual_receipt=residual_receipt,
            residual_used=residual_used,
            claim_boundary=(
                "Bounded deployment-safety composition only. The receipt may compare declared "
                "deployment strategy, rollback policy, service health, current evidence, SLO budget, "
                "and explicit deployment causal rule; otherwise it must refuse or route only declared "
                "deployment-risk fields to a residual worker."
            ),
        )


def _composition_receipt(
    question: CompositionQuestion,
    *,
    status: CompositionStatus,
    answer: Mapping[str, Any],
    components: Mapping[str, LearnedCapabilityFact | None],
    unsupported: list[str],
    residual_payload: Mapping[str, Any] | None,
    residual_receipt: Mapping[str, Any] | None,
    residual_used: bool,
    claim_boundary: str,
) -> dict[str, Any]:
    receipt = {
        "beast_object_type": "capability_composition_receipt",
        "version": "1.0",
        "question": question.to_dict(),
        "status": status.value,
        "composed": status in {CompositionStatus.COMPOSED, CompositionStatus.RESIDUAL_COMPOSED, CompositionStatus.REFUTED},
        "residual_used": residual_used,
        "answer": dict(answer),
        "component_fact_digests": {
            name: fact.fact_digest
            for name, fact in components.items()
            if isinstance(fact, LearnedCapabilityFact)
        },
        "component_evidence_digests": tuple(
            fact.evidence_digest
            for fact in components.values()
            if isinstance(fact, LearnedCapabilityFact)
        ),
        "unsupported_causal_gaps": tuple(unsupported),
        "residual_payload": dict(residual_payload or {}),
        "residual_receipt": dict(residual_receipt or {}),
        "claim_boundary": claim_boundary,
        "provider_calls_used": 0,
        "created_at": utc_now_iso(),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _coerce_question(question: CompositionQuestion | Mapping[str, Any]) -> CompositionQuestion:
    return question if isinstance(question, CompositionQuestion) else _question_from_mapping(question)


def _coerce_facts(
    facts: tuple[LearnedCapabilityFact, ...] | list[LearnedCapabilityFact] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> tuple[LearnedCapabilityFact, ...]:
    return tuple(item if isinstance(item, LearnedCapabilityFact) else _fact_from_mapping(item) for item in facts)


def _select_restart_components(question: CompositionQuestion, facts: tuple[LearnedCapabilityFact, ...]) -> dict[str, LearnedCapabilityFact | None]:
    source = question.source_service
    target = question.target_service
    return {
        "source_health": _first(facts, CapabilityFactType.SERVICE_HEALTH, subject=source),
        "target_health": _first(facts, CapabilityFactType.SERVICE_HEALTH, subject=target),
        "dependency": _dependency_fact(facts, source=source, target=target),
        "restart_policy": _first(facts, CapabilityFactType.RESTART_POLICY, subject=source),
        "current_evidence": _current_evidence(facts, source=source, target=target),
        "causal_rule": _causal_rule(facts, source=source, target=target),
    }


def _select_traffic_shift_components(question: CompositionQuestion, facts: tuple[LearnedCapabilityFact, ...]) -> dict[str, LearnedCapabilityFact | None]:
    source = question.source_service
    target = question.target_service
    return {
        "source_health": _first(facts, CapabilityFactType.SERVICE_HEALTH, subject=source),
        "target_health": _first(facts, CapabilityFactType.SERVICE_HEALTH, subject=target),
        "traffic_route": _relation_fact(facts, CapabilityFactType.TRAFFIC_ROUTE, source=source, target=target, predicates=("can_shift_to", "traffic_route")),
        "target_headroom": _first(facts, CapabilityFactType.RESOURCE_HEADROOM, subject=target),
        "current_evidence": _current_evidence(facts, source=source, target=target),
        "shift_policy": _relation_fact(facts, CapabilityFactType.TRAFFIC_SHIFT_POLICY, source=source, target=target, predicates=("shift_policy", "traffic_shift_policy")),
    }


def _select_deployment_components(question: CompositionQuestion, facts: tuple[LearnedCapabilityFact, ...]) -> dict[str, LearnedCapabilityFact | None]:
    source = question.source_service
    return {
        "service_health": _first(facts, CapabilityFactType.SERVICE_HEALTH, subject=source),
        "deployment_policy": _first(facts, CapabilityFactType.DEPLOYMENT_POLICY, subject=source),
        "rollback_policy": _first(facts, CapabilityFactType.ROLLBACK_POLICY, subject=source),
        "slo_budget": _first(facts, CapabilityFactType.SLO_BUDGET, subject=source) or _first(facts, CapabilityFactType.SLO_BUDGET, subject=question.target_service),
        "current_evidence": _current_evidence(facts, source=source, target=question.target_service),
        "deployment_causal_rule": _first(facts, CapabilityFactType.DEPLOYMENT_CAUSAL_RULE, subject=source)
        or _first(facts, CapabilityFactType.DEPLOYMENT_CAUSAL_RULE, subject="service_deployment"),
    }


def _question_from_mapping(value: Mapping[str, Any]) -> CompositionQuestion:
    allowed = {"question_id", "source_service", "target_service", "utterance", "question_type"}
    return CompositionQuestion(**{key: item for key, item in dict(value).items() if key in allowed})


def _fact_from_mapping(value: Mapping[str, Any]) -> LearnedCapabilityFact:
    allowed = {"fact_id", "fact_type", "subject", "predicate", "value", "evidence_digest", "object", "authority", "metadata"}
    return LearnedCapabilityFact(**{key: item for key, item in dict(value).items() if key in allowed})


def _missing_components_for(components: Mapping[str, LearnedCapabilityFact | None], names: tuple[str, ...]) -> list[str]:
    return [name for name in names if components.get(name) is None]


def _first(
    facts: tuple[LearnedCapabilityFact, ...],
    fact_type: CapabilityFactType,
    *,
    subject: str,
) -> LearnedCapabilityFact | None:
    for fact in facts:
        if fact.fact_type is fact_type and fact.subject == subject:
            return fact
    return None


def _dependency_fact(
    facts: tuple[LearnedCapabilityFact, ...],
    *,
    source: str,
    target: str,
) -> LearnedCapabilityFact | None:
    for fact in facts:
        if fact.fact_type is not CapabilityFactType.DEPENDENCY_TOPOLOGY:
            continue
        if fact.subject == target and fact.predicate == "depends_on" and fact.object == source:
            return fact
        if fact.subject == source and fact.predicate == "upstream_of" and fact.object == target:
            return fact
    return None


def _dependency_path(
    facts: tuple[LearnedCapabilityFact, ...],
    *,
    source: str,
    target: str,
) -> tuple[LearnedCapabilityFact, ...]:
    edges = tuple(fact for fact in facts if fact.fact_type is CapabilityFactType.DEPENDENCY_TOPOLOGY)
    frontier: list[tuple[str, tuple[LearnedCapabilityFact, ...]]] = [(target, ())]
    visited = {target}
    while frontier:
        current, path = frontier.pop(0)
        for edge in edges:
            if edge.subject != current or edge.predicate != "depends_on" or not edge.object:
                continue
            next_node = edge.object
            next_path = (*path, edge)
            if next_node == source:
                return next_path
            if next_node not in visited:
                visited.add(next_node)
                frontier.append((next_node, next_path))
    return ()


def _relation_fact(
    facts: tuple[LearnedCapabilityFact, ...],
    fact_type: CapabilityFactType,
    *,
    source: str,
    target: str,
    predicates: tuple[str, ...],
) -> LearnedCapabilityFact | None:
    for fact in facts:
        if fact.fact_type is fact_type and fact.subject == source and fact.object == target and fact.predicate in predicates:
            return fact
    return None


def _current_evidence(
    facts: tuple[LearnedCapabilityFact, ...],
    *,
    source: str,
    target: str,
) -> LearnedCapabilityFact | None:
    for fact in facts:
        if fact.fact_type is CapabilityFactType.CURRENT_EVIDENCE and fact.subject in {source, target, "runtime"}:
            return fact
    return None


def _causal_rule(
    facts: tuple[LearnedCapabilityFact, ...],
    *,
    source: str,
    target: str,
) -> LearnedCapabilityFact | None:
    for fact in facts:
        if fact.fact_type is not CapabilityFactType.RESTART_CAUSAL_RULE:
            continue
        if fact.subject in {source, "service_restart", "runtime"} and fact.object in {target, "dependent_service", ""}:
            return fact
    return None


def _compose_restart_with_causal_rule(
    question: CompositionQuestion,
    components: Mapping[str, LearnedCapabilityFact | None],
) -> tuple[str, str]:
    policy = components["restart_policy"]
    evidence = components["current_evidence"]
    rule = components["causal_rule"]
    assert policy is not None and evidence is not None and rule is not None
    mode = str(_value_mapping(policy).get("mode") or "")
    evidence_state = str(_value_mapping(evidence).get("state") or "")
    rule_name = str(_value_mapping(rule).get("rule") or "")
    topology = "transitive dependency path" if any(name.startswith("dependency_edge_") for name in components) else "direct dependency"
    if mode in {"rolling_with_healthcheck", "graceful_restart"} and evidence_state in {"stable", "healthy"} and "compatible" in rule_name:
        return (
            "low",
            f"Restarting {question.source_service} is low destabilization risk for {question.target_service}: topology shows a {topology}, but the restart policy is {mode}, current evidence is {evidence_state}, and the causal rule supports compatible rolling restarts.",
        )
    return (
        "elevated",
        f"Restarting {question.source_service} could destabilize {question.target_service}: {topology} is present and the restart policy/evidence do not prove a safe rolling restart.",
    )


def _compose_traffic_shift_with_policy(
    question: CompositionQuestion,
    components: Mapping[str, LearnedCapabilityFact | None],
) -> tuple[str, str]:
    target_health = components["target_health"]
    headroom = components["target_headroom"]
    evidence = components["current_evidence"]
    policy = components["shift_policy"]
    assert target_health is not None and headroom is not None and evidence is not None and policy is not None
    target_state = str(_value_mapping(target_health).get("state") or "")
    available_percent = _number(_value_mapping(headroom).get("available_percent"))
    demand_percent = _number(_value_mapping(evidence).get("traffic_to_shift_percent"))
    max_shift_percent = _number(_value_mapping(policy).get("max_shift_percent"))
    if target_state in {"healthy", "stable"} and available_percent >= demand_percent and demand_percent <= max_shift_percent:
        return (
            "low",
            f"Traffic shift from {question.source_service} to {question.target_service} is low risk: target is {target_state}, declared headroom is {available_percent:g}%, requested shift is {demand_percent:g}%, and policy allows up to {max_shift_percent:g}%.",
        )
    return (
        "elevated",
        f"Traffic shift from {question.source_service} to {question.target_service} is elevated risk: target health, declared headroom, requested shift, or policy limit does not prove safe capacity.",
    )


def _compose_deployment_with_rule(
    question: CompositionQuestion,
    components: Mapping[str, LearnedCapabilityFact | None],
) -> tuple[str, str]:
    health = components["service_health"]
    deployment = components["deployment_policy"]
    rollback = components["rollback_policy"]
    slo = components["slo_budget"]
    evidence = components["current_evidence"]
    rule = components["deployment_causal_rule"]
    assert health is not None and deployment is not None and rollback is not None and slo is not None and evidence is not None and rule is not None
    state = str(_value_mapping(health).get("state") or "")
    strategy = str(_value_mapping(deployment).get("strategy") or "")
    automatic_rollback = bool(_value_mapping(rollback).get("automatic"))
    error_budget = _number(_value_mapping(slo).get("remaining_error_budget_percent"))
    evidence_state = str(_value_mapping(evidence).get("state") or "")
    rule_name = str(_value_mapping(rule).get("rule") or "")
    if state in {"healthy", "stable"} and strategy in {"canary", "rolling"} and automatic_rollback and error_budget >= 20 and evidence_state in {"stable", "healthy"} and "compatible" in rule_name:
        return (
            "low",
            f"Deployment for {question.source_service} is low risk: service/evidence are stable, strategy is {strategy}, rollback is automatic, and remaining SLO budget is {error_budget:g}%.",
        )
    return (
        "elevated",
        f"Deployment for {question.source_service} is elevated risk: deployment strategy, rollback, current evidence, SLO budget, or causal rule does not prove a safe rollout.",
    )


def _residual_payload(
    question: CompositionQuestion,
    components: Mapping[str, LearnedCapabilityFact | None],
    *,
    task_family: str,
    unresolved_fields: tuple[str, ...],
    allowed_output: Mapping[str, Any],
    residual_scope: str,
    forbidden_claims: tuple[str, ...],
) -> dict[str, Any]:
    def value(name: str) -> Any:
        fact = components.get(name)
        return fact.value if isinstance(fact, LearnedCapabilityFact) else None

    payload = {
        "task_family": task_family,
        "question_digest": question.question_digest,
        "unresolved_fields": list(unresolved_fields),
        "allowed_output": dict(allowed_output),
        "component_fact_digests": {
            name: fact.fact_digest
            for name, fact in components.items()
            if isinstance(fact, LearnedCapabilityFact)
        },
        "bounded_context": {
            "dependency_relation": "target_depends_on_source" if components.get("dependency") or any(name.startswith("dependency_edge_") for name in components) else "no_direct_dependency",
            "restart_policy": value("restart_policy"),
            "current_evidence": value("current_evidence"),
            "source_health": value("source_health"),
            "target_health": value("target_health"),
            "traffic_route": value("traffic_route"),
            "target_headroom": value("target_headroom"),
            "shift_policy": value("shift_policy"),
            "service_health": value("service_health"),
            "deployment_policy": value("deployment_policy"),
            "rollback_policy": value("rollback_policy"),
            "slo_budget": value("slo_budget"),
        },
        "forbidden_claims": forbidden_claims,
        "residual_scope": residual_scope,
    }
    payload["residual_payload_digest"] = sha256_digest(payload)
    return payload


def _validate_residual_result(
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    allowed_fields: tuple[str, ...],
    class_field: str,
    rationale_field: str,
) -> dict[str, Any]:
    allowed = set(allowed_fields)
    extra = sorted(set(result) - allowed)
    if extra:
        raise ValueError("composition residual returned undeclared fields: " + ", ".join(extra))
    risk = str(result.get(class_field) or "")
    if risk not in {"low", "elevated", "unknown"}:
        raise ValueError(f"composition residual returned invalid {class_field}")
    rationale = str(result.get(rationale_field) or "").strip()
    if not rationale:
        raise ValueError(f"composition residual must return {rationale_field}")
    receipt = {
        "beast_object_type": "capability_composition_residual_receipt",
        "version": "1.0",
        "residual_payload_digest": str(payload.get("residual_payload_digest") or sha256_digest(payload)),
        "returned_fields": tuple(sorted(result)),
        "accepted": True,
        "created_at": utc_now_iso(),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _value_mapping(fact: LearnedCapabilityFact) -> Mapping[str, Any]:
    return fact.value if isinstance(fact.value, Mapping) else {"value": fact.value}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
