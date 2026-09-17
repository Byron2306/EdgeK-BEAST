#!/usr/bin/env python3
"""Generate a deterministic BEAST full-system census.

This scanner intentionally separates static repository facts from runtime truth.
It never treats imports, files, tests, or docs as proof that a component is
constructed or invoked in production.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

SCANNED_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".yml", ".yaml", ".json", ".toml", ".sh", ".ps1",
}
IGNORED_PARTS = {
    ".git", ".beast_backups", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build",
    ".venv", "venv",
}
IGNORED_FILES = {
    "docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json",
}

JS_IMPORT_PATTERNS = (
    re.compile(r'''(?:import|export)\s+(?:[^'\"]*?\s+from\s+)?['\"]([^'\"]+)['\"]'''),
    re.compile(r'''require\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
    re.compile(r'''import\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
)


def classify_layer(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("desktop-ide/"):
        return "interface_ingress"
    if p.startswith("app/routes/"):
        return "interface_ingress"
    if p.startswith("app/kernel/agents/"):
        return "agency_planning"
    if p.startswith("app/kernel/data_processing/"):
        return "semantic_context"
    if "/sensorium/" in f"/{p}" or "sensorium" in Path(p).name.lower():
        return "perception_sensorium"
    if p.startswith("app/kernel/compute/"):
        return "compute_reuse"
    if p.startswith("app/kernel/crystal_bus/"):
        return "crystal_transport"
    if p.startswith("app/kernel/storage/"):
        return "memory_evidence"
    if p.startswith(("app/kernel/governance/", "app/kernel/approvals/", "app/kernel/capability/")):
        return "governance_authority"
    if p.startswith("app/kernel/execution/"):
        return "execution"
    if p.startswith("app/kernel/commons/"):
        return "distributed_commons"
    if p.startswith("app/kernel/workspaces/"):
        return "workspace_state"
    if p.startswith(".github/workflows/"):
        return "ci_proof"
    if p.startswith("scripts/"):
        return "operations_proof"
    if p.startswith("tests/"):
        return "verification_tests"
    if p.startswith("app/kernel/"):
        return "kernel_other"
    if p.startswith("app/"):
        return "app_other"
    return "repository_support"


def language_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".sh": "shell",
        ".ps1": "powershell",
    }.get(suffix, suffix.lstrip(".") or "unknown")


def python_imports(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * int(node.level or 0)
            for alias in node.names:
                if alias.name == "*":
                    values.add(f"{prefix}{module}.*".rstrip("."))
                elif module:
                    values.add(f"{prefix}{module}.{alias.name}")
                else:
                    values.add(f"{prefix}{alias.name}")
    return sorted(values)


def javascript_imports(text: str) -> list[str]:
    values: set[str] = set()
    for pattern in JS_IMPORT_PATTERNS:
        values.update(pattern.findall(text))
    return sorted(values)


def extract_imports(path: Path, text: str) -> list[str]:
    if path.suffix.lower() == ".py":
        return python_imports(text)
    if path.suffix.lower() in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
        return javascript_imports(text)
    return []


def _iter_scannable_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in IGNORED_FILES:
            continue
        if any(part in IGNORED_PARTS for part in rel.parts):
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        yield path


def scan_repository(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    components = []
    for path in _iter_scannable_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        components.append(
            {
                "path": rel,
                "language": language_for(path),
                "layer": classify_layer(rel),
                "imports": extract_imports(path, text),
                "runtime": {
                    "constructed": "unverified",
                    "invoked": "unverified",
                    "evidence_producing": "unverified",
                },
                "authority": "unverified",
                "disposition": "unclassified",
                "agent_relevance": "unclassified",
                "notes": [],
            }
        )

    components.sort(key=lambda item: item["path"])
    layer_counts = dict(sorted(Counter(x["layer"] for x in components).items()))
    language_counts = dict(sorted(Counter(x["language"] for x in components).items()))
    return {
        "beast_object_type": "beast_full_system_census",
        "version": "0.1",
        "methodology": {
            "scope": "static repository inventory",
            "runtime_truth_rule": (
                "Runtime status is not inferred from imports, file presence, tests, "
                "documentation, registries, or generated artifacts."
            ),
            "ignored_parts": sorted(IGNORED_PARTS),
            "ignored_files": sorted(IGNORED_FILES),
        },
        "summary": {
            "component_count": len(components),
            "layer_counts": layer_counts,
            "language_counts": language_counts,
        },
        "components": components,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# BEAST Full System Census",
        "",
        "## Methodology",
        "",
        "**Runtime status is not inferred from imports.** File presence, tests, documentation, "
        "registry entries, generated evidence, and static reachability are not sufficient to "
        "claim that an organ is constructed or invoked in a live coding-agent request.",
        "",
        f"Static components discovered: **{summary['component_count']}**",
        "",
        "## Layer counts",
        "",
        "| Layer | Components |",
        "|---|---:|",
    ]
    for layer, count in summary["layer_counts"].items():
        lines.append(f"| `{layer}` | {count} |")
    lines.extend(
        [
            "",
            "## Runtime evidence state",
            "",
            "All runtime fields begin as `unverified`. Phase 0 runtime tracing and composition-root "
            "analysis promote those fields only when evidence exists.",
            "",
            "## Component inventory",
            "",
            "| Path | Layer | Language | Constructed | Invoked | Disposition |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in report["components"]:
        lines.append(
            f"| `{item['path']}` | `{item['layer']}` | `{item['language']}` | "
            f"`{item['runtime']['constructed']}` | `{item['runtime']['invoked']}` | "
            f"`{item['disposition']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()

    report = scan_repository(args.root)
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(report)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json_text, encoding="utf-8")
    else:
        print(json_text, end="")

    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(md_text, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
