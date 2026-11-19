from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from rich.text import Text
from textual.widget import Widget
from textual.widgets import Input, Static

from app.cli.coder import BeastCoderApp
from app.cli.coder_client import RuntimeEvent
from app.cli.coder_state import project_runtime_event


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

    async def start_run(self, session_id: str, prompt: str, provider: str, model: str, **kwargs):
        return {"run_id": "run-coder", "state": "planning"}

    async def start_turn(self, run_id: str):
        return {"run_id": run_id, "state": "completed"}

    def turn_events(
        self, run_id: str, *, after: int = 0, max_events: int = 50,
        idle_timeout: float = 2.0, completion=None,
    ):
        return self.follow_run(run_id)

    async def list_approvals(self, run_id: str):
        return []

    async def resolve_approval(
        self, run_id: str, approval_id: str, *, approved: bool = True,
        operator: str = "tli-operator",
    ):
        return {"ok": True, "approval": {"approval_id": approval_id, "status": "approved"}}

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


class BlockingTurnClient(FakeRuntimeClient):
    """Expose whether SSE is consumed while the blocking turn POST is active."""

    def __init__(self, workspace: Path):
        super().__init__(workspace)
        self.turn_started = asyncio.Event()
        self.stream_opened = asyncio.Event()
        self.release_turn = asyncio.Event()
        self.completion_was_live = False

    async def start_turn(self, run_id: str):
        self.turn_started.set()
        await self.release_turn.wait()
        return {"run_id": run_id, "state": "completed"}

    async def turn_events(
        self, run_id: str, *, after: int = 0, max_events: int = 50,
        idle_timeout: float = 2.0, completion=None,
    ):
        self.stream_opened.set()
        self.completion_was_live = completion is not None and not completion.done()
        yield RuntimeEvent(
            "agent.model.delta",
            {"sequence": 1, "payload": {"text": "live now"}},
            "1",
        )
        await self.release_turn.wait()


class MultiTurnClient(FakeRuntimeClient):
    def __init__(self, workspace: Path, *, approval: bool = False):
        super().__init__(workspace)
        self.turn_count = 0
        self.needs_approval = approval
        self.approved = not approval

    async def start_turn(self, run_id: str):
        self.turn_count += 1
        if self.needs_approval and not self.approved:
            return {"run_id": run_id, "state": "waiting_for_approval"}
        if self.turn_count == 1 and not self.needs_approval:
            return {"run_id": run_id, "state": "updating_plan"}
        return {"run_id": run_id, "state": "completed"}

    async def turn_events(
        self, run_id: str, *, after: int = 0, max_events: int = 50,
        idle_timeout: float = 2.0, completion=None,
    ):
        await asyncio.sleep(0)
        if self.needs_approval and not self.approved:
            yield RuntimeEvent(
                "agent.model.delta",
                {"sequence": 1, "payload": {"text": '{"decision_type":"tool","tool_id":"workspace.read"}'}},
                "1",
            )
        elif self.turn_count == 1:
            yield RuntimeEvent(
                "agent.model.delta",
                {"sequence": 1, "payload": {"text": '{"decision_type":"tool","tool_id":"workspace.index"}'}},
                "1",
            )
        else:
            yield RuntimeEvent(
                "agent.model.delta",
                {"sequence": 2, "payload": {"text": "Here is the requested final answer."}},
                "2",
            )

    async def list_approvals(self, run_id: str):
        if self.approved:
            return []
        return [{
            "approval_id": "approval-tap-me",
            "status": "pending",
            "request": {
                "tool_id": "workspace.read",
                "risk_class": "governed",
                "summary": "Read the requested source file",
            },
        }]

    async def resolve_approval(
        self, run_id: str, approval_id: str, *, approved: bool = True,
        operator: str = "tli-operator",
    ):
        assert approval_id == "approval-tap-me"
        self.approved = approved
        return {"ok": True, "approval": {"approval_id": approval_id, "status": "approved"}}


def _plain(renderable) -> str:
    if isinstance(renderable, Text):
        return renderable.plain
    return str(renderable)


