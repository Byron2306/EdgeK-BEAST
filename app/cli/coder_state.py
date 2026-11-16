"""Persistent state and event projection for the BEAST Coder TLI."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.cli.coder_client import RuntimeEvent


REQUIRED_COMMANDS = (
    "help",
    "subject",
    "context",
    "compact",
    "budget",
    "thinking",
    "permission",
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

    @staticmethod
    def _read_object(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return default

    def _atomic_write(self, path: Path, payload: Any) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
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
    if event.event == "agent.model.delta":
        return ProjectedEvent("token", str(payload.get("text") or ""), sequence)
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
    status = str(payload.get("status") or data.get("state") or "")
    text = str(payload.get("text") or payload.get("message") or event.event)
    return ProjectedEvent("status", text, sequence, status=status, details=payload)
