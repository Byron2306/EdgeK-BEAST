"""Focused Claude Code-style terminal interface for the BEAST coding runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Input, Static

# Over SSH (e.g. Termux) the terminal often never answers textual-image's cell-size
# query; it then falls back to VT340 sizes and logs a TimeoutError traceback at
# WARNING. The fallback is fine, so keep that noise out of the operator console.
logging.getLogger("textual_image._terminal").setLevel(logging.ERROR)

try:
    # Imported before Textual starts so textual-image can safely detect Kitty
    # graphics / Sixel and select its Unicode fallback when neither is present.
    from textual_image.widget import (
        HalfcellImage,
        Image as AutoTerminalImage,
        SixelImage,
        TGPImage,
    )
    _IMAGE_PROTOCOL = os.environ.get("BEAST_IMAGE_PROTOCOL", "auto").strip().lower()
    TerminalImage = {
        "auto": AutoTerminalImage,
        "kitty": TGPImage,
        "tgp": TGPImage,
        "sixel": SixelImage,
        "halfcell": HalfcellImage,
    }.get(_IMAGE_PROTOCOL, AutoTerminalImage)
except ImportError:  # Python < 3.12 and minimal/offline installations
    TerminalImage = None  # type: ignore[assignment,misc]

from app.cli.coder_client import CoderRuntimeClient, RuntimeClientError, RuntimeTurnUnconfirmed
from app.kernel.agents.intent_routing import route_composer_mode, resolve_context_files
from app.cli.coder_state import (
    COMMAND_GROUPS,
    REQUIRED_COMMANDS,
    CoderSettings,
    ConversationStore,
    parse_slash_command,
    project_runtime_event, is_history_row,
)
from app.cli.ui import (
    BEAST_ACID,
    BEAST_BORDER,
    BEAST_DEEP,
    BEAST_GREEN,
    BEAST_INFO,
    BEAST_MUTED,
    BEAST_PANEL,
    BEAST_PANEL_ALT,
    BEAST_TEXT,
    BEAST_WARN,
    beast_wordmark,
    pet_sprite,
    sprite_mascot,
)

RuntimeFactory = Callable[[Path], CoderRuntimeClient]

_PET_FRAME_PATHS = tuple(
    sorted((Path(__file__).with_name("assets") / "sprites" / "pet").glob("frame_*.png"))
)
_PET_FRAME_ORDER = {
    "idle": tuple(range(0, 6)),
    "working": tuple(range(6, 22)),
    "finished": tuple(range(39, 45)),
    "alert": tuple(range(45, 51)),
}


class ToolEventPanel(Static):
    """Tap/click target for expanding and collapsing runtime receipts."""

    can_focus = True

    async def on_click(self) -> None:
        if not self.screen.has_class("action-timeline"):
            await self.app.toggle_tool_details()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.toggle_tool_details)  # type: ignore[attr-defined]
            event.stop()


class ApprovalPanel(Static):
    """A keyboard- and touch-friendly approval action card."""

    can_focus = True

    async def on_click(self) -> None:
        await self.app.activate_pending_approval()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.activate_pending_approval)  # type: ignore[attr-defined]
            event.stop()


class DiffPanel(Static):
    """Live red/green unified diff for the current run."""

    can_focus = True

    async def on_click(self) -> None:
        await self.app.toggle_diff_expanded()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.toggle_diff_expanded)  # type: ignore[attr-defined]
            event.stop()


class ThinkingPanel(Static):
    """Collapsible thinking/reasoning block with a turning light, like OpenCode."""

    can_focus = True

    async def on_click(self) -> None:
        self.app.toggle_thinking_expanded()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.toggle_thinking_expanded)  # type: ignore[attr-defined]
            event.stop()


class IdeCompatPanel(Static):
    """IDE compatibility status: language servers, notebooks, SSH, containers, extensions."""

    can_focus = True

    async def on_click(self) -> None:
        self.app.toggle_ide_compat_expanded()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.toggle_ide_compat_expanded)  # type: ignore[attr-defined]
            event.stop()


class CrystalLatticePanel(Static):
    """Live crystal reuse + lattice promotion status for the current run.

    Shows verified crystal promotions, lattice node/edge composition, and
    autopromotion activity. Click to expand/collapse.
    """

    can_focus = True

    async def on_click(self) -> None:
        self.app.toggle_crystal_lattice_expanded()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.toggle_crystal_lattice_expanded)  # type: ignore[attr-defined]
            event.stop()


class JumpLatestPanel(Static):
    """One-key/one-tap return to the live tail of the conversation."""

    can_focus = True

    async def on_click(self) -> None:
        self.app.action_jump_latest()  # type: ignore[attr-defined]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            self.app.call_later(self.app.action_jump_latest)  # type: ignore[attr-defined]
            event.stop()


_TERMINAL_RUN_STATES = {
    "completed", "failed", "blocked", "budget_exhausted",
    "policy_blocked", "cancelled", "rejected", "rolled_back",
}


class ConversationScroll(VerticalScroll):
    """Scrollable output that stops following as soon as the operator moves up."""

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        app = self.app
        if getattr(app, "_auto_scrolling", False):
            return
        at_end = new_value >= max(0.0, float(self.max_scroll_y) - 0.5)
        app._follow_output = at_end  # type: ignore[attr-defined]
        with suppress(Exception):
            app.screen.set_class(not at_end, "show-jump")  # type: ignore[attr-defined]
            app.query_one("#coder-identity", Static).update(app._identity_text())  # type: ignore[attr-defined]

    def _pause_follow(self) -> None:
        app = self.app
        app._follow_output = False  # type: ignore[attr-defined]
        with suppress(NoMatches):
            app.screen.add_class("show-jump")
            app.query_one("#coder-identity", Static).update(app._identity_text())  # type: ignore[attr-defined]

    def scroll_page_up(self, *args: Any, **kwargs: Any) -> None:
        self._pause_follow()
        super().scroll_page_up(*args, **kwargs)

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._pause_follow()
        super()._on_mouse_scroll_up(event)


# Textual's terminal parser handles complete SGR mouse reports. Some SSH/mobile
# terminal combinations can, however, deliver a truncated report (or its
# caret-escaped representation) as text. Keep those reports out of the editor
# and conversation without intercepting normal Key or MouseEvent messages.
_SGR_MOUSE_TEXT = re.compile(
    r"(?:\x1b\[|\x9b|\^\[\[|\[)<[0-9]{1,4};-?[0-9]{1,6};-?[0-9]{1,6}[Mm]"
)
_PARTIAL_SGR_MOUSE_TEXT = re.compile(
    r"(?:\x1b\[|\x9b|\^\[\[)<[0-9;+-]{1,32}[Mm]?"
)
_ANSI_CONTROL_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_UNSAFE_TEXT_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitize_terminal_text(value: str) -> str:
    """Remove terminal reports that must never become conversation content."""
    text = str(value or "")
    text = _SGR_MOUSE_TEXT.sub("", text)
    text = _PARTIAL_SGR_MOUSE_TEXT.sub("", text)
    text = _ANSI_CONTROL_SEQUENCE.sub("", text)
    return _UNSAFE_TEXT_CONTROLS.sub("", text)


_PASTE_TOKEN = re.compile(r"\[Pasted #(\d+): \d+ lines\]")


class PasteInput(Input):
    """Single-line composer that keeps multi-line pastes intact.

    Textual's Input keeps only the first line of a bracketed paste. A multi-line paste is
    stored whole and shown as a compact '[Pasted #n: N lines]' token that expands on submit,
    so a big paste is one message, never submitted line by line."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pastes: dict[int, str] = {}

    def _on_paste(self, event: events.Paste) -> None:
        text = str(event.text or "").replace("\r\n", "\n").replace("\r", "\n")
        if "\n" not in text.strip("\n"):
            return  # Textual also runs Input._on_paste, which inserts a single line
        number = len(self.pastes) + 1
        self.pastes[number] = text.strip("\n")
        self.insert_text_at_cursor(f"[Pasted #{number}: {text.strip(chr(10)).count(chr(10)) + 1} lines]")
        event.prevent_default()  # skip Input._on_paste (it would add the first line again)
        event.stop()

    def expand(self, value: str) -> str:
        expanded = _PASTE_TOKEN.sub(lambda m: self.pastes.get(int(m.group(1)), m.group(0)), value)
        self.pastes = {}
        return expanded


