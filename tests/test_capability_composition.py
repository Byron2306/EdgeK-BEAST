from pathlib import Path

from app.kernel.compute.capability_composition import (
    CapabilityCompositionPlane,
    CapabilityFactType,
    CompositionQuestion,
    LearnedCapabilityFact,
)
from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.residual_contracts import sha256_digest


def test_capability_composition_answers_unseen_restart_question_from_components():
    receipt = CapabilityCompositionPlane().compose_restart_destabilization(
        _question(),
        _facts(include_causal_rule=True),
    )

    assert receipt["status"] == "composed"
    assert receipt["answer"]["risk_class"] == "low"
    assert receipt["residual_used"] is False
    assert not receipt["unsupported_causal_gaps"]
    assert set(receipt["component_fact_digests"]) == {
        "source_health",
        "target_health",
        "dependency",
        "restart_policy",
        "current_evidence",
        "causal_rule",
    }
    assert receipt["receipt_digest"].startswith("sha256:")


def test_capability_composition_follows_transitive_dependency_chain():
    receipt = CapabilityCompositionPlane().compose_restart_destabilization(
        _question(),
        (
            _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
            _fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
            _fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "commons", "depends_on", {"relation": "depends_on"}, object="gateway"),
            _fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "gateway", "depends_on", {"relation": "depends_on"}, object="beast"),
            _fact(CapabilityFactType.RESTART_POLICY, "beast", "restart_policy", {"mode": "rolling_with_healthcheck"}),
            _fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "restart_count": 0}),
            _fact(
                CapabilityFactType.RESTART_CAUSAL_RULE,
                "service_restart",
                "causal_rule",
                {"rule": "rolling_restart_compatible_with_dependents"},
                object="dependent_service",
            ),
        ),
    )

    assert receipt["status"] == "composed"
    assert receipt["answer"]["risk_class"] == "low"
    assert "transitive dependency path" in receipt["answer"]["summary"]
    assert {"dependency_edge_0", "dependency_edge_1"} <= set(receipt["component_fact_digests"])


def test_capability_composition_refuses_unsupported_causal_gap_without_residual():
    receipt = CapabilityCompositionPlane().compose_restart_destabilization(
        _question(),
        _facts(include_causal_rule=False),
    )

    assert receipt["status"] == "unsupported"
    assert receipt["composed"] is False
    assert receipt["unsupported_causal_gaps"] == ("restart_destabilization_causal_rule",)
    assert receipt["residual_payload"]["unresolved_fields"] == [
        "destabilization_risk_class",
        "causal_rationale",
    ]
    assert receipt["residual_payload"]["residual_scope"] == "causal_gap_only"
    assert "component_fact_digests" in receipt["residual_payload"]


def test_capability_composition_routes_only_unresolved_fields_to_residual():
    seen = {}

    def worker(payload):
        seen.update(payload)
        return {
            "destabilization_risk_class": "low",
            "causal_rationale": "Bounded residual: rolling health-checked restart is compatible with the declared dependency.",
        }

    receipt = CapabilityCompositionPlane().compose_restart_destabilization(
        _question(),
        _facts(include_causal_rule=False),
        residual_worker=worker,
    )

    assert receipt["status"] == "residual_composed"
    assert receipt["answer"]["risk_class"] == "low"
    assert receipt["residual_used"] is True
    assert receipt["residual_receipt"]["accepted"] is True
    assert seen["unresolved_fields"] == ["destabilization_risk_class", "causal_rationale"]
    assert seen["residual_scope"] == "causal_gap_only"
    assert set(seen["allowed_output"]) == {"destabilization_risk_class", "causal_rationale"}


def test_capability_composition_answers_traffic_shift_capacity_chain():
    receipt = CapabilityCompositionPlane().compose_traffic_shift_safety(
        _traffic_question(),
        _traffic_facts(include_shift_policy=True),
    )

    assert receipt["status"] == "composed"
    assert receipt["answer"]["risk_class"] == "low"
    assert set(receipt["component_fact_digests"]) == {
        "source_health",
        "target_health",
        "traffic_route",
        "target_headroom",
        "current_evidence",
        "shift_policy",
    }


def test_capability_composition_routes_only_capacity_gap_to_residual():
    seen = {}

    def worker(payload):
        seen.update(payload)
        return {
            "capacity_risk_class": "low",
            "capacity_rationale": "Bounded residual: declared headroom can absorb the requested shift under local policy.",
        }

    receipt = CapabilityCompositionPlane().compose_traffic_shift_safety(
        _traffic_question(),
        _traffic_facts(include_shift_policy=False),
        residual_worker=worker,
    )

    assert receipt["status"] == "residual_composed"
    assert receipt["answer"]["risk_class"] == "low"
    assert seen["residual_scope"] == "capacity_gap_only"
    assert seen["unresolved_fields"] == ["capacity_risk_class", "capacity_rationale"]
    assert set(seen["allowed_output"]) == {"capacity_risk_class", "capacity_rationale"}


def test_capability_composition_answers_deployment_safety_chain():
    receipt = CapabilityCompositionPlane().compose_deployment_safety(
        _deployment_question(),
        _deployment_facts(include_causal_rule=True),
    )

    assert receipt["status"] == "composed"
    assert receipt["answer"]["risk_class"] == "low"
    assert set(receipt["component_fact_digests"]) == {
        "service_health",
        "deployment_policy",
        "rollback_policy",
        "slo_budget",
        "current_evidence",
        "deployment_causal_rule",
    }


