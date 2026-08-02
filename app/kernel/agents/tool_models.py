"""Typed tool and observation contracts for the BEAST AgentRun runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolEffect(str, Enum):
    READ = "read"
    ISOLATED_MUTATION = "isolated_mutation"
    EXECUTION = "execution"
    PROMOTION = "promotion"


ToolHandler = Callable[[dict[str, Any], "ToolExecutionContext"], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    version: str
    title: str
    description: str
    category: str
    risk: ToolRisk
    effect: ToolEffect
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    max_output_bytes: int = 65536
    requires_approval: bool = False
    requires_worktree: bool = False
    idempotent: bool = True
    targets: tuple[str, ...] = ("local",)
    handler: ToolHandler | None = field(default=None, repr=False, compare=False)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("handler", None)
        data["risk"] = self.risk.value
        data["effect"] = self.effect.value
        data["targets"] = list(self.targets)
        return data


@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str
    workspace_root: str
    execution_target: str = "local"
    execution_target_payload: dict[str, Any] = field(default_factory=dict)
    worktree_root: str = ""
    approval_id: str = ""
    engine: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ToolRequest:
    tool_id: str
    arguments: dict[str, Any]
    execution_target: str = "local"
    execution_target_payload: dict[str, Any] = field(default_factory=dict)
    approval_id: str = ""


@dataclass
class ToolObservation:
    observation_id: str
    run_id: str
    tool_id: str
    tool_version: str
    status: str
    started_at: float
    completed_at: float
    duration_ms: int
    arguments: dict[str, Any]
    result: dict[str, Any]
    error: str = ""
    truncated: bool = False
    evidence_digest: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
