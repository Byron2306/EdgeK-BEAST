from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli.coder_client import RuntimeEvent
from app.cli.coder_state import (
    CoderSettings,
    ConversationStore,
    SlashCommand,
    parse_slash_command,
    project_runtime_event,
)


def test_settings_reject_non_directory_workspace_without_persisting(tmp_path: Path):
    missing = tmp_path / "missing"

    with pytest.raises(ValueError, match="existing directory"):
        CoderSettings(workspace=missing, provider="ollama", model="granite")

    assert not (missing / ".beast").exists()


def test_settings_and_conversation_round_trip_atomically(tmp_path: Path):
    store = ConversationStore(tmp_path)
    settings = CoderSettings(
        workspace=tmp_path,
        provider="ollama",
        model="granite-code:8b",
        session_id="agent-1",
        last_run_id="run-2",
    )

    store.save_settings(settings)
    store.append("user", "create demo.py")
    store.append(
        "assistant",
        "done",
        metadata={"run_id": "run-2", "receipt_ids": ["obs-1"]},
    )

    loaded = store.load_settings()
    messages = store.messages()
    assert loaded == settings
    assert messages == [
        {"role": "user", "content": "create demo.py", "metadata": {}},
        {
            "role": "assistant",
            "content": "done",
            "metadata": {"run_id": "run-2", "receipt_ids": ["obs-1"]},
        },
    ]
    assert not list(store.state_dir.glob("*.tmp"))
    assert json.loads(store.settings_path.read_text())["provider"] == "ollama"


def test_clear_removes_conversation_but_preserves_runtime_selection(tmp_path: Path):
    store = ConversationStore(tmp_path)
    settings = CoderSettings(tmp_path, "ollama", "granite-code:8b", "agent-1", "run-2")
    store.save_settings(settings)
    store.append("user", "hello")

    store.clear()

    assert store.messages() == []
    assert store.load_settings() == settings


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("/help", SlashCommand("help", "")),
        ("/model granite-code:8b", SlashCommand("model", "granite-code:8b")),
        ("/provider ollama", SlashCommand("provider", "ollama")),
        ("/skills", SlashCommand("skills", "")),
        ("/mcp", SlashCommand("mcp", "")),
        ("/tools", SlashCommand("tools", "")),
        ("/workspace /tmp/demo", SlashCommand("workspace", "/tmp/demo")),
        ("/status", SlashCommand("status", "")),
        ("/clear", SlashCommand("clear", "")),
        ("/exit", SlashCommand("exit", "")),
    ],
)
def test_parse_slash_command_supports_required_interface(text: str, want: SlashCommand):
    assert parse_slash_command(text) == want


def test_parse_slash_command_rejects_unknown_command():
    with pytest.raises(ValueError, match="unknown command"):
        parse_slash_command("/swarm")


def test_project_model_delta_as_stream_token():
    projected = project_runtime_event(
        RuntimeEvent(
            "agent.model.delta",
            {"sequence": 3, "payload": {"text": "hello"}},
            "3",
        )
    )

    assert projected.kind == "token"
    assert projected.text == "hello"
    assert projected.sequence == 3


def test_project_completed_tool_only_as_executed_with_real_observation_receipt():
    projected = project_runtime_event(
        RuntimeEvent(
            "agent.tool.completed",
            {
                "sequence": 8,
                "payload": {
                    "observation": {
                        "observation_id": "obs-8",
                        "tool_id": "worktree.write_file",
                        "status": "completed",
                        "result": {"path": "demo.py", "bytes": 12},
                        "evidence_digest": "abc123",
                    }
                },
            },
            "8",
        )
    )

    assert projected.kind == "tool_result"
    assert projected.tool_id == "worktree.write_file"
    assert projected.executed is True
    assert projected.success is True
    assert projected.receipt == {
        "observation_id": "obs-8",
        "evidence_digest": "abc123",
    }
    assert projected.details == {"path": "demo.py", "bytes": 12}


def test_project_tool_completion_without_receipt_as_unverified_not_success():
    projected = project_runtime_event(
        RuntimeEvent(
            "agent.tool.completed",
            {
                "sequence": 9,
                "payload": {
                    "observation": {
                        "tool_id": "worktree.write_file",
                        "status": "completed",
                        "result": {"path": "demo.py"},
                    }
                },
            },
            "9",
        )
    )

    assert projected.executed is False
    assert projected.success is False
    assert projected.status == "unverified"
    assert "missing" in projected.text.lower()


def test_project_failed_tool_preserves_actual_error_and_receipt():
    projected = project_runtime_event(
        RuntimeEvent(
            "agent.tool.failed",
            {
                "sequence": 10,
                "payload": {
                    "observation": {
                        "observation_id": "obs-10",
                        "tool_id": "worktree.verify",
                        "status": "failed",
                        "result": {"returncode": 1},
                        "error": "pytest failed",
                        "evidence_digest": "def456",
                    }
                },
            },
            "10",
        )
    )

    assert projected.executed is True
    assert projected.success is False
    assert projected.status == "failed"
    assert projected.text == "pytest failed"


def test_project_real_crystal_formation_exposes_durable_evidence_to_coder_ui():
    projected = project_runtime_event(
        RuntimeEvent(
            "agent.crystal.formed",
            {
                "sequence": 11,
                "payload": {
                    "status": "promoted",
                    "crystal_id": "coding-crystal:abc123",
                    "heldout_successes": 3,
                    "heldout_attempts": 3,
                    "lattice_admitted": True,
                    "lattice_checkpoint_hash": "sha256:checkpoint",
                    "crystal_chain_block_hash": "sha256:block",
                },
            },
            "11",
        )
    )

    assert projected.kind == "crystal"
    assert projected.status == "formed"
    assert projected.success is True
    assert "3/3" in projected.text
    assert "lattice admitted" in projected.text.lower()
    assert projected.details["crystal_id"] == "coding-crystal:abc123"


@pytest.mark.parametrize(
    ("event_name", "want_status", "want_success"),
    [
        ("agent.crystal.activated", "activated", True),
        ("agent.crystal.completed", "reused", True),
        ("agent.crystal.formation_refused", "refused", False),
        ("agent.crystal.formation_failed", "failed", False),
    ],
)
def test_project_crystal_lifecycle_statuses_truthfully(event_name, want_status, want_success):
    projected = project_runtime_event(
        RuntimeEvent(event_name, {"sequence": 12, "payload": {"reason": "evidence"}}, "12")
    )

    assert projected.kind == "crystal"
    assert projected.status == want_status
    assert projected.success is want_success


def test_session_archive_list_and_resume_round_trip(tmp_path: Path):
    store = ConversationStore(tmp_path)
    store.append("user", "first task")
    store.append("assistant", "first answer")

    archived = store.archive_session("demo work")
    assert archived is not None
    assert archived["messages"] == 2
    assert store.messages() == []

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == archived["session_id"]
    assert sessions[0]["title"] == "demo work"

    loaded = store.load_session(archived["session_id"])
    assert loaded is not None
    assert [row["content"] for row in store.messages()] == ["first task", "first answer"]


def test_settings_round_trip_preserves_session_title(tmp_path: Path):
    store = ConversationStore(tmp_path)
    store.save_settings(CoderSettings(workspace=tmp_path, session_title="fix auth"))
    assert store.load_settings().session_title == "fix auth"
