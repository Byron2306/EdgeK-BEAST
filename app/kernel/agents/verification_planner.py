"""Deterministic verifier planning for bounded agent runs."""

from __future__ import annotations

import posixpath
from typing import Any


MUTATION_TOOLS = {"worktree.replace_exact", "worktree.write_file"}


def _request_payload(run: dict[str, Any]) -> dict[str, Any]:
    return run.get("request") if isinstance(run.get("request"), dict) else {}


def changed_paths_from_observations(run: dict[str, Any]) -> list[str]:
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
    observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
    changed: list[str] = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") != "completed":
            continue
        if str(item.get("tool_id") or "") not in MUTATION_TOOLS:
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        path = str(result.get("path") or "").strip().replace("\\", "/")
        if path and path not in changed:
            changed.append(path)
    return changed


def execution_target_descriptor(run: dict[str, Any]) -> dict[str, str]:
    request = _request_payload(run)
    payload = request.get("execution_target_payload") if isinstance(request.get("execution_target_payload"), dict) else {}
    nested_target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    kind = str(
        payload.get("kind")
        or payload.get("target_kind")
        or nested_target.get("kind")
        or request.get("execution_target")
        or "local"
    ).strip().lower() or "local"
    label = str(
        payload.get("label")
        or payload.get("sessionId")
        or payload.get("host")
        or nested_target.get("host")
        or kind
    ).strip()
    base = str(
        payload.get("remoteRoot")
        or payload.get("remote_root")
        or payload.get("workspaceFolder")
        or payload.get("workspace_folder")
        or payload.get("path")
        or nested_target.get("remoteRoot")
        or nested_target.get("workspaceFolder")
        or ""
    ).strip()
    container_id = str(
        payload.get("containerId")
        or payload.get("container_id")
        or payload.get("id")
        or payload.get("name")
        or nested_target.get("containerId")
        or nested_target.get("name")
        or ""
    ).strip()
    return {
        "kind": kind,
        "label": label,
        "session_id": str(payload.get("sessionId") or "").strip(),
        "host": str(payload.get("host") or nested_target.get("host") or "").strip(),
        "base": base,
        "container_id": container_id,
        "target_execution": f"remote_{kind}" if kind in {"ssh", "container", "devcontainer"} else "local_snapshot",
    }


def _target_runner_for(run: dict[str, Any], family: str) -> list[str]:
    kind = str(execution_target_descriptor(run).get("kind") or "local")
    if family == "python":
        return ["python3", "-m"] if kind in {"ssh", "container", "devcontainer"} else ["python", "-m"]
    if family == "javascript":
        return ["node", "--check"]
    if family == "typescript":
        return ["npx", "tsc", "--noEmit"]
    if family == "playwright":
        return ["npx", "playwright", "test"]
    if family == "cypress":
        return ["npx", "cypress", "run"]
    if family == "go":
        return ["go", "test"]
    if family == "rust":
        return ["cargo", "test"]
    if family == "java_maven":
        return ["mvn", "test"]
    if family == "java_gradle":
        return ["./gradlew", "test"]
    if family == "dotnet":
        return ["dotnet", "test"]
    return []


def _verification_strategy(run: dict[str, Any], family: str, scope: str, reason: str) -> dict[str, Any]:
    target = execution_target_descriptor(run)
    kind = str(target.get("kind") or "local")
    if kind in {"ssh", "container", "devcontainer"}:
        mode = "target_native_remote"
        summary = f"Run {family} verification on the selected {kind} target so repair evidence matches the real execution environment."
    else:
        mode = "target_native_local"
        summary = f"Run {family} verification in the local bound worktree for the latest mutation epoch."
    return {
        "mode": mode,
        "family": family,
        "scope": scope,
        "reason": reason,
        "execution_target": target,
        "summary": summary,
    }


def _catalog_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if isinstance(value.get("tests"), list):
            return [item for item in value["tests"] if isinstance(item, dict)]
        if isinstance(value.get("items"), list):
            return [item for item in value["items"] if isinstance(item, dict)]
    return []


