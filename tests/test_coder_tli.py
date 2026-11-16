from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import Input, Static

from app.cli.coder import BeastCoderApp
from app.cli.coder_client import RuntimeEvent


class FakeRuntimeClient:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.closed = False

    async def discover_providers(self):
        return {
            "beast_object_type": "provider_registry",
            "providers": [
                {
                    "provider_id": "ollama",
                    "default_model": "granite-code:8b",
                    "enabled": True,
                },
                {
                    "provider_id": "nvidia_nim",
                    "default_model": "nvidia/nemotron",
                    "enabled": True,
                },
            ],
        }

    async def discover_skills(self):
        return {
            "skills": [
                {"id": "skill-review", "name": "Review changes", "category": "meta_tool"}
            ],
            "state": {"skills": {"total": 1}},
        }

    async def discover_mcp(self):
        return {
            "stats": {"servers": 1, "tools": 2},
            "servers": [{"name": "remotehub", "server_class": "github", "status": "ready"}],
            "recent_execution_events": [],
        }

    async def discover_tools(self, run_id: str):
        return {
            "ok": True,
            "run_id": run_id,
            "count": 1,
            "tools": [{"tool_id": "workspace.read_range", "effect": "read"}],
        }

    async def grant_verified_skill(self, session_id: str, skill_id: str):
        return {
            "ok": True,
            "session": {"session_id": session_id},
            "receipt": {"receipt_id": f"grant-{skill_id}"},
        }

    async def execute_mcp(self, request):
        return {
            "executed": True,
            "request_id": "mcp-coder",
            "tool_name": request["tool_name"],
            "content": "BEAST",
            "edgek_crystal_tool_boundary": {
                "beast_object_type": "crystal_tool_boundary_receipt"
            },
        }

    async def runtime_status(self, run_id: str = ""):
        return {"ok": True, "run": {"run_id": run_id, "state": "completed"}}

    async def ensure_session(self, provider: str, model: str):
        return {"session_id": "agent-coder", "provider": provider, "model": model}

    async def start_run(self, session_id: str, prompt: str, provider: str, model: str):
        return {"run_id": "run-coder", "state": "planning"}

    async def follow_run(self, run_id: str):
        yield RuntimeEvent(
            "agent.model.delta",
            {"sequence": 1, "payload": {"text": "hello "}},
            "1",
        )
        yield RuntimeEvent(
            "agent.tool.started",
            {
                "sequence": 2,
                "payload": {
                    "tool_id": "workspace.read_range",
                    "arguments": {"path": "README.md"},
                },
            },
            "2",
        )
        yield RuntimeEvent(
            "agent.tool.completed",
            {
                "sequence": 3,
                "payload": {
                    "observation": {
                        "observation_id": "obs-coder",
                        "tool_id": "workspace.read_range",
                        "status": "completed",
                        "result": {"path": "README.md", "content": "BEAST"},
                        "evidence_digest": "digest-coder",
                    }
                },
            },
            "3",
        )
        yield RuntimeEvent(
            "agent.model.delta",
            {"sequence": 4, "payload": {"text": "world"}},
            "4",
        )
        yield RuntimeEvent(
            "agent.run.completed",
            {"sequence": 5, "payload": {"status": "completed"}},
            "5",
        )

    async def aclose(self):
        self.closed = True


class PausedStreamClient(FakeRuntimeClient):
    def __init__(self, workspace: Path):
        super().__init__(workspace)
        self.first_token_visible = asyncio.Event()
        self.release = asyncio.Event()

    async def follow_run(self, run_id: str):
        yield RuntimeEvent(
            "agent.model.delta",
            {"sequence": 1, "payload": {"text": "partial "}},
            "1",
        )
        self.first_token_visible.set()
        await self.release.wait()
        yield RuntimeEvent(
            "agent.model.delta",
            {"sequence": 2, "payload": {"text": "complete"}},
            "2",
        )


def _plain(renderable) -> str:
    if isinstance(renderable, Text):
        return renderable.plain
    return str(renderable)


