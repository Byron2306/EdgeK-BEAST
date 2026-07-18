"""DevSecOps release-chain orchestration over the Control Evidence Graph."""
from __future__ import annotations

from typing import Any, Dict

from app.kernel.evidence.control_graph import ControlEvidenceGraph, EvidenceNode


class ReleaseChain:
    def __init__(self, graph: ControlEvidenceGraph | None = None):
        self.graph = graph or ControlEvidenceGraph()

    def record(self, stage: str, receipt: Dict[str, Any], *, parent: EvidenceNode | None = None) -> EvidenceNode:
        node = self.graph.add(stage, receipt)
        if parent is not None:
            self.graph.link(parent, "PRODUCES", node)
        return node

    def audit(self, query: str) -> tuple[EvidenceNode, ...]:
        if query == "production_without_two_person_approval":
            return tuple(node for node in self.graph.query("deployment") if not node.receipt.get("two_person_approval"))
        if query == "approved_digest_mismatch":
            return tuple(node for node in self.graph.query("deployment") if node.receipt.get("approved_digest") != node.receipt.get("deployed_digest"))
        if query == "privileged_changes":
            return tuple(node for node in self.graph.query("commit") if node.receipt.get("privileged"))
        if query == "missing_evidence":
            return tuple(node for node in self.graph.nodes.values() if not node.receipt)
        raise ValueError("unknown evidence audit query")

