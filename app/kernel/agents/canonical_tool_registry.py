"""One synchronized tool catalog for BEAST governance and Effect execution.

The durable agent runtime still consumes the established ``tool_models.ToolSpec``
contract.  The OpenCode-style Effect executor consumes the schema registry in
``tool_registry.ToolRegistry``.  This facade owns both projections so they
cannot silently drift into separate catalogs.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.kernel.agents.tool_models import ToolEffect as BeastToolEffect
from app.kernel.agents.tool_models import ToolSpec as BeastToolSpec
from app.kernel.agents.tool_registry import (
    AgentToolRegistry,
    ExecutionTarget,
    ToolEffect,
    ToolRegistry,
    ToolRisk,
    ToolSpec,
)


_EFFECT_MAP = {
    BeastToolEffect.READ: ToolEffect.READ,
    BeastToolEffect.ISOLATED_MUTATION: ToolEffect.WRITE,
    BeastToolEffect.EXECUTION: ToolEffect.EXECUTE,
    BeastToolEffect.PROMOTION: ToolEffect.PROMOTION,
}


class CanonicalToolRegistry:
    """Keep the durable BEAST and schema-first Effect views in lockstep."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self._beast = AgentToolRegistry()
        self.effect_registry = ToolRegistry(str(self.workspace_root))
        self._lock = threading.RLock()

    @classmethod
    def from_agent_registry(
        cls,
        registry: AgentToolRegistry,
        *,
        workspace_root: str | Path,
    ) -> "CanonicalToolRegistry":
        canonical = cls(workspace_root)
        specs = list(getattr(registry, "_tools", {}).values())
        for spec in specs:
            canonical.register(spec)
        return canonical

    @staticmethod
    def _effect_spec(spec: BeastToolSpec) -> ToolSpec:
        return ToolSpec(
            tool_id=spec.tool_id,
            version=spec.version,
            title=spec.title,
            description=spec.description,
            category=spec.category,
            risk=ToolRisk(spec.risk.value),
            effect=_EFFECT_MAP[spec.effect],
            input_schema=dict(spec.input_schema or {}),
            output_schema=dict(spec.output_schema or {}),
            targets=[ExecutionTarget(str(target)) for target in spec.targets],
            requires_approval=spec.requires_approval,
            requires_worktree=spec.requires_worktree,
            timeout_seconds=float(spec.timeout_seconds),
            handler=spec.handler,
            metadata={
                "max_output_bytes": int(spec.max_output_bytes),
                "idempotent": bool(spec.idempotent),
                "beast_effect": spec.effect.value,
            },
        )

    def register(self, spec: BeastToolSpec, *, replace: bool = False) -> BeastToolSpec:
        projected = self._effect_spec(spec)
        with self._lock:
            self._beast.register(spec, replace=replace)
            try:
                self.effect_registry.register(projected, replace=replace)
            except Exception:
                # Registration is an administrative operation. Roll back the
                # first projection so callers never observe a split catalog.
                with self._beast._lock:  # noqa: SLF001 - facade owns this registry
                    if replace:
                        self._beast._tools.pop(spec.tool_id, None)  # noqa: SLF001
                    else:
                        self._beast._tools.pop(spec.tool_id, None)  # noqa: SLF001
                raise
        return spec

    def get(self, tool_id: str) -> BeastToolSpec:
        return self._beast.get(tool_id)

    def list(self, *, category: str = "", effect: str = "") -> list[dict[str, Any]]:
        return self._beast.list(category=category, effect=effect)

    def validate_arguments(self, spec: BeastToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        # Preserve the established public error contract while also requiring
        # the schema-first projection to accept the exact same payload.
        validated = self._beast.validate_arguments(spec, arguments)
        self.effect_registry.validate_input(spec.tool_id, validated)
        return validated

