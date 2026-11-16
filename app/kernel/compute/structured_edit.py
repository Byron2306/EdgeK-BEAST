"""Structured exact-edit contract for model repair proposals (Ollama specialist + NIM fallback).

A proposal is one JSON object ``{"old_text", "new_text"}`` with optional disambiguators
``anchor_line``, ``before_context``, ``after_context`` and ``occurrence``. Parsing is strict: prose,
partial objects, empty ``old_text`` and no-op edits are rejected, so only an applicable exact edit
ever reaches a verifier. The model output is still only a proposal; the unittest/postcondition
verifier decides.

When ``old_text`` is unique in the target, it is applied as before. When it occurs more than once,
the actuator disambiguates by nearest ``anchor_line``, then surrounding context, then ``occurrence``
(1-based among matches in file order). Still-ambiguous edits are rejected with a candidate list
(line numbers and surrounding lines) so the next model attempt can pick.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

EDIT_ITEM_PROPERTIES: dict[str, Any] = {
    "path": {"type": "string"},
    "old_text": {"type": "string"},
    "new_text": {"type": "string"},
    "anchor_line": {"type": "integer", "minimum": 1, "description": "1-based line of the intended occurrence"},
    "before_context": {"type": "string", "description": "text immediately before old_text"},
    "after_context": {"type": "string", "description": "text immediately after old_text"},
    "occurrence": {"type": "integer", "minimum": 1, "description": "1-based index among matches in file order"},
}
EDIT_OPTIONAL = ("anchor_line", "before_context", "after_context", "occurrence")

EDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {k: v for k, v in EDIT_ITEM_PROPERTIES.items() if k != "path"},
    "required": ["old_text", "new_text"],
    "additionalProperties": False,
}
_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_DISAMBIGUATE = (
    "If old_text occurs more than once, also supply anchor_line (1-based line of the intended "
    "occurrence; nearest wins), and/or before_context and after_context (text immediately before "
    "and after the intended occurrence), and/or occurrence (1-based index among matches)."
)
SYSTEM = ("You are a precise code repair agent. Reply with exactly one JSON object "
          '{"old_text": <exact existing text copied from the file>, "new_text": <replacement>, '
          '"anchor_line": <optional 1-based line>, "before_context": <optional text immediately before>, '
          '"after_context": <optional text immediately after>, "occurrence": <optional 1-based index>} '
          "and nothing else. old_text must be copied exactly from the file. " + _DISAMBIGUATE +
          " Prefer the smallest change that makes the test pass.")
FEW_SHOT: tuple[tuple[str, str], ...] = (
    ("--- app/limits.py ---\nRETRY_LIMIT = 2\nTIMEOUT_S = 30\n--- failing test output ---\n"
     "AssertionError: 2 != 4",
     '{"old_text": "RETRY_LIMIT = 2", "new_text": "RETRY_LIMIT = 4"}'),
    ("--- util/window.py ---\ndef last(items, n):\n    return items[-n - 1:]\n--- failing test output ---\n"
     "AssertionError: Lists differ: [3, 4, 5] != [4, 5]",
     '{"old_text": "    return items[-n - 1:]", "new_text": "    return items[-n:]"}'),
)


def _optional_edit_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep recognized disambiguators; ignore missing, empty, or unparsable values."""
    out: dict[str, Any] = {}
    for key in ("anchor_line", "occurrence"):
        if key not in value or value[key] is None:
            continue
        try:
            number = int(value[key])
        except (TypeError, ValueError):
            continue
        if number >= 1:
            out[key] = number
    for key in ("before_context", "after_context"):
        if isinstance(value.get(key), str) and value[key]:
            out[key] = value[key]
    return out


def parse_edit(text: str) -> dict[str, Any] | None:
    text = _THINK.sub("", str(text or ""))
    blobs = [m.strip() for m in _FENCE.findall(text)] + [text.strip()]
    blobs += re.findall(r"\{.*\}", text, flags=re.S)
    for blob in blobs:
        try:
            value = json.loads(blob)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        old, new = value.get("old_text"), value.get("new_text")
        if isinstance(old, str) and isinstance(new, str):
            old, new = old.rstrip("\n"), new.rstrip("\n")
            if old and old != new:
                return {"old_text": old, "new_text": new, **_optional_edit_fields(value)}
    return None


def edit_messages(target: str, content: str, failure: str, *, hint: str = "") -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": SYSTEM}]
    for user, assistant in FEW_SHOT:
        msgs += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    body = f"--- {target} ---\n{content}\n--- failing test output ---\n{failure[-1500:]}"
    msgs.append({"role": "user", "content": (hint + "\n" if hint else "") + body})
    return msgs


def repair_message(previous: str, reason: str) -> dict[str, str]:
    return {"role": "user", "content": (
        f"Your previous reply was rejected by the verifier ({reason}). Previous reply:\n{str(previous)[:600]}\n"
        "Reply again with exactly one JSON object {\"old_text\", \"new_text\"} and, if old_text is not unique, "
        "anchor_line, before_context/after_context, or occurrence; old_text must be copied exactly "
        "from the file.")}


