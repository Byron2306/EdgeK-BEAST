from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.ide import build_ide_router


EXPECTED_ROUTE_CONTRACT = [
    ("GET", "/edgek/ide/snapshot", "edgek_ide_snapshot"),
    ("GET", "/edgek/ide/events", "edgek_ide_events"),
    ("GET", "/edgek/ide/related-context", "edgek_ide_related_context"),
    ("GET", "/edgek/ide/symbol-outline", "edgek_ide_symbol_outline"),
    ("GET", "/edgek/ide/symbol-search", "edgek_ide_symbol_search"),
    ("GET", "/edgek/ide/text-search", "edgek_ide_text_search"),
    ("GET", "/edgek/ide/code-intel", "edgek_ide_code_intel"),
    ("GET", "/edgek/ide/mission-timeline", "edgek_ide_mission_timeline"),
    ("POST", "/edgek/ide/sourceplan/lifecycle", "edgek_ide_sourceplan_lifecycle"),
    ("GET", "/edgek/ide/receipts/chooser", "edgek_ide_receipts_chooser"),
    ("POST", "/edgek/ide/mission-runbook/export", "edgek_ide_mission_runbook_export"),
    ("POST", "/edgek/ide/mission-runbook/verify", "edgek_ide_mission_runbook_verify"),
    ("GET", "/edgek/ide/mission-route", "edgek_ide_mission_route"),
    ("POST", "/edgek/ide/sourceplan/handoff-package", "edgek_ide_sourceplan_handoff_package"),
    ("POST", "/edgek/ide/release-readiness/check", "edgek_ide_release_readiness_check"),
    ("GET", "/edgek/ide/tooling-snapshot", "edgek_ide_tooling_snapshot"),
    ("GET", "/edgek/ide/system-snapshot", "edgek_ide_system_snapshot"),
    ("GET", "/edgek/ide/ports", "edgek_ide_ports"),
    ("GET", "/edgek/ide/processes", "edgek_ide_processes"),
    ("GET", "/edgek/ide/process/{pid}", "edgek_ide_process_detail"),
    ("GET", "/edgek/ide/environment", "edgek_ide_environment"),
    ("GET", "/edgek/ide/packages", "edgek_ide_packages"),
    ("GET", "/edgek/ide/extensions", "edgek_ide_extensions"),
    ("GET", "/edgek/ide/catalog", "edgek_ide_catalog"),
    ("POST", "/edgek/ide/system/kill", "edgek_ide_system_kill"),
    ("POST", "/edgek/ide/ports/free", "edgek_ide_ports_free"),
    ("GET", "/edgek/ide/terminal/stream", "edgek_ide_terminal_stream"),
    ("POST", "/edgek/ide/learning-queue/propose", "edgek_ide_learning_queue_propose"),
    ("GET", "/edgek/ide/actions/manifest", "edgek_ide_actions_manifest"),
    ("POST", "/edgek/ide/actions/plan", "edgek_ide_action_plan"),
    ("GET", "/edgek/ide/agent-sessions", "edgek_ide_agent_sessions"),
    ("GET", "/edgek/ide/conductor/dispatches", "edgek_ide_conductor_dispatches"),
    ("GET", "/edgek/ide/agent-sessions/{session_id}", "edgek_ide_agent_session_detail"),
    ("POST", "/edgek/ide/agent-sessions/create", "edgek_ide_agent_session_create"),
    ("POST", "/edgek/ide/agent-sessions/update", "edgek_ide_agent_session_update"),
    ("POST", "/edgek/ide/agent-sessions/capabilities/grant", "edgek_ide_agent_session_capabilities_grant"),
    ("POST", "/edgek/ide/agent-sessions/pause", "edgek_ide_agent_session_pause"),
    ("POST", "/edgek/ide/agent-sessions/resume", "edgek_ide_agent_session_resume"),
    ("POST", "/edgek/ide/agent-sessions/cancel", "edgek_ide_agent_session_cancel"),
    ("POST", "/edgek/ide/agent-sessions/sourceplan-draft", "edgek_ide_agent_session_sourceplan_draft"),
    ("POST", "/edgek/ide/agent-sessions/action-ir-sourceplan", "edgek_ide_agent_session_action_ir_sourceplan"),
    ("POST", "/edgek/ide/agent-sessions/verify-sourceplan", "edgek_ide_agent_session_verify_sourceplan"),
    ("GET", "/edgek/ide/agent-sessions/{session_id}/run-events", "edgek_ide_agent_session_run_events"),
    ("POST", "/edgek/ide/sourceplan/from-editor", "edgek_ide_sourceplan_from_editor"),
    ("POST", "/edgek/ide/sourceplan/from-selection", "edgek_ide_sourceplan_from_selection"),
    ("POST", "/edgek/ide/worktree-mission/create", "edgek_ide_worktree_mission_create"),
    ("GET", "/edgek/ide/worktree-mission/list", "edgek_ide_worktree_mission_list"),
    ("POST", "/edgek/ide/worktree-mission/test", "edgek_ide_worktree_mission_test"),
    ("POST", "/edgek/ide/worktree-mission/diff", "edgek_ide_worktree_mission_diff"),
    ("POST", "/edgek/ide/worktree-mission/promote", "edgek_ide_worktree_mission_promote"),
    ("POST", "/edgek/ide/worktree-mission/sourceplan-draft", "edgek_ide_worktree_mission_sourceplan_draft"),
    ("POST", "/edgek/ide/worktree-mission/close", "edgek_ide_worktree_mission_close"),
]


