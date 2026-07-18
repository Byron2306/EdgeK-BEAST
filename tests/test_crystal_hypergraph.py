from app.kernel.compute.crystal_hypergraph import CrystalHypergraph
from app.kernel.compute.heldout_replay import HeldOutReplayGate


def test_typed_hyperedge_requires_existing_nodes():
    graph = CrystalHypergraph()
    graph.add_node("task:port", "TaskPattern")
    graph.add_node("tool:sock_diag", "Tool")
    graph.add_node("crystal:repair", "Crystal")
    edge = graph.add_edge("REQUIRES", ("task:port", "tool:sock_diag"), "crystal:repair")
    assert edge.source_ids == ("task:port", "tool:sock_diag")


def test_held_out_replay_requires_all_variants():
    gate = HeldOutReplayGate()
    passed = gate.evaluate("crystal:repair", [1, 2, 3], lambda value: value != 2)
    assert passed.promoted is False
    succeeded = gate.evaluate("crystal:repair", [1, 2, 3], lambda value: value > 0)
    assert succeeded.promoted is True

def test_hypergraph_extracts_verified_equivalent_crystal():
    graph = CrystalHypergraph()
    graph.add_node("local", "Crystal"); graph.add_node("cloud", "Crystal")
    graph.add_equivalent_crystal(expression_id="local", equivalence_key="repair", cost=2, verified=True)
    graph.add_equivalent_crystal(expression_id="cloud", equivalence_key="repair", cost=10, verified=True)
    assert graph.extract_equivalent("repair").node_id == "local"