@pytest.mark.asyncio
async def test_coder_header_uses_original_wordmark_mascot_and_explicit_workspace(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        wordmark = app.query_one("#coder-wordmark", Static)
        mascot = app.query_one("#coder-mascot", Static)
        identity = app.query_one("#coder-identity", Static)

        assert _plain(wordmark.render()).startswith("██████╗ ███████╗ █████╗")
        assert _plain(mascot.render()).strip()
        assert str(tmp_path.resolve()) in _plain(identity.render())
        assert app.mascot_state == "idle"


@pytest.mark.asyncio
async def test_required_commands_switch_real_capability_selections_and_render_discovery(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 40)) as pilot:
        await app.submit_text("/help")
        await app.submit_text("/provider ollama")
        await app.submit_text("/model granite-code:8b")
        await app.submit_text("inspect README")
        await app.submit_text("/skills")
        await app.submit_text("/mcp")
        await app.submit_text("/tools")
        await app.submit_text("/status")
        await pilot.pause()

        combined = "\n".join(item["content"] for item in app.transcript_entries)
        assert all(
            f"/{name}" in combined
            for name in (
                "help",
                "beastie",
                "model",
                "provider",
                "skills",
                "mcp",
                "tools",
                "workspace",
                "status",
                "clear",
                "exit",
            )
        )
        assert app.settings.provider == "ollama"
        assert app.settings.model == "granite-code:8b"
        assert "Review changes" in combined
        assert "remotehub" in combined
        assert "workspace.read_range" in combined
        assert "run-coder" in combined


@pytest.mark.asyncio
async def test_streaming_turn_shows_model_text_and_receipted_tool_result(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 40)) as pilot:
        await app.submit_text("inspect README")
        await pilot.pause()

        assistant = [
            item["content"] for item in app.transcript_entries if item["role"] == "assistant"
        ]
        assert assistant[-1] == "hello world"
        assert app.tool_entries[0]["kind"] == "tool_call"
        assert app.tool_entries[1]["executed"] is True
        assert app.tool_entries[1]["success"] is True
        assert app.tool_entries[1]["receipt"] == {
            "observation_id": "obs-coder",
            "evidence_digest": "digest-coder",
        }
        assert app.mascot_state == "finished"
        persisted = json.loads(
            (tmp_path / ".beast" / "coder" / "conversation.json").read_text()
        )
        assert persisted["messages"][-1]["content"] == "hello world"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("size", "compact"),
    [
        ((40, 20), True),
        ((60, 24), True),
        ((80, 30), True),
        ((120, 40), False),
        ((140, 22), True),
    ],
)
async def test_responsive_layout_keeps_input_visible_without_overlap(
    tmp_path: Path, size: tuple[int, int], compact: bool
):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        input_widget = app.query_one("#coder-input", Input)
        conversation = app.query_one("#conversation-scroll")
        tools = app.query_one("#tool-scroll")
        header = app.query_one("#coder-header")

        assert app._compact_layout is compact
        assert input_widget.region.height > 0
        assert input_widget.region.y + input_widget.region.height <= size[1]
        assert conversation.region.height > 0
        assert conversation.region.y + conversation.region.height <= input_widget.region.y
        assert input_widget.region.x + input_widget.region.width <= size[0]
        assert conversation.region.x + conversation.region.width <= size[0]
        assert tools.display is False
        assert header.display is True
        assert header.region.height > 0
        assert app.focused is input_widget

        wordmark = _plain(app.query_one("#coder-wordmark", Static).render())
        mascot = _plain(app.query_one("#coder-mascot", Static).render())
        assert wordmark.startswith("█ BEAST" if app._branding_compact else "██████╗")
        assert mascot.strip()


@pytest.mark.asyncio
async def test_input_accepts_typing_backspace_enter_and_slash_commands(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(60, 24)) as pilot:
        input_widget = app.query_one("#coder-input", Input)
        assert app.focused is input_widget

        await pilot.press(*"inspectX")
        await pilot.press("backspace")
        assert input_widget.value == "inspect"
        await pilot.press("enter")
        await pilot.pause()

        assert any(
            item["role"] == "user" and item["content"] == "inspect"
            for item in app.transcript_entries
        )
        assert input_widget.value == ""
        assert app.focused is input_widget

        await pilot.press(*"/help")
        await pilot.press("enter")
        await pilot.pause()
        assert "/workspace" in app.transcript_entries[-1]["content"]
        assert app.focused is input_widget


@pytest.mark.asyncio
async def test_terminal_mouse_reports_never_become_conversation_text(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(60, 24)) as pilot:
        input_widget = app.query_one("#coder-input", Input)
        input_widget.value = "safe ^[[<0;77;24M request"
        await pilot.pause()
        assert input_widget.value == "safe  request"

        await pilot.press("enter")
        await pilot.pause()
        combined = "\n".join(item["content"] for item in app.transcript_entries)
        assert "safe  request" in combined
        assert "^[[<" not in combined
        assert "\x1b[<" not in combined

        await app.submit_text("\x1b[<0;77;24M")
        await app.submit_text("^[[<0;77;24")
        await pilot.pause()
        combined = "\n".join(item["content"] for item in app.transcript_entries)
        assert "77;24" not in combined


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 24), (140, 22)])
async def test_compact_tool_events_render_inline_with_execution_receipt(
    tmp_path: Path, size: tuple[int, int]
):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=size) as pilot:
        await app.submit_text("inspect README")
        await pilot.pause()

        inline = _plain(app.query_one("#coder-inline-tools", Static).render())
        assert app.query_one("#tool-scroll").display is False
        assert "workspace.read_range" in inline
        assert "receipt obs-coder" in inline
        assert "digest-coder" in inline


