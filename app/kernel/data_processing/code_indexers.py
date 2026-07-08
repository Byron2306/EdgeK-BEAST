"""Lightweight repository code indexing helpers for WorkspaceGraph.

These helpers intentionally stay dependency-free. They give BEAST a richer
local graph baseline before any optional tree-sitter/Gortex integration.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}

SOURCE_SUFFIXES = set(LANGUAGE_BY_SUFFIX)
TEST_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def language_for_path(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "text")


def test_runner_for_path(rel_path: str, language: str, content: str) -> str:
    lower = rel_path.lower()
    basename = Path(rel_path).name.lower()
    if language == "python" and (
        basename.startswith("test_") or basename.endswith("_test.py") or "/tests/" in f"/{lower}"
    ):
        return "pytest"
    if language in {"javascript", "typescript"} and (
        basename.endswith((".test.js", ".spec.js", ".test.jsx", ".spec.jsx", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
        or "/__tests__/" in f"/{lower}"
    ):
        if "vitest" in content:
            return "vitest"
        if "@playwright/test" in content:
            return "playwright"
        return "jest"
    return ""


def file_metadata(path: Path, root: Path, content: str) -> Dict[str, Any]:
    rel_path = path.relative_to(root).as_posix()
    language = language_for_path(path)
    stat = path.stat()
    lines = content.splitlines()
    content_hash = sha256_text(content)
    test_runner = test_runner_for_path(rel_path, language, content)
    return {
        "path": rel_path,
        "absolute_path": str(path),
        "suffix": path.suffix.lower(),
        "language": language,
        "size_bytes": int(stat.st_size),
        "line_count": len(lines) or 1,
        "mtime": int(stat.st_mtime),
        "mtime_ns": int(stat.st_mtime_ns),
        "content_hash": content_hash,
        "sha256": content_hash,
        "preview": content[:1200],
        "is_test": bool(test_runner),
        "test_runner": test_runner,
    }


def extract_symbols(content: str, language: str, rel_path: str) -> List[Dict[str, Any]]:
    if language == "python":
        return _extract_python_symbols(content, rel_path)
    if language in {"javascript", "typescript"}:
        return _extract_jsts_symbols(content, rel_path)
    if language == "markdown":
        return _extract_markdown_sections(content, rel_path)
    return []


def _extract_python_symbols(content: str, rel_path: str) -> List[Dict[str, Any]]:
    symbols: List[Dict[str, Any]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "file": rel_path,
                    "line": int(node.lineno),
                    "end_line": int(getattr(node, "end_lineno", node.lineno) or node.lineno),
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "file": rel_path,
                    "line": int(node.lineno),
                    "end_line": int(getattr(node, "end_lineno", node.lineno) or node.lineno),
                    "async": isinstance(node, ast.AsyncFunctionDef),
                })
        return sorted(symbols, key=lambda item: (int(item.get("line") or 0), str(item.get("name") or "")))

    for idx, line in enumerate(content.splitlines(), start=1):
        match = re.match(r"\s*(?:(async)\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if match:
            symbols.append({
                "name": match.group(2),
                "kind": "function" if "def" in line else "class",
                "file": rel_path,
                "line": idx,
                "end_line": idx,
                "async": bool(match.group(1)),
            })
    return symbols


def _extract_jsts_symbols(content: str, rel_path: str) -> List[Dict[str, Any]]:
    patterns = [
        ("class", r"\bclass\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
        ("function", r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
        ("function", r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\("),
        ("function", r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?function\b"),
    ]
    symbols: List[Dict[str, Any]] = []
    seen = set()
    for idx, line in enumerate(content.splitlines(), start=1):
        for kind, pattern in patterns:
            match = re.search(pattern, line)
            if match:
                key = (match.group(1), idx)
                if key not in seen:
                    symbols.append({"name": match.group(1), "kind": kind, "file": rel_path, "line": idx, "end_line": idx})
                    seen.add(key)
                break
    return symbols


def _extract_markdown_sections(content: str, rel_path: str) -> List[Dict[str, Any]]:
    symbols: List[Dict[str, Any]] = []
    for idx, line in enumerate(content.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            symbols.append({
                "name": match.group(2).strip(),
                "kind": "section",
                "file": rel_path,
                "line": idx,
                "end_line": idx,
                "level": len(match.group(1)),
            })
    return symbols


def extract_imports(content: str, language: str, rel_path: str) -> List[Dict[str, Any]]:
    if language == "python":
        return _extract_python_imports(content, rel_path)
    if language in {"javascript", "typescript"}:
        return _extract_jsts_imports(content, rel_path)
    if language in {"json", "yaml", "toml"}:
        return _extract_config_references(content, language, rel_path)
    return []


def extract_routes(content: str, language: str, rel_path: str) -> List[Dict[str, Any]]:
    """Extract lightweight HTTP/API route declarations from common frameworks."""
    routes: List[Dict[str, Any]] = []
    if language == "python":
        decorator = re.compile(
            r"^\s*@(?P<router>[A-Za-z_][A-Za-z0-9_\.]*)\.(?P<method>get|post|put|patch|delete|options|head)\(\s*['\"](?P<path>[^'\"]+)['\"]",
            re.IGNORECASE,
        )
        flask = re.compile(
            r"^\s*@(?P<router>[A-Za-z_][A-Za-z0-9_\.]*)\.route\(\s*['\"](?P<path>[^'\"]+)['\"](?:.*?methods\s*=\s*\[(?P<methods>[^\]]+)\])?",
            re.IGNORECASE,
        )
        for idx, line in enumerate(content.splitlines(), start=1):
            match = decorator.search(line)
            if match:
                routes.append({
                    "path": match.group("path"),
                    "method": match.group("method").upper(),
                    "framework_hint": "fastapi",
                    "router": match.group("router"),
                    "line": idx,
                    "file": rel_path,
                })
                continue
            match = flask.search(line)
            if match:
                methods = [item.strip(" '\"").upper() for item in (match.group("methods") or "GET").split(",")]
                for method in methods:
                    if method:
                        routes.append({
                            "path": match.group("path"),
                            "method": method,
                            "framework_hint": "flask",
                            "router": match.group("router"),
                            "line": idx,
                            "file": rel_path,
                        })
    elif language in {"javascript", "typescript"}:
        express = re.compile(
            r"\b(?P<router>app|router)\.(?P<method>get|post|put|patch|delete|options|head)\(\s*['\"](?P<path>[^'\"]+)['\"]",
            re.IGNORECASE,
        )
        for idx, line in enumerate(content.splitlines(), start=1):
            match = express.search(line)
            if match:
                routes.append({
                    "path": match.group("path"),
                    "method": match.group("method").upper(),
                    "framework_hint": "express",
                    "router": match.group("router"),
                    "line": idx,
                    "file": rel_path,
                })
    return routes


def _extract_python_imports(content: str, rel_path: str) -> List[Dict[str, Any]]:
    imports: List[Dict[str, Any]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"name": alias.name, "module": alias.name, "line": int(node.lineno), "file": rel_path})
            elif isinstance(node, ast.ImportFrom):
                module = "." * int(node.level or 0) + str(node.module or "")
                imports.append({"name": module, "module": module, "line": int(node.lineno), "file": rel_path})
        return imports

    for idx, line in enumerate(content.splitlines(), start=1):
        match = re.match(r"\s*(?:from\s+([A-Za-z0-9_\.]+)\s+import|import\s+([A-Za-z0-9_\.]+))", line)
        if match:
            module = match.group(1) or match.group(2)
            imports.append({"name": module, "module": module, "line": idx, "file": rel_path})
    return imports


def _extract_jsts_imports(content: str, rel_path: str) -> List[Dict[str, Any]]:
    imports: List[Dict[str, Any]] = []
    patterns = [
        r"\bimport\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]",
        r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)",
        r"\bexport\s+.+?\s+from\s+['\"]([^'\"]+)['\"]",
    ]
    for idx, line in enumerate(content.splitlines(), start=1):
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                imports.append({"name": match.group(1), "module": match.group(1), "line": idx, "file": rel_path})
                break
    return imports


def _extract_config_references(content: str, language: str, rel_path: str) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    if language == "json":
        try:
            payload = json.loads(content)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            for key in ("scripts", "dependencies", "devDependencies"):
                value = payload.get(key)
                if isinstance(value, dict):
                    for name in list(value)[:80]:
                        refs.append({"name": str(name), "module": str(name), "line": 1, "file": rel_path, "config_key": key})
    return refs
