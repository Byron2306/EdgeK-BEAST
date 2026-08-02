from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter

from app.routes.ide_support.action_ir import action_ir_retry_prompt, reject_incomplete_function_replacements
from app.routes.ide_support.agent_session_routes import register_agent_session_routes
from app.routes.ide_support.common import (
    bounded_workspace_files,
    extract_json_object,
    is_ignored_workspace_directory,
    pair_programmer_limits,
    safe_relative,
)
from app.routes.ide_support.context import IdeRouteContext
from app.routes.ide_support.events import ide_event
from app.routes.ide_support.system_routes import register_system_inspection_routes
from app.routes.ide_support.worktree_routes import register_worktree_mission_routes


def test_pair_programmer_limits_are_route_specific() -> None:
    assert pair_programmer_limits("ollama", "qwen2.5:3b", 9999, 999999) == (1024, 2400, 3)
    assert pair_programmer_limits("nvidia_nim", "coder", 9999, 999999) == (4096, 12000, 3)
    assert pair_programmer_limits("openai", "coder", 9999, 999999) == (3072, 12000, 4)


def test_extract_json_object_accepts_fenced_object_and_list() -> None:
    assert extract_json_object('before ```json\n{"actions": []}\n``` after') == {"actions": []}
    assert extract_json_object('prefix [{"type": "read"}] suffix') == {"actions": [{"type": "read"}]}
    assert extract_json_object("no packet") == {}


def test_safe_relative_rejects_workspace_escape(tmp_path: Path) -> None:
    assert safe_relative(tmp_path, "src/main.py") == (tmp_path / "src/main.py").resolve()
    assert safe_relative(tmp_path, "../secret") is None
    assert safe_relative(tmp_path, str((tmp_path / "absolute").resolve())) is None


def test_bounded_workspace_files_prunes_generated_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a=1")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.py").write_text("no")
    (tmp_path / "src" / "b.js").write_text("const b=1")
    (tmp_path / ".phase1-backup").mkdir()
    (tmp_path / ".phase1-backup" / "stale.py").write_text("no")
    (tmp_path / ".beast-phase0-backup-old").mkdir()
    (tmp_path / ".beast-phase0-backup-old" / "stale.py").write_text("no")
    result = list(bounded_workspace_files(tmp_path, {".py"}, 10))
    assert result == [tmp_path / "src" / "a.py"]


def test_installer_backup_directories_are_ignored() -> None:
    assert is_ignored_workspace_directory(".phase1-backup")
    assert is_ignored_workspace_directory(".phase1a-backup-20260718")
    assert is_ignored_workspace_directory(".beast-phase0-backup-old")
    assert not is_ignored_workspace_directory("phase1-notes")


def test_ide_event_envelope_is_sse_compatible() -> None:
    event = ide_event("agent_turn", {"ok": True})
    assert event.startswith("event: agent_turn\n")
    assert '"beast_object_type": "beast_ide_event"' in event
    assert '"payload": {"ok": true}' in event
    assert event.endswith("\n\n")


def test_ide_route_context_resolves_default_and_override_roots(tmp_path: Path) -> None:
    default_root = tmp_path / "default"
    override_root = tmp_path / "override"
    default_root.mkdir()
    override_root.mkdir()
    context = IdeRouteContext(default_root)
    assert context.fallback_root == default_root.resolve()
    assert context.root() == default_root.resolve()
    assert context.root(override_root) == override_root.resolve()


def test_action_ir_retry_prompt_includes_anchors_and_rules(tmp_path: Path) -> None:
    def fake_references(root: Path, files: list[str]) -> list[SimpleNamespace]:
        assert root == tmp_path
        assert files == ["app.py"]
        return [SimpleNamespace(path="app.py", anchors={"A1": "def run():\n    return 1"})]

    prompt = action_ir_retry_prompt(
        "Fix run",
        "previous prose",
        ["app.py"],
        action_ir_kind="beast.action_ir.v1",
        diagnostics="bad anchor",
        root=tmp_path,
        build_file_references=fake_references,
    )
    assert "Return BEAST Action IR JSON only" in prompt
    assert "beast.action_ir.v1" in prompt
    assert "[A1] def run():" in prompt
    assert "bad anchor" in prompt


def test_incomplete_function_replacement_is_rejected() -> None:
    error = reject_incomplete_function_replacements(
        [{"id": "a1", "old": "def run():", "new": "def run():\n    return 2"}]
    )
    assert "complete anchored function" in error
    assert reject_incomplete_function_replacements([{"old": "return 1", "new": "return 2"}]) == ""


def test_route_registrars_preserve_system_and_worktree_paths(tmp_path: Path) -> None:
    router = APIRouter()
    resolve = lambda value=None: Path(value or tmp_path).resolve()
    register_system_inspection_routes(router, resolve_root=resolve)
    register_worktree_mission_routes(router, resolve_root=resolve)
    paths = {route.path for route in router.routes}
    assert {
        "/edgek/ide/system-snapshot",
        "/edgek/ide/ports",
        "/edgek/ide/processes",
        "/edgek/ide/process/{pid}",
        "/edgek/ide/environment",
        "/edgek/ide/packages",
        "/edgek/ide/extensions",
        "/edgek/ide/catalog",
        "/edgek/ide/worktree-mission/create",
        "/edgek/ide/worktree-mission/list",
        "/edgek/ide/worktree-mission/test",
        "/edgek/ide/worktree-mission/diff",
        "/edgek/ide/worktree-mission/promote",
        "/edgek/ide/worktree-mission/sourceplan-draft",
        "/edgek/ide/worktree-mission/close",
    }.issubset(paths)


def test_agent_session_registrar_preserves_session_paths(tmp_path: Path) -> None:
    router = APIRouter()
    resolve = lambda value=None: Path(value or tmp_path).resolve()
    register_agent_session_routes(
        router,
        resolve_root=resolve,
        compile_action_ir_sourceplan=lambda *args, **kwargs: {"ok": True},
        validate_agent_sourceplan=lambda *args, **kwargs: {"ok": True, "status": "passed"},
        json_hash=lambda payload: "sha256:test",
    )
    paths = {route.path for route in router.routes}
    assert {
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
    }.issubset(paths)
