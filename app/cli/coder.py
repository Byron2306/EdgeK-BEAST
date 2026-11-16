"""Focused Claude Code-style terminal interface for the BEAST coding runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static

from app.cli.coder_client import CoderRuntimeClient, RuntimeClientError
from app.cli.coder_state import (
    REQUIRED_COMMANDS,
    CoderSettings,
    ConversationStore,
    parse_slash_command,
    project_runtime_event,
)
from app.cli.ui import (
    BEAST_ACID,
    BEAST_BORDER,
    BEAST_DEEP,
    BEAST_GREEN,
    BEAST_MUTED,
    BEAST_PANEL,
    BEAST_PANEL_ALT,
    BEAST_TEXT,
    BEAST_WARN,
    beast_wordmark,
    sprite_mascot,
)

RuntimeFactory = Callable[[Path], CoderRuntimeClient]


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


class BeastCoderApp(App[None]):
    """A single-purpose coding conversation over BEAST's durable AgentRuns."""

    AUTO_FOCUS = "#coder-input"
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
        height: 17;
        background: {BEAST_PANEL};
        border-bottom: solid {BEAST_BORDER};
        padding: 0 2;
    }}
    #coder-wordmark {{ width: 2fr; height: 8; padding-top: 1; }}
    #coder-mascot {{ width: 42; height: 16; content-align: center middle; }}
    #coder-identity {{
        height: 3;
        padding: 0 2;
        background: {BEAST_PANEL_ALT};
        color: {BEAST_GREEN};
        border-bottom: solid {BEAST_BORDER};
    }}
    #coder-body {{ height: 1fr; min-height: 0; }}
    #conversation-scroll {{ width: 3fr; height: 1fr; min-height: 0; padding: 1 2; scrollbar-color: {BEAST_GREEN}; }}
    #coder-transcript, #coder-inline-tools {{ height: auto; }}
    #coder-inline-tools {{ display: none; }}
    #coder-beastie {{
        display: none;
        width: 100%;
        height: 16;
        content-align: center middle;
    }}
    #tool-scroll {{
        display: none;
        width: 1fr;
        min-width: 32;
        padding: 1;
        background: {BEAST_PANEL};
        border-left: solid {BEAST_BORDER};
        scrollbar-color: {BEAST_GREEN};
    }}
    #coder-input {{
        height: 3;
        border: tall {BEAST_BORDER};
        background: {BEAST_PANEL_ALT};
        color: {BEAST_TEXT};
    }}
    #coder-input:focus {{ border: tall {BEAST_ACID}; }}

    Screen.compact #coder-header {{ height: 10; padding: 0 1; }}
    Screen.compact #coder-wordmark {{ width: 46; height: 8; padding-top: 1; }}
    Screen.compact #coder-mascot {{ width: 1fr; height: 9; }}
    Screen.branding-compact #coder-wordmark {{ width: 10; }}
    Screen.tiny #coder-header {{ height: 7; }}
    Screen.tiny #coder-wordmark {{ width: 10; height: 5; padding-top: 0; }}
    Screen.tiny #coder-mascot {{ width: 1fr; height: 6; }}
    Screen.branding-hidden #coder-header {{ display: none; }}
    Screen.compact #coder-identity {{
        height: 1;
        padding: 0 1;
        border-bottom: none;
    }}
    Screen.compact #conversation-scroll {{ width: 1fr; padding: 0 1; }}
    Screen.has-tools #tool-scroll {{ display: block; }}
    Screen.compact #tool-scroll {{ display: none; }}
    Screen.compact.has-tools #coder-inline-tools {{ display: block; }}
    Screen.beastie-expanded #coder-beastie {{ display: block; }}
    """

    def __init__(
        self,
        *,
        workspace: str | Path,
        base_url: str | None = None,
        runtime_client: CoderRuntimeClient | Any | None = None,
        runtime_client_factory: RuntimeFactory | None = None,
    ) -> None:
        super().__init__()
        root = Path(workspace).expanduser().resolve()
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
        self.mascot_state = "idle"
        self._mascot_frame = 0
        self._branding_compact = False
        self._mascot_cells = 34
        self._mascot_rows = 14
        self.beastie_expanded = False
        self._welcome_active = True
        self._compact_layout = True
        self.exit_requested = False
        self._streaming = False
        self.subject = ""
        self._last_stream_paint = 0.0

    def _new_runtime(self, workspace: Path) -> CoderRuntimeClient:
        if self._runtime_client_factory is not None:
            return self._runtime_client_factory(workspace)
        return CoderRuntimeClient(self.base_url, workspace)

    def compose(self) -> ComposeResult:
        with Horizontal(id="coder-header"):
            yield Static(beast_wordmark(), id="coder-wordmark")
            yield Static(
                sprite_mascot(self.mascot_state, self._mascot_frame),
                id="coder-mascot",
            )
        yield Static(self._identity_text(), id="coder-identity")
        with Horizontal(id="coder-body"):
            with VerticalScroll(id="conversation-scroll"):
                yield Static(self._transcript_text(), id="coder-transcript")
                yield Static(self._tools_text(), id="coder-inline-tools")
                yield Static(
                    sprite_mascot(self.mascot_state, self._mascot_frame),
                    id="coder-beastie",
                )
            with VerticalScroll(id="tool-scroll"):
                yield Static(self._tools_text(), id="coder-tools")
        yield Input(
            placeholder="Ask BEAST to inspect, edit, or verify code — /help for commands",
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
        if not self.is_mounted or self._streaming:
            return
        editor = self.query_one("#coder-input", Input)
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
        self.screen.set_class(bool(self.tool_entries), "has-tools")
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
        self.query_one("#coder-wordmark", Static).update(
            beast_wordmark(self._branding_compact, self._mascot_frame)
        )
        self.query_one("#coder-mascot", Static).update(
            sprite_mascot(
                self.mascot_state,
                self._mascot_frame,
                target_cells=self._mascot_cells,
                target_rows=self._mascot_rows,
            )
        )

    async def on_unmount(self) -> None:
        await self.runtime.aclose()

    def _identity_text(self) -> Text:
        text = Text()
        if self._compact_layout:
            text.append("BEAST ", style=f"bold {BEAST_GREEN}")
            text.append(self.mascot_state.upper(), style=f"bold {BEAST_ACID}")
            width = int(getattr(self.size, "width", 0) or 0)
            if width >= 50:
                text.append("  ·  ", style=BEAST_MUTED)
                text.append(self.settings.provider, style=BEAST_ACID)
                text.append("/", style=BEAST_MUTED)
                text.append(self.settings.model, style=BEAST_WARN)
            if width >= 72:
                text.append("  ·  ", style=BEAST_MUTED)
                text.append(self.settings.workspace.name, style=BEAST_GREEN)
            return text
        text.append("WORKSPACE ", style=f"bold {BEAST_MUTED}")
        text.append(str(self.settings.workspace), style=f"bold {BEAST_GREEN}")
        text.append("   PROVIDER ", style=f"bold {BEAST_MUTED}")
        text.append(self.settings.provider, style=f"bold {BEAST_ACID}")
        text.append("   MODEL ", style=f"bold {BEAST_MUTED}")
        text.append(self.settings.model, style=f"bold {BEAST_WARN}")
        text.append("   STATE ", style=f"bold {BEAST_MUTED}")
        text.append(self.mascot_state.upper(), style=f"bold {BEAST_GREEN}")
        return text

    def _transcript_text(self) -> Text:
        text = Text()
        if not self.transcript_entries:
            text.append("BEAST Coder ready. Runtime actions remain governed.\n", style=BEAST_MUTED)
            text.append("Type a coding request or /help.", style=BEAST_GREEN)
            return text
        styles = {
            "user": f"bold {BEAST_ACID}",
            "assistant": BEAST_TEXT,
            "system": BEAST_MUTED,
            "error": "bold #D35E68",
        }
        labels = {"user": "YOU", "assistant": "BEAST", "system": "SYSTEM", "error": "ERROR"}
        for index, item in enumerate(self.transcript_entries):
            role = str(item.get("role") or "system")
            text.append(f"{labels.get(role, role.upper())}> ", style=styles.get(role, BEAST_MUTED))
            text.append(str(item.get("content") or ""), style=styles.get(role, BEAST_TEXT))
            if index < len(self.transcript_entries) - 1:
                text.append("\n\n")
        return text

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
            if details:
                compact = json.dumps(details, sort_keys=True, default=str)
                text.append(f"  {compact[:420]}\n", style=BEAST_MUTED)
            text.append("\n")
        return text

    def _sync(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#coder-identity", Static).update(self._identity_text())
        self.query_one("#coder-transcript", Static).update(self._transcript_text())
        self.query_one("#coder-tools", Static).update(self._tools_text())
        self.query_one("#coder-inline-tools", Static).update(self._tools_text())
        self.screen.set_class(bool(self.tool_entries), "has-tools")
        self.screen.set_class(
            not self._welcome_active
            and self.size.height < self.BRANDING_MIN_CONTENT_HEIGHT,
            "branding-hidden",
        )
        # Textual can update Static content before its new wrapped height has
        # been measured. A single scroll_end during that frame uses stale
        # virtual_size and leaves the latest tokens below the viewport.
        with suppress(Exception):
            self.query_one("#coder-transcript", Static).refresh(layout=True)
            self.query_one("#conversation-scroll", VerticalScroll).refresh(layout=True)
            self.call_after_refresh(self._scroll_transcript_end)
            if not getattr(self, "_follow_scroll_pending", False):
                self._follow_scroll_pending = True
                self.set_timer(0.07, self._scroll_transcript_after_layout)

    def _scroll_transcript_after_layout(self) -> None:
        self._follow_scroll_pending = False
        self._scroll_transcript_end()

    def _scroll_transcript_end(self) -> None:
        with suppress(Exception):
            viewport = self.query_one("#conversation-scroll", VerticalScroll)
            viewport.scroll_end(animate=False, force=True)

    def _animate_mascot(self) -> None:
        self._mascot_frame = (self._mascot_frame + 1) % 120
        if self.is_mounted:
            frame = sprite_mascot(
                self.mascot_state,
                self._mascot_frame,
                target_cells=self._mascot_cells,
                target_rows=self._mascot_rows,
            )
            self.query_one("#coder-wordmark", Static).update(
                beast_wordmark(self._branding_compact, self._mascot_frame)
            )
            self.query_one("#coder-mascot", Static).update(frame)
            self.query_one("#coder-beastie", Static).update(
                sprite_mascot(self.mascot_state, self._mascot_frame)
            )

    def _set_mascot(self, state: str) -> None:
        self.mascot_state = state
        self._sync()

    def _append(self, role: str, content: str, *, persist: bool = True, metadata: dict[str, Any] | None = None) -> None:
        row = {"role": role, "content": str(content), "metadata": dict(metadata or {})}
        self.transcript_entries.append(row)
        if persist:
            self.store.append(role, str(content), metadata=metadata)
        self._sync()

    def _save_settings(self, **changes: Any) -> None:
        self.settings = replace(self.settings, **changes)
        self.store.save_settings(self.settings)
        self._sync()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = sanitize_terminal_text(event.value).strip()
        event.input.value = ""
        event.input.focus()
        if value:
            await self.submit_text(value)
        if event.input.is_mounted:
            event.input.focus()

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
            try:
                command = parse_slash_command(value)
                await self._run_command(command.name, command.argument)
            except (ValueError, RuntimeClientError, json.JSONDecodeError) as exc:
                self._set_mascot("alert")
                self._append("error", str(exc))
            return
        await self._run_turn(value)

    async def _run_command(self, name: str, argument: str) -> None:
        if name == "help":
            self._append(
                "system",
                "Commands: " + "  ".join(f"/{item}" for item in REQUIRED_COMMANDS),
                persist=False,
            )
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
        if name == "clear":
            # Clearing the visible transcript alone would retain the old agent session.
            # Rotate session identity so the next turn cannot silently reuse it.
            self._save_settings(session_id="", last_run_id="")
            self.store.clear()
            self.transcript_entries.clear()
            self.tool_entries.clear()
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
        if name in {"budget", "thinking", "permission", "compact"}:
            self._append("system", f"/{name}: not wired to an enforceable BEAST runtime contract. No setting was changed. Backend support and receipts are required before enabling this control.", persist=False)
            return
        if name == "exit":
            self.exit_requested = True
            self.exit()
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
            new_settings = CoderSettings(
                workspace=Path(argument),
                provider=self.settings.provider,
                model=self.settings.model,
            )
            if self._injected_runtime and self._runtime_client_factory is None:
                raise ValueError("workspace switching is unavailable for the injected runtime client")
            await self.runtime.aclose()
            self.store = ConversationStore(new_settings.workspace)
            self.settings = new_settings
            self.store.save_settings(self.settings)
            self.runtime = self._new_runtime(new_settings.workspace)
            self.transcript_entries = self.store.messages()
            self.tool_entries.clear()
            self._append("system", f"Workspace selected: {new_settings.workspace}")
            return
        if name == "status":
            status = await self.runtime.runtime_status(self.settings.last_run_id)
            self._append(
                "system",
                f"Workspace: {self.settings.workspace}\nProvider: {self.settings.provider}\nModel: {self.settings.model}\n"
                + self._format_mapping("Runtime", status),
                persist=False,
            )

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

    @staticmethod
    def _is_conversational_turn(prompt: str) -> bool:
        """Conservative no-tool admission for greetings and explanation requests.

        All other prompts continue through governed AgentRuns. This is not an
        authorization classifier: the direct lane has zero tool capabilities.
        """
        text = str(prompt or "").strip().lower()
        return bool(re.match(
            r"^(?:hi|hello|hey|good morning|good evening|thanks|thank you|"
            r"what is |what are |explain |describe |define |how does |"
            r"tell me about |why does |can you explain )\b", text
        ))

    @staticmethod
    def _explicit_source_path(prompt: str) -> str | None:
        """Admit only explicit, single-file, read-only source questions."""
        text = str(prompt or "")
        # Negative safety instructions are not requests to mutate files.
        # Remove only recognized prohibitions before checking action verbs.
        action_text = re.sub(
            r"\b(?:do\s+not|don't|dont|never|without)\s+"
            r"(?:attempting\s+to\s+|trying\s+to\s+)?"
            r"(?:edit|modify|write|delete|remove|rename|execute|run|fix|patch|replace|create|commit|deploy)\b",
            "",
            text,
            flags=re.I,
        )
        if re.search(
            r"\b(?:edit|modify|write|delete|remove|rename|execute|run|fix|patch|replace|create|commit|deploy)\b",
            action_text,
            re.I,
        ):
            return None
        if not re.search(r"\b(?:read|find|inspect|explain|describe|summarize|show)\b", text, re.I):
            return None
        paths = re.findall(r"(?<![\w./-])(?:[\w.-]+/)+[\w.-]+\.(?:py|js|jsx|ts|tsx|json|md|css|html|yaml|yml|toml)(?![\w./-])", text)
        return paths[0] if len(paths) == 1 else None

    async def _run_turn(self, prompt: str) -> None:
        if self._streaming:
            raise RuntimeClientError("a BEAST coding turn is already running")
        self._streaming = True
        self._set_mascot("working")
        self._append("user", prompt)
        assistant = ""
        assistant_index: int | None = None
        receipts: list[str] = []
        run_id = ""
        try:
            source_path = self._explicit_source_path(prompt)
            source_context = None
            if source_path and self.settings.provider in {"ollama", "local_ollama"}:
                source_context = self.runtime.read_local_source(source_path)
            if (self.settings.provider in {"ollama", "local_ollama"}
                    and (self._is_conversational_turn(prompt) or source_context is not None)):
                assistant_index = len(self.transcript_entries)
                self.transcript_entries.append({"role": "assistant", "content": "",
                                                "metadata": {"streaming": True, "lane": "local_chat"}})
                self._sync()
                async for token in self.runtime.stream_local_chat(
                    prompt, self.settings.model, source_context=source_context
                ):
                    assistant += token
                    now = time.monotonic()
                    if now - self._last_stream_paint >= 0.12:
                        self.transcript_entries[assistant_index]["content"] = assistant
                        self._last_stream_paint = now
                        self._sync()
                if not assistant.strip():
                    raise RuntimeClientError("Local model returned no assistant text")
                metadata = {"lane": "local_source_read" if source_context is not None else "local_chat",
                            "source_path": source_path if source_context is not None else None,
                            "provider": self.settings.provider, "model": self.settings.model}
                self.transcript_entries[assistant_index] = {
                    "role": "assistant", "content": assistant, "metadata": metadata}
                self.store.append("assistant", assistant, metadata=metadata)
                self._sync()
                self._set_mascot("finished")
                return
            session_id = self.settings.session_id
            if not session_id:
                session = await self.runtime.ensure_session(
                    self.settings.provider, self.settings.model
                )
                session_id = str(session.get("session_id") or "")
                self._save_settings(session_id=session_id)
            run = await self.runtime.start_run(
                session_id, prompt, self.settings.provider, self.settings.model
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
            async for runtime_event in self.runtime.follow_run(run_id):
                projected = project_runtime_event(runtime_event)
                if projected.kind == "token":
                    assistant += projected.text
                    # Coalesce token updates. Rebuilding Rich text on every token
                    # competes with the mascot animation and terminal SSH writes.
                    now = time.monotonic()
                    if now - self._last_stream_paint >= 0.12:
                        self.transcript_entries[assistant_index]["content"] = assistant
                        self._last_stream_paint = now
                        self._sync()
                elif projected.kind in {"tool_call", "tool_result"}:
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
                    self.transcript_entries[assistant_index]["content"] = assistant
                    if projected.receipt.get("observation_id"):
                        receipts.append(projected.receipt["observation_id"])
                    self._sync()
            if not assistant.strip():
                raise RuntimeError("AgentRun stream closed without a user-facing model answer; server state not verified")
            final_text = assistant
            final_metadata = {"run_id": run_id, "receipt_ids": receipts}
            self.transcript_entries[assistant_index] = {
                "role": "assistant",
                "content": final_text,
                "metadata": final_metadata,
            }
            self.store.append("assistant", final_text, metadata=final_metadata)
            self._sync()
            self._set_mascot("finished")
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
            self._set_mascot("alert")
            self._append("error", f"BEAST coding turn failed: {exc}")
        finally:
            self._streaming = False


def run(*, workspace: str | Path | None = None, base_url: str | None = None) -> None:
    root = Path(workspace or os.environ.get("BEAST_WORKSPACE") or os.getcwd()).expanduser().resolve()
    BeastCoderApp(workspace=root, base_url=base_url).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="BEAST Coder terminal interface")
    parser.add_argument("--workspace", required=True, help="Explicit coding workspace")
    parser.add_argument("--gateway-url", default=os.environ.get("BEAST_GATEWAY_URL", "http://127.0.0.1:8101"))
    args = parser.parse_args()
    run(workspace=args.workspace, base_url=args.gateway_url)


if __name__ == "__main__":
    main()