class BeastCoderApp(App[None]):
    """A single-purpose coding conversation over BEAST's durable AgentRuns."""

    # Short greetings / pleasantries get a friendly reply instead of spawning
    # a full autonomous coding run (worktree, bind, edit, verify, apply).
    _CONVERSATIONAL = (
        r"^(hi|hello|hey|sup|yo|howdy|greetings)[!,. ]*(bro|dude|friend|mate|pal|there|everyone|all)?[!,. ]*$",
        r"^(good morning|good afternoon|good evening)[!,. ]*$",
        r"^(thanks|thank you|thx|cheers|appreciate it)[!,. ]*$",
        r"^(bye|goodbye|see you|later|catch you)[!,. ]*$",
        r"^(how are you|what.s up|what is up|how.s it going)[?,. ]*$",
        r"^(ok|okay|k|cool|nice|great|awesome)[!,. ]*$",
    )

    @staticmethod
    def _is_conversational(prompt: str) -> bool:
        stripped = prompt.strip()
        if len(stripped) > 60:
            return False
        import re
        return any(re.search(pat, stripped, re.IGNORECASE) for pat in BeastCoderApp._CONVERSATIONAL)

    @staticmethod
    def _conversational_reply(prompt: str) -> str:
        lowered = prompt.strip().lower()
        if any(w in lowered for w in ("bye", "goodbye", "see you", "later", "catch you")):
            return "Catch you later. Drop a coding task whenever you're ready — I'll spin up the agent loop and verify every edit before it touches your workspace."
        if any(w in lowered for w in ("thanks", "thank you", "thx", "cheers", "appreciate")):
            return "You're welcome! Got a file that needs fixing or a feature to build? Just describe it and I'll handle the rest."
        if any(w in lowered for w in ("how are you", "what.s up", "what is up", "how.s it going")):
            return "I'm here and ready to code. What are we working on?"
        if any(w in lowered for w in ("ok", "okay", "k", "cool", "nice", "great", "awesome")):
            return "Copy that. What's the next coding task?"
        return "Hello! I'm BEAST, your autonomous coding agent. Describe what you want to build or fix, and I'll inspect, edit, verify, and apply it — with a live red/green diff so you can see every change."

    AUTO_FOCUS = "#coder-input"
    BINDINGS = [
        Binding("ctrl+shift+c", "copy_smart", "Copy selection or last run", show=False, priority=True),
        Binding("f2", "copy_smart", "Copy selection or last run", show=False),
        Binding("f3", "toggle_mouse", "Toggle mouse capture", show=False),
        Binding("ctrl+end", "jump_latest", "Jump to latest", show=False, priority=True),
        Binding("f6", "jump_latest", "Jump to latest", show=False),
        Binding("f7", "toggle_diff", "Toggle live diff", show=False),
        Binding("f8", "toggle_thinking", "Toggle thinking", show=False),
        Binding("f9", "toggle_receipts", "Toggle tool calls and receipts", show=False),
        Binding("f10", "toggle_crystal_lattice", "Toggle crystal/lattice", show=False),
        Binding("escape", "close_menu", "Close menu", show=False),
        Binding("down", "menu_down", "Agent menu", show=False, priority=True),
        Binding("up", "menu_up", "Menu up", show=False, priority=True),
    ]
    COMPACT_MIN_WIDTH = 100
    COMPACT_MIN_HEIGHT = 28
    BRANDING_MIN_CONTENT_HEIGHT = 24

    CSS = f"""
    Screen {{
        background: {BEAST_DEEP};
        color: {BEAST_TEXT};
        layout: vertical;
    }}
    #coder-header {{
        height: 7;
        background: {BEAST_PANEL};
        border-bottom: solid {BEAST_BORDER};
        padding: 0 1;
    }}
    #coder-wordmark {{ width: 1fr; height: 6; color: {BEAST_GREEN}; text-style: bold; content-align: left middle; }}
    #coder-pet {{ width: 30; height: 6; content-align: center middle; }}
    #coder-mascot {{ display: none; }}
    #coder-identity {{
        height: 1;
        padding: 0 1;
        background: {BEAST_PANEL_ALT};
        color: {BEAST_GREEN};
    }}
    #coder-body {{ height: 1fr; min-height: 0; }}
    #conversation-scroll {{ width: 1fr; height: 1fr; min-height: 0; padding: 1 2; scrollbar-color: {BEAST_GREEN}; }}
    #coder-transcript, #coder-inline-tools, #coder-approvals {{ height: auto; }}
    #coder-diff-scroll {{
        display: none;
        height: auto;
        max-height: 12;
    }}
    Screen.has-diff #coder-diff-scroll {{ display: block; }}
    #coder-diff {{
        height: auto;
        margin: 1 0;
        padding: 0 1;
        border: round {BEAST_BORDER};
        background: {BEAST_PANEL};
    }}
    #coder-diff:focus {{ border: round {BEAST_ACID}; }}
    #coder-thinking {{
        display: none;
        height: auto;
        max-height: 20;
        margin: 1 0;
        padding: 0 1;
        border: round {BEAST_WARN};
        background: {BEAST_PANEL_ALT};
        color: {BEAST_WARN};
    }}
    #coder-thinking:focus {{ border: round {BEAST_ACID}; }}
    Screen.has-thinking #coder-thinking {{ display: block; }}
    Screen.action-timeline #coder-thinking {{ height: 4; margin: 0 1; }}
    #coder-ide-compat {{
        display: none;
        height: auto;
        max-height: 22;
        margin: 1 0;
        padding: 0 1;
        border: round {BEAST_ACID};
        background: {BEAST_PANEL_ALT};
        color: {BEAST_TEXT};
    }}
    #coder-ide-compat:focus {{ border: round {BEAST_GREEN}; }}
    Screen.has-ide-compat #coder-ide-compat {{ display: block; }}
    #coder-crystal-lattice {{
        display: none;
        height: auto;
        max-height: 22;
        margin: 1 0;
        padding: 0 1;
        border: round {BEAST_WARN};
        background: {BEAST_PANEL_ALT};
        color: {BEAST_WARN};
    }}
    #coder-crystal-lattice:focus {{ border: round {BEAST_ACID}; }}
    Screen.has-crystal-lattice #coder-crystal-lattice {{ display: block; }}
    #coder-jump {{
        display: none;
        height: 1;
        padding: 0 1;
        background: {BEAST_PANEL_ALT};
        color: {BEAST_WARN};
        content-align: center middle;
    }}
    Screen.show-jump #coder-jump {{ display: block; }}
    #coder-menu {{
        display: none;
        height: auto;
        max-height: 12;
        margin: 0 1;
        padding: 0 1;
        border: round {BEAST_ACID};
        background: {BEAST_PANEL_ALT};
        color: {BEAST_TEXT};
    }}
    Screen.menu-open #coder-menu {{ display: block; }}
    #coder-inline-tools {{ display: none; }}
    #coder-approvals {{
        display: none;
        margin: 1 0;
        padding: 1 2;
        border: round {BEAST_WARN};
        background: {BEAST_PANEL_ALT};
    }}
    #coder-approvals:focus {{ border: round {BEAST_ACID}; }}
    #coder-inline-tools:focus {{ background: {BEAST_PANEL_ALT}; }}
    #coder-beastie {{
        display: none;
        width: 100%;
        height: 16;
        content-align: center middle;
    }}
    #tool-scroll {{
        display: none;
        height: auto;
        max-height: 10;
        margin: 0 1;
        padding: 0 1;
        border: round {BEAST_BORDER};
        background: {BEAST_PANEL};
    }}
    Screen.show-receipts #tool-scroll {{ display: block; }}
    #coder-receipts-toggle {{
        display: none;
        height: 1;
        min-height: 1;
        margin: 0 1;
        padding: 0 1;
        border: none;
        width: auto;
        color: {BEAST_ACID};
        background: {BEAST_PANEL_ALT};
    }}
    Screen.action-timeline #coder-receipts-toggle {{ display: block; }}
    #coder-input {{
        height: 3;
        border: tall {BEAST_BORDER};
        background: {BEAST_PANEL_ALT};
        color: {BEAST_TEXT};
    }}
    #coder-input:focus {{ border: tall {BEAST_ACID}; }}

    Screen.compact #coder-header {{ height: 2; padding: 0 1; }}
    Screen.compact #coder-wordmark {{ width: 1fr; height: 1; }}
    Screen.compact #coder-pet {{ display: none; }}
    Screen.tiny #coder-header {{ height: 2; }}
    Screen.branding-hidden #coder-header {{ display: none; }}
    Screen.compact #coder-identity {{
        height: 1;
        padding: 0 1;
        border-bottom: none;
    }}
    Screen.compact #conversation-scroll {{ width: 1fr; padding: 0 1; }}
    Screen.has-tools #coder-inline-tools {{ display: block; }}
    Screen.has-approvals #coder-approvals {{ display: block; }}
    Screen.beastie-expanded #coder-beastie {{ display: block; }}
    """

    def __init__(
        self,
        *,
        workspace: str | Path,
        base_url: str | None = None,
        runtime_client: CoderRuntimeClient | Any | None = None,
        runtime_client_factory: RuntimeFactory | None = None,
        engine: str | None = None,
    ) -> None:
        super().__init__()
        root = Path(workspace).expanduser().resolve()
        self.engine = str(engine or os.environ.get("BEAST_TLI_ENGINE") or "direct_coder").strip().lower()
        if self.engine not in {"direct_coder", "typed_planner"}:
            raise ValueError("engine must be 'direct_coder' or 'typed_planner'")
        self.store = ConversationStore(root)
        self.settings = self.store.load_settings()
        self.base_url = str(
            base_url
            or os.environ.get("BEAST_GATEWAY_URL")
            or "http://127.0.0.1:8101"
        ).rstrip("/")
        self._runtime_client_factory = runtime_client_factory
        self.runtime = runtime_client or self._new_runtime(root)
        self._injected_runtime = runtime_client is not None
        self.transcript_entries: list[dict[str, Any]] = self.store.messages()
        self.tool_entries: list[dict[str, Any]] = []
        self._run_tool_start = 0
        self.pending_approvals: list[dict[str, Any]] = []
        self.mascot_state = "idle"
        self._mascot_frame = 0
        self._branding_compact = False
        self._mascot_cells = 34
        self._mascot_rows = 14
        self.beastie_expanded = False
        self.details_expanded = False
        self._welcome_active = True
        self._compact_layout = True
        self.exit_requested = False
        self._streaming = False
        self._turn_ready = False
        self._run_event_after: dict[str, int] = {}
        self.subject = ""
        self._last_stream_paint = 0.0
        self._follow_output = True
        self._auto_scrolling = False
        # Live diff + working timer + menus.
        self.diff_bundle: dict[str, Any] = {}
        self._live_diffs: dict[str, str] = {}
        self.diff_expanded = True
        # Thinking / reasoning block.
        self.thinking_bundle: str = ""
        self.thinking_expanded = False
        self._actions: list[dict[str, Any]] = []
        self._current_action: dict[str, Any] | None = None
        self._action_count = 0
        self._expanded_actions: set[int] = set()
        self._last_thinking_paint = 0.0
        self._show_cumulative_diff = True
        self._action_summary = ""
        # IDE compatibility.
        self.ide_compat: dict[str, Any] = {}
        self.ide_compat_expanded = False
        self.execution_target: str = "local"
        # Crystal reuse + lattice compounding.
        self.crystal_lattice: dict[str, Any] = {}
        self.crystal_lattice_expanded = False
        self._work_started_at: float | None = None
        self._status_dot = 0
        self._menu_kind = ""
        self._menu_items: list[dict[str, str]] = []
        self._menu_index = 0
        self._pending_agent = "AGENT"
        self._pending_mode = "agent"
        self._pending_prefix = ""
        self._permission_nuked = False

    def _new_runtime(self, workspace: Path) -> CoderRuntimeClient:
        if self._runtime_client_factory is not None:
            return self._runtime_client_factory(workspace)
        return CoderRuntimeClient(self.base_url, workspace, engine=self.engine)

    def compose(self) -> ComposeResult:
        with Horizontal(id="coder-header"):
            yield Static(beast_wordmark(), id="coder-wordmark")
            if TerminalImage is not None and _PET_FRAME_PATHS:
                yield TerminalImage(self._pet_frame_path(), id="coder-pet")
            else:
                yield Static(pet_sprite(self.mascot_state, self._mascot_frame), id="coder-pet")
            yield Static("", id="coder-mascot")
        yield Static(self._identity_text(), id="coder-identity")
        with Horizontal(id="coder-body"):
            with ConversationScroll(id="conversation-scroll"):
                yield Static(self._transcript_text(), id="coder-transcript")
                yield ApprovalPanel(self._approval_text(), id="coder-approvals")
                yield ToolEventPanel(self._tools_text(), id="coder-inline-tools")
                yield IdeCompatPanel(self._ide_compat_text(), id="coder-ide-compat")
                yield CrystalLatticePanel(self._crystal_lattice_text(), id="coder-crystal-lattice")
                yield Static(
                    sprite_mascot(self.mascot_state, self._mascot_frame),
                    id="coder-beastie",
                )
        yield Button("Show tool calls + receipts · F9", id="coder-receipts-toggle")
        with VerticalScroll(id="tool-scroll"):
            yield Static(self._tools_text(), id="coder-tools")
        with VerticalScroll(id="coder-diff-scroll"):
            yield DiffPanel(self._diff_text(), id="coder-diff")
        yield ThinkingPanel(self._thinking_text(), id="coder-thinking")
        yield JumpLatestPanel("▼  JUMP TO LATEST  ·  F6 / Ctrl+End", id="coder-jump")
        yield Static("", id="coder-menu")
        yield PasteInput(
            placeholder="Ask BEAST · ↓ agent menu · /help · F2 copy · F3 mouse select",
            id="coder-input",
        )

    def on_mount(self) -> None:
        self._apply_responsive_layout(self.size.width, self.size.height)
        self.call_after_refresh(self._focus_input)
        self.set_interval(0.32, self._animate_mascot)

    def on_key(self, event: events.Key) -> None:
        """Recover typing if a mobile SSH terminal leaves focus on a Static widget.

        Normal Input key handling is untouched. This only catches printable
        keys when Textual has unexpectedly lost editor focus.
        """
        if not self.is_mounted:
            return
        if self._menu_kind == "agents" and not self._streaming:
            if event.key in {"up", "down"}:
                self._move_menu(-1 if event.key == "up" else 1)
                event.stop()
                event.prevent_default()
                return
            if event.key in {"enter", "space"}:
                self.call_later(self._choose_menu)
                event.stop()
                event.prevent_default()
                return
            if event.key == "escape":
                self.close_menu()
                event.stop()
                event.prevent_default()
                return
            if event.character and event.character.isprintable():
                # Typing dismisses the menu and falls through to the editor.
                self.close_menu()
        # During streaming, allow scrolling and menu keys but block typing.
        if self._streaming:
            if self._menu_kind == "agents":
                if event.key in {"up", "down"}:
                    self._move_menu(-1 if event.key == "up" else 1)
                    event.stop()
                    event.prevent_default()
                    return
                if event.key in {"enter", "space"}:
                    self.call_later(self._choose_menu)
                    event.stop()
                    event.prevent_default()
                    return
                if event.key == "escape":
                    self.close_menu()
                    event.stop()
                    event.prevent_default()
                    return
            return
        editor = self.query_one("#coder-input", Input)
        if self.focused is editor and event.key == "down" and not editor.value.strip():
            self.open_agent_menu()
            event.stop()
            event.prevent_default()
            return
        if self.focused is editor:
            return
        if event.character and event.character.isprintable() and not event.key.startswith(("ctrl+", "alt+")):
            editor.focus()
            editor.insert_text_at_cursor(event.character)
            event.stop()
            event.prevent_default()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive_layout(event.size.width, event.size.height)

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        """Apply the mobile-first layout, including short keyboard viewports."""
        compact = width < self.COMPACT_MIN_WIDTH or height < self.COMPACT_MIN_HEIGHT
        tiny = width < 55
        # On launch the welcome branding is always present. Once a conversation
        # is under way, a keyboard-short viewport gives those rows back to the
        # transcript and restores the panel as soon as space returns.
        branding_hidden = (
            not self._welcome_active and height < self.BRANDING_MIN_CONTENT_HEIGHT
        )
        self._compact_layout = compact
        self._branding_compact = width < 78 or height < 20
        if tiny:
            self._mascot_cells, self._mascot_rows = max(16, width - 13), 5
        elif compact:
            self._mascot_cells, self._mascot_rows = min(30, max(20, width // 2)), 8
        else:
            self._mascot_cells, self._mascot_rows = 34, 14
        if not self.is_mounted:
            return
        self.screen.set_class(compact, "compact")
        self.screen.set_class(tiny, "tiny")
        self.screen.set_class(self._branding_compact, "branding-compact")
        self.screen.set_class(bool(self.tool_entries or self._actions), "has-tools")
        self.screen.set_class(bool(self._actions), "action-timeline")
        self.screen.set_class(self.beastie_expanded, "beastie-expanded")
        self._sync_branding()
        self._sync()
        # Use the Resize event's dimensions; self.size may still contain the
        # previous terminal size while that event is being dispatched.
        self.screen.set_class(branding_hidden, "branding-hidden")
        self.call_after_refresh(self._focus_input)
        self.refresh(layout=True)

    def _focus_input(self) -> None:
        """Keep the editor as the keyboard owner, including after resizes."""
        if self.is_mounted:
            self.query_one("#coder-input", Input).focus()

    def _sync_branding(self) -> None:
        if not self.is_mounted:
            return
        compact = self._compact_layout or self._branding_compact
        self.query_one("#coder-wordmark", Static).update(
            beast_wordmark(compact=compact, frame=self._mascot_frame)
        )
        self._update_pet()
        self.query_one("#coder-mascot", Static).update("")

    def _pet_frame_path(self) -> Path | None:
        if not _PET_FRAME_PATHS:
            return None
        order = _PET_FRAME_ORDER.get(self.mascot_state, _PET_FRAME_ORDER["idle"])
        valid = tuple(index for index in order if index < len(_PET_FRAME_PATHS)) or (0,)
        return _PET_FRAME_PATHS[valid[self._mascot_frame % len(valid)]]

    def _update_pet(self) -> None:
        if not self.is_mounted:
            return
        pet = self.query_one("#coder-pet")
        if TerminalImage is not None and isinstance(pet, TerminalImage):
            frame = self._pet_frame_path()
            if frame is not None:
                pet.image = frame
        elif isinstance(pet, Static):
            pet.update(pet_sprite(self.mascot_state, self._mascot_frame))

    async def on_unmount(self) -> None:
        # Stop waiting on in-flight turn POSTs before the HTTP client closes, so
        # their recovery path never runs against a closed client. The gateway
        # finishes the turn on its own; /status shows it after reopening.
        for task in list(getattr(self, "_turn_tasks", ())):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
        await self.runtime.aclose()

    @property
    def _turn_tasks(self) -> set:
        tasks = self.__dict__.get("_beast_turn_tasks")
        if tasks is None:
            tasks = self.__dict__["_beast_turn_tasks"] = set()
        return tasks

    def _observe_turn_task(self, task: "asyncio.Task[Any]") -> None:
        """Always retrieve a turn task's outcome (no 'Task exception was never retrieved')."""
        self._turn_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()  # marks it retrieved
        if error is None:
            return

        def report_if_unhandled() -> None:
            handled = self.__dict__.setdefault("_beast_handled_turns", set())
            if id(task) in handled:
                handled.discard(id(task))
                return
            try:
                if self.is_running:
                    self._append("system", f"BEAST turn request ended: {error}", persist=False)
            except Exception:
                pass

        try:
            asyncio.get_running_loop().call_later(1.0, report_if_unhandled)
        except RuntimeError:
            pass

    def _conversation_for_run(self, prompt: str) -> list[dict[str, str]]:
        """User/assistant history of this session, without the prompt being sent now."""
        rows = [
            {"role": str(e.get("role") or ""), "content": str(e.get("content") or "")}
            for e in self.transcript_entries
            if isinstance(e, dict) and e.get("role") in {"user", "assistant"}
            and str(e.get("content") or "").strip()
            and is_history_row(e)  # no streaming rows or per-turn progress lines
        ]
        if rows and rows[-1]["role"] == "user" and rows[-1]["content"].strip() == str(prompt).strip():
            rows.pop()
        return rows[-8:]

    def _working_clock(self) -> str:
        if not self._work_started_at:
            return ""
        elapsed = max(0, int(time.monotonic() - self._work_started_at))
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

    def _status_badge(self) -> Text:
        dot = "●" if self._status_dot % 2 == 0 else "○"
        style = f"bold {BEAST_ACID}" if self._streaming else f"bold {BEAST_GREEN}"
        text = Text()
        if self._streaming:
            text.append(f"{dot} WORKING {self._working_clock()}", style=style)
        else:
            text.append(f"{dot} {self.mascot_state.upper()}", style=style)
        return text

    def _identity_text(self) -> Text:
        text = Text()
        if self._compact_layout:
            text.append("BEAST ", style=f"bold {BEAST_GREEN}")
            text.append_text(self._status_badge())
            width = int(getattr(self.size, "width", 0) or 0)
            if width >= 50:
                text.append("  ·  ", style=BEAST_MUTED)
                text.append(self.settings.provider, style=BEAST_ACID)
                text.append("/", style=BEAST_MUTED)
                text.append(self.settings.model, style=BEAST_WARN)
            if not self._follow_output:
                text.append("  ·  OUTPUT PAUSED", style=f"bold {BEAST_WARN}")
            elif width >= 72:
                text.append("  ·  ", style=BEAST_MUTED)
                text.append(self.settings.workspace.name, style=BEAST_GREEN)
            return text
        text.append("WORKSPACE ", style=f"bold {BEAST_MUTED}")
        text.append(str(self.settings.workspace), style=f"bold {BEAST_GREEN}")
        text.append("   PROVIDER ", style=f"bold {BEAST_MUTED}")
        text.append(self.settings.provider, style=f"bold {BEAST_ACID}")
        text.append("   MODEL ", style=f"bold {BEAST_MUTED}")
        text.append(self.settings.model, style=f"bold {BEAST_WARN}")
        text.append("   AGENT ", style=f"bold {BEAST_MUTED}")
        text.append(self._pending_agent, style=f"bold {BEAST_ACID}")
        text.append("   AUTOPILOT ", style=f"bold {BEAST_MUTED}")
        text.append("ON" if self.settings.auto_mode else "OFF",
                    style=f"bold {BEAST_GREEN if self.settings.auto_mode else BEAST_MUTED}")
        text.append("   ", style=BEAST_MUTED)
        text.append_text(self._status_badge())
        if self.diff_bundle.get("diff"):
            added = int(self.diff_bundle.get("added") or 0)
            removed = int(self.diff_bundle.get("removed") or 0)
            text.append(f"   DIFF +{added} −{removed}", style=f"bold {BEAST_GREEN}")
        if not self._follow_output:
            text.append("   OUTPUT PAUSED · F6 to jump to latest", style=f"bold {BEAST_WARN}")
        return text

    def _transcript_text(self) -> Text:
        text = Text()
        if not self.transcript_entries:
            text.append_text(beast_wordmark())
            text.append("\n\n")
            text.append("BEAST Coder ready. Plain prompts run the autonomous coding loop.\n", style=BEAST_MUTED)
            text.append("Type a coding request or /help. Use /ask for a read-only question.", style=BEAST_GREEN)
            return text
        styles = {
            "user": f"bold {BEAST_ACID}",
            "assistant": BEAST_TEXT,
            "system": BEAST_MUTED,
            "error": "bold #D35E68",
        }
        labels = {"user": "YOU", "assistant": "BEAST", "system": "SYSTEM", "error": "ERROR"}
        entries = [
            item for item in self.transcript_entries
            if not (self._action_summary and (item.get("metadata") or {}).get("action_summary")
                    and (item.get("metadata") or {}).get("run_id") == self.settings.last_run_id)
        ]
        for index, item in enumerate(entries):
            role = str(item.get("role") or "system")
            text.append(f"{labels.get(role, role.upper())}> ", style=styles.get(role, BEAST_MUTED))
            content = str(item.get("content") or "")
            if role == "assistant" and self._append_decision(text, content):
                pass
            elif role == "system" and "APPROVAL" in content.upper():
                text.append(content, style=f"bold {BEAST_WARN}")
            elif role == "system" and content.startswith("Turn complete"):
                text.append(content, style=BEAST_GREEN)
            else:
                text.append(content, style=styles.get(role, BEAST_TEXT))
            if index < len(entries) - 1:
                text.append("\n\n")
        return text

    @staticmethod
    def _is_control_packet(content: str) -> bool:
        """Detect a planner decision JSON so it is never rendered as prose."""
        stripped = str(content or "").strip()
        return stripped.startswith("{") and '"decision_type"' in stripped

    @staticmethod
    def _append_decision(output: Text, content: str) -> bool:
        """Render one or more concatenated planner decisions without repeats."""
        source = content.strip()
        if not source.startswith("{"):
            return False
        decoder = json.JSONDecoder()
        cursor = 0
        decisions: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            while cursor < len(source):
                value, cursor = decoder.raw_decode(source, cursor)
                while cursor < len(source) and source[cursor].isspace():
                    cursor += 1
                if isinstance(value, dict) and "decision_type" in value:
                    signature = json.dumps(value, sort_keys=True, default=str)
                    if signature not in seen:
                        seen.add(signature)
                        decisions.append(value)
        except (json.JSONDecodeError, TypeError):
            return False
        if not decisions:
            return False
        for decision_index, decision in enumerate(decisions):
            if decision_index:
                output.append("\n")
            output.append(
                str(decision.get("decision_type") or "decision").upper(),
                style=f"bold {BEAST_WARN}",
            )
            tool_id = decision.get("tool_id")
            if tool_id:
                output.append("  ")
                output.append(str(tool_id), style=f"bold {BEAST_ACID}")
            arguments = decision.get("arguments")
            if isinstance(arguments, dict) and arguments:
                output.append("\n       ", style=BEAST_MUTED)
                for index, (key, value) in enumerate(arguments.items()):
                    if index:
                        output.append("  ", style=BEAST_MUTED)
                    output.append(f"{key}=", style=BEAST_MUTED)
                    output.append(json.dumps(value, default=str), style=BEAST_TEXT)
            summary = str(decision.get("summary") or "").strip()
            if summary:
                output.append("\n       ", style=BEAST_MUTED)
                output.append(summary, style=BEAST_TEXT)
        return True

    def _approval_text(self) -> Text:
        text = Text()
        if not self.pending_approvals:
            return text
        item = self.pending_approvals[0]
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        text.append("APPROVAL REQUIRED\n", style=f"bold {BEAST_WARN}")
        text.append(str(request.get("tool_id") or "governed action"), style=f"bold {BEAST_ACID}")
        risk = str(request.get("risk_class") or "governed")
        text.append(f"  ·  risk={risk}\n", style=BEAST_MUTED)
        summary = str(request.get("summary") or "Review and approve this action")
        text.append(summary + "\n", style=BEAST_TEXT)
        text.append("Tap to approve and continue", style=f"bold {BEAST_GREEN}")
        if len(self.pending_approvals) > 1:
            text.append(f"  ·  {len(self.pending_approvals) - 1} more pending", style=BEAST_MUTED)
        return text

    @staticmethod
    def _changed_lines(patch: str) -> list[tuple[int, str, str]]:
        lines: list[tuple[int, str, str]] = []
        old = new = None
        for line in patch.splitlines():
            if line.startswith(("diff --git ", "--- ", "+++ ")):
                old = new = None
                continue
            header = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if header:
                old, new = map(int, header.groups())
            elif old is not None and new is not None:
                if line.startswith("+"):
                    lines.append((new, "+", line[1:]))
                    new += 1
                elif line.startswith("-"):
                    lines.append((old, "-", line[1:]))
                    old += 1
                elif line.startswith(" "):
                    old += 1
                    new += 1
        return lines

    def _actions_text(self) -> Text:
        text = Text("ACTIONS\n", style=f"bold {BEAST_ACID}")
        for action in self._actions[-24:]:
            tool = action.get("tool_id") or ""
            details = action.get("details") or {}
            args = action.get("arguments") or {}
            path = str(details.get("path") or args.get("path") or "")
            status = action.get("status") or "thinking"
            if not tool:
                continue
            patch = details.get("action_diff") or ""
            changed = self._changed_lines(patch) if status == "completed" else []
            code = details.get("returncode")
            title = {
                "workspace.read_range": "Read", "worktree.read_file": "Read",
                "worktree.replace_exact": "Edited" if status == "completed" else "Edit",
                "worktree.write_file": "Created" if status == "completed" else "Write",
                "worktree.bind": "Bound worktree" if status == "completed" else "Bind worktree",
                "workspace.search_text": "Searched", "worktree.search_text": "Searched",
                "worktree.verify": "Verified" if status == "completed" else "Verifying",
                "worktree.diff": "Inspected diff",
            }.get(tool, tool)
            if status == "failed" and code is not None:
                title = "Verification failed" if tool == "worktree.verify" else "Command failed"
            color = BEAST_GREEN if status == "completed" else "#FF8A93" if status in {"failed", "rejected"} else BEAST_WARN
            text.append(f"• {title}", style=f"bold {color}")
            subject = path or str(details.get("subject") or "")
            if not subject and isinstance(args.get("command"), list):
                subject = " ".join(str(value) for value in args["command"])
            if subject:
                text.append(f"  {subject[:125]}", style=BEAST_TEXT)
            if changed:
                added = sum(mark == "+" for _, mark, _ in changed)
                text.append(f"  (+{added} −{len(changed) - added})", style=BEAST_MUTED)
            if code is not None:
                text.append(f"  ·  exit {code}", style=color)
            elif status != "completed":
                text.append(f"  ·  {status}", style=color)
            text.append("\n")
            for line_no, mark, body in changed[:6]:
                style = f"{BEAST_GREEN} on #04170F" if mark == "+" else "#FFB3B8 on #1B0508"
                text.append(f"  {line_no:>4} {mark}{body[:160]}\n", style=style)
            if len(changed) > 6:
                text.append(f"    + {len(changed) - 6} preview lines · F7 for full diff\n", style=BEAST_MUTED)
            if status in {"failed", "rejected"} and action.get("error"):
                text.append("    " + str(action["error"]).splitlines()[0][:180] + "\n", style=color)
            reason = action.get("thinking") or ""
            if reason:
                opened = action["id"] in self._expanded_actions
                text.append("    ▾ Thinking\n" if opened else "    ▸ Thinking\n", style=Style(
                    color=BEAST_MUTED, meta={"@click": f"app.toggle_action_reasoning({action['id']})"},
                ))
                if opened:
                    preview = " ".join(reason.split())
                    text.append("    " + preview[:230] + ("…" if len(preview) > 230 else "") + "\n",
                                style=BEAST_MUTED)
        if self._action_summary:
            text.append("\n" + self._action_summary + "\n", style=BEAST_TEXT)
        return text

    def action_toggle_action_reasoning(self, action_id: int) -> None:
        was_open = action_id in self._expanded_actions
        self._expanded_actions.clear()
        if not was_open:
            self._expanded_actions.add(action_id)
        if self.is_mounted:
            self.query_one("#coder-inline-tools", ToolEventPanel).update(self._actions_text())

    def _reset_actions(self) -> None:
        self._actions.clear()
        self._expanded_actions.clear()
        self._current_action = None
        self.thinking_bundle = ""
        self._show_cumulative_diff = True
        self._action_summary = ""

    def _begin_action(self) -> None:
        self._action_count += 1
        self.thinking_bundle = ""
        self._current_action = {"id": self._action_count, "status": "thinking"}
        self._actions.append(self._current_action)
        if len(self._actions) > 80:
            removed = self._actions.pop(0)
            self._expanded_actions.discard(removed["id"])

    def _update_action(self, row: dict[str, Any]) -> None:
        action = self._current_action
        if action is None:
            return
        action["tool_id"] = row.get("tool_id")
        action["status"] = row.get("status") or "running"
        if row["kind"] == "tool_call":
            action["arguments"] = row["details"].get("arguments") or {}
        else:
            action["details"] = {k: row["details"][k] for k in ("path", "action_diff", "returncode")
                                 if k in row["details"]}
            if row["tool_id"] not in {"worktree.replace_exact", "worktree.write_file"}:
                action["details"].pop("action_diff", None)
            action["receipt"] = row.get("receipt") or {}
            action["error"] = row.get("text") if row.get("status") in {"failed", "rejected"} else ""
        if self.thinking_bundle:
            action["thinking"] = self.thinking_bundle
            self.thinking_bundle = ""

    def _paint_thinking(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if self.is_mounted and (force or now - self._last_thinking_paint >= 0.12):
            self._last_thinking_paint = now
            self.screen.set_class(bool(self.thinking_bundle), "has-thinking")
            self.query_one("#coder-thinking", ThinkingPanel).update(self._thinking_text())

    def _tools_text(self) -> Text:
        text = Text("TOOL CALLS + RECEIPTS\n", style=f"bold {BEAST_ACID}")
        text.append("─" * 30 + "\n", style=BEAST_BORDER)
        if not self.tool_entries:
            text.append("No runtime tool events yet.", style=BEAST_MUTED)
            return text
        for item in self.tool_entries[-40:]:
            success = bool(item.get("success"))
            executed = bool(item.get("executed"))
            marker = "✓" if success else ("×" if executed else "◇")
            style = BEAST_GREEN if success else ("#D35E68" if executed else BEAST_WARN)
            text.append(f"{marker} {item.get('tool_id') or item.get('kind')}\n", style=f"bold {style}")
            text.append(f"  {item.get('text') or item.get('status') or ''}\n", style=BEAST_TEXT)
            receipt = item.get("receipt") if isinstance(item.get("receipt"), dict) else {}
            if receipt:
                receipt_id = receipt.get("observation_id") or receipt.get("receipt_id") or receipt.get("request_id")
                digest = receipt.get("evidence_digest") or receipt.get("receipt_digest")
                if receipt_id:
                    text.append(f"  receipt {receipt_id}\n", style=BEAST_MUTED)
                if digest:
                    text.append(f"  digest  {str(digest)[:20]}…\n", style=BEAST_MUTED)
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            if details and self.details_expanded:
                compact = json.dumps(details, sort_keys=True, default=str)
                text.append(f"  {compact[:1800]}\n", style=BEAST_MUTED)
            elif details:
                text.append("  ▸ Tap or /expand for event details\n", style=BEAST_MUTED)
            text.append("\n")
        return text

    @staticmethod
    def _patch_stats(patch: str) -> tuple[int, int]:
        added = removed = 0
        for line in patch.splitlines():
            if line.startswith(("+++", "---")):
                continue
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1
        return added, removed

    def _merge_diff(self, details: dict[str, Any], *, status: str = "ready") -> None:
        patch = str(details.get("diff") or "")
        if not patch.strip():
            return
        added, removed = self._patch_stats(patch)
        files = details.get("files") if isinstance(details.get("files"), list) else []
        self.diff_bundle = {
            "diff": patch,
            "files": [str(item) for item in files],
            "added": int(details.get("added") or added),
            "removed": int(details.get("removed") or removed),
            "status": status,
            "truncated": bool(details.get("truncated")),
        }

    def _record_tool_patch(self, tool: str, details: dict[str, Any]) -> None:
        patch = details.get("diff")
        if not isinstance(patch, str):
            return
        if tool == "worktree.diff":
            self._live_diffs.clear()
            for piece in re.split(r"(?m)(?=^diff --git )", patch):
                match = re.search(r"(?m)^\+\+\+ b/(.+?)(?:\t.*)?$", piece)
                if not match:
                    match = re.search(r"(?m)^--- a/(.+?)(?:\t.*)?$", piece)
                if match:
                    self._live_diffs[match[1]] = piece
            if patch.strip():
                self._merge_diff({**details, "files": details.get("files") or list(self._live_diffs)}, status="editing")
            else:
                self.diff_bundle = {}
        elif tool in {"worktree.replace_exact", "worktree.write_file"} and details.get("path"):
            self._merge_live_diff(str(details["path"]), details)

    def _merge_live_diff(self, path: str, details: dict[str, Any]) -> None:
        """Accumulate per-edit patches so the diff grows while the agent works."""
        patch = str(details.get("diff") or "")
        if not patch.strip():
            return
        key = path or f"change-{len(self._live_diffs) + 1}"
        self._live_diffs[key] = patch
        joined = "\n".join(patch for patch in self._live_diffs.values())
        added, removed = self._patch_stats(joined)
        self.diff_bundle = {
            "diff": joined,
            "files": list(self._live_diffs),
            "added": added,
            "removed": removed,
            "status": "editing",
            "truncated": False,
        }

    def _diff_text(self) -> Text:
        text = Text()
        if not self.diff_bundle.get("diff"):
            text.append("LIVE DIFF\n", style=f"bold {BEAST_MUTED}")
            text.append("No edits yet. Every change appears here in red/green as the agent works.",
                        style=BEAST_MUTED)
            return text
        status = str(self.diff_bundle.get("status") or "editing").upper()
        added = int(self.diff_bundle.get("added") or 0)
        removed = int(self.diff_bundle.get("removed") or 0)
        files = [str(item) for item in self.diff_bundle.get("files") or []]
        status_style = (
            f"bold {BEAST_GREEN}" if status in {"READY", "APPLIED"} else f"bold {BEAST_WARN}"
        )
        text.append("LIVE DIFF  ", style=f"bold {BEAST_ACID}")
        text.append(status, style=status_style)
        text.append(f"  ·  {len(files)} file(s)  ", style=BEAST_MUTED)
        text.append(f"+{added}", style=f"bold {BEAST_GREEN}")
        text.append(" ", style=BEAST_MUTED)
        text.append(f"−{removed}", style="bold #FF8A93")
        if files:
            text.append("\n")
            text.append("  ".join(files[:6]) + (" …" if len(files) > 6 else ""), style=BEAST_MUTED)
        note = str(self.diff_bundle.get("note") or "")
        if note and status in {"APPLIED", "BLOCKED"}:
            text.append("\n" + note[:160], style=f"bold {BEAST_GREEN if status == 'APPLIED' else BEAST_WARN}")
        text.append("\n" + "─" * 40 + "\n", style=BEAST_BORDER)
        patch = str(self.diff_bundle.get("diff") or "")
        lines = patch.splitlines()
        limit = 600 if self.diff_expanded else 36
        for line in lines[:limit]:
            if line.startswith(("diff --git", "index ", "new file mode", "deleted file mode")):
                text.append(line + "\n", style=BEAST_MUTED)
            elif line.startswith(("+++", "---")):
                text.append(line + "\n", style=f"bold {BEAST_MUTED}")
            elif line.startswith("@@"):
                text.append(line + "\n", style=f"bold {BEAST_INFO}")
            elif line.startswith("+"):
                text.append(line + "\n", style=f"{BEAST_GREEN} on #04170F")
            elif line.startswith("-"):
                text.append(line + "\n", style=f"#FFB3B8 on #1B0508")
            else:
                text.append(line + "\n", style=BEAST_TEXT)
        if len(lines) > limit:
            text.append(
                f"… {len(lines) - limit} more lines · /diff or F7 to "
                + ("collapse" if self.diff_expanded else "expand") + "\n",
                style=f"bold {BEAST_WARN}",
            )
        elif not self.diff_expanded:
            text.append("… /diff or F7 to expand\n", style=f"bold {BEAST_WARN}")
        return text

    async def toggle_diff_expanded(self) -> None:
        self.diff_expanded = not self.diff_expanded
        if self._actions:
            self._show_cumulative_diff = not self._show_cumulative_diff
            self.diff_expanded = self._show_cumulative_diff
        self._sync()
        if self.diff_expanded and self.is_mounted and not self._actions:
            self.call_after_refresh(self._scroll_transcript_end)

    def action_toggle_diff(self) -> None:
        self.call_later(self.toggle_diff_expanded)

    def _thinking_text(self) -> Text:
        text = Text()
        if not self.thinking_bundle:
            text.append("THINKING\n", style=f"bold {BEAST_MUTED}")
            text.append("Model reasoning appears here while it plans its next move.",
                        style=BEAST_MUTED)
            return text
        dot = "◐" if self._status_dot % 2 == 0 else "◑"
        if self._actions:
            text.append(f"THINKING  {dot} · current action\n", style=f"bold {BEAST_WARN}")
            preview = " ".join(self.thinking_bundle.split())
            limit = 180 if self.thinking_expanded else 85
            text.append(preview[:limit].strip() + ("…" if len(preview) > limit else ""), style=BEAST_WARN)
            return text
        text.append(f"THINKING  {dot}\n", style=f"bold {BEAST_WARN}")
        text.append("▸ Tap to show reasoning · ", style=BEAST_MUTED)
        text.append(str(self._status_dot), style=BEAST_MUTED)
        text.append("\n")
        limit = 2000 if self.thinking_expanded else 120
        visible = self.thinking_bundle[:limit]
        text.append(visible, style=BEAST_WARN)
        if len(self.thinking_bundle) > limit:
            text.append(
                f"\n… {len(self.thinking_bundle) - limit} more characters · tap to expand\n",
                style=f"bold {BEAST_WARN}",
            )
        return text

    def toggle_thinking_expanded(self) -> None:
        if self._actions:
            if self.thinking_bundle:
                self.thinking_expanded = not self.thinking_expanded
                self._paint_thinking(force=True)
            else:
                latest = next((action for action in reversed(self._actions) if action.get("thinking")), None)
                if latest:
                    self.action_toggle_action_reasoning(latest["id"])
            return
        self.thinking_expanded = not self.thinking_expanded
        self._sync()

    def action_toggle_thinking(self) -> None:
        self.call_later(self.toggle_thinking_expanded)

    def _ide_compat_text(self) -> Text:
        text = Text()
        if not self.ide_compat:
            text.append("IDE COMPATIBILITY\n", style=f"bold {BEAST_MUTED}")
            text.append("Run /ide to probe language servers, notebooks, SSH, containers, and extensions.",
                        style=BEAST_MUTED)
            return text
        summary = self.ide_compat.get("summary") or {}
        available = int(summary.get("available") or 0)
        total = int(summary.get("total") or 0)
        coverage = int(summary.get("coverage") or 0)
        dot = "●" if self._status_dot % 2 == 0 else "○"
        text.append(f"IDE COMPAT  {dot}  {available}/{total}  ({coverage}%)\n", style=f"bold {BEAST_ACID}")
        text.append(f"Target: {self.execution_target}", style=BEAST_MUTED)
        text.append("\n")

        def section(title: str, items: list[dict[str, Any]]) -> None:
            if not items:
                return
            text.append(f"  {title}\n", style=f"bold {BEAST_GREEN}")
            for item in items[:6]:
                label = str(item.get("label") or item.get("id") or "item")
                avail = bool(item.get("available"))
                detail = str(item.get("detail") or "")
                style = BEAST_GREEN if avail else BEAST_MUTED
                text.append(f"    {'✓' if avail else '✗'} {label}", style=style)
                if detail and avail:
                    text.append(f"  ·  {detail[:60]}", style=BEAST_MUTED)
                text.append("\n")
            if len(items) > 6:
                text.append(f"    … {len(items) - 6} more\n", style=BEAST_MUTED)

        section("Languages", self.ide_compat.get("languages") or [])
        section("Debuggers", self.ide_compat.get("debug") or [])
        section("Notebooks", self.ide_compat.get("notebooks") or [])
        section("Remote", self.ide_compat.get("remote") or [])

        ext_host = self.ide_compat.get("extensionHost") or {}
        if ext_host:
            status = str(ext_host.get("status") or "unknown")
            text.append(f"  Extension host: {status}", style=BEAST_MUTED)
            text.append("\n")

        limit = 2000 if self.ide_compat_expanded else 120
        visible = json.dumps(self.ide_compat, sort_keys=True, default=str)[:limit]
        text.append(visible, style=BEAST_MUTED)
        raw = json.dumps(self.ide_compat, sort_keys=True, default=str)
        if len(raw) > limit:
            text.append(
                f"\n… {len(raw) - limit} more characters · tap to expand\n",
                style=f"bold {BEAST_MUTED}",
            )
        return text

    def toggle_ide_compat_expanded(self) -> None:
        self.ide_compat_expanded = not self.ide_compat_expanded
        self._sync()

    def action_toggle_ide_compat(self) -> None:
        self.call_later(self.toggle_ide_compat_expanded)

    def _crystal_lattice_text(self) -> Text:
        text = Text()
        if not self.crystal_lattice:
            text.append("CRYSTAL / LATTICE\n", style=f"bold {BEAST_MUTED}")
            text.append("Crystal reuse decisions and lattice promotions appear here.",
                        style=BEAST_MUTED)
            return text
        dot = "●" if self._status_dot % 2 == 0 else "○"
        decisions = self.crystal_lattice.get("decisions") or []
        promotions = self.crystal_lattice.get("promotions") or []
        reductions = self.crystal_lattice.get("reductions") or []
        autopromo = self.crystal_lattice.get("autopromotion") or {}
        text.append(f"CRYSTAL/LATTICE  {dot}\n", style=f"bold {BEAST_WARN}")
        text.append(f"Decisions: {len(decisions)}  ·  Promotions: {len(promotions)}  ·  Reductions: {len(reductions)}\n",
                    style=BEAST_MUTED)

        def section(title: str, items: list[dict[str, Any]]) -> None:
            if not items:
                return
            text.append(f"  {title}\n", style=f"bold {BEAST_GREEN}")
            for item in items[:5]:
                action = str(item.get("action") or item.get("kind") or "item")
                conf = item.get("confidence")
                conf_str = f" ({int(conf * 100)}%)" if isinstance(conf, (int, float)) else ""
                item_style = BEAST_GREEN if item.get("success", True) else "#D35E68"
                text.append(f"    • {action}{conf_str}", style=item_style)
                reason = str(item.get("reason") or "")
                if reason:
                    text.append(f"      {reason[:70]}\n", style=BEAST_MUTED)
                crystal_id = str(item.get("crystal_id") or "")
                if crystal_id:
                    text.append(f"      {crystal_id}\n", style=BEAST_ACID)
                successes = int(item.get("heldout_successes") or 0)
                attempts = int(item.get("heldout_attempts") or 0)
                if attempts:
                    admitted = "admitted" if item.get("lattice_admitted") else "not admitted"
                    text.append(f"      held-out {successes}/{attempts} · lattice {admitted}\n", style=BEAST_MUTED)
                text.append("\n")
            if len(items) > 5:
                text.append(f"    … {len(items) - 5} more\n", style=BEAST_MUTED)

        section("Decisions", decisions)
        section("Promotions", promotions)
        section("Reductions", reductions)

        if autopromo:
            text.append(f"  Autopromotion: scanned={autopromo.get('scanned', 0)}  "
                        f"promoted={autopromo.get('promoted_count', 0)}  "
                        f"rejected={autopromo.get('rejected_count', 0)}\n",
                        style=BEAST_MUTED)

        limit = 2000 if self.crystal_lattice_expanded else 120
        visible = json.dumps(self.crystal_lattice, sort_keys=True, default=str)[:limit]
        text.append(visible, style=BEAST_MUTED)
        raw = json.dumps(self.crystal_lattice, sort_keys=True, default=str)
        if len(raw) > limit:
            text.append(
                f"\n… {len(raw) - limit} more characters · tap to expand\n",
                style=f"bold {BEAST_MUTED}",
            )
        return text

    def toggle_crystal_lattice_expanded(self) -> None:
        self.crystal_lattice_expanded = not self.crystal_lattice_expanded
        self._sync()

    def action_toggle_crystal_lattice(self) -> None:
        self.call_later(self.toggle_crystal_lattice_expanded)

    def _append_completion_summary(self, run_id: str, run_state: str, advisory: str, receipts: list[str]) -> None:
        """Render a rich end-of-task summary banner after a completed agent run."""
        status = str(self.diff_bundle.get("status") or "").upper()
        added = int(self.diff_bundle.get("added") or 0)
        removed = int(self.diff_bundle.get("removed") or 0)
        files = [str(item) for item in self.diff_bundle.get("files") or []]
        lines = []
        if status in {"READY", "APPLIED"}:
            lines.append(f"Task complete · {run_state}")
            if files:
                lines.append(f"Files: {', '.join(files[:6])}")
            if added or removed:
                lines.append(f"Changes: +{added} −{removed}")
            if status == "APPLIED":
                lines.append("Applied to your workspace.")
            else:
                lines.append("Left in the isolated worktree (review only).")
        elif advisory:
            lines.append(advisory)
        if lines:
            self._append("system", "COMPLETION · " + "  ·  ".join(lines), persist=False)

    def action_jump_latest(self) -> None:
        self._follow_output = True
        if self.is_mounted:
            self.screen.remove_class("show-jump")
            self.query_one("#coder-identity", Static).update(self._identity_text())
        self._scroll_transcript_end()

    # --- agent / swarm menu -------------------------------------------------

    _AGENT_MENU: tuple[dict[str, str], ...] = (
        {"id": "agent", "label": "AGENT", "detail": "autonomous coding · verifies and applies edits"},
        {"id": "plan", "label": "PLAN", "detail": "read-only analysis · no files changed"},
        {"id": "review", "label": "REVIEW", "detail": "source-line review of an attached file"},
        {"id": "swarm", "label": "SWARM", "detail": "real swarm role advice and optional local edit recovery"},
    )

    def open_agent_menu(self) -> None:
        self._menu_kind = "agents"
        self._menu_items = [dict(item) for item in self._AGENT_MENU]
        self._menu_index = next(
            (index for index, item in enumerate(self._menu_items)
             if item["label"] == self._pending_agent),
            0,
        )
        self._render_menu()

    def _open_sessions_menu(self, sessions: list[dict[str, Any]]) -> None:
        if not sessions:
            return
        self._menu_kind = "sessions"
        self._menu_items = [
            {
                "id": str(item.get("session_id") or ""),
                "label": str(item.get("title") or item.get("session_id") or "session")[:48],
                "detail": f"{item.get('created') or ''} · {item.get('messages') or 0} messages",
            }
            for item in sessions[:12]
        ]
        self._menu_index = 0
        self._render_menu()

    def _render_menu(self) -> None:
        if not self.is_mounted:
            return
        text = Text()
        title = "SELECT AGENT" if self._menu_kind == "agents" else "SESSIONS"
        text.append(f"{title}  ·  ↑/↓ move · Enter select · Esc close\n", style=f"bold {BEAST_ACID}")
        for index, item in enumerate(self._menu_items):
            selected = index == self._menu_index
            marker = "▸ " if selected else "  "
            style = f"bold {BEAST_DEEP} on {BEAST_ACID}" if selected else f"bold {BEAST_TEXT}"
            label = str(item.get("label") or "")
            text.append(marker + label, style=style)
            detail = str(item.get("detail") or "")
            if detail:
                text.append("  " + detail, style=BEAST_MUTED if not selected else f"{BEAST_DEEP} on {BEAST_ACID}")
            text.append("\n")
        self.query_one("#coder-menu", Static).update(text)
        self.screen.set_class(True, "menu-open")
        self.refresh(layout=True)

    def close_menu(self) -> None:
        self._menu_kind = ""
        self._menu_items = []
        self._menu_index = 0
        if self.is_mounted:
            self.screen.remove_class("menu-open")
            self.query_one("#coder-menu", Static).update("")
        with suppress(Exception):
            self.query_one("#coder-input", Input).focus()

    def action_close_menu(self) -> None:
        if self._menu_kind:
            self.close_menu()

    def action_menu_down(self) -> None:
        if self._menu_kind:
            self._move_menu(1)
            return
        if self._streaming:
            return
        try:
            editor = self.query_one("#coder-input", Input)
        except Exception:
            return
        if self.focused is editor and not editor.value.strip():
            self.open_agent_menu()

    def action_menu_up(self) -> None:
        if self._menu_kind:
            self._move_menu(-1)

    def _move_menu(self, delta: int) -> None:
        if not self._menu_items:
            return
        self._menu_index = (self._menu_index + delta) % len(self._menu_items)
        self._render_menu()

    async def _choose_menu(self) -> None:
        if not self._menu_items:
            return
        item = self._menu_items[self._menu_index]
        kind = self._menu_kind
        self.close_menu()
        if kind == "sessions":
            self._resume_session(item.get("id") or "")
            return
        identity = item.get("id") or "agent"
        self._pending_agent = item.get("label") or "AGENT"
        self._pending_prefix = ""
        if identity == "plan":
            self._pending_mode = "ask"
        elif identity == "review":
            self._pending_mode = "review"
        elif identity == "swarm":
            self._pending_mode = "agent"
        else:
            self._pending_mode = "agent"
        self.query_one("#coder-input", Input).placeholder = (
            f"{self._pending_agent} · type the task and press Enter"
        )
        self._append(
            "system",
            f"Agent set to {self._pending_agent}. Next prompt runs in {self._pending_mode} mode.",
            persist=False,
        )
        self._sync()

    def _resume_session(self, session_id: str) -> None:
        if not session_id:
            return
        payload = self.store.load_session(session_id)
        if payload is None:
            self._append("error", f"Session not found: {session_id}", persist=False)
            return
        self.transcript_entries = self.store.messages()
        self.tool_entries.clear()
        self._reset_actions()
        self.pending_approvals.clear()
        self.diff_bundle = {}
        self._live_diffs.clear()
        self._welcome_active = not bool(self.transcript_entries)
        self._save_settings(
            session_title=str(payload.get("title") or session_id),
            session_id="",
            last_run_id="",
        )
        self._append("system", f"Resumed session: {payload.get('title') or session_id}", persist=False)
        self._sync()

    def _sync(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#coder-identity", Static).update(self._identity_text())
        self.query_one("#coder-transcript", Static).update(self._transcript_text())
        self.query_one("#coder-approvals", ApprovalPanel).update(self._approval_text())
        show_receipts = bool(self._actions and self.details_expanded)
        self.query_one("#coder-receipts-toggle", Button).label = (
            ("Hide" if show_receipts else "Show") + " tool calls + receipts · F9"
        )
        if show_receipts:
            self.query_one("#coder-tools", Static).update(self._tools_text())
        self.query_one("#coder-inline-tools", ToolEventPanel).update(
            self._actions_text() if self._actions else self._tools_text()
        )
        with suppress(Exception):
            self.query_one("#coder-diff", DiffPanel).update(self._diff_text())
        with suppress(Exception):
            self.query_one("#coder-thinking", ThinkingPanel).update(self._thinking_text())
        with suppress(Exception):
            self.query_one("#coder-ide-compat", IdeCompatPanel).update(self._ide_compat_text())
        with suppress(Exception):
            self.query_one("#coder-crystal-lattice", CrystalLatticePanel).update(self._crystal_lattice_text())
        self.screen.set_class(bool(self.tool_entries or self._actions), "has-tools")
        self.screen.set_class(bool(self._actions), "action-timeline")
        self.screen.set_class(show_receipts, "show-receipts")
        self.screen.set_class(bool(self.pending_approvals), "has-approvals")
        self.screen.set_class(
            bool(self.diff_bundle.get("diff")) and (not self._actions or self._show_cumulative_diff),
            "has-diff",
        )
        self.screen.set_class(bool(self.thinking_bundle), "has-thinking")
        self.screen.set_class(bool(self.ide_compat), "has-ide-compat")
        self.screen.set_class(bool(self.crystal_lattice), "has-crystal-lattice")
        self.screen.set_class(not self._follow_output, "show-jump")
        self.screen.set_class(
            not self._welcome_active
            and self.size.height < self.BRANDING_MIN_CONTENT_HEIGHT,
            "branding-hidden",
        )
        if not self._follow_output:
            return
        # Textual can update Static content before its new wrapped height has
        # been measured. A single scroll_end during that frame uses stale
        # virtual_size and leaves the latest tokens below the viewport.
        with suppress(Exception):
            self.query_one("#coder-transcript", Static).refresh(layout=True)
            self.query_one("#coder-inline-tools", Static).refresh(layout=True)
            self.query_one("#coder-approvals", ApprovalPanel).refresh(layout=True)
            self.query_one("#conversation-scroll", VerticalScroll).refresh(layout=True)
            self.call_after_refresh(self._scroll_transcript_end)
            if not getattr(self, "_follow_scroll_pending", False):
                self._follow_scroll_pending = True
                self.set_timer(0.07, self._scroll_transcript_after_layout)

    def _scroll_transcript_after_layout(self) -> None:
        self._follow_scroll_pending = False
        self._scroll_transcript_end()
        # Wrapped tool receipts can change height a frame later than the
        # transcript. A second follow keeps the current decision visible.
        if self.is_mounted:
            self.set_timer(0.10, self._scroll_transcript_end)

    def _scroll_transcript_end(self) -> None:
        if not self._follow_output:
            return
        with suppress(Exception):
            viewport = self.query_one("#conversation-scroll", VerticalScroll)
            self._auto_scrolling = True
            try:
                viewport.scroll_end(animate=False, force=True)
            finally:
                self._auto_scrolling = False

    def _animate_mascot(self) -> None:
        self._mascot_frame = (self._mascot_frame + 1) % 120
        self._status_dot = (self._status_dot + 1) % 2
        if not self.is_mounted:
            return
        # A final animation tick can overlap widget teardown.
        with suppress(NoMatches):
            self.query_one("#coder-wordmark", Static).update(
                beast_wordmark(
                    compact=self._compact_layout or self._branding_compact,
                    frame=self._mascot_frame,
                )
            )
            self._update_pet()
            self.query_one("#coder-beastie", Static).update(
                sprite_mascot(self.mascot_state, self._mascot_frame)
            )
            # The working clock and pulse repaint independently of the
            # transcript so a long model call still looks alive.
            with suppress(Exception):
                self.query_one("#coder-identity", Static).update(self._identity_text())

    def _set_mascot(self, state: str) -> None:
        if state == "working" and self.mascot_state != "working":
            self._work_started_at = time.monotonic()
        elif state != "working":
            self._work_started_at = None
        self.mascot_state = state
        self._sync()

    def _append(self, role: str, content: str, *, persist: bool = True, metadata: dict[str, Any] | None = None) -> None:
        row = {"role": role, "content": str(content), "metadata": dict(metadata or {})}
        self.transcript_entries.append(row)
        if persist:
            self.store.append(role, str(content), metadata=metadata)
        self._sync()

    def _last_user_prompt(self) -> str | None:
        for entry in reversed(self.transcript_entries):
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            if entry.get("role") == "user" and not metadata.get("command"):
                return str(entry.get("content") or "") or None
        return None

    def _last_answer_text(self) -> str:
        for entry in reversed(self.transcript_entries):
            if entry.get("role") == "assistant" and str(entry.get("content") or "").strip():
                return str(entry.get("content") or "")
        return ""

    def _selected_text(self) -> str:
        try:
            return str(self.screen.get_selected_text() or "")
        except Exception:
            return ""

    def _copy_text(self, text: str, label: str) -> None:
        clean = sanitize_terminal_text(text)
        if not clean.strip():
            self.notify(f"Nothing to copy ({label}).", title="Copy")
            return
        # Textual sends OSC 52, so this reaches the local clipboard over SSH (e.g. Termux).
        self.copy_to_clipboard(clean)
        self.notify(f"Copied {label}: {len(clean.splitlines()) or 1} lines.", title="Copy")

    def action_copy_smart(self) -> None:
        """Copy the mouse selection if there is one, otherwise the last run."""
        selected = self._selected_text()
        if selected.strip():
            self._copy_text(selected, "selection")
        else:
            self.action_copy_run()

    def action_toggle_mouse(self, enable: bool | None = None) -> None:
        """Release the mouse so the terminal's own select/copy works (Termux long-press etc.)."""
        current = bool(getattr(self, "_mouse_captured", True))
        enable = (not current) if enable is None else enable
        driver = getattr(self, "_driver", None)
        try:
            if driver is not None:
                if enable and hasattr(driver, "_enable_mouse_support"):
                    driver._enable_mouse_support()
                elif not enable and hasattr(driver, "_disable_mouse_support"):
                    driver._disable_mouse_support()
        except Exception:
            pass
        self._mouse_captured = enable
        self._append("system", "Mouse capture on: drag to select, F2 / Ctrl+Shift+C to copy." if enable
                     else "Mouse capture off: select and copy with your terminal (long-press on Termux). "
                          "Scroll with PgUp/PgDn. /mouse on or F3 to restore.", persist=False)

    def action_copy_run(self, *, to_file: bool = False) -> None:
        """Copy the last request's visible transcript and receipt summaries."""
        start = next(
            (i for i in range(len(self.transcript_entries) - 1, -1, -1)
             if self.transcript_entries[i].get("role") == "user"
             and not (self.transcript_entries[i].get("metadata") or {}).get("command")),
            None,
        )
        if start is None:
            self.notify("No BEAST request to copy yet.", title="Copy last run")
            return

        transcript = [
            row for row in self.transcript_entries[start:]
            if not (row.get("metadata") or {}).get("command")
            and str(row.get("content") or "").strip()
        ]
        run_id = next(
            (str(row["metadata"]["run_id"]) for row in reversed(transcript)
             if (row.get("metadata") or {}).get("run_id")),
            "",
        )
        lines = [f"BEAST last run{f' · {run_id}' if run_id else ''}", ""]
        lines.extend(f"{str(row.get('role') or 'event').upper()}> {row['content']}" for row in transcript)
        tools = self.tool_entries[self._run_tool_start:]
        if tools:
            lines.extend(("", "Tool and integration events"))
            for item in tools:
                tool_id = item.get("tool_id") or item.get("kind") or "event"
                receipt = item.get("receipt") or {}
                receipt_id = receipt.get("observation_id") or receipt.get("receipt_id")
                suffix = f" · receipt {receipt_id}" if receipt_id else ""
                lines.append(f"{item.get('sequence') or '-'} {tool_id}: {item.get('text') or item.get('status') or ''}{suffix}")
        sanitized = sanitize_terminal_text("\n".join(lines))
        if to_file:
            root = Path(self.settings.workspace).expanduser().resolve()
            directory = root / ".beast" / "coder"
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.resolve().is_relative_to(root):
                raise RuntimeClientError("Transcript export directory escapes the workspace")
            safe_run = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)[:96] or "latest"
            target = directory / f"last-run-{safe_run}.txt"
            if target.is_symlink():
                raise RuntimeClientError("Transcript export target is a symlink")
            target.write_text(sanitized + "\n", encoding="utf-8")
            target.chmod(0o600)
            self._append("system", f"Sanitized last run saved: {target}", persist=False)
            self.notify(str(target), title="Copy last run to file")
            return
        self.copy_to_clipboard(sanitized)
        self.notify("Last BEAST run sent to the clipboard.", title="Copy last run")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "coder-receipts-toggle":
            await self.toggle_tool_details()

    async def action_toggle_receipts(self) -> None:
        await self.toggle_tool_details()

    async def toggle_tool_details(self) -> None:
        self.details_expanded = not self.details_expanded
        self._sync()

    async def activate_pending_approval(self) -> None:
        if self.pending_approvals and not self._streaming:
            approval_id = str(self.pending_approvals[0].get("approval_id") or "")
            if approval_id:
                await self._approve_pending(approval_id)

    def _save_settings(self, **changes: Any) -> None:
        self.settings = replace(self.settings, **changes)
        self.store.save_settings(self.settings)
        self._sync()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.input.expand(event.value) if isinstance(event.input, PasteInput) else event.value
        value = sanitize_terminal_text(raw).strip()
        event.input.value = ""
        event.input.focus()
        self.run_worker(self._submit_input(value), group="coder-input", exit_on_error=False)

    async def _submit_input(self, value: str) -> None:
        if self._streaming:
            self._append("system", "BEAST is still working. Wait for this turn to finish.", persist=False)
            return
        if self._menu_kind:
            await self._choose_menu()
            return
        if value:
            if self._turn_ready and not value.startswith("/"):
                # User typed plain text while waiting for a turn - treat as /next then new prompt
                self._turn_ready = False
                self._set_mascot("working")
                await self._run_turn(value, mode=self._pending_mode, prefix=self._pending_prefix,
                                     swarm=self._pending_agent == "SWARM")
                return
            await self.submit_text(value)
        elif self._turn_ready:
            # Empty input while waiting for turn - advance to next turn
            self._turn_ready = False
            self._set_mascot("working")
            last_user = self._last_user_prompt()
            if last_user:
                await self._run_turn(last_user, append_user=False)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Drop leaked terminal reports before they are visible or submitted."""
        clean = sanitize_terminal_text(event.value)
        if clean != event.value:
            event.input.value = clean
            event.input.cursor_position = len(clean)

    async def submit_text(self, text: str) -> None:
        value = sanitize_terminal_text(text).strip()
        if not value:
            return
        if self._streaming:
            self._append("system", "BEAST is still working. Wait for this turn to finish.", persist=False)
            return
        self._welcome_active = False
        if self.is_mounted:
            self.screen.set_class(
                self.size.height < self.BRANDING_MIN_CONTENT_HEIGHT,
                "branding-hidden",
            )
        if value.startswith("/"):
            self._append(
                "user",
                value,
                persist=False,
                metadata={"command": True},
            )
            try:
                command = parse_slash_command(value)
                await self._run_command(command.name, command.argument)
            except (ValueError, RuntimeClientError, json.JSONDecodeError) as exc:
                self._set_mascot("alert")
                self._append("error", str(exc))
            return
        await self._run_turn(value, mode=self._pending_mode, prefix=self._pending_prefix,
                             swarm=self._pending_agent == "SWARM")

    @staticmethod
    def _pending(items: Any) -> list[dict[str, Any]]:
        rows = items if isinstance(items, list) else []
        return [
            item for item in rows
            if isinstance(item, dict)
            and str(item.get("status") or "pending").lower() == "pending"
        ]

    async def _approve_pending(self, approval_id: str) -> None:
        run_id = self.settings.last_run_id or ""
        if not run_id:
            self._append("error", "No AgentRun is available for approval.", persist=False)
            return
        await self.runtime.resolve_approval(run_id, approval_id, approved=True)
        self.pending_approvals = self._pending(await self.runtime.list_approvals(run_id))
        self._sync()
        if self.pending_approvals:
            self._append(
                "system",
                f"Approved {approval_id}. Tap the next approval to continue.",
                persist=False,
            )
            return
        prompt = self._last_user_prompt()
        self._turn_ready = False
        self._append("system", f"Approved {approval_id}. Continuing the run…", persist=False)
        if prompt:
            await self._run_turn(prompt, append_user=False)

    async def _run_command(self, name: str, argument: str) -> None:
        if name == "copy":
            what = argument.strip().lower()
            if what in {"", "run", "file"}:
                self.action_copy_run(to_file=what == "file")
                return
            if what in {"answer", "last"}:
                self._copy_text(self._last_answer_text(), "last answer")
                return
            if what == "diff":
                self._copy_text(str(self.diff_bundle.get("diff") or ""), "diff")
                return
            if what in {"selection", "sel"}:
                self._copy_text(self._selected_text(), "selection")
                return
            raise ValueError("Usage: /copy [run|answer|diff|selection|file]")
        if name == "mouse":
            what = argument.strip().lower()
            if what not in {"", "on", "off"}:
                raise ValueError("Usage: /mouse on|off")
            self.action_toggle_mouse(None if not what else what == "on")
            return
        if name in {"ask", "review", "edit", "agent"}:
            if not argument:
                raise ValueError(f"Usage: /{name} <task>. This applies to one request only.")
            if name == "review" and not self._composer_context_files(argument):
                raise ValueError("Use /review with an existing workspace file path.")
            await self._run_turn(argument, mode=name)
            return
        if name == "help":
            text = Text()
            text.append("BEAST COMMANDS\n", style=f"bold {BEAST_ACID}")
            text.append("Plain text runs the autonomous coding loop. Prefix with /ask for read-only.\n\n",
                        style=BEAST_MUTED)
            for group, commands in COMMAND_GROUPS:
                text.append(f"{group}\n", style=f"bold {BEAST_GREEN}")
                for command, description in commands:
                    text.append(f"  /{command:<11}", style=f"bold {BEAST_ACID}")
                    text.append(f"{description}\n", style=BEAST_TEXT)
                text.append("\n")
            text.append("Keys: F6 jump to latest · F7 toggle live diff · ↓ agent menu\n",
                        style=BEAST_MUTED)
            text.append("Copy/paste: drag to select, F2 or Ctrl+Shift+C copies the selection (else the last run) "
                        "via OSC 52, which works over SSH. /copy answer|diff|run|selection. F3 or /mouse off "
                        "hands the mouse to your terminal for native select. Multi-line pastes stay one "
                        "message ([Pasted #n: N lines]).\n", style=BEAST_MUTED)
            self._append("system", text.plain, persist=False)
            return
        if name == "beastie":
            self.beastie_expanded = not self.beastie_expanded
            self.screen.set_class(self.beastie_expanded, "beastie-expanded")
            self._append(
                "system",
                f"Original BEAST mascot {'expanded' if self.beastie_expanded else 'collapsed'}.",
                persist=False,
            )
            self.refresh(layout=True)
            return
        if name in {"expand", "less"}:
            self.details_expanded = name == "expand"
            self._append(
                "system",
                "Runtime event details expanded." if self.details_expanded
                else "Runtime event details collapsed.",
                persist=False,
            )
            return
        if name == "clear":
            # Clearing the visible transcript alone would retain the old agent session.
            # Rotate session identity so the next turn cannot silently reuse it.
            self._save_settings(session_id="", last_run_id="", session_title="")
            self.store.clear()
            self.transcript_entries.clear()
            self.tool_entries.clear()
            self._reset_actions()
            self.pending_approvals.clear()
            self.diff_bundle = {}
            self._live_diffs.clear()
            self._welcome_active = True
            self.screen.remove_class("branding-hidden")
            self._set_mascot("idle")
            return
        if name == "subject":
            if argument:
                self.subject = argument[:120]
            self._append("system", f"Subject: {self.subject or '(none)'}", persist=False)
            return
        if name == "context":
            messages = self.store.messages()
            chars = sum(len(str(row.get("content") or "")) for row in messages)
            self._append("system", f"Visible history: {len(messages)} messages, {chars} characters. Token use and model context capacity are not exposed by this AgentRun API; no token count is asserted. Session: {self.settings.session_id or '(new)'}. /clear rotates the session.", persist=False)
            return
        if name == "btw":
            note = argument.strip()
            if not note:
                self._append("system", "Usage: /btw <note> — add a side context note to this session without starting an agent run.", persist=False)
                return
            self._append("system", f"BTW: {note}", persist=True)
            self.store.append("system", f"BTW: {note}")
            self._sync()
            return
        if name == "permission":
            value = argument.strip().lower()
            if not value:
                self._append(
                    "system",
                    f"/permission off — nuke all per-call approval prompts for this session (runtime still audits). "
                    f"Usage: /permission off | /permission on",
                    persist=False,
                )
                return
            if value == "off":
                self._permission_nuked = True
                self._append("system", "PERMISSION NUKED: all per-call approval prompts disabled. The runtime still writes audit records but never parks for approval.", persist=False)
            elif value == "on":
                self._permission_nuked = False
                self._append("system", "PERMISSION RESTORED: per-call approval prompts re-enabled.", persist=False)
            else:
                self._append("system", "Usage: /permission off | /permission on", persist=False)
            self._sync()
            return
        if name in {"thinking"}:
            self._append("system", f"/{name}: not wired to an enforceable BEAST runtime contract. No setting was changed. Backend support and receipts are required before enabling this control.", persist=False)
            return
        if name == "exit":
            self.exit_requested = True
            self.exit()
            return
        if name == "approvals":
            run_id = self.settings.last_run_id or ""
            if not run_id:
                self._append("system", "No AgentRun yet. Submit a prompt first.", persist=False)
                return
            items = await self.runtime.list_approvals(run_id)
            pending = self._pending(items)
            self.pending_approvals = pending
            self._sync()
            if not pending:
                self._append("system", f"No pending approvals for run {run_id}.", persist=False)
                return
            self._append("system", "Pending approval shown below. Tap the card or use /approve.", persist=False)
            return
        if name == "approve":
            run_id = self.settings.last_run_id or ""
            if not run_id:
                self._append("system", "No AgentRun yet. Submit a prompt first.", persist=False)
                return
            items = await self.runtime.list_approvals(run_id)
            pending = self._pending(items)
            self.pending_approvals = pending
            self._sync()
            if not pending:
                self._append("system", f"No pending approvals for run {run_id}.", persist=False)
                return
            wanted = argument.strip()
            target = None
            if wanted:
                target = next(
                    (item for item in pending
                     if str(item.get("approval_id") or "").startswith(wanted)),
                    None,
                )
                if target is None:
                    self._append("error", f"No pending approval matches {wanted!r}.", persist=False)
                    return
            else:
                target = pending[0]
            approval_id = str(target.get("approval_id") or "")
            await self._approve_pending(approval_id)
            return
        if name == "next":
            if not self._turn_ready:
                self._append("system", "No turn is ready to advance. Submit a prompt first.", persist=False)
                return
            self._turn_ready = False
            self._set_mascot("working")
            last_user = self._last_user_prompt()
            if last_user:
                await self._run_turn(last_user, append_user=False)
            return
        if name == "auto":
            wanted = argument.strip().lower()
            if wanted in {"on", "true", "1", "autopilot", "auto"}:
                self._save_settings(auto_mode=True)
            elif wanted in {"off", "false", "0", "manual", "governed"}:
                self._save_settings(auto_mode=False)
            else:
                state = "ON" if self.settings.auto_mode else "OFF"
                self._append(
                    "system",
                    f"Autopilot is {state}. Use /auto on or /auto off.",
                    persist=False,
                )
                return
            state = "ON" if self.settings.auto_mode else "OFF"
            self._append(
                "system",
                f"Autopilot {state}. "
                + (
                    "Coding turns run to completion, approvals are granted to workspace-bounded tools, "
                    "and the runtime verifies the isolated diff automatically."
                    if self.settings.auto_mode
                    else "Each mutating tool now waits for an explicit approval."
                ),
                persist=False,
            )
            return
        if name == "diff":
            self.diff_expanded = True
            self._show_cumulative_diff = True
            self._sync()
            if not self.diff_bundle.get("diff"):
                self._append("system", "No live diff yet. Edits appear here as the agent works.", persist=False)
                return
            added = int(self.diff_bundle.get("added") or 0)
            removed = int(self.diff_bundle.get("removed") or 0)
            files = ", ".join(str(item) for item in self.diff_bundle.get("files") or []) or "worktree"
            self._append(
                "system",
                f"Live diff: {files} · +{added} −{removed} · panel expanded (F7 toggles).",
                persist=False,
            )
            self.call_after_refresh(self._scroll_transcript_end)
            return
        if name == "ide":
            await self._refresh_ide_compat()
            return
        if name == "agents":
            self.open_agent_menu()
            return
        if name == "sessions":
            if argument.strip():
                self._resume_session(argument.strip())
                return
            sessions = self.store.list_sessions()
            if not sessions:
                self._append("system", "No archived sessions yet. Use /new to start one.", persist=False)
                return
            self._open_sessions_menu(sessions)
            self._append(
                "system",
                "SESSIONS\n" + "\n".join(
                    f"  {item['session_id']}  ·  {item['title']}  ·  {item['messages']} messages"
                    for item in sessions
                ) + "\nUse /sessions <id> to resume, or pick from the menu with ↑/↓ + Enter.",
                persist=False,
            )
            return
        if name == "new":
            archived = self.store.archive_session(argument.strip() or self.settings.session_title or "session")
            self.transcript_entries.clear()
            self.tool_entries.clear()
            self._reset_actions()
            self.pending_approvals.clear()
            self.diff_bundle = {}
            self._live_diffs.clear()
            self._welcome_active = True
            self.store.clear()
            self._save_settings(session_id="", last_run_id="", session_title=argument.strip())
            self._append(
                "system",
                f"New session started. Archived previous conversation as {archived['session_id']}."
                if archived else "New session started.",
                persist=False,
            )
            return
        if name == "rename":
            title = argument.strip()
            if not title:
                self._append("system", f"Session title: {self.settings.session_title or '(none)'}", persist=False)
                return
            self._save_settings(session_title=title[:120])
            self._append("system", f"Session renamed to {title[:120]}.", persist=False)
            return
        if name == "budget":
            messages = self.store.messages()
            chars = sum(len(str(row.get("content") or "")) for row in messages)
            limit = 0
            try:
                limit = int(os.environ.get("BEAST_TLI_CONTEXT_CHARS", "200000"))
            except ValueError:
                limit = 200000
            tokens = chars // 4
            pct = int((chars / limit) * 100) if limit else 0
            lines = [
                f"Visible history: {len(messages)} messages, {chars} chars (~{tokens} tokens)",
                f"Auto-compact threshold: {limit} chars ({pct}% used)",
            ]
            run_id = self.settings.last_run_id or ""
            if run_id:
                try:
                    status = await self.runtime.runtime_status(run_id)
                    run = status.get("run") if isinstance(status.get("run"), dict) else {}
                    budget = run.get("budget") if isinstance(run.get("budget"), dict) else {}
                    lines.append(
                        f"Run {run_id}: state={run.get('state')} turn={run.get('turn')} "
                        f"budget={json.dumps(budget, sort_keys=True, default=str)[:200]}"
                    )
                except (RuntimeClientError, json.JSONDecodeError) as exc:
                    lines.append(f"Run budget unavailable: {exc}")
            if pct >= 70:
                lines.append("Above 70%: /compact archives and compresses the history.")
            self._append("system", "\n".join(lines), persist=False)
            return
        if name == "compact":
            self._compact_history(argument.strip())
            return
        if name == "apply":
            await self._apply_last_run()
            return
        if name == "provider":
            providers = await self.runtime.discover_providers()
            records = providers.get("providers") if isinstance(providers.get("providers"), list) else []
            if not argument:
                self._append("system", self._format_records("Providers", records), persist=False)
                return
            selected = next(
                (item for item in records if str(item.get("provider_id") or "") == argument and item.get("enabled", True)),
                None,
            )
            if selected is None:
                raise ValueError(f"provider is not enabled in the BEAST registry: {argument}")
            self._save_settings(
                provider=argument,
                model=str(selected.get("default_model") or self.settings.model),
                session_id="",
                last_run_id="",
            )
            self._append("system", f"Provider selected: {argument}; model: {self.settings.model}")
            return
        if name == "model":
            if not argument:
                providers = await self.runtime.discover_providers()
                records = providers.get("providers") if isinstance(providers.get("providers"), list) else []
                self._append(
                    "system",
                    f"Selected model: {self.settings.model}\n" + self._format_records("Provider defaults", records),
                    persist=False,
                )
                return
            self._save_settings(model=argument, session_id="", last_run_id="")
            self._append("system", f"Model selected: {argument}")
            return
        if name == "skills":
            if argument:
                discovery = await self.runtime.discover_skills()
                skills = discovery.get("skills") if isinstance(discovery.get("skills"), list) else []
                selected_skill = next(
                    (
                        item
                        for item in skills
                        if argument
                        in {
                            str(item.get("id") or ""),
                            str(item.get("skill_id") or ""),
                            str(item.get("name") or ""),
                        }
                    ),
                    None,
                )
                if selected_skill is None:
                    raise ValueError(
                        f"Meta Skill is not reported by runtime discovery: {argument}"
                    )
                skill_id = str(
                    selected_skill.get("id")
                    or selected_skill.get("skill_id")
                    or selected_skill.get("name")
                )
                session_id = self.settings.session_id
                if not session_id:
                    session = await self.runtime.ensure_session(
                        self.settings.provider, self.settings.model
                    )
                    session_id = str(session.get("session_id") or "")
                    self._save_settings(session_id=session_id)
                grant = await self.runtime.grant_verified_skill(session_id, skill_id)
                grant_receipt = grant.get("receipt") if isinstance(grant.get("receipt"), dict) else {}
                if not grant_receipt:
                    session = grant.get("session") if isinstance(grant.get("session"), dict) else {}
                    evidence = session.get("evidence") if isinstance(session.get("evidence"), list) else []
                    last = evidence[-1] if evidence and isinstance(evidence[-1], dict) else {}
                    grant_receipt = last.get("receipt") if isinstance(last.get("receipt"), dict) else last
                self.tool_entries.append(
                    {
                        "kind": "skill_grant",
                        "text": f"Verified Meta Skill capability granted for next turn: {skill_id}",
                        "status": "granted",
                        "tool_id": skill_id,
                        "executed": False,
                        "success": bool(grant.get("ok")),
                        "receipt": grant_receipt,
                        "details": {"authority": "advisory verified skill"},
                    }
                )
                self._sync()
                await self._run_turn(f"Invoke the verified BEAST Meta Skill {skill_id} for this coding workspace.")
                return
            skills = await self.runtime.discover_skills()
            self._append("system", self._format_records("Meta Skills", skills.get("skills") or []), persist=False)
            return
        if name == "mcp":
            if argument:
                prefix, separator, remainder = argument.partition(" ")
                if prefix.lower() != "call" or not separator:
                    raise ValueError('/mcp invocation syntax: /mcp call TOOL_NAME {"argument":"value"}')
                server_name, separator, tool_tail = remainder.strip().partition(" ")
                if not separator:
                    raise ValueError('/mcp invocation syntax: /mcp call SERVER TOOL {"argument":"value"}')
                tool_name, separator, raw_payload = tool_tail.strip().partition(" ")
                request_payload = json.loads(raw_payload) if separator and raw_payload.strip() else {}
                if not isinstance(request_payload, dict):
                    raise ValueError("MCP arguments must be a JSON object")
                request_payload["server_name"] = server_name
                request_payload["tool_name"] = tool_name
                result = await self.runtime.execute_mcp(request_payload)
                executed = bool(result.get("executed"))
                boundary = (
                    result.get("edgek_crystal_tool_boundary")
                    if isinstance(result.get("edgek_crystal_tool_boundary"), dict)
                    else {}
                )
                self.tool_entries.append(
                    {
                        "kind": "mcp_result",
                        "text": str(result.get("reason") or f"MCP {tool_name} {'executed' if executed else 'blocked'}"),
                        "status": "completed" if executed else str(result.get("decision") or "blocked"),
                        "tool_id": tool_name,
                        "executed": executed,
                        "success": executed,
                        "receipt": {
                            "request_id": str(result.get("request_id") or ""),
                            "receipt_digest": str(
                                boundary.get("receipt_digest")
                                or (boundary.get("residue_seal") or {}).get("digest")
                                or ""
                            ),
                        },
                        "details": result,
                    }
                )
                self._sync()
                return
            mcp = await self.runtime.discover_mcp()
            self._append("system", self._format_mapping("MCP", mcp), persist=False)
            return
        if name == "tools":
            if not self.settings.last_run_id:
                raise ValueError("/tools requires a coding run first")
            tools = await self.runtime.discover_tools(self.settings.last_run_id)
            self._append("system", self._format_records("Agent tools", tools.get("tools") or []), persist=False)
            return
        if name == "workspace":
            if not argument:
                self._append("system", f"Workspace: {self.settings.workspace}", persist=False)
                return
            target_store = ConversationStore(Path(argument))
            saved = target_store.load_settings()

            # Preserve durable per-workspace session/run identity when switching
            # back to an existing coding workspace. Provider/model follow the
            # current operator selection unless the destination already records
            # an active session/run.
            new_settings = CoderSettings(
                workspace=Path(argument),
                provider=saved.provider if saved.last_run_id else self.settings.provider,
                model=saved.model if saved.last_run_id else self.settings.model,
                session_id=saved.session_id,
                last_run_id=saved.last_run_id,
                auto_mode=saved.auto_mode,
                session_title=saved.session_title,
            )
            if self._injected_runtime and self._runtime_client_factory is None:
                raise ValueError("workspace switching is unavailable for the injected runtime client")
            await self.runtime.aclose()
            self.store = target_store
            self.settings = new_settings
            self.store.save_settings(self.settings)
            self.runtime = self._new_runtime(new_settings.workspace)
            self.transcript_entries = self.store.messages()
            self.tool_entries.clear()
            self._reset_actions()

            # Rehydrate the durable AgentRun timeline when returning to an
            # existing workspace. Conversation text and execution evidence are
            # separate stores; both must be restored for an honest UI.
            if self.settings.last_run_id:
                try:
                    for runtime_event in await self.runtime.run_events(
                        self.settings.last_run_id,
                        limit=2000,
                    ):
                        projected = project_runtime_event(runtime_event)
                        if projected.kind in {"tool_call", "tool_result", "integration"}:
                            self.tool_entries.append({
                                "kind": projected.kind,
                                "text": projected.text,
                                "sequence": projected.sequence,
                                "status": projected.status,
                                "tool_id": projected.tool_id,
                                "executed": projected.executed,
                                "success": projected.success,
                                "receipt": projected.receipt,
                                "details": projected.details,
                            })
                except (RuntimeClientError, json.JSONDecodeError) as exc:
                    self._append(
                        "system",
                        f"Run event history unavailable: {exc}",
                        persist=False,
                    )

            self._append("system", f"Workspace selected: {new_settings.workspace}")
            self._sync()
            return
        if name == "status":
            status = await self.runtime.runtime_status(self.settings.last_run_id)
            self._append(
                "system",
                f"Workspace: {self.settings.workspace}\nProvider: {self.settings.provider}\nModel: {self.settings.model}\n"
                + self._format_mapping("Runtime", status),
                persist=False,
            )

    def _compact_history(self, reason: str = "") -> None:
        """Archive the full transcript and keep a compact, resumable digest."""
        archived = self.store.archive_session(
            reason or self.settings.session_title or "compact"
        )
        rows = (archived or {}).get("messages") or len(self.transcript_entries)
        users = [row for row in self.transcript_entries if row.get("role") == "user"]
        assistants = [row for row in self.transcript_entries if row.get("role") == "assistant"]
        first = str(users[0].get("content") or "")[:200] if users else ""
        last = str(users[-1].get("content") or "")[:200] if users else ""
        summary = str(assistants[-1].get("content") or "")[:1200] if assistants else ""
        digest = (
            "COMPACTED CONTEXT\n"
            f"Archived {rows} messages as {((archived or {}).get('session_id') or 'session')}.\n"
            f"First request: {first or '(none)'}\n"
            f"Latest request: {last or '(none)'}\n"
            f"Latest outcome: {summary or '(none)'}"
        )
        compact_rows = [{"role": "system", "content": digest, "metadata": {"compacted": True}}]
        if summary:
            compact_rows.append({
                "role": "assistant",
                "content": summary,
                "metadata": {"compacted": True},
            })
        self.store.replace_messages(compact_rows)
        self.transcript_entries = self.store.messages()
        self._append(
            "system",
            f"Compacted {rows} messages into a digest. Full transcript remains at /sessions {((archived or {}).get('session_id') or '')}.",
            persist=False,
        )

    async def _auto_compact_if_needed(self) -> None:
        try:
            limit = int(os.environ.get("BEAST_TLI_CONTEXT_CHARS", "200000"))
        except ValueError:
            limit = 200000
        chars = sum(len(str(row.get("content") or "")) for row in self.transcript_entries)
        if chars <= limit or not self.transcript_entries:
            return
        self._compact_history("auto-compact")

    async def _refresh_ide_compat(self) -> None:
        """Probe the IDE compatibility plane and render it in the compat panel."""
        try:
            snapshot = await self.runtime.discover_ide_snapshot()
        except Exception as exc:
            self._append("error", f"IDE compatibility probe failed: {exc}", persist=False)
            return
        self.ide_compat = snapshot or {}
        self.screen.set_class(bool(self.ide_compat), "has-ide-compat")
        self._sync()
        summary = self.ide_compat.get("summary") or {}
        available = int(summary.get("available") or 0)
        total = int(summary.get("total") or 0)
        coverage = int(summary.get("coverage") or 0)
        ext_host = self.ide_compat.get("extensionHost") or {}
        lines = [
            f"IDE compatibility: {available}/{total} available ({coverage}%)",
            f"Extension host: {str(ext_host.get('status') or 'unknown')}",
        ]
        langs = [l for l in (self.ide_compat.get("languages") or []) if l.get("available")]
        dbgs = [d for d in (self.ide_compat.get("debug") or []) if d.get("available")]
        nb = [n for n in (self.ide_compat.get("notebooks") or []) if n.get("available")]
        rem = [r for r in (self.ide_compat.get("remote") or []) if r.get("available")]
        if langs:
            lines.append("Languages: " + ", ".join(str(l.get("label") or l.get("id")) for l in langs[:6]))
        if dbgs:
            lines.append("Debuggers: " + ", ".join(str(d.get("label") or d.get("id")) for d in dbgs[:6]))
        if nb:
            lines.append("Notebooks: " + ", ".join(str(n.get("label") or n.get("id")) for n in nb[:4]))
        if rem:
            lines.append("Remote: " + ", ".join(str(r.get("label") or r.get("id")) for r in rem[:4]))
        self._append("system", "\n".join(lines), persist=False)

    async def _apply_last_run(self) -> None:
        run_id = self.settings.last_run_id or ""
        if not run_id:
            self._append("system", "No AgentRun yet. Submit a prompt first.", persist=False)
            return
        status = await self.runtime.runtime_status(run_id)
        run = status.get("run") if isinstance(status.get("run"), dict) else {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        applied = checkpoint.get("workspace_apply") if isinstance(checkpoint.get("workspace_apply"), dict) else {}
        if applied.get("status") == "applied":
            self._append(
                "system",
                f"Run {run_id} already applied: {', '.join(applied.get('files') or []) or 'no files'}.",
                persist=False,
            )
            return
        worktree_root = str(checkpoint.get("worktree_root") or "").strip()
        base_commit = str(checkpoint.get("worktree_base_commit") or "").strip()
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
        files: list[str] = []
        for observation in reversed(observations):
            if not isinstance(observation, dict):
                continue
            if observation.get("tool_id") != "worktree.sourceplan_draft":
                continue
            if observation.get("status") != "completed":
                continue
            plan = (observation.get("result") or {}).get("plan") if isinstance(observation.get("result"), dict) else {}
            if isinstance(plan, dict) and isinstance(plan.get("files"), list):
                files = [str(item) for item in plan["files"]]
                break
        if not worktree_root or not files:
            self._append(
                "system",
                "Nothing to apply: this run has no verified SourcePlan in an isolated worktree. "
                "Autopilot runs apply automatically; run /auto on and rerun the task.",
                persist=False,
            )
            return
        try:
            from app.kernel.agents.worktree_apply import ApplyBlocked, apply_workspace_files

            result = await asyncio.to_thread(
                apply_workspace_files,
                workspace_root=self.settings.workspace,
                worktree_root=worktree_root,
                base_commit=base_commit,
                files=files,
            )
        except ApplyBlocked as exc:
            self._append("error", f"Apply blocked: {exc}. Your workspace file was not changed.", persist=False)
            return
        except Exception as exc:  # pragma: no cover - defensive surface
            self._append("error", f"Apply failed: {exc}", persist=False)
            return
        paths = [str(item.get("path") or "") for item in result.get("applied", [])]
        self._append(
            "system",
            f"Applied verified diff to the workspace: {', '.join(paths) or 'no files'}.",
            persist=False,
        )
        self._set_mascot("finished")

    @staticmethod
    def _format_records(title: str, records: Any) -> str:
        rows = records if isinstance(records, list) else []
        if not rows:
            return f"{title}: none reported by runtime"
        lines = [f"{title} ({len(rows)}):"]
        for row in rows[:40]:
            if isinstance(row, dict):
                name = next((str(row[k]) for k in ("name", "provider_id", "model_id", "id", "tool_id", "slug") if row.get(k)), "unnamed")
                detail = next((str(row[k]) for k in ("description", "default_model", "status", "effect", "category") if row.get(k)), "")
                lines.append(f"  {name}" + (f"  ·  {detail[:100]}" if detail else ""))
            else:
                lines.append(f"  {str(row)[:140]}")
        if len(rows) > 40:
            lines.append(f"  ... {len(rows) - 40} more (not shown)")
        return "\n".join(lines)

    @staticmethod
    def _format_mapping(title: str, payload: Any) -> str:
        if not isinstance(payload, dict):
            return f"{title}: {str(payload)[:300]}"
        lines = [f"{title}:"]
        for key, value in list(payload.items())[:18]:
            if isinstance(value, list):
                lines.append(f"  {key}: {len(value)} entries")
                for item in value[:8]:
                    if isinstance(item, dict):
                        label = item.get("name") or item.get("id") or item.get("tool_name") or item.get("server_name") or item.get("status") or "item"
                        lines.append(f"    {label}")
                    else:
                        lines.append(f"    {str(item)[:100]}")
            elif isinstance(value, dict):
                lines.append(f"  {key}: {', '.join(map(str, list(value)[:10]))}")
            else:
                lines.append(f"  {key}: {str(value)[:180]}")
        return "\n".join(lines)

    def _composer_context_files(self, prompt: str) -> tuple[str, ...]:
        return resolve_context_files(self.settings.workspace, prompt)

    def _route_turn_mode(self, mode: str, prompt: str) -> str:
        """Keep explicit ask/review/edit; route agent analysis prompts like the IDE."""
        routed = route_composer_mode(mode, prompt)
        if routed == "review" and not self._composer_context_files(prompt):
            return "ask"
        return routed

    async def _run_turn(
        self,
        prompt: str,
        *,
        append_user: bool = True,
        auto_turns: int = 0,
        mode: str = "agent",
        prefix: str = "",
        swarm: bool = False,
    ) -> None:
        if self._streaming:
            raise RuntimeClientError("a BEAST coding turn is already running")
        if append_user and self._is_conversational(prompt):
            self._streaming = False
            self._set_mascot("idle")
            self._turn_ready = True
            self._append("user", prompt)
            reply = self._conversational_reply(prompt)
            self._append("assistant", reply, metadata={"conversational": True})
            self.store.append("user", prompt)
            self.store.append("assistant", reply)
            self._sync()
            return
        if append_user:
            await self._auto_compact_if_needed()
        requested_mode = mode
        mode = self._route_turn_mode(mode, prompt)
        # Swarm's mutate-and-verify prefix is only for implementation runs.
        if prefix and mode in {"agent", "edit"}:
            effective_prompt = f"{prefix}{prompt}"
        else:
            effective_prompt = prompt
        self._streaming = True
        self._set_mascot("working")
        if append_user:
            self._turn_ready = False
            self.pending_approvals.clear()
            self._run_tool_start = len(self.tool_entries)
            self._append("user", prompt)
            if requested_mode == "agent" and mode in {"ask", "review"}:
                self._append(
                    "system",
                    'Routed as analysis; say "apply" to patch.',
                    persist=False,
                )
            prompt = effective_prompt
            self._reset_actions()
            # A new objective starts a fresh live diff; the previous run's
            # verified diff returns via agent.worktree.diff_ready.
            self._live_diffs.clear()
            self.diff_bundle = {}
            self.thinking_bundle = ""
            self.crystal_lattice = {}
        assistant = ""
        advisory = ""
        answer_error = ""
        context_files = self._composer_context_files(prompt)
        grounded = mode in {"ask", "review"} and bool(context_files)
        assistant_index: int | None = None
        receipts: list[str] = []
        run_id = ""
        try:
            session_id = self.settings.session_id
            if not session_id:
                session = await self.runtime.ensure_session(
                    self.settings.provider, self.settings.model
                )
                session_id = str(session.get("session_id") or "")
                self._save_settings(session_id=session_id)
            # A new operator prompt is a new objective. Only internal
            # auto-continuations and approval resumes may reuse an AgentRun.
            run_id = "" if append_user else (self.settings.last_run_id or "")
            if run_id:
                # Check run state - if terminal, start new run
                status = await self.runtime.runtime_status(run_id)
                run_state = str(status.get("run", {}).get("state", ""))
                if run_state in _TERMINAL_RUN_STATES:
                    run_id = ""
            if not run_id:
                run = await self.runtime.start_run(
                    session_id, prompt, self.settings.provider, self.settings.model, mode=mode,
                    context_files=context_files,
                    conversation=self._conversation_for_run(prompt),
                    autonomy="autopilot" if self.settings.auto_mode else "manual",
                    permission_mode="nuked" if self._permission_nuked else "normal",
                    **({"swarm": True} if swarm and mode == "agent" else {}),
                )
                run_id = str(run.get("run_id") or "")
                self._save_settings(last_run_id=run_id)
            assistant_index = len(self.transcript_entries)
            self.transcript_entries.append(
                {
                    "role": "assistant",
                    "content": "",
                    "metadata": {"run_id": run_id, "streaming": True},
                }
            )
            self._sync()
            # Open the durable event tail while the turn POST is executing.
            # The old ordering awaited the entire model/tool turn first, which
            # made the TUI appear frozen and only replayed output afterwards.
            turn_task = asyncio.create_task(self.runtime.start_turn(run_id))
            turn_task.add_done_callback(self._observe_turn_task)
            self._turn_tasks.add(turn_task)
            after = int(self._run_event_after.get(run_id, 0))
            try:
                async for runtime_event in self.runtime.turn_events(
                    run_id,
                    after=after,
                    max_events=2000,
                    idle_timeout=0.35,
                    completion=turn_task,
                ):
                    try:
                        event_sequence = int(runtime_event.event_id or 0)
                    except ValueError:
                        event_sequence = 0
                    if event_sequence > after:
                        after = event_sequence
                    if runtime_event.event == "agent.coder.turn.started":
                        self._begin_action()
                        self._sync()
                        continue
                    projected = project_runtime_event(runtime_event)
                    if projected.kind == "token" and not grounded and not self._actions:
                        assistant += projected.text
                        # Planner control packets are rendered as tool cards,
                        # not as assistant prose. Keep the raw JSON out of the
                        # visible conversation and the persisted transcript.
                        if not self._is_control_packet(assistant):
                            now = time.monotonic()
                            if now - self._last_stream_paint >= 0.04:
                                self.transcript_entries[assistant_index]["content"] = assistant
                                self._last_stream_paint = now
                                self._sync()
                    elif projected.kind == "reasoning":
                        # Render model reasoning in the collapsible thinking
                        # block instead of as assistant prose.
                        if projected.details.get("delta"):
                            self.thinking_bundle = (self.thinking_bundle + projected.text)[-8000:]
                        else:
                            self.thinking_bundle = str(projected.text or "")
                        self._paint_thinking()
                    elif projected.kind == "action_rejected":
                        self._update_action({"kind": "tool_result", "details": {}, "status": "rejected",
                                             "tool_id": projected.tool_id, "text": projected.text})
                        self._sync()
                    elif projected.kind == "answer_error":
                        answer_error = projected.text
                    elif projected.kind == "advisory":
                        advisory = projected.text
                    elif projected.kind == "crystal":
                        # Crystal/lattice events: reuse decisions, promotions,
                        # reductions, autopromotion activity. Accumulate into the
                        # crystal_lattice bundle for the live panel.
                        details = projected.details if isinstance(projected.details, dict) else {}
                        status = projected.status or ""
                        kind_map = {
                            "refused": ("decisions", {"action": "refused", "reason": str(details.get("reason") or "")}),
                            "formed": ("promotions", {"action": "formed", "reason": "durable registry + lattice admission"}),
                            "activated": ("decisions", {"action": "activated", "reason": "provider bypass armed"}),
                            "reused": ("reductions", {"action": "reused", "reason": "completed without provider decision"}),
                            "credited": ("reductions", {"action": "credited", "reason": str(details.get("reason") or "")}),
                            "scan": ("autopromotion", details),
                            "failed": ("reductions", {"action": "failed", "reason": str(details.get("reason") or "")}),
                            "aborted": ("reductions", {"action": "aborted", "reason": str(details.get("reason") or "")}),
                        }
                        section, item = kind_map.get(status, ("decisions", {"action": status, "reason": str(details.get("reason") or "")}))
                        if section == "autopromotion":
                            self.crystal_lattice["autopromotion"] = dict(details)
                            self.screen.set_class(True, "has-crystal-lattice")
                            self._sync()
                            continue
                        item = {**item, **{k: v for k, v in details.items() if k not in item}}
                        item["success"] = bool(projected.success)
                        self.crystal_lattice.setdefault(section, [])
                        self.crystal_lattice[section].append(item)
                        # Keep only the most recent 10 per section.
                        self.crystal_lattice[section] = self.crystal_lattice[section][-10:]
                        self.screen.set_class(bool(self.crystal_lattice), "has-crystal-lattice")
                        self._sync()
                    elif projected.kind == "diff":
                        if str(projected.details.get("diff") or "").strip():
                            self._merge_diff(projected.details, status=projected.status or "ready")
                        else:
                            self.diff_bundle = {
                                **self.diff_bundle,
                                "status": projected.status or "ready",
                                "note": projected.text,
                            }
                        self._sync()
                    elif projected.kind in {"tool_call", "tool_result", "integration"}:
                        row = {
                            "kind": projected.kind,
                            "text": projected.text,
                            "sequence": projected.sequence,
                            "status": projected.status,
                            "tool_id": projected.tool_id,
                            "executed": projected.executed,
                            "success": projected.success,
                            "receipt": projected.receipt,
                            "details": projected.details,
                        }
                        self.tool_entries.append(row)
                        if projected.kind == "integration" and projected.tool_id in {"swarm_roles", "swarm_recovery"}:
                            # Show actual role events and recovery receipts, not fictitious worker turns.
                            self._action_count += 1
                            roles = [str(item.get("role") or "") for item in projected.details.get("roles", [])
                                     if isinstance(item, dict) and item.get("role")]
                            status = {"fired": "completed", "started": "running"}.get(projected.status, projected.status)
                            self._actions.append({
                                "id": self._action_count, "status": status,
                                "tool_id": "Swarm roles" if projected.tool_id == "swarm_roles" else "Swarm recovery",
                                "details": {"subject": ", ".join(dict.fromkeys(roles)) or projected.text},
                                "thinking": projected.text if roles else "",
                            })
                        elif projected.kind == "integration" and (
                            projected.tool_id.startswith("family_crystal")
                            or projected.tool_id.startswith("family_lattice")
                            or projected.tool_id.startswith("compound_crystal")
                            or projected.tool_id.startswith("crystal.")
                            or projected.tool_id.startswith("crystal_")
                        ):
                            # Crystal/lattice execution is operator-visible control flow.
                            # These events must remain visible live, not merely durable
                            # in the event ledger / receipt drawer.
                            self._action_count += 1

                            status = {
                                "fired": "completed",
                                "observed": "completed",
                                "started": "running",
                                "skipped": "failed",
                                "refused": "failed",
                            }.get(projected.status, projected.status or "completed")

                            capability = projected.tool_id
                            if capability.startswith("family_crystal"):
                                label = "Crystal"
                            elif capability.startswith("family_lattice"):
                                label = "Lattice"
                            elif capability.startswith("compound_crystal"):
                                label = "Compound crystal"
                            else:
                                label = "Crystal"

                            self._actions.append({
                                "id": self._action_count,
                                "status": status,
                                "tool_id": label,
                                "details": {
                                    "subject": projected.text,
                                    "capability": capability,
                                },
                                "thinking": "",
                            })
                        elif projected.kind != "integration":
                            self._update_action(row)
                        if projected.kind == "tool_result" and projected.success:
                            self._record_tool_patch(projected.tool_id, projected.details)
                        self.transcript_entries[assistant_index]["content"] = assistant
                        if projected.receipt.get("observation_id"):
                            receipts.append(projected.receipt["observation_id"])
                        self._sync()
                try:
                    result = await turn_task
                finally:
                    self.__dict__.setdefault("_beast_handled_turns", set()).add(id(turn_task))
                if self._current_action is not None and self._current_action["status"] == "thinking":
                    if self.thinking_bundle:
                        self._current_action["thinking"] = self.thinking_bundle
                    self._current_action["status"] = str(result.get("state") or "finished")
                    self.thinking_bundle = ""
            except Exception:
                self.__dict__.setdefault("_beast_handled_turns", set()).add(id(turn_task))
                if not turn_task.done():
                    turn_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await turn_task
                elif not turn_task.cancelled() and turn_task.exception() is not None:
                    # Retrieve it so asyncio does not print "Task exception was never
                    # retrieved"; prefer the turn's own error (e.g. a dropped POST).
                    turn_error = turn_task.exception()
                    if isinstance(turn_error, RuntimeClientError):
                        raise turn_error
                raise
            run_state = str(result.get("state") or "running")
            self._run_event_after[run_id] = after
            # Turn complete - check if terminal
            if run_state in _TERMINAL_RUN_STATES:
                self.pending_approvals.clear()
                visible = "" if self._is_control_packet(assistant) else assistant
                final_text = advisory or ("" if grounded else visible)
                if grounded and not final_text:
                    answer_error = answer_error or str(result.get("error") or "No grounded answer was returned.")
                elif run_state != "completed":
                    answer_error = answer_error or str(result.get("error") or "").strip()
                final_metadata = {"run_id": run_id, "receipt_ids": receipts, "turn_complete": True}
                if self._actions and final_text and run_state == "completed" and not answer_error:
                    final_metadata["action_summary"] = True
                    self._action_summary = final_text
                if final_text:
                    self.transcript_entries[assistant_index] = {
                        "role": "assistant",
                        "content": final_text,
                        "metadata": final_metadata,
                    }
                    self.store.append("assistant", final_text, metadata=final_metadata)
                else:
                    # Don't leave a blank BEAST> bubble when the run was blocked
                    # or failed without an answer. The error line carries the reason.
                    self.transcript_entries.pop(assistant_index)
                    assistant_index = None
                self._sync()
                self._set_mascot("finished" if run_state == "completed" and not answer_error else "alert")
                if run_state == "completed" and not answer_error and not self._action_summary:
                    self._append_completion_summary(run_id, run_state, advisory, receipts)
                if answer_error or run_state != "completed":
                    reason = answer_error or f"AgentRun ended as {run_state}."
                    if (
                        run_state != "completed"
                        and answer_error
                        and run_state not in answer_error
                    ):
                        reason = f"AgentRun ended as {run_state}: {answer_error}"
                    self._append("error", reason)
                self._turn_ready = False
                return
            # Turn complete but not terminal - wait for operator to advance
            visible = "" if self._is_control_packet(assistant) else assistant
            final_text = advisory or visible or self.transcript_entries[assistant_index]["content"]
            if self._is_control_packet(final_text):
                final_text = advisory
            final_metadata = {"run_id": run_id, "receipt_ids": receipts, "turn_complete": False}
            if final_text:
                self.transcript_entries[assistant_index] = {
                    "role": "assistant",
                    "content": final_text,
                    "metadata": final_metadata,
                }
                self.store.append("assistant", final_text, metadata=final_metadata)
            else:
                # A planner turn that only emitted a control packet has no
                # prose to keep; the tool cards already show the action.
                self.transcript_entries.pop(assistant_index)
                assistant_index = None
            self._sync()
            if run_state == "waiting_for_approval":
                pending = self._pending(await self.runtime.list_approvals(run_id))
                if self.settings.auto_mode and pending:
                    # Client-side safety net: even if the run was created by an
                    # older gateway without server autopilot, keep the loop
                    # moving by granting the bounded approval now.
                    for item in pending:
                        approval_id = str(item.get("approval_id") or "")
                        if not approval_id:
                            continue
                        await self.runtime.resolve_approval(run_id, approval_id, approved=True)
                    self.pending_approvals = []
                    self._append(
                        "system",
                        "Autopilot granted "
                        + ", ".join(str(item.get("approval_id") or "") for item in pending)
                        + " and continued.",
                        persist=False,
                    )
                    self._streaming = False
                    await self._run_turn(
                        prompt,
                        append_user=False,
                        auto_turns=auto_turns + 1,
                        mode=mode,
                    )
                    return
                self._set_mascot("alert")
                self.pending_approvals = pending
                self._turn_ready = False
                self._sync()
                return
            if run_state == "paused":
                self._set_mascot("idle")
                self._turn_ready = True
                self._append("system", "Coding run paused. Use /next to retry or continue this run.", persist=False)
                return
            try:
                auto_budget = max(1, int(os.environ.get("BEAST_TLI_MAX_AUTO_TURNS", "48")))
            except ValueError:
                auto_budget = 48
            if auto_turns < auto_budget:
                # Planner turns are an internal implementation detail. Keep
                # advancing until an answer, terminal state, or approval is
                # reached instead of making the operator repeatedly type /next.
                self._streaming = False
                await self._run_turn(
                    prompt,
                    append_user=False,
                    auto_turns=auto_turns + 1,
                    mode=mode,
                )
                return
            self._set_mascot("idle")
            self._turn_ready = True
            self._append(
                "system",
                f"Paused after {auto_budget} automatic turns (run state: {run_state}). Use /next to continue.",
                persist=False,
            )
        except Exception as exc:
            if assistant_index is not None:
                if assistant:
                    partial_metadata = {
                        "run_id": run_id,
                        "receipt_ids": receipts,
                        "incomplete": True,
                    }
                    self.transcript_entries[assistant_index]["metadata"] = partial_metadata
                    self.store.append("assistant", assistant, metadata=partial_metadata)
                else:
                    self.transcript_entries.pop(assistant_index)
            if isinstance(exc, RuntimeTurnUnconfirmed):
                self._turn_ready = False
                self._set_mascot("idle")
                self._append("system", str(exc), persist=False)
            else:
                self._set_mascot("alert")
                self._append("error", f"BEAST coding turn failed: {exc}")
        finally:
            self._streaming = False


def run(*, workspace: str | Path | None = None, base_url: str | None = None, engine: str | None = None) -> None:
    from app.kernel.agents.direct_coder_defaults import apply_direct_coder_env_defaults

    apply_direct_coder_env_defaults()
    root = Path(workspace or os.environ.get("BEAST_WORKSPACE") or os.getcwd()).expanduser().resolve()
    BeastCoderApp(workspace=root, base_url=base_url, engine=engine).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="BEAST Coder terminal interface")
    parser.add_argument("--workspace", required=True, help="Explicit coding workspace")
    parser.add_argument("--gateway-url", default=os.environ.get("BEAST_GATEWAY_URL", "http://127.0.0.1:8101"))
    parser.add_argument(
        "--engine",
        choices=("direct_coder", "typed_planner"),
        default=None,
        help="Coding engine (default: direct_coder). Use typed_planner for the heuristic/NIM planner path.",
    )
    args = parser.parse_args()
    run(workspace=args.workspace, base_url=args.gateway_url, engine=args.engine)


if __name__ == "__main__":
    main()
