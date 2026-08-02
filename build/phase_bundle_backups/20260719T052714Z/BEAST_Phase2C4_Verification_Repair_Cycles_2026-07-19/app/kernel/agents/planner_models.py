"""Typed decisions and durable planner state for BEAST AgentRun loops."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PlannerDecisionType(str, Enum):
    TOOL = "tool"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PlannerDecision:
    decision_type: PlannerDecisionType
    rationale: str = ""
    tool_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_target: str = "local"
    approval_id: str = ""
    summary: str = ""
    blocker: str = ""

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision_type"] = self.decision_type.value
        return data


@dataclass
class PlannerState:
    run_id: str
    turn: int = 0
    max_turns: int = 8
    status: str = "ready"
    last_decision: dict[str, Any] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    final_summary: str = ""
    blocker: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