@pytest.mark.asyncio
async def test_coder_header_keeps_ascii_logo_image_pet_and_workspace_visible(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        wordmark = app.query_one("#coder-wordmark", Static)
        mascot = app.query_one("#coder-mascot", Static)
        pet = app.query_one("#coder-pet", Widget)
        identity = app.query_one("#coder-identity", Static)

        assert _plain(wordmark.render()).startswith("██████╗ ███████╗")
        assert mascot.display is False
        assert pet.display is True
        assert getattr(pet, "image", None) is not None or _plain(pet.render()).strip()
        assert app.query_one("#coder-header").region.height <= 7
        assert str(tmp_path.resolve()) in _plain(identity.render())
        assert _plain(app.query_one("#coder-transcript", Static).render()).startswith(
            "██████╗ ███████╗"
        )
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
                "next",
                "approvals",
                "approve",
                "clear",
                "exit",
            )
        )
        assert app.settings.provider == "ollama"
        assert app.settings.model == "granite-code:8b"
        assert "Review changes" in combined
        assert "remotehub" in combined
        assert "workspace.read_range" in combined
        assert app.settings.last_run_id == "run-coder"


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
        assert header.region.height <= (2 if compact else 7)
        assert app.focused is input_widget

        wordmark = _plain(app.query_one("#coder-wordmark", Static).render())
        mascot = _plain(app.query_one("#coder-mascot", Static).render())
        assert wordmark == "█ BEAST" if compact else wordmark.startswith("██████╗ ███████╗")
        assert mascot == ""


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
async def test_tool_receipts_stay_inline_without_opening_a_sidebar(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        tools = app.query_one("#tool-scroll")
        conversation = app.query_one("#conversation-scroll")
        assert tools.display is False
        assert conversation.region.width == 120

        await app.submit_text("inspect README")
        await pilot.pause()
        assert tools.display is False
        assert conversation.region.width == 120
        inline = _plain(app.query_one("#coder-inline-tools", Static).render())
        assert "workspace.read_range" in inline


@pytest.mark.asyncio
async def test_expand_and_less_toggle_raw_tool_event_details(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("inspect README")
        collapsed = _plain(app.query_one("#coder-inline-tools", Static).render())
        assert '"content": "BEAST"' not in collapsed
        assert "/expand for event details" in collapsed

        await app.submit_text("/expand")
        await pilot.pause()
        expanded = _plain(app.query_one("#coder-inline-tools", Static).render())
        assert '"content": "BEAST"' in expanded

        await app.submit_text("/less")
        await pilot.pause()
        collapsed_again = _plain(app.query_one("#coder-inline-tools", Static).render())
        assert '"content": "BEAST"' not in collapsed_again


@pytest.mark.asyncio
async def test_tool_receipts_expand_when_tapped(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("inspect README")
        await pilot.pause()
        assert app.details_expanded is False

        await pilot.click("#coder-inline-tools")
        await pilot.pause()

        assert app.details_expanded is True
        expanded = _plain(app.query_one("#coder-inline-tools").render())
        assert '"content": "BEAST"' in expanded


def test_planner_decision_json_is_rendered_as_semantic_text(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    app.transcript_entries = [{
        "role": "assistant",
        "content": json.dumps({
            "decision_type": "tool",
            "tool_id": "workspace.index",
            "arguments": {"limit": 100},
        }) * 3,
    }]

    rendered = app._transcript_text().plain
    assert '"decision_type"' not in rendered
    assert "TOOL  workspace.index" in rendered
    assert rendered.count("workspace.index") == 1
    assert "limit=100" in rendered


def test_complete_planner_decision_renders_its_answer_summary(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    app.transcript_entries = [{
        "role": "assistant",
        "content": json.dumps({
            "decision_type": "complete",
            "summary": "coder.py contains the interactive BEAST terminal application.",
        }),
    }]

    rendered = app._transcript_text().plain
    assert "coder.py contains the interactive BEAST terminal application." in rendered


@pytest.mark.asyncio
async def test_safe_planner_turns_auto_continue_until_final_answer(tmp_path: Path):
    client = MultiTurnClient(tmp_path)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)

    async with app.run_test(size=(120, 40)):
        await app.submit_text("summarize coder.py")

        assert client.turn_count == 2
        assert sum(row["role"] == "user" for row in app.transcript_entries) == 1
        assert any(
            row["role"] == "assistant" and "final answer" in row["content"]
            for row in app.transcript_entries
        )


@pytest.mark.asyncio
async def test_new_user_prompt_never_reuses_a_stale_active_run(tmp_path: Path):
    client = FakeRuntimeClient(tmp_path)
    started_prompts = []

    async def active_status(run_id: str = ""):
        return {"ok": True, "run": {"run_id": run_id, "state": "updating_plan"}}

    async def record_start(session_id: str, prompt: str, provider: str, model: str, **kwargs):
        started_prompts.append(prompt)
        return {"run_id": "fresh-run", "state": "planning"}

    client.runtime_status = active_status
    client.start_run = record_start
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)

    async with app.run_test(size=(120, 40)):
        app._save_settings(session_id="session-existing", last_run_id="stale-run")
        await app.submit_text("find and summarize coder.py")

        assert started_prompts == ["find and summarize coder.py"]
        assert app.settings.last_run_id == "fresh-run"


@pytest.mark.asyncio
async def test_approval_card_tap_approves_and_resumes_to_answer(tmp_path: Path):
    client = MultiTurnClient(tmp_path, approval=True)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)

    async with app.run_test(size=(120, 40)) as pilot:
        app._save_settings(auto_mode=False)
        await app.submit_text("read coder.py")
        await pilot.pause()
        approval = app.query_one("#coder-approvals")
        assert approval.display is True
        assert "Tap to approve" in _plain(approval.render())

        await pilot.click("#coder-approvals")
        await pilot.pause()

        assert client.approved is True
        assert client.turn_count == 2
        assert approval.display is False
        assert any(
            row["role"] == "assistant" and "final answer" in row["content"]
            for row in app.transcript_entries
        )


@pytest.mark.asyncio
async def test_slash_commands_are_echoed_in_the_visible_transcript(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)):
        await app.submit_text("/approvals")

        assert any(
            row["role"] == "user"
            and row["content"] == "/approvals"
            and row.get("metadata", {}).get("command") is True
            for row in app.transcript_entries
        )


@pytest.mark.asyncio
async def test_new_decisions_and_receipts_keep_output_scrolled_to_end(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(80, 24)) as pilot:
        app.tool_entries = [
            {
                "kind": "tool_result",
                "tool_id": f"workspace.tool_{index}",
                "text": f"decision {index} completed",
                "executed": True,
                "success": True,
                "receipt": {"observation_id": f"obs-{index}"},
                "details": {"index": index},
            }
            for index in range(30)
        ]
        app._sync()
        await pilot.pause(0.25)

        viewport = app.query_one("#conversation-scroll")
        assert viewport.max_scroll_y > 0
        assert viewport.scroll_y == viewport.max_scroll_y


@pytest.mark.asyncio
async def test_user_scroll_up_pauses_follow_until_returning_to_bottom(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(80, 24)) as pilot:
        app.tool_entries = [
            {
                "kind": "tool_result",
                "tool_id": f"workspace.tool_{index}",
                "text": f"decision {index} completed",
                "executed": True,
                "success": True,
                "receipt": {"observation_id": f"obs-{index}"},
                "details": {"index": index},
            }
            for index in range(30)
        ]
        app._sync()
        await pilot.pause(0.25)
        viewport = app.query_one("#conversation-scroll")
        assert viewport.scroll_y == viewport.max_scroll_y

        viewport.scroll_page_up(animate=False)
        await pilot.pause()
        held_position = viewport.scroll_y
        assert held_position < viewport.max_scroll_y
        assert "OUTPUT PAUSED" in _plain(app.query_one("#coder-identity").render())

        app.tool_entries.append({
            "kind": "tool_result",
            "tool_id": "workspace.new_result",
            "text": "new streamed decision",
            "executed": True,
            "success": True,
            "receipt": {"observation_id": "obs-new"},
            "details": {"new": True},
        })
        app._sync()
        await pilot.pause(0.25)
        assert viewport.scroll_y == held_position

        viewport.scroll_end(animate=False)
        await pilot.pause()
        assert viewport.scroll_y == viewport.max_scroll_y
        assert app._follow_output is True


@pytest.mark.asyncio
async def test_resize_keeps_compact_branding_and_beastie_toggles(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        header = app.query_one("#coder-header")
        wordmark = app.query_one("#coder-wordmark", Static)
        beastie = app.query_one("#coder-beastie", Static)
        assert header.display is True
        assert _plain(wordmark.render()).startswith("██████╗ ███████╗")

        await pilot.resize_terminal(60, 24)
        await pilot.pause()
        assert header.display is True
        assert _plain(wordmark.render()) == "█ BEAST"
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
        assert _plain(wordmark.render()).startswith("██████╗ ███████╗")
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
async def test_turn_event_stream_opens_before_turn_post_completes(tmp_path: Path):
    client = BlockingTurnClient(tmp_path)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)

    async with app.run_test(size=(120, 34)) as pilot:
        turn = asyncio.create_task(app.submit_text("stream concurrently"))
        await asyncio.wait_for(client.stream_opened.wait(), timeout=1)
        await pilot.pause()

        assert client.turn_started.is_set()
        assert client.completion_was_live is True
        assert turn.done() is False
        assert app.transcript_entries[-1]["content"] == "live now"

        client.release_turn.set()
        await turn


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


@pytest.mark.asyncio
async def test_composer_edit_and_agent_are_one_shot(tmp_path: Path):
    client = FakeRuntimeClient(tmp_path)
    recorded = []

    async def start_run(session_id, prompt, provider, model, *, mode="agent", context_files=(), autonomy=None, **kwargs):
        recorded.append((mode, prompt))
        return {"run_id": f"composer-{len(recorded)}", "state": "planning"}

    client.start_run = start_run
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)
    async with app.run_test(size=(100, 30)):
        for text in ("Explain the project", "/edit Fix the typo", "/agent Add tests", "Explain the tests"):
            await app.submit_text(text)
    assert recorded == [
        ("agent", "Explain the project"),
        ("edit", "Fix the typo"),
        ("agent", "Add tests"),
        ("agent", "Explain the tests"),
    ]


