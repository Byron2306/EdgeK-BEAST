"""Unified Adaptive Router for BEAST.

Bridges the gap between raw provider routing and crystallized compute.
Routes tasks based on capability lattice analysis, embedding similarity,
and path-boundary fingerprint matching.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

# Assuming these exist in the codebase based on research
from app.kernel.compute.crystal_distillation import CrystalToAdapterDistiller
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.adapters.vector_adapters import VectorAdapterRegistry

logger = logging.getLogger(__name__)


class AdaptiveDispatcher:
    """Dynamically routes tasks to local specialists or crystals."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = Path(workspace_root or Path(__file__).resolve().parents[2])
        self.distiller = CrystalToAdapterDistiller(
            results_root=self.workspace_root / "benchmarks" / "results"
        )
        self.vector_registry = VectorAdapterRegistry()

    async def route(self, task_ir: EdgeKIR) -> Optional[Dict[str, Any]]:
        """
        Evaluate if a task can be dispatched to a local specialist adapter.
        
        Returns a dict with routing instructions if a local specialist is found,
        otherwise returns None to fall back to the standard Provider path.
        """
        # 1. Fetch current distillation evaluation
        eval_path = self.distiller.output_root / "adapter_candidate_evaluation_latest.json"
        if not eval_path.is_file():
            return None

        # 2. Check if the candidate is "ready"
        evaluation = self._load_json(eval_path)
        if evaluation.get("decision") != "candidate_ready_for_local_training":
            return None

        # 3. Discovery candidates are hypotheses.  A route requires an exact
        # structured capability contract, never a task-class-only or vector hit.
        node = self._find_best_lattice_node(task_ir)
        if not node:
            return None

        # 4. Gating Check: all current identity boundaries must match.
        if not self._verify_path_fingerprints(node, task_ir.metadata):
            logger.info("Routing demoted/stale due to fingerprint mismatch.")
            return None

        # 5. Route to local specialist
        return {
            "execution_mode": "local_specialist_adapter",
            "model_ref": f"ollama://beast-specialist-{node['node_id']}",
            "confidence_score": node.get("confidence", 1.0),
            "boundary_checks_passed": True,
        }

    def _find_best_lattice_node(self, task_ir: EdgeKIR) -> Optional[Dict[str, Any]]:
        lattice_path = self.distiller.output_root / "capability_lattice_latest.json"
        lattice = self._load_json(lattice_path)
        nodes = lattice.get("nodes", [])
        
        # Do not route on a broad task class.  Vector/semantic similarity may
        # rank candidates upstream, but equivalence is established here only by
        # the structured capability contract emitted by the semantic mapper.
        task_class = task_ir.metadata.get("task_class") or "general"
        contract_digest = str(task_ir.metadata.get("capability_contract_digest") or "")
        if not contract_digest:
            return None
        for node in nodes:
            if (
                node.get("task_class") == task_class
                and str(node.get("capability_contract_digest") or "") == contract_digest
            ):
                return {**node, "confidence": 0.95}
        return None

    def _verify_path_fingerprints(self, node: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
        required = (
            "impact_fingerprint_hash",
            "repo_fingerprint",
            "policy_digest",
            "verifier_digest",
            "state_digest",
        )
        return all(
            bool(metadata.get(key))
            and str(node.get(key) or "") == str(metadata.get(key) or "")
            for key in required
        )

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        try:
            import json
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except Exception:
            return {}
