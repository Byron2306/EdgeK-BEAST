"""Synthesize bounded declarative verifier plans from crystallization evidence.

The output is data, not a test script.  A later reviewed opcode registry maps
``kind`` to a local verifier; unknown kinds are rejected by the compiler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class VerifierPlan:
    checks: tuple[Mapping[str, Any], ...]
    source_evidence: tuple[str, ...]
    plan_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "crystal_verifier_plan", "version": "1.0",
                "checks": [dict(item) for item in self.checks],
                "source_evidence": list(self.source_evidence), "plan_digest": self.plan_digest,
                "contains_executable_code": False}


def synthesize_verifier_plan(
    templates: Iterable[Mapping[str, Any]], *, postconditions: Iterable[str],
    negative_conditions: Iterable[str], evidence: Iterable[str],
) -> VerifierPlan:
    """Create a deterministic verifier plan from repeated observed effects."""
    checks: list[dict[str, Any]] = []
    for index, step in enumerate(templates):
        operation, result = str(step.get("operation") or ""), str(step.get("result") or "")
        if not operation or not result:
            raise ValueError("verifier synthesis requires typed operation/result facts")
        if str(step.get("phase") or "") == "verification":
            checks.append({"id": f"effect-{index}", "kind": "observed_effect",
                           "operation": operation, "expected_result": result})
        for required in step.get("requires") or ():
            checks.append({"id": f"precondition-{index}-{len(checks)}", "kind": "precondition_present",
                           "condition": str(required)})
    for value in sorted(set(map(str, postconditions))):
        checks.append({"id": f"postcondition-{len(checks)}", "kind": "postcondition",
                       "condition": value})
    for value in sorted(set(map(str, negative_conditions))):
        checks.append({"id": f"negative-{len(checks)}", "kind": "negative_condition_absent",
                       "condition": value})
    # Deduplicate structurally while retaining a stable order for receipts.
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for check in checks:
        key = content_hash(check)
        if key not in seen:
            seen.add(key); unique.append(check)
    source = tuple(sorted(set(map(str, evidence))))
    body = {"checks": unique, "source_evidence": source}
    return VerifierPlan(tuple(unique), source, content_hash(body))
