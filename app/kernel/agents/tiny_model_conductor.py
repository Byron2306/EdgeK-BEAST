"""Deterministic conductor for the first visible tiny-model golden path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class TinyModelState(str, Enum):
    CREATED = "CREATED"
    INSPECT_REQUIRED = "INSPECT_REQUIRED"
    WORKTREE_REQUIRED = "WORKTREE_REQUIRED"
    BASELINE_REQUIRED = "BASELINE_REQUIRED"
    PATCH_REQUIRED = "PATCH_REQUIRED"
    VERIFY_REQUIRED = "VERIFY_REQUIRED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class TinyModelStep:
    state: TinyModelState
    label: str
    allowed_next_tools: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "label": self.label,
            "allowed_next_tools": list(self.allowed_next_tools),
        }


class TinyModelConductor:
    """Expose one legal action at a time; never delegate lifecycle to Ollama."""

    STEPS = (
        TinyModelStep(TinyModelState.INSPECT_REQUIRED, "Repository inspected", ("workspace.inspect",)),
        TinyModelStep(TinyModelState.WORKTREE_REQUIRED, "Worktree created and bound", ("worktree.bind",)),
        TinyModelStep(TinyModelState.BASELINE_REQUIRED, "Baseline verifier failed", ("worktree.verify",)),
        TinyModelStep(TinyModelState.PATCH_REQUIRED, "Bounded patch requested", ("residual.solve",)),
        TinyModelStep(TinyModelState.VERIFY_REQUIRED, "Patch applied; verifier running", ("worktree.replace_exact", "worktree.verify")),
        TinyModelStep(TinyModelState.REVIEW_REQUIRED, "Diff awaiting approval", ("worktree.diff",)),
        TinyModelStep(TinyModelState.COMPLETED, "Golden path completed", ()),
    )

    def __init__(self) -> None:
        self._index = 0

    def next(self) -> TinyModelStep:
        return self.STEPS[self._index]

    def complete_current(self, *, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        step = self.next()
        row = {**step.to_dict(), "status": "passed", "evidence": dict(evidence or {})}
        if self._index < len(self.STEPS) - 1:
            self._index += 1
        return row

    def timeline(self) -> list[Dict[str, Any]]:
        return [
            {**step.to_dict(), "status": "pending", "evidence": {}}
            for step in self.STEPS
        ]

    @classmethod
    def expected_states(cls) -> tuple[str, ...]:
        return tuple(step.state.value for step in cls.STEPS)
