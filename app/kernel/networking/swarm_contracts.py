"""Typed contracts shared by the governed swarm roles.

The database still stores JSON for backwards compatibility, but role payloads
are validated at the boundary before they are persisted or sent to the UI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Literal, Optional


RoleStatus = Literal["completed", "failed", "blocked", "skipped"]


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SwarmRoleInput:
    """Small typed envelope passed into a role."""

    role: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    @property
    def inputs_digest(self) -> str:
        return _digest({"role": self.role, "inputs": self.inputs})


@dataclass(frozen=True)
class SwarmRoleResult:
    """Validated, serializable result emitted by every swarm role."""

    role: str
    status: RoleStatus
    inputs_digest: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    next_role: Optional[str] = None
    model_calls: int = 0
    tool_calls: int = 0
    mutations: int = 0

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("role is required")
        if self.status not in {"completed", "failed", "blocked", "skipped"}:
            raise ValueError(f"unsupported role status: {self.status}")
        if not self.inputs_digest.startswith("sha256:"):
            raise ValueError("inputs_digest must be a sha256 digest")
        for name, value in (("model_calls", self.model_calls), ("tool_calls", self.tool_calls), ("mutations", self.mutations)):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.mutations or self.outputs.get("execution_claimed"):
            receipt = self.outputs.get("tool_receipt") or self.outputs.get("receipt")
            if not receipt:
                raise ValueError("execution claims require a tool receipt")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "status": self.status,
            "inputs_digest": self.inputs_digest,
            "outputs": self.outputs,
            "evidence_refs": list(self.evidence_refs),
            "next_role": self.next_role,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "mutations": self.mutations,
        }

    @classmethod
    def from_event(
        cls,
        *,
        role: str,
        details: Dict[str, Any],
        next_role: Optional[str] = None,
        status: RoleStatus = "completed",
    ) -> "SwarmRoleResult":
        payload = dict(details or {})
        refs = payload.get("evidence_refs") or []
        if not refs:
            refs = [str(payload[key]) for key in ("receipt_id", "packet_hash", "failure_signature", "handoff_hash") if payload.get(key)]
        outputs = dict(payload)
        return cls(
            role=role,
            status=status,
            inputs_digest=_digest({"role": role, "details": payload}),
            outputs=outputs,
            evidence_refs=tuple(str(item) for item in refs),
            next_role=next_role,
            model_calls=int(payload.get("model_calls") or 0),
            tool_calls=int(payload.get("tool_calls") or 0),
            mutations=int(payload.get("mutations") or 0),
        )


def role_result_from_details(role: str, details: Dict[str, Any], *, next_role: Optional[str] = None, status: RoleStatus = "completed") -> SwarmRoleResult:
    """Build the common contract from an existing role implementation."""

    return SwarmRoleResult.from_event(role=role, details=details, next_role=next_role, status=status)