def request_test_catalog(run: dict[str, Any]) -> list[dict[str, Any]]:
    request = _request_payload(run)
    catalog: list[dict[str, Any]] = []
    for key in ("test_catalog", "workspace_tests", "tests"):
        catalog.extend(_catalog_items(request.get(key)))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in catalog:
        identity = str(item.get("id") or item.get("command") or item.get("framework") or "").strip()
        if identity and identity not in seen:
            seen.add(identity)
            deduped.append(item)
    return deduped[:80]


def latest_workspace_index(run: dict[str, Any]) -> dict[str, Any]:
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
    observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
    for item in reversed(observations):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") != "completed" or str(item.get("tool_id") or "") != "workspace.index":
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if result.get("beast_object_type") == "beast_workspace_index_snapshot":
            return result
    return {}


def latest_verification_failure(run: dict[str, Any]) -> dict[str, Any]:
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
    failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
    latest = failures[-1] if failures and isinstance(failures[-1], dict) else {}
    return dict(latest) if latest else {}


def _fallback_syntax_plan(run: dict[str, Any], *, changed: list[str], reason: str, catalog_matches: list[str] | None = None) -> dict[str, Any]:
    python_files = [path for path in changed if path.endswith(".py")]
    js_files = [path for path in changed if path.endswith((".js", ".jsx", ".mjs", ".cjs"))]
    ts_files = [path for path in changed if path.endswith((".ts", ".tsx"))]
    if python_files:
        return {
            "command": [*_target_runner_for(run, "python"), "py_compile", *python_files[:12]],
            "reason": reason,
            "scope": "changed_files",
            "catalog_matches": list(catalog_matches or []),
            "strategy": _verification_strategy(run, "python_compile", "changed_files", reason),
        }
    if js_files:
        return {
            "command": [*_target_runner_for(run, "javascript"), *js_files[:12]],
            "reason": reason,
            "scope": "changed_files",
            "catalog_matches": list(catalog_matches or []),
            "strategy": _verification_strategy(run, "javascript_syntax", "changed_files", reason),
        }
    if ts_files:
        return {
            "command": [*_target_runner_for(run, "typescript"), *ts_files[:12]],
            "reason": reason,
            "scope": "changed_files",
            "catalog_matches": list(catalog_matches or []),
            "strategy": _verification_strategy(run, "typescript_check", "changed_files", reason),
        }
    return {
        "command": ["git", "diff", "--check"],
        "reason": reason,
        "scope": "worktree_diff",
        "catalog_matches": list(catalog_matches or []),
        "strategy": _verification_strategy(run, "git_diff_check", "worktree_diff", reason),
    }


def _python_module_aliases(path: str) -> set[str]:
    value = str(path or "").replace("\\", "/").strip()
    if not value.endswith(".py"):
        return set()
    stem = value[:-3]
    parts = [part for part in stem.split("/") if part and part != "__init__"]
    aliases = {".".join(parts)} if parts else set()
    if parts:
        aliases.add(parts[-1])
    if len(parts) > 1 and parts[0] in {"src", "app"}:
        aliases.add(".".join(parts[1:]))
    return {alias for alias in aliases if alias}


def related_pytest_files_from_index(run: dict[str, Any], changed: list[str]) -> list[str]:
    index = latest_workspace_index(run)
    if not index:
        return []
    imports = index.get("imports") if isinstance(index.get("imports"), list) else []
    tests = index.get("tests") if isinstance(index.get("tests"), list) else []
    files = index.get("files") if isinstance(index.get("files"), list) else []
    test_paths = {
        str(item or "").replace("\\", "/")
        for item in tests
        if isinstance(item, str) and _is_pytest_file(str(item))
    }
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/")
        if _is_pytest_file(path):
            test_paths.add(path)
    aliases: set[str] = set()
    for path in changed:
        aliases.update(_python_module_aliases(path))
    if not aliases:
        return []
    related: list[str] = []
    for item in imports:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/")
        target = str(item.get("target") or "").strip()
        if path not in test_paths:
            continue
        if any(target == alias or target.endswith(f".{alias}") or alias.endswith(f".{target}") for alias in aliases):
            if path not in related:
                related.append(path)
    return related[:8]


