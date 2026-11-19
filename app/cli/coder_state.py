"""Persistent state and event projection for the BEAST Coder TLI."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.cli.coder_client import RuntimeEvent


REQUIRED_COMMANDS = (
    "help",
    "copy",
    "ask",
    "review",
    "edit",
    "agent",
    "subject",
    "context",
    "compact",
    "budget",
    "thinking",
    "permission",
    "expand",
    "less",
    "beastie",
    "model",
    "provider",
    "skills",
    "mcp",
    "tools",
    "workspace",
    "status",
    "next",
    "auto",
    "diff",
    "apply",
    "agents",
    "sessions",
    "new",
    "rename",
    "approvals",
    "approve",
    "clear",
    "exit",
)

COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("RUN", (
        ("agent", "Autonomous coding loop (default for plain text)"),
        ("ask", "Read-only question about the workspace"),
        ("review", "Review an attached file, read-only"),
        ("edit", "Make one bounded edit"),
        ("next", "Advance the current run one turn"),
        ("auto", "Autopilot on/off (workspace-bounded approvals)"),
        ("apply", "Apply the last verified isolated diff to the workspace"),
        ("diff", "Toggle the live red/green diff panel"),
        ("ide", "Probe IDE compatibility: languages, notebooks, SSH, containers, extensions"),
        ("agents", "Open the agent/swarm menu (or press ↓)"),
    )),
    ("CONTEXT", (
        ("context", "Show visible history and session identity"),
        ("compact", "Archive and compress the visible history"),
        ("budget", "Show context budget and token estimate"),
        ("subject", "Set a short subject for this session"),
        ("btw", "Add a side context note without starting an agent run"),
        ("permission", "Nuke or restore per-call approval prompts (/permission off|on)"),
        ("clear", "Rotate the session and clear the transcript"),
    )),
    ("SESSIONS", (
        ("sessions", "List saved sessions"),
        ("new", "Archive this conversation and start a new session"),
        ("rename", "Rename the current session"),
    )),
    ("RUNTIME", (
        ("provider", "List or select a provider"),
        ("model", "Show or select a model"),
        ("skills", "List or invoke a Meta Skill"),
        ("mcp", "Inspect MCP or call a tool"),
        ("tools", "List tools for the last run"),
        ("status", "Runtime status for the last run"),
        ("workspace", "Show or switch the workspace"),
        ("approvals", "Show pending approvals"),
        ("approve", "Approve a pending action"),
    )),
    ("VIEW", (
        ("expand", "Expand runtime event details"),
        ("less", "Collapse runtime event details"),
        ("beastie", "Expand the original BEAST mascot"),
        ("copy", "Copy the last run to the clipboard"),
        ("exit", "Exit the TLI"),
    )),
)



@dataclass(frozen=True)
class SlashCommand:
    name: str
    argument: str = ""


def parse_slash_command(text: str) -> SlashCommand:
    value = str(text or "").strip()
    if not value.startswith("/"):
        raise ValueError("slash command must start with /")
    name, _, argument = value[1:].partition(" ")
    normalized = name.strip().lower()
    if normalized not in REQUIRED_COMMANDS:
        raise ValueError(f"unknown command: /{normalized}")
    return SlashCommand(normalized, argument.strip())


@dataclass(frozen=True)
class CoderSettings:
    workspace: Path
    provider: str = "ollama"
    model: str = "beast-auto"
    session_id: str = ""
    last_run_id: str = ""
    auto_mode: bool = True
    session_title: str = ""

    def __post_init__(self) -> None:
        workspace = Path(self.workspace).expanduser().resolve()
        if not workspace.is_dir():
            raise ValueError(f"workspace must be an existing directory: {workspace}")
        object.__setattr__(self, "workspace", workspace)
        object.__setattr__(self, "provider", str(self.provider or "ollama").strip())
        object.__setattr__(self, "model", str(self.model or "beast-auto").strip())

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workspace"] = str(self.workspace)
        return payload


class ConversationStore:
    """Workspace-scoped Coder settings and visible transcript."""

    def __init__(self, workspace: str | Path) -> None:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"workspace must be an existing directory: {root}")
        self.workspace = root
        self.state_dir = root / ".beast" / "coder"
        self.settings_path = self.state_dir / "settings.json"
        self.conversation_path = self.state_dir / "conversation.json"
        self.sessions_dir = self.state_dir / "sessions"

    @staticmethod
    def _read_object(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return default

    def _atomic_write(self, path: Path, payload: Any) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=self.state_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def save_settings(self, settings: CoderSettings) -> None:
        if settings.workspace != self.workspace:
            raise ValueError("settings workspace does not match conversation store")
        self._atomic_write(self.settings_path, settings.to_dict())

    def load_settings(self) -> CoderSettings:
        payload = self._read_object(self.settings_path, {})
        if not isinstance(payload, dict):
            payload = {}
        return CoderSettings(
            workspace=self.workspace,
            provider=str(payload.get("provider") or "ollama"),
            model=str(payload.get("model") or "beast-auto"),
            session_id=str(payload.get("session_id") or ""),
            last_run_id=str(payload.get("last_run_id") or ""),
            auto_mode=bool(payload.get("auto_mode", True)),
            session_title=str(payload.get("session_title") or ""),
        )

    def messages(self) -> list[dict[str, Any]]:
        payload = self._read_object(self.conversation_path, {"messages": []})
        rows = payload.get("messages") if isinstance(payload, dict) else []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def append(
        self, role: str, content: str, *, metadata: dict[str, Any] | None = None
    ) -> None:
        rows = self.messages()
        rows.append(
            {
                "role": str(role),
                "content": str(content),
                "metadata": dict(metadata or {}),
            }
        )
        self._atomic_write(self.conversation_path, {"messages": rows})

    def clear(self) -> None:
        self._atomic_write(self.conversation_path, {"messages": []})

    def replace_messages(self, rows: list[dict[str, Any]]) -> None:
        self._atomic_write(self.conversation_path, {"messages": [dict(row) for row in rows]})

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
        return cleaned[:48] or "session"

    def archive_session(self, title: str = "") -> dict[str, Any] | None:
        """Move the visible transcript into a durable, resumable session file."""
        rows = self.messages()
        if not rows:
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        session_id = f"{stamp}-{self._slug(title)}"
        path = self.sessions_dir / f"{session_id}.json"
        self._atomic_write(path, {
            "session_id": session_id,
            "title": str(title or session_id)[:120],
            "created": stamp,
            "workspace": str(self.workspace),
            "messages": rows,
        })
        self.clear()
        return {"session_id": session_id, "title": str(title or session_id)[:120],
                "messages": len(rows), "path": str(path)}

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        if not self.sessions_dir.is_dir():
            return sessions
        for path in sorted(self.sessions_dir.glob("*.json"), reverse=True):
            payload = self._read_object(path, {})
            if not isinstance(payload, dict):
                continue
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            sessions.append({
                "session_id": str(payload.get("session_id") or path.stem),
                "title": str(payload.get("title") or path.stem),
                "created": str(payload.get("created") or ""),
                "messages": len(messages),
            })
        return sessions[:50]

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        candidate = self.sessions_dir / f"{Path(session_id).name}.json"
        payload = self._read_object(candidate, {})
        if not isinstance(payload, dict):
            return None
        rows = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        self.replace_messages([dict(row) for row in rows if isinstance(row, dict)])
        return payload



@dataclass(frozen=True)
class ProjectedEvent:
    kind: str
    text: str = ""
    sequence: int = 0
    status: str = ""
    tool_id: str = ""
    executed: bool = False
    success: bool = False
    receipt: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


def project_runtime_event(event: RuntimeEvent) -> ProjectedEvent:
    data = event.data if isinstance(event.data, dict) else {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    sequence = int(data.get("sequence") or event.event_id or 0)
    if event.event == "agent.planner.review_incomplete":
        coverage = str(payload.get("coverage") or "")
        error = str(payload.get("error") or "No grounded file answer was accepted.")
        return ProjectedEvent("answer_error", error + (f" Coverage: {coverage}." if coverage else ""),
                              sequence, details=payload)
    if event.event == "agent.run.advisory":
        return ProjectedEvent("advisory", str(payload.get("text") or ""), sequence, details=payload)
    if event.event.startswith("agent.integration.") or event.event == "agent.stream.interception":
        capability = str(payload.get("capability") or "stream.interception")
        if event.event == "agent.stream.interception":
            default_status = "fired" if payload.get("upstream_cancel_requested") is True else "skipped"
        else:
            default_status = event.event.rsplit(".", 1)[-1]
        status = str(payload.get("status") or default_status)
        reason = str(payload.get("reason") or payload.get("stop_reason") or "")
        stage = str(payload.get("stage") or "")
        text = " · ".join(value for value in (status, stage, reason) if value)
        checks = payload.get("checks")
        if capability == "quality_cascade" and isinstance(checks, list):
            issues = [
                f"{check.get('name')} ({check.get('status')}): {check.get('reason')}"
                for check in checks[:16]
                if isinstance(check, dict) and check.get("status") in {"failed", "warning", "skipped"}
            ]
            if issues:
                text += " · " + " | ".join(issues)
        return ProjectedEvent("integration", text, sequence, status=status, tool_id=capability,
                              executed=status == "fired" and stage in {"execution", "postflight"},
                              success=status == "fired", details=payload)
    if event.event == "agent.model.delta":
        return ProjectedEvent("token", str(payload.get("text") or ""), sequence)
    if event.event == "agent.model.reasoning":
        return ProjectedEvent(
            "reasoning",
            str(payload.get("text") or ""),
            sequence,
            status=str(payload.get("status") or "thinking"),
            details=payload,
        )
    if event.event == "agent.tool.started":
        tool_id = str(payload.get("tool_id") or "BEAST governed tool")
        return ProjectedEvent(
            "tool_call",
            f"Calling {tool_id}",
            sequence,
            status="running",
            tool_id=tool_id,
            details={"arguments": payload.get("arguments") or {}},
        )
    if event.event in {"agent.tool.completed", "agent.tool.failed"}:
        observation = (
            payload.get("observation")
            if isinstance(payload.get("observation"), dict)
            else {}
        )
        tool_id = str(observation.get("tool_id") or "BEAST governed tool")
        observation_id = str(observation.get("observation_id") or "")
        evidence_digest = str(observation.get("evidence_digest") or "")
        receipted = bool(observation_id and evidence_digest)
        runtime_status = str(observation.get("status") or "")
        completed = event.event == "agent.tool.completed" and runtime_status == "completed"
        status = runtime_status or ("completed" if completed else "failed")
        if not receipted:
            status = "unverified"
        error = str(observation.get("error") or "")
        text = error or f"{tool_id} {status}"
        if not receipted:
            text = f"{tool_id} result missing durable observation receipt"
        return ProjectedEvent(
            "tool_result",
            text,
            sequence,
            status=status,
            tool_id=tool_id,
            executed=receipted,
            success=bool(receipted and completed),
            receipt=(
                {
                    "observation_id": observation_id,
                    "evidence_digest": evidence_digest,
                }
                if receipted
                else {}
            ),
            details=(
                observation.get("result")
                if isinstance(observation.get("result"), dict)
                else {}
            ),
        )
    if event.event == "agent.worktree.diff_ready":
        files = payload.get("files") if isinstance(payload.get("files"), list) else []
        diff = str(payload.get("diff") or "")
        added = int(payload.get("added") or 0)
        removed = int(payload.get("removed") or 0)
        return ProjectedEvent(
            "diff",
            f"{len(files)} file(s) · +{added} −{removed}",
            sequence,
            status="ready",
            tool_id="worktree.diff",
            success=True,
            details={**payload, "diff": diff, "files": [str(item) for item in files]},
        )
    if event.event == "agent.worktree.applied":
        applied = payload.get("applied") if isinstance(payload.get("applied"), list) else []
        paths = [str(item.get("path") or "") for item in applied if isinstance(item, dict)]
        return ProjectedEvent(
            "diff",
            f"Applied to workspace: {', '.join(paths[:6]) or 'no files'}",
            sequence,
            status="applied",
            tool_id="worktree.apply",
            executed=True,
            success=True,
            details={**payload, "files": paths},
        )
    if event.event == "agent.worktree.apply_blocked":
        return ProjectedEvent(
            "diff",
            f"Apply blocked: {str(payload.get('reason') or 'unsafe delivery')}",
            sequence,
            status="blocked",
            tool_id="worktree.apply",
            executed=True,
            success=False,
            details=payload,
        )
    status = str(payload.get("status") or data.get("state") or "")
    text = str(payload.get("text") or payload.get("message") or event.event)
    return ProjectedEvent("status", text, sequence, status=status, details=payload)
