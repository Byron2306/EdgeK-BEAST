"""Typed, payload-safe facts for reconstructing physical runtime effects.

The envelope is deliberately embedded in an ordinary ``SensorEvent`` payload.
This lets existing producers remain valid while physical producers opt into a
stronger contract.  It describes observations and effects; it grants no
authority and contains no live file descriptors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.kernel.sensorium.contracts import ContractValidationError


IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
PHASES = {"observation", "decision", "actuation", "verification", "refusal", "rollback"}
RESULTS = {"observed", "selected", "success", "failure", "denied", "refused", "rolled_back", "unknown"}
RELATION_FIELDS = ("reads", "requires", "writes", "produces")


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"physical_effect.{field_name} must be a list of strings")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result) or len(set(result)) != len(result):
        raise ContractValidationError(f"physical_effect.{field_name} must contain unique nonempty strings")
    return result


@dataclass(frozen=True)
class PhysicalEffect:
    operation: str
    phase: str
    subject: str
    result: str
    reads: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    descriptor_refs: tuple[str, ...] = ()
    caused_by_event_ids: tuple[str, ...] = ()
    branch: str = ""
    state_transition: tuple[str, str, str] | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PhysicalEffect | None":
        raw = payload.get("physical_effect")
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ContractValidationError("physical_effect must be an object")
        operation = str(raw.get("operation") or "")
        phase = str(raw.get("phase") or "")
        subject = str(raw.get("subject") or "")
        result = str(raw.get("result") or "")
        if not IDENTIFIER_RE.fullmatch(operation):
            raise ContractValidationError("physical_effect.operation must be a dotted lowercase identifier")
        if phase not in PHASES:
            raise ContractValidationError(f"physical_effect.phase must be one of {sorted(PHASES)}")
        if not subject:
            raise ContractValidationError("physical_effect.subject is required")
        if result not in RESULTS:
            raise ContractValidationError(f"physical_effect.result must be one of {sorted(RESULTS)}")
        transition = raw.get("state_transition")
        normalized_transition = None
        if transition is not None:
            if not isinstance(transition, Mapping):
                raise ContractValidationError("physical_effect.state_transition must be an object")
            resource = str(transition.get("resource") or "")
            before = str(transition.get("from") or "")
            after = str(transition.get("to") or "")
            if not resource or not before or not after or before == after:
                raise ContractValidationError(
                    "physical_effect.state_transition requires resource and distinct from/to states"
                )
            normalized_transition = (resource, before, after)
        return cls(
            operation=operation,
            phase=phase,
            subject=subject,
            result=result,
            reads=_string_list(raw.get("reads"), "reads"),
            requires=_string_list(raw.get("requires"), "requires"),
            writes=_string_list(raw.get("writes"), "writes"),
            produces=_string_list(raw.get("produces"), "produces"),
            descriptor_refs=_string_list(raw.get("descriptor_refs"), "descriptor_refs"),
            caused_by_event_ids=_string_list(raw.get("caused_by_event_ids"), "caused_by_event_ids"),
            branch=str(raw.get("branch") or ""),
            state_transition=normalized_transition,
        )

    def fact_projection(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "operation": self.operation,
            "phase": self.phase,
            "subject": self.subject,
            "result": self.result,
            "reads": list(self.reads),
            "requires": list(self.requires),
            "writes": list(self.writes),
            "produces": list(self.produces),
            "descriptor_refs": list(self.descriptor_refs),
            "branch": self.branch,
        }
        if self.state_transition is not None:
            resource, before, after = self.state_transition
            value["state_transition"] = {"resource": resource, "from": before, "to": after}
        return value


def physical_effect_payload(
    *, operation: str, phase: str, subject: str, result: str, **facts: Any
) -> dict[str, Any]:
    """Build and validate a canonical physical-effect payload fragment."""
    raw = {"operation": operation, "phase": phase, "subject": subject, "result": result, **facts}
    effect = PhysicalEffect.from_payload({"physical_effect": raw})
    assert effect is not None
    projection = effect.fact_projection()
    if effect.caused_by_event_ids:
        projection["caused_by_event_ids"] = list(effect.caused_by_event_ids)
    return {"physical_effect": projection}