def nim_request_extras(*, thinking: bool) -> dict[str, Any]:
    """NIM/OpenAI-compatible request extras. Nemotron honours chat_template_kwargs.enable_thinking."""
    return {} if thinking else {"chat_template_kwargs": {"enable_thinking": False}}


# -- multi-file form (rename/refactor/tool-chain tasks) ------------------------------------------------------------
EDITS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"edits": {"type": "array", "minItems": 1, "maxItems": 8, "items": {
        "type": "object",
        "properties": dict(EDIT_ITEM_PROPERTIES),
        "required": ["path", "old_text", "new_text"], "additionalProperties": False}}},
    "required": ["edits"],
    "additionalProperties": False,
}
EDITS_SYSTEM = ("You are a precise code repair agent. Reply with exactly one JSON object "
                '{"edits": [{"path": <repo-relative file>, "old_text": <exact existing text>, '
                '"new_text": <replacement>, "anchor_line": <optional 1-based line>, '
                '"before_context": <optional text immediately before>, "after_context": <optional text immediately after>, '
                '"occurrence": <optional 1-based index>}]} '
                "and nothing else. Each old_text must be copied exactly from that file. " + _DISAMBIGUATE +
                " Use the fewest edits that make the failing tests pass; never edit test files.")
EDITS_FEW_SHOT: tuple[tuple[str, str], ...] = (
    ("--- app/limits.py ---\nRETRY_LIMIT = 2\nTIMEOUT_S = 30\n--- failing test output ---\nAssertionError: 2 != 4",
     '{"edits": [{"path": "app/limits.py", "old_text": "RETRY_LIMIT = 2", "new_text": "RETRY_LIMIT = 4"}]}'),
    ("--- shop/core.py ---\ndef get_cart(user):\n    return []\n--- shop/api.py ---\nfrom shop.core import get_cart\n"
     "\n\ndef view(user):\n    return get_cart(user)\n--- failing test output ---\n"
     "ImportError: cannot import name 'load_cart' from 'shop.core'",
     '{"edits": [{"path": "shop/core.py", "old_text": "def get_cart(user):", "new_text": "def load_cart(user):"}, '
     '{"path": "shop/api.py", "old_text": "from shop.core import get_cart", "new_text": "from shop.core import load_cart"}, '
     '{"path": "shop/api.py", "old_text": "    return get_cart(user)", "new_text": "    return load_cart(user)"}]}'),
)


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and ".." not in path.split("/")


def parse_edits(text: str, *, default_path: str) -> list[dict[str, Any]] | None:
    text = _THINK.sub("", str(text or ""))
    blobs = [m.strip() for m in _FENCE.findall(text)] + [text.strip()] + re.findall(r"\{.*\}", text, flags=re.S)
    for blob in blobs:
        try:
            value = json.loads(blob)
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("edits"), list):
            out = []
            for item in value["edits"][:8]:
                if not isinstance(item, dict):
                    return None
                path, old, new = item.get("path"), item.get("old_text"), item.get("new_text")
                if not (isinstance(path, str) and isinstance(old, str) and isinstance(new, str)) or not _safe_path(path):
                    return None
                if old.rstrip("\n") and old != new:
                    out.append({"path": path, "old_text": old.rstrip("\n"), "new_text": new.rstrip("\n"),
                                **_optional_edit_fields(item)})
            return out or None
        single = parse_edit(blob) if isinstance(value, dict) else None
        if single:
            return [{"path": default_path, **single}]
    return None


def edits_messages(files: dict[str, str], failure: str, *, target: str = "") -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": EDITS_SYSTEM}]
    for user, assistant in EDITS_FEW_SHOT:
        msgs += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    body = "".join(f"--- {path} ---\n{content}\n" for path, content in files.items())
    head = f"Implementation target: {target}\n" if target else ""
    msgs.append({"role": "user", "content": f"{head}{body}--- failing test output ---\n{failure[-1800:]}"})
    return msgs


_STUB_LINES = {"pass", "return", "return none", "...", "return ...", "return 0", "return ''", 'return ""', "return []",
               "return {}", "return false", "return true"}


def degenerate_edit(edit: dict[str, str]) -> str | None:
    """Reason string when an edit erases the computation it replaces with a bare stub (e.g. ``return None``).

    Such edits can satisfy a weak visible verifier while destroying intent, so the gate refuses them outright.
    """
    new_lines = [ln.strip().lower() for ln in str(edit.get("new_text", "")).splitlines() if ln.strip()]
    old_lines = [ln.strip().lower() for ln in str(edit.get("old_text", "")).splitlines() if ln.strip()]
    if not new_lines or not all(" ".join(ln.split()) in _STUB_LINES for ln in new_lines):
        return None
    if old_lines and all(" ".join(ln.split()) in _STUB_LINES for ln in old_lines):
        return None
    return f"degenerate_edit:stub_replaces_logic:{edit.get('path', '')}"


