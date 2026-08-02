"""Deterministic decomposition of IDE repairs into bounded typed subtasks."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


KIND_ORDER = {"find_import": 0, "replace_expression": 1, "add_condition": 2, "run_test": 3}


@dataclass(frozen=True)
class RepairSubproblem:
    subproblem_id: str
    kind: str
    objective: str
    target_path: str = ""
    target_symbol: str = ""
    depends_on: tuple[str, ...] = ()
    model_allowed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"authority": "bounded_subtask", "whole_file_replacement": False}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _target(payload: Mapping[str, Any]) -> tuple[str, str]:
    target = payload.get("target") if isinstance(payload.get("target"), Mapping) else {}
    return _text(target.get("path") or payload.get("path")), _text(target.get("symbol") or payload.get("symbol"))


def decompose_repair(payload: Mapping[str, Any]) -> tuple[RepairSubproblem, ...]:
    """Derive a stable plan from evidence; caller input cannot reorder it."""
    path, symbol = _target(payload)
    failure = _text(payload.get("failure_summary") or payload.get("failure") or payload.get("verifier_failure")).casefold()
    operation = _text(payload.get("operation") or payload.get("action") or "replace_expression").casefold()
    constraints = payload.get("constraints") or []
    if isinstance(constraints, str):
        constraints = [constraints]
    constraint_text = " ".join(_text(item).casefold() for item in constraints)
    explicit = payload.get("subproblems")
    selected: set[str] = set()
    if isinstance(explicit, (list, tuple)):
        selected = {_text(item.get("kind") if isinstance(item, Mapping) else item) for item in explicit}
    if any(marker in failure for marker in ("nameerror", "importerror", "missing import", "no module named")):
        selected.add("find_import")
    if any(marker in operation for marker in ("condition", "guard", "if_")) or "condition" in constraint_text:
        selected.add("add_condition")
    if not selected or any(marker in operation for marker in ("replace", "expression", "statement", "normalize", "fill")):
        selected.add("replace_expression")
    selected.add("run_test")

    result: list[RepairSubproblem] = []
    previous = ""
    for kind in sorted(selected, key=lambda item: KIND_ORDER.get(item, 99)):
        if kind not in KIND_ORDER:
            raise ValueError(f"unsupported deterministic subproblem: {kind}")
        sub_id = f"subtask_{len(result) + 1}_{kind}"
        if kind == "find_import":
            objective = "Identify the one required import and add only that import."
        elif kind == "replace_expression":
            objective = "Fill one typed source slot using the exact old snippet."
        elif kind == "add_condition":
            objective = "Add one bounded condition without rewriting surrounding code."
        else:
            objective = "Run the targeted verifier and report its result; do not edit source."
        result.append(RepairSubproblem(
            subproblem_id=sub_id, kind=kind, objective=objective,
            target_path=path, target_symbol=symbol,
            depends_on=(previous,) if previous else (),
            model_allowed=kind != "run_test",
        ))
        previous = sub_id
    return tuple(result)


def decomposition_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    subtasks = decompose_repair(payload)
    active = next((item for item in subtasks if item.model_allowed), subtasks[0])
    return {
        "subproblems": [item.to_dict() for item in subtasks],
        "active_subproblem": active.to_dict(),
        "execution_order": [item.subproblem_id for item in subtasks],
        "model_scope": active.kind,
        "max_source_files_per_turn": 1,
    }

