"""Crystal Tongue v2: tokenizer-aware symbolic codebooks.

The codebook is data, not authority.  BEAST retains the canonical C1 IR and
uses this layer only to choose compact symbols for model-facing text.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable, Mapping
from urllib.parse import quote, unquote

from app.kernel.compute.crystal_tongue import CrystalTongueIR


VERSION = "C2"
TokenCounter = Callable[[str], int]
_SHARED_CODEBOOKS: dict[str, "CrystalTongueCodebook"] = {}
_SHARED_CODEBOOK_LOCK = RLock()


@dataclass(frozen=True)
class CodebookEntry:
    field: str
    code: str
    value: str


@dataclass(frozen=True)
class CrystalTongueCodebook:
    entries: tuple[CodebookEntry, ...]
    tokenizer_id: str = "fallback"
    active_entries: tuple[CodebookEntry, ...] | None = None

    @property
    def lexicon_id(self) -> str:
        """Stable identity for a process-wide tokenizer lexicon."""
        import hashlib
        material = self.tokenizer_id + "|" + "|".join(
            f"{entry.field}={entry.code}" for entry in self.entries
        )
        return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()

    @property
    def by_field(self) -> dict[str, CodebookEntry]:
        return {entry.field: entry for entry in self.entries}

    def stable_prefix(self) -> str:
        definitions = ";".join(
            f"{entry.code}={quote(entry.value, safe='._-/:,@')}" for entry in self.entries
        )
        if self.active_entries is not None:
            definitions = ";".join(
                f"{entry.code}={quote(entry.value, safe='._-/:,@')}" for entry in self.active_entries
            )
        return f"{VERSION}LEX|tokenizer:{self.tokenizer_id}|{definitions}"

    def encode(self, ir: CrystalTongueIR) -> str:
        values = {
            "F": ir.task_family, "E": ir.failure_signature,
            "T": ir.target_symbol, "O": ir.old_expression,
            "A": ir.operation, "V": ir.verifier,
        }
        by_key = self.by_field
        fields = [f"{key}:{by_key[f'{key}:{value}'].code}" for key, value in values.items()]
        fields.extend((f"R:{','.join(by_key[f'R:{value}'].code for value in ir.crystal_rules) or '-'}",))
        fields.extend((f"S:{','.join(by_key[f'S:{value}'].code for value in ir.constraints) or '-'}",))
        fields.extend((f"Q:{','.join(by_key[f'Q:{value}'].code for value in ir.unresolved) or '-'}",))
        return "|".join((VERSION, *fields))


def _values(ir: CrystalTongueIR) -> list[tuple[str, str]]:
    result = [
        ("F", ir.task_family), ("E", ir.failure_signature),
        ("T", ir.target_symbol), ("O", ir.old_expression),
        ("A", ir.operation), ("V", ir.verifier),
    ]
    result.extend(("R", value) for value in ir.crystal_rules)
    result.extend(("S", value) for value in ir.constraints)
    result.extend(("Q", value) for value in ir.unresolved)
    return result


def compile_codebook(ir: CrystalTongueIR, *, tokenizer: TokenCounter | None = None, tokenizer_id: str = "fallback") -> CrystalTongueCodebook:
    """Choose the cheapest deterministic aliases for the exact tokenizer."""
    counter = tokenizer or (lambda value: len(value))
    entries: list[CodebookEntry] = []
    seen: set[tuple[str, str]] = set()
    counters: dict[str, int] = {}
    for field, value in _values(ir):
        key = (field, value)
        if key in seen:
            continue
        seen.add(key)
        counters[field] = counters.get(field, 0) + 1
        number = counters[field]
        candidates = (f"{field.lower()}{number}", f"p{len(entries) + 1}")
        code = min(candidates, key=lambda candidate: (int(counter(candidate)), candidate))
        entries.append(CodebookEntry(f"{field}:{value}", code, value))
    return CrystalTongueCodebook(tuple(entries), tokenizer_id=tokenizer_id)


def shared_codebook(
    ir: CrystalTongueIR,
    *,
    tokenizer: TokenCounter | None = None,
    tokenizer_id: str = "fallback",
) -> tuple[CrystalTongueCodebook, int, int]:
    """Return a reusable lexicon and counts for this request.

    C2 symbols must remain stable across requests or Forge KV cannot reuse the
    codebook prefix. New values extend the process-wide lexicon; old values
    retain their codes. The bounded size prevents a long IDE session from
    turning request vocabulary into an unbounded memory cache.
    """
    key = str(tokenizer_id or "fallback")
    counter = tokenizer or (lambda value: len(value))
    with _SHARED_CODEBOOK_LOCK:
        current = _SHARED_CODEBOOKS.get(key)
        entries = list(current.entries) if current else []
        known = {(entry.field.split(":", 1)[0], entry.value) for entry in entries}
        next_number: dict[str, int] = {}
        for entry in entries:
            prefix = entry.field.split(":", 1)[0]
            suffix = entry.code[len(prefix.lower()):] if entry.code.startswith(prefix.lower()) else ""
            if suffix.isdigit():
                next_number[prefix] = max(next_number.get(prefix, 0), int(suffix))
        added = 0
        reused = 0
        for field, value in _values(ir):
            if (field, value) in known:
                reused += 1
                continue
            if len(entries) >= 512:
                raise ValueError("shared Crystal Tongue lexicon limit reached")
            next_number[field] = next_number.get(field, 0) + 1
            candidates = (f"{field.lower()}{next_number[field]}", f"p{len(entries) + 1}")
            used = {entry.code for entry in entries}
            candidates = tuple(candidate for candidate in candidates if candidate not in used)
            code = min(candidates, key=lambda candidate: (int(counter(candidate)), candidate))
            entries.append(CodebookEntry(f"{field}:{value}", code, value))
            known.add((field, value))
            added += 1
        active_keys = set(_values(ir))
        active_entries = tuple(entry for entry in entries if (entry.field.split(":", 1)[0], entry.value) in active_keys)
        result = CrystalTongueCodebook(tuple(entries), tokenizer_id=key, active_entries=active_entries)
        _SHARED_CODEBOOKS[key] = result
        return result, added, reused


def clear_shared_codebooks() -> None:
    """Test/operator reset; production callers should normally retain the lexicon."""
    with _SHARED_CODEBOOK_LOCK:
        _SHARED_CODEBOOKS.clear()


def decode_suffix(encoded: str, codebook: CrystalTongueCodebook) -> CrystalTongueIR:
    parts = str(encoded or "").split("|")
    if not parts or parts[0] != VERSION:
        raise ValueError("unsupported Crystal Tongue v2 packet")
    fields: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, value = part.partition(":")
        if not separator or key in fields or key not in {"F", "E", "T", "O", "A", "R", "S", "V", "Q"}:
            raise ValueError("malformed Crystal Tongue v2 field")
        fields[key] = value
    if set(fields) != {"F", "E", "T", "O", "A", "R", "S", "V", "Q"}:
        raise ValueError("incomplete Crystal Tongue v2 packet")
    reverse = {entry.code: entry.value for entry in codebook.entries}
    def value(key: str) -> str:
        try:
            return reverse[fields[key]]
        except KeyError as exc:
            raise ValueError("codebook does not contain packet symbol") from exc
    def many(key: str) -> tuple[str, ...]:
        return tuple(value_for(item) for item in fields[key].split(",") if item and item != "-")
    def value_for(code: str) -> str:
        try:
            return unquote(reverse[code])
        except KeyError as exc:
            raise ValueError("codebook does not contain packet symbol") from exc
    return CrystalTongueIR(value("F"), value("E"), value("T"), value("O"), value("A"), many("R"), many("S"), value("V"), many("Q"))