# -- line-anchored / context-expanded actuator ---------------------------------------------------------------------
class EditApplyError(PermissionError):
    """The exact edit cannot be applied uniquely (nothing is written)."""

    def __init__(self, message: str, *, candidates: list[Occurrence] | None = None):
        super().__init__(message)
        self.candidates = list(candidates or [])


@dataclass(frozen=True)
class Occurrence:
    start: int
    end: int
    line: int
    end_line: int
    index: int  # 1-based among non-overlapping matches in file order


def find_occurrences(text: str, old_text: str) -> list[Occurrence]:
    """Non-overlapping matches, matching ``str.count`` / ``str.replace(..., 1)`` semantics."""
    old = old_text.rstrip("\n") if old_text else ""
    if not old:
        return []
    out: list[Occurrence] = []
    start, index = 0, 0
    while start <= len(text):
        found = text.find(old, start)
        if found < 0:
            break
        index += 1
        end = found + len(old)
        out.append(Occurrence(found, end, text.count("\n", 0, found) + 1,
                              text.count("\n", 0, end) + 1, index))
        start = end
    return out


def _int_field(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def _surrounding(text: str, occ: Occurrence, *, radius: int = 2) -> str:
    lines = text.splitlines()
    lo = max(1, occ.line - radius)
    hi = min(len(lines), occ.end_line + radius)
    return "\n".join(f"{n:>4}|{lines[n - 1]}" for n in range(lo, hi + 1))


def format_candidates(text: str, matches: list[Occurrence], path: str = "") -> str:
    loc = f" in {path}" if path else ""
    lines = [f"edit old_text is not unique in target ({len(matches)} matches{loc}). Candidates:"]
    for occ in matches:
        lines.append(f"  occurrence={occ.index}, line {occ.line}:")
        lines.append(_surrounding(text, occ))
    lines.append("Supply anchor_line (1-based, nearest wins), before_context/after_context, or occurrence to pick one.")
    return "\n".join(lines)


def resolve_occurrence(text: str, edit: Mapping[str, Any], *, path: str = "") -> Occurrence:
    """Pick the unique intended match, or raise ``EditApplyError`` with a candidate list."""
    old = str(edit.get("old_text") or "").rstrip("\n")
    found = find_occurrences(text, old)
    loc = f" in {path}" if path else ""
    if not old or not found:
        raise EditApplyError(f"edit old_text is not unique in target (0 matches{loc})")
    if len(found) == 1:
        return found[0]

    remaining = list(found)
    anchor = _int_field(edit.get("anchor_line"))
    if anchor is not None:
        best = min(abs(occ.line - anchor) for occ in remaining)
        nearest = [occ for occ in remaining if abs(occ.line - anchor) == best]
        if len(nearest) == 1:
            return nearest[0]
        remaining = nearest

    before = edit.get("before_context") if isinstance(edit.get("before_context"), str) else ""
    after = edit.get("after_context") if isinstance(edit.get("after_context"), str) else ""
    if before or after:
        filtered = [occ for occ in remaining
                    if (not before or text[:occ.start].endswith(before))
                    and (not after or text[occ.end:].startswith(after))]
        if len(filtered) == 1:
            return filtered[0]
        if filtered:
            remaining = filtered

    occurrence = _int_field(edit.get("occurrence"))
    if occurrence is not None:
        by_index = {occ.index: occ for occ in remaining}
        if occurrence in by_index:
            return by_index[occurrence]
        raise EditApplyError(
            f"edit old_text is not unique in target (occurrence={occurrence} not in remaining matches{loc}).\n"
            + format_candidates(text, remaining, path),
            candidates=remaining,
        )

    raise EditApplyError(format_candidates(text, remaining, path), candidates=remaining)


def atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` via a same-directory temp file and ``os.replace``."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".beast-edit-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def apply_one_edit(path: Path, edit: Mapping[str, Any]) -> None:
    """Resolve and apply one exact edit to ``path`` (atomic replace). Raises ``EditApplyError``."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    rel = str(edit.get("path") or path.name)
    occ = resolve_occurrence(text, edit, path=rel)
    new = str(edit.get("new_text") or "").rstrip("\n")
    atomic_write(path, text[:occ.start] + new + text[occ.end:])


__all__ = [
    "EDITS_SCHEMA", "EDIT_SCHEMA", "EDIT_ITEM_PROPERTIES", "EDIT_OPTIONAL", "EditApplyError", "Occurrence",
    "FEW_SHOT", "SYSTEM", "action_optional_fields", "apply_one_edit", "atomic_write", "degenerate_edit",
    "edits_messages", "edit_messages", "find_occurrences", "format_candidates", "nim_request_extras",
    "parse_edit", "parse_edits", "repair_message", "resolve_occurrence",
]


def action_optional_fields(edit: Mapping[str, Any]) -> dict[str, Any]:
    """Copy recognized disambiguators from a model action item onto an actuator edit."""
    return _optional_edit_fields(edit)
