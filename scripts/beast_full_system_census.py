#!/usr/bin/env python3
"""Generate a deterministic BEAST full-system census.

This scanner intentionally separates static repository facts from runtime truth.
It never treats imports, files, tests, docs, registries, or historical evidence
as proof that a component is constructed or invoked in production.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from copy import deepcopy
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
ALLOWED_DISPOSITIONS = {
    "online_authoritative",
    "online_supporting",
    "supervised_offline",
    "dormant_gated",
    "stranded",
    "duplicate_candidate",
    "compatibility_shim",
    "retired",
    "unclassified",
}
ALLOWED_AGENT_RELEVANCE = {
    "direct", "supporting", "future", "irrelevant", "unclassified",
}
OVERLAY_LIST_FIELDS = {
    "composition_roots", "claimed_responsibilities", "overlap_candidates", "notes",
}
COMPUTE_SOURCE_MAP = {
    "ONLINE_ENFORCEMENT": "online_supporting",
    "SUPERVISED_EVIDENCE": "supervised_offline",
    "OFFLINE_LIBRARY": "stranded",
    "RETIRED": "retired",
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


def _refresh_summary(report: dict[str, Any]) -> None:
    components = report["components"]
    report["summary"] = {
        "component_count": len(components),
        "layer_counts": dict(sorted(Counter(x["layer"] for x in components).items())),
        "language_counts": dict(sorted(Counter(x["language"] for x in components).items())),
        "disposition_counts": dict(sorted(Counter(x["disposition"] for x in components).items())),
        "agent_relevance_counts": dict(sorted(Counter(x["agent_relevance"] for x in components).items())),
    }


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
                "composition_roots": [],
                "claimed_responsibilities": [],
                "overlap_candidates": [],
                "notes": [],
            }
        )

    components.sort(key=lambda item: item["path"])
    report = {
        "beast_object_type": "beast_full_system_census",
        "version": "0.2",
        "methodology": {
            "scope": "static repository inventory plus source-evidence overlays",
            "runtime_truth_rule": (
                "Runtime status is not inferred from imports, file presence, tests, "
                "documentation, registries, source dispositions, or generated artifacts."
            ),
            "ignored_parts": sorted(IGNORED_PARTS),
            "ignored_files": sorted(IGNORED_FILES),
        },
        "summary": {},
        "components": components,
    }
    _refresh_summary(report)
    return report


def load_overrides(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid census overrides: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("components", {}), dict):
        raise ValueError("invalid census overrides: 'components' must be an object")

    components = payload.get("components", {})
    for component_path, override in components.items():
        if not isinstance(component_path, str) or not isinstance(override, dict):
            raise ValueError("invalid census override component record")
        disposition = override.get("disposition")
        if disposition is not None and disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"invalid disposition: {disposition}")
        relevance = override.get("agent_relevance")
        if relevance is not None and relevance not in ALLOWED_AGENT_RELEVANCE:
            raise ValueError(f"invalid agent relevance: {relevance}")
        for field in OVERLAY_LIST_FIELDS:
            value = override.get(field)
            if value is not None and (
                not isinstance(value, list) or not all(isinstance(item, str) for item in value)
            ):
                raise ValueError(f"invalid override field {field}: expected list[str]")
    return payload


def apply_overrides(report: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(report)
    by_path = {item["path"]: item for item in result["components"]}
    stale_paths: list[str] = []
    applied_paths: list[str] = []

    for component_path, override in sorted((overrides.get("components") or {}).items()):
        item = by_path.get(component_path)
        if item is None:
            stale_paths.append(component_path)
            continue
        applied_paths.append(component_path)
        if "disposition" in override:
            item["disposition"] = override["disposition"]
        if "agent_relevance" in override:
            item["agent_relevance"] = override["agent_relevance"]
        for field in ("composition_roots", "claimed_responsibilities", "overlap_candidates"):
            if field in override:
                item[field] = sorted(set(override[field]))
        if "notes" in override:
            item["notes"] = sorted(set(item.get("notes", []) + override["notes"]))

    overlay = dict(result.get("overlay") or {})
    overlay["override_source"] = overrides.get("source", "config/beast_coding_agent_census_overrides.json")
    overlay["applied_paths"] = sorted(applied_paths)
    overlay["stale_paths"] = sorted(stale_paths)
    result["overlay"] = overlay
    _refresh_summary(result)
    return result


def _literal_string_collection(node: ast.AST) -> set[str]:
    target = node
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset":
        if len(node.args) != 1 or node.keywords:
            return set()
        target = node.args[0]
    try:
        value = ast.literal_eval(target)
    except (ValueError, TypeError, SyntaxError):
        return set()
    if not isinstance(value, (set, frozenset, list, tuple)):
        return set()
    return {item for item in value if isinstance(item, str)}


def _read_compute_disposition_source(path: Path) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    found: dict[str, Any] = {}
    wanted = {"ONLINE_ENFORCEMENT", "SUPERVISED_EVIDENCE", "OFFLINE_LIBRARY", "RETIRED"}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in wanted:
            continue
        if name == "RETIRED":
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                value = {}
            found[name] = value if isinstance(value, dict) else {}
        else:
            found[name] = _literal_string_collection(node.value)
    return found


def apply_compute_module_dispositions(report: dict[str, Any], root: Path) -> dict[str, Any]:
    result = deepcopy(report)
    source_path = Path(root).resolve() / "app/kernel/compute/module_dispositions.py"
    source = _read_compute_disposition_source(source_path)
    if not source:
        return result

    by_path = {item["path"]: item for item in result["components"]}
    stale_modules: list[str] = []
    category_counts: Counter[str] = Counter()

    for category in ("ONLINE_ENFORCEMENT", "SUPERVISED_EVIDENCE", "OFFLINE_LIBRARY"):
        for module_name in sorted(source.get(category, set())):
            component_path = f"app/kernel/compute/{module_name}.py"
            item = by_path.get(component_path)
            if item is None:
                stale_modules.append(f"{category}:{module_name}")
                continue
            category_counts[category] += 1
            if item["disposition"] == "unclassified":
                item["disposition"] = COMPUTE_SOURCE_MAP[category]
            item["notes"] = sorted(set(item["notes"] + [f"source_disposition:{category}"]))

    for module_name, reason in sorted((source.get("RETIRED") or {}).items()):
        component_path = f"app/kernel/compute/{module_name}.py"
        item = by_path.get(component_path)
        if item is None:
            stale_modules.append(f"RETIRED:{module_name}")
            continue
        category_counts["RETIRED"] += 1
        item["disposition"] = "retired"
        item["notes"] = sorted(set(item["notes"] + [
            "source_disposition:RETIRED",
            f"source_retired_reason:{reason}",
        ]))

    overlay = dict(result.get("overlay") or {})
    overlay["compute_module_dispositions"] = {
        "source": "app/kernel/compute/module_dispositions.py",
        "category_counts": dict(sorted(category_counts.items())),
        "stale_modules": sorted(stale_modules),
        "runtime_promotion": False,
    }
    result["overlay"] = overlay
    _refresh_summary(result)
    return result


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# BEAST Full System Census",
        "",
        "## Methodology",
        "",
        "**Runtime status is not inferred from imports.** File presence, tests, documentation, "
        "registry entries, source disposition labels, generated evidence, and static reachability "
        "are not sufficient to claim that an organ is constructed or invoked in a live coding-agent request.",
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
    lines.extend(["", "## Disposition counts", "", "| Disposition | Components |", "|---|---:|"])
    for disposition, count in summary.get("disposition_counts", {}).items():
        lines.append(f"| `{disposition}` | {count} |")
    lines.extend(
        [
            "",
            "## Runtime evidence state",
            "",
            "All runtime fields begin as `unverified`. Source-evidence and responsibility overlays "
            "do not promote runtime truth. Phase 0 runtime tracing promotes those fields only when "
            "matching request evidence exists.",
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
    parser.add_argument("--overrides", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    report = scan_repository(root)
    report = apply_compute_module_dispositions(report, root)

    override_path = args.overrides or (root / "config/beast_coding_agent_census_overrides.json")
    if override_path.exists():
        report = apply_overrides(report, load_overrides(override_path))

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
