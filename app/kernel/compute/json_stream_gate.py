"""Incremental JSON action gate for streamed model output (step 5: stream).

Feeds on text deltas; the moment the first complete top-level JSON object (or
array) has arrived *and* validates against the action schema, ``feed``
returns ``"stop"`` so the caller can close the upstream stream and stop
paying for tokens.  It also flags runaway output (no JSON start within a
prose budget, or repetition) so the governed client can cut a stall early.

Understands string escapes, skips ``<think>...</think>`` blocks and markdown
fences, and never executes anything.  Deterministic and dependency-light
(jsonschema optional; a minimal required-keys check is used without it).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

try:  # pragma: no cover - availability depends on env
    import jsonschema as _jsonschema
except Exception:  # pragma: no cover
    _jsonschema = None


def schema_valid(value: Any, schema: Optional[Mapping[str, Any]]) -> tuple[bool, str]:
    if not schema:
        return True, ""
    if _jsonschema is not None:
        try:
            _jsonschema.validate(value, dict(schema))
            return True, ""
        except Exception as exc:  # jsonschema.ValidationError and SchemaError
            return False, str(getattr(exc, "message", exc))[:200]
    if schema.get("type") == "object":
        if not isinstance(value, dict):
            return False, "not_object"
        missing = [k for k in schema.get("required", []) if k not in value]
        return (not missing), (f"missing:{missing}" if missing else "")
    return True, ""


@dataclass
class JsonStreamGate:
    schema: Optional[Mapping[str, Any]] = None
    prose_budget_chars: int = 4000      # max chars of non-JSON preamble before declaring runaway
    max_chars: int = 60000              # absolute cap on accumulated output
    buffer: str = ""
    state: str = "scanning"             # scanning | in_json | complete | invalid | runaway
    value: Any = None
    error: str = ""
    stop_reason: str = ""
    chars_at_stop: int = 0
    _start: int = -1
    _depth: int = 0
    _in_str: bool = False
    _esc: bool = False
    _pos: int = 0
    _in_think: bool = False
    _attempts: int = 0
    extras: dict = field(default_factory=dict)

    def feed(self, delta: str) -> str:
        """Consume a delta. Returns ``continue`` | ``stop`` | ``runaway``."""
        if self.state in {"complete", "runaway"}:
            return "stop" if self.state == "complete" else "runaway"
        self.buffer += delta or ""
        text = self.buffer
        while self._pos < len(text):
            ch = text[self._pos]
            if self.state == "scanning":
                rest = text[self._pos:self._pos + 8]
                if ch == "<" and len(rest) < 8 and ("<think>".startswith(rest) or "</think>".startswith(rest)):
                    break  # tag split across deltas: wait for more text
                if text.startswith("<think>", self._pos):
                    self._in_think = True
                    self._pos += 7
                    continue
                if self._in_think:
                    if text.startswith("</think>", self._pos):
                        self._in_think = False
                        self._pos += 8
                        continue
                    self._pos += 1
                    continue
                if ch in "{[":
                    self.state, self._start, self._depth = "in_json", self._pos, 0
                    continue
                self._pos += 1
                continue
            # in_json
            if self._in_str:
                if self._esc:
                    self._esc = False
                elif ch == "\\":
                    self._esc = True
                elif ch == '"':
                    self._in_str = False
            elif ch == '"':
                self._in_str = True
            elif ch in "{[":
                self._depth += 1
            elif ch in "}]":
                self._depth -= 1
                if self._depth == 0:
                    candidate = text[self._start:self._pos + 1]
                    self._pos += 1
                    try:
                        value = json.loads(candidate)
                    except ValueError as exc:
                        self._reset_scan(f"json_error:{exc}")
                        continue
                    ok, why = schema_valid(value, self.schema)
                    if ok:
                        self.value, self.state, self.stop_reason = value, "complete", "schema_valid_action"
                        self.chars_at_stop = self._pos
                        return "stop"
                    self._reset_scan(f"schema_invalid:{why}")
                    continue
            self._pos += 1
        if self.state == "scanning" and not self._in_think and len(self._visible_prose()) > self.prose_budget_chars:
            self.state, self.stop_reason = "runaway", "prose_without_action"
            return "runaway"
        if len(text) > self.max_chars or self._repetitive(text):
            self.state, self.stop_reason = "runaway", "runaway_output"
            return "runaway"
        return "continue"

    def _reset_scan(self, why: str) -> None:
        self._attempts += 1
        self.error = why
        self.state, self._start, self._depth, self._in_str, self._esc = "scanning", -1, 0, False, False

    def _visible_prose(self) -> str:
        return re.sub(r"<think>.*?</think>", "", self.buffer, flags=re.S)

    @staticmethod
    def _repetitive(text: str) -> bool:
        tail = text[-1200:]
        if len(tail) < 1200:
            return False
        unit = tail[-60:]
        return tail.count(unit) >= 12

    def finish(self) -> dict[str, Any]:
        """Final parse for streams that ended without an early stop."""
        if self.state != "complete" and self.value is None:
            visible = self._visible_prose()
            fenced = re.findall(r"```(?:json)?\s*(.*?)```", visible, flags=re.S)
            for chunk in fenced + [visible]:
                start = min([i for i in (chunk.find("{"), chunk.find("[")) if i >= 0], default=-1)
                if start < 0:
                    continue
                try:
                    value, _ = json.JSONDecoder().raw_decode(chunk[start:])
                except ValueError:
                    continue
                ok, why = schema_valid(value, self.schema)
                if ok:
                    self.value, self.state = value, "complete_at_end"
                    break
                self.error = f"schema_invalid:{why}"
        return {"state": self.state, "valid": self.value is not None, "value": self.value, "error": self.error,
                "stop_reason": self.stop_reason, "chars_total": len(self.buffer), "chars_at_stop": self.chars_at_stop,
                "invalid_candidates": self._attempts}


__all__ = ["JsonStreamGate", "schema_valid"]