def test_kitty_ask_attaches_only_visible_workspace_files(tmp_path: Path):
    wanted = tmp_path / "coder.py"
    wanted.write_text("pass\n")
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside\n")
    (tmp_path / "link.md").symlink_to(outside)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    assert app._composer_context_files(f"Read {wanted} and {outside}, link.md, or coder.py") == ("coder.py",)


@pytest.mark.asyncio
async def test_copy_last_run_includes_transcript_and_receipts_not_previous_run(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(100, 30)):
        await app.submit_text("Old question")
        await app.submit_text("Explain README.md")
        await app.submit_text("/copy")
        assert "Explain README.md" in app.clipboard
        assert "hello " in app.clipboard
        assert "obs-coder" in app.clipboard
        assert app.clipboard.count("obs-coder") == 1
        assert "Old question" not in app.clipboard
        assert "/copy" not in app.clipboard


def test_kitty_attachment_accepts_sentence_period_but_not_backup_extension(tmp_path: Path):
    (tmp_path / "coder.py").write_text("pass\n")
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    assert app._composer_context_files("Explain coder.py. Ignore coder.py.bak.") == ("coder.py",)


@pytest.mark.asyncio
async def test_grounded_ask_shows_rejection_not_raw_control_packet(tmp_path: Path):
    (tmp_path / "coder.py").write_text("def run(): pass\n")
    client = FakeRuntimeClient(tmp_path)

    async def start_turn(run_id):
        return {"run_id": run_id, "state": "failed"}

    async def follow_run(run_id):
        yield RuntimeEvent("agent.model.delta", {"payload": {"text": '{"decision_type":"complete"}'}}, "1")
        yield RuntimeEvent("agent.planner.review_incomplete",
                           {"payload": {"error": "Quote did not match", "coverage": "coder.py line 1"}}, "2")

    client.start_turn = start_turn
    client.follow_run = follow_run
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)
    async with app.run_test(size=(100, 30)):
        await app.submit_text("/ask Explain coder.py.")
        await app.submit_text("/copy")
        assert "Quote did not match" in app.clipboard
        assert "Coverage: coder.py line 1" in app.clipboard
        assert "decision_type" not in app.clipboard


