#!/usr/bin/env python3
"""Prevent new production imports from deprecated app.kernel compatibility facades."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
DEPRECATED = {
    "app.kernel.task_envelope": "app.kernel.execution.task_envelope",
    "app.kernel.ollama_scout": "app.kernel.local.ollama_scout",
    "app.kernel.commons_spaces": "app.kernel.networking.commons_spaces",
    "app.kernel.canon_registry": "app.kernel.registry.canon_registry",
    "app.kernel.forensic_memory": "app.kernel.storage.forensic_memory",
    "app.kernel.insight_compiler": "app.kernel.data_processing.insight_compiler",
    "app.kernel.beast_cli_executor": "app.kernel.deployment.beast_cli_executor",
}
FACADE_FILES = {APP / Path(module.replace(".", "/") + ".py").relative_to("app") for module in DEPRECATED}


def imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def main() -> int:
    violations: list[dict[str, object]] = []
    parse_failures: list[dict[str, object]] = []
    for path in sorted(APP.rglob("*.py")):
        if path in FACADE_FILES or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            parse_failures.append({"path": str(path.relative_to(ROOT)), "error": str(exc)})
            continue
        for lineno, module in imported_modules(tree):
            for deprecated, canonical in DEPRECATED.items():
                if module == deprecated or module.startswith(deprecated + "."):
                    violations.append({
                        "path": str(path.relative_to(ROOT)),
                        "line": lineno,
                        "deprecated": module,
                        "canonical": canonical,
                    })
    result = {"ok": not violations and not parse_failures, "violations": violations, "parse_failures": parse_failures}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
