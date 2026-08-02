"""Crystal Tongue C3: symbolic control packets for small local models.

C3 is deliberately text-renderable.  It does not pretend to be a hidden-state
embedding and it never grants mutation authority.  Its job is to make the
unresolved operation, target slot, constraints, and verifier unambiguous.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping


VERSION = "C3"
MAX_FIELD = 2400
MAX_ITEMS = 12
MAX_PACKET_CHARS = 8000
SLOT_TYPES = {
    "python_expression", "return_statement", "condition", "dictionary_entry",
    "import", "exact_replacement", "json_value", "unknown",
}
PLACEHOLDERS = (
    "complete replacement source", "replacement code here", "insert code",
    "your code", "example implementation", "todo", "<unresolved>",
)


def _clean(value: Any, limit: int = MAX_FIELD) -> str:
    return str(value or "").strip()[:limit]


def _items(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[str] = []
    for item in value[:MAX_ITEMS]:
        text = _clean(item, 600)
        if text and text not in result:
            result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class CrystalControlPacket:
    task_family: str
    operation: str
    slot_type: str
    target_path: str
    target_symbol: str
    old_code: str
    allowed_fields: tuple[str, ...]
    constraints: tuple[str, ...]
    failure_signatures: tuple[str, ...]
    verified_patterns: tuple[str, ...]
    verifier: str
    source_context_available: bool = False

    def __post_init__(self) -> None:
        if self.slot_type not in SLOT_TYPES:
            raise ValueError(f"unsupported C3 slot type: {self.slot_type}")
        if not self.task_family or not self.operation:
            raise ValueError("C3 task_family and operation are required")
        if not self.allowed_fields:
            raise ValueError("C3 requires at least one allowed output field")
        if any(not item or any(marker in item.casefold() for marker in PLACEHOLDERS)
               for item in self.verified_patterns):
            raise ValueError("C3 verified patterns cannot contain placeholders")
        if self.target_path and PurePosixPath(self.target_path).is_absolute():
            raise ValueError("C3 target path must be workspace-relative")
        if len(self.encode()) > MAX_PACKET_CHARS:
            raise ValueError("C3 packet exceeds bounded size")

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "crystal_control_packet", "version": VERSION, **asdict(self),
                "authority": "model_guidance_only", "mutation_authorized": False,
                "packet_digest": self.digest}

    def encode(self) -> str:
        body = {
            "task": self.task_family, "operation": self.operation,
            "slot": self.slot_type, "path": self.target_path,
            "symbol": self.target_symbol, "old": self.old_code,
            "fields": list(self.allowed_fields), "constraints": list(self.constraints),
            "failures": list(self.failure_signatures), "patterns": list(self.verified_patterns),
            "verifier": self.verifier, "source_context": self.source_context_available,
        }
        return VERSION + "|" + json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.encode().encode("utf-8")).hexdigest()

    def render_prompt(self) -> str:
        """Render a small-model contract without natural-language ambiguity."""
        return (
            "CRYSTAL_CONTROL_PACKET C3\n"
            f"TASK={self.task_family}\nOPERATION={self.operation}\nSLOT_TYPE={self.slot_type}\n"
            f"TARGET_PATH={self.target_path or '(not supplied)'}\n"
            f"TARGET_SYMBOL={self.target_symbol or '(not supplied)'}\n"
            f"OLD_EXACT={self.old_code or '(not supplied; do not invent surrounding code)'}\n"
            f"ALLOWED_FIELDS={json.dumps(list(self.allowed_fields), separators=(',', ':'))}\n"
            f"CONSTRAINTS={json.dumps(list(self.constraints), separators=(',', ':'))}\n"
            f"KNOWN_FAILURES={json.dumps(list(self.failure_signatures), separators=(',', ':'))}\n"
            f"VERIFIED_PATTERNS={json.dumps(list(self.verified_patterns), separators=(',', ':'))}\n"
            f"VERIFIER={self.verifier}\n"
            "OUTPUT_RULE=Return one JSON object containing only ALLOWED_FIELDS."
        )


def compile_control_packet(payload: Mapping[str, Any]) -> CrystalControlPacket:
    """Compile sanitized residual evidence into a C3 control packet."""
    target = payload.get("target") if isinstance(payload.get("target"), Mapping) else {}
    contract = payload.get("residual_contract") if isinstance(payload.get("residual_contract"), Mapping) else {}
    allowed = payload.get("unresolved_fields") or [contract.get("field") or "new"]
    scope = _clean(contract.get("scope") or payload.get("slot_type") or "unknown").lower()
    aliases = {"expression": "python_expression", "python_statement": "return_statement",
               "statement": "return_statement", "exact_snippet": "exact_replacement"}
    slot_type = aliases.get(scope, scope if scope in SLOT_TYPES else "unknown")
    old = _clean(contract.get("old") or payload.get("old") or payload.get("current_body"))
    guidance = payload.get("verified_patterns") or payload.get("crystal_guidance") or []
    failures = payload.get("failure_summary") or payload.get("failure") or payload.get("verifier_failure") or ""
    packet = CrystalControlPacket(
        task_family=_clean(payload.get("task_family") or payload.get("task") or "code_change", 160),
        operation=_clean(payload.get("operation") or payload.get("action") or "fill_residual", 160),
        slot_type=slot_type,
        target_path=_clean(target.get("path") or payload.get("path"), 400),
        target_symbol=_clean(target.get("symbol") or payload.get("symbol"), 240),
        old_code=old,
        allowed_fields=_items(allowed),
        constraints=_items(payload.get("constraints") or contract.get("constraints")),
        failure_signatures=_items(failures),
        verified_patterns=_items(guidance),
        verifier=_clean(payload.get("verifier") or payload.get("verify") or "fresh_verification", 240),
        source_context_available=bool(old),
    )
    return packet

