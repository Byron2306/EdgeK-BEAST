"""Crystal Tongue v1: deterministic textual encoding for verified task IR.

This is intentionally a text protocol. It reduces repeated prose while keeping
the authoritative meaning in a canonical object that BEAST can validate and
compile before any model output is trusted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping
from urllib.parse import quote, unquote


VERSION = "C1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _encode(value: Any) -> str:
    return quote(_text(value), safe="._-/:,@")


def _decode(value: str) -> str:
    return unquote(value)


def _slug(value: Any) -> str:
    return _encode(value)


@dataclass(frozen=True)
class CrystalTongueIR:
    task_family: str
    failure_signature: str
    target_symbol: str
    old_expression: str
    operation: str
    crystal_rules: tuple[str, ...]
    constraints: tuple[str, ...]
    verifier: str
    unresolved: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "crystal_tongue_ir", "version": VERSION, **asdict(self)}

    def encode(self) -> str:
        rules = ",".join(_slug(item) for item in self.crystal_rules if _text(item)) or "-"
        constraints = ",".join(_slug(item) for item in self.constraints if _text(item)) or "-"
        unresolved = ",".join(_slug(item) for item in self.unresolved if _text(item)) or "-"
        return "|".join((
            VERSION,
            f"F:{_slug(self.task_family)}",
            f"E:{_slug(self.failure_signature)}",
            f"T:{_slug(self.target_symbol)}",
            f"O:{_slug(self.old_expression)}",
            f"A:{_slug(self.operation)}",
            f"R:{rules}",
            f"S:{constraints}",
            f"V:{_slug(self.verifier)}",
            f"Q:{unresolved}",
        ))


def compile_crystal_tongue(payload: Mapping[str, Any]) -> CrystalTongueIR:
    """Compile ordinary BEAST evidence into the bounded C1 text protocol."""
    target = payload.get("target") if isinstance(payload.get("target"), Mapping) else {}
    rules = payload.get("crystal_rules") or payload.get("rules") or []
    constraints = payload.get("constraints") or []
    unresolved = payload.get("unresolved") or payload.get("unresolved_fields") or ["new"]
    if isinstance(rules, str):
        rules = [rules]
    if isinstance(constraints, str):
        constraints = [constraints]
    if isinstance(unresolved, str):
        unresolved = [unresolved]
    return CrystalTongueIR(
        task_family=_text(payload.get("task_family") or payload.get("family") or payload.get("task")),
        failure_signature=_text(payload.get("failure_signature") or payload.get("failure") or payload.get("verifier_failure")),
        target_symbol=_text(payload.get("target_symbol") or target.get("symbol") or payload.get("symbol")),
        old_expression=_text(payload.get("old_expression") or payload.get("old") or payload.get("current_body")),
        operation=_text(payload.get("operation") or payload.get("action") or "replace_expression"),
        crystal_rules=tuple(_text(item) for item in rules if _text(item)),
        constraints=tuple(_text(item) for item in constraints if _text(item)),
        verifier=_text(payload.get("verifier") or payload.get("verify") or "fresh_verification"),
        unresolved=tuple(_text(item) for item in unresolved if _text(item)),
    )


def parse_crystal_tongue(encoded: str) -> CrystalTongueIR:
    """Parse C1 only; unknown fields and malformed packets fail closed."""
    parts = str(encoded or "").split("|")
    if not parts or parts[0] != VERSION:
        raise ValueError("unsupported Crystal Tongue version")
    values: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, value = part.partition(":")
        if not separator or key not in {"F", "E", "T", "O", "A", "R", "S", "V", "Q"} or key in values:
            raise ValueError("malformed Crystal Tongue field")
        values[key] = value
    required = {"F", "E", "T", "O", "A", "R", "S", "V", "Q"}
    if set(values) != required:
        raise ValueError("incomplete Crystal Tongue packet")
    split = lambda value: tuple(_decode(item) for item in value.split(",") if item and item != "-")
    return CrystalTongueIR(
        task_family=_decode(values["F"]), failure_signature=_decode(values["E"]),
        target_symbol=_decode(values["T"]), old_expression=_decode(values["O"]),
        operation=_decode(values["A"]), crystal_rules=split(values["R"]),
        constraints=split(values["S"]), verifier=_decode(values["V"]), unresolved=split(values["Q"]),
    )