@pytest.mark.asyncio
async def test_gateway_pause_does_not_auto_submit_a_second_turn(tmp_path: Path):
    client = FakeRuntimeClient(tmp_path)
    posts = []

    async def pause(run_id):
        posts.append(run_id)
        return {"run_id": run_id, "state": "paused"}

    client.start_turn = pause
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)
    async with app.run_test(size=(120, 34)):
        await app.submit_text("Inspect this")
        assert posts == ["run-coder"]
        assert app._turn_ready
        assert any("Coding run paused" in row["content"] for row in app.transcript_entries)


@pytest.mark.asyncio
async def test_auto_toggle_persists_and_surfaces_in_identity(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert app.settings.auto_mode is True
        identity = app.query_one("#coder-identity", Static)
        assert "AUTOPILOT" in _plain(identity.render())
        assert "ON" in _plain(identity.render())

        await app.submit_text("/auto off")
        assert app.settings.auto_mode is False
        assert app.store.load_settings().auto_mode is False
        assert "OFF" in _plain(identity.render())

        await app.submit_text("/auto on")
        assert app.settings.auto_mode is True
        assert app.store.load_settings().auto_mode is True


class ApprovalThenDoneClient(FakeRuntimeClient):
    def __init__(self, workspace: Path):
        super().__init__(workspace)
        self.turns = 0
        self.resolved: list[str] = []

    async def start_turn(self, run_id: str):
        self.turns += 1
        if self.turns == 1:
            return {"run_id": run_id, "state": "waiting_for_approval"}
        return {"run_id": run_id, "state": "completed"}

    async def list_approvals(self, run_id: str):
        return [{
            "approval_id": "approval-auto-1",
            "status": "pending",
            "request": {"tool_id": "worktree.replace_exact"},
        }]

    async def resolve_approval(self, run_id: str, approval_id: str, *, approved: bool = True, operator: str = "tli-operator"):
        self.resolved.append(approval_id)
        return {"ok": True, "approval": {"approval_id": approval_id, "status": "approved"}}


@pytest.mark.asyncio
async def test_autopilot_grants_pending_approval_and_finishes_without_operator(tmp_path: Path):
    client = ApprovalThenDoneClient(tmp_path)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("read coder.py")
        await pilot.pause()

        assert client.resolved == ["approval-auto-1"]
        assert client.turns == 2
        assert app._turn_ready is False
        assert app.mascot_state == "finished"
        assert not app.pending_approvals
        assert any(
            row["role"] == "assistant" and "hello world" in row["content"]
            for row in app.transcript_entries
        )


@pytest.mark.asyncio
async def test_live_diff_panel_renders_red_green_and_grows_with_edits(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        app._merge_live_diff(
            "demo.py",
            {
                "path": "demo.py",
                "diff": (
                    "--- a/demo.py\n+++ b/demo.py\n@@ -1,2 +1,2 @@\n"
                    "-def greet(name):\n-    return f\"hello {name}\"\n"
                    "+def greet(name):\n+    return f\"howdy {name}\"\n"
                ),
            },
        )
        app._sync()
        await pilot.pause()

        assert app.screen.has_class("has-diff")
        rendered = _plain(app.query_one("#coder-diff", Static).render())
        assert "LIVE DIFF" in rendered
        assert "EDITING" in rendered
        assert "+    return f\"howdy {name}\"" in rendered
        assert "-    return f\"hello {name}\"" in rendered
        assert "demo.py" in rendered
        assert app.diff_bundle["added"] == 2
        assert app.diff_bundle["removed"] == 2

        app._merge_live_diff(
            "utils.py",
            {"path": "utils.py", "diff": "-OLD = 1\n+OLD = 2\n"},
        )
        app._sync()
        assert set(app.diff_bundle["files"]) == {"demo.py", "utils.py"}
        assert app.diff_bundle["added"] == 3


@pytest.mark.asyncio
async def test_diff_ready_event_populates_and_marks_applied(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        event = RuntimeEvent(
            "agent.worktree.diff_ready",
            {"payload": {
                "files": ["demo.py"],
                "diff": "--- a/demo.py\n+++ b/demo.py\n@@\n-hello\n+howdy\n",
                "added": 1,
                "removed": 1,
            }},
            "7",
        )
        projected = project_runtime_event(event)
        assert projected.kind == "diff"
        app._merge_diff(projected.details, status=projected.status)
        app._sync()
        await pilot.pause()
        rendered = _plain(app.query_one("#coder-diff", Static).render())
        assert "READY" in rendered
        assert "+howdy" in rendered
        assert "-hello" in rendered
        assert app.settings.workspace.name in _plain(app.query_one("#coder-identity", Static).render())


@pytest.mark.asyncio
async def test_down_opens_agent_menu_and_selection_sets_next_mode(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("down")
        await pilot.pause()
        assert app._menu_kind == "agents"
        assert app.screen.has_class("menu-open")
        menu = _plain(app.query_one("#coder-menu", Static).render())
        for label in ("AGENT", "PLAN", "REVIEW", "SWARM"):
            assert label in menu
        assert "▸ AGENT" in menu

        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app._menu_kind == ""
        assert not app.screen.has_class("menu-open")
        assert app._pending_agent == "PLAN"
        assert app._pending_mode == "ask"


@pytest.mark.asyncio
async def test_swarm_menu_sets_decomposition_prefix_for_next_prompt(tmp_path: Path):
    recorded = []

    class MenuClient(FakeRuntimeClient):
        async def start_run(self, session_id, prompt, provider, model, **kwargs):
            recorded.append((prompt, kwargs))
            return await super().start_run(session_id, prompt, provider, model, **kwargs)

    app = BeastCoderApp(workspace=tmp_path, runtime_client=MenuClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        app.open_agent_menu()
        app._menu_index = 3
        await app._choose_menu()
        assert app._pending_mode == "agent"
        assert app._pending_agent == "SWARM"
        await app.submit_text("Add tests")
        await pilot.pause()
    assert recorded, "the swarm prompt must reach the runtime"
    assert recorded[0][0].startswith("Decompose this request")
    assert recorded[0][0].endswith("Add tests")


@pytest.mark.asyncio
async def test_help_lists_grouped_commands_and_new_controls(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("/help")
        await pilot.pause()
        combined = "\n".join(item["content"] for item in app.transcript_entries)
        for token in ("RUN", "CONTEXT", "SESSIONS", "RUNTIME", "VIEW"):
            assert token in combined
        for token in ("/diff", "/apply", "/sessions", "/new", "/agents", "/compact", "/budget"):
            assert token in combined
        assert "F6" in combined and "F7" in combined


@pytest.mark.asyncio
async def test_compact_archives_transcript_and_keeps_resumable_digest(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("/ask Explain demo.py.")
        await pilot.pause()
        app._compact_history("manual")
        await pilot.pause()
        assert len(app.transcript_entries) <= 3
        digest = "\n".join(str(row.get("content") or "") for row in app.transcript_entries)
        assert "COMPACTED CONTEXT" in digest
        sessions = app.store.list_sessions()
        assert sessions and sessions[0]["messages"] >= 2


@pytest.mark.asyncio
async def test_jump_latest_restores_follow_mode(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(80, 24)) as pilot:
        app.tool_entries = [
            {
                "kind": "tool_result",
                "tool_id": f"workspace.tool_{index}",
                "text": f"decision {index} completed",
                "executed": True,
                "success": True,
                "receipt": {"observation_id": f"obs-{index}"},
                "details": {"index": index},
            }
            for index in range(30)
        ]
        app._sync()
        await pilot.pause(0.25)
        viewport = app.query_one("#conversation-scroll")
        viewport.scroll_page_up(animate=False)
        await pilot.pause()
        assert app._follow_output is False
        assert app.screen.has_class("show-jump")

        await pilot.press("f6")
        await pilot.pause(0.2)
        assert app._follow_output is True
        assert not app.screen.has_class("show-jump")
        assert viewport.scroll_y == viewport.max_scroll_y


@pytest.mark.asyncio
async def test_sessions_command_opens_menu_and_resumes_archive(tmp_path: Path):
    client = FakeRuntimeClient(tmp_path)
    app = BeastCoderApp(workspace=tmp_path, runtime_client=client)
    app.store.append("user", "archived question")
    app.store.append("assistant", "archived answer")
    archived = app.store.archive_session("old session")
    assert archived is not None

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("/sessions")
        await pilot.pause()
        assert app._menu_kind == "sessions"
        assert app.screen.has_class("menu-open")
        assert "SESSIONS" in _plain(app.query_one("#coder-menu", Static).render())

        await pilot.press("enter")
        await pilot.pause()
        assert app._menu_kind == ""
        contents = [row["content"] for row in app.transcript_entries]
        assert "archived question" in contents
        assert "archived answer" in contents


@pytest.mark.asyncio
async def test_conversational_greeting_does_not_start_agent_run(tmp_path: Path):
    """Plain greetings like 'Sup bro' get a friendly reply, not an agent run."""
    started = []

    class NoRunClient(FakeRuntimeClient):
        async def start_run(self, *args, **kwargs):
            started.append(True)
            return await super().start_run(*args, **kwargs)

    app = BeastCoderApp(workspace=tmp_path, runtime_client=NoRunClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        await app.submit_text("Sup bro")
        await pilot.pause()

        # No agent run should have been started
        assert not started, "Conversational input must not start an AgentRun"
        assert app._streaming is False
        assert app.mascot_state == "idle"
        assert app._turn_ready is True

        # A friendly assistant reply should appear in the transcript
        assistant_rows = [row for row in app.transcript_entries if row.get("role") == "assistant"]
        assert assistant_rows, "Expected an assistant reply"
        reply = assistant_rows[-1]["content"]
        assert len(reply) > 10
        assert "workspace" in reply.lower() or "coding" in reply.lower()

        # No tool entries (no worktree bind/edit/verify)
        assert app.tool_entries == []


@pytest.mark.asyncio
async def test_thinking_panel_renders_reasoning_content(tmp_path: Path):
    """Model reasoning_content renders in the collapsible thinking panel."""
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        # Initially no thinking content
        assert app.screen.has_class("has-thinking") is False
        thinking = _plain(app.query_one("#coder-thinking", Static).render())
        assert "THINKING" in thinking

        # Inject a reasoning event
        event = RuntimeEvent(
            "agent.model.reasoning",
            {"payload": {"text": "I need to inspect demo.py before making any changes."}},
            "1",
        )
        projected = project_runtime_event(event)
        assert projected.kind == "reasoning"
        app.thinking_bundle = str(projected.text or "")
        app.screen.set_class(bool(app.thinking_bundle), "has-thinking")
        app._sync()
        await pilot.pause()

        assert app.screen.has_class("has-thinking")
        rendered = _plain(app.query_one("#coder-thinking", Static).render())
        assert "THINKING" in rendered
        assert "inspect demo.py" in rendered

        # Toggle expanded
        app.toggle_thinking_expanded()
        app._sync()
        assert app.thinking_expanded is True

        # Clearing thinking removes the class
        app.thinking_bundle = ""
        app.screen.set_class(False, "has-thinking")
        app._sync()
        assert app.screen.has_class("has-thinking") is False


@pytest.mark.asyncio
async def test_thinking_panel_toggle_expanded(tmp_path: Path):
    """Toggling the thinking panel switches expanded state."""
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))

    async with app.run_test(size=(120, 40)) as pilot:
        app.thinking_bundle = "Some reasoning text here."
        app.screen.set_class(True, "has-thinking")
        app._sync()
        assert app.screen.has_class("has-thinking")
        app.toggle_thinking_expanded()
        app._sync()
        assert app.thinking_expanded is True
        app.toggle_thinking_expanded()
        app._sync()
        assert app.thinking_expanded is False


@pytest.mark.asyncio
async def test_copy_file_writes_sanitized_last_run_without_changing_clipboard(tmp_path: Path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(100, 30)):
        await app.submit_text("Explain README.md")
        app.copy_to_clipboard("SENTINEL")
        await app.submit_text("/copy file")
        exported = sorted((tmp_path / ".beast" / "coder").glob("last-run-*.txt"))
        assert len(exported) == 1
        content = exported[0].read_text(encoding="utf-8")
        assert "Explain README.md" in content
        assert "obs-coder" in content
        assert "/copy file" not in content
        assert "\\x1b[" not in content
        assert app.clipboard == "SENTINEL"
        assert exported[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_input_submits_in_worker_so_diff_binding_responds_during_turn(tmp_path):
    class HeldRuntime(FakeRuntimeClient):
        async def start_turn(self, run_id):
            await asyncio.sleep(0.7)
            return {"run_id": run_id, "state": "completed"}

    app = BeastCoderApp(workspace=tmp_path, runtime_client=HeldRuntime(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        app.query_one(Input).value = "/agent Change the fixture"
        await pilot.press("enter")
        assert app._streaming, "the input handler must return before the turn completes"
        before = app.diff_expanded
        await pilot.press("f7")
        assert app.diff_expanded is not before
        assert app._streaming


def test_worktree_snapshot_replaces_live_edit_and_next_edit_keeps_other_files(tmp_path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    a = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+A\n"
    b = a.replace("a.py", "b.py").replace("-a\n+A\n", "-b\n+B\n")
    app._record_tool_patch("worktree.replace_exact", {"path": "a.py", "diff": a})
    app._record_tool_patch("worktree.diff", {"diff": a + b})
    assert app.diff_bundle["files"] == ["a.py", "b.py"]
    assert app.diff_bundle["added"] == 2
    app._record_tool_patch("worktree.replace_exact", {"path": "a.py", "diff": a.replace("+A\n", "+AA\n")})
    assert app.diff_bundle["diff"].count("diff --git") == 2
    assert "+AA\n" in app.diff_bundle["diff"]


@pytest.mark.asyncio
async def test_direct_timeline_keeps_reasoning_and_edit_delta_per_action(tmp_path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(120, 40)):
        app._begin_action()
        app.thinking_bundle = "Read the target."
        app._update_action({"kind": "tool_call", "tool_id": "workspace.read_range", "details": {}})
        app._update_action({"kind": "tool_result", "tool_id": "workspace.read_range", "status": "completed", "details": {}})
        app._begin_action()
        app.thinking_bundle = "Make a bounded edit."
        app._update_action({"kind": "tool_call", "tool_id": "worktree.replace_exact", "details": {}})
        app._update_action({"kind": "tool_result", "tool_id": "worktree.replace_exact", "status": "completed",
                            "details": {"path": "a.py", "action_diff": "@@ -1 +1 @@\n-a\n+b\n"}})
        assert [x["thinking"] for x in app._actions] == ["Read the target.", "Make a bounded edit."]
        collapsed = app._actions_text().plain
        assert "Read the target." not in collapsed and "+b" in collapsed
        app.action_toggle_action_reasoning(app._actions[0]["id"])
        expanded = app._actions_text().plain
        assert "Read the target." in expanded and "Make a bounded edit." not in expanded


@pytest.mark.asyncio
async def test_direct_diff_dock_appears_on_edit_while_output_is_paused(tmp_path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        app._begin_action()
        app._follow_output = False
        app._record_tool_patch("worktree.replace_exact", {
            "path": "a.py", "diff": "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-a\n+b\n",
        })
        app._sync()
        await pilot.pause()
        dock = app.query_one("#coder-diff-scroll")
        assert dock.display
        assert "+b" in _plain(app.query_one("#coder-diff", Static).render())
        assert not app._follow_output
        await pilot.press("f7")
        assert not dock.display
        await pilot.press("f7")
        assert dock.display


@pytest.mark.asyncio
async def test_direct_history_shows_numbered_edits_one_reasoning_preview_and_one_summary(tmp_path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(120, 40)):
        app._actions.extend([
            {"id": 1, "status": "completed", "tool_id": "workspace.read_range",
             "thinking": "First thought. " + "Long repeated text. " * 50},
            {"id": 2, "status": "completed", "tool_id": "worktree.replace_exact",
             "thinking": "Second thought.", "details": {"path": "a.py", "action_diff": "@@ -5,2 +5,2 @@\n same\n-a\n+b\n"}},
        ])
        app.action_toggle_action_reasoning(1)
        assert len(app._actions_text().plain) < 440
        app.action_toggle_action_reasoning(2)
        app._action_summary = "Verified change."
        text = app._actions_text().plain
        assert "First thought." not in text and "Second thought." in text
        assert "6 +b" in text and "6 -a" in text
        assert text.count("Verified change.") == 1
        assert text.index("Edited") < text.index("Verified change.")


@pytest.mark.asyncio
async def test_receipts_have_visible_toggle_without_replacing_action_history(tmp_path):
    app = BeastCoderApp(workspace=tmp_path, runtime_client=FakeRuntimeClient(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        app._begin_action()
        app._update_action({"kind": "tool_call", "tool_id": "worktree.read_file",
                            "details": {"arguments": {"path": "a.py"}}})
        app._sync()
        await pilot.pause()
        toggle = app.query_one("#coder-receipts-toggle")
        pane = app.query_one("#tool-scroll")
        assert toggle.display and not pane.display
        await pilot.click("#coder-receipts-toggle")
        assert pane.display and "Read" in _plain(app.query_one("#coder-inline-tools", Static).render())
        await pilot.press("f9")
        assert not pane.display