def _strip_js_extension(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    for suffix in (".test.tsx", ".spec.tsx", ".test.jsx", ".spec.jsx", ".test.ts", ".spec.ts", ".test.js", ".spec.js", ".tsx", ".jsx", ".mts", ".cts", ".mjs", ".cjs", ".ts", ".js"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _js_module_aliases(path: str) -> set[str]:
    value = str(path or "").replace("\\", "/").strip()
    if not value.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")):
        return set()
    stem = _strip_js_extension(value)
    aliases = {stem, f"/{stem}", stem.rsplit("/", 1)[-1]}
    if stem.endswith("/index"):
        aliases.add(stem[: -len("/index")])
    if "/" in stem and stem.split("/", 1)[0] in {"src", "app", "lib"}:
        aliases.add(stem.split("/", 1)[1])
    return {alias for alias in aliases if alias}


def _resolve_js_import(importer_path: str, target: str) -> str:
    raw = str(target or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("."):
        base = posixpath.dirname(str(importer_path or "").replace("\\", "/"))
        return _strip_js_extension(posixpath.normpath(posixpath.join(base, raw))).lstrip("./")
    return _strip_js_extension(raw).lstrip("./")


def _is_js_test_file(path: str) -> bool:
    value = str(path or "").replace("\\", "/")
    name = value.rsplit("/", 1)[-1].lower()
    return value.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")) and (
        "/tests/" in f"/{value.lower()}"
        or "/__tests__/" in f"/{value.lower()}"
        or name.endswith((".test.js", ".spec.js", ".test.jsx", ".spec.jsx", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
    )


def related_js_test_files_from_index(run: dict[str, Any], changed: list[str]) -> list[str]:
    index = latest_workspace_index(run)
    if not index:
        return []
    imports = index.get("imports") if isinstance(index.get("imports"), list) else []
    tests = index.get("tests") if isinstance(index.get("tests"), list) else []
    files = index.get("files") if isinstance(index.get("files"), list) else []
    test_paths = {
        str(item or "").replace("\\", "/")
        for item in tests
        if isinstance(item, str) and _is_js_test_file(str(item))
    }
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/")
        if _is_js_test_file(path):
            test_paths.add(path)
    aliases: set[str] = set()
    for path in changed:
        aliases.update(_js_module_aliases(path))
    if not aliases:
        return []
    related: list[str] = []
    for item in imports:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/")
        if path not in test_paths:
            continue
        resolved = _resolve_js_import(path, str(item.get("target") or ""))
        if any(resolved == alias or resolved.endswith(f"/{alias}") or alias.endswith(f"/{resolved}") for alias in aliases):
            if path not in related:
                related.append(path)
    return related[:8]


def _catalog_has_pytest(catalog: list[dict[str, Any]]) -> bool:
    for item in catalog:
        value = " ".join(str(item.get(key) or "") for key in ("id", "framework", "command", "label")).lower()
        if "pytest" in value or value == "python:pytest":
            return True
    return False


def _catalog_has(catalog: list[dict[str, Any]], *needles: str) -> bool:
    wanted = [needle.lower() for needle in needles if needle]
    for item in catalog:
        value = " ".join(str(item.get(key) or "") for key in ("id", "framework", "command", "label", "kind")).lower()
        if any(needle in value for needle in wanted):
            return True
    return False


def _index_paths(run: dict[str, Any]) -> list[str]:
    index = latest_workspace_index(run)
    paths: list[str] = []
    tests = index.get("tests") if isinstance(index.get("tests"), list) else []
    files = index.get("files") if isinstance(index.get("files"), list) else []
    for item in tests:
        if isinstance(item, str):
            path = item.replace("\\", "/")
            if path not in paths:
                paths.append(path)
    for item in files:
        if isinstance(item, dict):
            path = str(item.get("path") or "").replace("\\", "/")
            if path and path not in paths:
                paths.append(path)
    return paths


def _nearest_package_root(path: str, markers: set[str], all_paths: list[str]) -> str:
    value = str(path or "").replace("\\", "/").strip()
    parts = value.split("/")[:-1]
    def matches_marker(filename: str) -> bool:
        return filename in markers or any(marker.startswith("*") and filename.endswith(marker[1:]) for marker in markers)
    marker_dirs = {
        candidate.rsplit("/", 1)[0] if "/" in candidate else ""
        for candidate in all_paths
        if matches_marker(candidate.rsplit("/", 1)[-1])
    }
    for index in range(len(parts), -1, -1):
        directory = "/".join(parts[:index])
        if directory in marker_dirs:
            return directory
    return parts[0] if parts else ""


def _same_root_related_tests(changed: list[str], all_paths: list[str], *, suffixes: tuple[str, ...], markers: set[str], test_predicate) -> list[str]:
    roots = {_nearest_package_root(path, markers, all_paths) for path in changed if path.endswith(suffixes)}
    roots = {root for root in roots if root or len(changed) == 1}
    related: list[str] = []
    for path in all_paths:
        if not test_predicate(path):
            continue
        root = _nearest_package_root(path, markers, all_paths)
        if root in roots or any(path.startswith(f"{candidate}/") for candidate in roots if candidate):
            related.append(path)
    return related[:8]


def _is_go_test_file(path: str) -> bool:
    return str(path or "").replace("\\", "/").endswith("_test.go")


def _is_rust_test_file(path: str) -> bool:
    value = str(path or "").replace("\\", "/")
    return value.endswith(".rs") and ("/tests/" in f"/{value}" or value.endswith("_test.rs"))


def _is_java_test_file(path: str) -> bool:
    value = str(path or "").replace("\\", "/")
    name = value.rsplit("/", 1)[-1]
    return value.endswith(".java") and ("/src/test/" in f"/{value}" or name.endswith("Test.java") or name.endswith("Tests.java"))


def _is_dotnet_test_file(path: str) -> bool:
    value = str(path or "").replace("\\", "/")
    name = value.rsplit("/", 1)[-1].lower()
    return value.endswith((".cs", ".fs", ".vb")) and ("/tests/" in f"/{value.lower()}" or name.endswith("tests.cs") or name.endswith("test.cs"))


def _is_e2e_spec(path: str) -> bool:
    value = str(path or "").replace("\\", "/").lower()
    name = value.rsplit("/", 1)[-1]
    return name.endswith((".spec.ts", ".spec.js", ".cy.ts", ".cy.js")) and (
        "/e2e/" in f"/{value}" or "/playwright/" in f"/{value}" or "/cypress/" in f"/{value}" or "/tests/" in f"/{value}"
    )


def _js_test_runner(catalog: list[dict[str, Any]]) -> tuple[list[str], str] | tuple[None, str]:
    for item in catalog:
        value = " ".join(str(item.get(key) or "") for key in ("id", "framework", "command", "label")).lower()
        if "vitest" in value:
            return ["npx", "vitest", "run"], "javascript:vitest"
        if "jest" in value:
            return ["npx", "jest", "--runTestsByPath"], "javascript:jest"
    for item in catalog:
        value = " ".join(str(item.get(key) or "") for key in ("id", "framework", "command", "label")).lower()
        if "npm" in value and "test" in value:
            return ["npm", "test", "--"], "javascript:npm-test"
    return None, ""


def _is_pytest_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        path.endswith(".py")
        and (
            "/tests/" in f"/{path}"
            or name.startswith("test_")
            or name.endswith("_test.py")
        )
    )


def plan_verification(run: dict[str, Any]) -> dict[str, Any]:
    changed = changed_paths_from_observations(run)
    target = execution_target_descriptor(run)
    catalog = request_test_catalog(run)
    plan: dict[str, Any] = {
        "command": None,
        "reason": "no_completed_mutation",
        "scope": "none",
        "changed_paths": changed[:20],
        "execution_target": target,
        "target_execution": target.get("target_execution"),
        "catalog_matches": [],
        "strategy": _verification_strategy(run, "none", "none", "no_completed_mutation"),
    }
    if not changed:
        return plan
    latest_failure = latest_verification_failure(run)
    latest_analysis = latest_failure.get("analysis") if isinstance(latest_failure.get("analysis"), dict) else {}
    latest_command = latest_failure.get("command") if isinstance(latest_failure.get("command"), list) else []
    latest_reason = str(latest_analysis.get("failure_class") or "").strip()
    if latest_command and bool(latest_analysis.get("retryable_without_code_change")) and int(latest_failure.get("repair_cycle") or 0) <= 1:
        plan.update({
            "command": list(latest_command),
            "reason": "retry_same_target_verifier_once",
            "scope": "retry_same_scope",
            "catalog_matches": ["retryable_failure"],
            "strategy": {
                **_verification_strategy(run, "retry_same_command", "retry_same_scope", "retry_same_target_verifier_once"),
                "prior_failure_class": latest_reason,
                "retryable_without_code_change": True,
            },
            "prior_failure": {
                "failure_class": latest_reason,
                "target_execution": str(latest_failure.get("target_execution") or ""),
                "repair_cycle": int(latest_failure.get("repair_cycle") or 0),
            },
        })
        return plan

    python_files = [path for path in changed if path.endswith(".py")]
    js_files = [path for path in changed if path.endswith((".js", ".jsx", ".mjs", ".cjs"))]
    ts_files = [path for path in changed if path.endswith((".ts", ".tsx"))]
    go_files = [path for path in changed if path.endswith(".go")]
    rust_files = [path for path in changed if path.endswith(".rs")]
    java_files = [path for path in changed if path.endswith(".java")]
    dotnet_files = [path for path in changed if path.endswith((".cs", ".fs", ".vb"))]
    all_paths = _index_paths(run)
    degraded_fallback = bool(latest_command) and latest_reason in {"environment_issue", "flaky_test"} and int(latest_failure.get("repair_cycle") or 0) > 1
    if degraded_fallback:
        plan.update({
            **_fallback_syntax_plan(run, changed=changed, reason="degraded_target_fallback_after_retryable_verifier_failure", catalog_matches=["retryable_failure"]),
            "prior_failure": {
                "failure_class": latest_reason,
                "target_execution": str(latest_failure.get("target_execution") or ""),
                "repair_cycle": int(latest_failure.get("repair_cycle") or 0),
            },
        })
        return plan
    if python_files and _catalog_has_pytest(catalog):
        related_pytest = related_pytest_files_from_index(run, python_files)
        if related_pytest:
            plan.update({
                "command": [*_target_runner_for(run, "python"), "pytest", "-q", *related_pytest],
                "reason": "related_pytest_from_workspace_index",
                "scope": "related_tests",
                "catalog_matches": ["python:pytest"],
                "related_tests": related_pytest,
                "strategy": _verification_strategy(run, "python_pytest", "related_tests", "related_pytest_from_workspace_index"),
            })
            return plan
        pytest_files = [path for path in python_files if _is_pytest_file(path)]
        if pytest_files:
            plan.update({
                "command": [*_target_runner_for(run, "python"), "pytest", "-q", *pytest_files[:8]],
                "reason": "focused_pytest_for_changed_test_files",
                "scope": "focused_tests",
                "catalog_matches": ["python:pytest"],
                "strategy": _verification_strategy(run, "python_pytest", "focused_tests", "focused_pytest_for_changed_test_files"),
            })
            return plan
    js_family_files = [*js_files, *ts_files]
    if js_family_files and _catalog_has(catalog, "playwright"):
        e2e_specs = [path for path in js_family_files if _is_e2e_spec(path)]
        if not e2e_specs:
            e2e_specs = _same_root_related_tests(js_family_files, all_paths, suffixes=(".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"), markers={"package.json", "playwright.config.ts", "playwright.config.js"}, test_predicate=_is_e2e_spec)
        if e2e_specs:
            plan.update({
                "command": [*_target_runner_for(run, "playwright"), *e2e_specs[:8]],
                "reason": "focused_playwright_specs_from_workspace_index",
                "scope": "focused_e2e",
                "catalog_matches": ["javascript:playwright"],
                "related_tests": e2e_specs[:8],
                "strategy": _verification_strategy(run, "playwright", "focused_e2e", "focused_playwright_specs_from_workspace_index"),
            })
            return plan
    if js_family_files and _catalog_has(catalog, "cypress"):
        cypress_specs = [path for path in js_family_files if _is_e2e_spec(path) and ".cy." in path.lower()]
        if not cypress_specs:
            cypress_specs = [path for path in _same_root_related_tests(js_family_files, all_paths, suffixes=(".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"), markers={"package.json", "cypress.config.ts", "cypress.config.js"}, test_predicate=_is_e2e_spec) if ".cy." in path.lower()]
        if cypress_specs:
            plan.update({
                "command": [*_target_runner_for(run, "cypress"), "--spec", ",".join(cypress_specs[:8])],
                "reason": "focused_cypress_specs_from_workspace_index",
                "scope": "focused_e2e",
                "catalog_matches": ["javascript:cypress"],
                "related_tests": cypress_specs[:8],
                "strategy": _verification_strategy(run, "cypress", "focused_e2e", "focused_cypress_specs_from_workspace_index"),
            })
            return plan
    js_runner, js_catalog_match = _js_test_runner(catalog)
    if js_family_files and js_runner:
        related_js_tests = related_js_test_files_from_index(run, js_family_files)
        if related_js_tests:
            plan.update({
                "command": [*js_runner, *related_js_tests],
                "reason": "related_javascript_tests_from_workspace_index",
                "scope": "related_tests",
                "catalog_matches": [js_catalog_match],
                "related_tests": related_js_tests,
                "strategy": _verification_strategy(run, "javascript_tests", "related_tests", "related_javascript_tests_from_workspace_index"),
            })
            return plan
        changed_js_tests = [path for path in js_family_files if _is_js_test_file(path)]
        if changed_js_tests:
            plan.update({
                "command": [*js_runner, *changed_js_tests[:8]],
                "reason": "focused_javascript_tests_for_changed_test_files",
                "scope": "focused_tests",
                "catalog_matches": [js_catalog_match],
                "strategy": _verification_strategy(run, "javascript_tests", "focused_tests", "focused_javascript_tests_for_changed_test_files"),
            })
            return plan
    if go_files:
        changed_go_tests = [path for path in go_files if _is_go_test_file(path)]
        packages = sorted({
            f"./{path.rsplit('/', 1)[0]}" if "/" in path else "."
            for path in (changed_go_tests or go_files)
        })[:8]
        plan.update({
            "command": [*_target_runner_for(run, "go"), *packages],
            "reason": "go_test_for_changed_packages" if not changed_go_tests else "focused_go_test_for_changed_test_packages",
            "scope": "changed_packages",
            "catalog_matches": ["go:test"],
            "related_tests": changed_go_tests[:8],
            "strategy": _verification_strategy(run, "go_test", "changed_packages", "go_test_for_changed_packages" if not changed_go_tests else "focused_go_test_for_changed_test_packages"),
        })
        return plan
    if rust_files and (_catalog_has(catalog, "cargo", "rust") or any(path.endswith("Cargo.toml") for path in all_paths)):
        related_rust_tests = _same_root_related_tests(rust_files, all_paths, suffixes=(".rs",), markers={"Cargo.toml"}, test_predicate=_is_rust_test_file)
        command = [*_target_runner_for(run, "rust")]
        plan.update({
            "command": command,
            "reason": "cargo_test_for_changed_crate",
            "scope": "changed_crate",
            "catalog_matches": ["rust:cargo-test"],
            "related_tests": related_rust_tests,
            "strategy": _verification_strategy(run, "cargo_test", "changed_crate", "cargo_test_for_changed_crate"),
        })
        return plan
    if java_files and (_catalog_has(catalog, "maven", "mvn") or any(path.endswith("pom.xml") for path in all_paths)):
        related_java_tests = _same_root_related_tests(java_files, all_paths, suffixes=(".java",), markers={"pom.xml"}, test_predicate=_is_java_test_file)
        test_names = [path.rsplit("/", 1)[-1].removesuffix(".java") for path in related_java_tests[:8]]
        command = [*_target_runner_for(run, "java_maven"), f"-Dtest={','.join(test_names)}"] if test_names else [*_target_runner_for(run, "java_maven")]
        plan.update({
            "command": command,
            "reason": "maven_related_tests_from_workspace_index" if test_names else "maven_test_for_changed_module",
            "scope": "related_tests" if test_names else "changed_module",
            "catalog_matches": ["java:maven-test"],
            "related_tests": related_java_tests,
            "strategy": _verification_strategy(run, "maven_test", "related_tests" if test_names else "changed_module", "maven_related_tests_from_workspace_index" if test_names else "maven_test_for_changed_module"),
        })
        return plan
    if java_files and (_catalog_has(catalog, "gradle") or any(path.endswith(("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")) for path in all_paths)):
        related_java_tests = _same_root_related_tests(java_files, all_paths, suffixes=(".java",), markers={"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}, test_predicate=_is_java_test_file)
        plan.update({
            "command": [*_target_runner_for(run, "java_gradle")],
            "reason": "gradle_test_for_changed_module",
            "scope": "changed_module",
            "catalog_matches": ["java:gradle-test"],
            "related_tests": related_java_tests,
            "strategy": _verification_strategy(run, "gradle_test", "changed_module", "gradle_test_for_changed_module"),
        })
        return plan
    if dotnet_files and (_catalog_has(catalog, "dotnet") or any(path.endswith((".csproj", ".sln")) for path in all_paths)):
        related_dotnet_tests = _same_root_related_tests(dotnet_files, all_paths, suffixes=(".cs", ".fs", ".vb"), markers={"*.sln", ".csproj", ".fsproj", ".vbproj"}, test_predicate=_is_dotnet_test_file)
        plan.update({
            "command": [*_target_runner_for(run, "dotnet"), "--no-restore"],
            "reason": "dotnet_test_for_changed_project",
            "scope": "changed_project",
            "catalog_matches": ["dotnet:test"],
            "related_tests": related_dotnet_tests,
            "strategy": _verification_strategy(run, "dotnet_test", "changed_project", "dotnet_test_for_changed_project"),
        })
        return plan
    if python_files:
        plan.update({
            "command": [*_target_runner_for(run, "python"), "py_compile", *python_files[:12]],
            "reason": "python_compile_for_changed_sources",
            "scope": "changed_files",
            "strategy": _verification_strategy(run, "python_compile", "changed_files", "python_compile_for_changed_sources"),
        })
        return plan
    if js_files:
        plan.update({
            "command": [*_target_runner_for(run, "javascript"), *js_files[:12]],
            "reason": "node_syntax_check_for_changed_sources",
            "scope": "changed_files",
            "strategy": _verification_strategy(run, "javascript_syntax", "changed_files", "node_syntax_check_for_changed_sources"),
        })
        return plan
    if ts_files:
        plan.update({
            "command": [*_target_runner_for(run, "typescript"), *ts_files[:12]],
            "reason": "typescript_check_for_changed_sources",
            "scope": "changed_files",
            "strategy": _verification_strategy(run, "typescript_check", "changed_files", "typescript_check_for_changed_sources"),
        })
        return plan
    plan.update({
        "command": ["git", "diff", "--check"],
        "reason": "generic_diff_whitespace_check",
        "scope": "worktree_diff",
        "strategy": _verification_strategy(run, "git_diff_check", "worktree_diff", "generic_diff_whitespace_check"),
    })
    return plan