@pytest.mark.asyncio
async def test_wide_empty_tool_sidebar_is_removed_until_real_events_exist(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        tools = app.query_one("#tool-scroll")
        conversation = app.query_one("#conversation-scroll")
        assert tools.display is False
        assert conversation.region.width == 120

        await app.submit_text("inspect README")
        await pilot.pause()
        assert tools.display is True
        assert conversation.region.width < 120


@pytest.mark.asyncio
async def test_resize_restores_original_branding_and_beastie_toggles(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        header = app.query_one("#coder-header")
        wordmark = app.query_one("#coder-wordmark", Static)
        beastie = app.query_one("#coder-beastie", Static)
        assert header.display is True
        assert _plain(wordmark.render()).startswith("██████╗ ███████╗ █████╗")

        await pilot.resize_terminal(60, 24)
        await pilot.pause()
        assert header.display is True
        assert _plain(wordmark.render()).startswith("█ BEAST")
        assert app.query_one("#tool-scroll").display is False

        await app.submit_text("/beastie")
        await pilot.pause()
        assert beastie.display is True
        assert _plain(beastie.render()).strip()

        await app.submit_text("/beastie")
        await pilot.pause()
        assert beastie.display is False

        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        assert header.display is True
        assert _plain(wordmark.render()).startswith("██████╗ ███████╗ █████╗")
        assert app.query_one("#tool-scroll").display is False


@pytest.mark.asyncio
async def test_keyboard_short_resize_reclaims_branding_after_submission(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 22)) as pilot:
        header = app.query_one("#coder-header")
        input_widget = app.query_one("#coder-input", Input)
        assert header.display is True

        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
        assert header.display is False
        assert input_widget.region.y + input_widget.region.height <= 22
        assert app.focused is input_widget

        await pilot.resize_terminal(140, 40)
        await pilot.pause()
        assert header.display is True
        assert app.focused is input_widget


@pytest.mark.asyncio
async def test_first_model_delta_is_visible_before_stream_completes(tmp_path: Path):
    client = PausedStreamClient(tmp_path)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)

    async with app.run_test(size=(120, 34)) as pilot:
        turn = asyncio.create_task(app.submit_text("stream now"))
        await client.first_token_visible.wait()
        await pilot.pause()

        assert app.mascot_state == "working"
        assert app.transcript_entries[-1]["role"] == "assistant"
        assert app.transcript_entries[-1]["content"] == "partial "

        client.release.set()
        await turn
        assert app.transcript_entries[-1]["content"] == "partial complete"


@pytest.mark.asyncio
async def test_skill_and_mcp_invocations_show_actual_runtime_receipts(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 40)) as pilot:
        await app.submit_text("/skills skill-review")
        await app.submit_text('/mcp call remotehub github_search {"query":"BEAST"}')
        await pilot.pause()

        assert any(
            item.get("kind") == "skill_grant"
            and item.get("receipt", {}).get("receipt_id") == "grant-skill-review"
            for item in app.tool_entries
        )
        assert any(
            item.get("kind") == "mcp_result"
            and item.get("executed") is True
            and item.get("receipt", {}).get("request_id") == "mcp-coder"
            for item in app.tool_entries
        )


@pytest.mark.asyncio
async def test_unknown_skill_is_rejected_before_capability_grant(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 34)) as pilot:
        await app.submit_text("/skills missing-skill")
        await pilot.pause()

        assert app.tool_entries == []
        assert any(
            row["role"] == "error" and "not reported by runtime discovery" in row["content"]
            for row in app.transcript_entries
        )


@pytest.mark.asyncio
async def test_clear_and_exit_are_explicit_and_workspace_rejects_missing_path(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 34)) as pilot:
        await app.submit_text("hello")
        await app.submit_text(f"/workspace {tmp_path / 'missing'}")
        assert any("existing directory" in row["content"] for row in app.transcript_entries)
        assert app.settings.workspace == tmp_path.resolve()

        await app.submit_text("/clear")
        assert app.transcript_entries == []
        assert app.store.messages() == []

        await app.submit_text("/exit")
        assert app.exit_requested is True
        await pilot.pause()
