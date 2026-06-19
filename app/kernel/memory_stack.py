"""
EdgeK BEAST layered memory and governance stack.

This facade makes the existing L0-L4 stores visible as one canonical memory
model without moving their underlying data.
"""

from pathlib import Path
from typing import Any, Dict, Optional


class MemoryStack:
    """Report the tiered BEAST memory/governance model."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        reasoner: Any = None,
        runtime_governor: Any = None,
        workspace_graph: Any = None,
        skill_tree: Any = None,
        crystallizer: Any = None,
        mcp_broker: Any = None,
        task_envelope_builder: Any = None,
        enterprise_manager: Any = None,
    ):
        self.policies = policies or {}
        self.reasoner = reasoner
        self.runtime_governor = runtime_governor
        self.workspace_graph = workspace_graph
        self.skill_tree = skill_tree
        self.crystallizer = crystallizer
        self.mcp_broker = mcp_broker
        self.task_envelope_builder = task_envelope_builder
        self.enterprise_manager = enterprise_manager

    def state(self, session_id: str = "default") -> Dict[str, Any]:
        """Return L0-L4 memory status and storage pointers."""
        return {
            "beast_object_type": "memory_stack",
            "version": "1.0",
            "principle": "append-only truth stores with rebuildable retrieval views",
            "prompt_entrypoint": {
                "first_retrieval_layers": ["L1", "L2", "L3"],
                "policy_boundary": "L0",
                "audit_sink": "L4",
            },
            "layers": {
                "L0": self._l0_meta_rules(session_id),
                "L1": self._l1_insight_index(),
                "L2": self._l2_workspace_graph(),
                "L3": self._l3_skill_tree(),
                "L4": self._l4_forensic_archive(),
            },
            "truth_stores": [
                "policies/default.yaml",
                self._path("budget_db", self.reasoner and self.reasoner.budget_ledger),
                self._path("runtime_db", self.runtime_governor),
                self._path("workspace_graph_db", self.workspace_graph),
                self._skill_db_path(),
                self._trace_path(),
                "data/chronicles/*.json",
                "data/route_cards/*.json",
            ],
            "retrieval_views": [
                "workspace graph nodes/edges",
                "workspace semantic embeddings",
                "file read L1/L2 cache",
                "BEAST artifact chunks",
                "route cards",
                "skill registry",
                "Chronicle summaries",
            ],
        }

    def _l0_meta_rules(self, session_id: str) -> Dict[str, Any]:
        meta_rules = self.policies.get("meta_rules", {})
        provider_count = len(self.policies.get("providers", {}))
        budget = {}
        if self.reasoner:
            budget = self.reasoner.budget_ledger.usage_summary(session_id)
        return {
            "name": "Meta Rules",
            "scope": "Immutable Governance",
            "role": "primary safety boundary enforced before provider dispatch",
            "persistence": "Config / Policy DB",
            "status": "active" if bool(meta_rules) else "missing",
            "examples": [
                "spend caps",
                "shell allowlists",
                "blocked files",
                "destructive action gates",
                "provider budgets",
            ],
            "counts": {
                "meta_rules": len(meta_rules),
                "providers": provider_count,
                "mcp_server_classes": len(self.policies.get("mcp_server_classes", {})),
            },
            "budget": budget,
            "storage": {
                "policy_path": getattr(self.reasoner, "policy_path", "policies/default.yaml"),
                "budget_db": self._path("db_path", self.reasoner and self.reasoner.budget_ledger),
            },
        }

    def _l1_insight_index(self) -> Dict[str, Any]:
        runtime = self.runtime_governor.state() if self.runtime_governor else {}
        mcp = self.mcp_broker.stats() if self.mcp_broker else {}
        return {
            "name": "Insight Index",
            "scope": "Active Session State",
            "role": "short-lived handles, runtime state, loop signatures, and hot caches",
            "persistence": "In-memory / Redis-ready / SQLite-backed runtime ledgers",
            "status": "active",
            "examples": [
                "request hashes",
                "runtime attempts",
                "circuit breaker state",
                "MCP pending approvals",
                "file read cache handles",
            ],
            "counts": {
                "active_runtime_providers": len(runtime.get("active_counts", {})),
                "runtime_attempt_statuses": runtime.get("attempts", {}),
                "pending_mcp_approvals": mcp.get("pending_approvals", 0),
            },
            "storage": {
                "runtime_db": self._path("db_path", self.runtime_governor),
                "mcp_audit_db": mcp.get("audit_db"),
            },
        }

    def _l2_workspace_graph(self) -> Dict[str, Any]:
        stats = self.workspace_graph.stats() if self.workspace_graph else {}
        return {
            "name": "Workspace Graph",
            "scope": "Project Facts",
            "role": "queryable project structure, symbols, semantic chunks, and file context",
            "persistence": "SQLite / Vector DB",
            "status": "active" if self.workspace_graph else "unavailable",
            "examples": [
                "symbol maps",
                "dependency edges",
                "file trees",
                "semantic chunks",
                "payload fingerprints",
            ],
            "counts": {
                "nodes": stats.get("total_nodes", 0),
                "edges": stats.get("total_edges", 0),
                "node_types": stats.get("node_types", {}),
                "semantic": stats.get("semantic", {}),
                "file_read_cache": stats.get("file_read_cache", {}),
                "beast_artifacts": stats.get("node_types", {}).get("beast_artifact", 0),
            },
            "storage": {
                "workspace_graph_db": self._path("db_path", self.workspace_graph),
            },
        }

    def _l3_skill_tree(self) -> Dict[str, Any]:
        state = self.skill_tree.state() if self.skill_tree else {}
        return {
            "name": "Skill Tree",
            "scope": "Reusable Recipes",
            "role": "promoted workflows, repeated sequences, reusable route and repair patterns",
            "persistence": "SQLite / Postgres-ready",
            "status": "active" if self.skill_tree else "unavailable",
            "examples": [
                "optimized test summarization",
                "provider diagnostic route",
                "scaffold dashboard widget",
                "fix repeated import loop",
            ],
            "counts": {
                "skills": state.get("skills", {}),
                "patterns": state.get("patterns", {}),
                "candidates": len(state.get("candidates", [])),
                "route_cards": self._route_card_count(),
            },
            "storage": state.get("storage", {}),
        }

    def _l4_forensic_archive(self) -> Dict[str, Any]:
        chronicle = (
            self.task_envelope_builder.list_chronicles(limit=5)
            if self.task_envelope_builder
            else {"count": 0, "total_matches": 0}
        )
        enterprise = self.enterprise_manager.state() if self.enterprise_manager else {}
        trace_storage_count = len(getattr(self.crystallizer, "trace_storage", [])) if self.crystallizer else 0
        telemetry_count = len(getattr(self.crystallizer, "telemetry_data", [])) if self.crystallizer else 0
        return {
            "name": "Forensic Archive",
            "scope": "Audit and Telemetry",
            "role": "append-only records of what happened, what was checked, and what was learned",
            "persistence": "Append-only logs / SQLite indexes / Chronicle JSON",
            "status": "active" if self.crystallizer or self.task_envelope_builder else "unavailable",
            "examples": [
                "request IR traces",
                "tool results",
                "circuit breaker triggers",
                "Chronicle summaries",
                "route card artifacts",
            ],
            "counts": {
                "in_memory_traces": trace_storage_count,
                "telemetry_events": telemetry_count,
                "chronicles": chronicle.get("total_matches", chronicle.get("count", 0)),
                "encrypted_traces": enterprise.get("encrypted_traces", 0),
                "observability_events": enterprise.get("observability_events", 0),
            },
            "storage": {
                "trace_jsonl": self._trace_path(),
                "trace_index": str(getattr(self.crystallizer, "index_path", "")) if self.crystallizer else None,
                "chronicle_dir": chronicle.get("chronicle_dir"),
                "enterprise_db": enterprise.get("db"),
            },
        }

    def _route_card_count(self) -> int:
        if not self.task_envelope_builder:
            return 0
        return self.task_envelope_builder.list_route_cards(limit=100).get("total_matches", 0)

    def _skill_db_path(self) -> Optional[str]:
        if not self.skill_tree:
            return None
        try:
            return str(self.skill_tree.skill_registry.db_path)
        except AttributeError:
            return None

    def _trace_path(self) -> Optional[str]:
        if not self.crystallizer:
            return None
        return str(getattr(self.crystallizer, "trace_path", ""))

    def _path(self, attr: str, obj: Any) -> Optional[str]:
        if not obj:
            return None
        value = getattr(obj, attr, None)
        if value is None:
            return None
        return str(Path(value))