class DummyCodeCortex:
    def build_snapshot(self, *_args, **_kwargs):
        return {"status": "dummy"}

    def related_context(self, *_args, **_kwargs):
        return []

    def context_for(self, *_args, **_kwargs):
        return []


def _contract(router):
    rows = []
    for route in router.routes:
        methods = sorted(route.methods or [])
        assert len(methods) == 1
        rows.append((methods[0], route.path, route.name))
    return rows


def test_ide_router_is_a_small_composition_root():
    source = Path("app/routes/ide.py").read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 60
    assert "IdeRouteContext" in source
    assert "register_agent_sessions_routes" in source
    assert "@router." not in source


def test_ide_route_families_exist_and_are_bounded():
    expected = {
        "overview.py",
        "mission.py",
        "system.py",
        "learning.py",
        "actions.py",
        "agent_sessions.py",
        "agent_run_stream.py",
        "editor_sourceplans.py",
        "worktrees.py",
    }
    directory = Path("app/routes/ide_routes")
    assert expected.issubset({path.name for path in directory.glob("*.py")})
    assert Path("app/routes/ide_context.py").exists()
    assert len(Path("app/routes/ide_context.py").read_text(encoding="utf-8").splitlines()) < 900


def test_ide_route_contract_is_unchanged():
    router = build_ide_router(".", code_cortex_router=DummyCodeCortex())
    assert _contract(router) == EXPECTED_ROUTE_CONTRACT


def test_decomposed_routes_match_original_live_read_responses():
    original_path = Path("/mnt/data/beast_phase1d_renderer/app/routes/ide.py")
    if not original_path.exists():
        return
    spec = importlib.util.spec_from_file_location("beast_original_ide_routes", original_path)
    assert spec and spec.loader
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)

    def make_client(builder, root: Path) -> TestClient:
        app = FastAPI()
        app.include_router(builder(root, code_cortex_router=DummyCodeCortex()))
        return TestClient(app)

    with TemporaryDirectory() as old_dir, TemporaryDirectory() as new_dir:
        Path(old_dir, "sample.py").write_text('def hello(name):\n    return f"hello {name}"\n', encoding="utf-8")
        Path(new_dir, "sample.py").write_text('def hello(name):\n    return f"hello {name}"\n', encoding="utf-8")
        old_client = make_client(original.build_ide_router, Path(old_dir))
        new_client = make_client(build_ide_router, Path(new_dir))
        calls = [
            ("/edgek/ide/symbol-outline", {"path": "sample.py"}),
            ("/edgek/ide/symbol-search", {"query": "hello"}),
            ("/edgek/ide/text-search", {"query": "hello"}),
            ("/edgek/ide/mission-route", {}),
            ("/edgek/ide/actions/manifest", {}),
            ("/edgek/ide/agent-sessions", {}),
            ("/edgek/ide/worktree-mission/list", {}),
        ]

        def normalize(value):
            if isinstance(value, dict):
                return {
                    key: normalize(item)
                    for key, item in value.items()
                    if key not in {"workspace_root", "requested_workspace_root", "timestamp", "generated_at", "created_at", "updated_at"}
                }
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        for path, params in calls:
            old_response = old_client.get(path, params=params)
            new_response = new_client.get(path, params=params)
            assert new_response.status_code == old_response.status_code
            assert normalize(new_response.json()) == normalize(old_response.json())
