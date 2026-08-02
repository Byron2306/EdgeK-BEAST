"""Action IR helpers for BEAST IDE agent/sourceplan routes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable


def action_ir_anchor_hints(
    root: Path | None,
    allowed_files: list[str],
    *,
    build_file_references: Callable[[Path, list[str]], Any],
) -> str:
    if root is None or not allowed_files:
        return ""
    try:
        refs = build_file_references(root, allowed_files[:8])
    except Exception:
        return ""
    chunks: list[str] = []
    for ref in refs:
        anchors = list((ref.anchors or {}).items())[:8]
        if not anchors:
            continue
        chunks.append(f"{ref.path}:")
        for anchor_id, snippet in anchors:
            compact = str(snippet).strip()
            if compact:
                chunks.append(f"[{anchor_id}] {compact[:500]}")
    hints = "\n".join(chunks).strip()
    return hints[:5000]


def action_ir_retry_prompt(
    objective: str,
    previous_output: str,
    allowed_files: list[str],
    *,
    action_ir_kind: str,
    diagnostics: str = "",
    root: Path | None = None,
    build_file_references: Callable[[Path, list[str]], Any],
) -> str:
    allowed = "\n".join(f"- {path}" for path in allowed_files) or "- provide one allowed file first"
    bounded_previous = str(previous_output or "")[:8000]
    bounded_diagnostics = str(diagnostics or "")[:4000]
    anchor_hints = action_ir_anchor_hints(root, allowed_files, build_file_references=build_file_references)
    return (
        "Return BEAST Action IR JSON only. Do not include markdown, prose, or explanation.\n\n"
        f"Objective: {objective or 'Convert the prior answer into a governed file edit.'}\n"
        "Allowed files:\n"
        f"{allowed}\n\n"
        f"Schema:\n{{\"kind\": \"{action_ir_kind}\", \"objective\": \"...\", \"actions\": [{{\"type\": \"replace_exact\", \"target\": {{\"path\": \"relative/file.py\", \"anchor_ref\": \"A1\"}}, \"old\": \"exact old snippet (omit when using anchor_ref)\", \"new\": \"replacement for the complete anchor\"}}]}}\n\n"
        "Rules:\n"
        "1. Use only allowed files.\n"
        "2. Use exact old snippets that exist in the file today.\n"
        "2a. If a short old snippet appears more than once, use one of the supplied target.anchor_ref values and make new a replacement for that complete anchor; never guess which duplicate occurrence to change.\n"
        "3. Emit the complete valid set of replace_exact actions required by the objective, including directly affected tests, callers, and configuration when they are in scope. Do not omit a required edit merely to keep the patch small.\n"
        "3a. Emit at most one source-edit action per file. If a file needs several changes, use one complete anchor replacement that incorporates all of them; sequential edits to the same file are not accepted.\n"
        "4. Return one JSON object and nothing else.\n"
        "5. Correct every validation diagnostic below without expanding scope.\n\n"
        + (f"Validation diagnostics from the proposed files:\n{bounded_diagnostics}\n\n" if bounded_diagnostics else "")
        + (f"Exact snippets available in the allowed files. Prefer these snippets as old anchors:\n{anchor_hints}\n\n" if anchor_hints else "")
        + "Previous answer to convert:\n"
        f"{bounded_previous}"
    )


def reject_incomplete_function_replacements(actions: list[Any]) -> str:
    """Reject a common model failure before it is rendered as a patch."""
    for index, raw in enumerate(actions):
        if not isinstance(raw, dict):
            continue
        old = str(raw.get("old") or "").strip()
        new = str(raw.get("new") or "").strip()
        if (
            re.fullmatch(r"(?:async\s+)?def\s+[A-Za-z_]\w*\s*\([^\n]*\)\s*(?:->[^\n:]+)?\s*:", old)
            and re.match(r"(?:async\s+)?def\s+[A-Za-z_]\w*\s*\(", new)
            and "\n" in new
        ):
            return (
                f"action {raw.get('id') or raw.get('op_id') or f'a{index + 1}'} uses only a function header as its old anchor. "
                "The model must replace the complete anchored function, not append a new body after its header."
            )
    return ""
