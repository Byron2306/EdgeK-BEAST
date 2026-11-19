from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.cli.api import BeastApiClient


def test_stream_live_turn_sends_governed_context_overrides_to_provider(
    tmp_path: Path, monkeypatch
) -> None:
    original = (
        "def service():\n"
        "    hidden = 'original-body'\n"
        "    return hidden\n"
    )
    override = (
        "def service():\n"
        "    ...  # [beast-lcz: body elided 2 lines]\n"
    )
    (tmp_path / "service.py").write_text(original, encoding="utf-8")
    captured: dict = {}

    async def fake_stream_chat_completion(self, provider, messages, **kwargs):
        captured["provider"] = provider
        captured["messages"] = messages
        captured["context_files"] = kwargs.get("context_files")
        yield {"type": "token", "text": "ok"}
        yield {"type": "provider_done", "completed": True}

    monkeypatch.setattr(
        BeastApiClient, "stream_chat_completion", fake_stream_chat_completion
    )
    client = BeastApiClient("http://offline.invalid", workspace=tmp_path)

    async def collect_stream():
        return [
            event
            async for event in client.stream_live_turn(
                "adjust service arithmetic",
                [],
                provider="ollama",
                model="qwen2.5:3b",
                context_files=["service.py"],
                context_overrides={"service.py": override},
                governance_level="ide_agent_session",
                action_ir_required=True,
            )
        ]

    events = asyncio.run(collect_stream())

    rendered = json.dumps(captured["messages"], sort_keys=True)
    assert "body elided" in rendered
    assert "original-body" not in rendered
    assert captured["context_files"] == ["service.py"]
    compute = next(
        event
        for event in events
        if event.get("type") == "compute"
        and "transformed_files" in (event.get("context") or {})
    )
    assert compute["context"]["transformed_files"] == 1
    assert compute["context"]["policy"] == "governed_transformed_selected_context"
    assert any(
        event.get("type") == "token" and event.get("text") == "ok" for event in events
    )
