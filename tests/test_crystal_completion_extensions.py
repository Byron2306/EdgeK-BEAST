from app.kernel.compute.causal_inference import infer_consensus_edges
from app.kernel.compute.crystal_verifier_synthesis import synthesize_verifier_plan
from app.kernel.compute.equivalence_engine import EGraph, RewriteRule


def test_egraph_saturates_a_declarative_commutativity_rule_and_extracts_costed_term():
    graph = EGraph()
    left = {"op": "join", "args": ["a", "b"]}
    right = {"op": "join", "args": ["b", "a"]}
    graph.add(left)
    result = graph.saturate([RewriteRule("join_commutes", left, right)])
    assert result["saturated"] is True
    assert graph.equivalent(left, right)
    assert graph.extract(left, cost=lambda item: 0 if item == right else 1) == right


def test_consensus_causality_requires_repetition_and_explicit_evidence():
    edges = infer_consensus_edges([
        [{"id": "read", "writes": "artifact"}, {"id": "verify", "reads": "artifact"}],
        [{"id": "read", "writes": "artifact"}, {"id": "verify", "reads": "artifact"}],
        [{"id": "other", "writes": "different"}],
    ])
    assert any(edge.source == "read" and edge.target == "verify" and edge.reason == "reads" for edge in edges)
    assert not any(edge.reason == "ordered_episode" for edge in edges)


def test_verifier_synthesis_is_declarative_sealed_and_covers_negative_conditions():
    plan = synthesize_verifier_plan(
        [{"operation": "service.verify", "result": "passed", "phase": "verification", "requires": ["socket:ready"]}],
        postconditions=["service.verify:passed"], negative_conditions=["port:conflict"], evidence=["event:a"],
    )
    payload = plan.to_dict()
    assert payload["contains_executable_code"] is False
    assert payload["plan_digest"]
    assert any(check["kind"] == "negative_condition_absent" for check in payload["checks"])
