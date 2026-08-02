"""Deterministic, explainable task and environment fingerprints.

Fingerprints are identity aids, not reuse authority. Every digest binds a canonical
component manifest so drift can be explained without embeddings or heuristics.
"""
from __future__ import annotations

import ast
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from app.kernel.evidence.evidence_digest import sha256_bytes, sha256_digest

_LOCKFILES = (
    "uv.lock", "poetry.lock", "Pipfile.lock", "requirements.txt", "requirements-dev.txt",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "Cargo.lock", "go.sum",
)
_MANIFESTS = ("pyproject.toml", "package.json", "Cargo.toml", "go.mod")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]*")


def _normal_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _safe_relative(root: Path, value: str) -> Path | None:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _file_digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _operation_paths(sourceplan: dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    for operation in sourceplan.get("operations") or []:
        if not isinstance(operation, dict):
            continue
        for key in ("path", "file", "target", "destination"):
            value = operation.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value.strip().replace("\\", "/"))
    return sorted(paths)


def _symbols_from_python(path: Path) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    symbols: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            symbols.append({"name": node.name, "kind": kind, "line": int(node.lineno)})
    return sorted(symbols, key=lambda item: (item["name"], item["kind"], item["line"]))


def _symbols_from_text(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    patterns = [
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M)),
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", re.M)),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", re.M)),
    ]
    found: set[tuple[str, str]] = set()
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            found.add((match.group(1), kind))
    return [{"name": name, "kind": kind} for name, kind in sorted(found)]


def _symbol_manifest(root: Path, paths: Iterable[str]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for relative in sorted(set(paths))[:200]:
        path = _safe_relative(root, relative)
        if not path or not path.is_file() or path.stat().st_size > 2_000_000:
            files.append({"path": relative, "present": False, "symbols": []})
            continue
        symbols = _symbols_from_python(path) if path.suffix == ".py" else _symbols_from_text(path)
        files.append({"path": relative, "present": True, "digest": _file_digest(path), "symbols": symbols})
    manifest = {"files": files}
    return {**manifest, "digest": sha256_digest(manifest)}


def build_task_fingerprint(run: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
    sourceplan = dict(checkpoint.get("sourceplan") or {})
    planner = dict(checkpoint.get("planner") or {})
    objective = _normal_text(run.get("objective"))
    operations: list[dict[str, Any]] = []
    for item in sourceplan.get("operations") or []:
        if not isinstance(item, dict):
            continue
        operations.append({
            "kind": _normal_text(item.get("kind") or item.get("operation") or item.get("type")),
            "path": str(item.get("path") or item.get("file") or item.get("target") or "").replace("\\", "/"),
        })
    operations.sort(key=lambda item: (item["path"], item["kind"]))
    error_terms = sorted({token.lower() for token in _WORD.findall(" ".join([
        str(planner.get("blocker") or ""), str(planner.get("final_summary") or ""), objective
    ])) if token.lower().endswith(("error", "exception", "failure"))})
    components = {
        "objective": objective,
        "mode": _normal_text(run.get("mode")),
        "operation_manifest": operations,
        "affected_paths": _operation_paths(sourceplan),
        "error_terms": error_terms,
    }
    return {"algorithm": "beast.task.v1", "digest": sha256_digest(components), "components": components}


def build_environment_fingerprint(root_path: str | Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    root = Path(root_path).expanduser().resolve()
    dependencies: list[dict[str, Any]] = []
    for name in sorted(set((*_LOCKFILES, *_MANIFESTS))):
        path = root / name
        if path.is_file():
            dependencies.append({"path": name, "digest": _file_digest(path), "bytes": path.stat().st_size})
    sourceplan = dict(checkpoint.get("sourceplan") or {})
    symbols = _symbol_manifest(root, _operation_paths(sourceplan))
    components = {
        "git": {
            "head": _git(root, "rev-parse", "HEAD") or str(checkpoint.get("worktree_base_commit") or ""),
            "tree": _git(root, "rev-parse", "HEAD^{tree}"),
            "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or str(checkpoint.get("worktree_branch") or ""),
        },
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system().lower(),
            "machine": platform.machine().lower(),
        },
        "dependencies": dependencies,
        "dependency_digest": sha256_digest(dependencies),
        "symbols": symbols,
        "policy_profile": str(checkpoint.get("policy_profile") or "default"),
    }
    return {"algorithm": "beast.environment.v1", "digest": sha256_digest(components), "components": components}


def build_fingerprint_bundle(root_path: str | Path, run: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
    task = build_task_fingerprint(run, checkpoint)
    environment = build_environment_fingerprint(root_path, checkpoint)
    core = {"version": "3.3", "task": task, "environment": environment}
    return {**core, "bundle_digest": sha256_digest(core)}


def compare_fingerprints(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    task_equal = left.get("task", {}).get("digest") == right.get("task", {}).get("digest")
    env_equal = left.get("environment", {}).get("digest") == right.get("environment", {}).get("digest")
    left_env = left.get("environment", {}).get("components", {})
    right_env = right.get("environment", {}).get("components", {})
    checks = {
        "task": task_equal,
        "environment": env_equal,
        "git_head": left_env.get("git", {}).get("head") == right_env.get("git", {}).get("head"),
        "dependency_digest": left_env.get("dependency_digest") == right_env.get("dependency_digest"),
        "symbol_digest": left_env.get("symbols", {}).get("digest") == right_env.get("symbols", {}).get("digest"),
        "runtime": left_env.get("runtime") == right_env.get("runtime"),
        "policy_profile": left_env.get("policy_profile") == right_env.get("policy_profile"),
    }
    changed = [name for name, ok in checks.items() if not ok]
    if task_equal and env_equal:
        classification = "identical"
    elif task_equal and checks["dependency_digest"] and checks["symbol_digest"] and checks["policy_profile"]:
        classification = "environment_drift"
    elif task_equal:
        classification = "same_task_changed_context"
    else:
        classification = "different_task"
    receipt_core = {"classification": classification, "checks": checks, "changed_components": changed}
    return {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
