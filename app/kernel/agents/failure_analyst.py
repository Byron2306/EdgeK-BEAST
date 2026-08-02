"""Deterministic classification of verifier failures into repair slots."""

from __future__ import annotations

import re
from typing import Any, Dict


def _match(pattern: str, message: str) -> str:
    found = re.search(pattern, message, re.IGNORECASE)
    return found.group(1) if found else ""


def analyze_failure(text: str) -> Dict[str, Any]:
    message = str(text or "")
    lower = message.casefold()
    missing_symbol = _match(r"name ['\"]([^'\"]+)['\"] is not defined", message)
    missing_module = _match(r"no module named ['\"]([^'\"]+)['\"]", message)
    if "syntaxerror" in lower or "indentationerror" in lower or "unterminated" in lower or "eof while scanning" in lower:
        kind, slot_type, next_action, confidence = "bad_patch", "syntax_region", "repair_changed_patch_region", 0.92
    elif "nameerror" in lower or "no module named" in lower or "importerror" in lower or "cannot find module" in lower or "module not found" in lower:
        kind, slot_type, next_action, confidence = "dependency_missing", "import_or_dependency", "add_or_correct_import_or_dependency", 0.88
    elif "connection refused" in lower or "timed out" in lower or "timeout" in lower or "econnreset" in lower or "temporarily unavailable" in lower:
        kind, slot_type, next_action, confidence = "environment_issue", "runtime_environment", "retry_or_repair_environment_before_code", 0.84
    elif "flaky" in lower or "rerun" in lower or "race condition" in lower or "intermittent" in lower or "randomly failed" in lower:
        kind, slot_type, next_action, confidence = "flaky_test", "test_stability", "rerun_then_isolate_flake", 0.78
    elif "assertionerror" in lower or "expected" in lower and "actual" in lower or "assert " in lower or "failed" in lower:
        kind, slot_type, next_action, confidence = "logic_regression", "behavioral_expression", "inspect_assertion_and_repair_logic", 0.76
    else:
        kind, slot_type, next_action, confidence = "unknown", "diagnostic_context", "inspect_failure_context", 0.4
    retryable = kind in {"environment_issue", "flaky_test"}
    code_repair = kind in {"bad_patch", "dependency_missing", "logic_regression", "unknown"}
    return {
        "failure_class": kind,
        "slot_type": slot_type,
        "missing_symbol": missing_symbol,
        "missing_module": missing_module,
        "repair_required": True,
        "retryable_without_code_change": retryable,
        "code_repair_likely": code_repair,
        "confidence": confidence,
        "next_action": next_action,
        "escalation_hint": "stronger_model_recommended" if kind in {"logic_regression", "unknown"} else "",
    }
