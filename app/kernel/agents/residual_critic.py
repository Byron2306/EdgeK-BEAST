"""Pre-mutation critic for typed residual candidates."""

from __future__ import annotations

import ast
import re
from typing import Any, Dict


PLACEHOLDER_RE = re.compile(r"(?i)(complete replacement source|replacement code here|insert code|your code|example implementation|\bTODO\b|<MODEL_FILL>|<RESIDUAL>)")


def critique_candidate(*, source: str, old: str, new: str, slot_type: str = "python_expression") -> Dict[str, Any]:
    candidate = str(source or "")
    replacement = str(new or "")
    errors: list[str] = []
    if not replacement.strip():
        errors.append("empty_residual")
    if PLACEHOLDER_RE.search(replacement):
        errors.append("placeholder_detected")
    if not old or candidate.count(old) != 1:
        errors.append("exact_anchor_not_unique")
    composed = candidate.replace(old, replacement, 1) if "exact_anchor_not_unique" not in errors else candidate
    if slot_type.startswith("python"):
        try:
            ast.parse(composed)
        except SyntaxError as exc:
            errors.append(f"syntax:{exc.msg}")
    return {
        "status": "blocked" if errors else "accepted",
        "mutation_authorized": not errors,
        "errors": errors,
        "candidate": composed,
        "stage_order": ["schema", "placeholder", "ast", "scope", "exact_match"],
    }
