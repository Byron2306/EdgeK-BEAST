"""Typed causal graph for proof-carrying crystals."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple
from app.kernel.compute.equivalence_engine import EqualitySaturation, EquivalentAlternative


NODE_TYPES = {"TaskPattern", "Crystal", "Tool", "Skill", "Dataset", "Model", "ProcessProfile", "SocketTopology", "MemoryProfile", "Policy", "Verifier", "Artifact", "FailurePattern"}
EDGE_TYPES = {"REQUIRES", "PRODUCES", "VERIFIED_BY", "OBSERVED_BY", "COMPOSES_WITH", "CONFLICTS_WITH", "EQUIVALENT_TO", "SPECIALISES", "SUPERSEDES", "FAILED_UNDER", "SAFE_UNDER", "DISPLACED", "DERIVED_FROM"}


@dataclass(frozen=True)
class HyperNode:
    node_id: str
    node_type: str


@dataclass(frozen=True)
class HyperEdge:
    edge_type: str
    source_ids: Tuple[str, ...]
    target_id: str


class CrystalHypergraph:
    def __init__(self):
        self.nodes: Dict[str, HyperNode] = {}
        self.edges: list[HyperEdge] = []
        self.equivalences = EqualitySaturation()

    def add_equivalent_crystal(self, *, expression_id: str, equivalence_key: str, cost: float, verified: bool = False, payload=None) -> None:
        if expression_id not in self.nodes or self.nodes[expression_id].node_type != "Crystal":
            raise ValueError("equivalent expression must reference a Crystal node")
        self.equivalences.add(EquivalentAlternative(expression_id, equivalence_key, cost, verified, payload))

    def extract_equivalent(self, equivalence_key: str) -> HyperNode:
        choice = self.equivalences.extract(equivalence_key)
        return self.nodes[choice.expression_id]

    def add_node(self, node_id: str, node_type: str) -> HyperNode:
        if node_type not in NODE_TYPES or not node_id:
            raise ValueError("invalid hypergraph node")
        node = HyperNode(node_id, node_type)
        self.nodes[node_id] = node
        return node

    def add_edge(self, edge_type: str, source_ids: Iterable[str], target_id: str) -> HyperEdge:
        sources = tuple(source_ids)
        if edge_type not in EDGE_TYPES or not sources or target_id not in self.nodes or any(item not in self.nodes for item in sources):
            raise ValueError("invalid hypergraph edge")
        edge = HyperEdge(edge_type, sources, target_id)
        self.edges.append(edge)
        return edge