def test_capability_composition_refuses_deployment_blast_radius_gap():
    receipt = CapabilityCompositionPlane().compose_deployment_safety(
        _deployment_question(),
        _deployment_facts(include_causal_rule=False),
    )

    assert receipt["status"] == "unsupported"
    assert receipt["unsupported_causal_gaps"] == ("deployment_blast_radius_rule",)
    assert receipt["residual_payload"]["residual_scope"] == "deployment_gap_only"
    assert receipt["residual_payload"]["unresolved_fields"] == ["deployment_risk_class", "deployment_rationale"]


def test_compute_plane_records_capability_composition_learning(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    result = plane.compose_restart_destabilization_risk(
        {"question": _question().to_dict(), "facts": [fact.to_dict() for fact in _facts(include_causal_rule=True)]},
        interface="test",
    )
    learning = plane.capability_learning_report()

    assert result["status"] == "composed"
    assert result["evidence_node_id"].startswith("sha256:")
    assert learning["by_capability_type"]["capability_composition"] == 1
    assert learning["capabilities"][0]["reuse_hits"] >= 5


def test_compute_plane_records_multiple_capability_composition_families(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    restart = plane.compose_restart_destabilization_risk(
        {"question": _question().to_dict(), "facts": [fact.to_dict() for fact in _facts(include_causal_rule=True)]},
        interface="test",
    )
    traffic = plane.compose_traffic_shift_safety(
        {"question": _traffic_question().to_dict(), "facts": [fact.to_dict() for fact in _traffic_facts(include_shift_policy=True)]},
        interface="test",
    )
    deployment = plane.compose_deployment_safety(
        {"question": _deployment_question().to_dict(), "facts": [fact.to_dict() for fact in _deployment_facts(include_causal_rule=True)]},
        interface="test",
    )
    learning = plane.capability_learning_report()

    assert restart["status"] == traffic["status"] == deployment["status"] == "composed"
    assert learning["by_capability_type"]["capability_composition"] == 3
    assert {item["capability_id"].split(":", 1)[0] for item in learning["capabilities"]} >= {
        "restart-destabilization",
        "traffic-shift",
        "deployment-safety",
    }


def _question() -> CompositionQuestion:
    return CompositionQuestion(
        question_id="question:restart-beast-affects-commons",
        source_service="beast",
        target_service="commons",
        utterance="Could restarting BEAST destabilize Commons?",
    )


def _traffic_question() -> CompositionQuestion:
    return CompositionQuestion(
        question_id="question:shift-beast-traffic-to-commons",
        source_service="beast",
        target_service="commons",
        question_type="traffic_shift_safety",
        utterance="Can BEAST traffic shift to Commons safely?",
    )


def _deployment_question() -> CompositionQuestion:
    return CompositionQuestion(
        question_id="question:deploy-beast-production",
        source_service="beast",
        target_service="production",
        question_type="deployment_safety",
        utterance="Can we deploy BEAST safely right now?",
    )


def _facts(*, include_causal_rule: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.DEPENDENCY_TOPOLOGY, "commons", "depends_on", {"relation": "depends_on"}, object="beast"),
        _fact(CapabilityFactType.RESTART_POLICY, "beast", "restart_policy", {"mode": "rolling_with_healthcheck"}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "restart_count": 0}),
    ]
    if include_causal_rule:
        facts.append(
            _fact(
                CapabilityFactType.RESTART_CAUSAL_RULE,
                "service_restart",
                "causal_rule",
                {"rule": "rolling_restart_compatible_with_dependents"},
                object="dependent_service",
            )
        )
    return tuple(facts)


def _traffic_facts(*, include_shift_policy: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "degraded"}),
        _fact(CapabilityFactType.SERVICE_HEALTH, "commons", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.TRAFFIC_ROUTE, "beast", "can_shift_to", {"route": "weighted"}, object="commons"),
        _fact(CapabilityFactType.RESOURCE_HEADROOM, "commons", "headroom", {"available_percent": 40}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "beast", "current_evidence", {"state": "stable", "traffic_to_shift_percent": 15}),
    ]
    if include_shift_policy:
        facts.append(
            _fact(
                CapabilityFactType.TRAFFIC_SHIFT_POLICY,
                "beast",
                "shift_policy",
                {"max_shift_percent": 25, "requires_target_healthy": True},
                object="commons",
            )
        )
    return tuple(facts)


def _deployment_facts(*, include_causal_rule: bool) -> tuple[LearnedCapabilityFact, ...]:
    facts = [
        _fact(CapabilityFactType.SERVICE_HEALTH, "beast", "health", {"state": "healthy"}),
        _fact(CapabilityFactType.DEPLOYMENT_POLICY, "beast", "deployment_policy", {"strategy": "canary"}),
        _fact(CapabilityFactType.ROLLBACK_POLICY, "beast", "rollback_policy", {"automatic": True, "max_rollback_seconds": 60}),
        _fact(CapabilityFactType.SLO_BUDGET, "production", "slo_budget", {"remaining_error_budget_percent": 83}),
        _fact(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", {"state": "stable", "active_incidents": 0}),
    ]
    if include_causal_rule:
        facts.append(
            _fact(
                CapabilityFactType.DEPLOYMENT_CAUSAL_RULE,
                "service_deployment",
                "causal_rule",
                {"rule": "canary_rollback_compatible_with_slo_budget"},
                object="production",
            )
        )
    return tuple(facts)


def _fact(
    fact_type: CapabilityFactType,
    subject: str,
    predicate: str,
    value,
    *,
    object: str = "",
) -> LearnedCapabilityFact:
    return LearnedCapabilityFact(
        fact_id=f"fact:{fact_type.value}:{subject}:{predicate}:{object}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object=object,
        value=value,
        evidence_digest=sha256_digest({"fact": fact_type.value, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    )
