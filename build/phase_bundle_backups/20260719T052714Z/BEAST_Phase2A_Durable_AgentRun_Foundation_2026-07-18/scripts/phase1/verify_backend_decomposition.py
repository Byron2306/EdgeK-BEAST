#!/usr/bin/env python3
"""Verify the Phase 1E IDE backend decomposition contract."""

from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path
from typing import Any


REQUIRED_MODULES = (
    "overview.py",
    "mission.py",
    "system.py",
    "learning.py",
    "actions.py",
    "agent_sessions.py",
    "agent_run_stream.py",
    "editor_sourceplans.py",
    "worktrees.py",
)

EXPECTED_PATHS = (
    "/edgek/ide/snapshot",
    "/edgek/ide/events",
    "/edgek/ide/related-context",
    "/edgek/ide/symbol-outline",
    "/edgek/ide/symbol-search",
    "/edgek/ide/text-search",
    "/edgek/ide/code-intel",
    "/edgek/ide/mission-timeline",
    "/edgek/ide/sourceplan/lifecycle",
    "/edgek/ide/receipts/chooser",
    "/edgek/ide/mission-runbook/export",
    "/edgek/ide/mission-runbook/verify",
    "/edgek/ide/mission-route",
    "/edgek/ide/sourceplan/handoff-package",
    "/edgek/ide/release-readiness/check",
    "/edgek/ide/tooling-snapshot",
    "/edgek/ide/system-snapshot",
    "/edgek/ide/ports",
    "/edgek/ide/processes",
    "/edgek/ide/process/{pid}",
    "/edgek/ide/environment",
    "/edgek/ide/packages",
    "/edgek/ide/extensions",
    "/edgek/ide/catalog",
    "/edgek/ide/system/kill",
    "/edgek/ide/ports/free",
    "/edgek/ide/terminal/stream",
    "/edgek/ide/learning-queue/propose",
    "/edgek/ide/actions/manifest",
    "/edgek/ide/actions/plan",
    "/edgek/ide/agent-sessions",
    "/edgek/ide/conductor/dispatches",
    "/edgek/ide/agent-sessions/{session_id}",
    "/edgek/ide/agent-sessions/create",
    "/edgek/ide/agent-sessions/update",
    "/edgek/ide/agent-sessions/capabilities/grant",
    "/edgek/ide/agent-sessions/pause",
    "/edgek/ide/agent-sessions/resume",
    "/edgek/ide/agent-sessions/cancel",
    "/edgek/ide/agent-sessions/sourceplan-draft",
    "/edgek/ide/agent-sessions/action-ir-sourceplan",
    "/edgek/ide/agent-sessions/verify-sourceplan",
    "/edgek/ide/agent-sessions/{session_id}/run-events",
    "/edgek/ide/sourceplan/from-editor",
    "/edgek/ide/sourceplan/from-selection",
    "/edgek/ide/worktree-mission/create",
    "/edgek/ide/worktree-mission/list",
    "/edgek/ide/worktree-mission/test",
    "/edgek/ide/worktree-mission/diff",
    "/edgek/ide/worktree-mission/promote",
    "/edgek/ide/worktree-mission/sourceplan-draft",
    "/edgek/ide/worktree-mission/close",
)


class _DummyCodeCortex:
    def build_snapshot(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "dummy"}

    def related_context(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def context_for(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))

    ide_entry = repo / "app/routes/ide.py"
    context = repo / "app/routes/ide_context.py"
    routes_dir = repo / "app/routes/ide_routes"
    checks: dict[str, bool] = {}

    checks["composition_root_exists"] = ide_entry.exists()
    entry_source = ide_entry.read_text(encoding="utf-8") if ide_entry.exists() else ""
    checks["composition_root_bounded"] = len(entry_source.splitlines()) <= 60
    checks["composition_root_has_no_routes"] = "@router." not in entry_source
    checks["explicit_route_context"] = context.exists() and "class IdeRouteContext" in context.read_text(encoding="utf-8")
    checks["route_modules_complete"] = all((routes_dir / name).exists() for name in REQUIRED_MODULES)
    checks["agent_stream_isolated"] = (
        (routes_dir / "agent_run_stream.py").exists()
        and "/edgek/ide/agent-sessions/{session_id}/run-events" in (routes_dir / "agent_run_stream.py").read_text(encoding="utf-8")
        and "run-events" not in (routes_dir / "agent_sessions.py").read_text(encoding="utf-8")
    )

    compile_failures: list[str] = []
    for path in [ide_entry, context, *sorted(routes_dir.glob("*.py"))]:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as error:  # pragma: no cover - surfaced in report
            compile_failures.append(f"{path.relative_to(repo)}: {error}")
    checks["python_compilation"] = not compile_failures

    route_rows: list[dict[str, Any]] = []
    route_error = ""
    try:
        from app.routes.ide import build_ide_router

        router = build_ide_router(repo, code_cortex_router=_DummyCodeCortex())
        for route in router.routes:
            route_rows.append(
                {
                    "path": route.path,
                    "methods": sorted(route.methods or []),
                    "name": route.name,
                }
            )
    except Exception as error:  # pragma: no cover - surfaced in report
        route_error = str(error)

    paths = [row["path"] for row in route_rows]
    checks["route_count_52"] = len(route_rows) == 52
    checks["route_paths_stable"] = tuple(paths) == EXPECTED_PATHS
    checks["route_paths_unique"] = len(paths) == len(set(paths))
    checks["single_method_per_route"] = bool(route_rows) and all(len(row["methods"]) == 1 for row in route_rows)

    module_lines = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in sorted(routes_dir.glob("*.py"))
        if path.name != "__init__.py"
    }
    result = {
        "phase": "1E",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "passed": sum(1 for value in checks.values() if value),
        "total": len(checks),
        "entry_lines": len(entry_source.splitlines()),
        "context_lines": len(context.read_text(encoding="utf-8").splitlines()) if context.exists() else 0,
        "route_count": len(route_rows),
        "route_modules": module_lines,
        "compile_failures": compile_failures,
        "route_error": route_error,
    }
    report_path = repo / "build/PHASE1E_BACKEND_STATUS.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
