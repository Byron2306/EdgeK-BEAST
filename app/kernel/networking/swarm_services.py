"""Composition root for the governed swarm service graph.

Phase A deliberately binds services without changing role behavior. Later role
implementations receive narrow subsets of this container instead of importing
or constructing runtime services themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict, Optional


@dataclass
class SwarmKernelServices:
    """Shared production dependencies available to swarm roles.

    Complex services remain optional until their existing composition roots are
    passed in. An absent service is reported explicitly, never replaced with a
    fake implementation.
    """

    economist: Any = None
    dispatcher: Any = None
    interceptor: Any = None
    residual_solver: Any = None
    patch_compiler: Any = None
    forge_executor: Any = None
    verifier: Any = None
    critic: Any = None
    scribe: Any = None
    archivist: Any = None
    background_forge: Any = None
    cost_predictor: Any = None
    cache_selector: Any = None
    local_route_optimizer: Any = None
    context_economizer: Any = None
    compression_pipeline: Any = None
    ast_compressor: Any = None
    workspace_graph: Any = None
    workspace_graph_service: Any = None
    semantic_raid: Any = None
    fingerprint_engine: Any = None
    context_packet: Any = None
    insight_compiler: Any = None
    evidence_retriever: Any = None
    evidence_ledger: Any = None
    evidence_bus: Any = None
    crystal_gateway: Any = None
    crystal_assistance_compiler: Any = None
    mission_lattice: Any = None
    skill_tree: Any = None
    action_resolver: Any = None
    worktree_forge_factory: Any = None
    quality_cascade: Any = None
    policy_gate: Any = None

    @classmethod
    def from_runtime(
        cls,
        *,
        policies: Optional[Dict[str, Any]] = None,
        workspace_graph: Any = None,
        **overrides: Any,
    ) -> "SwarmKernelServices":
        """Bind low-risk existing services and accept production overrides.

        Heavy services such as the interceptor, crystal gateway, and evidence
        stores have workspace-specific ownership and must be supplied by the
        application composition root before a role may use them.
        """

        from app.context.economizer import ContextEconomizer
        from app.kernel.adapters.provider_economist import ProviderEconomist
        from app.kernel.compute.ast_compressor import ASTCompressor
        from app.kernel.compute.compression_pipeline import CompressionPipeline

        values: Dict[str, Any] = {
            "economist": ProviderEconomist(),
            "context_economizer": ContextEconomizer(policies or {}),
            "compression_pipeline": CompressionPipeline(policies or {}),
            "ast_compressor": ASTCompressor(),
            "workspace_graph": workspace_graph,
        }
        values.update({key: value for key, value in overrides.items() if key in cls.field_names()})
        return cls(**values)

    @classmethod
    def field_names(cls) -> set[str]:
        return {item.name for item in fields(cls)}

    def inventory(self) -> Dict[str, Any]:
        """Return an honest, serializable service binding inventory."""

        bound = {name: getattr(self, name) is not None for name in self.field_names()}
        return {
            "beast_object_type": "swarm_kernel_service_inventory",
            "version": "1.0",
            "bound": sorted(name for name, present in bound.items() if present),
            "missing": sorted(name for name, present in bound.items() if not present),
            "count": sum(bound.values()),
            "total": len(bound),
        }

    def require(self, *names: str) -> Dict[str, Any]:
        """Return a narrow role dependency view or fail with named gaps."""

        missing = [name for name in names if name not in self.field_names() or getattr(self, name) is None]
        if missing:
            raise RuntimeError(f"Swarm service bindings missing: {', '.join(sorted(missing))}")
        return {name: getattr(self, name) for name in names}
